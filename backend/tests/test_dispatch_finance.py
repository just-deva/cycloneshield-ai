from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import engine, finance
from app.config import settings
from app.dispatch import audit, cap, workflow
from app.main import app


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    from app.ai import aicache
    monkeypatch.setattr(aicache, "DIR", tmp_path / "ai_cache")
    monkeypatch.setattr(settings(), "state_dir", tmp_path)
    monkeypatch.setattr(settings(), "telegram_bot_token", None)
    monkeypatch.setattr(workflow, "_ADV", {})
    monkeypatch.setattr(workflow, "_LOADED", True)


client = TestClient(app)


@pytest.fixture(scope="module")
def hudhud():
    return engine.simulate("IN-AP", "hudhud-2014", ensemble=False)


def _draft(sim_id, lead_h=24, role="district_collector"):
    r = client.post("/api/advisories/draft", json={"sim_id": sim_id, "lead_h": lead_h, "role": role, "use_ai": False})
    assert r.status_code == 200, r.text
    return r.json()


def test_audit_chain_detects_tampering():
    audit.append("a", "one", "x", {"n": 1})
    audit.append("b", "two", "x", {"n": 2})
    audit.append("c", "three", "x", {"n": 3})
    assert audit.verify()["ok"]
    lines = (settings().state_dir / "audit.jsonl").read_text().splitlines()
    e = json.loads(lines[1]); e["actor"] = "mallory"
    lines[1] = json.dumps(e, sort_keys=True)
    (settings().state_dir / "audit.jsonl").write_text("\n".join(lines) + "\n")
    v = audit.verify()
    assert not v["ok"] and v["broken_at"] == 2
    # deleting an entry also breaks the chain
    (settings().state_dir / "audit.jsonl").write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert not audit.verify()["ok"]


def test_cap_is_exercise_restricted_and_well_formed(hudhud):
    a = _draft(hudhud["sim_id"])
    xml = client.get(f"/api/advisories/{a['id']}/cap.xml").text
    assert cap.check_cap(xml) == []
    assert "<cap:status>Exercise</cap:status>" in xml and "<cap:scope>Restricted</cap:scope>" in xml
    assert "cycloneshield-demo" in xml and "IMD" not in xml.split("<cap:sender>")[1].split("</cap:sender>")[0]
    # tampering with the safety fields is caught
    bad = xml.replace("Exercise", "Actual")
    assert "status must be Exercise" in cap.check_cap(bad)


def test_orange_needs_two_distinct_approvers_and_maker_cannot_approve(hudhud):
    a = _draft(hudhud["sim_id"], lead_h=24)              # orange -> two approvals
    assert a["required_approvals"] == 2 and a["tier"]["colour"] == "orange"
    i = a["id"]
    assert client.post(f"/api/advisories/{i}/dispatch", json={"actor": "x"}).status_code == 409   # not approved
    assert client.post(f"/api/advisories/{i}/submit", json={"actor": "Maker"}).status_code == 200
    assert client.post(f"/api/advisories/{i}/approve", json={"actor": "Maker"}).status_code == 409  # maker-checker
    assert client.post(f"/api/advisories/{i}/approve", json={"actor": "Approver A"}).json()["status"] == "PENDING_APPROVAL"
    assert client.post(f"/api/advisories/{i}/approve", json={"actor": "Approver A"}).status_code == 409  # same person twice
    assert client.post(f"/api/advisories/{i}/approve", json={"actor": "Approver B"}).json()["status"] == "APPROVED"
    d = client.post(f"/api/advisories/{i}/dispatch", json={"actor": "Approver B"}).json()
    assert d["status"] == "DISPATCHED"
    statuses = {r["channel"]: r["status"] for r in d["dispatch"]["results"]}
    assert statuses["telegram"] == "simulated" and statuses["sms"] == "simulated" and statuses["cell_broadcast"] == "simulated"
    assert client.post(f"/api/advisories/{i}/ack", json={"actor": "collector"}).json()["status"] == "ACKED"
    assert audit.verify()["ok"] and audit.verify()["entries"] == 6      # draft, submit, 2 approvals, dispatch, ack


def test_yellow_needs_one_approver(hudhud):
    a = _draft(hudhud["sim_id"], lead_h=48, role="hospital")
    assert a["required_approvals"] == 1 and a["tier"]["colour"] == "yellow"
    i = a["id"]
    client.post(f"/api/advisories/{i}/submit", json={"actor": "Maker"})
    assert client.post(f"/api/advisories/{i}/approve", json={"actor": "Approver A"}).json()["status"] == "APPROVED"


