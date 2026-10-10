"""FastAPI dependencies: shared state and role checks (M41)."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from packages.adapters.registry import Adapters
from packages.core.enums import Role
from packages.core.errors import ForbiddenError
from packages.core.params import ParamRegistry
from packages.core.settings import AppSettings

__all__ = ["AppState", "Principal", "StateDep", "get_principal", "get_state", "require_role"]


@dataclass
class AppState:
    """Everything request handlers need, built once at startup."""

    settings: AppSettings
    adapters: Adapters
    params: ParamRegistry


@dataclass(frozen=True)
class Principal:
    role: Role


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.coolroof
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def _matches(candidate: str, secret: str | None) -> bool:
    return bool(secret) and hmac.compare_digest(candidate, secret or "")


def get_principal(
    state: StateDep,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal:
    """Phase 1 auth: anonymous by default; API keys unlock planner/admin (Cognito in Phase 2)."""
    if x_api_key:
        settings = state.settings
        admin = settings.admin_api_key.get_secret_value() if settings.admin_api_key else None
        planner = settings.planner_api_key.get_secret_value() if settings.planner_api_key else None
        if _matches(x_api_key, admin):
            return Principal(Role.ADMIN)
        if _matches(x_api_key, planner):
            return Principal(Role.PLANNER)
    return Principal(Role.ANON)


def require_role(minimum: Role) -> Callable[[Principal], Principal]:
    """Dependency factory: 403 unless the caller's role is at least ``minimum``."""

    def check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.role.level < minimum.level:
            raise ForbiddenError(f"requires role {minimum.value}")
        return principal

    return check
