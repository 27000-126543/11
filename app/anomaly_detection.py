import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, as_completed

from .database import get_db_context
from .models import Employee, HealthData, HealthBaseline, AlertTicket, HealthAdmin
from .logging_config import get_logger, log_alert
from .config import get_settings

settings = get_settings()
logger = get_logger(__name__)


class MetricType:
    HEART_RATE = "heart_rate"
    HEART_RATE_RESTING = "heart_rate_resting"
    STEPS = "steps"
    SLEEP_DURATION = "sleep_duration"
    DEEP_SLEEP = "deep_sleep"
    SLEEP_SCORE = "sleep_score"
    BLOOD_OXYGEN = "blood_oxygen"
    STRESS_LEVEL = "stress_level"


class AlertSeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyDirection:
    HIGH = "high"
    LOW = "low"


METRIC_THRESHOLDS = {
    MetricType.HEART_RATE: {
        "high": 20,
        "low": 15,
        "critical_high": settings.HEART_RATE_UPPER_LIMIT,
        "critical_low": settings.HEART_RATE_LOWER_LIMIT,
    },
    MetricType.HEART_RATE_RESTING: {
        "high": 20,
        "low": 15,
        "critical_high": 90,
        "critical_low": 50,
    },
    MetricType.STEPS: {
        "high": None,
        "low": 30,
        "critical_low": settings.STEPS_MIN_DAILY,
    },
    MetricType.SLEEP_DURATION: {
        "high": 20,
        "low": 25,
        "critical_low": settings.SLEEP_MIN_HOURS,
    },
    MetricType.DEEP_SLEEP: {
        "high": None,
        "low": 30,
        "critical_low": 0.5,
    },
    MetricType.SLEEP_SCORE: {
        "high": None,
        "low": 20,
        "critical_low": 50,
    },
    MetricType.BLOOD_OXYGEN: {
        "high": None,
        "low": 5,
        "critical_low": 92,
    },
    MetricType.STRESS_LEVEL: {
        "high": 30,
        "low": None,
        "critical_high": 8,
    },
}

METRIC_NAMES_CN = {
    MetricType.HEART_RATE: "心率",
    MetricType.HEART_RATE_RESTING: "静息心率",
    MetricType.STEPS: "步数",
    MetricType.SLEEP_DURATION: "睡眠时长",
    MetricType.DEEP_SLEEP: "深睡时长",
    MetricType.SLEEP_SCORE: "睡眠评分",
    MetricType.BLOOD_OXYGEN: "血氧饱和度",
    MetricType.STRESS_LEVEL: "压力水平",
}


