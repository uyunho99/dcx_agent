"""Stage-seven validated file contract with a stage-eight read projection.

Unknown fields are retained at every level for forward compatibility. Numbering
is local to a Persona: desire support first, then Contexts in package order,
with support, counter, and rare lists traversed in that order. Duplicate source
quotes remain separate references because their context/role can differ.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.context.versions import version_dir
from app.context.store import read_json
from app.evidence.package import EvidencePackage


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='allow')


class Quote(ContractModel):
    field: str
    idx: int | None
    start: int | None
    end: int | None
    text: str
    # Older producers may omit verification; never assume such quotes verified.
    verified: bool = False


class Evidence(ContractModel):
    doc_id: str
    source: str
    quote: Quote | None
    tags: Any
    # Desire support does not require Context-only annotations in section 2.4.
    novelty: str | None = None


class ContextEvidenceItem(Evidence):
    polarity: float | None
    novelty: str | None
    known_match: Any
    tab: list[str]
    role: str


class RareEvidence(ContextEvidenceItem):
    dist_centroid: float | None
    combo_rarity: float | None


class Metrics(ContractModel):
    importance: float | None
    satisfaction: float | None
    odi: float | None
    doc_count: int
    author_count: int
    provisional: list[str]


class PersonaQuality(ContractModel):
    cohesion: float | None
    boundary: float | None
    stability_ari: float | None


class ContextQuality(ContractModel):
    cohesion: float | None
    boundary: float | None
    stability: float | None
    npmi: float | None


class ContextMetrics(Metrics):
    quality: ContextQuality


class Artifact(ContractModel):
    name: str
    mention_count: int


class PersonaEvidence(ContractModel):
    cluster_id: str
    persona_id: str
    persona_name: str
    desire: str
    goal: list[str]
    desire_support: list[Evidence]
    artifacts: list[Artifact]
    metrics: Metrics
    quality: PersonaQuality


class Situation(ContractModel):
    state: str | None
    emotion: str | None
    barrier: str | None


class ContextEvidence(ContractModel):
    context_id: str
    context_name: str
    action: str
    situation: Situation
    situation_origin: str
    dominant_constraint: str | None
    keywords: list[str]
    metrics: ContextMetrics
    evidence: list[ContextEvidenceItem]
    counter_evidence: list[ContextEvidenceItem]
    rare_evidence: list[RareEvidence]
    flags: list[str]


class PersonaBlock(ContractModel):
    persona_evidence: PersonaEvidence
    context_evidence: list[ContextEvidence]


class Package(ContractModel):
    schema_: str = Field(alias='schema')
    version: str
    params: dict
    personas: list[PersonaBlock]


class PackageMissing(FileNotFoundError):
    """The requested version has no Evidence Package."""


class EvidenceRef(Evidence):
    context_id: str | None
    role: str
    verified: bool
    field: str | None


def load_package(sid: str, version: str) -> Package:
    path = version_dir(sid, version) / 'evidence' / 'package.json'
    try:
        raw = path.read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise PackageMissing(f'Evidence Package missing: {sid}/{version}') from exc
    validated = EvidencePackage.model_validate_json(raw)
    package = Package.model_validate(validated.model_dump(by_alias=True))
    # Generation metadata belongs to the version session, not the wire package.
    session = read_json(version_dir(sid, version) / 'session.json') or {}
    package.run = session.get('evidence', {}).get('run')
    return package


def evidence_index(block: PersonaBlock) -> dict[str, EvidenceRef]:
    refs = {}

    def add(items, context_id, role):
        for item in items:
            data = item.model_dump()
            data.update(context_id=context_id, role=role, verified=item.quote.verified if item.quote else False,
                        field=item.quote.field if item.quote else None)
            refs[f'E{len(refs) + 1}'] = EvidenceRef.model_validate(data)

    add(block.persona_evidence.desire_support, None, 'support')
    for context in block.context_evidence:
        for name, role in (('evidence', 'support'), ('counter_evidence', 'counter'), ('rare_evidence', 'rare')):
            add(getattr(context, name), context.context_id, role)
    return refs
