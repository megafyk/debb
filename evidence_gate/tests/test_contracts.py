from evidence_gate.contracts import (
    AuditEvent,
    DiagnosticFeature,
    EvidenceRequest,
    EvidenceSession,
    EvidenceSessionContext,
    MaskedEvidencePackage,
    MetabaseQueryPlan,
    QueryFilter,
    QuickwitQueryPlan,
    QuickwitQueryResult,
    SanitizedTicketContext,
    SensitiveRef,
)


def test_sanitized_ticket_context():
    t = SanitizedTicketContext(
        ticket_id="BUG-1",
        summary="Test",
        issue_type="Bug",
        priority="High",
        status="Open",
    )
    data = t.model_dump()
    assert data["ticket_id"] == "BUG-1"
    roundtrip = SanitizedTicketContext.model_validate(data)
    assert roundtrip.summary == "Test"


def test_evidence_session_generates_id():
    s = EvidenceSession(ticket_id="BUG-1")
    assert s.evidence_session_id.startswith("ESESS-")
    assert len(s.evidence_session_id) > 6


def test_sensitive_ref():
    r = SensitiveRef(value_ref="SECURE_VALUE_REF_phone_001", field_type="phone_number")
    assert r.field_type == "phone_number"


def test_evidence_session_context():
    ticket = SanitizedTicketContext(
        ticket_id="BUG-1", summary="Test", issue_type="Bug", priority="High", status="Open"
    )
    ctx = EvidenceSessionContext(
        evidence_session_id="ESESS-test",
        ticket_id="BUG-1",
        trace_id="abc",
        sanitized_ticket=ticket,
    )
    json_str = ctx.model_dump_json()
    assert "ESESS-test" in json_str


def test_quickwit_query_plan():
    plan = QuickwitQueryPlan(
        evidence_session_id="ESESS-1",
        service="login-service",
        datasource_uid="login-service-prod",
        from_="2026-01-01T00:00:00Z",
        to="2026-01-01T01:00:00Z",
        query_intent="Find login failures",
        filters=[QueryFilter(field="service", op="=", value="login-service")],
        fields_requested=["timestamp", "error_code"],
        max_hits=100,
    )
    assert plan.type == "quickwit_query_plan"
    assert plan.from_ == "2026-01-01T00:00:00Z"
    # Plan serialises with the spec field name 'from'.
    assert plan.model_dump(by_alias=True)["from"] == "2026-01-01T00:00:00Z"


def test_quickwit_query_result():
    result = QuickwitQueryResult(hits=[], is_valuable=False, reason="zero_hits")
    assert result.is_valuable is False
    assert result.reason == "zero_hits"


def test_metabase_query_plan():
    plan = MetabaseQueryPlan(
        evidence_session_id="ESESS-1",
        service="account-service",
        entity="account",
        query_intent="Check account status",
        facts_requested=["account_exists"],
    )
    assert plan.type == "metabase_query_plan"


def test_evidence_request_generates_id():
    req = EvidenceRequest(
        evidence_session_id="ESESS-1",
        request_type="quickwit_query_plan",
    )
    assert req.evidence_request_id.startswith("EREQ-")
    assert req.state == "created"


def test_masked_evidence_package():
    pkg = MaskedEvidencePackage(
        evidence_session_id="ESESS-1",
        source_type="quickwit_logs",
        masked_data={"summary": "3 error events found"},
        diagnostic_features=[
            DiagnosticFeature(field="phone", subject_token="PHONE_TOK_A", features={"digit_count": 9})
        ],
    )
    assert pkg.evidence_id.startswith("EVID-")
    assert len(pkg.diagnostic_features) == 1


def test_audit_event():
    e = AuditEvent(
        evidence_session_id="ESESS-1",
        event_type="session_created",
        details={"ticket_id": "BUG-1"},
    )
    assert e.audit_id.startswith("AUD-")
