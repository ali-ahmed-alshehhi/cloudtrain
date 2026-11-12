"""JSON logs: one line per event, so logs can be searched by request_id."""

import json
import logging
import sys
from datetime import UTC, datetime

SERVICE_NAME = "project-service"
# Extra fields a log call may add, e.g. logger.info("request", extra={"status": 200})
EXTRA_FIELDS = ("request_id", "method", "path", "status", "duration_ms")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "service": SERVICE_NAME,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                line[field] = getattr(record, field)
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line)


def setup_logging(level: str) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(SERVICE_NAME)
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    return logger
