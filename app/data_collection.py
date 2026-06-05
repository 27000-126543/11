import random
import asyncio
import httpx
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy import func
from tenacity import retry, stop_after_attempt, wait_exponential

from .database import get_db_context
from .models import Employee, HealthData
from .logging_config import get_logger, log_data_collection, log_audit
from .config import get_settings

settings = get_settings()
logger = get_logger(__name__)


class HealthDataSource:
    SMART_BAND = "smart_band"
    HEALTH_APP = "health_app"
    MANUAL = "manual"


class DataCollector:
    def __init__(self):
        self.max_workers = 50
        self.timeout = 30.0

    async def collect_all_employees_data_async(self, data_date: Optional[date] = None) -> Tuple[int, int]:
        data_date = data_date or date.today()

        with get_db_context() as db:
            employees = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.device_id != None
            ).all()

        total = len(employees)
        success = 0

        semaphore = asyncio.Semaphore(20)

        async def collect_with_semaphore(employee: Employee):
            async with semaphore:
                return await self.collect_employee_data_async(employee, data_date)

        tasks = [collect_with_semaphore(emp) for emp in employees]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result and not isinstance(result, Exception):
                success += 1

        logger.info(f"批量数据采集完成: 总计{total}人, 成功{success}人, 失败{total-success}人")
        return total, success

    def collect_all_employees_data(self, data_date: Optional[date] = None) -> Tuple[int, int]:
        data_date = data_date or date.today()

        with get_db_context() as db:
            employees = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.device_id != None
            ).all()

        total = len(employees)
        success = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.collect_employee_data, emp, data_date): emp
                for emp in employees
            }

            for future in as_completed(futures):
                emp = futures[future]
                try:
                    result = future.result()
                    if result:
                        success += 1
                except Exception as e:
                    logger.error(f"采集员工{emp.id}({emp.name})数据失败: {str(e)}")
                    log_data_collection(emp.id, "batch", "failed", str(e))

        logger.info(f"批量数据采集完成: 总计{total}人, 成功{success}人, 失败{total-success}人")
        return total, success

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def collect_employee_data_async(self, employee: Employee, data_date: date) -> bool:
        try:
            health_data = self._generate_mock_health_data(employee, data_date)

            if employee.device_id and employee.device_id.startswith("APP_"):
                data_source = HealthDataSource.HEALTH_APP
            else:
                data_source = HealthDataSource.SMART_BAND

            health_data["data_source"] = data_source
            health_data["employee_id"] = employee.id
            health_data["data_date"] = data_date

            await self._save_health_data_async(health_data)

            log_data_collection(employee.id, data_source, "success", f"日期:{data_date}")
            return True

        except Exception as e:
            logger.error(f"异步采集员工{employee.id}数据失败: {str(e)}")
            log_data_collection(employee.id, "async", "failed", str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def collect_employee_data(self, employee: Employee, data_date: date) -> bool:
        try:
            health_data = self._generate_mock_health_data(employee, data_date)

            if employee.device_id and employee.device_id.startswith("APP_"):
                data_source = HealthDataSource.HEALTH_APP
            else:
                data_source = HealthDataSource.SMART_BAND

            health_data["data_source"] = data_source
            health_data["employee_id"] = employee.id
            health_data["data_date"] = data_date

            self._save_health_data(health_data)

            log_data_collection(employee.id, data_source, "success", f"日期:{data_date}")
            return True

        except Exception as e:
            logger.error(f"采集员工{employee.id}数据失败: {str(e)}")
            log_data_collection(employee.id, data_source, "failed", str(e))
            raise

    def _generate_mock_health_data(self, employee: Employee, data_date: date) -> Dict:
        age_factor = min(employee.age / 30.0, 1.5) if employee.age else 1.0

        base_heart_rate = int(70 + random.gauss(0, 5))
        heart_rate = int(max(50, min(100, base_heart_rate + random.gauss(0, 8))))
        heart_rate_resting = int(max(55, min(85, base_heart_rate - 5 + random.gauss(0, 3))))

        base_steps = int(8000 / age_factor)
        steps = int(max(1000, min(20000, base_steps + random.gauss(0, 3000))))

        base_sleep = 7.5 - (age_factor - 1) * 1.5
        sleep_duration = round(max(3.0, min(10.0, base_sleep + random.gauss(0, 1.0)), 1))

        deep_sleep_ratio = random.uniform(0.15, 0.25)
        light_sleep_ratio = random.uniform(0.45, 0.60)
        rem_sleep_ratio = random.uniform(0.15, 0.25)

        deep_sleep = round(sleep_duration * deep_sleep_ratio, 1)
        light_sleep = round(sleep_duration * light_sleep_ratio, 1)
        rem_sleep = round(sleep_duration * rem_sleep_ratio, 1)
        sleep_awake_time = round(sleep_duration * (1 - deep_sleep_ratio - light_sleep_ratio - rem_sleep_ratio), 1)

        sleep_score = int(min(100, max(50, 70 + (sleep_duration - 7) * 5 + random.gauss(0, 5))))

        anom_prob = random.random()
        if anom_prob < 0.08:
            anomaly_type = random.choice(["heart_rate_high", "heart_rate_low", "steps_low", "sleep_low"])
            if anomaly_type == "heart_rate_high":
                heart_rate = int(110 + random.randint(0, 30))
            elif anomaly_type == "heart_rate_low":
                heart_rate = int(45 + random.randint(0, 10))
            elif anomaly_type == "steps_low":
                steps = int(1000 + random.randint(0, 2000))
            elif anomaly_type == "sleep_low":
                sleep_duration = round(3.0 + random.random() * 2.0, 1)
                sleep_score = int(40 + random.randint(0, 15))

        systolic_bp = int(115 + random.gauss(0, 8))
        diastolic_bp = int(75 + random.gauss(0, 5))

        return {
            "heart_rate": heart_rate,
            "heart_rate_resting": heart_rate_resting,
            "heart_rate_variability": round(random.uniform(20, 70), 1),
            "steps": steps,
            "distance": round(steps * 0.0007, 2),
            "calories_burned": round(steps * 0.04 + random.randint(200, 400), 1),
            "sleep_duration": sleep_duration,
            "deep_sleep": deep_sleep,
            "light_sleep": light_sleep,
            "rem_sleep": rem_sleep,
            "sleep_awake_time": sleep_awake_time,
            "sleep_score": sleep_score,
            "systolic_bp": max(90, min(160, systolic_bp)),
            "diastolic_bp": max(60, min(100, diastolic_bp)),
            "blood_oxygen": round(random.uniform(95.0, 100.0), 1),
            "stress_level": int(random.uniform(1, 10)),
        }

    async def _save_health_data_async(self, health_data: Dict):
        def _save():
            with get_db_context() as db:
                existing = db.query(HealthData).filter(
                    HealthData.employee_id == health_data["employee_id"],
                    HealthData.data_date == health_data["data_date"]
                ).first()

                if existing:
                    for key, value in health_data.items():
                        if hasattr(existing, key) and key not in ["employee_id", "data_date"]:
                            setattr(existing, key, value)
                else:
                    db_health_data = HealthData(**health_data)
                    db.add(db_health_data)
                db.commit()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save)

    def _save_health_data(self, health_data: Dict):
        with get_db_context() as db:
            existing = db.query(HealthData).filter(
                HealthData.employee_id == health_data["employee_id"],
                HealthData.data_date == health_data["data_date"]
            ).first()

            if existing:
                for key, value in health_data.items():
                    if hasattr(existing, key) and key not in ["employee_id", "data_date"]:
                        setattr(existing, key, value)
            else:
                db_health_data = HealthData(**health_data)
                db.add(db_health_data)
            db.commit()

    def collect_historical_data(self, employee: Employee, days: int = 60):
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days)

        current = start_date
        while current <= end_date:
            try:
                self.collect_employee_data(employee, current)
            except Exception as e:
                logger.warning(f"历史数据采集失败 - 员工{employee.id}, 日期{current}: {e}")
            current += timedelta(days=1)

        logger.info(f"员工{employee.id}历史数据采集完成: {days}天")


class APIDataCollector(DataCollector):
    def __init__(self, api_base_url: str, api_key: str):
        super().__init__()
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def fetch_from_smart_band_api(self, device_id: str, data_date: date) -> Optional[Dict]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"device_id": device_id, "date": data_date.isoformat()}

            response = await self.client.get(
                f"{self.api_base_url}/smartband/data",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"从智能手环API获取数据失败: {str(e)}")
            return None

    async def fetch_from_health_app_api(self, account: str, data_date: date) -> Optional[Dict]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"account": account, "date": data_date.isoformat()}

            response = await self.client.get(
                f"{self.api_base_url}/healthapp/data",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"从健康App API获取数据失败: {str(e)}")
            return None

    async def close(self):
        await self.client.aclose()


def get_data_collector() -> DataCollector:
    return DataCollector()
