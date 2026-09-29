"""P1 review aggregates, including shared keyword discoveries."""
from contextlib import closing
from dataclasses import dataclass
from app.crawl.queue import CrawlQueue

GATE_LOW_COUNT = 10
GATE_LOW_UNIQUE = 0.2


@dataclass
class GateRow:
    kw: str
    axis: str
    sub: str
    per_source: dict
    listed: int
    after_filter: int
    unique_ratio: float
    badges: list[str]


def matrix(queue):
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        db.execute('BEGIN')
        rows = db.execute('''SELECT h.kw,h.source,count(*) listed,
            sum(u.status='filtered') filtered,sum(u.status='excluded') excluded,
            sum(u.status='done' AND u.fetch_level='full') AS "full",
            sum(u.status='done' AND u.fetch_level='snippet') snippet,
            sum(u.status='done' AND u.access='restricted') restricted,
            sum(h.kw=(SELECT h2.kw FROM url_hits h2
                WHERE h2.url_norm=h.url_norm AND h2.source=h.source
                ORDER BY h2.kw_order,h2.kw LIMIT 1)) AS "unique"
            FROM url_hits h JOIN urls u USING(url_norm,source) GROUP BY h.kw,h.source''').fetchall()
        result = {}
        for row in db.execute('SELECT DISTINCT kw,source FROM list_tasks'):
            result.setdefault(row['kw'], {})[row['source']] = dict.fromkeys(
                ['listed', 'filtered', 'excluded', 'full', 'snippet', 'restricted', 'unique'], 0)
        for row in rows:
            result.setdefault(row['kw'], {})[row['source']] = {k: row[k] for k in row.keys() if k not in ('kw', 'source')}
        return result


def compute_gate(queue):
    cells = matrix(queue)
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        metadata = list(db.execute('SELECT * FROM keyword_meta ORDER BY kw_order,kw'))
    result = []
    for m in metadata:
        sources = {s: {k: v[k] for k in ('listed', 'filtered', 'unique')} for s, v in cells.get(m['kw'], {}).items()}
        listed = sum(v['listed'] for v in sources.values())
        after = listed - sum(v['filtered'] for v in sources.values())
        ratio = sum(v['unique'] for v in sources.values()) / listed if listed else 0
        badges = (['zero'] if listed == 0 else []) + (['low'] if after < GATE_LOW_COUNT else []) + (['low_unique'] if listed and ratio < GATE_LOW_UNIQUE else [])
        result.append(GateRow(m['kw'], m['kw_axis'], m['kw_sub'], sources, listed, after, ratio, badges))
    return sorted(result, key=lambda r: not bool(r.badges))


def estimate(queue, cfg):
    excluded = cfg.get('gateExclusions', [])
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        placeholders = ','.join('?' for _ in excluded) or "''"
        rows = db.execute(f'''SELECT u.source,count(*) FROM urls u WHERE u.status NOT IN ('filtered','excluded')
            AND EXISTS(SELECT 1 FROM url_hits h WHERE h.url_norm=u.url_norm AND h.source=u.source
            AND h.kw NOT IN ({placeholders})) GROUP BY u.source''', excluded).fetchall()
    return {'urls': sum(r[1] for r in rows), 'minutes': max((r[1] / cfg.get('perChannel', {}).get(r[0], {}).get('per_minute', 60) for r in rows), default=0)}
