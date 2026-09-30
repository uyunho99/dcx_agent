# gstack /review — feature/dcx2-stage3-5 (READ-ONLY)

- Range: `0e4501e..e16c5ce` (36 commits, 195 files, +17,735 / -724). DIFF_BASE=0e4501e (stage 0-2 branch point), no fetch.
- Mode: report-only (harness). No AUTO-FIX, no repo edits, no commits, no AskUserQuestion.
- Skipped per harness: Greptile (no PR), Codex passes, Claude adversarial subagent, Review Army subagent dispatch (specialist lenses were applied inline by the main reviewer instead: security, testing, performance, API contract).
- Already-known residuals were NOT re-reported: backlog B-108, and everything in reports/final-review1.md, including the unfixed minors (manual audit uses up a schedule slot, paused worker polling a read-only version, monitor blocking new versions, overview polling cost, lease `at` not refreshed during a batch).
- Prior learning applied: dcx-full-session-save (confidence 9/10, from 2026-09-29). Verified: `routers/sessions.py` `owned` now includes `prep`, `labeling`, `training`, and the new screens do not call `/save-session`.
- Cross-project learnings: config was already `true`. This run searched project-scoped only, and the config was not changed.

```
Scope Check: CLEAN
Intent: DCX2 stages 3-5 rebuild (prep, dual-LLM labeling and audit, MLP ensemble, stage-5 export) + Known Insight, local float16 RAG, Pinecone removed (03-plan.md / 02-design-r2.md)
Plan: /Users/persona1/Desktop/dcx_agent-dcx2-stage3-5-plan/docs/development/dcx2-stage3-5/03-plan.md
Delivered: work runner + prep pipeline + Jev/GPT judge + merge/route/queue/audit + model train/infer/monitor/export + Known Insight/RAG + stage 3-5 version rules + T16-T20 screens
Plan items: 29 DONE, 1 PARTIAL, 0 NOT DONE, 1 UNVERIFIABLE
```
The stage 0-2 files touched (crawl/control.py, crawl/queue.py, llm/codex_exec.py, chat/search/personas/clustering/embedding) all map to planned items E8 and T14. No scope creep was found.

## Plan Completion Audit

```
PLAN COMPLETION AUDIT
═══════════════════════════════
Plan: .../dcx2-stage3-5/03-plan.md

## Implementation Items
  [PARTIAL]      T01 deps/settings/worker: runner, worker and settings are done, and tensorflow and pinecone are gone from requirements.txt. But `.env.example:27 PINECONE_API_KEY=` and README.md:12,319 still ship the removed setting (D-121 "설정을 없앤다"). See finding #3.
  [DONE]         T02 vectors: vectors/store.py (float16 shards, fsynced index), search.py, embedder.py
  [DONE]         T03 rule r1: label/rule.py (no boundary rule, D-143)
  [DONE]         T04/T05 prep pipeline + API: prep/pipeline.py, routers/prep.py
  [DONE]         T06 Jev client: label/jev.py (normalization, bad on missing answer, idempotency key)
  [DONE]         T07 GPT labeler: label/gpt.py (per-batch run_many ID, partial salvage, usage-limit pause)
  [DONE]         T08 judge cache/worker: label/judge.py, label/votes.py (ctxKey cache, lease reclaim R-110)
  [DONE]         T09 merge/labels.sqlite: label/merge.py, route.rebuild_final (incremental journal)
  [DONE]         T10 audit: label/audit.py (1,000 then every 10,000, reissue 2, kappa floor)
  [DONE]         T11 routing/queue/API: label/route.py, routers/labeling_v2.py
  [DONE]         T12 ensemble: model/net.py, train.py, calibrate.py
  [DONE]         T13 registry/infer/export/model mode/monitor: model/*.py, routers/training_v2.py
  [DONE]         T14 Known Insight + local RAG + 6/6.5 reuse: known/*, routers/known.py, services/*
  [DONE]         T15 versions/badges: context/versions.py (_copy_file, _restart), store.session_activities
  [DONE]         T16-T20 frontend: components/{prep,label,train,known}, lib/api/*, pages
  [DONE]         E1-E10 (labeler in run key, per-version export path, ctxKey, per-batch run ID, labeler_failed queue, sqlite backup copy, server-owned keys, shared pid_alive, incremental merge/memmap cache, τ/α/calibration removed)
## Test Items
  [DONE]         Review Focus 1-5 tests present (tests/label/test_jev.py, test_gpt.py, test_label_api.py, vectors/test_search.py, known/test_known.py)
## External
  [UNVERIFIABLE] Browser QA (QA-P, QA-L1..L6, QA-M, QA-K, QA-V, QA-E2E). The task reports record code-contract review, not browser runs (e.g. reports/task-T18-report.md "Code/contract review against QA-L1–L6"). Needs a manual browser pass.
─────────────────────────────────
COMPLETION: 29/31 DONE, 1 PARTIAL, 0 NOT DONE, 0 CHANGED, 1 UNVERIFIABLE
─────────────────────────────────
DISCREPANCY: PARTIAL | T01 "삭제: pinecone_api_key" / D-121 settings removal | code setting removed, env template + README still advertise it
INVESTIGATION: the config.py field was deleted in T01/T14, but .env.example and README.md are untouched in the diff. Likely forgotten.
IMPACT: MEDIUM. A non-empty value in .env now crashes startup (finding #3).
```

