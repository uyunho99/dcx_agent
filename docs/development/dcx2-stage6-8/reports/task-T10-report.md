# T10 report

- status: complete
- executor: codex
- Task: DCX 2.0 stage 6 bundle 1, FastAPI router and confirmation gates.

## Files

- `backend/app/routers/segment.py` — new version-aware router, validation, projections, worker launch/status, confirmation generation checks, global layer gates, bulk confirmation, request memos, original-document paging.
- `backend/app/main.py` — router import and one `include_router` line.
- `backend/tests/segment/test_api.py` — HTTP tests using `segment_synth` and the real pipeline synchronously; fake local LLM/embedding backends; no external network.
- `.superpowers/sdd/03-plan/task-T10-report.md` — this requested report.

No git add/commit. No subagents. Existing store, pipeline, worker, and background documents remain unchanged.

## RED

Command: `backend/.venv/bin/python -m pytest backend/tests/segment/test_api.py -q`

Initial RED: **14 failed**, 1 warning, 3.64s. All failures were expected HTTP 404 responses before route registration. Every API-table row was covered, including stale single/bulk confirmations, reset consent, global layer gates, validation, read-only writes, transactional cross-Persona rejection, and completion.

Review RED: **1 failed, 17 passed**, 2 warnings, 29.11s. The added concurrent-generation paging test showed that reading `run` after the document rows could label an old page with a new generation. The router now captures the generation before reading documents. Additional tests verify a generation change between the initial check and the write transaction, single-confirmation completion/stale clearing, and invalid inputs/missing entities.

## GREEN

Initial implementation: **14 passed**, 2 warnings, 24.29s.

Final targeted result after refactoring: **18 passed**, 2 warnings, 28.97s.

Refactor: consolidated writable-version validation, generation validation, global gating, and lock lifetime into a shared `_confirmation` context manager for single and bulk confirmation. Public behavior is unchanged. `git diff --check` passed.

## Full suite

Command: `backend/.venv/bin/python -m pytest backend/tests -q`

Result: **1645 passed, 2 deselected, 2 warnings in 216.61s (0:03:36)**. Executed once after the final refactor; exit code 0. No full-suite failures.

## Final API shapes for frontend

All routes accept optional `?version=vN`; omission selects the active version. All write routes enforce existing `assert_writable`; a historical/read-only version returns 409. Layer lists use objects containing `run` and the named collection. `run` is the segmentation generation UUID and is **different from** the detached worker's `runId`. Confirmation bodies must echo the list's `run`.

Errors retain the existing `{status:"error",error:{kind,message}}` envelope (the shared route also includes `error.code` for StoreError responses). Exact stale message: `다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.` Exact missing-stage-five message: `학습 단계에서 결과를 저장한 뒤 클러스터링을 실행하세요.`

### POST `/segment/{sid}/run`

Body: `{k?: integer 3..8, confirmReset?: boolean}`; body may be omitted. Explicit integer `k`, or any existing layer results, requires `confirmReset:true`, otherwise 409 `confirm_required`. A first run without `k` needs no consent. Worker arguments are exactly `{k: integer|null, fresh: boolean}`; `fresh` comes from `confirmReset`. No checkpoint/result deletion is performed by the router.

Response example:
```json
{"runId":"worker-1"}
```

### GET `/segment/{sid}/status`

Returns live worker state when running/paused/failed/interrupted, otherwise session review/done state. Includes `run`, `status`, `step`, `progress`, store-derived `confirm`; optional `stage6` is the complete existing `stage_6.json`, and optional `reason` explains a stopped worker. Initial status is `none`, step `load`, progress `0`; no generation is `null`.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","status":"interrupted","step":"L3","progress":0.4,"confirm":{"clusters":"0/5","personas":"0/12","contexts":"0/31"},"reason":"이어서 진행"}
```

### GET `/segment/{sid}/clusters`

`kSuggest` contains the pipeline's `L1` report, or null before it is available. `k` is the chosen value; `suggested` is the automatic recommendation. Metrics count all assigned documents, not only a page.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","clusters":[{"id":"CL0","docs":120,"nameDraft":"절전 생활","name":null,"confirmed":false,"keywords":["절전"],"reps":[{"docId":"doc-1","text":"예약으로 냉방한다","source":"naver_cafe","field":"body","idx":null}],"quality":{"cohesion":0.8,"boundary":0.1,"ari":0.9,"flags":[]},"channels":{"naver_cafe":0.6,"youtube":0.4},"channelSkew":false,"requests":[]}],"kSuggest":{"k":5,"suggested":5,"silhouette":{"5":0.7},"inertia":{"5":12.0},"dendrogram":[],"sample":600}}
```

### GET `/segment/{sid}/personas?cluster=CL0`

