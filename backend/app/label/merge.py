"""Deterministic dual-vote merge and incremental materialization of final labels."""
import json
from typing import Literal

from app.label import questions, rule
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


def rebuild_final(store, jev_cache, gpt_cache):
    """Merge newly paired done votes, returning the number materialized.

    Cache files are attached read-only. No provider calls or cache writes occur.
    Only a rule/question version change invalidates existing automatic results;
    human results and the submission history belong to the review workflow.
    All final/queue changes commit together or roll back together.
    """
    with store._db() as db:
        db.execute('ATTACH DATABASE ? AS jev', (jev_cache.path.resolve().as_uri() + '?mode=ro',))
        db.execute('ATTACH DATABASE ? AS gpt', (gpt_cache.path.resolve().as_uri() + '?mode=ro',))
        changed = db.execute('''SELECT 1 FROM final WHERE source != 'human'
            AND (rule_version != ? OR questions_version != ?) LIMIT 1''',
            (rule.RULE_VERSION, questions.QVER)).fetchone()
        if changed:
            db.execute("DELETE FROM final WHERE source != 'human'")
            db.execute("DELETE FROM queue WHERE reason='grade_mismatch' AND status='open'")

        # A terminal failure goes to review even while the other vote is pending.
        # INSERT OR IGNORE retains completed/skipped review state on repeat calls.
        db.execute('''INSERT OR IGNORE INTO queue(doc_id, reason, priority, status)
            SELECT failed.doc_id, 'labeler_failed', 0, 'open' FROM (
                SELECT doc_id FROM jev.votes WHERE status='bad'
                UNION SELECT doc_id FROM gpt.votes WHERE status='bad'
            ) AS failed WHERE NOT EXISTS (
                SELECT 1 FROM final f WHERE f.doc_id=failed.doc_id AND f.source='human'
            )''')

        candidates = db.execute('''SELECT j.doc_id, j.payload_json AS jev_json,
                g.payload_json AS gpt_json
            FROM jev.votes j JOIN gpt.votes g ON g.doc_id=j.doc_id
            LEFT JOIN final f ON f.doc_id=j.doc_id
            WHERE j.status='done' AND g.status='done' AND f.doc_id IS NULL''')
        count = 0
        for row in candidates:
            jev = JevVote.model_validate_json(row['jev_json'])
            gpt = GptVote.model_validate_json(row['gpt_json'])
            merged = merge(jev, gpt)
            route = 'escalated:grade_mismatch' if merged.grade_mismatch else 'accepted'
            tags = Tags.model_validate(merged.model_dump())
            db.execute('''INSERT INTO final
                (doc_id, level, confidence, source, route, tags_json, reason_code,
                 signal, rule_version, questions_version, votes_json, disagree_json,
                 grade_mismatch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (row['doc_id'], merged.evidence_level, merged.confidence, 'agreed', route,
                 tags.model_dump_json(), merged.reason_code, merged.signal,
                 rule.RULE_VERSION, questions.QVER,
                 json.dumps({'jev': jev.model_dump(), 'gpt': gpt.model_dump()}),
                 json.dumps(merged.disagree), int(merged.grade_mismatch)))
            if merged.grade_mismatch:
                db.execute('''INSERT OR IGNORE INTO queue(doc_id, reason, priority, status)
                    VALUES (?, 'grade_mismatch', ?, 'open')''',
                    (row['doc_id'], 1 + merged.confidence))
            count += 1
        return count
