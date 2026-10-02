"""Pure epistemic grading and trace construction (design 5.3, D-213)."""
from typing import Literal

from app.persona.package import EvidenceRef
from app.persona.params import INFERRED_FIELDS, OBSERVED_FIELDS, TRACE_MIN

Grade = Literal['observed', 'inferred', 'speculated']
_DOWNGRADE: dict[Grade, Grade] = {
    'observed': 'inferred', 'inferred': 'speculated', 'speculated': 'speculated',
}
_ALWAYS_SPECULATED = ('intent', 'persona_profile')


def _valid_cites(cites: list[str], refs: dict[str, EvidenceRef]) -> bool:
    return bool(cites) and all(cite in refs for cite in cites)


def grade_field(field: str, cites: list[str], refs: dict[str, EvidenceRef]) -> Grade:
    """Unknown fields or any dangling citation conservatively remain speculation.

    Valid citations need not be verified to support inference. A verified quote
    promotes only the observation-capable fields; intent/profile never promote.
    """
    if field in _ALWAYS_SPECULATED or not _valid_cites(cites, refs):
        return 'speculated'
    if field in OBSERVED_FIELDS:
        return 'observed' if any(refs[cite].verified for cite in cites) else 'inferred'
    if field in INFERRED_FIELDS:
        return 'inferred'
    return 'speculated'


def _populated(fields: dict) -> dict:
    return {name: value for name, value in fields.items()
            if isinstance(value, dict) and value.get('text') is not None}


def traceable_support(fields: dict[str, dict], refs: dict[str, EvidenceRef]) -> float:
    """Fraction of non-null cells with nonempty, entirely resolvable citations.

    Empty/all-null Contexts have support zero. Duplicate citations count once
    per field, and unverified quotes still constitute traceable evidence.
    """
    populated = _populated(fields)
    if not populated:
        return 0.0
    return sum(_valid_cites(value.get('cite', []), refs)
               for value in populated.values()) / len(populated)


def grade_card(card: dict, refs: dict[str, EvidenceRef]) -> dict:
    """Return grades, summary grades, Context support ratios, and trace rows.

    Input follows 5.2: contexts[{context_id, state, emotion, barrier, ...}]
    plus top-level summary cells. Output ``grades`` is {context_id: {field:
    grade}}; ``summary`` grades top-level cells without a Context downgrade.
    Null cells are omitted. Inputs are never changed.

    Each trace row links {context_id, field, evidence_id} to a detached
    ``evidence`` snapshot in the Evidence Package format, including original
    quote, verification, role, and source Context. Summary context_id is None.
    Resolvable citations are traced even if another citation is dangling.
    """
    result = {'grades': {}, 'summary': {}, 'traceable_support': {}, 'trace': []}

    def grade_fields(fields, context_id, downgrade=False):
        grades = {}
        for field, value in _populated(fields).items():
            cites = value.get('cite', [])
            grade = grade_field(field, cites, refs)
            grades[field] = _DOWNGRADE[grade] if downgrade else grade
            for cite in dict.fromkeys(cites):
                if cite in refs:
                    result['trace'].append(dict(context_id=context_id, field=field,
                        evidence_id=cite, evidence=refs[cite].model_dump()))
        return grades

    for context in card.get('contexts', []):
        context_id = context['context_id']
        fields = {name: value for name, value in context.items() if name != 'context_id'}
        support = traceable_support(fields, refs)
        result['traceable_support'][context_id] = support
        result['grades'][context_id] = grade_fields(fields, context_id, support < TRACE_MIN)

    summary = {name: value for name, value in card.items() if name != 'contexts'}
    # Concepts use a plain string for persona_profile (design 5.7).
    for name in _ALWAYS_SPECULATED:
        if summary.get(name) is not None and not isinstance(summary[name], dict):
            summary[name] = {'text': summary[name]}
    result['summary'] = grade_fields(summary, None)
    return result