Global gate: every Cluster must be confirmed, even when filtering to one Cluster; otherwise 409 `locked`. `authors` is distinct nonempty author hashes. Optional `hint` is not synthesized; persisted `flags` remain available for UI guidance.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","personas":[{"id":"CL0-P0","clusterId":"CL0","docs":60,"authors":32,"nameDraft":"절전을 원하는 사람","name":null,"desireDraft":"편하게 지내고 싶다.","desire":null,"goalsDraft":["전기료 절약"],"goals":[],"centrality":[["절전",0.8]],"network":{"nodes":[],"edges":[]},"similar":[],"reps":[],"flags":[],"confirmed":false}]}
```

### GET `/segment/{sid}/contexts?persona=CL0-P0`

Global gate: every Persona must be confirmed, otherwise 409 `locked`. `emptyGoalConstraintRatio` is the overall sampled ratio from `stage6.dims.empty_goal_or_constraint` (0 before available), including when filtering by Persona.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","contexts":[{"id":"CL0-P0-C0","personaId":"CL0-P0","docs":30,"nameDraft":"취침 예약","name":null,"actionDraft":"취침 전에 예약한다.","action":null,"keywords":["취침","예약"],"dominantConstraint":"전기료","dimsSummary":{},"quality":{"cohesion":0.8,"npmi":0.4},"flags":[],"confirmed":false}],"emptyGoalConstraintRatio":0.1}
```

### PUT `/segment/{sid}/clusters/{id}`

Body: `{run, name, confirm:true}`. Required text is trimmed and cannot be blank. Returns the same public row shape used in the Cluster list.

Response example:
```json
{"id":"CL0","docs":120,"nameDraft":"절전 생활","name":"절전 생활","confirmed":true,"keywords":["절전"],"reps":[],"quality":{"cohesion":0.8,"boundary":0.1,"ari":0.9,"flags":[]},"channels":{"naver_cafe":1.0},"channelSkew":true,"requests":[]}
```

### PUT `/segment/{sid}/personas/{id}`

Body: `{run, name, desire, goals:[1..3 nonblank strings], confirm:true}`. Empty/whitespace Desire, invalid goals, or missing `run` returns 422. All Clusters must be confirmed.

Response example:
```json
{"id":"CL0-P0","clusterId":"CL0","docs":60,"authors":32,"nameDraft":"절전을 원하는 사람","name":"절전을 원하는 사람","desireDraft":"편하게 지내고 싶다.","desire":"편하게 지내고 싶다.","goalsDraft":["전기료 절약"],"goals":["전기료 절약"],"centrality":[["절전",0.8]],"network":{"nodes":[],"edges":[]},"similar":[],"reps":[],"flags":[],"confirmed":true}
```

### PUT `/segment/{sid}/contexts/{id}`

Body: `{run, name, action, confirm:true}`. All Personas must be confirmed. Every successful single Context confirmation calls `mark_done_if_complete(sid, version)`.

Response example:
```json
{"id":"CL0-P0-C0","personaId":"CL0-P0","docs":30,"nameDraft":"취침 예약","name":"취침 예약","actionDraft":"취침 전에 예약한다.","action":"취침 전에 예약한다.","keywords":["취침","예약"],"dominantConstraint":"전기료","dimsSummary":{},"quality":{"cohesion":0.8,"npmi":0.4},"flags":[],"confirmed":true}
```

### POST `/segment/{sid}/personas/{id}/confirm-contexts`

