# Review-fix1 backend report

Requirements: `.superpowers/sdd/03-plan/review-fix1.md`; findings: `codex-branch-review1.md` and `gstack-review1.md`; ruling: R-111 in `docs/development/dcx2-stage3-5/decision-log.md`.

## Scope

Implemented C1–C6 and G2–G6. C4's backend contract is `overview.trainable`; frontend consumption, C7, and G1 belong to the parallel frontend job. This job edited only `backend/`, `.env.example`, `README.md`, and this explicitly requested report. No commits, package installation, subagents, or live provider calls. Existing decision-log/review-report changes and the parallel frontend edits were left alone.

## TDD evidence

Added `backend/tests/test_review_fix1.py` before implementation and ran it against the original application. All **17 cases failed** (3.19 s), with a defect-specific failure for every assigned item. An initial test-only correction used the existing `Label.evidence_level` field and an immediate HTTP error response to avoid retry delays; the recorded 17-case RED run followed those corrections and preceded application edits. After implementation, the same 17 cases passed (2.23 s).

Expanded coverage then added real environment-configured subprocesses, compatibility service guards, unchanged-ref reuse, unsafe-cache invalidation, and failures at four export boundaries. The focused review and prep-pipeline run passed **53 tests** (8.73 s).

| Item | RED observed before implementation | GREEN behavior and coverage | Implementation files (under `backend/app/` unless noted) |
|---|---|---|---|
| C1 | Audit response was `non`, persisted human projection was `core`. | Recomputes grade with `rule.grade`; unchanged requires equal tags **and** grade. Model confirmations also save the recomputed grade. Regression uses four agreeing members with anchor/situation `.99`, semantics `.4`, null optional tags; stored result is human/audited/Non and reconciliation is idempotent. | `label/audit.py`, `label/route.py` |
| C2 | Identical run IDs for the same document IDs with different bodies. | Execution context hashes the canonical prepared prompt plus caller context; that context hash appears in the run ID. Changed body gets a new ID; unchanged retry stays stable. Existing real `run_many` reorder/retry coverage remains passing. | `label/gpt.py` |
| C3 | Both `/prep/run` start/reuse and legacy `/preprocess` returned 200 for unfinished collection. | Shared guard requires `crawl.control.phase_state(...)=done`, before start/reuse and again in workers/publication. Both HTTP entry points return 409 with the exact required message. New manifests record `collectionFinalized=true`; older results without provenance are rebuilt, including docs/tokens/vectors, instead of resuming an unsafe snapshot. Tested API rejection, legacy direct-service rejection, old-cache rejection after finalization, and pipeline rebuild with changed document IDs. | `prep/guards.py` (new), `routers/prep.py`, `routers/preprocessing.py`, `services/preprocessing.py`, `prep/pipeline.py` |
| C4 | `KeyError: trainable` with human-only labels. | Exposes `overview.trainable` from the same SQL predicate used by training: human rows regardless of route, or accepted agreed rows. Counts prepared documents with finite, nonzero vectors. Regression has 40 usable human-only labels across audited/escalated:human routes plus zero/missing-vector rows; accepted=0, trainable=40, matching worker features. | `model/dataset.py` (new), `label/overview.py`, `routers/training_v2.py` |
| C5 | Fake setting reached MockTransport through real HTTP and raised `JevError`. | Both worker paths select deterministic `FakeJevClient` through the real `get_jev_client` factory. No HTTP client or credential is required in fake mode. Factory tests assert zero requests and repeatable votes. Separate judge and monitor subprocesses load `JEV_BACKEND=fake` from the environment, retain the real factory, install MockTransport at the HTTP boundary, finish all three documents, and assert zero requests. | `label/jev.py`, `label/judge.py`, `model/monitor.py` |
| C6 | Published export had no generation-local `stage_5.json`; paths were reused across exports. | Fresh `classified/{sid}/{version}/gen-{uuid}/` holds all three artifacts. Files and directories are fsynced before publishing exportRef/allRef/stage5Ref together via atomic session update under the session lock. Injected failures during all.jsonl, relevant.jsonl, stage_5.json, and before pointer publication preserve the old reference and every old artifact byte. Successful retry publishes a new generation. `read_export` reads both old/new references; training status reads generation-local stage5Ref. | `model/export.py`, `routers/training_v2.py` |
| G2 | `prevSeenAt` was absent. | `/seen` saves old lastSeenAt as prevSeenAt, then updates lastSeenAt. Overview uses prevSeenAt, with fallback for pre-migration sessions. Two visits and repeated polls retain changes since the previous visit. | `routers/labeling_v2.py`, `label/overview.py` |
| G3 | Unknown dotenv keys raised `extra_forbidden`. | Settings uses `extra='ignore'`; regression includes obsolete PINECONE_API_KEY in both process environment and dotenv plus an unrelated unknown key. Removed obsolete key from root template and README. | `config.py`, root `.env.example`, root `README.md` |
| G4 | Fixture, other, and absent channels raised `ValueError` from tuple.index. | Unknown/missing channels leave the existing five one-hot columns zero; vector and scalar features retain the 1032-column contract. | `model/features.py` |
| G5 | Both prep HTTP entry points returned 200 after labeling started with a changed derivedRef. | Shared guard invokes `assert_labeling_not_started` when computed ref changes, including the legacy v2 service and pipeline publication. Exact R-106 message verified. Same verified ref remains reusable after labeling starts. | Same prep files as C3 |
| G6 | README/template still contained PINECONE_API_KEY and README omitted stage settings. | README describes local float16 vector search and lists all stage 3–5 setting names from Settings, including VOYAGE_API_KEY, JEVMODEL_API_KEY, EMBED_*, JEV_*, LABEL_*, audit/model/monitor/Known settings and offline fake setup. No credential values added. Documentation regression checks removal and setting coverage. | Root `README.md`, `.env.example` |

