from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from payroll_mcp import security_context, tools
from payroll_mcp.auth import AuthError, make_userinfo_validator, make_validator


class _SigningClient:
    def __init__(self, public_key) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token: str):
        return type("SigningKey", (), {"key": self.public_key})()


class EntraValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.tenant = str(uuid4())
        self.audience = str(uuid4())
        now = datetime.now(timezone.utc)
        claims = {
            "tid": self.tenant,
            "iss": f"https://login.microsoftonline.com/{self.tenant}/v2.0",
            "aud": self.audience,
            "scp": "access_as_user",
            "sub": "test-user",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
        }
        self.token = jwt.encode(
            claims,
            self.key,
            algorithm="RS256",
            headers={"kid": "test"},
        )

    def validator(self, audience: str):
        client = _SigningClient(self.key.public_key())
        return make_validator(
            self.tenant,
            [audience],
            "access_as_user",
            jwks_client_factory=lambda _tenant: client,
        )

    def test_accepts_expected_audience(self) -> None:
        claims = self.validator(self.audience)(self.token)
        self.assertEqual(claims["sub"], "test-user")

    def test_rejects_wrong_audience(self) -> None:
        with self.assertRaises(AuthError):
            self.validator("wrong-audience")(self.token)

    def test_generic_oauth_requires_https(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            make_userinfo_validator(
                "http://identity.example.com/userinfo",
                subject_field="sub",
            )


class PrincipalIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_state_isolated_by_principal(self) -> None:
        principal_a = f"tenant-a:{uuid4()}"
        token_a = security_context.set_current_principal(principal_a)
        try:
            await tools.process_payroll()
            result = await tools.get_run_summary()
            self.assertTrue(result.structuredContent["hasRun"])
        finally:
            security_context.reset_current_principal(token_a)

        principal_b = f"tenant-b:{uuid4()}"
        token_b = security_context.set_current_principal(principal_b)
        try:
            result = await tools.get_run_summary()
            self.assertFalse(result.structuredContent["hasRun"])
        finally:
            security_context.reset_current_principal(token_b)


if __name__ == "__main__":
    unittest.main()