class BaselineCalculator:
    def __init__(self, baseline_days: int = 30):
        self.baseline_days = baseline_days

    def calculate_employee_baselines(self, employee_id: int, calc_date: Optional[date] = None) -> List[HealthBaseline]:
        calc_date = calc_date or date.today()
        start_date = calc_date - timedelta(days=self.baseline_days)
        end_date = calc_date - timedelta(days=1)

        with get_db_context() as db:
            health_data = db.query(HealthData).filter(
                HealthData.employee_id == employee_id,
                HealthData.data_date >= start_date,
                HealthData.data_date <= end_date
            ).order_by(HealthData.data_date).all()

            if len(health_data) < self.baseline_days // 2:
                logger.warning(f"员工{employee_id}基线数据不足: {len(health_data)}/{self.baseline_days}天")
                return []

            baselines = []
            metric_columns = [
                MetricType.HEART_RATE,
                MetricType.HEART_RATE_RESTING,
                MetricType.STEPS,
                MetricType.SLEEP_DURATION,
                MetricType.DEEP_SLEEP,
                MetricType.SLEEP_SCORE,
                MetricType.BLOOD_OXYGEN,
                MetricType.STRESS_LEVEL,
            ]

            for metric in metric_columns:
                values = [getattr(d, metric) for d in health_data if getattr(d, metric) is not None]
                if len(values) < 10:
                    continue

                values_array = np.array(values)
                baseline = self._calculate_baseline_stats(
                    employee_id=employee_id,
                    metric_name=metric,
                    values=values_array,
                    calc_date=calc_date
                )
                baselines.append(baseline)

            existing_baselines = db.query(HealthBaseline).filter(
                HealthBaseline.employee_id == employee_id,
                HealthBaseline.calculation_date == calc_date
            ).all()

            existing_metrics = {b.metric_name for b in existing_baselines}

            for baseline in baselines:
                if baseline.metric_name in existing_metrics:
                    continue
                db.add(baseline)

            db.commit()

            logger.info(f"员工{employee_id}基线计算完成: {len(baselines)}个指标")
            return baselines

    def _calculate_baseline_stats(
        self,
        employee_id: int,
        metric_name: str,
        values: np.ndarray,
        calc_date: date
    ) -> HealthBaseline:
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        filtered_values = values[(values >= lower_bound) & (values <= upper_bound)]

        if len(filtered_values) < 5:
            filtered_values = values

        return HealthBaseline(
            employee_id=employee_id,
            metric_name=metric_name,
            baseline_value=float(np.mean(filtered_values)),
            std_dev=float(np.std(filtered_values)),
            min_value=float(np.min(filtered_values)),
            max_value=float(np.max(filtered_values)),
            percentile_25=float(np.percentile(filtered_values, 25)),
            percentile_50=float(np.percentile(filtered_values, 50)),
            percentile_75=float(np.percentile(filtered_values, 75)),
            data_count=len(filtered_values),
            calculation_date=calc_date,
            baseline_days=self.baseline_days
        )

    def get_latest_baseline(self, employee_id: int, metric_name: str, db: Session) -> Optional[HealthBaseline]:
        return db.query(HealthBaseline).filter(
            HealthBaseline.employee_id == employee_id,
            HealthBaseline.metric_name == metric_name
        ).order_by(HealthBaseline.calculation_date.desc()).first()

    def calculate_all_baselines(self) -> Tuple[int, int]:
        with get_db_context() as db:
            employees = db.query(Employee).filter(Employee.is_active == True).all()

        total = len(employees)
        success = 0

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(self.calculate_employee_baselines, emp.id): emp
                for emp in employees
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        success += 1
                except Exception as e:
                    logger.error(f"计算基线失败: {str(e)}")

        logger.info(f"全体员工基线计算完成: 成功{success}/{total}")
        return total, success


