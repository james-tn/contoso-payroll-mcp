"""Bearer-token validators for the protected MCP endpoint.

The Entra validator uses PyJWT and Microsoft's tenant-specific JWKS. The generic
OAuth validator calls a configured HTTPS userinfo endpoint for opaque tokens.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError


class AuthError(Exception):
    """Raised when a bearer token fails validation."""


_MULTITENANT = {"common", "organizations", "*"}


def _tenant_guid(value: Any) -> str:
    tenant = str(value or "").strip()
    try:
        return str(UUID(tenant))
    except ValueError as exc:
        raise AuthError("invalid tenant claim") from exc


@lru_cache(maxsize=64)
def _jwks_client(tenant_id: str) -> PyJWKClient:
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        cache_keys=True,
        lifespan=3600,
    )


def make_validator(
    tenant_id: str,
    audiences: list[str],
    required_scope: str = "",
    *,
    leeway: int = 120,
    allowed_tenants: list[str] | None = None,
    jwks_client_factory: Callable[[str], PyJWKClient] | None = None,
) -> Callable[[str], dict[str, Any]]:
    """Validate Entra access tokens for one tenant or a tenant allowlist."""
    configured_tenant = tenant_id.strip().lower()
    if not configured_tenant:
        raise ValueError("entra_tenant_id is required")
    if not audiences:
        raise ValueError("at least one Entra audience is required")

    multitenant = configured_tenant in _MULTITENANT
    single_tenant = "" if multitenant else _tenant_guid(configured_tenant)
    allow_set = {_tenant_guid(value) for value in (allowed_tenants or [])}
    client_factory = jwks_client_factory or _jwks_client

    def validate(token: str) -> dict[str, Any]:
        try:
            unverified = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
                algorithms=["RS256"],
            )
            token_tenant = _tenant_guid(unverified.get("tid"))
            if multitenant:
                if allow_set and token_tenant not in allow_set:
                    raise AuthError("tenant not allowed")
                key_tenant = token_tenant
            else:
                if token_tenant != single_tenant:
                    raise AuthError("wrong tenant")
                key_tenant = single_tenant

            signing_key = client_factory(key_tenant).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=audiences,
                leeway=leeway,
                options={
                    "require": ["exp", "iss", "tid"],
                    "verify_iss": False,
                },
            )
        except AuthError:
            raise
        except PyJWTError as exc:
            raise AuthError("token validation failed") from exc

        valid_issuers = {
            f"https://login.microsoftonline.com/{token_tenant}/v2.0",
            f"https://sts.windows.net/{token_tenant}/",
        }
        if claims.get("iss") not in valid_issuers:
            raise AuthError("invalid issuer")
        if required_scope and required_scope not in str(claims.get("scp", "")).split():
            raise AuthError("missing required scope")
        return claims

    return validate


_userinfo_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_USERINFO_TTL = 60.0


def _require_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        return
    raise ValueError("userinfo URL must use HTTPS")


def make_userinfo_validator(
    userinfo_url: str,
    *,
    subject_field: str,
    allowed_subjects: list[str] | None = None,
    cache_ttl: float = _USERINFO_TTL,
    fetch: Callable[[str, str], tuple[int, dict[str, Any]]] | None = None,
) -> Callable[[str], dict[str, Any]]:
    """Validate opaque OAuth tokens through an HTTPS userinfo endpoint."""
    _require_https(userinfo_url)
    if not subject_field.strip():
        raise ValueError("oauth_subject_field is required for generic OAuth")

    allow_set = {subject.strip() for subject in (allowed_subjects or []) if subject.strip()}
    do_fetch = fetch or _http_get_json

    def validate(token: str) -> dict[str, Any]:
        token = (token or "").strip()
        if not token:
            raise AuthError("missing token")

        now = time.time()
        cached = _userinfo_cache.get(token)
        if cached and now - cached[0] < cache_ttl:
            claims = cached[1]
        else:
            try:
                status, claims = do_fetch(userinfo_url, token)
            except Exception as exc:
                raise AuthError("userinfo call failed") from exc
            if status in (401, 403):
                raise AuthError("invalid or expired token")
            if status != 200 or not isinstance(claims, dict):
                raise AuthError("userinfo validation failed")
            if len(_userinfo_cache) >= 2048:
                _userinfo_cache.clear()
            _userinfo_cache[token] = (now, claims)

        subject = str(claims.get(subject_field) or "").strip()
        if not subject:
            raise AuthError("userinfo response has no stable subject")
        if allow_set and subject not in allow_set:
            raise AuthError("subject not allowed")
        return claims

    return validate


def _http_get_json(url: str, token: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "contoso-payroll-mcp",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {}
