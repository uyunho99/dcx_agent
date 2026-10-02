# Stage 7 browser QA fix round 3

Date: 2026-10-02. Branch: `feature/dcx2-stage7`.

## Status

E-F8, E-F9, E-F6, E-F5 and the E6 QA hook are implemented. E-F7 has a prompt/input-contract mitigation, but **the critical real-provider rejection diagnosis and real-shaped regression remain unverified** because this execution environment cannot resolve `api.openai.com`. No API keys were printed. No git add/commit, subagents, or port 8320/8323 process changes were made. The pre-existing decision-log edit was left intact.

## E-F7 — diagnosis and mitigation

Diagnostics ran with the worktree `backend/.venv/bin/python`, with cwd/imports pointing at the supplied `scratchpad/l2root/backend` copy so its parent `.env` was loaded. The effective tag model was `gpt-6.1-sol`. Direct backend calls bypassed registry schema retries and captured the validator input when available.

Two transport-failing diagnostic passes were attempted. For each of `evidence.tag`, `evidence.queries`, and `evidence.novelty`, the observed result was:

```text
result.ok = False
result.error = kind='backend' message='OpenAI request failed'
raw = None
```

An independent DNS check returned `gaierror [Errno 8] nodename nor servname provided, or not known` for `api.openai.com`. There was no model response to sanitize or turn into a captured regression fixture. These are transport failures, not evidence that the schema rejected a particular real output. No synthetic response is represented as captured real output.

Code inspection confirmed attachment titles are included by `compose()`. The tag prompt previously did not explicitly identify those titles as the IDs to copy, and the Claude transport does not itself transmit the Pydantic schema. The tag request now embeds `doc_id` inside each document JSON and appends the full output schema in its instructions. The prompt explicitly specifies exact ID copying, object wrapping, required/null fields, enum values, neutral polarity, quote indexes, and literal quotation. Its changed bytes produce a new prompt-version cache filename. Schema validation and rejection of unknown IDs remain strict; unsupported guesses about real output variants were not added.

Offline regression verifies explicit IDs and schema reach the task. Existing tests retain coverage of invalid schemas, alien IDs, missing-ID retry, and exact quote preparation. Queries and novelty were attempted diagnostically but received no provider output; no unsupported parsing changes were made to them.

## Implemented fixes

- **E-F8:** A nonempty Context candidate pool with at least 90% missing tag judgments fails with `근거 원문을 태깅하지 못했습니다. 다시 시도하세요.` Checks run after initial tagging and after expansion. Failed candidates remain in the store for accurate untagged reporting. Valid `relevant=false` judgments count as successful tags. Regression covers zero/one surviving judgment, retry recovery, valid irrelevant-only results, and isolated fake failure/skip flow.
- **E-F9:** Tag and Known Insight reads used for tagging/judging filter by the current task model. Retagging also removes that document's other-model Known Insight judgments. Same-model cache reuse and content-fingerprinted incremental KI behavior remain; D-256 embedding behavior is untouched. Regression switches models and requires fresh tag/KI judgments. Two older cache tests now seed the current model instead of an unrelated hard-coded model.
- **E-F6:** Stage 7 is routed to a dedicated evidence comparison before the generic file-shape detector. Korean report metrics and per-Context all/new selection counts include added/removed IDs, so equal-sized replacement selections remain visible. Null/missing report sides render safely. Static-render tests assert no `Invalid Date`.
- **E-F5:** Restarting stage 7 now navigates to `/pipeline/evidence`.
- **E6 hook:** `make_segment_qa.py DATA_DIR --confirm-all --fail-context CL0-P0-C1` writes a session-local `qa-evidence.json` listing that Context's documents. Only the fake echo tagger omits their judgments. Other Contexts remain usable. Remove `DATA_DIR/sessions/SID/qa-evidence.json` before retrying to allow successful fake tagging; leave it present to test repeated failure and skip-and-proceed. The parser rejects unknown Contexts and requires `--confirm-all`.

## Validation

