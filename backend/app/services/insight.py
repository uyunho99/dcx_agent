"""STEP 11 deterministic assembly and persistence (no generated CX formula).

T3/T8 integration: sessions/{sid}/session.json.known_insights is the canonical
[{id, text}] list. Confirmation appends the insight ID/headline, idempotently.
Call inherit_known_insights(source_sid, target_sid) when creating a follow-up
session, BEFORE T4 embedding/T8 collection. There is no global knowledge key.

T9 is not present in this lane. grade_sentence uses Action-scoped lexical
retrieval and query-token overlap; replace the retrieve boundary with T9's
retriever when integrated. Grades follow the golden confirmed/speculated enum.
Storage offers no CAS: callers must serialize writes to the same session or
concept across processes (the existing S3 interface is read/modify/write).
"""

from copy import deepcopy
from datetime import datetime, timezone
import re
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field

from app.services import s3


Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$", max_length=128)]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Number = Annotated[float, Field(allow_inf_nan=False)]


_confirmation_locks = WeakValueDictionary()
_confirmation_locks_guard = Lock()


def _confirmation_lock(sid):
    with _confirmation_locks_guard:
        lock = _confirmation_locks.get(sid)
        if lock is None:
            lock = Lock()
            _confirmation_locks[sid] = lock
        return lock


class Cell(BaseModel):
    text: Text
    grade: Literal["confirmed", "speculated"]
    cites: list[Text]


class Measurement(BaseModel):
    model_config = ConfigDict(extra="allow")
    doc_id: Text
    importance: Number
    satisfaction: Number | None


class Column(BaseModel):
    model_config = ConfigDict(extra="allow")
    action_id: Identifier
    context_id: Identifier
    context: Cell
    action: Cell
    barrier: Cell | None
    barrier_gen_fail: bool
    measurements: list[Measurement]
    odi: Number | None


class Cam(BaseModel):
    model_config = ConfigDict(extra="allow")
    sid: Identifier
    persona_id: Identifier
    columns: list[Column] = Field(min_length=1)


class SynthesizeRequest(BaseModel):
    sid: Identifier
    headline: Text
    cams: list[Cam] = Field(min_length=1)


class ActionText(BaseModel):
    text: Text
    from_action: Identifier


class Interview(BaseModel):
    quote: Text
    stance: Literal["support", "refute"]


class CX4D(BaseModel):
    """Human assigned numbers; no invented scale, defaults, or formula."""
    model_config = ConfigDict(extra="forbid")
    physical: Number
    system: Number
    mental: Number
    cultural: Number


class EvidenceAction(BaseModel):
    action_id: Identifier
    context_id: Identifier
    doc_ids: list[Text]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")
    doc_id: Text
    quote: Text
    action_id: Identifier
    cluster_id: Identifier
    persona_id: Identifier
    context_id: Identifier
    role: Literal["support", "refute"]


class EvidencePackage(BaseModel):
    sid: Identifier
    cluster_id: Identifier
    persona_id: Identifier
    actions: list[EvidenceAction]
    evidence: list[Evidence]


class GenerateRequest(BaseModel):
    sid: Identifier
    from_insight: Identifier
    service_bullets: list[ActionText] = Field(min_length=1)
    experience: list[ActionText] = Field(min_length=1)
    evidence_packages: list[EvidencePackage] = Field(min_length=1)
    interviews: list[Interview] = Field(default_factory=list)
    cx_4d: CX4D | None = None
    lexical_overlap_min: float = Field(default=.40, ge=0, le=1, allow_inf_nan=False)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Invalid identifier")
    return value


def _session(sid):
    key = f"sessions/{_identifier(sid)}/session.json"
    data = s3.load_json(key)
    if data is None:
        raise FileNotFoundError(f"Session not found: {sid}")
    return key, data


def _append_known(data, entries):
    known = data.setdefault("known_insights", [])
    for entry in entries:
        existing = next((item for item in known if item["id"] == entry["id"]), None)
        if existing is not None and existing["text"] != entry["text"]:
            raise ValueError("Conflicting known insight ID")
        if existing is None:
            known.append({"id": entry["id"], "text": entry["text"]})


