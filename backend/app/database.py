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
from sqlalchemy import create_engine, event, text
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


# ---------- 3.5 轻量迁移：为旧库补齐新增列 ----------
# Base.metadata.create_all() 只能创建"不存在的表"，不会给已存在的表加新列。
# 项目使用 SQLite 单机库、没有引入 Alembic，这里用 PRAGMA table_info 检查列、
# 再用 ALTER TABLE ADD COLUMN 补列（SQLite 3.35+ 不支持 DROP COLUMN 也无妨，
# 本项目只做"加列"这一种向前兼容的变更）。
# 结构：{表名: [(列名, 列DDL), ...]}
_PENDING_COLUMNS = {
    "users": [
        ("credit_score", "INTEGER NOT NULL DEFAULT 100"),
    ],
    "bookings": [
        ("participant_count", "INTEGER NOT NULL DEFAULT 1"),
        # B-多Agent/人机协同：审核 Agent 自动结论标记、提醒去重、签到时间
        ("auto_reviewed", "BOOLEAN NOT NULL DEFAULT 0"),
        ("reminder_sent", "BOOLEAN NOT NULL DEFAULT 0"),
        ("urge_sent", "BOOLEAN NOT NULL DEFAULT 0"),
        ("confirmed_at", "DATETIME"),
    ],
}


def run_lightweight_migrations() -> None:
    """启动时执行一次：检查旧库是否缺少新列，缺少则 ALTER TABLE 补上。"""
    with engine.begin() as conn:
        for table, columns in _PENDING_COLUMNS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                # 表还不存在：create_all 会按最新模型建表，无需补列
                continue
            for col_name, col_ddl in columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_ddl}"))


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
