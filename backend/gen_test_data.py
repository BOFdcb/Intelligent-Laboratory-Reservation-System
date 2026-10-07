"""生成测试数据：额外学生账号 + 过去14天~未来7天的预约（覆盖全部状态）+ 站内消息。

直接操作 ORM 插入（不触发审核 Agent / LLM），保证数据分析图表有内容。
运行：.\\.venv\\Scripts\\python.exe gen_test_data.py
"""
import random
from datetime import date, datetime, time, timedelta

from app.database import Base, engine, SessionLocal
from app.models import (
    User, Laboratory, Booking, BookingMember, Notification,
)
from app.security import hash_password

random.seed(42)  # 可复现

TODAY = date.today()
NOW = datetime.now().replace(microsecond=0)

NEW_STUDENTS = [
    ("zhangsan", "张三"), ("lisi", "李四"), ("wangwu", "王五"),
    ("zhaoliu", "赵六"), ("sunqi", "孙七"), ("zhouba", "周八"),
]

PURPOSES = [
    "深度学习模型训练实验", "计算机网络课程实验", "嵌入式系统开发",
    "毕业设计实验数据采集", "图像处理算法验证", "操作系统课程实验",
    "数据库系统课程设计", "人工智能课程项目", "机器人控制实验",
    "网络安全攻防演练", "编译原理实验", "分布式系统实验",
]

# 各实验室开放时段内的合法 2 小时槽位
LAB_SLOTS = {
    "人工智能实验室": [(8, 10), (10, 12), (14, 16), (16, 18), (19, 21)],
    "计算机网络实验室": [(9, 11), (13, 15), (15, 17), (19, 21)],
    "嵌入式系统实验室": [(9, 11), (13, 15), (15, 17), (18, 20)],
}


def ensure_students(db):
    created = 0
    for username, nickname in NEW_STUDENTS:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(
                username=username, password_hash=hash_password("123456"),
                role="student", nickname=nickname,
                email=f"{username}@stu.edu.cn",
                credit_score=random.choice([100, 100, 100, 95, 90, 75]),
            ))
            created += 1
    db.commit()
    return created


def slot_status(d, start_h):
    """按日期与开始时段决定预约状态分布。"""
    slot_start = datetime.combine(d, time(start_h))
    if d < TODAY:
        r = random.random()
        if r < 0.68:
            return "used"
        if r < 0.78:
            return "cancelled"
        if r < 0.88:
            return "rejected"
        return "released"
    if d == TODAY:
        if slot_start + timedelta(hours=2) <= NOW:
            return random.choice(["used", "used", "released"])
        if slot_start <= NOW:
            return "confirmed"
        return random.choice(["approved", "approved", "pending"])
    # 未来
    return "approved" if random.random() < 0.6 else "pending"


def gen_bookings(db):
    labs = db.query(Laboratory).filter(Laboratory.status == "enabled").all()
    students = db.query(User).filter(User.role == "student").all()
    admin = db.query(User).filter(User.username == "admin").first()

    existing = set(
        (b.lab_id, b.booking_date, b.start_time)
        for b in db.query(Booking).all()
    )
    created = 0
    stats = {}

    for offset in range(-14, 8):  # 过去14天 ~ 未来7天
        d = TODAY + timedelta(days=offset)
        is_weekend = d.weekday() >= 5
        for lab in labs:
            slots = LAB_SLOTS.get(lab.name, [(10, 12), (14, 16)])
            for start_h, end_h in slots:
                # 周末稀疏、工作日较满
                prob = 0.3 if is_weekend else 0.72
                if random.random() > prob:
                    continue
                st, et = time(start_h), time(end_h)
                if (lab.id, d, st) in existing:
                    continue

                status = slot_status(d, start_h)
                user = random.choice(students)
                is_team = random.random() < 0.25
                extra = []
                if is_team and len(students) > 1:
                    pool = [s for s in students if s.id != user.id]
                    extra = random.sample(pool, k=random.randint(1, min(4, len(pool))))

                # created_at：提前 0~5 天创建
                created_dt = datetime.combine(d, st) - timedelta(
                    days=random.randint(0, 5), hours=random.randint(0, 8))
                confirmed_at = None
                if status in ("confirmed", "used"):
                    confirmed_at = datetime.combine(d, st) + timedelta(
                        minutes=random.randint(-10, 12))

                review_note = ""
                auto = False
                if status in ("approved", "rejected"):
                    auto = random.random() < 0.5
                    if auto:
                        review_note = ("AI审核通过：用途明确，时段合规"
                                       if status == "approved"
                                       else "AI审核驳回：用途描述不合规")
                    elif status == "rejected":
                        review_note = "管理员驳回：该时段优先安排教学任务"

                b = Booking(
                    user_id=user.id, lab_id=lab.id, booking_date=d,
                    start_time=st, end_time=et,
                    purpose=random.choice(PURPOSES),
                    status=status, review_note=review_note,
                    participant_count=1 + len(extra),
                    auto_reviewed=auto,
                    reminder_sent=(d < TODAY),
                    urge_sent=(status == "pending" and offset < 0),
                    confirmed_at=confirmed_at,
                    created_at=created_dt,
                )
                db.add(b)
                db.flush()
                for mu in extra:
                    db.add(BookingMember(booking_id=b.id, user_id=mu.id))
                existing.add((lab.id, d, st))
                created += 1
                stats[status] = stats.get(status, 0) + 1
    db.commit()
    return created, stats, admin


def gen_notifications(db, admin):
    student = db.query(User).filter(User.username == "student").first()
    samples = [
        (student, "booking_result", "预约审核通过",
         "您预约的「人工智能实验室」10月8日 14:00-16:00 已审核通过，请按时到场签到。"),
        (student, "reminder", "预约即将开始",
         "您预约的「计算机网络实验室」今天 14:00 开始，请提前到场，开始后15分钟未签到将自动释放。"),
        (student, "booking_result", "预约被驳回",
         "很抱歉，您预约的「嵌入式系统实验室」10月6日 19:00-21:00 未通过审核：用途描述不合规。"),
        (admin, "urge", "待审核催办",
         "有 3 条预约已等待超过 2 小时，请及时前往「预约审核」处理。"),
        (admin, "system", "系统通知",
         "数据分析 Agent 已上线，可在「数据分析」页用自然语言查询实验室使用情况。"),
    ]
    created = 0
    for user, category, title, content in samples:
        if user is None:
            continue
        db.add(Notification(
            user_id=user.id, category=category, title=title, content=content,
            is_read=False,
            created_at=NOW - timedelta(hours=random.randint(1, 30)),
        ))
        created += 1
    db.commit()
    return created


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n_users = ensure_students(db)
        n_bookings, stats, admin = gen_bookings(db)
        n_notices = gen_notifications(db, admin)
        total = db.query(Booking).count()
        print(f"新增学生账号: {n_users}（密码均为 123456）")
        print(f"新增预约: {n_bookings} 条，状态分布: {stats}")
        print(f"新增站内消息: {n_notices} 条")
        print(f"数据库预约总数: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
