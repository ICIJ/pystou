from datetime import datetime
from logging import handlers
import json
import logging
import os


def setup_logging(script_name: str = "script", log_dir: str = ".") -> None:
    """Sets up JSON logging to a file with the current timestamp.

    Args:
        script_name (str): Name of the script (used in log filename).
        log_dir (str): Directory to store log files.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"{script_name}.{timestamp}.log")
    handler = handlers.RotatingFileHandler(
        log_filename, maxBytes=10485760, backupCount=5
    )
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


class JsonFormatter(logging.Formatter):
    """Custom logging formatter to output JSON-formatted logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Formats a log record as JSON.

        Args:
            record (logging.LogRecord): The log record.

        Returns:
            str: JSON-formatted log record.
        """
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.msg,  # Expected to be a dict
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)
