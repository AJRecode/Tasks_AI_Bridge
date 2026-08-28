"""Unit tests for WorkOS MCP OAuth token verification."""

from __future__ import annotations

import asyncio
import time

from bridge.auth.oauth import (
    DISCOVERY_SCOPES,
    WorkOSTokenVerifier,
    audience_values,
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
    assert email_from_claims({}) is None


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
