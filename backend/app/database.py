"""数据库连接模块。

职责：
1. 创建 SQLAlchemy 全局引擎 engine（连接池，整个应用共用一个）；
2. 创建会话工厂 SessionLocal（每个请求用它生成一个独立会话）；
3. 声明所有 ORM 模型的基类 Base；
4. 提供 FastAPI 依赖函数 get_db()，负责请求级会话的创建与关闭。

调用关系：
    config.py(数据库地址) → 本文件(engine/SessionLocal/Base/get_db)
        → models.py(继承 Base 定义表)
        → routers/*.py(Depends(get_db) 拿到会话操作数据库)
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# ---------- 1. 创建数据库引擎 ----------
# engine 是 SQLAlchemy 的"连接池核心"，负责管理到底层 SQLite 文件的连接。
# settings.DATABASE_URL 形如 "sqlite:///./data/lab.db"。
engine = create_engine(
    settings.DATABASE_URL,
    # SQLite 默认不允许跨线程使用同一个连接；
    # FastAPI 每个请求可能跑在不同线程，必须关掉这个检查。
    connect_args={"check_same_thread": False},
)


# ---------- 2. 每个新连接建立时，打开 SQLite 外键约束 ----------
# SQLite 默认不强制外键约束（即使建表时写了 ForeignKey），
# 这里监听 "connect" 事件：每建立一条数据库连接，就执行一次 PRAGMA。
# 开启后，删除被其他表引用的数据时会被阻止，保证数据一致性。
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------- 3. 会话工厂 ----------
# SessionLocal 不是会话本身，而是"造会话的机器"。
# 每调用一次 SessionLocal() 就得到一个独立的数据库会话（一次请求用一个）。
# autocommit=False：不自动提交，所有变更要显式 db.commit()，出错可回滚；
# autoflush=False：不自动把待写入数据刷到数据库，避免查询时意外触发写入。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 模型基类：models.py 里的 User/Booking 等类都继承它，
# SQLAlchemy 据此知道有哪些表、表结构是什么。
Base = declarative_base()


# ---------- 4. FastAPI 依赖：为每个请求提供一个数据库会话 ----------
# 在路由里这样用：db: Session = Depends(get_db)
# 请求进来 → 创建会话；请求结束（无论成功还是抛异常）→ finally 里关闭连接。
# yield 把会话"交给"路由函数使用，路由执行完后再回来执行 close()。
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