- Full default backend suite, once: `backend/.venv/bin/python -m pytest backend/tests -q` → **2004 passed, 2 failed, 3 deselected**, 403.97 s. The three `perf` tests are excluded by the repository's default `addopts = -m "not perf"`.
- Both failures were old fixtures inserting cache rows with model `fake` while the test task's configured model differed: `test_restart_from7_reuses_tag_cache` and `test_handed_and_semantic_known_api_fields_and_refresh_isolation`. Their seeds now use `_model()`. Targeted rerun of both → **2 passed**. The full suite was not rerun a second time; there is no all-green single full-run result to claim.
- Focused tagging/pipeline/echo suite → **47 passed**; additional isolated fake-failure/skip and valid-irrelevant-only regressions → **2 passed**. The four initial new ID/schema/model/failure cases were observed failing before implementation.
- `npm --prefix frontend test` → **56 files, 560 tests passed**.
- `npm --prefix frontend run lint` → **passed**.
- `git diff --check` → passed. No Next build was run.

Logs: `/private/tmp/dcx-fix3-backend-tests.log`, `/private/tmp/dcx-fix3-frontend-tests.log`, `/private/tmp/dcx-fix3-lint.log`.

## One fresh QA-L2 real-provider rerun

After validation, rsynced the worktree backend into the supplied `l2root/backend`, excluding `.venv`, `.env`, data and Python/test caches. Existing L2 tag SQLite files were moved, with sidecars if present, into `scratchpad/fix3-tag-cache-backup`. No server was stopped or restarted.

Executed `/private/tmp/dcx_rerun3.py` from that backend copy using the worktree venv and the real configured LLM, for session `segment-synth-cfcc8d85d6f0`, active version `v2`, with `fresh=True` and the three CL0-P0 Context IDs. No fake LLM override was used.

| Metric | Rerun result |
| --- | --- |
| Model | `gpt-6.1-sol` |
| Final state | `interrupted`, `_LLMUnavailable` |
| Query task calls | 2, both unavailable |
| `tag_calls` | **0** |
| Candidates attempted | **0** |
| `untagged` | **Not computed**: interrupted before candidate tagging/report assembly |
| CL0-P0-C1 | queued; all/new selections **0/0** |
| CL0-P0-C2 | queued; all/new selections **0/0** |
| CL0-P0-C3 | queued; all/new selections **0/0** |
| Verified sample quotes | **Unavailable**, no evidence package produced |
| `relevant=false` reason codes | **Unavailable**, no tag judgments produced |

The interruption reason was `LLM이 연결되지 않았거나 한도를 넘었습니다. 연결을 확인한 뒤 이어서 진행하세요.` These zero selections are unprocessed Contexts, not successful empty evidence results. They do not demonstrate that the original 40-call/120-untagged defect is fixed.

Full machine-readable outcome: `/private/tmp/dcx-fix3-rerun.json`; stdout: `/private/tmp/dcx-fix3-rerun.log`. Diagnostic and rerun scripts remain in `/private/tmp` for review; neither contains API credentials.

## Remaining concern

E-F7 remains a release blocker pending network-enabled real diagnostics, a sanitized captured-response regression, and a successful fresh 3-Context rerun with quote verification and reason-code reporting. The prompt mitigation is not a confirmed diagnosis. Browser interaction itself was not rerun; comparison rendering and failure/retry/skip behavior were exercised offline. The existing 8323 process was left untouched and may still hold its previously imported code.

## Controller real-LLM verification (network-enabled, 2026-10-02)

- Root cause confirmed by controller probe: the real model returned `{"items": []}` because the tag prompt did not name the requested doc IDs; with explicit IDs it returned full items.
- After this fix (IDs embedded per document + exact-copy instruction), fresh QA-L2 rerun on 3 Contexts of CL0-P0: tag_calls 21, untagged 5/120, LLM calls 25 (tag 21 · queries 1 · novelty 3), every Context all 10 / new 10 / coverage 6/6, sampled quotes verified=true (comment field), queries first-person without forbidden words, novelty "none" on repeated synthetic sentences.
- E-F7 resolved. Captured-response regression: the offline tests cover IDs/schema reaching the prompt; a sanitised real response fixture can be added later (low risk).
