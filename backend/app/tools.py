"""Agent 可用工具集（A-工具扩展 / D-角色权限）。

设计约定：
1. 工具函数只做"参数接收 → 调 services 业务层 → 包装结果"，不写业务规则；
2. 每个工具在 TOOL_ROLES 中声明可用角色，agent 节点按角色过滤 schema，
   tools_node 执行前还会二次校验，防止越权；
3. 工具签名统一为 tool_xxx(db, user, **args)，业务错误统一返回 {"error": ...}，
   由大模型转述给用户，不向用户抛异常。
"""
from sqlalchemy.orm import Session

from .models import Laboratory, User
from . import rag
from . import analytics
from . import services as svc

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
ALL_ROLES = (ROLE_STUDENT, ROLE_ADMIN)
ADMIN_ONLY = (ROLE_ADMIN,)

TOOLS_SCHEMA = [
    # ---------- 查询类（学生/管理员通用） ----------
    {
        "type": "function",
        "function": {
            "name": "list_labs",
            "description": "查询所有启用中的实验室列表（名称、位置、容量、开放时间）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lab_equipment",
            "description": "查询指定实验室的设备列表（含设备库存数量与状态）",
            "parameters": {
                "type": "object",
                "properties": {"lab_id": {"type": "integer", "description": "实验室ID"}},
                "required": ["lab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "查询某实验室某天的占用情况。若同时给出 start_time/end_time，"
                "会判断该时段是否可约；被占用时自动返回同实验室其他空闲时段和"
                "同时段空闲的备选实验室"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_id": {"type": "integer", "description": "实验室ID"},
                    "booking_date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "开始时间 HH:MM（可选）"},
                    "end_time": {"type": "string", "description": "结束时间 HH:MM（可选）"},
                },
                "required": ["lab_id", "booking_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rules",
            "description": "检索实验室使用规则、开放时间、预约须知等知识库文档",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索问题"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_equipment",
            "description": "按关键字跨实验室检索可预约设备（如 GPU、示波器、开发板），可指定 lab_id",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "设备名称关键字（可选）"},
                    "lab_id": {"type": "integer", "description": "限定实验室ID（可选）"},
                },
                "required": [],
            },
        },
    },
    # ---------- 我的预约：查询 / 取消 / 改约 ----------
    {
        "type": "function",
        "function": {
            "name": "list_my_bookings",
            "description": "查询当前用户的实验室预约记录及审核状态，可按状态过滤（pending/approved/rejected/cancelled）",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "description": "状态过滤，可选"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "取消当前用户本人的实验室预约（待审核/已通过可取消）。临期取消将扣信用分。",
            "parameters": {
                "type": "object",
                "properties": {"booking_id": {"type": "integer", "description": "预约ID"}},
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_booking",
            "description": (
                "修改当前用户本人的预约（改时间/实验室/用途/成员）。"
                "已通过的预约改约后会回到待审核状态。调用前需与用户确认新信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "integer", "description": "预约ID"},
                    "lab_id": {"type": "integer", "description": "新实验室ID（可选）"},
                    "booking_date": {"type": "string", "description": "新日期 YYYY-MM-DD（可选）"},
                    "start_time": {"type": "string", "description": "新开始时间 HH:MM（可选）"},
                    "end_time": {"type": "string", "description": "新结束时间 HH:MM（可选）"},
                    "purpose": {"type": "string", "description": "新用途（可选）"},
                    "members": {
                        "type": "array", "items": {"type": "string"},
                        "description": "团队成员用户名列表（不含本人，可选，传入即整体替换）",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": (
                "为当前用户提交实验室预约（待审核）。提交前必须已与用户确认实验室、"
                "日期、时段、用途；团队预约需提供成员用户名列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_id": {"type": "integer"},
                    "booking_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM"},
                    "end_time": {"type": "string", "description": "HH:MM"},
                    "purpose": {"type": "string", "description": "预约用途"},
                    "members": {
                        "type": "array", "items": {"type": "string"},
                        "description": "团队成员的用户名列表（不含预约人本人，可选）",
                    },
                },
                "required": ["lab_id", "booking_date", "start_time", "end_time", "purpose"],
            },
        },
    },
    # ---------- 设备级预约 ----------
    {
        "type": "function",
        "function": {
            "name": "book_equipment",
            "description": (
                "为当前用户预约某台/某类设备的使用时段。设备有数量库存，"
                "同时段在约数量不超过库存即可预约。调用前需与用户确认设备、日期、时段。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "equipment_id": {"type": "integer", "description": "设备ID"},
                    "booking_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM"},
                    "end_time": {"type": "string", "description": "HH:MM"},
                    "purpose": {"type": "string", "description": "使用用途"},
                },
                "required": ["equipment_id", "booking_date", "start_time", "end_time", "purpose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_equipment_booking",
            "description": "取消当前用户本人的设备预约",
            "parameters": {
                "type": "object",
                "properties": {"equipment_booking_id": {"type": "integer", "description": "设备预约ID"}},
                "required": ["equipment_booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_equipment_bookings",
            "description": "查询当前用户的设备预约记录",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "description": "active/cancelled，可选"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_booking",
            "description": (
                "为当前用户本人的已通过实验室预约到场签到。"
                "签到窗口为开始前15分钟到开始后15分钟；超时未签到会被系统自动释放并扣信用分。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"booking_id": {"type": "integer", "description": "预约ID"}},
                "required": ["booking_id"],
            },
        },
    },
    # ---------- 管理员专用 ----------
    {
        "type": "function",
        "function": {
            "name": "admin_list_bookings",
            "description": "【管理员】查询预约审核列表，可按状态过滤（默认返回最新20条）",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "description": "pending/approved/rejected，可选"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "admin_approve_booking",
            "description": "【管理员】通过指定的待审核预约",
            "parameters": {
                "type": "object",
                "properties": {"booking_id": {"type": "integer", "description": "预约ID"}},
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "admin_reject_booking",
            "description": "【管理员】驳回指定的待审核预约，可附驳回原因",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "integer", "description": "预约ID"},
                    "review_note": {"type": "string", "description": "驳回原因（可选）"},
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_booking_stats",
            "description": (
                "【管理员】数据分析：按指标与时间范围统计预约数据，"
                "用于回答'这周哪个实验室最忙''热门时段是几点''通过率/取消率多少'等问题。"
                "metric 可选 overview(综合看板)/lab_usage(实验室使用排名)/"
                "hot_slots(热门时段)/daily_trend(每日趋势)/status_distribution(状态分布)；"
                "range 可选 today/this_week/last_week/this_month/last_7_days/last_30_days。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "统计指标，默认 overview"},
                    "range": {"type": "string", "description": "时间范围，默认 this_week"},
                },
                "required": [],
            },
        },
    },
]