## Findings

Pre-emit gate: every finding below quotes the line that motivated it.

### INFORMATIONAL

1. [P2] (confidence 8/10) frontend/src/components/label/QueueCard.tsx:55. Model-mode queue reasons are not handled in the UI. The backend enqueues `model_uncertain` and `model_disagree` (backend/app/model/infer.py:65-68 `return 'model_uncertain'` / `'model_disagree' if pred.memberDisagree`; `_project` `INSERT INTO queue VALUES (?,?,?,'open')`). The card label, however, is `item.reason === 'labeler_failed' ? '판정 실패' : item.reason === 'grade_mismatch' ? '두 라벨러 등급 불일치' : mode === 'reissue' ? '이전 감사 다시 판정' : '감사 판정'`, so every model-mode escalation is shown as "감사 판정". The summary line in Queue.tsx:28 (`등급 불일치 {byReason.grade_mismatch ?? 0}건 · 판정 실패 {byReason.labeler_failed ?? 0}건`) shows 0/0 while the tab count shows the real total. lib/types.ts:149 also narrows `reason` to the two LLM values.
   Fix: add labels for `model_uncertain` ("모델 확신 낮음") and `model_disagree` ("앙상블 불일치"), show them in the Queue summary by mode, and widen the `QueueItem.reason` type.

2. [P2] (confidence 8/10) frontend/src/components/label/useLabelSeen.ts:9-13. The "지난 접속 이후" baseline is overwritten as the screen opens. `useLabelSeen` (declared at labeling/page.tsx:29, before the overview effect at :32) fires `markLabelSeen` in parallel with the first `getLabelOverview`. The backend then computes changes from the new value: overview.py:139-142 `since = labeling.get('lastSeenAt')` … `WHERE at>?`. The count is race-dependent on the first read, and from the first 5-second poll it always means "since this screen opened". The design (02-design-r2 line 280) asks for the previous visit.
   Fix: have `/seen` keep the prior timestamp (e.g. `labeling.previousSeenAt`, or return it) and compute `changes` from that, or pin the first overview's `lastSeenAt` client-side and send it as `since`.

3. [P2] (confidence 7/10) backend/app/config.py:43 (field `pinecone_api_key` removed) with .env.example:27 `PINECONE_API_KEY=`. `Settings` uses pydantic-settings defaults (only `class Config: env_file = _ENV_FILE`, config.py:90-91), so extras are forbidden. I verified this with backend/.venv: a dotenv line `PINECONE_API_KEY=abc` raises `ValidationError … pinecone_api_key Extra inputs are not permitted` (an empty value is fine). README.md:319 still lists the key as required ("O"), so anyone who follows it cannot import `app.config`, and the backend does not start.
   Fix: remove the key from .env.example and the README, and/or set `extra='ignore'` on Settings.

