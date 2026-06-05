import os
import logging
from typing import Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from concurrent_log_handler import ConcurrentRotatingFileHandler
from datetime import datetime

from .config import get_settings

settings = get_settings()

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging():
    log_dir = settings.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    log_level = LOG_LEVELS.get(settings.LOG_LEVEL.upper(), logging.INFO)

    logger = logging.getLogger("health_management")
    logger.setLevel(log_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    app_log_file = os.path.join(log_dir, "app.log")
    app_handler = ConcurrentRotatingFileHandler(
        app_log_file, maxBytes=10 * 1024 * 1024, backupCount=30, use_gzip=True
    )
    app_handler.setLevel(log_level)
    app_handler.setFormatter(formatter)
    logger.addHandler(app_handler)

    error_log_file = os.path.join(log_dir, "error.log")
    error_handler = ConcurrentRotatingFileHandler(
        error_log_file, maxBytes=10 * 1024 * 1024, backupCount=30, use_gzip=True
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    data_log_file = os.path.join(log_dir, "data_collection.log")
    data_handler = TimedRotatingFileHandler(
        data_log_file, when="midnight", interval=1, backupCount=90, encoding="utf-8"
    )
    data_handler.setLevel(logging.INFO)
    data_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    data_handler.setFormatter(data_formatter)
    data_logger = logging.getLogger("data_collection")
    data_logger.setLevel(logging.INFO)
    data_logger.addHandler(data_handler)
    data_logger.propagate = False

    alert_log_file = os.path.join(log_dir, "alerts.log")
    alert_handler = TimedRotatingFileHandler(
        alert_log_file, when="midnight", interval=1, backupCount=90, encoding="utf-8"
    )
    alert_handler.setLevel(logging.INFO)
    alert_handler.setFormatter(data_formatter)
    alert_logger = logging.getLogger("alerts")
    alert_logger.setLevel(logging.INFO)
    alert_logger.addHandler(alert_handler)
    alert_logger.propagate = False

    audit_log_file = os.path.join(log_dir, "audit.log")
    audit_handler = TimedRotatingFileHandler(
        audit_log_file, when="midnight", interval=1, backupCount=180, encoding="utf-8"
    )
    audit_handler.setLevel(logging.INFO)
    audit_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(user)s - %(action)s - %(detail)s"
    )
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False

    return logger


def get_logger(name: str = "health_management") -> logging.Logger:
    return logging.getLogger(name)


def log_audit(*args, **kwargs):
    audit_logger = logging.getLogger("audit")

    if len(args) >= 2:
        operation_type = args[0]
        operation_desc = args[1]
        operator_type = args[2] if len(args) > 2 else "system"
        operator_id = args[3] if len(args) > 3 else None
    else:
        operation_type = kwargs.get("action", kwargs.get("operation_type", "unknown"))
        operation_desc = kwargs.get("detail", kwargs.get("operation_desc", ""))
        user = kwargs.get("user", "system")
        if "_" in user:
            parts = user.split("_")
            operator_type = parts[0]
            operator_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        else:
            operator_type = user
            operator_id = None

    extra = {
        "operation_type": operation_type,
        "operation_desc": operation_desc,
        "operator_type": operator_type,
        "operator_id": operator_id
    }
    audit_logger.info(
        f"[{operator_type}] {operation_type}: {operation_desc}",
        extra=extra
    )


def log_data_collection(employee_id: int, data_type: str, status: str, detail: str = ""):
    data_logger = logging.getLogger("data_collection")
    data_logger.info(
        f"Employee: {employee_id}, Type: {data_type}, Status: {status}, Detail: {detail}"
    )


def log_alert(alert_id: int, employee_id: int, severity: str, message: str):
    alert_logger = logging.getLogger("alerts")
    alert_logger.info(
        f"Alert: {alert_id}, Employee: {employee_id}, Severity: {severity}, Message: {message}"
    )
