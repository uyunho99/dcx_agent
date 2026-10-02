"""Deterministic stage-seven assembly; no search, embedding or LLM calls.

The worker persists ranked all-tab persona results in persona_support(kind=desire).
Its contexts.counts carries coverage_supplements, query_gen_fail, new_expansions,
rare_fallback, dpp_fill, lazy_dims, llm_calls and cache_hits. Assembly derives
observable distributions from the snapshot and adds escalation document IDs.
Callers own the session/run lock and writable-version checks, as for the stores.
"""
from collections import Counter
from itertools import combinations
import json
import math
import sqlite3

import numpy as np

from app.context import store as sessions
from app.context.versions import version_dir
from app.evidence import params, generation
from app.evidence.cache import TagCache, prompt_version, known_key
from app.evidence.package import EvidencePackage
from app.evidence.quotes import locate
from app.evidence.rerank import quality
from app.evidence.store import EvidenceStore
from app.known.models import read_known
from app.model.infer import prepared_root
from app.segment.stopwords import filter_words
from app.segment.store import SegmentStore
from app.vectors.store import VectorStore


def _documents(store):
    """SegmentStore's default limit is 100; metrics must include every document."""
    result, offset = [], 0
    while True:
        batch = store.docs(limit=1000, offset=offset)
        result.extend(batch)
        if len(batch) < 1000:
            return result
        offset += len(batch)


def context_polarity_mean(pool, tags):
    return _mean(tags[i].get('polarity') for i in {r['doc_id'] for r in pool}
                 if i in tags and tags[i].get('relevant'))


def counter_evidence(candidates, tags, *, context_mean):
    if context_mean is None:
        return []
    threshold = context_mean - params.COUNTER_POLARITY_GAP
    rows = [r for r in candidates if 'Counter' in (r.get('dims_hit') or [])
            and (t := tags.get(r['doc_id']) or {}).get('relevant')
            and t.get('polarity') is not None
            and t['polarity'] <= math.nextafter(threshold, math.inf)]
    return sorted(rows, key=lambda r: (-r['relevance'], r['doc_id']))[:params.COUNTER_TOP]


def _rare_candidates(candidates, tags, docs):
    rows = [r for r in candidates if r.get('band') == 'edge'
            and (t := tags.get(r['doc_id']) or {}).get('relevant')
            and (t.get('pain_point') or t.get('unmet_need'))]
    return sorted(rows, key=lambda r: (
        -quality(r['relevance'], r.get('combo_rarity', docs[r['doc_id']].get('combo_rarity'))), r['doc_id']))


def rare_evidence(candidates, tags, docs):
    return _rare_candidates(candidates, tags, docs)[:params.RARE_TOP]


def undifferentiated_candidate(rare_candidates, vectors):
    """Return the first deterministic mutually similar triple, not a graph chain."""
    units = {}
    for row in rare_candidates:
        doc_id = row['doc_id']
        if doc_id not in vectors:
            continue
        vector = np.asarray(vectors[doc_id], dtype=float)
        norm = np.linalg.norm(vector)
        if norm > 0 and np.isfinite(vector).all():
            units[doc_id] = vector / norm
    for group in combinations(units, params.UNDIFF_MIN):
        if all(float(units[a] @ units[b]) >= np.nextafter(params.UNDIFF_COSINE, -np.inf)
               for a, b in combinations(group, 2)):
            return list(group)
    return []


def append_context_flag(store_seg, context_id, flag, *, present=True):
    """Append under a writer lock without replacing confirmations or other flags."""
    with sqlite3.connect(store_seg.path, timeout=30) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT flags_json FROM contexts WHERE context_id=?', (context_id,)).fetchone()
        if row is None:
            raise ValueError(f'Unknown Context: {context_id}')
        flags = json.loads(row[0] or '[]')
        updated = [f for f in flags if f != flag] + ([flag] if present else [])
        if updated != flags:
            flags = updated
            db.execute('UPDATE contexts SET flags_json=? WHERE context_id=?',
                       (json.dumps(flags, ensure_ascii=False), context_id))


