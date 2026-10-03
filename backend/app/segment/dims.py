"""Observed Core dimensions, shared extraction cache and sample-only statistics.

``codes`` and ``combos`` are lists of SegmentStore row dictionaries. Public
``combo_rarity`` accepts raw phrases (including lazy extractions) and maps them
against that fixed codebook without changing either table.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from fnmatch import fnmatchcase
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.base import Attachment, LLMTask
from app.model.infer import prepared_root
from app.segment import params
from app.vectors.embedder import get_embedder

DIMENSIONS = ('environment', 'internal_state', 'task_goal', 'activity_response', 'resource_constraint')
PAIRS = {'tg_rc': ('task_goal', 'resource_constraint'), 'env_ar': ('environment', 'activity_response')}
PROMPT_PATH = Path(__file__).with_name('prompts') / 'dims.v1.md'


class DimsItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    doc_id: str
    environment: str | None
    internal_state: str | None
    task_goal: str | None
    activity_response: str | None
    resource_constraint: str | None


class DimsOut(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    items: list[DimsItem]


def _vectors(phrases):
    values = np.asarray(get_embedder().embed(phrases), dtype=np.float64)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return np.divide(values, norms, out=np.zeros_like(values), where=np.isfinite(norms) & (norms > 0))


def normalize_dims(dims_by_doc):
    """Greedily join the first matching representative, frequency then lexical order.

    Representatives never move; the most frequent phrase seeds each group.
    Each dimension has an independent code space. Zero embeddings never merge.
    """
    coded = {doc_id: dict.fromkeys(DIMENSIONS) for doc_id in dims_by_doc}
    codes = []
    for dim in DIMENSIONS:
        counts = Counter(row[dim] for row in dims_by_doc.values() if row.get(dim))
        phrases = sorted(counts, key=lambda phrase: (-counts[phrase], phrase))
        if not phrases:
            continue
        vectors = _vectors(phrases)
        representatives, rows, lookup = [], [], {}
        for i, phrase in enumerate(phrases):
            match = next((j for j, index in enumerate(representatives)
                          if float(vectors[i] @ vectors[index]) >= params.CODE_COS), None)
            if match is None:
                match = len(rows)
                representatives.append(i)
                rows.append(dict(dim=dim, code=f'{dim}:{match}', label=phrase, count=0))
            rows[match]['count'] += counts[phrase]
            lookup[phrase] = rows[match]['code']
        codes.extend(rows)
        for doc_id, row in dims_by_doc.items():
            coded[doc_id][dim] = lookup.get(row.get(dim))
    return coded, codes


def count_combos(coded):
    rows = []
    for pair, (a, b) in PAIRS.items():
        counts = Counter((row[a], row[b]) for row in coded.values() if row.get(a) and row.get(b))
        rows.extend(dict(pair=pair, a_code=x, b_code=y, count=count)
                    for (x, y), count in sorted(counts.items()))
    return rows


def _map_codes(dims_by_doc, codes):
    coded = {doc_id: dict.fromkeys(DIMENSIONS) for doc_id in dims_by_doc}
    for dim in DIMENSIONS:
        rows = [row for row in codes if row['dim'] == dim]
        exact = {row['label']: row['code'] for row in rows}
        phrases = sorted({row[dim] for row in dims_by_doc.values() if row.get(dim)} - exact.keys())
        lookup = dict(exact)
        if phrases and rows:
            vectors = _vectors([row['label'] for row in rows] + phrases)
            for i, phrase in enumerate(phrases, len(rows)):
                match = next((j for j in range(len(rows))
                              if float(vectors[i] @ vectors[j]) >= params.CODE_COS), None)
                if match is not None:
                    lookup[phrase] = rows[match]['code']
        for doc_id, row in dims_by_doc.items():
            phrase = row.get(dim)
            # A tuple sentinel cannot collide with any stored string code.
            coded[doc_id][dim] = lookup.get(phrase, ('unseen', phrase)) if phrase else None
    return coded


def _rarity(coded, combos):
    """Freeze min/max to observed sample pairs, then clip lazy scores to [0, 1].

    -log((count + 1) / N) = log(N) - log(count + 1): N cancels in
    min-max normalization, so no sample-size metadata is needed at stage seven.
    Missing pairs contribute zero. With constant sample frequency, observed
    pairs score zero and unseen pairs score one (no observed spread).
    """
    result = dict.fromkeys(coded, 0.0)
    for pair, (a, b) in PAIRS.items():
        counts = {(row['a_code'], row['b_code']): row['count'] for row in combos if row['pair'] == pair}
        values = [-math.log1p(count) for count in counts.values()]
        low, high = (min(values), max(values)) if values else (0.0, 0.0)
        for doc_id, row in coded.items():
            if row.get(a) is None or row.get(b) is None:
                continue
            count = counts.get((row[a], row[b]), 0)
            score = ((-math.log1p(count) - low) / (high - low)
                     if high > low else float(count == 0))
            result[doc_id] = max(result[doc_id], min(1.0, max(0.0, score)))
    return result


def combo_rarity(dims_by_doc, codes, combos) -> dict[str, float]:
    """Score raw sample/lazy phrases using only the supplied fixed sample tables."""
    return _rarity(_map_codes(dims_by_doc, codes), combos)


def _source_docs(sid, session, wanted):
    # Stream preparation shards: do not load vectors or every document into RAM.
    result = {}
    for path in sorted((prepared_root(sid, session) / 'docs').glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    doc = json.loads(line)
                    if doc['doc_id'] in wanted:
                        result[doc['doc_id']] = doc
    ref = session.get('training', {}).get('exportRef', '')
    base = (Path(settings.local_data_dir) / 'classified' / sid).resolve()
    export = (Path(settings.local_data_dir) / ref).resolve()
    if not export.is_relative_to(base) or export.name != 'relevant.jsonl':
        raise ValueError('Invalid stage-five export reference')
    with export.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                doc = json.loads(line)
                if doc['doc_id'] in result:
                    # Preserve explicit null: it marks an unavailable model head.
                    result[doc['doc_id']]['tagProbs'] = doc.get('tagProbs', {})
                    result[doc['doc_id']]['sem'] = (doc.get('sem') or {})
    return result


def _model():
    backend = settings.llm_backend
    for pattern, override in settings.llm_backend_overrides.items():
        if fnmatchcase('segment.dims', pattern):
            backend = override
            break
    return {'openai_api': settings.openai_model, 'claude_api': settings.claude_model,
            'codex_exec': settings.codex_profile}.get(backend, backend)


def _clean(row):
    values, too_long = {}, 0
    for dim in DIMENSIONS:
        phrase = row[dim]
        if phrase is not None:
            phrase = phrase.strip()
            too_long += len(phrase) > params.DIMS_PHRASE_MAX
            phrase = phrase if 0 < len(phrase) <= params.DIMS_PHRASE_MAX else None
        values[dim] = phrase
    return values, too_long


def _write_rows(cache, rows):
    with cache:
        cache.executemany('INSERT OR REPLACE INTO dims VALUES (?, ?, ?, ?, ?)', rows)


def write_cache(path, values, *, origin, model):
    """Share the sample cache format/writer with lazy stage-seven extraction."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as cache:
        cache.execute('CREATE TABLE IF NOT EXISTS dims (doc_id TEXT PRIMARY KEY, context_dims TEXT NOT NULL, origin TEXT NOT NULL, model TEXT NOT NULL, phrase_too_long INTEGER NOT NULL DEFAULT 0)')
        _write_rows(cache, [(doc_id, json.dumps(row, ensure_ascii=False), origin, model, too_long)
                            for doc_id, (row, too_long) in values.items()])


