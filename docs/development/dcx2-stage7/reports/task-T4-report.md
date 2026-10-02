# T4 report — complete

Worktree: `/Users/persona1/Desktop/dcx_agent-stage7`  
Branch: `feature/dcx2-stage7`  
Task: stage 7 evidence params, versioned store, shared tag cache, Evidence Package schema.

## Files

Created:

- `backend/app/evidence/params.py`: copied the brief's Python parameter block verbatim, including all values, tuple order, Korean regex, and provisional names.
- `backend/app/evidence/store.py`: six D-251 tables, WAL, version-one schema initialization, scoped atomic replacements, JSON encode/decode, context upserts, reset, detached `EvidenceSnapshot`.
- `backend/app/evidence/cache.py`: version-independent tags and per-KI known cache, WAL, prompt byte hashing, incremental writes and KI deletion.
- `backend/app/evidence/package.py`: Quote, EvidenceItem, Situation, Artifact, PersonaMetrics, ContextMetrics, ContextEvidence, PersonaEvidence, PersonaBlock, EvidencePackage.
- `backend/tests/evidence/test_store.py`: 13 focused tests (including parametrized cases).
- `.superpowers/sdd/03-plan/task-T4-report.md`: this report.

No existing implementation files were modified. Neither stopwords file was touched. No subagents, git add, or commit were used.

## Requirements and patterns read

- `.superpowers/sdd/03-plan/task-T4-brief.md` first.
- `docs/development/dcx2-stage7/02-design.md`, especially section 2.
- `docs/development/dcx2-stage6-8/02-design.md`, especially sections 2.3, 2.4, and 4.7.
- `backend/app/segment/store.py`: version directory, WAL, user_version DDL guard, transaction context manager, JSON column behavior.
- `backend/app/routers/segment.py`: ConfirmationStore's explicit read transaction (D-239).
- `backend/app/segment/dims.py`: configured local root, prepKey source, shared cache location.
- `backend/app/model/infer.py` and `backend/app/routers/prep.py`: prepared_root and preparation-key validation.
- Existing evidence fixtures, pytest configuration, and network-blocking conftest.

## RED → GREEN → refactor

All commands ran from the worktree root using the requested virtualenv. Tests were written before the four implementation modules.

1. RED:

   `backend/.venv/bin/python -m pytest backend/tests/evidence/test_store.py -q`

   Exit 2. Expected collection failure: `ImportError: cannot import name 'params' from 'app.evidence'`. One collection error, one existing Pydantic warning; 0.08 seconds. Implementation modules did not yet exist.

2. GREEN after implementation:

   `backend/.venv/bin/python -m pytest backend/tests/evidence/test_store.py -q`

   Exit 0. **12 passed**, one existing warning; 2.28 seconds.

3. Refactor/self-review:

   Moved scoped row validation and JSON serialization ahead of the write lock, leaving DELETE and all INSERTs in the same transaction. Strengthened the rollback test with a valid first insert followed by a SQL constraint failure. Added a trace-based test proving reopening both databases does not execute CREATE/ALTER/DROP DDL.

   `backend/.venv/bin/python -m pytest backend/tests/evidence/test_store.py -q`

   Exit 0. **13 passed**, one existing warning; 3.08 seconds.

4. Required complete evidence suite, run once:

   `backend/.venv/bin/python -m pytest backend/tests/evidence -q`

   Exit 0. **35 passed**, two warnings; 7.11 seconds.

5. `git diff --check`: exit 0. The implementation files are new/untracked, so this command alone does not inspect their contents; they were also reviewed directly. Branch check returned `feature/dcx2-stage7`.

## Decisions and integration contract

### EvidenceStore

- `EvidenceStore.open(sid, version)` uses `app.context.versions.version_dir` and writes `versions/vN/evidence/evidence.sqlite`.
- Exactly six tables: meta, queries, candidates, selected, contexts, persona_support. No extra bookkeeping table; `PRAGMA user_version=1` guards DDL.
- `reset(run, params)` atomically clears all result tables and replaces meta with one row containing run, params, and started_at. After reset, the five result tables have zero rows; meta intentionally has one row.
- `write_queries` replaces one owner; `write_candidates` replaces one context; `write_selected` replaces one context/tab; `write_persona_support` replaces one persona. Empty inputs clear only that scope. Candidate expansion callers must pass the combined candidate set when preserving earlier rounds.
- Selected keys include role, allowing a document to have support/counter/rare memberships. Persona support keys include kind, allowing desire and artifact membership for one document. Ordering is deterministic and rank-aware.
- Candidate `round` has no SQLite affinity so integers 0–3 stay integers and `cov` stays text. Its default is integer 0.
- JSON readers expose `params`, `dims_hit`, and `counts`; writers accept decoded field names or serialized `*_json` names. Context updates preserve omitted fields.
- `snapshot()` returns a detached frozen dataclass with attributes `run`, `params`, `started_at`, `queries`, `candidates`, `selected`, `contexts`, `persona_support`. The row lists/dicts themselves are ordinary mutable Python objects, detached from SQLite. Explicit BEGIN precedes the meta SELECT and all five table reads, so no per-instance shared read connection is needed.
- Caller owns writable-version and stale-run checks, consistent with SegmentStore. Store methods do not make the entire multi-call pipeline one transaction.

