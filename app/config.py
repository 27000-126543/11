from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    APP_NAME: str = "EmployeeHealthManagement"
    APP_ENV: str = "development"
    APP_PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./health_management.db"

    SECRET_KEY: str = "default-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    SCHEDULER_ENABLED: bool = True
    DAILY_COLLECTION_HOUR: int = 8
    DAILY_COLLECTION_MINUTE: int = 0
    WEEKLY_REPORT_DAY: int = 0
    WEEKLY_REPORT_HOUR: int = 2
    WEEKLY_REPORT_MINUTE: int = 0
    BASELINE_CALCULATION_HOUR: int = 1
    BASELINE_CALCULATION_MINUTE: int = 0
    DEPARTMENT_MONITOR_INTERVAL: int = 60

    ANOMALY_THRESHOLD_STD: float = 2.0
    CRITICAL_ANOMALY_THRESHOLD_STD: float = 3.5
    HEART_RATE_UPPER_LIMIT: int = 100
    HEART_RATE_LOWER_LIMIT: int = 50
    SLEEP_MIN_HOURS: float = 5.0
    SLEEP_MAX_HOURS: float = 10.0
    STEPS_MIN_DAILY: int = 3000
    STEPS_MAX_DAILY: int = 20000
    DEPARTMENT_ANOMALY_THRESHOLD: float = 0.2
    CONSECUTIVE_DAYS_THRESHOLD: int = 3

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10485760

    OCR_LANGUAGE: str = "chi_sim+eng"
    TESSERACT_CMD: str = "/usr/bin/tesseract"

    LOG_DIR: str = "./logs"
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 10485760
    LOG_BACKUP_COUNT: int = 10

    MAX_WORKERS: int = 50
    ASYNC_SEMAPHORE_LIMIT: int = 20
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30

    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    NOTIFICATION_FROM_EMAIL: str = "noreply@company.com"
    HR_EMAIL: str = "hr@company.com"

    BASELINE_DAYS: int = 30


@lru_cache()
def get_settings() -> Settings:
    return Settings()
