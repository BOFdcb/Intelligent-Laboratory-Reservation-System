"""数据分析 Agent 的"计算层"（B-数据分析）。

架构原则（与 RAG 形成差异化）：
- 大模型绝不直连数据库：它只把自然语言问题解析成结构化指标参数，
  真正的统计全部在这里用确定性 SQL 聚合完成，结果可复现、零注入风险；
- 输出统一的 charts 结构（bar/line/pie），前端直接喂给 ECharts 渲染；
- facts 是精简后的关键数字，供大模型生成中文洞察。

支持指标：
- lab_usage           各实验室预约量 / 时长 / 使用率排名
- hot_slots           热门时段（按开始小时聚合）
- daily_trend         预约量每日趋势
- status_distribution 预约状态分布（通过率/待审量/取消率）
- overview            以上指标的综合看板
"""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .models import Booking, Laboratory

# 计入"有效使用"的状态（已通过 / 已签到 / 已完成）
EFFECTIVE_STATUSES = ("approved", "confirmed", "used")

STATUS_LABELS = {
    "pending": "待审核", "approved": "已通过", "rejected": "已驳回",
    "cancelled": "已取消", "confirmed": "已签到", "used": "已使用",
    "released": "已释放",
}

RANGE_LABELS = {
    "today": "今天", "this_week": "本周", "last_week": "上周",
    "this_month": "本月", "last_7_days": "近7天", "last_30_days": "近30天",
}