# 工具 -> 允许调用的角色。未列出的工具默认禁止一切调用（最小权限原则）。
TOOL_ROLES = {
    "list_labs": ALL_ROLES,
    "get_lab_equipment": ALL_ROLES,
    "check_availability": ALL_ROLES,
    "search_rules": ALL_ROLES,
    "search_equipment": ALL_ROLES,
    "list_my_bookings": ALL_ROLES,
    "cancel_booking": ALL_ROLES,
    "update_booking": ALL_ROLES,
    "create_booking": ALL_ROLES,
    "book_equipment": ALL_ROLES,
    "cancel_equipment_booking": ALL_ROLES,
    "list_my_equipment_bookings": ALL_ROLES,
    "confirm_booking": ALL_ROLES,
    "admin_list_bookings": ADMIN_ONLY,
    "admin_approve_booking": ADMIN_ONLY,
    "admin_reject_booking": ADMIN_ONLY,
    "query_booking_stats": ADMIN_ONLY,
}


def is_tool_allowed(tool_name: str, role: str) -> bool:
    return role in TOOL_ROLES.get(tool_name, ())


def schemas_for_role(role: str) -> list[dict]:
    """按角色返回工具声明：学生拿不到管理员工具，模型层面"看不到"也调不了。"""
    return [
        s for s in TOOLS_SCHEMA
        if role in TOOL_ROLES.get(s["function"]["name"], ())
    ]


# ---------------- 工具实现（薄封装） ----------------
def tool_list_labs(db: Session, user: User, **_) -> dict:
    labs = db.query(Laboratory).filter(Laboratory.status == "enabled").order_by(Laboratory.id).all()
    return {"labs": [svc.lab_to_dict(l) for l in labs]}


def tool_get_lab_equipment(db: Session, user: User, lab_id: int, **_) -> dict:
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        return {"error": "实验室不存在"}
    return {
        "lab": svc.lab_to_dict(lab),
        "equipment": [svc.equipment_to_dict(e, include_lab=False) for e in lab.equipment],
    }


