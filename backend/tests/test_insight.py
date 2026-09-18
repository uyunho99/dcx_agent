from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import insight, s3
from app.routers.insight import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def draft(client, golden_cam, golden_classified):
    s3.save_json("sessions/golden-a/session.json", {
        "bk": "preserved", "known_insights": [
            {"id": item["id"], "text": item["text"]}
            for item in golden_classified()["known_insights"]],
    })
    response = client.post("/api/insight/synthesize", json={
        "sid": "golden-a", "headline": "준비 부담을 줄인다", "cams": [golden_cam()],
    })
    assert response.status_code == 200, response.text
    return response.json()


def concept_payload(draft, golden_evidence):
    package = golden_evidence()
    counter = next(e for e in package["evidence"] if e["role"] == "refute")
    return {
        "sid": "golden-a", "from_insight": draft["insight_id"],
        "service_bullets": [{"text": "선택적으로 준비한다", "from_action": counter["action_id"]}],
        "experience": [{"text": counter["quote"] + " 우주선이 순간이동한다.",
                        "from_action": counter["action_id"], "grade": "confirmed"}],
        "evidence_packages": [package],
        "cx_4d": {"physical": .82, "system": .61, "mental": .30, "cultural": .24},
    }


def test_synthesis_preserves_cam_and_null_odi(draft, golden_cam):
    cam = golden_cam()
    assert draft["actions"] == [c["action_id"] for c in cam["columns"]]
    assert draft["contributing"] == [cam["persona_id"]]
    assert draft["pain_points"] == [cam["columns"][0]["barrier"]["text"]]
    assert draft["odi_sum"] == 11
    assert draft["action_sources"][cam["columns"][1]["action_id"]]["column"]["odi"] is None
    assert insight.get_artifact("insights", "golden-a", draft["insight_id"]) == draft


def test_confirm_append_and_next_session_contract(client, draft):
    before = deepcopy(s3.load_json("sessions/golden-a/session.json"))
    assert len(before["known_insights"]) == 5  # synthesis is not confirmation
    route = f'/api/insight/golden-a/{draft["insight_id"]}/confirm'
    assert client.post(route).status_code == 200
    assert client.post(route).status_code == 200
    saved = s3.load_json("sessions/golden-a/session.json")
    assert saved["bk"] == "preserved"
    assert saved["known_insights"] == before["known_insights"] + [
        {"id": draft["insight_id"], "text": draft["headline"]}]
    s3.save_json("sessions/next/session.json", {"known_insights": [], "bk": "next"})
    insight.inherit_known_insights("golden-a", "next")
    insight.inherit_known_insights("golden-a", "next")
    assert s3.load_json("sessions/next/session.json")["known_insights"] == saved["known_insights"]


