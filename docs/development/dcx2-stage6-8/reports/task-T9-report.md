# Task T9 report

- status: complete; focused, context/work and full suites GREEN
- executor: codex
- branch: feature/dcx2-stage6-8

## Files

- `backend/app/segment/pipeline.py`: load → L1 → L2 → L3 → quality → dims → drafts integration, persisted checkpoints, per-Persona L3 state, UUID generations, session publication, stage-six report, completion reconciliation, bounded boundary sampling, draft-call cache and heartbeat adapters.
- `backend/app/work/worker.py`: only the segment function and KINDS registration.
- `backend/app/context/versions.py`: additive restart invalidation for stages 6–8 and default downstream stale coverage through stage 8. Existing stage-3/4/5 code is unchanged.
- `backend/app/segment/store.py`: only `personas.flags_json` and migration of existing SQLite databases (default empty array).
- `backend/tests/segment/test_pipeline.py`: 13 integration/regression tests.
- `backend/tests/context/test_versions_stage6.py`: 10 parametrized restart/worker regression cases.
- `.superpowers/sdd/03-plan/task-T9-report.md`: this report.

No other repository files changed. No network, subagents, reviewers, git add, or git commit.

## RED

Tests were written before the implementation. Command:

`backend/.venv/bin/python -m pytest backend/tests/segment/test_pipeline.py backend/tests/context/test_versions_stage6.py -q`

Result: **1 collection error**, because `app.segment.pipeline` did not exist (0.35s). Log: `/tmp/T9-red.log`.

Initial implementation exposed a text/binary mismatch with the existing `sessions.atomic_write`: **8 failed, 11 passed**. JSON now uses its text contract; NumPy arrays use a flushed/fsynced temporary binary file and atomic rename. The next focused run passed **19 tests**.

Additional RED: mid-draft interruption/replay correctly avoided duplicate calls but lost similarity badges because the heartbeat adapter returned a one-shot Persona generator, while T8 iterates that collection twice. `test_resume_mid_drafts_and_dims_never_repeats_calls` failed on missing badges. Replaced that generator with a reusable list carrying lazy heartbeat iteration. Log: `/tmp/T9-cache-red.log`.

## GREEN

Final focused command, after adding the real worker execution and label-table checks:

`backend/.venv/bin/python -m pytest backend/tests/segment/test_pipeline.py backend/tests/context/test_versions_stage6.py -q`

**23 passed, 2 warnings in 25.14s**. Log: `/tmp/T9-green-final.log`.

Required regression command:

`backend/.venv/bin/python -m pytest backend/tests/context backend/tests/work -q`

**204 passed, 2 warnings in 24.36s**. Log: `/tmp/T9-context-work.log`.

Coverage:

- Real `worker.execute(Context(...))` dispatches segment and publishes durable worker completion, with fake embedder/LLM and the shared external-network guard.
- All 333 retained documents receive exactly one valid Cluster/Persona/Context ID; exported entropy is preserved and KNU sentiment is stored. The synthetic run chooses five clusters.
- Required stage_6 keys, every parameter value, bands, dimensions, call counts, UUID agreement across report/store/session, and review rather than premature done status.
- Stop after L2 skips L1 on resume. Stop after drafts skips all LLM calls on replay. Mid-draft replay preserves parent evidence, avoids repeated calls and retains similarity badges. Mid-dims replay reuses already committed batches.
- L3 and draft heartbeats contain every Persona ID. Long input, clustering and registry work execute with no session lock held.
- Explicit-k rerun clears layer confirmations and segmentDone. Exactly 212 target documents force k=3 and the required Korean warning.
- A synthetic approximately 90% dominant cluster completes, retains nonempty minority clusters, and gives every document one Context.
- L3 receives sentiment_by_id; counter flags persist; failed Persona drafts are retained in personas.flags_json. Existing databases gain the flags column without losing rows.
- Completed and confirmed stage-six sessions restarted from 3/4/5/6 drop segment, segmentDone and drafts.segment; preserve prior versions and shared cache files; mark stages 6–8 stale.
- Critical R3 checks exact stage_3/stage_5 deletion, prep status, training stale replacement, label restart message and retained labeling configuration. Final/queue rows are archived and live final/queue/review_done/route_sync cleared only for 3/4 restarts. Original version rows stay intact.
- Stage-7/8 restarts retain segment confirmations; stage 8 also retains evidence. A live segment worker prevents version creation with 409 through the existing generic worker activity guard.
- A real stage-6 version restart repeats dims with zero additional dims LLM calls.
- mark_done_if_complete returns false for incomplete Context confirmations, then sets done and segmentDone and clears only stale.stage6 after all Contexts are confirmed.