# ---------------- 时间范围解析 ----------------
def resolve_range(range_key: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if range_key == "today":
        return today, today
    if range_key == "this_week":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if range_key == "last_week":
        monday = today - timedelta(days=today.weekday() + 7)
        return monday, monday + timedelta(days=6)
    if range_key == "this_month":
        return today.replace(day=1), today
    if range_key == "last_30_days":
        return today - timedelta(days=29), today
    # 默认近 7 天
    return today - timedelta(days=6), today


def _hours(t) -> float:
    return t.hour + t.minute / 60.0


# ---------------- 各指标计算 ----------------
def _lab_usage(db: Session, d_from: date, d_to: date) -> tuple[list[dict], dict]:
    labs = db.query(Laboratory).filter(Laboratory.status == "enabled") \
        .order_by(Laboratory.id).all()
    days = (d_to - d_from).days + 1
    rows, chart_count, chart_util = [], [], []
    for lab in labs:
        bookings = db.query(Booking).filter(
            Booking.lab_id == lab.id,
            Booking.booking_date >= d_from, Booking.booking_date <= d_to,
            Booking.status.in_(EFFECTIVE_STATUSES),
        ).all()
        total_hours = sum(
            round(_hours(b.end_time) - _hours(b.start_time), 2) for b in bookings
        )
        open_hours = _hours(lab.close_time) - _hours(lab.open_time) or 14
        util = min(100.0, round(total_hours / (open_hours * days) * 100, 1))
        rows.append({
            "lab_id": lab.id, "lab_name": lab.name,
            "bookings": len(bookings), "total_hours": round(total_hours, 1),
            "utilization": util,
        })
        chart_count.append(len(bookings))
        chart_util.append(util)

    rows.sort(key=lambda r: r["bookings"], reverse=True)
    names = [r["lab_name"] for r in rows]
    charts = [
        {"key": "lab_count", "title": "各实验室预约次数",
         "x_labels": names,
         "series": [{"name": "预约次数", "type": "bar", "data": chart_count}]},
        {"key": "lab_util", "title": "各实验室时段使用率（%）",
         "x_labels": names,
         "series": [{"name": "使用率(%)", "type": "bar", "data": chart_util}]},
    ]
    total = sum(r["bookings"] for r in rows)
    busiest = rows[0] if rows and rows[0]["bookings"] else None
    avg_util = round(sum(r["utilization"] for r in rows) / len(rows), 1) if rows else 0
    facts = {
        "total_effective_bookings": total,
        "busiest_lab": busiest["lab_name"] if busiest else "无",
        "busiest_lab_count": busiest["bookings"] if busiest else 0,
        "average_utilization": avg_util,
        "ranking": [{"lab_name": r["lab_name"], "bookings": r["bookings"],
                     "total_hours": r["total_hours"], "utilization": r["utilization"]}
                    for r in rows[:5]],
    }
    return charts, facts


def _hot_slots(db: Session, d_from: date, d_to: date) -> tuple[list[dict], dict]:
    rows = db.query(Booking).filter(
        Booking.booking_date >= d_from, Booking.booking_date <= d_to,
        Booking.status.in_(EFFECTIVE_STATUSES),
    ).all()
    buckets = list(range(8, 22))  # 8:00 ~ 21:00 开始的时段
    counts = {h: 0 for h in buckets}
    for b in rows:
        h = b.start_time.hour
        if h in counts:
            counts[h] += 1
    data = [counts[h] for h in buckets]
    peak_h = max(buckets, key=lambda h: counts[h]) if rows else None
    charts = [{
        "key": "hot_slots", "title": "热门开始时段分布",
        "x_labels": [f"{h:02d}:00" for h in buckets],
        "series": [{"name": "预约次数", "type": "line", "data": data,
                    "area": True}],
    }]
    facts = {
        "total_effective_bookings": len(rows),
        "peak_slot": f"{peak_h:02d}:00-{(peak_h + 1) % 24:02d}:00" if peak_h else "无数据",
        "peak_slot_count": counts.get(peak_h, 0) if peak_h else 0,
    }
    return charts, facts


def _daily_trend(db: Session, d_from: date, d_to: date,
                 statuses=EFFECTIVE_STATUSES) -> tuple[list[dict], dict]:
    rows = db.query(Booking).filter(
        Booking.booking_date >= d_from, Booking.booking_date <= d_to,
        Booking.status.in_(statuses),
    ).all()
    counts: dict[str, int] = {}
    for b in rows:
        key = b.booking_date.isoformat()
        counts[key] = counts.get(key, 0) + 1
    days = (d_to - d_from).days + 1
    labels, data = [], []
    cur = d_from
    for _ in range(days):
        labels.append(cur.isoformat()[5:])  # MM-DD
        data.append(counts.get(cur.isoformat(), 0))
        cur += timedelta(days=1)
    peak_idx = max(range(len(data)), key=lambda i: data[i]) if data and any(data) else None
    charts = [{
        "key": "daily_trend", "title": "每日有效预约量趋势",
        "x_labels": labels,
        "series": [{"name": "预约量", "type": "line", "data": data, "area": True}],
    }]
    facts = {
        "total_effective_bookings": len(rows),
        "peak_day": labels[peak_idx] if peak_idx is not None else "无数据",
        "peak_day_count": data[peak_idx] if peak_idx is not None else 0,
        "average_per_day": round(len(rows) / days, 1),
    }
    return charts, facts


def _status_distribution(db: Session, d_from: date, d_to: date) -> tuple[list[dict], dict]:
    rows = db.query(Booking).filter(
        Booking.booking_date >= d_from, Booking.booking_date <= d_to,
    ).all()
    counts: dict[str, int] = {}
    for b in rows:
        counts[b.status] = counts.get(b.status, 0) + 1
    # 固定展示顺序，零值也给出来，饼图更稳定
    order = ["pending", "approved", "confirmed", "used", "rejected",
             "cancelled", "released"]
    items = [{"name": STATUS_LABELS[s], "value": counts.get(s, 0)}
             for s in order if counts.get(s, 0) > 0]
    charts = [{
        "key": "status_pie", "title": "预约状态分布",
        "x_labels": [],
        "series": [{"name": "预约量", "type": "pie", "data": items}],
    }]
    total = len(rows)
    effective = sum(counts.get(s, 0) for s in EFFECTIVE_STATUSES)
    facts = {
        "total_bookings": total,
        "pending_count": counts.get("pending", 0),
        "effective_count": effective,
        "approval_rate": round(effective / total * 100, 1) if total else 0,
        "cancel_rate": round(counts.get("cancelled", 0) / total * 100, 1) if total else 0,
        "release_rate": round(counts.get("released", 0) / total * 100, 1) if total else 0,
    }
    return charts, facts


# ---------------- 统一入口 ----------------
def compute_stats(db: Session, metric: str = "overview",
                  range_key: str = "this_week", lab_id: int | None = None,
                  today: date | None = None) -> dict:
    """计算指标。lab_id 目前保留参数（未来可下钻单实验室），统计以全局为主。"""
    d_from, d_to = resolve_range(range_key, today)
    charts: list[dict] = []
    facts: dict = {}

    if metric == "lab_usage":
        charts, facts = _lab_usage(db, d_from, d_to)
    elif metric == "hot_slots":
        charts, facts = _hot_slots(db, d_from, d_to)
    elif metric == "daily_trend":
        charts, facts = _daily_trend(db, d_from, d_to)
    elif metric == "status_distribution":
        charts, facts = _status_distribution(db, d_from, d_to)
    else:  # overview：综合看板（管理首页最常用）
        c1, f1 = _lab_usage(db, d_from, d_to)
        c2, f2 = _daily_trend(db, d_from, d_to)
        c3, f3 = _status_distribution(db, d_from, d_to)
        c4, f4 = _hot_slots(db, d_from, d_to)
        # 综合看板每个类别取一张主图，避免图表过多
        charts = [c3[0], c1[0], c2[0], c4[0]]
        facts.update({"lab": f1, "trend": f2, "status": f3, "slots": f4})

    return {
        "metric": metric,
        "range": {
            "key": range_key,
            "label": RANGE_LABELS.get(range_key, range_key),
            "from": d_from.isoformat(), "to": d_to.isoformat(),
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "charts": charts,
        "facts": facts,
    }
