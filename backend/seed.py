"""初始化数据库：创建表 + 管理员/学生账号 + 示例实验室与设备。"""
from datetime import time

from app.database import Base, engine, SessionLocal
from app.models import User, Laboratory, Equipment
from app.security import hash_password


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(username="admin", password_hash=hash_password("admin123"),
                        role="admin", nickname="管理员"))
        if not db.query(User).filter(User.username == "student").first():
            db.add(User(username="student", password_hash=hash_password("student123"),
                        role="student", nickname="学生"))
        db.commit()

        if db.query(Laboratory).count() == 0:
            lab1 = Laboratory(
                name="人工智能实验室", location="信息楼 A101", capacity=40,
                open_time=time(8, 0), close_time=time(22, 0), status="enabled",
                rules="禁止饮食；实验结束后关闭设备电源；贵重物品随身携带。",
            )
            lab2 = Laboratory(
                name="计算机网络实验室", location="信息楼 A203", capacity=30,
                open_time=time(8, 30), close_time=time(21, 30), status="enabled",
                rules="不得私自更改网络拓扑；实验数据课后自行备份。",
            )
            lab3 = Laboratory(
                name="嵌入式系统实验室", location="信息楼 B105", capacity=24,
                open_time=time(9, 0), close_time=time(20, 0), status="enabled",
                rules="开发板使用前后需登记；禁止带电插拔模块。",
            )
            db.add_all([lab1, lab2, lab3])
            db.commit()

            db.add_all([
                Equipment(lab_id=lab1.id, name="GPU 服务器", model="NVIDIA A100", quantity=2),
                Equipment(lab_id=lab1.id, name="工作站", model="Dell Precision 5820", quantity=20),
                Equipment(lab_id=lab2.id, name="核心交换机", model="Cisco Catalyst 9300", quantity=4),
                Equipment(lab_id=lab2.id, name="路由器", model="Cisco ISR 4331", quantity=8),
                Equipment(lab_id=lab3.id, name="STM32 开发板", model="STM32F407", quantity=24),
                Equipment(lab_id=lab3.id, name="示波器", model="Rigol DS1104Z", quantity=12),
            ])
            db.commit()
        print("种子数据初始化完成：admin/admin123（管理员），student/student123（学生）")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
