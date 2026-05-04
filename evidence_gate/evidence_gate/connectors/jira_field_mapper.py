from __future__ import annotations

from evidence_gate.contracts.sanitized_ticket import SanitizedTicketContext


# Allowlisted Jira fields — everything else is dropped
_ALLOWED_FIELDS = {
    "summary", "issuetype", "priority", "status", "labels", "components",
    "description", "comment", "created", "updated", "resolutiondate",
    "issuelinks", "subtasks", "parent", "assignee", "reporter",
    "attachment",
}


def map_jira_fields(ticket_id: str, raw_issue: dict) -> SanitizedTicketContext:
    """Map raw Jira REST JSON to SanitizedTicketContext with only allowlisted fields.

    Does NOT redact text — caller must redact description/comments separately.
    """
    fields = raw_issue.get("fields", {})

    # Safe nested access helpers
    def _name(obj: dict | None) -> str:
        if isinstance(obj, dict):
            return obj.get("name", "")
        return ""

    def _component_names(comps: list | None) -> list[str]:
        if not comps:
            return []
        return [c["name"] for c in comps if isinstance(c, dict) and "name" in c]

    def _comment_bodies(comment_field: dict | None) -> list[str]:
        if not comment_field:
            return []
        comments = comment_field.get("comments", [])
        return [c.get("body", "") for c in comments if isinstance(c, dict)]

    def _subtask_keys(subtasks: list | None) -> list[str]:
        if not subtasks:
            return []
        return [s["key"] if isinstance(s, dict) else str(s) for s in subtasks]

    def _link_summaries(links: list | None) -> list[dict]:
        if not links:
            return []
        result = []
        for link in links:
            if not isinstance(link, dict):
                continue
            entry: dict = {}
            if "type" in link and isinstance(link["type"], dict):
                entry["type"] = link["type"].get("name", "")
            if "outwardIssue" in link and isinstance(link["outwardIssue"], dict):
                entry["outward_key"] = link["outwardIssue"].get("key", "")
            if "inwardIssue" in link and isinstance(link["inwardIssue"], dict):
                entry["inward_key"] = link["inwardIssue"].get("key", "")
            result.append(entry)
        return result

    return SanitizedTicketContext(
        ticket_id=ticket_id,
        summary=fields.get("summary", ""),
        issue_type=_name(fields.get("issuetype")),
        priority=_name(fields.get("priority")),
        status=_name(fields.get("status")),
        labels=fields.get("labels", []),
        components=_component_names(fields.get("components")),
        description_sanitized=fields.get("description", "") or "",
        comments_sanitized=_comment_bodies(fields.get("comment")),
        created=fields.get("created"),
        updated=fields.get("updated"),
        issue_links=_link_summaries(fields.get("issuelinks")),
        subtasks=_subtask_keys(fields.get("subtasks")),
    )
