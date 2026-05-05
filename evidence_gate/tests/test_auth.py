from base64 import b64decode

from evidence_gate.config import Settings
from evidence_gate.connectors.auth import jira_basic_auth_header


def test_builds_basic_auth_header():
    s = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="user@test.com",
        jira_password="api-token-123",
    )
    headers = jira_basic_auth_header(s)

    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    decoded = b64decode(headers["Authorization"].split(" ", 1)[1]).decode()
    assert decoded == "user@test.com:api-token-123"
    assert headers["Accept"] == "application/json"
