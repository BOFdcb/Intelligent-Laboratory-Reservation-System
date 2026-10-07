"""定时提醒 Agent（B-人机协同）：APScheduler 周期触发业务扫描。

注册 3 个周期任务（业务规则全部在 services.py，本模块只负责"定时"）：
1. send_start_reminders      每 10 分钟：预约开始前 ~30 分钟的到场提醒；
2. urge_pending_reviews      每 30 分钟：待人工终审超过 2 小时的催办（发管理员）；
3. process_no_show_and_finish 每 10 分钟：开始后 15 分钟未签到自动释放并扣信用分、
                              已签到且过结束时间的预约置为 used。

每个任务内部自行创建独立 Session（调度器线程不在 FastAPI 请求上下文里，
不能用 get_db() 依赖）。任务幂等：reminder_sent / urge_sent 标记保证不重复通知。
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal
from . import services

logger = logging.getLogger("lab.scheduler")

REMIND_INTERVAL_MIN = 10    # 提醒/释放扫描间隔
URGE_INTERVAL_MIN = 30      # 催办扫描间隔

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _safe(name: str, func):
    """包装任务：独立会话 + 异常兜底，单次失败不影响后续调度。"""
    def runner():
        db = SessionLocal()
        try:
            result = func(db)
            logger.info("scheduled job %s done: %s", name, result)
        except Exception as e:
            logger.exception("scheduled job %s failed: %s", name, e)
        finally:
            db.close()
    return runner


def _register_jobs():
    scheduler.add_job(
        _safe("send_start_reminders", services.send_start_reminders),
        trigger="interval", minutes=REMIND_INTERVAL_MIN, id="send_start_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe("urge_pending_reviews", services.urge_pending_reviews),
        trigger="interval", minutes=URGE_INTERVAL_MIN, id="urge_pending_reviews",
        replace_existing=True,
    )
    scheduler.add_job(
        _safe("process_no_show_and_finish", services.process_no_show_and_finish),
        trigger="interval", minutes=REMIND_INTERVAL_MIN,
        id="process_no_show_and_finish", replace_existing=True,
    )


def start_scheduler():
    """FastAPI lifespan 启动时调用（已运行则跳过，兼容 --reload 双进程）。"""
    if not scheduler.running:
        _register_jobs()
        scheduler.start()
        logger.info("APScheduler started: %d jobs", len(scheduler.get_jobs()))


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
