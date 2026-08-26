from typing import Annotated, Protocol

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.auth.principal import (
    ApiPrincipal,
    AuthUnavailableError,
    InvalidApiKeyError,
)
from app.core.exceptions import AppError

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="X-API-Key",
)


class ApiKeyVerifier(Protocol):
    async def verify(self, secret: str) -> ApiPrincipal: ...


async def get_api_key_verifier(request: Request) -> ApiKeyVerifier:
    verifier = getattr(request.app.state, "api_key_verifier", None)
    if verifier is None:
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "A required service is unavailable",
        )
    return verifier


async def get_principal(
    api_key: Annotated[str | None, Security(api_key_header)],
    verifier: Annotated[ApiKeyVerifier, Depends(get_api_key_verifier)],
) -> ApiPrincipal:
    if not api_key:
        raise AppError(401, "API_KEY_REQUIRED", "API key required")
    try:
        return await verifier.verify(api_key)
    except InvalidApiKeyError:
        raise AppError(401, "INVALID_API_KEY", "Invalid API key") from None
    except AuthUnavailableError:
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "A required service is unavailable",
        ) from None


def require_scopes(*required: str):
    async def dependency(
        principal: Annotated[ApiPrincipal, Depends(get_principal)],
    ) -> ApiPrincipal:
        if not set(required) <= principal.scopes:
            raise AppError(
                403,
                "INSUFFICIENT_PERMISSIONS",
                "Insufficient permissions",
            )
        return principal

    return dependency
