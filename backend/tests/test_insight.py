from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

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


def test_concurrent_confirm_preserves_both_appends(client, draft, golden_cam, monkeypatch):
    second = client.post("/api/insight/synthesize", json={
        "sid": "golden-a", "headline": "대기 부담을 줄인다", "cams": [golden_cam()],
    }).json()
    key = "sessions/golden-a/session.json"
    stored = {key: deepcopy(s3.load_json(key))}
    before = deepcopy(stored[key]["known_insights"])
    load_json, save_json = s3.load_json, s3.save_json
    reads = Barrier(2)
    start = Barrier(2)

    def load(session_key):
        if session_key != key:
            return load_json(session_key)
        snapshot = deepcopy(stored[key])
        # Force stale reads without serialization; a lock lets only one reader
        # reach this barrier, so the bounded wait must also allow that case.
        try:
            reads.wait(timeout=1)
        except BrokenBarrierError:
            pass
        return snapshot

    def save(session_key, data):
        if session_key == key:
            stored[key] = deepcopy(data)
        else:
            save_json(session_key, data)

    monkeypatch.setattr(s3, "load_json", load)
    monkeypatch.setattr(s3, "save_json", save)

    def confirm(item):
        start.wait(timeout=5)
        with TestClient(client.app) as concurrent_client:
            return concurrent_client.post(f'/api/insight/golden-a/{item["insight_id"]}/confirm')

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(confirm, [draft, second]))
    assert all(response.status_code == 200 for response in responses)
    assert [response.json()["status"] for response in responses] == ["confirmed", "confirmed"]
    saved = stored[key]
    assert saved["bk"] == "preserved"
    assert saved["known_insights"][:len(before)] == before
    assert sorted(saved["known_insights"][len(before):], key=lambda item: item["id"]) == sorted(
        [{"id": item["insight_id"], "text": item["headline"]} for item in [draft, second]],
        key=lambda item: item["id"],
    )


@pytest.mark.parametrize("suffix, following", [
    ("", []),
    (" 다음 문장이다. Another sentence!", ["다음 문장이다.", "Another sentence!"]),
])
def test_decimal_sentence_keeps_one_grade(client, draft, golden_evidence, suffix, following):
    payload = concept_payload(draft, golden_evidence)
    sentence = "평균 대기 시간은 3.5분이다."
    payload["experience"][0]["text"] = sentence + suffix
    counter = next(row for row in payload["evidence_packages"][0]["evidence"]
                   if row["role"] == "refute")
    counter["quote"] = "평균 대기 시간은 짧다."
    response = client.post("/api/concept/generate", json=payload)
    assert response.status_code == 200, response.text
    experience = response.json()["experience"]
    assert [item["text"] for item in experience] == [sentence] + following
    assert experience[0]["grade"] == "confirmed"
    assert counter["doc_id"] in experience[0]["cites"]


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


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("storage_mode", ["local", "remote"])
def test_process_confirm_preserves_both_appends(draft, local_data_dir, reverse, storage_mode):
    """Independent interpreters share storage, never a threading.Lock."""
    import subprocess
    import sys

    second = {**draft, "insight_id": "IN-second", "timestamp": "second",
              "headline": "Second insight"}
    insight._save("insights", second)
    key = "sessions/golden-a/session.json"
    before = s3.load_json(key)
    worker = r'''
import fcntl
import sys
import time
from app.services import insight, s3

item, peer, mode, rank = sys.argv[1:]
root = s3._DATA_DIR
load, save = s3.load_json, s3.save_json
first = True
if mode == "remote":
    # Shared disk stands in for object storage; disable the production flock.
    s3._USE_LOCAL = False

def synchronized_load(key):
    global first
    snapshot = load(key)
    if key == "sessions/golden-a/session.json" and first:
        first = False
        (root / (item + ".read")).touch()
        deadline = time.monotonic() + 1
        while not (root / (peer + ".read")).exists() and time.monotonic() < deadline:
            time.sleep(.005)
        if mode == "remote" and rank == "1":
            # The peer commits after our snapshot but before our validation.
            deadline = time.monotonic() + 5
            while not (root / (peer + ".done")).exists():
                assert time.monotonic() < deadline, "peer did not finish"
                time.sleep(.005)
    return snapshot

def serialized_save(key, data):
    # Serialize individual file writes only, like atomic object PUTs; this does
    # not protect read/modify/write and reproduces lost updates in old code.
    with (root / "test-write.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        save(key, data)

s3.load_json = synchronized_load
s3.save_json = serialized_save
assert insight.confirm("golden-a", item)["status"] == "confirmed"
(root / (item + ".done")).touch()
'''
    ids = [draft["insight_id"], second["insight_id"]]
    if reverse:
        ids.reverse()
    processes = []
    try:
        for rank, (item, peer) in enumerate([ids, ids[::-1]]):
            processes.append(subprocess.Popen(
                [sys.executable, "-c", worker, item, peer, storage_mode, str(rank)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    saved = s3.load_json(key)
    assert saved["bk"] == before["bk"]
    assert saved["known_insights"][:len(before["known_insights"])] == before["known_insights"]
    assert {item["id"] for item in saved["known_insights"]} == {
        item["id"] for item in before["known_insights"]} | set(ids)
    for item in ids:
        assert insight.get_artifact("insights", "golden-a", item)["status"] == "confirmed"


@pytest.mark.parametrize("collision", ["before_write", "after_write"])
def test_confirm_retries_remote_changes(draft, monkeypatch, collision):
    monkeypatch.setattr(s3, "_USE_LOCAL", False)
    key = "sessions/golden-a/session.json"
    load, save = s3.load_json, s3.save_json
    before = load(key)
    calls = 0
    other = {"id": "IN-other", "text": "Other process"}

    def load_with_collision(path):
        nonlocal calls
        if path == key:
            calls += 1
            if calls == (2 if collision == "before_write" else 3):
                changed = deepcopy(before)
                changed["known_insights"].append(other)
                changed["bk"] = "concurrent edit"
                save(key, changed)
        return load(path)

    monkeypatch.setattr(s3, "load_json", load_with_collision)
    assert insight.confirm("golden-a", draft["insight_id"])["status"] == "confirmed"
    saved = load(key)
    assert saved["bk"] == "concurrent edit"
    assert saved["known_insights"] == before["known_insights"] + [
        other, {"id": draft["insight_id"], "text": draft["headline"]}]
    assert calls == (6 if collision == "after_write" else 5)


def test_confirm_retry_exhaustion_leaves_artifact_draft(draft, monkeypatch):
    monkeypatch.setattr(s3, "_USE_LOCAL", False)
    key = "sessions/golden-a/session.json"
    load = s3.load_json
    calls = 0

    def changing_load(path):
        nonlocal calls
        data = load(path)
        if path == key:
            calls += 1
            data["revision"] = calls
        return data

    monkeypatch.setattr(s3, "load_json", changing_load)
    with pytest.raises(RuntimeError, match="Session changed during confirmation"):
        insight.confirm("golden-a", draft["insight_id"])
    assert calls == 2 * insight._SESSION_WRITE_ATTEMPTS
    assert insight.get_artifact("insights", "golden-a", draft["insight_id"])["status"] == "draft"
    assert draft["insight_id"] not in {row["id"] for row in load(key)["known_insights"]}
    # Failure releases the process lock; a subsequent request can succeed.
    monkeypatch.setattr(s3, "load_json", load)
    assert insight.confirm("golden-a", draft["insight_id"])["status"] == "confirmed"
