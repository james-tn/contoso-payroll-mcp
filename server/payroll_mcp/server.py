"""MCP server bootstrap for the Contoso Payroll demo.

A Streamable-HTTP MCP server exposing payroll-processing tools, optionally gated by
a bearer token. No inline widget in this version — tool results are structured
data + text that Copilot renders (e.g. the payroll register as a table).

Run locally::

    python -m payroll_mcp          # http://localhost:3978/mcp
"""

from __future__ import annotations

import json

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from . import auth, security_context
from .settings import get_settings
from .tools import PROMPT_SPECS, TOOL_SPECS

settings = get_settings()

mcp = FastMCP(
    "contoso-payroll",
    host=settings.host,
    port=settings.port,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.transport_security_enabled,
        allowed_hosts=settings.allowed_hosts_list(),
        allowed_origins=settings.allowed_origins_list(),
    ),
)

for _spec in TOOL_SPECS:
    mcp.tool(name=_spec["name"], description=_spec["description"])(_spec["handler"])

for _spec in PROMPT_SPECS:
    mcp.prompt(name=_spec["name"], description=_spec["description"])(_spec["handler"])


# ── Bearer-token auth (pure ASGI, streaming-safe) ────────────────────────────

class BearerAuthMiddleware:
    """Require a valid bearer token on protected path prefixes (default /mcp).

    Pure ASGI passthrough so it never buffers MCP streaming responses. Health stays
    public; OPTIONS preflight is always allowed.
    """

    def __init__(self, app, validate, protect_prefixes=("/mcp",)) -> None:
        self.app = app
        self.validate = validate
        self.prefixes = protect_prefixes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if method == "OPTIONS" or not any(path.startswith(p) for p in self.prefixes):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"authorization", b"").decode("latin-1")
        token = raw[7:].strip() if raw[:7].lower() == "bearer " else ""

        detail = "missing bearer token"
        if token:
            try:
                claims = await anyio.to_thread.run_sync(self.validate, token)
                principal = security_context.principal_from_claims(claims)
                context_token = security_context.set_current_principal(principal)
                try:
                    return await self.app(scope, receive, send)
                finally:
                    security_context.reset_current_principal(context_token)
            except Exception as exc:  # noqa: BLE001 - any failure -> 401
                detail = str(exc)

        body = json.dumps({"error": "unauthorized", "detail": "invalid bearer token"}).encode()
        print(f"[auth-fail] path={path} token_present={bool(token)} detail={detail!r}", flush=True)
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer error="invalid_token"'),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def build_app():
    app = mcp.streamable_http_app()
    origins = settings.cors_origins_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "mcp-session-id", "mcp-protocol-version"],
            expose_headers=["mcp-session-id"],
        )

    async def healthz(_req: Request) -> Response:
        return PlainTextResponse("ok")

    app.add_route("/healthz", healthz, methods=["GET"])

    if settings.require_auth:
        if settings.auth_mode == "generic":
            validate = auth.make_userinfo_validator(
                settings.oauth_userinfo_url,
                subject_field=settings.oauth_subject_field,
                allowed_subjects=settings.allowed_subjects_list(),
            )
        else:
            validate = auth.make_validator(
                settings.entra_tenant_id,
                settings.audiences_list(),
                settings.entra_required_scope,
                allowed_tenants=settings.allowed_tenants_list(),
            )
        return BearerAuthMiddleware(app, validate)
    return app


app = build_app()


def main() -> None:
    print(
        f"\n  Contoso Payroll MCP server\n"
        f"  Transport : Streamable HTTP\n"
        f"  Endpoint  : http://{settings.host}:{settings.port}/mcp\n"
        f"  Auth      : {'ON (' + settings.auth_mode + ')' if settings.require_auth else 'OFF'}\n"
        f"  Tools     : {', '.join(s['name'] for s in TOOL_SPECS)}\n"
    )
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
