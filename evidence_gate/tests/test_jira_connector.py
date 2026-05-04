from evidence_gate.connectors.jira_connector import JiraConnector


def test_fetch_and_sanitize_returns_context():
    jc = JiraConnector()
    ticket, refs = jc.fetch_and_sanitize("BUG-123")

    assert ticket.ticket_id == "BUG-123"
    assert ticket.summary == "Login fails for users with phone numbers missing leading zero"
    assert ticket.issue_type == "Bug"
    assert ticket.priority == "High"
    assert "login-service" in ticket.components


def test_description_is_redacted():
    jc = JiraConnector()
    ticket, _ = jc.fetch_and_sanitize("BUG-123")

    # Raw email should be redacted
    assert "somchai@example.com" not in ticket.description_sanitized
    # Raw phone should be redacted
    assert "+66812345678" not in ticket.description_sanitized


def test_comments_are_redacted():
    jc = JiraConnector()
    ticket, _ = jc.fetch_and_sanitize("BUG-123")

    assert len(ticket.comments_sanitized) == 2
    # First comment has an email
    assert "support@company.com" not in ticket.comments_sanitized[0]
