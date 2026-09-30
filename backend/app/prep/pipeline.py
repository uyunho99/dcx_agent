"""Durable preparation, with a single writer per immutable preparation key."""
import fcntl
import json
from pathlib import Path
import re
import time

import numpy as np

from app.config import settings
from app.context import store
from app.context.versions import version_dir
from app.prep.clean import clean_html, strip_boilerplate, token_text
from app.prep.config import PrepConfig, analyzer_version, prep_key
from app.prep.report import stage3_report
from app.prep.tokens import tokenize
from app.services.preprocessing import _crawl_docs, filter_documents
from app.vectors.embedder import EmbedderUnconnected, FakeEmbedder, VoyageEmbedder, get_embedder
from app.vectors.store import VectorStore

SHARD_ROWS = 10_000
DOC_SHARD_ROWS = 5_000
BATCH_ROWS = 128


class _Unconnected:
    """Preserve offline preprocessing, recording every vector as failed."""
    name = 'voyage'

    def __init__(self, cfg):
        self.model, self.dim = cfg.embedModel, cfg.embedDim

    def embed(self, texts):
        raise EmbedderUnconnected('Voyage is not connected')


def _jsonl(path, rows):
    store.atomic_write(path, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))


def _text(doc):
    return '\n'.join([doc.get('title', ''), doc.get('body', ''),
                      *(comment.get('text', '') for comment in doc.get('comments', []))])


def _embed(embedder, texts):
    vectors = np.zeros((len(texts), embedder.dim), dtype=np.float32)
    failed = np.ones(len(texts), dtype=bool)
    for start in range(0, len(texts), BATCH_ROWS):
        indexes = np.arange(start, min(start + BATCH_ROWS, len(texts)))
        for _ in range(3):
            try:
                result = np.asarray(embedder.embed([texts[i][:2000] for i in indexes]), dtype=np.float32)
                if result.shape != (len(indexes), embedder.dim):
                    continue
                valid = np.isfinite(result).all(axis=1) & (np.linalg.norm(result, axis=1) > 0)
                valid &= (np.abs(result) <= np.finfo(np.float16).max).all(axis=1)
                vectors[indexes[valid]] = result[valid]
                failed[indexes[valid]] = False
                indexes = indexes[~valid]
                if not len(indexes):
                    break
            except EmbedderUnconnected:
                break
            except Exception:
                # Provider payloads may include credentials or document text.
                continue
    return vectors, failed.tolist()


def _checkpoint(ctx, done, total):
    detail = {'done_shards': done, 'total_shards': total}
    ctx.heartbeat(done / max(total, 1), detail)
    while ctx.should_pause() and not ctx.should_stop():
        time.sleep(.1)
        ctx.heartbeat(done / max(total, 1), detail)
    return not ctx.should_stop()


