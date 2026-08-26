from dataclasses import dataclass


@dataclass(frozen=True)
class ApiPrincipal:
    user_id: str
    scopes: frozenset[str]


class InvalidApiKeyError(Exception):
    pass


class AuthUnavailableError(Exception):
    pass