def _extract(sid, batches, docs, cache, instructions):
    failed = []
    ready = []
    for batch in batches:
        if any(doc_id not in docs for doc_id in batch):
            failed.extend(batch)
        else:
            ready.append(batch)

    def call(batch):
        attachments = []
        for doc_id in batch:
            doc = docs[doc_id]
            text = dict(title=doc.get('title', ''), body=(doc.get('body') or '')[:2000],
                        comments=[{'idx': i, 'text': ((c.get('text') or '') if isinstance(c, dict) else str(c))[:300]}
                                  for i, c in enumerate(doc.get('comments', [])[:10])])
            attachments.append(Attachment(title=doc_id, body=json.dumps(text, ensure_ascii=False)))
        task = LLMTask(task='segment.dims', sid=sid, instructions=instructions,
                       attachments=attachments, output_schema=DimsOut)
        for _ in range(2):
            result = registry.run_task(task)
            if not result.ok:
                continue
            items = result.data.items
            ids = [row.doc_id for row in items]
            if len(ids) != len(batch) or set(ids) != set(batch):
                continue
            # Cache only after the entire response passes one-to-one validation.
            rows = []
            for row in items:
                values, too_long = _clean(row.model_dump())
                rows.append((row.doc_id, json.dumps(values, ensure_ascii=False), 'sample', _model(), too_long))
            return rows
        return None

    # Provider calls run concurrently; the SQLite cache is written by this thread only.
    with ThreadPoolExecutor(max_workers=max(1, min(settings.segment_concurrency, len(ready) or 1))) as pool:
        for batch, rows in zip(ready, pool.map(call, ready)):
            if rows is None:
                failed.extend(batch)
            else:
                _write_rows(cache, rows)
    return failed


