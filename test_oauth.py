"""Unit tests for WorkOS MCP OAuth token verification."""

from __future__ import annotations

import asyncio
import time

from bridge.auth.oauth import (
    DISCOVERY_SCOPES,
    WorkOSTokenVerifier,
    audience_values,
    claim_keys,
    email_from_claims,
    protected_resource_payload,
)

ISSUER = "https://fine-ash-09-staging.authkit.app"
RESOURCE = "https://tasksaibridge-production.up.railway.app/mcp"
ALLOWED = "owner@example.com"


def _verifier() -> WorkOSTokenVerifier:
    return WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
    )


def test_email_from_claims_variants():
    assert email_from_claims({"email": "A@Example.COM"}) == "a@example.com"
    assert email_from_claims({"emails": ["b@example.com"]}) == "b@example.com"
    assert email_from_claims({"emails": [{"email": "c@example.com"}]}) == "c@example.com"
    assert email_from_claims({"preferred_username": "d@example.com"}) == "d@example.com"
    assert email_from_claims({"preferred_username": "user_01ABC"}) is None
    assert email_from_claims({"act": {"sub": "e@example.com"}}) == "e@example.com"
    assert email_from_claims({"https://authkit.app/email": "f@example.com"}) == (
        "f@example.com"
    )
    assert email_from_claims({}) is None
    assert claim_keys({"sub": "user_1", "org_id": "org_1"}) == ["org_id", "sub"]


def test_protected_resource_payload_matches_authkit_issuer():
    payload = protected_resource_payload(RESOURCE, ISSUER)
    assert payload["resource"] == RESOURCE
    assert payload["authorization_servers"] == [ISSUER]
    assert payload["bearer_methods_supported"] == ["header"]
    assert payload["scopes_supported"] == list(DISCOVERY_SCOPES)
    assert ISSUER.endswith("authkit.app")
    assert not ISSUER.endswith("/")


def test_audience_values_string_and_list():
    assert audience_values(RESOURCE) == [RESOURCE]
    assert audience_values([RESOURCE, "other"]) == [RESOURCE, "other"]
    assert audience_values(None) == []


def test_verify_token_accepts_allowed_email_and_audience(monkeypatch):
    verifier = _verifier()
    exp = int(time.time()) + 3600
    monkeypatch.setattr(
        verifier,
        "_claims_for_token",
        lambda _token: {
            "iss": ISSUER,
            "aud": RESOURCE,
            "sub": "user_1",
            "email": "Owner@example.com",
            "exp": exp,
            "scope": "openid email",
            "azp": "chatgpt",
        },
    )
    access = asyncio.run(verifier.verify_token("fake-token"))
    assert access is not None
    assert access.subject == "user_1"
    assert access.client_id == "chatgpt"
    assert "openid" in access.scopes


def test_verify_token_rejects_unknown_email(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(
        verifier,
        "_claims_for_token",
        lambda _token: {
            "iss": ISSUER,
            "aud": RESOURCE,
            "sub": "user_2",
            "email": "stranger@example.com",
            "exp": int(time.time()) + 3600,
        },
    )
    assert asyncio.run(verifier.verify_token("fake-token")) is None


def test_verify_token_rejects_wrong_audience(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(
        verifier,
        "_claims_for_token",
        lambda _token: {
            "iss": ISSUER,
            "aud": "https://other.example/mcp",
            "sub": "user_1",
            "email": ALLOWED,
            "exp": int(time.time()) + 3600,
        },
    )
    assert asyncio.run(verifier.verify_token("fake-token")) is None


def _workos_connect_claims(**extra):
    payload = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "user_01JQ0E27VT3MH79RY0FVA4QBP9",
        "org_id": "org_01HRDMC6CM357W30QMHMQ96Q0S",
        "sid": "app_consent_01JQ0E27WE4K1RCMH7Q094M1GJ",
        "jti": "01JQ0E27ZXE4XNHVP870S6PWYN",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    payload.update(extra)
    return payload


def test_verify_token_resolves_email_from_userinfo(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(issuer: str, token: str):
        assert issuer == ISSUER
        assert token == "fake-token"
        return {
            "sub": "user_01JQ0E27VT3MH79RY0FVA4QBP9",
            "email": "Owner@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(
        "bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo
    )
    access = asyncio.run(verifier.verify_token("fake-token"))
    assert access is not None
    assert access.claims["email"] == ALLOWED
    assert access.subject == "user_01JQ0E27VT3MH79RY0FVA4QBP9"


def test_verify_token_userinfo_unknown_email_rejected(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return {"sub": "user_01JQ0E27VT3MH79RY0FVA4QBP9", "email": "stranger@example.com"}

    monkeypatch.setattr(
        "bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo
    )
    assert asyncio.run(verifier.verify_token("fake-token")) is None


def test_verify_token_userinfo_missing_email_rejected(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return {"sub": "user_01JQ0E27VT3MH79RY0FVA4QBP9", "name": "No Email"}

    monkeypatch.setattr(
        "bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo
    )
    assert asyncio.run(verifier.verify_token("fake-token")) is None


def test_verify_token_userinfo_cached_by_subject(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())
    calls = {"n": 0}

    async def fake_userinfo(_issuer: str, _token: str):
        calls["n"] += 1
        return {"email": ALLOWED}

    monkeypatch.setattr(
        "bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo
    )
    assert asyncio.run(verifier.verify_token("token-a")) is not None
    assert asyncio.run(verifier.verify_token("token-b")) is not None
    assert calls["n"] == 1


def test_verify_token_skips_userinfo_when_email_in_jwt(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(
        verifier,
        "_claims_for_token",
        lambda _token: _workos_connect_claims(email=ALLOWED),
    )

    async def boom(_issuer: str, _token: str):
        raise AssertionError("userinfo should not run when email is on the JWT")

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", boom)
    access = asyncio.run(verifier.verify_token("fake-token"))
    assert access is not None
    assert access.claims["email"] == ALLOWED
