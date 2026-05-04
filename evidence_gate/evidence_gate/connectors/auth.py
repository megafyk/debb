from __future__ import annotations

from base64 import b64encode

import httpx

from evidence_gate.app.config import Settings


def jira_basic_auth_header(settings: Settings) -> dict[str, str]:
    """Build Basic Auth header for Jira REST API from Settings.

    Never accepts agent input — only reads from evidence_gate config.
    """
    credentials = f"{settings.jira_username}:{settings.jira_password}"
    encoded = b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
    }


def quickwit_basic_auth_header(settings: Settings) -> dict[str, str]:
    """Build Basic Auth header for Quickwit search API from Settings.

    Never accepts agent input — only reads from evidence_gate config.
    """
    credentials = f"{settings.quickwit_username}:{settings.quickwit_password}"
    encoded = b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def metabase_session_header(settings: Settings) -> dict[str, str]:
    """Authenticate with Metabase and return session header.

    POST /api/session with username/password, get session token.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.metabase_url}/api/session",
            json={"username": settings.metabase_username, "password": settings.metabase_password},
        )
        resp.raise_for_status()
        session_id = resp.json()["id"]
    return {"X-Metabase-Session": session_id, "Content-Type": "application/json"}


def metabase_fixture_session_header() -> dict[str, str]:
    return {"X-Metabase-Session": "fixture-session-token", "Content-Type": "application/json"}
