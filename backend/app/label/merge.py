"""Deterministic dual-vote merge."""
from typing import Literal

from app.label import rule
from app.label.gpt import GptVote
from app.label.jev import JevVote
from app.label.schema import Probability, Tags


class MergedLabel(Tags):
    evidence_level: Literal['core', 'supporting', 'non']
    confidence: Probability
    disagree: list[str]
    grade_mismatch: bool


def merge(jev: JevVote, gpt: GptVote) -> MergedLabel:
    jev_tags = {name: int(jev.probs[name] >= .5) for name in rule.GRADE_FIELDS}
    gpt_tags = dict(anchor=gpt.anchor, situation=gpt.situation, **gpt.sem)
    disagree = [name for name in rule.GRADE_FIELDS if jev_tags[name] != gpt_tags[name]]
    matches = len(rule.GRADE_FIELDS) - len(disagree)
    certainty = min(max(jev.probs[name], 1 - jev.probs[name]) for name in rule.GRADE_FIELDS)
    reason = max(jev.reason_probs, key=jev.reason_probs.get)
    reason = None if reason == 'not_non' else reason
    if reason != gpt.reason_code:
        disagree.append('reason_code')
    level = rule.grade(jev_tags)
    # Agreement and the Jev tie-break both yield the Jev binary value.
    return MergedLabel(anchor=bool(jev_tags['anchor']),
                       sem={name: jev_tags[name] for name in rule.SEM},
                       situation=bool(jev_tags['situation']), reason_code=reason,
                       signal=gpt.signal, evidence_level=level,
                       confidence=matches / 8 * certainty, disagree=disagree,
                       grade_mismatch=level != rule.grade(gpt_tags))
