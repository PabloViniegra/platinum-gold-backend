import json
import logging
import re
import sys
import traceback
from time import perf_counter
from typing import cast
from uuid import uuid4

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import ErrorDetail, ErrorResponse

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
API_KEY_PATTERN = re.compile(r"ak_[A-Za-z0-9_-]+")
request_logger = logging.getLogger("app.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        for field in (
            "request_id",
            "method",
            "path",
            "status",
            "duration_ms",
            "dependency",
            "cache_resource",
            "cache_operation",
            "exception_type",
            "exception_file",
            "exception_function",
            "exception_line",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("app")
    app_logger.handlers = [handler]
    app_logger.setLevel(level)
    app_logger.propagate = False


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        candidate = Headers(scope=scope).get("X-Request-ID", "")
        request_id = (
            candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid4())
        )
        started_at = perf_counter()
        status = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                response_started = True
                status = cast(int, message["status"])
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exception:
            frames = traceback.extract_tb(exception.__traceback__)
            frame = frames[-1] if frames else None
            request_logger.error(
                "unhandled_request_error",
                extra={
                    "event": "unhandled_request_error",
                    "request_id": request_id,
                    "exception_type": type(exception).__name__,
                    "exception_file": frame.filename if frame else None,
                    "exception_function": frame.name if frame else None,
                    "exception_line": frame.lineno if frame else None,
                },
            )
            if response_started:
                raise
            error = ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="An internal error occurred",
                )
            )
            response = JSONResponse(status_code=500, content=error.model_dump())
            await response(scope, receive, send_with_request_id)
        finally:
            request_logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": API_KEY_PATTERN.sub("ak_[REDACTED]", scope["path"]),
                    "status": status,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