class AnomalyDetector:
    def __init__(self):
        self.baseline_calculator = BaselineCalculator(settings.BASELINE_DAYS)

    def detect_employee_anomalies(
        self,
        employee_id: int,
        health_data: HealthData,
        db: Session
    ) -> List[Dict]:
        anomalies = []

        metric_columns = [
            MetricType.HEART_RATE,
            MetricType.HEART_RATE_RESTING,
            MetricType.STEPS,
            MetricType.SLEEP_DURATION,
            MetricType.DEEP_SLEEP,
            MetricType.SLEEP_SCORE,
            MetricType.BLOOD_OXYGEN,
            MetricType.STRESS_LEVEL,
        ]

        for metric in metric_columns:
            current_value = getattr(health_data, metric)
            if current_value is None:
                continue

            baseline = self.baseline_calculator.get_latest_baseline(employee_id, metric, db)
            if not baseline:
                continue

            anomaly = self._check_anomaly(metric, current_value, baseline)
            if anomaly:
                anomalies.append(anomaly)

        return anomalies

    def _check_anomaly(
        self,
        metric_name: str,
        current_value: float,
        baseline: HealthBaseline
    ) -> Optional[Dict]:
        thresholds = METRIC_THRESHOLDS.get(metric_name, {})
        baseline_value = baseline.baseline_value

        if baseline_value == 0:
            return None

        deviation_percent = ((current_value - baseline_value) / baseline_value) * 100
        direction = AnomalyDirection.HIGH if deviation_percent > 0 else AnomalyDirection.LOW

        is_anomaly = False
        severity = AlertSeverity.LOW
        threshold = 0

        if direction == AnomalyDirection.HIGH and thresholds.get("high") is not None:
            threshold = thresholds["high"]
            if deviation_percent > threshold:
                is_anomaly = True
                if thresholds.get("critical_high") and current_value >= thresholds["critical_high"]:
                    severity = AlertSeverity.CRITICAL
                elif deviation_percent > threshold * 1.5:
                    severity = AlertSeverity.HIGH
                elif deviation_percent > threshold:
                    severity = AlertSeverity.MEDIUM

        elif direction == AnomalyDirection.LOW and thresholds.get("low") is not None:
            threshold = thresholds["low"]
            if abs(deviation_percent) > threshold:
                is_anomaly = True
                if thresholds.get("critical_low") and current_value <= thresholds["critical_low"]:
                    severity = AlertSeverity.CRITICAL
                elif abs(deviation_percent) > threshold * 1.5:
                    severity = AlertSeverity.HIGH
                elif abs(deviation_percent) > threshold:
                    severity = AlertSeverity.MEDIUM

        if is_anomaly:
            return {
                "metric_name": metric_name,
                "metric_name_cn": METRIC_NAMES_CN.get(metric_name, metric_name),
                "current_value": current_value,
                "baseline_value": baseline_value,
                "deviation_percent": round(deviation_percent, 2),
                "direction": direction,
                "severity": severity,
                "threshold": threshold,
                "z_score": (current_value - baseline_value) / baseline.std_dev if baseline.std_dev > 0 else 0
            }

        return None

    def detect_all_anomalies(self, data_date: Optional[date] = None) -> Tuple[int, int]:
        data_date = data_date or date.today()
        total_processed = 0
        anomalies_found = 0

        with get_db_context() as db:
            health_data_list = db.query(HealthData).filter(
                HealthData.data_date == data_date,
                HealthData.processed == False
            ).all()

            for health_data in health_data_list:
                try:
                    employee_id = health_data.employee_id
                    anomalies = self.detect_employee_anomalies(employee_id, health_data, db)

                    if anomalies:
                        anomaly_details = {
                            "anomalies": anomalies,
                            "anomaly_count": len(anomalies),
                            "highest_severity": max([a["severity"] for a in anomalies],
                                                     key=lambda s: [AlertSeverity.LOW, AlertSeverity.MEDIUM,
                                                                    AlertSeverity.HIGH, AlertSeverity.CRITICAL].index(s))
                        }
                        health_data.is_anomaly = True
                        health_data.anomaly_details = anomaly_details
                        anomalies_found += 1

                    health_data.processed = True
                    total_processed += 1

                except Exception as e:
                    logger.error(f"异常检测失败 - 健康数据{health_data.id}: {str(e)}")

            db.commit()

        logger.info(f"异常检测完成: 处理{total_processed}条, 发现{anomalies_found}条异常")
        return total_processed, anomalies_found

    def check_consecutive_anomalies(
        self,
        employee_id: int,
        metric_name: str,
        days: int = 3
    ) -> Tuple[int, List[HealthData]]:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        with get_db_context() as db:
            health_data = db.query(HealthData).filter(
                HealthData.employee_id == employee_id,
                HealthData.data_date >= start_date,
                HealthData.data_date <= end_date,
                HealthData.is_anomaly == True
            ).order_by(HealthData.data_date.desc()).all()

            consecutive_count = 0
            consecutive_data = []

            current_date = end_date
            for _ in range(days):
                day_data = [d for d in health_data if d.data_date == current_date]
                has_anomaly = False

                for d in day_data:
                    if d.anomaly_details and "anomalies" in d.anomaly_details:
                        metric_anomalies = [a for a in d.anomaly_details["anomalies"]
                                            if a["metric_name"] == metric_name]
                        if metric_anomalies:
                            has_anomaly = True
                            consecutive_data.append(d)
                            break

                if has_anomaly:
                    consecutive_count += 1
                else:
                    break

                current_date -= timedelta(days=1)

            return consecutive_count, consecutive_data


def get_anomaly_detector() -> AnomalyDetector:
    return AnomalyDetector()


def get_baseline_calculator() -> BaselineCalculator:
    return BaselineCalculator(settings.BASELINE_DAYS)
