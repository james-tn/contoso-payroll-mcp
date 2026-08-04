"""Request-local authenticated principal used to isolate demo run state."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from .auth import AuthError

_principal: ContextVar[str] = ContextVar("payroll_mcp_principal", default="anonymous")


def principal_from_claims(claims: dict[str, Any]) -> str:
    """Return a stable, tenant-qualified key without exposing it to callers."""
    tenant = str(claims.get("tid") or claims.get("tenant") or "external")
    for field in ("oid", "sub", "id", "login", "userPrincipalName", "email"):
        value = str(claims.get(field) or "").strip()
        if value:
            return f"{tenant}:{field}:{value}"
    raise AuthError("validated token has no stable subject")


def set_current_principal(principal: str) -> Token[str]:
    return _principal.set(principal)


def reset_current_principal(token: Token[str]) -> None:
    _principal.reset(token)


def current_principal() -> str:
    return _principal.get()
