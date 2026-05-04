from __future__ import annotations

from base64 import b64encode

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
