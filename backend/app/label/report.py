"""Label-only stage-five report projection; exporting belongs to T13."""
from collections import Counter
import json

from app.label import rule
from app.label.overview import overview, session, labels_for


def label_part(sid, version=None) -> dict:
    view = overview(sid, version, sync=False)
    if view.get('legacy'):
        return view
    result = {key: view[key] for key in ('mode', 'selfConsistency', 'labelerAccuracy',
        'levelDistribution', 'accepted', 'escalated', 'mismatchRate', 'audit')}
    total = view['total']
    result['levelDistribution'] = {key: n / total if total else 0 for key, n in view['levelDistribution'].items()}
    counts = {name: Counter() for name in rule.GRADE_FIELDS}
    paired = agreed = 0
    with labels_for(sid, session(sid, version))._db() as db:
        for row in db.execute('SELECT votes_json FROM final'):
            votes = json.loads(row[0])
            if not votes.get('jev') or not votes.get('gpt'):
                continue
            left = {name: int(votes['jev']['probs'][name] >= .5) for name in rule.GRADE_FIELDS}
            gpt = votes['gpt']
            right = dict(anchor=int(gpt['anchor']), situation=int(gpt['situation']), **gpt['sem'])
            paired += 1
            agreed += rule.grade(left) == rule.grade(right)
            for name in counts:
                counts[name][left[name], right[name]] += 1
    result['agreementRate'] = agreed / paired if paired else None
    result['kappaLabelers'] = {}
    for name, pairs in counts.items():
        n = sum(pairs.values())
        observed = sum(pairs[v, v] for v in (0, 1)) / n if n else 0
        expected = sum(sum(pairs[v, b] for b in (0, 1)) * sum(pairs[a, v] for a in (0, 1))
                       for v in (0, 1)) / (n * n) if n else 1
        result['kappaLabelers'][name] = (observed - expected) / (1 - expected) if expected < 1 else None
    return result