def inherit_known_insights(source_sid: str, target_sid: str) -> list[dict]:
    """Explicit follow-up-session hook for T3; merge without duplicate IDs."""
    _, source = _session(source_sid)
    key, target = _session(target_sid)
    _append_known(target, source.get("known_insights", []))
    s3.save_json(key, target)
    return target["known_insights"]


def _save(kind, data):
    s3.save_json(f'{kind}/{data["sid"]}/{data["timestamp"]}.json', data)
    return data


def get_artifact(kind: str, sid: str, artifact_id: str) -> dict:
    if kind not in {"insights", "concepts"}:
        raise ValueError("Invalid artifact kind")
    _identifier(artifact_id)
    prefix = f"{kind}/{_identifier(sid)}/"
    for item in reversed(sorted(s3.list_objects(prefix), key=lambda item: item["Key"])):
        key = item["Key"]
        if not key.startswith(prefix) or not key.endswith(".json"):
            continue
        data = s3.load_json(key)
        if data and data.get(kind[:-1] + "_id") == artifact_id:
            return data
    raise FileNotFoundError(f"Artifact not found: {artifact_id}")


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]


def synthesize(req: SynthesizeRequest) -> dict:
    sources, pain_points, contributing, scores = {}, [], [], []
    for cam in req.cams:
        if cam.sid != req.sid:
            raise ValueError("CAM session mismatch")
        if cam.persona_id not in contributing:
            contributing.append(cam.persona_id)
        for column in cam.columns:
            if column.action_id in sources:
                raise ValueError("Duplicate CAM Action")
            if (column.barrier is None) != column.barrier_gen_fail:
                raise ValueError("Invalid barrier generation state")
            docs = {row.doc_id for row in column.measurements}
            for cell in (column.context, column.action, column.barrier):
                if cell is not None and not set(cell.cites) <= docs:
                    raise ValueError("CAM citation outside Action measurements")
            sources[column.action_id] = {"persona_id": cam.persona_id,
                                         "column": column.model_dump()}
            if column.barrier is not None:
                pain_points.append(column.barrier.text)
            if column.odi is not None:
                scores.append(column.odi)
    return _save("insights", {
        "sid": req.sid, "timestamp": _timestamp(), "insight_id": "IN-" + uuid4().hex,
        "headline": req.headline, "pain_points": pain_points,
        "contributing": contributing, "actions": list(sources),
        "odi_sum": sum(scores) if scores else None,
        "odi_missing_actions": [a for a, s in sources.items() if s["column"]["odi"] is None],
        "action_sources": sources, "status": "draft",
    })


def confirm(sid: str, insight_id: str) -> dict:
    # Hold a per-session lock across the read/append/write in this process.
    with _confirmation_lock(_identifier(sid)):
        data = get_artifact("insights", sid, insight_id)
        key, session = _session(sid)
        _append_known(session, [{"id": data["insight_id"], "text": data["headline"]}])
        # Append first: retry after an artifact-write failure remains idempotent.
        s3.save_json(key, session)
        data["status"] = "confirmed"
        return _save("insights", data)


def _tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


def retrieve(sentence: str, evidence: list[dict]) -> list[dict]:
    """Local retrieval boundary. Input is already restricted to this Action."""
    tokens = _tokens(sentence)
    return [row for row in evidence if tokens & _tokens(row["quote"])]


def grade_sentence(sentence: str, evidence: list[dict], lexical_overlap_min=.40) -> dict:
    tokens = _tokens(sentence)
    allowed = {row["doc_id"]: row for row in evidence}
    cites = []
    for hit in retrieve(sentence, evidence):
        # Never accept out-of-scope retriever results or a retriever's grade.
        row = allowed.get(hit["doc_id"])
        if row and tokens and len(tokens & _tokens(row["quote"])) / len(tokens) >= lexical_overlap_min:
            cites.append(row["doc_id"])
    return {"text": sentence, "grade": "confirmed" if cites else "speculated",
            "cites": sorted(set(cites))}


