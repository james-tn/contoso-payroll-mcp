"""Runtime configuration, loaded from environment variables (prefix ``PAYROLL_MCP_``).

Example::

    PAYROLL_MCP_PORT=3978
    PAYROLL_MCP_REQUIRE_AUTH=true
    PAYROLL_MCP_AUTH_MODE=entra
    PAYROLL_MCP_ENTRA_TENANT_ID=organizations
    PAYROLL_MCP_ENTRA_AUDIENCES=<client-id>,api://<client-id>
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PAYROLL_MCP_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 3978
    cors_origins: str = ""

    # MCP transport protection. Add the public service FQDN in production.
    transport_security_enabled: bool = True
    allowed_hosts: str = "localhost,localhost:*,127.0.0.1,127.0.0.1:*"
    allowed_origins: str = ""

    # ── Bearer-token auth (OFF by default so the local demo runs anonymously) ──
    require_auth: bool = False
    # "entra"   — Microsoft Entra ID access token, validated as a signed JWT.
    # "generic" — an OAuth 2 provider returning an opaque token, validated by
    #             calling the provider's HTTPS userinfo endpoint.
    auth_mode: Literal["entra", "generic"] = "entra"

    entra_tenant_id: str = ""
    entra_audiences: str = ""
    entra_required_scope: str = ""
    entra_allowed_tenants: str = ""

    oauth_userinfo_url: str = ""
    oauth_subject_field: str = ""
    oauth_allowed_subjects: str = ""

    # Never log payroll payloads unless explicitly debugging with synthetic data.
    debug_tool_payloads: bool = False

    # Demo follow-up state is isolated by authenticated principal and bounded.
    run_state_ttl_seconds: int = 3600
    max_run_states: int = 256

    @staticmethod
    def _csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    def audiences_list(self) -> list[str]:
        return self._csv(self.entra_audiences)

    def allowed_tenants_list(self) -> list[str]:
        return self._csv(self.entra_allowed_tenants)

    def allowed_subjects_list(self) -> list[str]:
        return self._csv(self.oauth_allowed_subjects)

    def cors_origins_list(self) -> list[str]:
        return self._csv(self.cors_origins)

    def allowed_hosts_list(self) -> list[str]:
        return self._csv(self.allowed_hosts)

    def allowed_origins_list(self) -> list[str]:
        return self._csv(self.allowed_origins)


def get_settings() -> Settings:
    return Settings()