### TagCache

- Path: `Path(settings.local_data_dir) / 'llmcache' / sid / prep_key / f'tag-{pver}.sqlite'`, exactly the bundle 1 layout with the tag prefix.
- Callers supply `session['prep']['derivedRef']['prepKey']`. Reuses `root_dir` session validation and `prepared_root` preparation-key validation. Because this API has no collection ID and does not need an active version, the latter receives a validation-only `c1` reference; that helper only constructs a path and neither reads nor creates that collection. Valid preparation keys follow the existing `p_[0-9a-f]{12}` rule.
- `prompt_version(name, *, prompt_dir=None)` hashes raw bytes of `{name}.v1.md` and returns SHA-256's first 12 hex characters. Default directory is `backend/app/evidence/prompts`; tests use `prompt_dir=tmp_path`. Missing production prompts raise FileNotFoundError rather than fabricating a version. Names and pver are validated as safe path components.
- Bundle 1 dims currently uses a full SHA-256 hash. T4 deliberately uses the brief's explicit 12-character hash; dims was not changed.
- `tags` stores `doc_id`, a lossless JSON payload, and model. JSON preserves the section 2.3 values and later tagging fields such as context_dims. `get_tags` returns decoded dictionaries including the authoritative model column.
- `known` stores `(doc_id, ki_id)`, match 0/1, model. Missing pairs are omitted; cached False is retained as a bool. Writes upsert only supplied pairs, and `drop_known` removes only the specified KI across documents. Tags and other KI judgments survive. The later tagging/orchestration task schedules judgments for new KI IDs; this storage task performs no LLM calls.
- Per-document indexed reads accept generators and avoid SQLite parameter-count limits. Reads spanning multiple requested documents use one read transaction.

### Evidence Package

- Exact external names retained: `schema`, `persona_evidence`, `context_evidence`, `goal` (singular), `desire_support`, `counter_evidence`, `rare_evidence`, `situation_origin`, and every item/quote field from the brief.
- Serialize with `model_dump(mode='json', by_alias=True)` or `model_dump_json(by_alias=True)` for the external `schema` key. Python attribute is `schema_`; population by field name is also accepted.
- The brief's full EvidenceItem contract takes precedence over the abbreviated desire_support example in design 2.4. Quote requires `verified` as specified by the brief.
- Context metrics follow design 4.7 (importance, satisfaction, odi, doc_count, author_count), plus provisional names and quality. Numeric observations and situation text can be null. Persona quality remains a dictionary as required; context quality is a numeric-or-null dictionary supporting cohesion/boundary/stability/npmi.
- Unknown model fields are rejected to expose contract spelling errors. Literal constraints cover schema version, quote field, tab, role, and situation origin. Optional rarity fields default to None; standard Pydantic dumps include those defaults unless the caller requests otherwise.

## Self-review

- Six-table schema and WAL confirmed directly from SQLite.
- Fresh open has no run; reopen preserves run; v2 cannot see v1 rows.
- Reset updates metadata and clears every result table atomically.
- Scoped replacements leave other owners/tabs/contexts intact; context updates preserve counts/coverage.
- JSON values, Korean strings, integer/cov rounds, novelty reasons, persona support, and params round-trip.
- Rollback test checks both validation failure and a SQL failure after a successful first insert.
- WAL reader completes while another connection holds an uncommitted write, observing the old committed generation.
- Deterministic trace-hook test commits a new run and rows on another connection after meta was read and before queries are read. Snapshot retains the old run and old rows in all checked tables; writer independently confirms the new run. No timing sleeps required.
- Tag cache stays outside versions; changing prompt bytes changes file; reopening reuses data; another preparation key is isolated.
- Adding KI judgments and deleting a KI preserve unrelated known rows and tags; missing versus False remains distinguishable.
- Package fixture exercises all nested structures, three roles, nullable values, rare metrics, quote coordinates/verification, and exact JSON key/value round-trip with alias serialization.
- Parameter test asserts every value in the brief.

## Concerns / remaining integration responsibilities

No blocking T4 concerns. Production prompts are intentionally supplied by later tasks. Callers must use alias serialization for package output, provide combined rows when replacing expanded candidate sets, and enforce stale-run/writable-version checks. KI addition/deletion workflow coordination remains with later tagging/pipeline tasks; the required cache primitives are implemented here.

Two pre-existing/environment warnings occurred: class-based Settings Config is deprecated by Pydantic, and joblib could not parse physical CPU count and fell back to logical cores. Neither affected test results. No dependency, configuration, network policy, or bundle 1 behavior was changed.
