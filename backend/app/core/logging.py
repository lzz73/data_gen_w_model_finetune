"""
Logging Configuration
日志配置
"""
import logging
import sys
from datetime import datetime
from typing import Any
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from app.core.config import get_settings

settings = get_settings()

# Log directory - 使用项目根目录作为绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app 的父目录
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日期格式
LOG_DATE = datetime.now().strftime("%Y-%m-%d")

# 当天的日志目录
CURRENT_LOG_DIR = LOG_DIR / LOG_DATE
CURRENT_LOG_DIR.mkdir(exist_ok=True)


def get_log_path(filename: str) -> Path:
    """获取当天的日志文件路径"""
    return CURRENT_LOG_DIR / filename


def setup_logging(name: str = "yg_dataset") -> logging.Logger:
    """Setup application logging"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Main log file handler - app.log
    main_file_handler = TimedRotatingFileHandler(
        get_log_path("app.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    main_file_handler.setLevel(logging.INFO)
    main_file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    main_file_handler.setFormatter(main_file_formatter)
    logger.addHandler(main_file_handler)

    return logger


# Create default logger
logger = setup_logging()


# ============== Success Logger ==============
def get_success_logger() -> logging.Logger:
    """获取成功日志记录器"""
    success_logger = logging.getLogger("yg_dataset.success")
    if not success_logger.handlers:
        handler = RotatingFileHandler(
            get_log_path("success.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=30,
            encoding="utf-8"
        )
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        success_logger.addHandler(handler)
        success_logger.setLevel(logging.INFO)
    return success_logger


# ============== Failure Logger ==============
def get_failure_logger() -> logging.Logger:
    """获取失败日志记录器"""
    failure_logger = logging.getLogger("yg_dataset.failure")
    if not failure_logger.handlers:
        handler = RotatingFileHandler(
            get_log_path("failure.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=30,
            encoding="utf-8"
        )
        handler.setLevel(logging.DEBUG)  # 改为 DEBUG 以便记录更多信息
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        failure_logger.addHandler(handler)
        failure_logger.setLevel(logging.DEBUG)  # 改为 DEBUG
    return failure_logger


# ============== Convenience functions ==============
def log_success(message: str, **kwargs):
    """记录成功日志"""
    extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()]) if kwargs else ""
    full_message = f"{message} | {extra_info}" if extra_info else message
    get_success_logger().info(full_message)


def log_failure(message: str, exc_info: bool = False, **kwargs):
    """记录失败日志"""
    extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()]) if kwargs else ""
    full_message = f"{message} | {extra_info}" if extra_info else message
    if exc_info:
        get_failure_logger().exception(full_message)
    else:
        get_failure_logger().error(full_message)


class LoggerMixin:
    """Mixin to add logging capability to classes"""

    @property
    def log(self) -> logging.Logger:
        """Get logger for this class"""
        return logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
