from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import cast

from clerk_backend_api import Clerk
from clerk_backend_api.models.clerkbaseerror import ClerkBaseError
from clerk_backend_api.utils.retries import BackoffStrategy, RetryConfig

from app.auth.principal import (
    ApiPrincipal,
    AuthUnavailableError,
    InvalidApiKeyError,
)

_INVALID_STATUSES = frozenset({400, 404})
_NO_RETRIES = RetryConfig("none", BackoffStrategy(0, 0, 0, 0), False)

VerifyApiKey = Callable[..., Awaitable[object]]


class UnavailableApiKeyVerifier:
    async def verify(self, secret: str) -> ApiPrincipal:
        raise AuthUnavailableError


class ClerkApiKeyVerifier:
    def __init__(self, verify_api_key: VerifyApiKey, timeout_ms: int) -> None:
        self._verify_api_key = verify_api_key
        self._timeout_ms = timeout_ms

    async def verify(self, secret: str) -> ApiPrincipal:
        try:
            result = await self._verify_api_key(
                secret=secret,
                timeout_ms=self._timeout_ms,
                retries=_NO_RETRIES,
            )
        except ClerkBaseError as exc:
            if exc.status_code in _INVALID_STATUSES:
                raise InvalidApiKeyError from None
            raise AuthUnavailableError from None
        except Exception:
            raise AuthUnavailableError from None

        if getattr(result, "expired", False) or getattr(result, "revoked", False):
            raise InvalidApiKeyError

        subject = getattr(result, "subject", None)
        if not isinstance(subject, str) or not subject:
            raise InvalidApiKeyError

        scopes: list[str] = []
        raw_scopes = getattr(result, "scopes", None)
        if isinstance(raw_scopes, list):
            for item in cast(list[object], raw_scopes):
                if isinstance(item, str):
                    scopes.append(item)
        return ApiPrincipal(user_id=subject, scopes=frozenset(scopes))


async def bind_api_key_verifier(
    stack: AsyncExitStack,
    secret: str | None,
    timeout_ms: int,
) -> UnavailableApiKeyVerifier | ClerkApiKeyVerifier:
    if not secret:
        return UnavailableApiKeyVerifier()
    client = await stack.enter_async_context(
        cast(
            AbstractAsyncContextManager[Clerk],
            Clerk(bearer_auth=secret, timeout_ms=timeout_ms),
        )
    )
    return ClerkApiKeyVerifier(
        client.api_keys.verify_api_key_async,
        timeout_ms,
    )
