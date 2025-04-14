import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FILE_PATH = "logs/app.log"

def get_app_logger(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        os.makedirs("logs", exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(filename)s | %(funcName)s | line:%(lineno)d | %(message)s"
        )

        file_handler = RotatingFileHandler(
            LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