def test_sentence_grades_lineage_and_manual_cx(client, draft, golden_evidence,
                                             golden_classified):
    payload = concept_payload(draft, golden_evidence)
    response = client.post("/api/concept/generate", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert [s["grade"] for s in result["experience"]] == ["confirmed", "confirmed", "speculated"]
    assert result["experience"][-1]["cites"] == []
    assert result["cx_4d"] == payload["cx_4d"]
    bullet = result["service_bullets"][0]
    counter = next(e for e in payload["evidence_packages"][0]["evidence"] if e["role"] == "refute")
    source = result["action_sources"][bullet["from_action"]]
    assert counter["doc_id"] in source["column"]["action"]["cites"]
    assert counter["doc_id"] in bullet["cites"]
    assert counter["doc_id"] in [d["doc_id"] for d in golden_classified()["records"]]
    saved = client.get(f'/api/concept/golden-a/{result["concept_id"]}').json()
    assert saved == result


def test_edge_counter_chain(client, golden_cam, golden_clusters, golden_evidence, golden_classified):
    # Golden refute d_000010 is not Edge; add a scoped Edge counter mock.
    edge = next(d["doc_id"] for d in golden_clusters()["clusters"][0]["documents"]
                if d["band"] == "edge")
    package = golden_evidence()
    counter = next(row for row in package["evidence"] if row["doc_id"] == edge)
    counter["role"] = "refute"
    cam = golden_cam()
    column = next(c for c in cam["columns"] if c["action_id"] == counter["action_id"])
    column["action"] = {"text": counter["quote"], "grade": "confirmed", "cites": [edge]}
    draft = client.post("/api/insight/synthesize", json={
        "sid": "golden-a", "headline": "반례에서 도출", "cams": [cam]}).json()
    item = {"text": counter["quote"], "from_action": counter["action_id"]}
    response = client.post("/api/concept/generate", json={
        "sid": "golden-a", "from_insight": draft["insight_id"],
        "service_bullets": [item], "experience": [item], "evidence_packages": [package]})
    assert response.status_code == 200, response.text
    result = response.json()
    bullet = result["service_bullets"][0]
    source = result["action_sources"][bullet["from_action"]]
    assert edge in bullet["cites"] and edge in source["column"]["action"]["cites"]
    assert any(row["doc_id"] == edge and row["role"] == "refute" for row in source["evidence"])
    assert next(row for row in golden_classified()["records"] if row["doc_id"] == edge)["text"] == counter["quote"]


def test_grade_requires_hit_and_overlap_and_scope(monkeypatch):
    evidence = [{"doc_id": "d1", "quote": "one two"}]
    monkeypatch.setattr(insight, "retrieve", lambda sentence, scope: evidence)
    assert insight.grade_sentence("one three four", evidence)["grade"] == "speculated"
    assert insight.grade_sentence("one two three four five", evidence)["grade"] == "confirmed"
    monkeypatch.setattr(insight, "retrieve", lambda sentence, scope: [])
    assert insight.grade_sentence("one two", evidence)["grade"] == "speculated"
    monkeypatch.setattr(insight, "retrieve", lambda sentence, scope: [{"doc_id": "foreign", "quote": "one two"}])
    assert insight.grade_sentence("one two", evidence)["cites"] == []


def test_interviews_revision_persists(client, draft, golden_evidence):
    concept = client.post("/api/concept/generate", json=concept_payload(draft, golden_evidence)).json()
    route = f'/api/concept/golden-a/{concept["concept_id"]}/interviews'
    assert client.post(route, json={"quote": "필요해요", "stance": "support"}).status_code == 200
    result = client.post(route, json={"quote": "준비가 더 복잡해요", "stance": "refute"}).json()
    assert result["stance_counts"] == {"support": 1, "refute": 1}
    assert result["revision_requests"] == [{"interview_index": 1, "quote": "준비가 더 복잡해요", "status": "requested"}]
    assert result["revision_required"] is True
    assert client.get(f'/api/concept/golden-a/{concept["concept_id"]}').json() == result
    assert client.post(route, json={"quote": "maybe", "stance": "neutral"}).status_code == 422


@pytest.mark.parametrize("fault", ["action", "scope", "doc", "session"])
def test_invalid_lineage_rejected(client, draft, golden_evidence, fault):
    payload = concept_payload(draft, golden_evidence)
    package = payload["evidence_packages"][0]
    if fault == "action":
        payload["service_bullets"][0]["from_action"] = "missing"
    elif fault == "scope":
        package["evidence"][0]["context_id"] = "foreign"
    elif fault == "doc":
        package["evidence"][0]["doc_id"] = "foreign"
    else:
        package["sid"] = "foreign"
    assert client.post("/api/concept/generate", json=payload).status_code == 422
    assert s3.list_objects("concepts/golden-a/") == []


def test_no_hits_overrides_claimed_grade(client, draft, golden_evidence):
    payload = concept_payload(draft, golden_evidence)
    payload["evidence_packages"][0]["evidence"] = []
    payload["cx_4d"] = None
    result = client.post("/api/concept/generate", json=payload).json()
    assert all(s["grade"] == "speculated" for s in result["experience"])
    assert result["cx_4d"] is None


def test_null_odi_not_zero_and_cross_session_cam_rejected(client, golden_cam):
    cam = golden_cam()
    cam["columns"] = cam["columns"][1:]
    payload = {"sid": "golden-a", "headline": "표본 부족", "cams": [cam]}
    assert client.post("/api/insight/synthesize", json=payload).json()["odi_sum"] is None
    payload["sid"] = "other"
    assert client.post("/api/insight/synthesize", json=payload).status_code == 422


def test_missing_resources_and_unsafe_ids(client):
    assert client.get("/api/concept/no/missing").status_code == 404
    assert client.post("/api/insight/no/missing/confirm").status_code == 404
    with pytest.raises(ValueError):
        insight.get_artifact("concepts", "../escape", "missing")


def test_malformed_cam_measurement_is_validation_error(client, golden_cam):
    cam = golden_cam()
    cam["columns"][0]["measurements"][0].pop("doc_id")
    response = client.post("/api/insight/synthesize", json={
        "sid": "golden-a", "headline": "잘못된 입력", "cams": [cam]})
    assert response.status_code == 422


def test_multiple_personas_and_conflicting_actions(client, golden_cam):
    cams = [golden_cam("CL0-P1"), golden_cam("CL1-P1")]
    payload = {"sid": "golden-a", "headline": "공통 인사이트", "cams": cams}
    result = client.post("/api/insight/synthesize", json=payload).json()
    assert result["contributing"] == ["CL0-P1", "CL1-P1"]
    assert len(result["actions"]) == 4 and result["odi_sum"] == 22
    payload["cams"] = [cams[0], cams[0]]
    assert client.post("/api/insight/synthesize", json=payload).status_code == 422