4. [P2] (confidence 6/10, medium: verify the fixture channel is used past stage 2) backend/app/model/features.py:30. `result[i, 1024 + CHANNELS.index(doc.get('channel', doc.get('source')))] = 1` raises ValueError for any source outside the five in `CHANNELS`. The stage 0-2 fixture adapter produces `source = "fixture"` (crawl/adapters/fixture.py:21), so a fixture-based run fails the whole train or infer worker instead of just one document.
   Fix: map unknown or missing channels to a zero one-hot (or an explicit "other" slot in the next feature contract), or reject them at prep with a clear message.

5. [P2] (confidence 5/10, medium: currently blocked in the UI) backend/app/routers/prep.py:90-111. The R-106 lock covers only `PUT /prep/config` (`store.assert_labeling_not_started(data)` at :81). `POST /prep/run` recomputes `key = prep_key(cid, cfg, identity)` from the current `collectionId` and calls `_save(... derivedRef=ref ...)` with no lock check. A same-version added-keywords crawl (crawl/control.py:157 `parent = session.get('collectionId') if mode == 'added-keywords'`, which is not labeling-locked) changes `collectionId`, so a later `/prep/run` swaps `derivedRef` under a started labeling. That recreates the known "labels never refresh / export blocked" state. The legacy `POST /preprocess` v2 branch (services/preprocessing.py:124-133) merges request config into `run_prep` and republishes `session['prep']` the same way. The current screen always saves config first, which 409s.
   Fix: in `/prep/run` and the v2 branch of `preprocess_data`, call `assert_labeling_not_started` when the computed ref differs from the current `derivedRef`, and consider locking `start_list` after labeling starts too.

6. [P2] (confidence 7/10) README.md:12,319. The docs are stale: they describe "Pinecone(벡터 DB)" and a required `PINECONE_API_KEY`, while this branch removes Pinecone (D-121) and adds new env settings (`JEVMODEL_API_KEY`, `EMBED_*`, `LABEL_GPT_BACKEND`, …) that the README does not mention.
   Fix: run `/document-release` (update the stack table and env table).

### Appendix: suppressed (confidence 3-4)
- (4/10) backend/app/label/overview.py:113-128 and audit.py:169,193. `GET /label/{sid}/overview?version=<past>` still runs DDL (`schema(labels)`, `_schema`) and `_apply_overrides` against a read-only version's labels.sqlite. This is idempotent today, but read-only snapshots are mutated on GET. Fix: open past versions with `mode=ro` and skip reconciliation.
- (4/10) backend/app/label/jev.py:18-33. The per-key limiter is process-local, but judge (per version) and monitor run as separate processes, so concurrent workers can exceed 120/min per key. The only effect is 429 retries plus the transient-pause path. Fix: a file-lock or sqlite token bucket per key fingerprint.
- (3/10) backend/app/routers/search.py:10. `search_docs` raises `StoreError` for an invalid `sid` (root_dir regex), which becomes an unhandled 500 on the plain router. Fix: catch it and return `reason`.

Specialists: not dispatched (harness: no subagents). The lenses applied inline found nothing beyond the items above. SQL uses fixed identifiers or parameters: the f-string table names in versions._restart_labels, route.py and audit next_item all come from constant tuples. Subprocess calls use arg arrays with no shell (work/runner.py:32-37). `torch.load` uses `weights_only=True`. Ids used in paths are regex-validated (root_dir, version_dir, registry._path, prep._root, judge.cache_root, database_path). LLM outputs are schema-validated before persisting (GptBatch salvage + Tags Literals, Jev `_parse_vote`). No dangerouslySetInnerHTML, and SourceCard href is restricted to http(s).

PR Quality Score: 7.0/10

Pre-Landing Review: 6 issues (0 critical, 6 informational)
