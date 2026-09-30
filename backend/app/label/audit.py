"""Deterministic audit rounds, human corrections, and agreement statistics.

Metrics have ``n``, ``accuracy`` and ``kappa``; undefined values are None.
Round summaries expose ``fields`` and ``grade``. Provider summaries are keyed
by ``jev``/``gpt``. All grades come from rule.grade.

Call apply_audit_overrides after LabelStore.submit(..., mode='audit'). The
statistics entry points also reconcile durable submissions on resume. Original
labels/votes are snapshotted at sampling so corrections cannot inflate κ_AI.
"""
from collections import Counter
import json
import math
import random
import time

from app.config import settings
from app.label import rule
from app.label.schema import Tags

_SEED = 42


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS audit_snapshot (
        round INTEGER NOT NULL, doc_id TEXT NOT NULL, tags_json TEXT NOT NULL,
        level TEXT NOT NULL, votes_json TEXT NOT NULL, human_floor INTEGER NOT NULL,
        PRIMARY KEY(round, doc_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS audit_reissue (
        round INTEGER NOT NULL, doc_id TEXT NOT NULL,
        PRIMARY KEY(round, doc_id))''')


def _flat(tags):
    return dict(anchor=int(tags['anchor']), situation=int(tags['situation']), **tags['sem'])


def _truths(db, round=None):
    """Latest audit per sampled item, bounded by its next sampling watermark.

    human has no round column: a submission belongs to the most recent sampling
    of that document. Reissues and escalations never become audit ground truth.
    """
    return db.execute('''SELECT s.*, h.rowid AS human_id, h.tags_json AS truth_json
        FROM audit_snapshot s JOIN human h ON h.rowid=(
            SELECT MAX(h2.rowid) FROM human h2
            WHERE h2.doc_id=s.doc_id AND h2.mode='audit'
              AND h2.rowid>s.human_floor
              AND h2.rowid<=COALESCE((
                  SELECT MIN(s2.human_floor) FROM audit_snapshot s2
                  WHERE s2.doc_id=s.doc_id AND s2.round>s.round
              ), 9223372036854775807)
        ) WHERE (? IS NULL OR s.round=?) ORDER BY h.rowid''', (round, round)).fetchall()


def maybe_new_round(store, accepted_count) -> int | None:
    """Create one due round at 1,000 + k*10,000 accepted documents.

    Repeated calls catch up crossed thresholds one at a time. Selection and
    snapshots commit atomically; a restart cannot duplicate an existing round.
    Reissues are extra items and excluded from the fresh random sample.
    """
    with store._db() as db:
        _schema(db)
        previous = db.execute('SELECT COALESCE(MAX(round), 0) FROM audit_set').fetchone()[0]
        if accepted_count < settings.audit_first + previous * settings.audit_every:
            return None
        round = previous + 1
        rng = random.Random(_SEED + round)
        prior = sorted({row['doc_id'] for row in _truths(db) if row['round'] < round})
        reissues = rng.sample(prior, min(settings.audit_reissue, len(prior)))
        excluded = set(reissues)
        # Reservoir sampling bounds memory independently of the accepted corpus.
        sample = []
        seen = 0
        for row in db.execute("SELECT * FROM final WHERE route='accepted' ORDER BY doc_id"):
            if row['doc_id'] in excluded:
                continue
            seen += 1
            if len(sample) < settings.audit_size:
                sample.append(row)
            else:
                index = rng.randrange(seen)
                if index < settings.audit_size:
                    sample[index] = row
        if not sample:
            return None
        picked_at = time.time()
        floor = db.execute('SELECT COALESCE(MAX(rowid), 0) FROM human').fetchone()[0]
        db.executemany('INSERT INTO audit_set VALUES (?,?,?)',
                       ((round, r['doc_id'], picked_at) for r in sample))
        db.executemany('INSERT INTO audit_snapshot VALUES (?,?,?,?,?,?)',
                       ((round, r['doc_id'], r['tags_json'], r['level'], r['votes_json'], floor)
                        for r in sample))
        db.executemany('INSERT INTO audit_reissue VALUES (?,?)',
                       ((round, doc_id) for doc_id in reissues))
        return round


def reissue_items(store, round) -> list[str]:
    """Return the persisted blind reissue IDs (at most two; none initially)."""
    with store._db() as db:
        _schema(db)
        return [r[0] for r in db.execute(
            'SELECT doc_id FROM audit_reissue WHERE round=? ORDER BY doc_id', (round,))]


def _metric(pairs):
    n = len(pairs)
    if not n:
        return dict(n=0, accuracy=None, kappa=None)
    accuracy = sum(a == b for a, b in pairs) / n
    left = Counter(a for a, _ in pairs)
    right = Counter(b for _, b in pairs)
    expected = sum(count * right[value] for value, count in left.items()) / (n * n)
    kappa = (accuracy - expected) / (1 - expected) if expected < 1 else None
    return dict(n=n, accuracy=accuracy, kappa=kappa)


def _summary(pairs, grade_pairs=None):
    if grade_pairs is None:
        grade_pairs = [(rule.grade(a), rule.grade(b)) for a, b in pairs]
    return dict(n=len(pairs), fields={
        name: _metric([(a[name], b[name]) for a, b in pairs]) for name in rule.GRADE_FIELDS
    }, grade=_metric(grade_pairs))


def _apply_overrides(db, truths):
    latest = {row['doc_id']: row for row in truths}
    changed = 0
    for doc_id, row in latest.items():
        # Do not overwrite a later, explicit escalation judgment.
        later = db.execute("SELECT 1 FROM human WHERE doc_id=? AND mode='escalate' AND rowid>? LIMIT 1",
                           (doc_id, row['human_id'])).fetchone()
        final = db.execute('SELECT tags_json FROM final WHERE doc_id=?', (doc_id,)).fetchone()
        if later or final is None:
            continue
        truth = Tags.model_validate_json(row['truth_json'])
        if json.loads(final['tags_json']) == truth.model_dump():
            continue
        db.execute('''UPDATE final SET tags_json=?, level=?, source='human',
            route='audited', reason_code=?, signal=?, rule_version=? WHERE doc_id=?''',
                   (truth.model_dump_json(), rule.grade(_flat(truth.model_dump())),
                    truth.reason_code, truth.signal, rule.RULE_VERSION, doc_id))
        changed += 1
    return changed


def apply_audit_overrides(store) -> int:
    """Reconcile saved audit answers into final; return changed document count.

    Safe to call after every submit or after a restart. Keeps original confidence,
    provider votes, and disagreement metadata for traceability.
    """
    with store._db() as db:
        _schema(db)
        return _apply_overrides(db, _truths(db))


def kappa_ai(store, round) -> dict:
    """Compare the sampled final AI labels with that round's independent answers."""
    with store._db() as db:
        _schema(db)
        truths = _truths(db)
        selected = [r for r in truths if r['round'] == round]
        pairs = [(_flat(json.loads(r['tags_json'])), _flat(json.loads(r['truth_json'])))
                 for r in selected]
        grades = [(r['level'], rule.grade(truth)) for r, (_, truth) in zip(selected, pairs)]
        _apply_overrides(db, truths)
        return _summary(pairs, grades)


def labeler_accuracy(store) -> dict:
    """Cumulative, unique-document accuracy/κ against latest audit truth.

    final.votes_json is the durable copy of VoteCache's done payloads populated
    by rebuild_final; no provider calls or guessed cache paths are necessary.
    Missing provider payloads are omitted from that provider's sample count.
    """
    with store._db() as db:
        _schema(db)
        truths = _truths(db)
        latest = {row['doc_id']: row for row in truths}
        pairs = {'jev': [], 'gpt': []}
        for row in latest.values():
            truth = _flat(json.loads(row['truth_json']))
            votes = json.loads(row['votes_json'])
            if votes.get('jev'):
                probs = votes['jev']['probs']
                pairs['jev'].append(({name: int(probs[name] >= .5) for name in rule.GRADE_FIELDS}, truth))
            if votes.get('gpt'):
                pairs['gpt'].append((_flat(votes['gpt']), truth))
        _apply_overrides(db, truths)
        return {name: _summary(items) for name, items in pairs.items()}


def self_consistency(store) -> dict:
    """Cumulative exact-answer agreement with the same person's initial audit.

    n counts reissue answers, not documents. Exact agreement includes reason and
    signal; field/grade summaries additionally expose where answers changed.
    """
    with store._db() as db:
        rows = db.execute('''SELECT h.rowid, h.* FROM human h
            WHERE EXISTS (SELECT 1 FROM audit_set s WHERE s.doc_id=h.doc_id
                          AND s.picked_at<=h.submitted_at)
            ORDER BY h.rowid''').fetchall()
    baselines = {}
    pairs = []
    exact = []
    for row in rows:
        key = (row['doc_id'], row['labeler'])
        tags = json.loads(row['tags_json'])
        if row['mode'] == 'audit':
            baselines.setdefault(key, tags)
        elif row['mode'] == 'reissue' and key in baselines:
            baseline = baselines[key]
            exact.append((baseline, tags))
            pairs.append((_flat(baseline), _flat(tags)))
    result = _summary(pairs)
    result['accuracy'] = sum(a == b for a, b in exact) / len(exact) if exact else None
    return result


def definition_signal(history) -> dict:
    """Input: chronological kappa_ai summaries; require three valid latest rounds."""
    values = [item['grade']['kappa'] for item in history[-3:]]
    valid = len(values) == 3 and all(value is not None and math.isfinite(value) for value in values)
    needed = bool(valid and values[0] > values[1] > values[2] and values[2] < settings.kappa_floor)
    return dict(needed=needed, reason=(
        '최근 감사에서 일치도가 두 번 연속 떨어졌습니다. 태그 정의를 확인하세요.' if needed else None))
