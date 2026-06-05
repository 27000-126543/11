import asyncio
from datetime import datetime, date
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import atexit

from .logging_config import get_logger, log_audit
from .config import get_settings
from .data_collection import get_data_collector
from .anomaly_detection import get_anomaly_detector, get_baseline_calculator
from .alert_ticket import get_alert_ticket_manager
from .report_generator import get_weekly_report_generator
from .health_promotion import get_health_promotion_manager

settings = get_settings()
logger = get_logger(__name__)


class HealthScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.data_collector = get_data_collector()
        self.anomaly_detector = get_anomaly_detector()
        self.baseline_calculator = get_baseline_calculator()
        self.ticket_manager = get_alert_ticket_manager()
        self.report_generator = get_weekly_report_generator()
        self.promotion_manager = get_health_promotion_manager()
        self._is_running = False

    def _run_daily_data_collection(self):
        logger.info("=" * 60)
        logger.info("开始执行每日健康数据采集任务")
        logger.info("=" * 60)

        try:
            total, success = self.data_collector.collect_all_employees_data()
            logger.info(f"数据采集完成: 总计{total}人, 成功{success}人")

            total_processed, anomalies_found = self.anomaly_detector.detect_all_anomalies()
            logger.info(f"异常检测完成: 处理{total_processed}条, 发现{anomalies_found}条异常")

            if anomalies_found > 0:
                tickets_total, tickets_created = self.ticket_manager.generate_tickets_from_anomalies()
                logger.info(f"工单生成完成: 应创建{tickets_total}张, 成功创建{tickets_created}张")

            log_audit(
                user="system",
                action="daily_data_collection",
                detail=f"每日数据采集任务完成: {success}/{total}人, 异常{anomalies_found}条, 工单{tickets_created}张"
            )

        except Exception as e:
            logger.error(f"每日数据采集任务执行失败: {str(e)}", exc_info=True)

        logger.info("=" * 60)
        logger.info("每日健康数据采集任务执行完毕")
        logger.info("=" * 60)

    def _run_weekly_report_generation(self):
        logger.info("=" * 60)
        logger.info("开始执行每周健康报告生成任务")
        logger.info("=" * 60)

        try:
            if date.today().weekday() != 0:
                logger.info("今天不是周一，跳过周报生成")
                return

            total, success = self.report_generator.generate_all_department_reports()
            logger.info(f"周报生成完成: {success}/{total}个部门")

            if success > 0:
                start_date, end_date, week_str = self.report_generator.get_week_range()
                self.report_generator.send_reports(week_str)
                logger.info(f"周报推送完成: 周{week_str}")

            log_audit(
                user="system",
                action="weekly_report_generation",
                detail=f"每周报告生成任务完成: {success}/{total}个部门"
            )

        except Exception as e:
            logger.error(f"每周健康报告生成任务执行失败: {str(e)}", exc_info=True)

        logger.info("=" * 60)
        logger.info("每周健康报告生成任务执行完毕")
        logger.info("=" * 60)

    def _run_department_health_monitoring(self):
        logger.info("=" * 60)
        logger.info("开始执行部门健康监控任务")
        logger.info("=" * 60)

        try:
            activities = self.promotion_manager.detect_and_trigger_activities()
            logger.info(f"部门健康监控完成: 创建{len(activities)}个健康促进活动")

            log_audit(
                user="system",
                action="department_health_monitoring",
                detail=f"部门健康监控任务完成: 创建{len(activities)}个活动"
            )

        except Exception as e:
            logger.error(f"部门健康监控任务执行失败: {str(e)}", exc_info=True)

        logger.info("=" * 60)
        logger.info("部门健康监控任务执行完毕")
        logger.info("=" * 60)

    def _run_baseline_calculation(self):
        logger.info("=" * 60)
        logger.info("开始执行基线计算任务")
        logger.info("=" * 60)

        try:
            total, success = self.baseline_calculator.calculate_all_baselines()
            logger.info(f"基线计算完成: {success}/{total}名员工")

            log_audit(
                user="system",
                action="baseline_calculation",
                detail=f"基线计算任务完成: {success}/{total}名员工"
            )

        except Exception as e:
            logger.error(f"基线计算任务执行失败: {str(e)}", exc_info=True)

        logger.info("=" * 60)
        logger.info("基线计算任务执行完毕")
        logger.info("=" * 60)

    def start(self):
        if self._is_running:
            logger.warning("调度器已在运行中")
            return

        logger.info("启动健康管理系统定时任务调度器")

        hour = settings.DAILY_COLLECTION_HOUR
        minute = settings.DAILY_COLLECTION_MINUTE
        self.scheduler.add_job(
            self._run_daily_data_collection,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="daily_data_collection",
            name="每日健康数据采集",
            replace_existing=True
        )
        logger.info(f"已注册每日数据采集任务: 每天 {hour:02d}:{minute:02d} 执行")

        report_hour = settings.WEEKLY_REPORT_HOUR
        report_minute = settings.WEEKLY_REPORT_MINUTE
        report_day = settings.WEEKLY_REPORT_DAY
        self.scheduler.add_job(
            self._run_weekly_report_generation,
            trigger=CronTrigger(day_of_week=report_day, hour=report_hour, minute=report_minute),
            id="weekly_report_generation",
            name="每周健康报告生成",
            replace_existing=True
        )
        logger.info(f"已注册每周报告生成任务: 每周{report_day} {report_hour:02d}:{report_minute:02d} 执行")

        monitor_interval = settings.DEPARTMENT_MONITOR_INTERVAL * 60
        self.scheduler.add_job(
            self._run_department_health_monitoring,
            trigger=IntervalTrigger(seconds=monitor_interval),
            id="department_health_monitoring",
            name="部门健康监控",
            replace_existing=True
        )
        logger.info(f"已注册部门健康监控任务: 每 {monitor_interval} 秒执行")

        self.scheduler.add_job(
            self._run_baseline_calculation,
            trigger=CronTrigger(hour=1, minute=0),
            id="baseline_calculation",
            name="每日基线计算",
            replace_existing=True
        )
        logger.info("已注册基线计算任务: 每天 01:00 执行")

        self.scheduler.start()
        self._is_running = True

        atexit.register(self.stop)

        logger.info("定时任务调度器启动成功")
        logger.info(f"当前已注册任务:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")

    def stop(self):
        if not self._is_running:
            logger.info("停止定时任务调度器")
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("定时任务调度器已停止")

    def get_jobs(self):
        return self.scheduler.get_jobs()

    def run_task_now(self, task_id: str):
        job = self.scheduler.get_job(task_id)
        if job:
            logger.info(f"立即执行任务: {task_id}")
            job.modify(next_run_time=datetime.now())
            return True
        return False

    def pause_task(self, task_id: str):
        job = self.scheduler.get_job(task_id)
        if job:
            job.pause()
            logger.info(f"暂停任务: {task_id}")
            return True
        return False

    def resume_task(self, task_id: str):
        job = self.scheduler.get_job(task_id)
        if job:
            job.resume()
            logger.info(f"恢复任务: {task_id}")
            return True
        return False


_scheduler_instance: Optional[HealthScheduler] = None


def get_scheduler() -> HealthScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = HealthScheduler()
    return _scheduler_instance


def start_scheduler():
    scheduler = get_scheduler()
    scheduler.start()
    return scheduler


def stop_scheduler():
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None