## Full suite

Executed once with the exact requested command:

`backend/.venv/bin/python -m pytest backend/tests -q`

**1613 passed, 2 deselected, 2 warnings in 176.29s (0:02:56)**. Exit 0. No test failures or environment-only failures. The final implementation and tests were in place before this single run began.

Log: `/tmp/T9-full-suite.log`.

## stage_6.json sample

From the real synthetic end-to-end run (333 retained documents). Abridged to one row per layer and one code per dimension; the full output also retains all rows, dendrogram, dims coverage and per-Context dims summaries. All top-level report keys are shown.

```json
{
  "run": "24849b12-7867-474e-8b8c-67ff5dcd0618",
  "input": {
    "relevant": 336,
    "zero_vector": 2,
    "no_tokens": 1,
    "truncated": 0,
    "by_channel": {
      "ppomppu": 67,
      "clien": 67,
      "naver_cafe": 67,
      "naver_blog": 66,
      "youtube": 66
    }
  },
  "L1": {
    "k": 5,
    "silhouette": {
      "3": 0.3460076153278351,
      "4": 0.4357593059539795,
      "5": 0.518386960029602,
      "6": 0.3964659869670868,
      "7": 0.31523996591567993,
      "8": 0.2061302661895752
    },
    "inertia": {
      "3": 160.15814208984375,
      "4": 115.71796417236328,
      "5": 75.10240173339844,
      "6": 74.19020080566406,
      "7": 73.41755676269531,
      "8": 72.58470153808594
    },
    "sample": 333,
    "suggested": 5
  },
  "clusters": [
    {
      "id": "CL0",
      "docs": 84,
      "cohesion": 0.8792363717442467,
      "boundary": 0.0,
      "ari": 1.0,
      "flags": [],
      "channels": {
        "youtube": 0.20238095238095238,
        "ppomppu": 0.20238095238095238,
        "clien": 0.20238095238095238,
        "naver_cafe": 0.20238095238095238,
        "naver_blog": 0.19047619047619047
      },
      "channel_skew": false
    }
  ],
  "personas": [
    {
      "id": "CL0-P0",
      "docs": 36,
      "fallback_assign": 0.0,
      "ari": 1.0,
      "flags": []
    }
  ],
  "contexts": [
    {
      "id": "CL0-P0-C1",
      "docs": 12,
      "cohesion": 0.8947399109601974,
      "npmi": 0.28888888888888886,
      "topics_scanned": {
        "2": 0.2894955722548067,
        "3": 0.2894955722548067,
        "4": 0.2894955722548067,
        "5": 0.29084285760496276,
        "6": 0.29584609031607717,
        "7": 0.2961725465084147,
        "8": 0.29425846080075957,
        "9": 0.29195207946693924,
        "10": 0.29574828479619414
      },
      "flags": []
    }
  ],
  "bands": {
    "core": 0.5015015015015015,
    "fringe": 0.35735735735735735,
    "edge": 0.14114114114114115
  },
  "dims": {
    "sampled": 250,
    "extracted": 250,
    "dims_failed": [],
    "phrase_too_long": 0,
    "empty_goal_or_constraint": 1.0,
    "act_mismatch": 0,
    "codes": {
      "environment": [
        {
          "dim": "environment",
          "code": "environment:0",
          "label": "여름 침실",
          "count": 250
        }
      ],
      "internal_state": [
        {
          "dim": "internal_state",
          "code": "internal_state:0",
          "label": "더위 걱정",
          "count": 250
        }
      ],
      "task_goal": [
        {
          "dim": "task_goal",
          "code": "task_goal:0",
          "label": "편안한 수면",
          "count": 250
        }
      ],
      "activity_response": [
        {
          "dim": "activity_response",
          "code": "activity_response:0",
          "label": "예약 냉방",
          "count": 250
        }
      ],
      "resource_constraint": []
    }
  },
  "llm_calls": {
    "cluster_name": 5,
    "persona_draft": 12,
    "context_draft": 20,
    "dims": 25
  },
  "params": {
    "SEED": 42,
    "WARD_SAMPLE": 20000,
    "K_RANGE": [
      3,
      8
    ],
    "KMEANS_FULL_MAX": 100000,
    "MINIBATCH": 4096,
    "CTFIDF_TOP": 10,
    "REPS": 5,
    "L2_VOCAB": 300,
    "L2_EDGE_MIN_DOC_RATIO": 0.005,
    "L2_RESOLUTIONS": [
      1.0,
      1.2,
      1.5,
      2.0
    ],
    "PERSONA_RANGE": [
      2,
      3
    ],
    "CENTRALITY_TOP": 16,
    "NETWORK_SHOW": 60,
    "L3_TOPICS": [
      2,
      10
    ],
    "CONTEXT_WARN_MAX": 4,
    "L3_MIN_DOCS": 30,
    "LDA_PASSES": 10,
    "DICT_NO_BELOW": 3,
    "DICT_NO_ABOVE": 0.5,
    "BAND_P": [
      50,
      90
    ],
    "COUNTER_SENT_GAP": 0.2,
    "COUNTER_DOC_SHARE": 0.15,
    "COHESION_MIN": 0.6,
    "BOUNDARY_MAX": 0.15,
    "ARI_MIN": {
      "L1": 0.7,
      "L2": 0.6
    },
    "ARI_RESAMPLE": {
      "L1": 5,
      "L2": 3
    },
    "RESAMPLE_FRAC": 0.8,
    "CHANNEL_SKEW": 0.8,
    "DIMS_PER_CONTEXT": 100,
    "DIMS_BATCH": 10,
    "DIMS_PHRASE_MAX": 12,
    "CODE_COS": 0.85,
    "DESIRE_SIMILAR": 0.85,
    "MIN_DOCS_WARN": 300
  },
  "warnings": [],
  "at": "2026-10-02T03:04:32.085883+00:00"
}
```

