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
    fetch_authkit_userinfo,
    fetch_workos_user_by_id,
    is_workos_user_id,
    protected_resource_payload,
    scope_claim_text,
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
    assert scope_claim_text({"scope": "openid email"}) == "openid email"
    assert scope_claim_text({"scp": ["openid", "email"]}) == "openid email"
    assert scope_claim_text({}) == ""
    assert is_workos_user_id("user_01JQ0E27VT3MH79RY0FVA4QBP9")
    assert not is_workos_user_id("user_01/../escape")
    assert not is_workos_user_id("client_01ABC")


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


class _FakeHTTPResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def request(self, method, url, headers=None):
        return self._handler("request", method, url, headers)

    async def get(self, url, headers=None):
        return self._handler("get", "GET", url, headers)


def _patch_httpx(monkeypatch, handler):
    monkeypatch.setattr(
        "bridge.auth.oauth.httpx.AsyncClient",
        lambda **_kwargs: _FakeAsyncClient(handler),
    )


def test_userinfo_uses_get_then_post_with_bearer(monkeypatch):
    calls = []

    def handler(kind, method, url, headers):
        calls.append((kind, method, url, headers.get("Authorization")))
        if method == "GET":
            return _FakeHTTPResponse(401)
        return _FakeHTTPResponse(200, {"email": "owner@example.com"})

    _patch_httpx(monkeypatch, handler)
    payload = asyncio.run(fetch_authkit_userinfo(ISSUER, "access-token"))
    assert payload == {"email": "owner@example.com"}
    assert [item[1] for item in calls] == ["GET", "POST"]
    assert all(item[3] == "Bearer access-token" for item in calls)
    assert all(item[2].endswith("/oauth2/userinfo") for item in calls)


def test_userinfo_get_success_skips_post(monkeypatch):
    calls = []

    def handler(_kind, method, url, headers):
        calls.append(method)
        return _FakeHTTPResponse(200, {"email": "owner@example.com"})

    _patch_httpx(monkeypatch, handler)
    payload = asyncio.run(fetch_authkit_userinfo(ISSUER, "access-token"))
    assert payload["email"] == "owner@example.com"
    assert calls == ["GET"]


def test_userinfo_both_401_returns_none(monkeypatch):
    def handler(_kind, _method, _url, _headers):
        return _FakeHTTPResponse(401, {"error": "invalid_token"})

    _patch_httpx(monkeypatch, handler)
    assert asyncio.run(fetch_authkit_userinfo(ISSUER, "access-token")) is None


def test_workos_users_api_returns_email(monkeypatch):
    def handler(kind, method, url, headers):
        assert kind == "get"
        assert method == "GET"
        assert url.endswith("/user_management/users/user_01JQ0E27VT3MH79RY0FVA4QBP9")
        assert headers["Authorization"] == "Bearer sk_test"
        return _FakeHTTPResponse(
            200,
            {
                "object": "user",
                "id": "user_01JQ0E27VT3MH79RY0FVA4QBP9",
                "email": "Owner@example.com",
            },
        )

    _patch_httpx(monkeypatch, handler)
    profile = asyncio.run(
        fetch_workos_user_by_id("user_01JQ0E27VT3MH79RY0FVA4QBP9", "sk_test")
    )
    assert profile["email"] == "Owner@example.com"


def test_workos_users_api_skips_unsafe_id(monkeypatch):
    def handler(*_args):
        raise AssertionError("Users API must not run for unsafe ids")

    _patch_httpx(monkeypatch, handler)
    assert asyncio.run(fetch_workos_user_by_id("user_01/../x", "sk_test")) is None
    assert asyncio.run(fetch_workos_user_by_id("user_01ABC", "")) is None


def test_verify_token_resolves_email_from_workos_users_api(monkeypatch):
    verifier = WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
        workos_api_key="sk_test",
    )
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return None

    async def fake_user(user_id: str, api_key: str):
        assert user_id == "user_01JQ0E27VT3MH79RY0FVA4QBP9"
        assert api_key == "sk_test"
        return {"id": user_id, "email": "Owner@example.com"}

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo)
    monkeypatch.setattr("bridge.auth.oauth.fetch_workos_user_by_id", fake_user)
    access = asyncio.run(verifier.verify_token("fake-token"))
    assert access is not None
    assert access.claims["email"] == ALLOWED


def test_verify_token_users_api_cached_by_subject(monkeypatch):
    verifier = WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
        workos_api_key="sk_test",
    )
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())
    calls = {"n": 0}

    async def fake_userinfo(_issuer: str, _token: str):
        return None

    async def fake_user(_user_id: str, _api_key: str):
        calls["n"] += 1
        return {"email": ALLOWED}

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo)
    monkeypatch.setattr("bridge.auth.oauth.fetch_workos_user_by_id", fake_user)
    assert asyncio.run(verifier.verify_token("token-a")) is not None
    assert asyncio.run(verifier.verify_token("token-b")) is not None
    assert calls["n"] == 1


def test_verify_token_users_api_unknown_email_rejected(monkeypatch):
    verifier = WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
        workos_api_key="sk_test",
    )
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return None

    async def fake_user(_user_id: str, _api_key: str):
        return {"email": "stranger@example.com"}

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo)
    monkeypatch.setattr("bridge.auth.oauth.fetch_workos_user_by_id", fake_user)
    assert asyncio.run(verifier.verify_token("fake-token")) is None


def test_verify_token_accepts_allowed_sub_when_email_missing(monkeypatch):
    subject = "user_01JQ0E27VT3MH79RY0FVA4QBP9"
    verifier = WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
        allowed_subs=frozenset({subject}),
    )
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return None

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo)
    access = asyncio.run(verifier.verify_token("fake-token"))
    assert access is not None
    assert access.subject == subject


def test_verify_token_unknown_sub_rejected_without_email(monkeypatch):
    verifier = WorkOSTokenVerifier(
        issuer=ISSUER,
        audiences=frozenset({RESOURCE}),
        allowed_emails=frozenset({ALLOWED}),
        allowed_subs=frozenset({"user_OTHER"}),
    )
    monkeypatch.setattr(verifier, "_claims_for_token", lambda _token: _workos_connect_claims())

    async def fake_userinfo(_issuer: str, _token: str):
        return None

    monkeypatch.setattr("bridge.auth.oauth.fetch_authkit_userinfo", fake_userinfo)
    assert asyncio.run(verifier.verify_token("fake-token")) is None
