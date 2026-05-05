import tempfile
from pathlib import Path

import httpx
import respx

from evidence_gate.config import Settings
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


_FAKE_JIRA_RESPONSE = {
    "key": "PROJ-42",
    "fields": {
        "summary": "API returns 500 for certain users",
        "issuetype": {"name": "Bug"},
        "priority": {"name": "Critical"},
        "status": {"name": "In Progress"},
        "labels": ["api", "production"],
        "components": [{"name": "api-gateway"}],
        "description": "User john.doe@acme.com reports 500 errors. Phone: +1-555-123-4567. Account ID: ACC-99887766.",
        "comment": {
            "comments": [
                {"body": "Reproduced with test account admin@internal.co"},
            ]
        },
        "created": "2026-05-01T10:00:00.000+0000",
        "updated": "2026-05-01T12:00:00.000+0000",
        "issuelinks": [],
        "subtasks": [],
        # Blocked fields — must not appear in output
        "worklog": {"worklogs": [{"timeSpent": "4h"}]},
        "votes": {"votes": 3},
    },
}


@respx.mock
def test_real_connector_calls_jira_rest():
    settings = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="bot@test.com",
        jira_password="secret-token",
    )

    route = respx.get("https://test.atlassian.net/rest/api/2/issue/PROJ-42").mock(
        return_value=httpx.Response(200, json=_FAKE_JIRA_RESPONSE)
    )

    jc = JiraConnector(settings)
    assert jc.is_live

    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        ticket, refs = jc.fetch_and_sanitize("PROJ-42", "ESESS-test", store)

    assert route.called
    assert ticket.ticket_id == "PROJ-42"
    assert ticket.summary == "API returns 500 for certain users"
    assert ticket.issue_type == "Bug"

    # PII must be extracted/redacted
    assert "john.doe@acme.com" not in ticket.description_sanitized
    assert "+1-555-123-4567" not in ticket.description_sanitized
    assert "admin@internal.co" not in ticket.comments_sanitized[0]

    # Sensitive refs should be generated
    assert len(refs) > 0
    email_refs = [r for r in refs if r.field_type == "email"]
    assert len(email_refs) >= 1


@respx.mock
def test_real_connector_sends_auth_header():
    settings = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="bot@test.com",
        jira_password="secret-token",
    )

    route = respx.get("https://test.atlassian.net/rest/api/2/issue/PROJ-1").mock(
        return_value=httpx.Response(200, json=_FAKE_JIRA_RESPONSE)
    )

    jc = JiraConnector(settings)
    jc.fetch_raw("PROJ-1")

    assert route.called
    request = route.calls[0].request
    assert "Authorization" in request.headers
    assert request.headers["Authorization"].startswith("Basic ")


def test_fixture_fallback_when_no_url():
    settings = Settings(jira_base_url="")
    jc = JiraConnector(settings)
    assert not jc.is_live

    ticket, refs = jc.fetch_and_sanitize("BUG-123")
    assert ticket.ticket_id == "BUG-123"
    assert ticket.summary == "Login fails for users with phone numbers missing leading zero"


def test_no_connector_settings_uses_fixture():
    jc = JiraConnector()
    assert not jc.is_live
    ticket, _ = jc.fetch_and_sanitize("ANY-1")
    assert ticket.ticket_id == "ANY-1"