Body: `{run, contexts:[{id,name,action}]}` (nonempty). Returns only submitted rows in natural ID order. Uses the store's single transaction; an ID outside this Persona or an unknown Context returns 422 with no partial writes. Same Persona-layer gate and stale-generation check as single confirmation. Every success calls `mark_done_if_complete`.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","contexts":[{"id":"CL0-P0-C0","personaId":"CL0-P0","docs":30,"nameDraft":"취침 예약","name":"취침 예약","actionDraft":"취침 전에 예약한다.","action":"취침 전에 예약한다.","keywords":["취침","예약"],"dominantConstraint":"전기료","dimsSummary":{},"quality":{"cohesion":0.8,"npmi":0.4},"flags":[],"confirmed":true}]}
```

### POST `/segment/{sid}/requests`

Body: `{layer:"clusters", id, kind:"split"|"merge", note}`. This records a memo and does not perform structural changes. The committed store only supports Cluster memos; other layer values return 422.

Response example:
```json
{"layer":"clusters","id":"CL0","kind":"split","note":"취침과 낮 시간 사용을 나눠 검토해 주세요.","at":"2026-10-02T00:00:00+00:00"}
```

### GET `/segment/{sid}/docs?context=CL0-P0-C0&band=core&offset=0&limit=100`

Optional filters: `context`, `band=core|fringe|edge`. Defaults: offset 0, limit 100; offset >=0; limit 1..1000. `total` counts all matching rows. Rows are sorted by document ID, with original title/body/comments/url from preparation and decoded assignment/signal fields from segment SQLite, converted to camelCase. Collection `source` is preserved, rather than the stage-five judge source. Missing matches return an empty page.

Response example:
```json
{"run":"6d707a7c-64eb-4023-a87e-657db0c2a270","docs":[{"docId":"doc-1","title":"예약 냉방","body":"취침 전에 예약한다.","comments":[],"url":"","clusterId":"CL0","personaId":"CL0-P0","contextId":"CL0-P0-C0","theta":0.9,"thetaJson":[0.9,0.1],"distCentroid":0.1,"band":"core","comboRarity":0.2,"emerging":null,"lexicalSurprise":null,"sentiment":0.0,"predEntropy":0.0,"evidenceLevel":"core","source":"naver_cafe","authorHash":"author-1","date":"2026-09-01"}],"total":30,"offset":0,"limit":100}
```

## Self-review

- Read the exact brief, design sections 8/9, D-239, and committed store/pipeline/runner interfaces before implementation.
- Session locks cover short writable/version validation and confirmation publication only. Worker launch is outside the lock; tests assert the synchronous pipeline starts without the lock held.
- Run comparisons happen before layer gating for stale clients and again inside the SQLite write transaction. The second check closes the check/write race with pipeline generation publication. The store instance is private to the request; no shared monkeypatching in production.
- Lower-layer gates are global, not limited to the requested parent. An empty previous layer cannot unlock the next layer.
- Context confirmations call the pipeline completion hook after releasing the outer session lock, avoiding nested lock deadlock. Completion counts come from persisted rows; all single and bulk success paths reach the hook.
- JSON projections exclude numpy centroids and internal timestamps. SQL aggregates count documents/authors without loading the complete assignment table into memory. Document originals are streamed and only requested rows retained.
- Confirmation writes and counts remain version-local; API tests also read the old version after activation of a new one.

## Concerns

- Original-document paging has bounded retained memory but can scan preparation JSONL shards to find a late page. An indexed original-text lookup would improve very large-session latency; it is outside the owned files/store contract.
- Shared route errors may contain an additional `error.code`, matching existing routers. Frontend should use `error.kind` and `error.message`.
- Both verification commands reported existing/environment warnings: Pydantic class-based settings configuration deprecation, and joblib physical-core detection falling back to logical cores. No failing tests; the full suite reported 2 deselected tests.
- No blocking concerns remain.

## Fix round 1

The run endpoint now checks the latest version-local segment worker before reset consent. Running or paused workers return HTTP 409 with the new frontend error kind `running` and the exact message `클러스터링이 이미 진행 중입니다.`; the endpoint does not launch another worker in these states, including when `confirmReset:true` or `k` is supplied.

This section supersedes the earlier statement that any existing layer results require reset consent. A session outside `review`/`done`, or a latest worker reporting interrupted/failed/stopped, can resume without reset consent when `k` is absent. The router passes exactly `{'k': None, 'fresh': False}` and returns HTTP 200. Completed results still require `confirmReset:true`, as does an explicit integer `k`. Confirmed resets still pass `fresh:true`; first runs still need no consent. Worker launch remains outside the session lock.

Added parameterized API tests for interrupted, failed, stopped, and stale session/worker state combinations; resume executes the real synthetic pipeline from a checkpoint with drafts pending and verifies that Cluster, Persona, and Context confirmation timestamps and user values survive while the public generation rotates. Tests also cover running/paused conflicts for ordinary, reset, and explicit-k requests, plus `review`/`done` completion regressions. Existing tests retain first-run and fresh-reset coverage.

TDD command (executed before and after the router change):
`backend/.venv/bin/python -m pytest backend/tests/segment/test_api.py -q`

- RED: **11 failed, 20 passed, 2 warnings in 51.25s**, exit 1. Five resume cases incorrectly returned `confirm_required`; six active-worker cases returned the wrong error kind or allowed a reset. Completed-result regression cases passed.
- GREEN: **31 passed, 2 warnings in 48.31s**, exit 0.

Full-suite command (one execution):
`backend/.venv/bin/python -m pytest backend/tests -q`

- Result: **1658 passed, 2 deselected, 2 warnings in 239.47s (0:03:59)**, exit 0.
- `git diff --check`: passed, exit 0.
- Warnings remain the existing Pydantic class-based configuration deprecation and joblib physical-core detection fallback. No blocking concerns.
- Only `backend/app/routers/segment.py`, `backend/tests/segment/test_api.py`, and this appended report section were changed. No git add/commit or subagents.