def desire_support(rows, tags):
    """Consume ranked persona-query all-tab results, retaining Known matches."""
    seen, result = set(), []
    for row in sorted(rows, key=lambda r: (r['rank'], r['doc_id'])):
        doc_id = row['doc_id']
        if row.get('kind') != 'desire' or doc_id in seen or not (tags.get(doc_id) or {}).get('relevant'):
            continue
        seen.add(doc_id)
        result.append(row)
        if len(result) == params.DESIRE_TOP:
            break
    return result


def artifacts(doc_ids, tags, bk):
    names = [''.join(name.lower().split()) for doc_id in dict.fromkeys(doc_ids)
             for name in (tags.get(doc_id) or {}).get('artifacts', [])]
    counts = Counter(filter_words(names, ''.join((bk or '').lower().split())))
    return [dict(name=name, mention_count=count)
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _mean(values):
    present = [float(v) for v in values if v is not None and math.isfinite(v)]
    return sum(present) / len(present) if present else None


def _raw_metrics(context, docs):
    assigned = [d for d in docs if d['context_id'] == context['context_id']]
    persona_count = sum(d['persona_id'] == context['persona_id'] for d in docs)
    theta = [d['theta'] for d in assigned if d.get('theta') is not None]
    sentiment = _mean(d.get('sentiment') for d in assigned)
    return dict(importance=sum(theta) / persona_count if theta and persona_count else None,
                satisfaction=(sentiment + 1) / 2 if sentiment is not None else None,
                doc_count=len(assigned), author_count=len({d['author_hash'] for d in assigned if d.get('author_hash')}))


def session_minmax(store_seg):
    """Observed session ranges; an empty range stays unavailable, a tie maps to 0."""
    docs = _documents(store_seg)
    rows = [_raw_metrics(c, docs) for c in store_seg.contexts()]
    return {key: (min(values), max(values)) if (values := [r[key] for r in rows if r[key] is not None])
            else (None, None) for key in ('importance', 'satisfaction')}


def _context_metrics(context, docs, ranges):
    result = _raw_metrics(context, docs)
    for key in ('importance', 'satisfaction'):
        low, high = ranges[key]
        value = result[key]
        result[key] = None if value is None or low is None else (value-low)/(high-low) if high > low else 0.
    importance, satisfaction = result['importance'], result['satisfaction']
    result['odi'] = None if importance is None or satisfaction is None else importance + max(importance-satisfaction, 0.)
    result['provisional'] = ['odi']
    result['quality'] = {k: (context.get('quality') or {}).get(k)
                         for k in ('cohesion', 'boundary', 'stability', 'npmi')}
    return result


def context_metrics(store_seg, context_id, *, session_minmax):
    context = next((c for c in store_seg.contexts() if c['context_id'] == context_id), None)
    if context is None:
        raise ValueError(f'Unknown Context: {context_id}')
    return _context_metrics(context, _documents(store_seg), session_minmax)


def persona_metrics(contexts, docs):
    result = {}
    for key in ('importance', 'satisfaction', 'odi'):
        observed = [c for c in contexts if c[key] is not None and c['doc_count']]
        count = sum(c['doc_count'] for c in observed)
        result[key] = sum(c[key]*c['doc_count'] for c in observed)/count if count else None
    result.update(doc_count=len(docs), author_count=len({d['author_hash'] for d in docs if d.get('author_hash')}),
                  provisional=['odi', 'importance', 'satisfaction'])
    return result


_COUNTERS = ('coverage_supplements', 'query_gen_fail', 'new_expansions', 'rare_fallback',
             'dpp_fill', 'untagged', 'lazy_dims', 'llm_calls', 'cache_hits', 'relevant_false', 'tag_calls', 'act_mismatch', 'persona_query_fail')
_DISTRIBUTIONS = ('coverage', 'band_exposure_ratios', 'novelty_distribution', 'escalation_candidates',
                  'reason_code', 'known_match_distribution')


def stage_report(counts: dict, params: dict) -> dict:
    """Explicit 4.8 whitelist: no retired A–C agreement measurement."""
    return {**{key: counts.get(key, 0) for key in _COUNTERS},
            **{key: counts.get(key, {}) for key in _DISTRIBUTIONS},
            'per_tab_counts': {tab: counts.get('per_tab_counts', {}).get(tab, 0) for tab in ('all', 'new')},
            'params': dict(params)}


def _situation(context, context_tags):
    summary = context.get('dims_summary') or {}
    phrases = {dim: ' '.join(r['label'] for r in rows if r.get('label')) or None
               for dim, rows in summary.items()}
    if any(phrases.values()):
        return dict(state=' '.join(p for p in (phrases.get('environment'), phrases.get('task_goal')) if p) or None,
                    emotion=phrases.get('internal_state'), barrier=phrases.get('resource_constraint')), 'dims'
    # Lazy dims take precedence over tag-only situations. Choose a stable modal
    # observed value per field, never generate another summary.
    observed = [t for t in context_tags if t.get('situation')]
    dims = [t for t in observed if t.get('situation_origin') == 'dims']
    rows = dims or observed
    result = {}
    for key in ('state', 'emotion', 'barrier'):
        counts = Counter(t['situation'].get(key) for t in rows if t['situation'].get(key))
        result[key] = min(counts, key=lambda x: (-counts[x], x)) if counts else None
    return result, 'dims' if dims else 'tag'


def _load_docs(root, wanted):
    result = {}
    for path in sorted((root / 'docs').glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    if row['doc_id'] in wanted:
                        result[row['doc_id']] = row
                        if len(result) == len(wanted):
                            return result
    return result


def _item(doc_id, docs, tags, *, role='support', tabs=('all',), novelty=None):
    doc, tag = docs[doc_id], tags[doc_id]
    quotes = tag.get('quotes') or []
    located = [locate(q, doc) for q in quotes]
    quote = next((q for q in located if q['verified']), located[0] if located else None)
    probabilities = doc.get('tagProbs') or {}
    return dict(doc_id=doc_id, source=doc.get('source') or '', quote=quote,
                tags=[dim for dim in ('sense', 'feel', 'think', 'act', 'relate', 'outcome')
                      if (probabilities.get(dim) or 0) >= params.TAG_PROB_ON],
                polarity=tag.get('polarity'), novelty=novelty, known_match=tag.get('known_match', 'none'),
                tab=list(tabs), role=role, dist_centroid=doc.get('dist_centroid'), combo_rarity=doc.get('combo_rarity'))


def item_view(row, docs, tags, role='support', *, known_items=()):
    doc_id = row['doc_id']
    doc, tag = docs.get(doc_id, {}), tags.get(doc_id, {})
    item = _item(doc_id, {doc_id:doc}, {doc_id:tag}, role=role, novelty=row.get('novelty'))
    handed = next((i['id'] for i in known_items if i.get('type') == 'doc'
                   and i.get('origin', i.get('from')) == 'rag' and i.get('doc_id') == doc_id), None)
    match = item['known_match']
    quote = item['quote'] or dict(field='body', idx=None, text='', start=None, end=None, verified=False)
    from app.evidence.quotes import quote_source
    return dict(docId=doc_id, source=item['source'], location={k:quote.get(k) for k in ('field','idx')},
                quote={k:quote.get(k) for k in ('text','start','end','verified')},
                quoteSource=quote_source(quote, doc), noveltyShown=row.get('novelty') in params.NOVELTY_SHOW,
                text=(doc.get('body') or doc.get('title') or '')[:600], tags=item['tags'], band=doc.get('band'),
                novelty=row.get('novelty'), noveltyReason=row.get('novelty_reason'), knownMatch=match,
                known=dict(handed=handed is not None, kiId=handed or (match if match != 'none' else None)),
                rare=doc.get('band') == 'edge' and bool(tag.get('pain_point') or tag.get('unmet_need')), role=role)


def assemble(sid: str, version: str) -> EvidencePackage:
    base = version_dir(sid, version)
    session = sessions.read_json(base / 'session.json')
    if session is None:
        raise sessions.StoreError('Session not found', 404, 'not_found')
    generation.check_read(sid, version, session)
    seg, evidence = SegmentStore.open(sid, version), EvidenceStore.open(sid, version)
    snapshot = evidence.snapshot()
    if snapshot.run is None:
        raise ValueError('Evidence run required')
    used_params = {name: getattr(params, name) for name in vars(params) if name.isupper()}
    used_params.update(snapshot.params)
    used_params = json.loads(json.dumps(used_params))
    session, tag_pver = generation.inputs(sid, version, session)
    root = prepared_root(sid, session)
    seg_docs = _documents(seg)
    docs = {d['doc_id']: d for d in seg_docs}
    prepared = _load_docs(root, set(docs))
    for doc_id, row in prepared.items():
        docs[doc_id] = {**docs[doc_id], **row}
    if session.get('training', {}).get('exportRef'):
        from app.known.filter import read_export
        for row in read_export(sid, session):
            if row['doc_id'] in docs:
                docs[row['doc_id']]['tagProbs'] = row.get('tagProbs')
    cache = TagCache.open(sid, session['prep']['derivedRef']['prepKey'], tag_pver)
    tags = cache.get_tags(docs)
    known = [k.model_dump() for k in read_known(session) if k.type == 'statement']
    judgments = cache.get_known(tags, [known_key(k) for k in known])
    for doc_id, tag in tags.items():
        tag['known_match'] = next((ki['id'] for ki in known if judgments.get((doc_id, known_key(ki)))), 'none')
    contexts = seg.contexts()
    ranges = session_minmax(seg)
    status = {c['context_id']: c for c in snapshot.contexts}
    counts = {key: sum((c.get('counts') or {}).get(key, 0) for c in snapshot.contexts)
              for key in _COUNTERS}
    counts.update(coverage={}, escalation_candidates={})
    counts['persona_query_fail'] = len({r['owner'] for r in snapshot.queries if r['owner'].startswith('persona:') and r['origin']=='fallback'})
    # Counts tied to tagging are distinct documents in this run's candidate or
    # persona-support pool, never every old entry in the shared cache.
    attempted = {r['doc_id'] for r in snapshot.candidates + snapshot.persona_support + snapshot.selected}
    observed = [tags[i] for i in sorted(attempted) if i in tags]
    counts['untagged'] = len(attempted - tags.keys())
    counts['act_mismatch'] = sum(bool((docs[i].get('tagProbs') or {}).get('act', 0) >= .5) != bool((tags[i].get('context_dims') or {}).get('activity_response')) for i in attempted if i in tags and tags[i].get('relevant'))
    counts['relevant_false'] = sum(t.get('relevant') is False for t in observed)
    counts['reason_code'] = dict(Counter(t.get('reason_code') or 'other' for t in observed if t.get('relevant') is False))
    counts['per_tab_counts'] = dict(Counter(r['tab'] for r in snapshot.selected))
    exposures = Counter(docs[r['doc_id']].get('band') for r in snapshot.selected)
    total = sum(exposures.values())
    counts['band_exposure_ratios'] = {k: v/total for k, v in exposures.items() if k is not None}
    counts['novelty_distribution'] = dict(Counter(r['novelty'] for r in snapshot.selected if r.get('novelty')))
    counts['known_match_distribution'] = dict(Counter(tags.get(r['doc_id'], {}).get('known_match', 'none') for r in snapshot.selected))
    blocks = []
    stage6 = sessions.read_json(base / 'segment/stage_6.json') or {}
    # Old stage-six runs lack Persona quality columns; use their report
    # stability as a fallback, leaving genuinely unavailable values null.
    persona_quality = {r['id']: dict(cohesion=r.get('cohesion'), boundary=r.get('boundary'),
                                    stability_ari=r.get('ari')) for r in stage6.get('personas', [])}
    for persona in seg.personas():
        pid = persona['persona_id']
        persona_docs = [d for d in seg_docs if d['persona_id'] == pid]
        context_blocks = []
        for context in (c for c in contexts if c['persona_id'] == pid):
            cid = context['context_id']
            assigned = {d['doc_id'] for d in seg_docs if d['context_id'] == cid}
            candidates = [r for r in snapshot.candidates if r['context_id'] == cid and r['doc_id'] in assigned]
            rare = _rare_candidates(candidates, tags, docs)
            ids, values = VectorStore(root).get([r['doc_id'] for r in rare])
            escalation = undifferentiated_candidate(rare, dict(zip(ids, values)))
            flags = list(context.get('flags') or [])
            append_context_flag(seg, cid, 'undifferentiated_candidate', present=bool(escalation))
            flags = [f for f in flags if f != 'undifferentiated_candidate']
            if escalation:
                if 'undifferentiated_candidate' not in flags:
                    flags.append('undifferentiated_candidate')
                counts['escalation_candidates'][cid] = escalation
            state = status.get(cid)
            if state:
                evidence.patch_counts(cid, undifferentiated=escalation)
            counts['coverage'][cid] = dict(covered=state.get('coverage') if state else None, total=6)
            selected = [r for r in snapshot.selected if r['context_id'] == cid and r['doc_id'] in assigned
                        and (tags.get(r['doc_id']) or {}).get('relevant')]
            support = {}
            for row in selected:
                if row['role'] != 'support':
                    continue
                item = support.setdefault(row['doc_id'], _item(row['doc_id'], docs, tags, tabs=()))
                if row['tab'] not in item['tab']:
                    item['tab'].append(row['tab'])
                if row['tab'] == 'new' and row.get('novelty'):
                    item['novelty'] = row['novelty']
            context_tags = [tags[i] for i in sorted(assigned) if i in tags and tags[i].get('relevant')]
            mean = context_polarity_mean(candidates, tags)
            counter = counter_evidence(candidates, tags, context_mean=mean)
            situation, origin = _situation(context, context_tags)
            context_blocks.append(dict(context_id=cid, context_name=context.get('name') or '',
                action=context.get('action') or '', situation=situation, situation_origin=origin,
                dominant_constraint=context.get('dominant_constraint'), keywords=context.get('keywords') or [],
                metrics=_context_metrics(context, seg_docs, ranges), evidence=list(support.values()),
                counter_evidence=[_item(r['doc_id'], docs, tags, role='counter') for r in counter],
                rare_evidence=[_item(r['doc_id'], docs, tags, role='rare') for r in rare[:params.RARE_TOP]], flags=flags))
        persona_ids = {d['doc_id'] for d in persona_docs}
        desire = desire_support([r for r in snapshot.persona_support if r['persona_id'] == pid and r['doc_id'] in persona_ids], tags)
        blocks.append(dict(persona_evidence=dict(cluster_id=persona['cluster_id'], persona_id=pid,
            persona_name=persona.get('name') or '', desire=persona.get('desire') or '', goal=persona.get('goals') or [],
            desire_support=[_item(r['doc_id'], docs, tags) for r in desire],
            artifacts=artifacts(sorted(persona_ids), tags, (session.get('projectContext') or {}).get('bk') or session.get('bk')),
            metrics=persona_metrics([c['metrics'] for c in context_blocks], persona_docs),
            quality={key: (persona.get('quality') or {}).get(key, persona_quality.get(pid, {}).get(key))
                     for key in ('cohesion', 'boundary', 'stability_ari')}),
            context_evidence=context_blocks))
    package = EvidencePackage.model_validate(dict(schema='evidence-package/1', version=version, params=used_params, personas=blocks))
    sessions.write_json(base / 'evidence/package.json', package.model_dump(by_alias=True, mode='json'))
    sessions.write_json(base / 'evidence/stage_7.json', stage_report(counts, used_params))
    (base / 'evidence/package_dirty.json').unlink(missing_ok=True)
    return package
