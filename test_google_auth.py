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


def test_env_creds_without_refresh_token_raise():
    env_creds = MagicMock()
    env_creds.valid = False
    env_creds.expired = False
    env_creds.refresh_token = None

    with patch.object(google_auth, "_credentials_from_env", return_value=env_creds):
        with pytest.raises(RuntimeError, match="GOOGLE_\\* environment credentials are invalid"):
            google_auth.get_credentials()
