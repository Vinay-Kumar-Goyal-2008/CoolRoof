"""FastAPI dependencies: shared state and role checks (M41).

Auth, strongest first: Cognito Bearer token (when configured) → ``X-API-Key`` (local planner /
admin keys) → anonymous. ``X-Actor`` names the person behind an API key so the two-person rules
(advisory approval, incident confirmation) can tell staff apart.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request

from packages.adapters.registry import Adapters
from packages.api.auth import CognitoVerifier
from packages.core.enums import Role
from packages.core.errors import AuthenticationError, ForbiddenError
from packages.core.params import ParamRegistry
from packages.core.settings import AppSettings

__all__ = ["AppState", "Principal", "StateDep", "get_principal", "get_state", "require_role"]


@dataclass
class AppState:
    """Everything request handlers need, built once at startup."""

    settings: AppSettings
    adapters: Adapters
    params: ParamRegistry
    verifier: CognitoVerifier | None = field(default=None)

    def __post_init__(self) -> None:
        s = self.settings
        if self.verifier is None and s.cognito_issuer and s.cognito_client_id:
            self.verifier = CognitoVerifier(s.cognito_issuer, s.cognito_client_id)


@dataclass(frozen=True)
class Principal:
    role: Role
    actor: str = "anonymous"


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.coolroof
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def _matches(candidate: str, secret: str | None) -> bool:
    return bool(secret) and hmac.compare_digest(candidate, secret or "")


def get_principal(
    state: StateDep,
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_actor: Annotated[str | None, Header()] = None,
) -> Principal:
    if authorization and authorization.lower().startswith("bearer "):
        if state.verifier is None:
            raise AuthenticationError("bearer tokens are not enabled on this deployment")
        claims = state.verifier.verify(authorization[7:].strip())
        return Principal(claims.role, f"cognito:{claims.subject}")
    if x_api_key:
        settings = state.settings
        admin = settings.admin_api_key.get_secret_value() if settings.admin_api_key else None
        planner = settings.planner_api_key.get_secret_value() if settings.planner_api_key else None
        actor = (x_actor or "").strip()[:40] or None
        if _matches(x_api_key, admin):
            return Principal(Role.ADMIN, actor or "admin")
        if _matches(x_api_key, planner):
            return Principal(Role.PLANNER, actor or "planner")
        raise AuthenticationError("invalid API key")
    return Principal(Role.ANON)


def require_role(minimum: Role) -> Callable[[Principal], Principal]:
    """Dependency factory: 401/403 unless the caller's role is at least ``minimum``."""

    def check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.role.level < minimum.level:
            if principal.role is Role.ANON:
                raise AuthenticationError("authentication required")
            raise ForbiddenError(f"requires role {minimum.value}")
        return principal

    return check