def _summary(ids, raw, coded, codes, docs):
    successful = [doc_id for doc_id in ids if doc_id in raw]
    summary = {}
    for dim in DIMENSIONS:
        counts = Counter(coded[doc_id][dim] for doc_id in successful if coded[doc_id][dim])
        summary[dim] = sorted([dict(code=row['code'], label=row['label'], count=counts[row['code']])
                               for row in codes if row['dim'] == dim and counts[row['code']]],
                              key=lambda row: (-row['count'], row['label']))[:3]
    constraints = summary['resource_constraint']
    empty = sum(not raw[i]['task_goal'] or not raw[i]['resource_constraint'] for i in successful)
    mismatch = unknown = 0
    for i in successful:
        doc = docs.get(i, {})
        probs = (doc.get('tagProbs') or {})
        # Original semantic labels cannot stand in for unavailable probabilities.
        act = None if doc.get('tagProbs', {}) is None else probs.get(
            'act', (probs.get('sem') or {}).get('act', (doc.get('sem') or {}).get('act')))
        if act is None:
            unknown += 1
            continue
        mismatch += (float(act or 0) >= .5) != bool(raw[i]['activity_response'])
    return dict(sampled=len(ids), extracted=len(successful), dominant_constraint=constraints[0]['label'] if constraints else None,
                dims_summary=summary, empty_goal_or_constraint=empty / len(successful) if successful else 0.0,
                act_mismatch=mismatch, act_unknown=unknown)


def extract_sample(sid, version, store) -> dict:
    """Persist sample code tables, rarity and summaries; return stage_6.dims.

    Ratios use successful extractions only. Failed rows remain absent and are
    listed in dims_failed, never treated as five observed-null dimensions.
    """
    session = sessions.read_json(version_dir(sid, version) / 'session.json')
    prep_key = session['prep']['derivedRef']['prepKey']
    prompt = PROMPT_PATH.read_bytes()
    pver = hashlib.sha256(prompt).hexdigest()
    directory = Path(settings.local_data_dir) / 'llmcache' / sid / prep_key
    prepared_root(sid, session)  # Validate the preparation reference before writing a cache.
    directory.mkdir(parents=True, exist_ok=True)
    contexts = store.contexts()
    samples = {}
    with store._db() as db:
        for context in contexts:
            context_id = context['context_id']
            samples[context_id] = [row['doc_id'] for row in db.execute(
                "SELECT doc_id FROM docs WHERE context_id=? AND evidence_level='core' "
                'ORDER BY theta DESC, doc_id LIMIT ?', (context_id, params.DIMS_PER_CONTEXT))]
    ids = [doc_id for group in samples.values() for doc_id in group]
    docs = _source_docs(sid, session, set(ids)) if ids else {}
    raw, too_long = {}, 0
    with closing(sqlite3.connect(directory / f'dims-{pver}.sqlite')) as cache:
        cache.execute('CREATE TABLE IF NOT EXISTS dims (doc_id TEXT PRIMARY KEY, context_dims TEXT NOT NULL, origin TEXT NOT NULL, model TEXT NOT NULL, phrase_too_long INTEGER NOT NULL DEFAULT 0)')
        for doc_id in ids:
            row = cache.execute('SELECT context_dims, phrase_too_long FROM dims WHERE doc_id=?', (doc_id,)).fetchone()
            if row:
                raw[doc_id] = json.loads(row[0])
                too_long += row[1]
        pending = [doc_id for doc_id in ids if doc_id not in raw]
        batches = [pending[i:i + params.DIMS_BATCH] for i in range(0, len(pending), params.DIMS_BATCH)]
        failed = _extract(sid, batches, docs, cache, prompt.decode('utf-8'))
        for doc_id in pending:
            row = cache.execute('SELECT context_dims, phrase_too_long FROM dims WHERE doc_id=?', (doc_id,)).fetchone()
            if row:
                raw[doc_id] = json.loads(row[0])
                too_long += row[1]
    coded, codes = normalize_dims(raw)
    combos = count_combos(coded)
    rarity = _rarity(coded, combos)
    summaries = {context: _summary(group, raw, coded, codes, docs) for context, group in samples.items()}
    total = _summary(ids, raw, coded, codes, docs)
    with store._db(write=True) as db:
        db.execute('DELETE FROM codes')
        db.execute('DELETE FROM combos')
        db.executemany('INSERT INTO codes VALUES (:dim, :code, :label, :count)', codes)
        db.executemany('INSERT INTO combos VALUES (:pair, :a_code, :b_code, :count)', combos)
        db.execute('UPDATE docs SET combo_rarity=NULL')
        db.executemany('UPDATE docs SET combo_rarity=? WHERE doc_id=?', [(v, k) for k, v in rarity.items()])
        for context, summary in summaries.items():
            db.execute('UPDATE contexts SET dominant_constraint=?, dims_summary_json=? WHERE context_id=?',
                       (summary['dominant_constraint'], json.dumps(summary['dims_summary'], ensure_ascii=False), context))
    return dict(sampled=len(ids), extracted=len(raw), dims_failed=failed, phrase_too_long=too_long,
                empty_goal_or_constraint=total['empty_goal_or_constraint'], act_mismatch=total['act_mismatch'], act_unknown=total['act_unknown'],
                codes={dim: [row for row in codes if row['dim'] == dim] for dim in DIMENSIONS},
                contexts=summaries, coverage={doc_id: dict(filled=sum(row[d] is not None for d in DIMENSIONS),
                    has_goal=row['task_goal'] is not None, has_constraint=row['resource_constraint'] is not None)
                    for doc_id, row in raw.items()})
