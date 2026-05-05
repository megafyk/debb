from evidence_gate.connectors.jira_connector import map_jira_fields


def test_maps_allowlisted_fields():
    raw = {
        "key": "TEST-1",
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "priority": {"name": "Medium"},
            "status": {"name": "Open"},
            "labels": ["backend"],
            "components": [{"name": "auth-service"}],
            "description": "Some description",
            "comment": {"comments": [{"body": "A comment"}]},
            "created": "2026-01-01T00:00:00.000+0000",
            "updated": "2026-01-02T00:00:00.000+0000",
            "issuelinks": [],
            "subtasks": [],
            # Fields that should NOT appear in output
            "worklog": {"worklogs": [{"timeSpent": "2h"}]},
            "votes": {"votes": 5},
            "watches": {"watchCount": 10},
        },
    }
    ticket = map_jira_fields("TEST-1", raw)

    assert ticket.ticket_id == "TEST-1"
    assert ticket.summary == "Test issue"
    assert ticket.issue_type == "Bug"
    assert ticket.components == ["auth-service"]
    assert ticket.comments_sanitized == ["A comment"]


def test_drops_blocked_fields():
    """Blocked fields from Jira should not appear in the mapped output."""
    raw = {
        "key": "TEST-2",
        "fields": {
            "summary": "Test",
            "issuetype": {"name": "Task"},
            "priority": {"name": "Low"},
            "status": {"name": "Done"},
            "worklog": {"worklogs": [{"timeSpent": "1h"}]},
            "votes": {"votes": 99},
        },
    }
    ticket = map_jira_fields("TEST-2", raw)
    dumped = ticket.model_dump()
    assert "worklog" not in dumped
    assert "votes" not in dumped
    assert "watches" not in dumped


def test_handles_missing_fields():
    raw = {"key": "TEST-3", "fields": {"summary": "Minimal"}}
    ticket = map_jira_fields("TEST-3", raw)
    assert ticket.summary == "Minimal"
    assert ticket.issue_type == ""
    assert ticket.components == []
    assert ticket.comments_sanitized == []


def test_maps_issue_links():
    raw = {
        "key": "TEST-4",
        "fields": {
            "summary": "Linked",
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "status": {"name": "Open"},
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "outwardIssue": {"key": "TEST-5"},
                },
                {
                    "type": {"name": "Relates"},
                    "inwardIssue": {"key": "TEST-6"},
                },
            ],
        },
    }
    ticket = map_jira_fields("TEST-4", raw)
    assert len(ticket.issue_links) == 2
    assert ticket.issue_links[0]["outward_key"] == "TEST-5"
    assert ticket.issue_links[1]["inward_key"] == "TEST-6"