def _scoped_evidence(req, sources):
    scoped = {action_id: [] for action_id in sources}
    seen_actions = set()
    for package in req.evidence_packages:
        if package.sid != req.sid:
            raise ValueError("Evidence session mismatch")
        actions = {}
        for action in package.actions:
            if action.action_id in seen_actions:
                raise ValueError("Duplicate evidence Action")
            seen_actions.add(action.action_id)
            actions[action.action_id] = action
            source = sources.get(action.action_id)
            if source is None or source["persona_id"] != package.persona_id:
                raise ValueError("Evidence Action outside insight")
            column = source["column"]
            if column["context_id"] != action.context_id:
                raise ValueError("Action context mismatch")
            docs = set(action.doc_ids)
            if not {m["doc_id"] for m in column["measurements"]} <= docs:
                raise ValueError("CAM documents outside evidence Action")
        seen_docs = set()
        for row in package.evidence:
            action = actions.get(row.action_id)
            if (action is None or row.doc_id not in action.doc_ids
                    or row.context_id != action.context_id
                    or row.persona_id != package.persona_id
                    or row.cluster_id != package.cluster_id or row.doc_id in seen_docs):
                raise ValueError("Evidence citation or scope mismatch")
            seen_docs.add(row.doc_id)
            scoped[row.action_id].append(row.model_dump())
    required = {item.from_action for item in req.service_bullets + req.experience}
    if not required <= seen_actions:
        raise ValueError("Missing evidence for referenced Action")
    return scoped


def _interview_summary(data):
    data["stance_counts"] = {stance: sum(i["stance"] == stance for i in data["interviews"])
                             for stance in ("support", "refute")}
    data["revision_requests"] = [
        {"interview_index": index, "quote": item["quote"], "status": "requested"}
        for index, item in enumerate(data["interviews"]) if item["stance"] == "refute"]
    data["revision_required"] = bool(data["revision_requests"])


def generate(req: GenerateRequest) -> dict:
    parent = get_artifact("insights", req.sid, req.from_insight)
    sources = deepcopy(parent["action_sources"])
    scoped = _scoped_evidence(req, sources)
    bullets = []
    for bullet in req.service_bullets:
        column = sources[bullet.from_action]["column"]
        cites = {doc for key in ("context", "action", "barrier")
                 if column[key] is not None for doc in column[key]["cites"]}
        cites.update(row["doc_id"] for row in scoped[bullet.from_action] if row["role"] == "refute")
        bullets.append({**bullet.model_dump(), "cites": sorted(cites)})
    experience = []
    for item in req.experience:
        # Split punctuation/newlines, but keep periods between digits intact.
        for sentence in re.split(r"(?<=[.!?。！？])(?!(?<=\d\.)\d)\s*|\n+", item.text):
            if sentence.strip():
                experience.append({**grade_sentence(sentence.strip(), scoped[item.from_action],
                                                     req.lexical_overlap_min),
                                   "from_action": item.from_action})
    for action_id, source in sources.items():
        source["evidence"] = scoped[action_id]
    data = {"sid": req.sid, "timestamp": _timestamp(), "concept_id": "CO-" + uuid4().hex,
            "from_insight": req.from_insight, "contributing": parent["contributing"],
            "service_bullets": bullets, "experience": experience, "action_sources": sources,
            "interviews": [item.model_dump() for item in req.interviews],
            "cx_4d": req.cx_4d.model_dump() if req.cx_4d is not None else None,
            "lexical_overlap_min": req.lexical_overlap_min}
    _interview_summary(data)
    return _save("concepts", data)


def add_interview(sid: str, concept_id: str, interview: Interview) -> dict:
    data = get_artifact("concepts", sid, concept_id)
    data["interviews"].append(interview.model_dump())
    _interview_summary(data)
    return _save("concepts", data)