def test_cancel_emits_cap_cancel(hudhud):
    a = _draft(hudhud["sim_id"], lead_h=48, role="power")
    i = a["id"]
    client.post(f"/api/advisories/{i}/submit", json={"actor": "M"})
    client.post(f"/api/advisories/{i}/approve", json={"actor": "A"})
    client.post(f"/api/advisories/{i}/dispatch", json={"actor": "A"})
    r = client.post(f"/api/advisories/{i}/cancel", json={"actor": "A"}).json()
    assert r["status"] == "CANCELLED"
    assert "<cap:msgType>Cancel</cap:msgType>" in workflow.get(i)["cap_cancel_xml"]


def test_mock_deoc_receiver_validates_cap(hudhud):
    a = _draft(hudhud["sim_id"], lead_h=72)
    xml = client.get(f"/api/advisories/{a['id']}/cap.xml").text
    r = client.post("/api/mock-deoc", json={"advisory_id": a["id"], "tier": "x", "cap_xml": xml}).json()
    assert r["received"] and r["cap_valid"]


def test_finance_tiers_are_cumulative_and_labelled(hudhud):
    r24 = finance.evaluate(hudhud, 24, pool_crore=10)
    assert r24["tier_reached"] == "T2 Warning" and r24["recommended_release_pct"] == 75
    assert r24["recommended_release_crore_inr"] == 7.5
    r72 = finance.evaluate(hudhud, 72, 10)
    assert r72["tier_reached"] == "T0 Readiness" and r72["recommended_release_pct"] == 10
    r12 = finance.evaluate(hudhud, 12, 10)
    assert r12["tier_reached"] == "T3 Landfall" and r12["recommended_release_pct"] == 100
    assert "illustrative" in r24["illustrative"].lower() and "No funds are moved" in r24["memo"]


def test_finance_no_trigger_for_weak_near_miss():
    m = engine.simulate("IN-AP", "montha-2025", ensemble=False)
    r = finance.evaluate(m, 12, 10)
    assert r["level"] == 0 and r["recommended_release_pct"] == 0


def test_finance_endpoint_and_approval_are_audited(hudhud):
    r = client.get(f"/api/finance/{hudhud['sim_id']}", params={"lead_h": 24, "pool_crore": 10}).json()
    assert r["tier_reached"] == "T2 Warning"
    ap = client.post(f"/api/finance/{hudhud['sim_id']}/approve", json={"actor": "Approver A", "lead_h": 24, "pool_crore": 10}).json()
    assert ap["approved"] and audit.verify()["ok"]


def test_telegram_acknowledge_button_marks_the_advisory_and_is_audited(hudhud, monkeypatch):
    from app import routes
    answers = []
    monkeypatch.setattr(routes.channels, "answer_callback", lambda cb_id, text: answers.append((cb_id, text)))
    a = _draft(hudhud["sim_id"], lead_h=48, role="hospital")            # yellow: one approver
    i = a["id"]
    client.post(f"/api/advisories/{i}/submit", json={"actor": "Maker"})
    client.post(f"/api/advisories/{i}/approve", json={"actor": "Approver A"})
    client.post(f"/api/advisories/{i}/dispatch", json={"actor": "Approver A"})
    routes.handle_telegram_update({"callback_query": {"id": "cb1", "data": f"ack:{i}", "from": {"username": "duty_officer", "id": 42}}})
    rec = workflow.get(i)
    assert rec["status"] == "ACKED" and rec["acks"][0]["via"] == "telegram" and rec["acks"][0]["actor"] == "telegram:duty_officer"
    assert answers[-1][1].startswith("Receipt acknowledged")
    assert audit.verify()["ok"]
    # a press for an advisory that was never dispatched is refused, told to the user, and audited (never silently dropped)
    b = _draft(hudhud["sim_id"], lead_h=48, role="power")
    routes.handle_telegram_update({"callback_query": {"id": "cb2", "data": f"ack:{b['id']}", "from": {"id": 7}}})
    assert workflow.get(b["id"])["status"] == "DRAFT" and answers[-1][1].startswith("Could not acknowledge")
    assert any(e["action"] == "telegram_ack_failed" for e in audit.read_all())
