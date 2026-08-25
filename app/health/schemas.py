from typing import Literal

from pydantic import BaseModel

from app.core.exceptions import ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ServiceStates(BaseModel):
    database: Literal["up", "down"]
    redis: Literal["up", "down"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    services: ServiceStates


class ReadinessUnavailableResponse(BaseModel):
    error: ErrorDetail
    services: ServiceStates