Exact prep message: `수집이 끝난 뒤에 전처리를 실행할 수 있습니다.`

Exact changed-ref lock message: `라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.`

## Compatibility and verification details

- Search and clustering already call `known/filter.py:read_export`, which resolves the exact exportRef, requires the filename `relevant.jsonl`, and bounds it under `classified/{sid}`. Nested generation paths satisfy those constraints; the validation was not relaxed.
- Previous export generations are retained, including more than two when present. Pruning was optional; retaining them also protects references inherited by historical versions. Interrupted unpublished generations can remain on disk.
- The version-local `stage_5.json` compatibility copy is written atomically; exported report consumers use the generation-local `stage5Ref` for consistency with exported data. Monitoring can still update the compatibility report without rewriting published export files.
- Existing tests were updated for intentional contract changes: generation/run paths, previous-visit counts, missing-collection guard message, and finalized crawl fixtures. Prep fixtures now declare the same fake embedder identity they actually inject. No production guard was bypassed to make fixtures pass.
- Additional modified tests: `tests/label/test_gpt.py`, `tests/label/test_label_api.py`, `tests/model/test_export.py`, `tests/prep/test_pipeline.py`, `tests/test_integration_stage0_2.py`, and `tests/test_integration_stage3_5.py`.
- `git diff --check -- backend .env.example README.md`: passed.

## Full backend verification

Final required command: `backend/.venv/bin/python -m pytest backend/tests -q` (from repository root).

**Result: 1244 passed, 2 warnings in 120.14 s (2:00), exit code 0.** The warnings are the existing Pydantic class-based Config deprecation and joblib physical-core detection fallback. No failures or errors remain.

Earlier full run identified 29 failures and 3 setup errors from superseded test expectations/fixtures (1201 passed). Those tests were updated as described above; focused reruns passed before the final whole-suite run.

Status: all 11 assigned backend/documentation items complete; final backend suite GREEN.
