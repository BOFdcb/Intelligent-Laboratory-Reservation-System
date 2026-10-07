"""业务逻辑层：预约/设备预约的核心规则集中在这里。

为什么需要这一层？
- Agent 工具（tools.py）和 REST 接口（routers/*.py）是两个入口，
  如果各自写一套校验，极易出现"页面能约、Agent 不能约"或绕过限制的情况；
- 把规则（开放时间、冲突、容量、信用分、频率上限）收敛到本模块，
  两个入口调用同一批函数，行为天然一致。

规则速览（D-安全治理）：
- 信用分初始 100；预约开始前 24 小时内取消扣 5 分；低于 60 分禁止新预约；
- 每人进行中的实验室预约最多 5 条、设备预约最多 5 条。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import (
    Laboratory, Equipment, Booking, BookingMember, EquipmentBooking, User,
    Notification,
)
from .review_agent import run_review, APPROVE, REJECT, MANUAL

# 占用实验室时段的状态：已通过 + 已签到（进行中）都算占位；
# pending 也占位是为了避免多条待审预约互相撞车；released/cancelled/used 不占位
ACTIVE_STATUSES = ("pending", "approved", "confirmed")

MAX_ACTIVE_LAB_BOOKINGS = 5       # 每人进行中的实验室预约上限
MAX_ACTIVE_EQUIP_BOOKINGS = 5     # 每人进行中的设备预约上限
CREDIT_BLOCK_THRESHOLD = 60       # 信用分低于该值禁止新预约
LATE_CANCEL_HOURS = 24            # 距开始不足该小时数取消算"爽约边缘"
LATE_CANCEL_DEDUCT = 5            # 临期取消扣减的信用分

# ---- B-定时 Agent 参数 ----
REMIND_BEFORE_MIN = 30            # 开始前多少分钟发提醒
REMIND_SCAN_LEAD_MIN = 40         # 扫描窗口上沿（10 分钟扫描间隔的容错余量）
NO_SHOW_GRACE_MIN = 15            # 开始后宽限签到分钟数，超时自动释放
REVIEW_URGE_HOURS = 2             # 待审核超过该小时数向管理员催办
NO_SHOW_DEDUCT = 10               # 爽约（超时未确认）扣减的信用分
CONFIRM_WINDOW_MIN = 15           # 签到窗口：开始前 15 分钟 ~ 开始后 15 分钟


class ServiceError(Exception):
    """业务规则错误：消息可直接展示给用户。"""


# ---------------- 站内消息（B-人机协同/提醒） ----------------
def notify_user(db: Session, user_id: int, category: str, title: str,
                content: str = "", related_id: int | None = None,
                commit: bool = True) -> Notification:
    """写一条站内消息。定时任务批量发送时可 commit=False 最后统一提交。"""
    n = Notification(user_id=user_id, category=category, title=title[:128],
                     content=content[:500], related_id=related_id)
    db.add(n)
    if commit:
        db.commit()
    return n


def notify_admins(db: Session, category: str, title: str, content: str = "",
                  related_id: int | None = None, commit: bool = True) -> int:
    admins = db.query(User).filter(User.role == "admin").all()
    for a in admins:
        db.add(Notification(user_id=a.id, category=category, title=title[:128],
                            content=content[:500], related_id=related_id))
    if commit:
        db.commit()
    return len(admins)


def list_notifications(db: Session, user: User, unread_only: bool = False,
                       limit: int = 30) -> list[dict]:
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.id.desc()).limit(limit).all()
    return [{
        "id": n.id, "category": n.category, "title": n.title,
        "content": n.content, "is_read": n.is_read,
        "related_id": n.related_id,
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else None,
    } for n in rows]


def mark_notification_read(db: Session, user: User, notification_id: int) -> None:
    n = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == user.id
    ).first()
    if not n:
        raise ServiceError("消息不存在")
    n.is_read = True
    db.commit()


def mark_all_read(db: Session, user: User) -> int:
    count = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).update({Notification.is_read: True})
    db.commit()
    return count


# ---------------- 通用解析与序列化 ----------------
def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ServiceError("日期格式应为 YYYY-MM-DD")


def parse_time(s: str):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (ValueError, TypeError):
        raise ServiceError("时间格式应为 HH:MM")


def _hm(t) -> str:
    return t.strftime("%H:%M") if t else None


def lab_to_dict(lab: Laboratory) -> dict:
    return {
        "id": lab.id, "name": lab.name, "location": lab.location,
        "capacity": lab.capacity,
        "open_time": _hm(lab.open_time), "close_time": _hm(lab.close_time),
        "status": lab.status, "rules": lab.rules,
    }


def booking_to_dict(b: Booking) -> dict:
    return {
        "id": b.id,
        "lab_id": b.lab_id,
        "lab": lab_to_dict(b.lab) if b.lab else None,
        "booking_date": b.booking_date.isoformat(),
        "start_time": _hm(b.start_time),
        "end_time": _hm(b.end_time),
        "purpose": b.purpose,
        "status": b.status,
        "review_note": b.review_note or "",
        "auto_reviewed": bool(b.auto_reviewed),
        "participant_count": b.participant_count or 1,
        "members": [m.user.username for m in b.members if m.user],
        "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else None,
    }


def equipment_to_dict(e: Equipment, include_lab: bool = True) -> dict:
    data = {
        "id": e.id, "lab_id": e.lab_id, "name": e.name,
        "model": e.model, "quantity": e.quantity, "status": e.status,
    }
    if include_lab and e.lab:
        data["lab_name"] = e.lab.name
        data["location"] = e.lab.location
    return data


def equipment_booking_to_dict(r: EquipmentBooking) -> dict:
    return {
        "id": r.id,
        "equipment_id": r.equipment_id,
        "equipment": equipment_to_dict(r.equipment) if r.equipment else None,
        "booking_date": r.booking_date.isoformat(),
        "start_time": _hm(r.start_time),
        "end_time": _hm(r.end_time),
        "purpose": r.purpose,
        "status": r.status,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }


# ---------------- 实验室预约：校验与查询 ----------------
def _get_enabled_lab(db: Session, lab_id: int) -> Laboratory:
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise ServiceError("实验室不存在")
    if lab.status != "enabled":
        raise ServiceError("实验室已停用")
    return lab


def _validate_slot(lab: Laboratory, d, st, et):
    if st >= et:
        raise ServiceError("开始时间必须早于结束时间")
    if st < lab.open_time or et > lab.close_time:
        raise ServiceError(
            f"预约时段超出开放时间（{_hm(lab.open_time)}-{_hm(lab.close_time)}）"
        )


def lab_conflict(db: Session, lab_id: int, d, st, et, exclude_id=None) -> Booking | None:
    """时段重叠判定：[s1,e1) 与 [s2,e2) 只要相交即冲突。"""
    q = db.query(Booking).filter(
        Booking.lab_id == lab_id,
        Booking.booking_date == d,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_time < et,
        Booking.end_time > st,
    )
    if exclude_id:
        q = q.filter(Booking.id != exclude_id)
    return q.first()


def _resolve_members(db: Session, members, self_user: User, lab: Laboratory) -> list[User]:
    """把用户名列表解析为用户对象，并做重复/容量校验。"""
    if not members:
        return []
    names = []
    for name in members:
        name = (name or "").strip()
        if name and name not in names:
            names.append(name)
    if self_user.username in names:
        raise ServiceError("成员名单中不能包含预约人自己")
    users = db.query(User).filter(User.username.in_(names)).all()
    found = {u.username: u for u in users}
    missing = [n for n in names if n not in found]
    if missing:
        raise ServiceError(f"以下成员不存在：{', '.join(missing)}")
    total = len(names) + 1  # 成员 + 预约人本人
    if lab.capacity and total > lab.capacity:
        raise ServiceError(f"参与人数 {total} 超过实验室容量 {lab.capacity}")
    return [found[n] for n in names]


def _free_windows(open_t, close_t, occupied: list[tuple]):
    """根据被占用区间，算出开放时间内的空闲窗口（自动合并重叠区间）。"""
    merged = sorted(occupied)
    windows, cur = [], open_t
    for s, e in merged:
        if s > cur:
            windows.append((cur, s))
        if e > cur:
            cur = e
    if cur < close_t:
        windows.append((cur, close_t))
    return windows


def suggest_same_lab_slots(db: Session, lab: Laboratory, d, st, et, limit=3) -> list[dict]:
    """目标时段被占时：在同一实验室、同一天，按相同时长找最早的几个空闲时段。"""
    duration = timedelta(
        hours=et.hour - st.hour, minutes=et.minute - st.minute
    ) if et.hour >= st.hour else timedelta()
    if duration <= timedelta(0):
        return []
    rows = db.query(Booking).filter(
        Booking.lab_id == lab.id, Booking.booking_date == d,
        Booking.status.in_(ACTIVE_STATUSES),
    ).all()
    suggestions = []
    for ws, we in _free_windows(lab.open_time, lab.close_time,
                                [(b.start_time, b.end_time) for b in rows]):
        if datetime.combine(d, we) - datetime.combine(d, ws) >= duration:
            suggestions.append({
                "type": "same_lab",
                "lab_id": lab.id, "lab_name": lab.name,
                "booking_date": d.isoformat(),
                "start_time": _hm(ws),
                "end_time": _hm((datetime.combine(d, ws) + duration).time()),
            })
        if len(suggestions) >= limit:
            break
    return suggestions


def suggest_alternative_labs(db: Session, lab_id: int, d, st, et, limit=3) -> list[dict]:
    """目标时段被占时：找同一时段空闲的其他启用实验室。"""
    labs = db.query(Laboratory).filter(
        Laboratory.status == "enabled", Laboratory.id != lab_id
    ).order_by(Laboratory.id).all()
    result = []
    for lab in labs:
        if st < lab.open_time or et > lab.close_time:
            continue
        if not lab_conflict(db, lab.id, d, st, et):
            result.append({
                "type": "another_lab",
                "lab_id": lab.id, "lab_name": lab.name,
                "location": lab.location, "capacity": lab.capacity,
                "booking_date": d.isoformat(),
                "start_time": _hm(st), "end_time": _hm(et),
            })
        if len(result) >= limit:
            break
    return result


def check_availability_detail(db: Session, lab_id: int, booking_date: str,
                              start_time: str | None = None,
                              end_time: str | None = None) -> dict:
    """查占用；若给出具体时段，额外返回"是否可约 + 备选时段/备选实验室"。"""
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise ServiceError("实验室不存在")
    d = parse_date(booking_date)
    bookings = db.query(Booking).filter(
        Booking.lab_id == lab_id, Booking.booking_date == d,
        Booking.status.in_(ACTIVE_STATUSES),
    ).all()
    data = {
        "lab": lab_to_dict(lab),
        "date": booking_date,
        "open_time": _hm(lab.open_time),
        "close_time": _hm(lab.close_time),
        "occupied_slots": [
            {"start_time": _hm(b.start_time), "end_time": _hm(b.end_time),
             "status": b.status}
            for b in bookings
        ],
    }
    if start_time and end_time:
        st, et = parse_time(start_time), parse_time(end_time)
        conflict = lab_conflict(db, lab_id, d, st, et)
        data["requested_slot"] = {"start_time": start_time, "end_time": end_time}
        data["requested_slot_free"] = conflict is None
        if conflict:
            data["suggestions"] = (
                suggest_same_lab_slots(db, lab, d, st, et)
                + suggest_alternative_labs(db, lab_id, d, st, et)
            )
    return data


def _check_frequency_and_credit(db: Session, user: User):
    if user.credit_score < CREDIT_BLOCK_THRESHOLD:
        raise ServiceError(
            f"信用分过低（当前 {user.credit_score}，低于 {CREDIT_BLOCK_THRESHOLD}），"
            f"暂不能发起预约，请联系管理员"
        )
    active_count = db.query(Booking).filter(
        Booking.user_id == user.id, Booking.status.in_(ACTIVE_STATUSES)
    ).count()
    if active_count >= MAX_ACTIVE_LAB_BOOKINGS:
        raise ServiceError(f"进行中的预约已达上限（{MAX_ACTIVE_LAB_BOOKINGS} 条），请先取消部分预约")


def _build_review_context(db: Session, b: Booking, user: User) -> dict:
    """组装审核 Agent 需要的预约快照（图不碰数据库，所有数据在这里备齐）。"""
    lab = b.lab
    duration = round(
        (datetime.combine(b.booking_date, b.end_time)
         - datetime.combine(b.booking_date, b.start_time)).total_seconds() / 3600, 1
    )
    start_dt = datetime.combine(b.booking_date, b.start_time)
    capacity = lab.capacity or 0
    return {
        "booking_id": b.id,
        "lab_name": lab.name,
        "date": b.booking_date.isoformat(),
        "start": _hm(b.start_time), "end": _hm(b.end_time),
        "start_hour": b.start_time.hour,
        "duration_hours": duration,
        "purpose": b.purpose or "",
        "participant_count": b.participant_count or 1,
        "capacity": capacity,
        "capacity_ratio": round((b.participant_count or 1) / capacity, 2) if capacity else 0,
        "credit_score": user.credit_score or 100,
        "hours_before_start": round((start_dt - datetime.now()).total_seconds() / 3600, 1),
        "is_weekend": b.booking_date.weekday() >= 5,
    }


def _apply_review(db: Session, b: Booking, user: User) -> dict:
    """调用审核 Agent 并按裁决落库 + 发站内通知，返回给调用方的结果。"""
    verdict = run_review(_build_review_context(db, b, user))
    decision = verdict["decision"]
    reasons = "；".join(verdict["reasons"])[:220]
    signals = "；".join(verdict["signals"])[:220]
    slot = f"{b.booking_date.isoformat()} {_hm(b.start_time)}-{_hm(b.end_time)}"
    lab_name = b.lab.name if b.lab else f"实验室{b.lab_id}"

    if decision == APPROVE:
        b.status = "approved"
        b.auto_reviewed = True
        b.review_note = f"AI 初审自动通过：{reasons}"
        db.commit()
        notify_user(
            db, user.id, "booking_result",
            "预约已通过 AI 初审",
            f"您预约的「{lab_name}」{slot} 已由审核 Agent 自动通过。"
            f"请在开始前后 {CONFIRM_WINDOW_MIN} 分钟内完成到场签到，超时未签到将被自动释放。",
            related_id=b.id,
        )
        return {"decision": APPROVE, "llm_used": verdict["llm_used"],
                "message": "审核 Agent 规则初审通过，预约已生效（请按时到场签到）"}

    if decision == REJECT:
        b.status = "rejected"
        b.auto_reviewed = True
        b.review_note = f"AI 初审驳回：{reasons}"
        db.commit()
        notify_user(
            db, user.id, "booking_result",
            "预约未通过 AI 初审",
            f"您预约的「{lab_name}」{slot} 被初审驳回：{reasons}。"
            f"如有异议可联系管理员人工复核。",
            related_id=b.id,
        )
        return {"decision": REJECT, "llm_used": verdict["llm_used"],
                "message": f"审核 Agent 判定不符合规定：{reasons}"}

    # 边界情况 → 转人工终审
    b.status = "pending"
    b.auto_reviewed = False
    b.review_note = f"AI 初审转人工：{signals or '存在边界情况'}"
    db.commit()
    notify_user(
        db, user.id, "booking_result",
        "预约已提交，等待人工终审",
        f"您预约的「{lab_name}」{slot} 命中边界审核项（{signals}），"
        f"已转交管理员人工终审，请留意审核结果通知。",
        related_id=b.id,
    )
    # 同步通知管理员：有新的待人工终审预约
    notify_admins(
        db, "urge", "新的预约待人工终审",
        f"{user.username} 申请「{lab_name}」{slot}，用途：{b.purpose or '未填写'}；"
        f"AI 初审提示：{signals or '边界情况'}。",
        related_id=b.id,
    )
    return {"decision": MANUAL, "llm_used": verdict["llm_used"],
            "message": "预约已提交，审核 Agent 判定为边界情况，已转管理员人工终审"}


def create_lab_booking(db: Session, user: User, lab_id: int, booking_date: str,
                       start_time: str, end_time: str, purpose: str,
                       members: list[str] | None = None) -> dict:
    _check_frequency_and_credit(db, user)
    lab = _get_enabled_lab(db, lab_id)
    d, st, et = parse_date(booking_date), parse_time(start_time), parse_time(end_time)
    _validate_slot(lab, d, st, et)
    if lab_conflict(db, lab_id, d, st, et):
        raise ServiceError("该时段已被占用，可让我帮你查询其他时段或实验室")
    member_users = _resolve_members(db, members, user, lab)

    booking = Booking(
        user_id=user.id, lab_id=lab_id, booking_date=d, start_time=st, end_time=et,
        purpose=purpose or "", status="pending",
        participant_count=1 + len(member_users),
    )
    db.add(booking)
    db.flush()  # 拿到 booking.id 再写成员表
    for mu in member_users:
        db.add(BookingMember(booking_id=booking.id, user_id=mu.id))
    db.commit()
    db.refresh(booking)

    # B-人机协同：先过审核 Agent（自动通过 / 自动驳回 / 转人工终审）
    review = _apply_review(db, booking, user)
    db.refresh(booking)
    return {
        "booking_id": booking.id, "status": booking.status,
        "participant_count": booking.participant_count,
        "decision": review["decision"],
        "llm_used": review["llm_used"],
        "message": review["message"],
    }


def confirm_booking_usage(db: Session, user: User, booking_id: int) -> dict:
    """到场签到：开始前 15 分钟 ~ 开始后 15 分钟内可确认，超时由调度器自动释放。"""
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise ServiceError("预约不存在")
    if b.user_id != user.id:
        raise ServiceError("只能为本人的预约签到")
    if b.status != "approved":
        raise ServiceError("仅已通过且未签到的预约可签到")
    now = datetime.now()
    start_dt = datetime.combine(b.booking_date, b.start_time)
    if now < start_dt - timedelta(minutes=CONFIRM_WINDOW_MIN):
        raise ServiceError(
            f"签到将于开始前 {CONFIRM_WINDOW_MIN} 分钟开放"
        )
    if now > start_dt + timedelta(minutes=NO_SHOW_GRACE_MIN):
        raise ServiceError("已超过签到时限，该预约已被/将被系统自动释放")
    b.status = "confirmed"
    b.confirmed_at = now
    db.commit()
    return {"booking_id": b.id, "status": "confirmed",
            "message": "签到成功，请正常使用实验室"}


def _owned_active_booking(db: Session, user: User, booking_id: int) -> Booking:
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise ServiceError("预约不存在")
    if b.user_id != user.id and user.role != "admin":
        raise ServiceError("只能操作本人的预约")
    if b.status not in ACTIVE_STATUSES:
        raise ServiceError("当前状态不可执行该操作")
    return b


def cancel_lab_booking(db: Session, user: User, booking_id: int) -> dict:
    b = _owned_active_booking(db, user, booking_id)
    # 临期取消扣分（D-防放鸽子）
    start_at = datetime.combine(b.booking_date, b.start_time)
    deducted = 0
    if start_at - datetime.now() < timedelta(hours=LATE_CANCEL_HOURS):
        user.credit_score = max(0, (user.credit_score or 100) - LATE_CANCEL_DEDUCT)
        deducted = LATE_CANCEL_DEDUCT
    b.status = "cancelled"
    db.commit()
    msg = "已取消"
    if deducted:
        msg += f"（距开始不足 {LATE_CANCEL_HOURS} 小时，扣 {deducted} 信用分，当前 {user.credit_score}）"
    return {"booking_id": b.id, "status": "cancelled", "credit_score": user.credit_score,
            "deducted": deducted, "message": msg}


def update_lab_booking(db: Session, user: User, booking_id: int, *,
                       lab_id: int | None = None, booking_date: str | None = None,
                       start_time: str | None = None, end_time: str | None = None,
                       purpose: str | None = None,
                       members: list[str] | None = None) -> dict:
    b = _owned_active_booking(db, user, booking_id)
    was_approved = b.status == "approved"
    new_lab_id = lab_id or b.lab_id
    lab = _get_enabled_lab(db, new_lab_id)
    d = parse_date(booking_date) if booking_date else b.booking_date
    st = parse_time(start_time) if start_time else b.start_time
    et = parse_time(end_time) if end_time else b.end_time
    _validate_slot(lab, d, st, et)
    if lab_conflict(db, new_lab_id, d, st, et, exclude_id=b.id):
        raise ServiceError("目标时段已被占用，请换一个时段")

    member_users = None
    if members is not None:
        member_users = _resolve_members(db, members, user, lab)

    b.lab_id = new_lab_id
    b.booking_date, b.start_time, b.end_time = d, st, et
    if purpose is not None:
        b.purpose = purpose
    if member_users is not None:
        b.members.clear()
        db.flush()
        for mu in member_users:
            db.add(BookingMember(booking_id=b.id, user_id=mu.id))
        b.participant_count = 1 + len(member_users)
    # 已通过的预约改约后需要重新审核（重新走一遍审核 Agent）
    review_msg = None
    if was_approved:
        b.status = "pending"
        db.commit()
        db.refresh(b)
        review = _apply_review(db, b, user)
        review_msg = review["message"]
    db.commit()
    db.refresh(b)
    return {
        "booking_id": b.id, "status": b.status,
        "message": review_msg or "改约成功",
    }


def list_my_lab_bookings(db: Session, user: User, status: str | None = None,
                         limit: int = 20) -> dict:
    q = db.query(Booking).filter(Booking.user_id == user.id)
    if status:
        q = q.filter(Booking.status == status)
    rows = q.order_by(Booking.id.desc()).limit(limit).all()
    return {"bookings": [booking_to_dict(b) for b in rows], "count": len(rows)}


# ---------------- 设备级预约 ----------------
def search_equipment(db: Session, keyword: str | None = None,
                     lab_id: int | None = None) -> dict:
    q = db.query(Equipment)
    if lab_id:
        q = q.filter(Equipment.lab_id == lab_id)
    if keyword:
        q = q.filter(Equipment.name.like(f"%{keyword}%"))
    items = q.order_by(Equipment.id).all()
    return {"equipment": [equipment_to_dict(e) for e in items]}


def _equipment_overlap_count(db: Session, equipment_id: int, d, st, et,
                             exclude_id=None) -> int:
    q = db.query(EquipmentBooking).filter(
        EquipmentBooking.equipment_id == equipment_id,
        EquipmentBooking.booking_date == d,
        EquipmentBooking.status == "active",
        EquipmentBooking.start_time < et,
        EquipmentBooking.end_time > st,
    )
    if exclude_id:
        q = q.filter(EquipmentBooking.id != exclude_id)
    return q.count()


def book_equipment(db: Session, user: User, equipment_id: int, booking_date: str,
                   start_time: str, end_time: str, purpose: str) -> dict:
    if user.credit_score < CREDIT_BLOCK_THRESHOLD:
        raise ServiceError(
            f"信用分过低（当前 {user.credit_score}），暂不能预约设备，请联系管理员"
        )
    active = db.query(EquipmentBooking).filter(
        EquipmentBooking.user_id == user.id,
        EquipmentBooking.status == "active",
    ).count()
    if active >= MAX_ACTIVE_EQUIP_BOOKINGS:
        raise ServiceError(f"进行中的设备预约已达上限（{MAX_ACTIVE_EQUIP_BOOKINGS} 条）")

    eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not eq:
        raise ServiceError("设备不存在")
    if eq.status != "available":
        raise ServiceError("该设备处于维护状态，暂不可预约")
    lab = eq.lab
    d, st, et = parse_date(booking_date), parse_time(start_time), parse_time(end_time)
    if st >= et:
        raise ServiceError("开始时间必须早于结束时间")
    if st < lab.open_time or et > lab.close_time:
        raise ServiceError(f"使用时段超出实验室开放时间（{_hm(lab.open_time)}-{_hm(lab.close_time)}）")
    # 数量型设备：同时段在约数量达到库存上限才冲突
    if _equipment_overlap_count(db, equipment_id, d, st, et) >= (eq.quantity or 1):
        raise ServiceError(f"该时段「{eq.name}」可预约数量不足（库存 {eq.quantity}），请换个时段")

    record = EquipmentBooking(
        user_id=user.id, equipment_id=equipment_id, booking_date=d,
        start_time=st, end_time=et, purpose=purpose or "", status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "equipment_booking_id": record.id, "status": "active",
        "equipment_name": eq.name,
        "message": f"设备「{eq.name}」预约成功（{booking_date} {start_time}-{end_time}）",
    }


def cancel_equipment_booking(db: Session, user: User, booking_id: int) -> dict:
    r = db.query(EquipmentBooking).filter(EquipmentBooking.id == booking_id).first()
    if not r:
        raise ServiceError("设备预约不存在")
    if r.user_id != user.id and user.role != "admin":
        raise ServiceError("只能取消本人的设备预约")
    if r.status != "active":
        raise ServiceError("该设备预约已取消")
    start_at = datetime.combine(r.booking_date, r.start_time)
    deducted = 0
    if start_at - datetime.now() < timedelta(hours=LATE_CANCEL_HOURS):
        user.credit_score = max(0, (user.credit_score or 100) - LATE_CANCEL_DEDUCT)
        deducted = LATE_CANCEL_DEDUCT
    r.status = "cancelled"
    db.commit()
    msg = "设备预约已取消"
    if deducted:
        msg += f"（临期取消扣 {deducted} 信用分，当前 {user.credit_score}）"
    return {"equipment_booking_id": r.id, "status": "cancelled",
            "credit_score": user.credit_score, "message": msg}


def list_my_equipment_bookings(db: Session, user: User, status: str | None = None,
                               limit: int = 20) -> dict:
    q = db.query(EquipmentBooking).filter(EquipmentBooking.user_id == user.id)
    if status:
        q = q.filter(EquipmentBooking.status == status)
    rows = q.order_by(EquipmentBooking.id.desc()).limit(limit).all()
    return {"bookings": [equipment_booking_to_dict(r) for r in rows], "count": len(rows)}


# ---------------- 管理员：审批 ----------------
def admin_list_bookings(db: Session, status: str | None = None, limit: int = 20) -> dict:
    q = db.query(Booking)
    if status:
        q = q.filter(Booking.status == status)
    rows = q.order_by(Booking.id.desc()).limit(limit).all()
    result = []
    for b in rows:
        item = booking_to_dict(b)
        item["applicant"] = b.user.username if b.user else ""
        result.append(item)
    return {"bookings": result, "count": len(result)}


def approve_booking(db: Session, booking_id: int) -> dict:
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise ServiceError("预约不存在")
    if b.status != "pending":
        raise ServiceError("仅待审核预约可审核")
    if lab_conflict(db, b.lab_id, b.booking_date, b.start_time, b.end_time, exclude_id=b.id):
        raise ServiceError("该时段已被其他已通过预约占用")
    b.status = "approved"
    b.review_note = "管理员人工终审通过"
    db.commit()
    slot = f"{b.booking_date.isoformat()} {_hm(b.start_time)}-{_hm(b.end_time)}"
    notify_user(
        db, b.user_id, "booking_result", "预约已通过人工审核",
        f"您预约的「{b.lab.name if b.lab else ''}」{slot} 已由管理员通过，"
        f"请在开始前后 {CONFIRM_WINDOW_MIN} 分钟内到场签到。",
        related_id=b.id,
    )
    return {"booking_id": b.id, "status": "approved", "message": "已通过"}


def reject_booking(db: Session, booking_id: int, review_note: str = "") -> dict:
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise ServiceError("预约不存在")
    if b.status != "pending":
        raise ServiceError("仅待审核预约可审核")
    b.status = "rejected"
    b.review_note = f"管理员驳回：{review_note}" if review_note else "管理员驳回"
    db.commit()
    slot = f"{b.booking_date.isoformat()} {_hm(b.start_time)}-{_hm(b.end_time)}"
    notify_user(
        db, b.user_id, "booking_result", "预约未通过人工审核",
        f"您预约的「{b.lab.name if b.lab else ''}」{slot} 被驳回。"
        + (f"原因：{review_note}" if review_note else ""),
        related_id=b.id,
    )
    return {"booking_id": b.id, "status": "rejected", "message": "已驳回"}


# ---------------- B-定时 Agent：由 APScheduler 周期调用 ----------------
def _slot_text(b: Booking) -> str:
    lab_name = b.lab.name if b.lab else f"实验室{b.lab_id}"
    return f"「{lab_name}」{b.booking_date.isoformat()} {_hm(b.start_time)}-{_hm(b.end_time)}"


def send_start_reminders(db: Session, now: datetime | None = None) -> dict:
    """预约开始前提醒：approved 且将在 ~40 分钟内开始的今日预约，逐条提醒并去重。"""
    now = now or datetime.now()
    rows = db.query(Booking).filter(
        Booking.status == "approved",
        Booking.reminder_sent.is_(False),
        Booking.booking_date == now.date(),
    ).all()
    sent = 0
    for b in rows:
        try:
            start_dt = datetime.combine(b.booking_date, b.start_time)
            delta_min = (start_dt - now).total_seconds() / 60
            if 0 <= delta_min <= REMIND_SCAN_LEAD_MIN:
                notify_user(
                    db, b.user_id, "reminder", "实验室预约即将开始",
                    f"您的{_slot_text(b)} 预约将于 {_hm(b.start_time)} 开始，"
                    f"请准时到场并在开始后 {NO_SHOW_GRACE_MIN} 分钟内签到，"
                    f"超时未签到预约将被自动释放并扣除 {NO_SHOW_DEDUCT} 信用分。",
                    related_id=b.id, commit=False,
                )
                b.reminder_sent = True
                sent += 1
        except Exception:
            db.rollback()
    db.commit()
    return {"reminded": sent}


def urge_pending_reviews(db: Session, now: datetime | None = None) -> dict:
    """待审核催办：pending 超过 REVIEW_URGE_HOURS 且开始时间仍在未来的，提醒管理员。"""
    now = now or datetime.now()
    deadline = now - timedelta(hours=REVIEW_URGE_HOURS)
    rows = db.query(Booking).filter(
        Booking.status == "pending",
        Booking.urge_sent.is_(False),
        Booking.created_at <= deadline,
    ).all()
    urged = 0
    for b in rows:
        try:
            start_dt = datetime.combine(b.booking_date, b.start_time)
            if start_dt <= now:
                continue  # 已过期的不再催办
            applicant = b.user.username if b.user else f"用户{b.user_id}"
            notify_admins(
                db, "urge", "待审核预约催办提醒",
                f"{applicant} 的{_slot_text(b)} 已等待超过 {REVIEW_URGE_HOURS} 小时，"
                f"用途：{b.purpose or '未填写'}，请尽快处理。",
                related_id=b.id, commit=False,
            )
            b.urge_sent = True
            urged += 1
        except Exception:
            db.rollback()
    db.commit()
    return {"urged": urged}


def process_no_show_and_finish(db: Session, now: datetime | None = None) -> dict:
    """超时未确认自动释放 + 已签到预约结束后置为 used（只扫描今日预约）。"""
    now = now or datetime.now()
    released = finished = 0

    # 1) approved：开始超过宽限期仍未签到 → 自动释放 + 扣信用分
    rows = db.query(Booking).filter(
        Booking.status == "approved",
        Booking.booking_date == now.date(),
    ).all()
    for b in rows:
        try:
            start_dt = datetime.combine(b.booking_date, b.start_time)
            if now > start_dt + timedelta(minutes=NO_SHOW_GRACE_MIN):
                b.status = "released"
                user = b.user
                if user:
                    user.credit_score = max(
                        0, (user.credit_score or 100) - NO_SHOW_DEDUCT
                    )
                    notify_user(
                        db, user.id, "system", "预约因超时未签到被自动释放",
                        f"您的{_slot_text(b)} 预约开始后 {NO_SHOW_GRACE_MIN} 分钟内"
                        f"未完成签到，系统已自动释放该时段并扣除 {NO_SHOW_DEDUCT} 信用分"
                        f"（当前 {user.credit_score}）。",
                        related_id=b.id, commit=False,
                    )
                released += 1
        except Exception:
            db.rollback()
    db.commit()

    # 2) confirmed：已过结束时间 → used
    rows = db.query(Booking).filter(
        Booking.status == "confirmed",
        Booking.booking_date == now.date(),
    ).all()
    for b in rows:
        try:
            end_dt = datetime.combine(b.booking_date, b.end_time)
            if now > end_dt:
                b.status = "used"
                finished += 1
        except Exception:
            db.rollback()
    db.commit()
    return {"released": released, "finished": finished}


def run_scheduled_jobs(db: Session, now: datetime | None = None) -> dict:
    """一次跑完全部定时任务（APScheduler 周期调用 / 管理员手动触发共用）。"""
    return {
        **send_start_reminders(db, now),
        **urge_pending_reviews(db, now),
        **process_no_show_and_finish(db, now),
    }
