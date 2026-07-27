"""Google Tasks OAuth helpers.

Local development:
    Place ``credentials.json`` (Desktop OAuth client) and ``token.json`` in the
    project root. The desktop browser flow runs on first use.

Production (Railway, headless):
    Set ``GOOGLE_CLIENT_ID``, ``GOOGLE_CLIENT_SECRET``, and
    ``GOOGLE_REFRESH_TOKEN`` as environment variables. Obtain the refresh token
    once locally (see docs/railway.md), then store it as a platform secret.

    Alternatively set ``GOOGLE_TOKEN_JSON`` to the full authorized-user JSON.
"""

from __future__ import annotations

import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

SCOPES = ["https://www.googleapis.com/auth/tasks"]


def _stored_token_scopes_from_file() -> set[str]:
    if not config.TOKEN_FILE.exists():
        return set()
    data = json.loads(config.TOKEN_FILE.read_text())
    return set(data.get("scopes", []))


def _needs_reconsent() -> bool:
    stored = _stored_token_scopes_from_file()
    if not stored:
        return True
    return not set(SCOPES).issubset(stored)


def _credentials_from_env() -> Credentials | None:
    if config.GOOGLE_TOKEN_JSON:
        creds = Credentials.from_authorized_user_info(
            json.loads(config.GOOGLE_TOKEN_JSON),
            SCOPES,
        )
        return creds

    if not (
        config.GOOGLE_CLIENT_ID
        and config.GOOGLE_CLIENT_SECRET
        and config.GOOGLE_REFRESH_TOKEN
    ):
        return None

    return Credentials(
        token=None,
        refresh_token=config.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )


def _run_local_auth_flow() -> Credentials:
    if not config.CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {config.CREDENTIALS_FILE.name}. Download OAuth client "
            "credentials from Google Cloud Console (Desktop app) and save them "
            f"as {config.CREDENTIALS_FILE}. See docs/local-dev.md."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.CREDENTIALS_FILE),
        SCOPES,
    )
    return flow.run_local_server(port=0)


def _refresh_credentials(creds: Credentials) -> Credentials:
    creds.refresh(Request())
    if not creds.valid or not creds.has_scopes(SCOPES):
        raise RuntimeError("Google OAuth refresh failed or scopes are insufficient.")
    return creds


def get_credentials() -> Credentials:
    """Return valid Google credentials, refreshing or prompting as needed."""
    env_creds = _credentials_from_env()
    if env_creds is not None:
        if env_creds.valid:
            return env_creds
        if env_creds.expired and env_creds.refresh_token:
            return _refresh_credentials(env_creds)
        raise RuntimeError(
            "GOOGLE_* environment credentials are invalid. "
            "Re-seed GOOGLE_REFRESH_TOKEN or GOOGLE_TOKEN_JSON."
        )

    if config.IS_PRODUCTION:
        raise RuntimeError(
            "Production requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and "
            "GOOGLE_REFRESH_TOKEN (or GOOGLE_TOKEN_JSON). "
            "Local credentials.json / token.json are not used in production."
        )

    creds: Credentials | None = None
    if config.TOKEN_FILE.exists() and not _needs_reconsent():
        creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds = _refresh_credentials(creds)
        if not config.IS_PRODUCTION:
            config.TOKEN_FILE.write_text(creds.to_json())
        return creds

    creds = _run_local_auth_flow()
    config.TOKEN_FILE.write_text(creds.to_json())
    return creds
