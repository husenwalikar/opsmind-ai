"""
Enterprise Structured JSON Logger
Outputs machine-readable logs with timestamps, service name, and correlation IDs.
"""
import json
import logging
import sys
from datetime import datetime, timezone
import uuid

class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "shopflow-api",
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", str(uuid.uuid4())[:8])
        }
        if record.exc_info:
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_structured_logger(name: str = "shopflow"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
    return logger

log = get_structured_logger()