def _publish(sid, version, root, cfg, manifest):
    # Publish compatibility output once per result, including recovery after a crash.
    target = Path(settings.local_data_dir) / manifest['compatRef']
    if not manifest.get('compatWritten') or not target.exists():
        from app.services import preprocessing
        documents = [json.loads(line) for path in sorted((root / 'docs').glob('*.jsonl'))
                     for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        preprocessing.save_jsonl(manifest['compatRef'], documents)
        # An interrupted export is overwritten on resume until this marker is durable.
        manifest['compatWritten'] = True
        store.write_json(root / 'manifest.json', manifest)
    with store.locked(sid):
        path = version_dir(sid, version) / 'session.json'
        session = store.read_json(path)
        if session is not None:
            session['prep'] = dict(config=cfg.model_dump(),
                                   derivedRef=dict(collectionId=manifest['collectionId'], prepKey=root.name),
                                   status='done', savedAt=store.now())
            store.write_json(path, session)


def run_prep(ctx, sid: str, version: str) -> Path:
    session = store.read_json(version_dir(sid, version) / 'session.json')
    if session is None:
        raise ValueError('Session version not found')
    cid = session.get('collectionId')
    if not isinstance(cid, str) or not re.fullmatch(r'c[1-9][0-9]*', cid):
        raise ValueError('Invalid crawl collection id')
    values = {**session.get('prep', {}).get('config', {}), **getattr(ctx, 'args', {}).get('config', {})}
    cfg = PrepConfig.model_validate(values)
    try:
        if cfg.embedder == settings.embed_backend:
            embedder = get_embedder()
        else:
            embedder = FakeEmbedder() if cfg.embedder == 'fake' else VoyageEmbedder()
    except EmbedderUnconnected:
        embedder = _Unconnected(cfg)
    if (embedder.model, embedder.dim) != (cfg.embedModel, cfg.embedDim):
        raise ValueError('Preparation embedding model/dimension must match configured embedder')
    key = prep_key(cid, cfg, embedder)
    root = Path(settings.local_data_dir) / 'derived' / sid / cid / key
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = store.read_json(root / 'manifest.json')
        if manifest and manifest['status'] == 'done':
            _publish(sid, version, root, cfg, manifest)
            return root
        if manifest is None:
            manifest = dict(collectionId=cid, prepKey=key, config=cfg.model_dump(),
                            embedder=dict(name=embedder.name, model=embedder.model, dim=embedder.dim),
                            analyzer=analyzer_version(), createdAt=store.now(), counts={}, progress={},
                            compatRef=f'preprocessed/{sid}/{time.time_ns()}.jsonl')
        manifest['status'] = 'running'
        store.write_json(root / 'manifest.json', manifest)
        try:
            documents = _crawl_docs(sid, session=session)
            return _run(ctx, sid, version, root, cfg, embedder, documents, manifest)
        except Exception:
            manifest['status'] = 'failed'
            store.write_json(root / 'manifest.json', manifest)
            raise


def _run(ctx, sid, version, root, cfg, embedder, documents, manifest):
    cleaned, replacements = [], {}
    for raw in documents:
        doc = dict(raw)
        phrases = cfg.boilerplate.get(doc.get('source', ''), [])
        doc['title'] = clean_html(doc.get('title', ''))
        if 'snippet' in doc:
            doc['snippet'] = clean_html(doc['snippet'])
        doc['body'], count = strip_boilerplate(clean_html(doc.get('body', '')), phrases)
        doc['comments'] = []
        for comment in raw.get('comments', []):
            text, n = strip_boilerplate(clean_html(comment.get('text', '')), phrases)
            doc['comments'].append({**comment, 'text': text})
            count += n
        if count:
            source = doc.get('source', '')
            replacements[source] = replacements.get(source, 0) + count
        cleaned.append(doc)
    filtered, removed = filter_documents(cleaned, cfg.adFilter, cfg.excludeSources,
                                         cfg.minBodyChars, full_text=True)
    vectors = VectorStore(root)
    existing = {doc_id: bool(failed[i]) for ids, _, failed in vectors.iter_shards()
                for i, doc_id in enumerate(ids)}
    total = (len(filtered) + SHARD_ROWS - 1) // SHARD_ROWS
    done = manifest['progress'].get('done_shards', 0)
    for shard, start in enumerate(range(0, len(filtered), SHARD_ROWS), 1):
        if shard <= done:
            continue
        if not _checkpoint(ctx, done, total):
            manifest['status'] = 'interrupted'
            store.write_json(root / 'manifest.json', manifest)
            return root
        batch = filtered[start:start + SHARD_ROWS]
        for offset in range(0, len(batch), DOC_SHARD_ROWS):
            part = (shard - 1) * ((SHARD_ROWS + DOC_SHARD_ROWS - 1) // DOC_SHARD_ROWS) + offset // DOC_SHARD_ROWS + 1
            docs = batch[offset:offset + DOC_SHARD_ROWS]
            filename = f'part-{part:05d}.jsonl'
            _jsonl(root / 'docs' / filename, docs)
            _jsonl(root / 'tokens' / filename,
                   [dict(doc_id=d['doc_id'], tokens=tokenize(token_text(_text(d)), cfg.tokenPos)) for d in docs])
        pending = [d for d in batch if d['doc_id'] not in existing]
        if pending:
            matrix, failed = _embed(embedder, [_text(d) for d in pending])
            ids = [d['doc_id'] for d in pending]
            vectors.write_shard(ids, matrix, failed)
            existing.update(zip(ids, failed))
        done = shard
        manifest['progress'] = dict(done_shards=done, total_shards=total,
                                    docs_written=start + len(batch), tokens_written=start + len(batch),
                                    vectors_written=len(existing))
        store.write_json(root / 'manifest.json', manifest)
    if not _checkpoint(ctx, done, total):
        manifest['status'] = 'interrupted'
        store.write_json(root / 'manifest.json', manifest)
        return root
    failures = sum(existing.values())
    report = stage3_report(original=len(documents), after=len(filtered), removed=removed,
                           boilerplate_replaced=replacements, tokens_written=len(filtered),
                           embedded=len(existing) - failures, embed_failed_zero_vector=failures,
                           prepKey=root.name, embedder=embedder.model, analyzer=analyzer_version())
    store.write_json(root / 'stage_3.json', report)
    manifest['counts'] = report
    manifest['status'] = 'done'
    store.write_json(root / 'manifest.json', manifest)
    _publish(sid, version, root, cfg, manifest)
    return root