## Self-review and integration conventions

- Read the T9 brief, design sections 2.1/2.2/3.9/6/7, decisions D-237/D-239, T2–T8 reports and the committed implementations. No parameter constants changed.
- `run(context)` creates a UUID every invocation, including resume, writes `SegmentStore.set_run`, and uses that same UUID in session.segment and stage_6.json. This is separate from the work runner's run_id; T10 should return/use the segment run for confirmation generation checks.
- Resume with `args.resume=true` reuses checkpoints. An unfinished checkpoint also resumes automatically when no k is supplied. A normal completed rerun or explicit-k fresh run clears old layers and local artifacts. T10 remains responsible for the confirmReset user-facing guard and stale_run API validation.
- Checkpoint path: `segment/checkpoint.json`, with `done` in pipeline order, requested k and the current run. Input rows and float16 NumPy vectors are persisted separately; resume memory maps vectors. State includes per-Persona L3 results and original topic-to-column mapping. Step completion is marked only after its result is durable.
- LLM calls still go through `app.llm.registry.run_task` and the committed Pydantic schemas. Since T7/T8 expose no registry injection argument, `_bind` creates run-local function bindings to their existing implementations. No shared module globals are modified. Draft cache keys include task, full prompt and evidence. Cached failures replay as draft_failed; a fresh run retries. Dims uses T7's shared, prompt-hashed cache unchanged.
- `llm_calls` counts registry task requests across the resumed segmentation, including T7 batch retries, but not retries internal to registry.run_task. Cached draft calls and cached dims rows do not increase these counters.
- Reusable heartbeat list adapters retain T8's layer order, cluster-name/persona-desire prompt context and similarity calculation. L2/quality and each step also pulse. The existing worker pulse thread remains responsible for liveness inside a single long algorithm/provider call.
- c-TF-IDF receives nouns. Clustering never receives targetScope; only T8's Persona prompt does. Representative source evidence is supplied for all layers, including Context reps that have no dedicated store column.
- Boundary diagnostics use one deterministic stratified subset capped by WARD_SAMPLE so a minority cluster cannot disappear from the sample; quality.boundary still compares all represented clusters and may return null for mathematically undefined partitions. L2 ARI uses the exact sampled-index adapter from T4.
- Flags are retained in cluster quality, Persona flags_json (L2/ARI/draft), Context flags (including localized counter_context), and T8's meta.draft_flags. Persona draft failures no longer rely solely on metadata.
- Session writes reload the version-specific file under a short lock and preserve unrelated fields. `mark_done_if_complete` calls clear_stale with already_locked=True to avoid reacquiring the nonreentrant session lock. Empty Context sets do not complete stage six.
- Restart changes are additive after the unmodified stage-3/4/5 logic. LLM/noun caches live outside the version and are untouched. Stage-7/8 copies use the existing SQLite backup path and preserve confirmation rows.

`git diff --check`: clean. Final scope inspection found only the six owned source/test files and this report changed.

## Concerns

- No blocking functional concern found; all required suites passed.
- Million-document memory/runtime was not benchmarked. JSON checkpoint state includes document rows, and each completed L3 Persona republishes that state. L1 Ward and repeated LDA costs remain those documented in T3/T5.
- The run-local binding adapter depends on T7/T8 private helper names (`_extract`, `_draft`); future module refactors should preserve those bindings or introduce explicit dependency injection in a separately authorized change.
- Cooperative stops and replay use durable per-call/per-batch caches. A process kill after a provider response but before cache publication retains the usual unavoidable duplicate-call window without provider-side idempotency.
- Existing Pydantic class-config and joblib physical-core detection warnings are unrelated to this implementation.

