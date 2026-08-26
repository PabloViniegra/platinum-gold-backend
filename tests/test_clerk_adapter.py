from types import SimpleNamespace

import httpx
import pytest
from clerk_backend_api.models.clerkbaseerror import ClerkBaseError

from app.auth.clerk import ClerkApiKeyVerifier, UnavailableApiKeyVerifier
from app.auth.principal import AuthUnavailableError, InvalidApiKeyError


class FakeApiKeys:
    def __init__(
        self,
        result: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    async def verify_api_key_async(
        self,
        *,
        secret: str,
        timeout_ms: int | None = None,
        retries: object = None,
    ) -> object:
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def clerk_error(status_code: int) -> ClerkBaseError:
    request = httpx.Request("POST", "https://api.clerk.com/v1/api_keys/verify")
    return ClerkBaseError("clerk error", httpx.Response(status_code, request=request))


def verify_result(
    *,
    subject: str = "user_1",
    scopes: list[str] | None = None,
    expired: bool = False,
    revoked: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        subject=subject,
        scopes=scopes or ["api:access"],
        expired=expired,
        revoked=revoked,
    )


@pytest.mark.asyncio
async def test_maps_subject_and_scopes_to_principal() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(
            result=verify_result(scopes=["api:access", "items:read"])
        ).verify_api_key_async,
        timeout_ms=2000,
    )

    principal = await verifier.verify("ak_valid")

    assert principal.user_id == "user_1"
    assert principal.scopes == frozenset({"api:access", "items:read"})


@pytest.mark.asyncio
async def test_expired_key_is_invalid() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(result=verify_result(expired=True)).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(InvalidApiKeyError):
        await verifier.verify("ak_expired")


@pytest.mark.asyncio
async def test_revoked_key_is_invalid() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(result=verify_result(revoked=True)).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(InvalidApiKeyError):
        await verifier.verify("ak_revoked")


@pytest.mark.asyncio
async def test_clerk_400_is_invalid() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(error=clerk_error(400)).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(InvalidApiKeyError):
        await verifier.verify("ak_bad")


@pytest.mark.asyncio
async def test_clerk_404_is_invalid() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(error=clerk_error(404)).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(InvalidApiKeyError):
        await verifier.verify("ak_missing")


@pytest.mark.asyncio
async def test_clerk_500_is_unavailable() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(error=clerk_error(500)).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(AuthUnavailableError):
        await verifier.verify("ak_valid")


@pytest.mark.asyncio
async def test_timeout_is_unavailable() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(error=TimeoutError()).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(AuthUnavailableError):
        await verifier.verify("ak_valid")


@pytest.mark.asyncio
async def test_transport_error_is_unavailable() -> None:
    verifier = ClerkApiKeyVerifier(
        FakeApiKeys(error=ConnectionError("clerk unreachable")).verify_api_key_async,
        timeout_ms=2000,
    )

    with pytest.raises(AuthUnavailableError):
        await verifier.verify("ak_valid")


@pytest.mark.asyncio
async def test_missing_secret_verifier_is_unavailable() -> None:
    verifier = UnavailableApiKeyVerifier()

    with pytest.raises(AuthUnavailableError):
        await verifier.verify("ak_valid")
