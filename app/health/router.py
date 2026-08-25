from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorDetail, ErrorResponse
from app.health.checks import ReadinessChecks, get_readiness_checks
from app.health.schemas import (
    HealthResponse,
    ReadinessResponse,
    ReadinessUnavailableResponse,
    ServiceStates,
)

router = APIRouter(prefix="/health", tags=["health"])
REQUEST_ID_HEADERS: dict[str, dict[str, object]] = {
    "X-Request-ID": {
        "description": "Request correlation identifier",
        "schema": {"type": "string"},
    }
}


@router.get(
    "",
    response_model=HealthResponse,
    responses={
        200: {"headers": REQUEST_ID_HEADERS},
        500: {"model": ErrorResponse, "headers": REQUEST_ID_HEADERS},
    },
)
async def liveness() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"headers": REQUEST_ID_HEADERS},
        500: {"model": ErrorResponse, "headers": REQUEST_ID_HEADERS},
        503: {
            "model": ReadinessUnavailableResponse,
            "headers": REQUEST_ID_HEADERS,
        },
    },
)
async def readiness(
    checks: Annotated[ReadinessChecks, Depends(get_readiness_checks)],
) -> ReadinessResponse | JSONResponse:
    result = await checks.run()
    services = ServiceStates(
        database="up" if result.database else "down",
        redis="up" if result.redis else "down",
    )
    if not result.is_ready:
        unavailable = ReadinessUnavailableResponse(
            error=ErrorDetail(
                code="SERVICE_UNAVAILABLE",
                message="A required service is unavailable",
            ),
            services=services,
        )
        return JSONResponse(status_code=503, content=unavailable.model_dump())
    return ReadinessResponse(services=services)