## Fix round 1

Review findings 1–5 addressed. Scope: `backend/app/segment/pipeline.py`,
`backend/tests/segment/test_pipeline.py`, `backend/tests/context/test_versions_stage6.py`,
and this report. `l2.py` and `versions.py` are unchanged; the stronger historical
regression found no deviation requiring a versions implementation change.
No subagents, reviewers, git add, or commit.

### Changes and covering tests

- R3: `test_restart_stage3_4_5_unchanged` loads and executes `versions.py` from
  commit `e0d124f` against an isolated copy of the same parent session. It compares
  entire new session objects, ignoring only the timestamp and intended D-237
  segment/stage7/stage8 changes. A separate whole-parent comparison removes only
  version, parentVersion, restartFrom, updatedAt, stale, prep, labeling, training,
  segment, completion.segmentDone, and drafts.segment. Nonempty drafts.other,
  completion.other, and stageResults are preserved. Exact downstream stale sets
  are asserted for all restart stages 3–8. Existing report/label-table assertions
  remain in place.
- Cache preservation uses actual `llmcache/{sid}/{prepKey}/cache.json` and
  `prepared_root(sid, parent)/nouns/cache.json` paths with valid derivedRef IDs.
- Draft calls cache successful responses only; old cached failures are ignored.
  `test_draft_cache_retries_failures` verifies both newly failed calls and legacy
  failure cache entries, plus successful replay without another provider call.
  `test_failed_persona_draft_retried_on_resume` fails one Persona draft, stops
  after drafts, then resumes with the provider recovered and verifies retry and
  removal of draft_failed from store/report. A completed drafts checkpoint with
  persisted draft failures is reopened on resume; successful calls retain caches.
- Fresh cleanup preserves every `segment.sqlite*` file; shutil is imported at
  module scope. `test_fresh_cleanup_preserves_sqlite_sidecars` checks journal/WAL/
  SHM sentinels and obsolete artifact removal, stopping before SQLite writes.
  This checks cleanup ownership rather than simulating a real corrupt database.
- T10 args contract is documented in the pipeline module docstring:
  `{'k': int|None, 'fresh': bool}` (defaults None/False). Existing checkpoints,
  including completed runs, resume with k=None and fresh=False. An integer k or
  fresh=True clears layers and confirmations; T10 sends fresh=True only after
  confirmReset. Legacy resume cannot override either reset trigger.
  `test_default_run_keeps_confirmations` covers omitted args and explicit None/
  False on both interrupted and completed checkpoints, prevents L1 recomputation,
  and checks confirmations/names and segmentDone. The existing reset test now
  covers explicit k and fresh=True. Resume preserves session completion and
  reconciles done status after publication.

### Verification

Tests were strengthened before production edits. Initial RED iterations also
caught fixture setup mistakes (invalid preparation IDs); these were corrected
before the final RED run below.

- RED: `backend/.venv/bin/python -m pytest backend/tests/segment/test_pipeline.py backend/tests/context/test_versions_stage6.py -q -k 'default_run or failed_persona or fresh_cleanup or draft_cache or restart'`
  — **8 failed, 9 passed, 15 deselected, 2 warnings in 10.40s** (exit 1).
  Failures reproduce confirmation/completion loss, non-retried drafts, cached
  failures, and sidecar deletion. Historical restart comparisons passed.
  Log: `/tmp/T9-fix1-red-final.log`.
- GREEN (required focused command): `backend/.venv/bin/python -m pytest backend/tests/segment/test_pipeline.py backend/tests/context -q`
  — **211 passed, 2 warnings in 44.55s** (exit 0).
  Log: `/tmp/T9-fix1-focused.log`.
- Full suite, executed once after focused GREEN:
  `backend/.venv/bin/python -m pytest backend/tests -q`
  — **1627 passed, 2 deselected, 2 warnings in 189.29s (0:03:09)** (exit 0).
  Log: `/tmp/T9-fix1-full-suite.log`.
- `git diff --check`: clean. Scope inspection confirms only the three requested
  source/test files changed; the requested report is appended in its existing
  git-ignored `.superpowers` location.

### Concerns

No blocking concern. The historical regression intentionally requires git and
commit `e0d124f` in the checkout (including CI checkouts). The two warnings are
existing Pydantic class-config deprecation and joblib physical-core detection
warnings. This fix section supersedes the original report's descriptions of
cached draft failures and automatic fresh runs after completed checkpoints.
