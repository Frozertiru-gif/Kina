import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def __init__(self, *, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "service": self.service,
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "action": getattr(record, "action", None),
            "request_id": getattr(record, "request_id", None),
            "tg_user_id": getattr(record, "tg_user_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service="bot"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
