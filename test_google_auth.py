"""Unit tests for production Google env credentials (no live Google API)."""

from unittest.mock import MagicMock, patch

import pytest

import services.tasks.google_auth as google_auth


def test_env_refresh_token_only_refreshes_when_expiry_unset():
    """Railway sets GOOGLE_REFRESH_TOKEN with token=None and expiry=None.

    google.oauth2.Credentials.expired is False when expiry is missing, so
    requiring expired=True skipped refresh and raised invalid credentials.
    """
    env_creds = MagicMock()
    env_creds.valid = False
    env_creds.expired = False
    env_creds.refresh_token = "1//refresh-token"
    refreshed = MagicMock()

    with (
        patch.object(google_auth, "_credentials_from_env", return_value=env_creds),
        patch.object(google_auth, "_refresh_credentials", return_value=refreshed) as refresh,
    ):
        assert google_auth.get_credentials() is refreshed
        refresh.assert_called_once_with(env_creds)


def test_local_invalid_grant_runs_desktop_flow(tmp_path, monkeypatch):
    from google.auth.exceptions import RefreshError

    monkeypatch.setattr(google_auth.config, "IS_PRODUCTION", False)
    monkeypatch.setattr(google_auth.config, "TOKEN_FILE", tmp_path / "token.json")
    file_creds = MagicMock()
    file_creds.valid = False
    file_creds.refresh_token = "1//stale"
    fresh = MagicMock()
    fresh.to_json.return_value = '{"refresh_token":"1//new"}'

    with (
        patch.object(google_auth, "_credentials_from_env", return_value=None),
        patch.object(google_auth, "_needs_reconsent", return_value=False),
        patch.object(
            google_auth.Credentials, "from_authorized_user_file", return_value=file_creds
        ),
        patch.object(
            google_auth,
            "_refresh_credentials",
            side_effect=RefreshError("invalid_grant", {"error": "invalid_grant"}),
        ),
        patch.object(google_auth, "_run_local_auth_flow", return_value=fresh) as flow,
    ):
        (tmp_path / "token.json").write_text("{}")
        assert google_auth.get_credentials() is fresh
        flow.assert_called_once()
        assert (tmp_path / "token.json").read_text() == '{"refresh_token":"1//new"}'


def test_production_invalid_grant_raises_reseed(monkeypatch):
    from google.auth.exceptions import RefreshError

    monkeypatch.setattr(google_auth.config, "IS_PRODUCTION", True)
    env_creds = MagicMock()
    env_creds.valid = False
    env_creds.refresh_token = "1//stale"

    with (
        patch.object(google_auth, "_credentials_from_env", return_value=env_creds),
        patch.object(
            google_auth,
            "_refresh_credentials",
            side_effect=RefreshError("invalid_grant", {"error": "invalid_grant"}),
        ),
        patch.object(google_auth, "_run_local_auth_flow") as flow,
    ):
        with pytest.raises(RuntimeError, match="Re-seed GOOGLE_"):
            google_auth.get_credentials()
        flow.assert_not_called()
    env_creds = MagicMock()
    env_creds.valid = False
    env_creds.expired = False
    env_creds.refresh_token = None

    with patch.object(google_auth, "_credentials_from_env", return_value=env_creds):
        with pytest.raises(RuntimeError, match="GOOGLE_\\* environment credentials are invalid"):
            google_auth.get_credentials()


def test_refresh_error_maps_to_reseed_message():
    from google.auth.exceptions import RefreshError

    from bridge.transport.http_security import production_safe_tool_error

    with pytest.raises(ValueError, match="GOOGLE_REFRESH_TOKEN"):
        production_safe_tool_error(
            RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant"})
        )


def test_generic_production_error_stays_opaque(monkeypatch):
    import bridge.config as config
    from bridge.transport.http_security import production_safe_tool_error

    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    result = production_safe_tool_error(RuntimeError("secret stack"))
    assert str(result) == "Request failed."