def tool_check_availability(db: Session, user: User, lab_id: int, booking_date: str,
                            start_time: str | None = None,
                            end_time: str | None = None, **_) -> dict:
    try:
        return svc.check_availability_detail(
            db, lab_id, booking_date, start_time=start_time, end_time=end_time
        )
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_search_rules(db: Session, user: User, query: str, **_) -> dict:
    docs = rag.search(query, top_k=3)
    if not docs:
        return {"result": "知识库暂无相关内容（ChromaDB 可能未启动或未入库文档）"}
    return {"documents": docs}


def tool_search_equipment(db: Session, user: User, keyword: str | None = None,
                          lab_id: int | None = None, **_) -> dict:
    return svc.search_equipment(db, keyword=keyword or None, lab_id=lab_id)


def tool_list_my_bookings(db: Session, user: User, status: str | None = None, **_) -> dict:
    return svc.list_my_lab_bookings(db, user, status=status or None)


def tool_create_booking(db: Session, user: User, lab_id: int, booking_date: str,
                        start_time: str, end_time: str, purpose: str,
                        members: list[str] | None = None, **_) -> dict:
    try:
        return svc.create_lab_booking(
            db, user, lab_id, booking_date, start_time, end_time, purpose,
            members=members,
        )
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_cancel_booking(db: Session, user: User, booking_id: int, **_) -> dict:
    try:
        return svc.cancel_lab_booking(db, user, booking_id)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_update_booking(db: Session, user: User, booking_id: int, **kwargs) -> dict:
    allowed = {"lab_id", "booking_date", "start_time", "end_time", "purpose", "members"}
    changes = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    try:
        return svc.update_lab_booking(db, user, booking_id, **changes)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_book_equipment(db: Session, user: User, equipment_id: int, booking_date: str,
                        start_time: str, end_time: str, purpose: str, **_) -> dict:
    try:
        return svc.book_equipment(
            db, user, equipment_id, booking_date, start_time, end_time, purpose
        )
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_cancel_equipment_booking(db: Session, user: User, equipment_booking_id: int, **_) -> dict:
    try:
        return svc.cancel_equipment_booking(db, user, equipment_booking_id)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_list_my_equipment_bookings(db: Session, user: User, status: str | None = None, **_) -> dict:
    return svc.list_my_equipment_bookings(db, user, status=status or None)


def tool_admin_list_bookings(db: Session, user: User, status: str | None = None, **_) -> dict:
    return svc.admin_list_bookings(db, status=status or None)


def tool_admin_approve_booking(db: Session, user: User, booking_id: int, **_) -> dict:
    try:
        return svc.approve_booking(db, booking_id)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_admin_reject_booking(db: Session, user: User, booking_id: int,
                              review_note: str = "", **_) -> dict:
    try:
        return svc.reject_booking(db, booking_id, review_note=review_note)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_confirm_booking(db: Session, user: User, booking_id: int, **_) -> dict:
    try:
        return svc.confirm_booking_usage(db, user, booking_id)
    except svc.ServiceError as e:
        return {"error": str(e)}


def tool_query_booking_stats(db: Session, user: User, metric: str = "overview",
                             range: str = "this_week", **_) -> dict:
    # 对话场景下只用确定性计算结果，由主模型负责组织中文回答（避免二次调模型）
    try:
        return analytics.compute_stats(db, metric=metric or "overview",
                                       range_key=range or "this_week")
    except Exception as e:
        return {"error": f"统计失败：{e}"}


TOOL_DISPATCH = {
    "list_labs": tool_list_labs,
    "get_lab_equipment": tool_get_lab_equipment,
    "check_availability": tool_check_availability,
    "search_rules": tool_search_rules,
    "search_equipment": tool_search_equipment,
    "list_my_bookings": tool_list_my_bookings,
    "cancel_booking": tool_cancel_booking,
    "update_booking": tool_update_booking,
    "create_booking": tool_create_booking,
    "book_equipment": tool_book_equipment,
    "cancel_equipment_booking": tool_cancel_equipment_booking,
    "list_my_equipment_bookings": tool_list_my_equipment_bookings,
    "confirm_booking": tool_confirm_booking,
    "admin_list_bookings": tool_admin_list_bookings,
    "admin_approve_booking": tool_admin_approve_booking,
    "admin_reject_booking": tool_admin_reject_booking,
    "query_booking_stats": tool_query_booking_stats,
}
