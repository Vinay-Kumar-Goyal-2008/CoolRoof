"""M41 Cognito token verification (Phase 2 auth).

When ``COGNITO_ISSUER`` and ``COGNITO_CLIENT_ID`` are set, ``Authorization: Bearer <jwt>`` is
verified against the pool's JWKS (RS256, issuer, expiry, client). Cognito groups map to roles:
``admin`` → ADMIN, ``planner`` → PLANNER, any other signed-in user → VIEWER. Without Cognito
settings only the API-key path in ``deps.py`` applies (local development).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt

from packages.core.enums import Role
from packages.core.errors import AuthenticationError

__all__ = ["CognitoVerifier", "TokenClaims"]

KeyResolver = Callable[[str], Any]


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    role: Role
    groups: tuple[str, ...]


class CognitoVerifier:
    def __init__(
        self, issuer: str, client_id: str, key_resolver: KeyResolver | None = None
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._resolver = key_resolver or self._default_resolver()

    def _default_resolver(self) -> KeyResolver:
        client = jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True)
        return lambda token: client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> TokenClaims:
        try:
            key = self._resolver(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
        except (jwt.PyJWTError, OSError) as exc:
            raise AuthenticationError("invalid or expired token") from exc
        use = claims.get("token_use")
        audience = claims.get("aud") if use == "id" else claims.get("client_id")
        if use not in ("id", "access") or audience != self._client_id:
            raise AuthenticationError("token was not issued for this application")
        groups = tuple(claims.get("cognito:groups", []))
        role = (
            Role.ADMIN
            if "admin" in groups
            else Role.PLANNER
            if "planner" in groups
            else Role.VIEWER
        )
        return TokenClaims(str(claims["sub"]), role, groups)
