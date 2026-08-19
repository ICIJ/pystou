import json
import logging
import os
from datetime import datetime
from logging import handlers
from typing import Optional

from common import paths


def setup_logging(script_name: str = "script", log_dir: Optional[str] = None) -> None:
    """Sets up JSON logging to a timestamped file.

    Idempotent: clears handlers added by previous calls so dispatching a
    subcommand (or running tests) does not duplicate log lines.

    Args:
        script_name (str): Name of the script (used in log filename).
        log_dir (Optional[str]): Directory to store log files. Defaults to the
            XDG log directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = log_dir if log_dir else str(paths.log_dir())
    log_filename = os.path.join(directory, f"{script_name}.{timestamp}.log")
    handler = handlers.RotatingFileHandler(log_filename, maxBytes=10485760, backupCount=5)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger()
    for existing in logger.handlers[:]:
        logger.removeHandler(existing)
        existing.close()
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
            "message": record.msg,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)
