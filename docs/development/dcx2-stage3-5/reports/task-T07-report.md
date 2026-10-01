# Task T07 — GPT 라벨러 report

## Implementation

Implemented the `label_gpt` task and synchronous batch judge using the shared LLM layer. `build_task(docs, one_liner)` creates `LLMTask` with `GptBatch{items: list[GptItem]}`. `judge_batch(docs, one_liner, *, sid, ctx_key, qver=QVER)` returns `(dict[str, GptVote], list[str])`. T08 supplies the session/context identity, schedules batches using `settings.label_batch_size` (20 by default), and owns pending/lease transitions. This function processes one supplied batch; it does not create a worker or split batches internally.

The versioned prompt's first line is the exact one-liner. Definitions and criteria are inserted verbatim from `load_questions()` at runtime; no duplicate definition text is maintained. The decision table is derived from `rule.grade` using `SEM` and `GRADE_FIELDS`, keeping executable grade rules in their existing single source. The prompt asks for semantic tags before signal; returned Non signals are cleared using that same rule.

Backend selection uses `settings.label_gpt_backend`, independently of the existing general-purpose LLM default/overrides. Codex calls real `run_many([task], run_id=..., concurrency=settings.label_concurrency)`; API calls use `OpenAIApiBackend`; fake mode uses `FakeBackend` with deterministic, conservative Non responses and requires no new fixture file.

Run IDs are `lbl-{sid}-{qver}-{ctx_key}-{digest}`, where digest is the first 12 hex characters of SHA-256 over UTF-8 compact JSON of sorted document IDs (`ensure_ascii=False`, separators `(',', ':')`). Both document order and JSON keys are canonicalized in task inputs, so reordering an unchanged batch resumes its existing manifest. Missing subsets get different run IDs. Identity components reject path separators, and unsupported question versions are rejected.

Response validation retains valid unique items, discards foreign/malformed items, and requeues missing or duplicated requested IDs. Duplicate IDs are treated as ambiguous rather than choosing one arbitrarily. Invalid envelopes requeue the whole batch. A Codex answer containing zero usable requested votes is moved to its existing `answers/bad/` directory, preventing an identical retry from replaying an unusable cached answer forever. Valid partial answers remain cached for resumability.

`LabelerPaused` signals operational backend failures. Since the shared Codex runner deliberately returns a generic error, the labeler inspects only its own latest worker-log attempt to recognize usage-limit messages and emit the exact design message:

> GPT 판정이 사용량 한도로 멈췄습니다. 잠시 뒤 이어서 진행하거나 설정에서 API 경로로 바꾸세요.

No provider log content is included in exceptions. Other operational failures get a generic safe pause message; parse/schema failures return retry IDs instead.

## Exact files created/modified

Created:
- `backend/app/label/gpt.py`
- `backend/app/label/prompts/gpt_label.q1.md`
- `backend/tests/label/test_gpt.py`
- `.superpowers/sdd/03-plan/task-T07-report.md` (this required report)

Modified:
- `backend/tests/fakes/fake_codex.py`

The fake executable now recognizes label-batch prompts and supports normal, partial, and usage-limit label responses via `FAKE_CODEX_LABEL_MODE`. Existing value, bad-schema, and sleep/child-process behaviors are preserved.

Did not edit the parallel T04 implementer's `backend/app/prep/*`, `backend/tests/prep/*`, or `backend/app/services/preprocessing.py`. No git write command or commit was performed. No network or real Codex CLI was used.

## TDD evidence

### Initial RED, before implementation

Command:
```sh
cd backend && .venv/bin/python -m pytest tests/label/test_gpt.py -q
```
Result: `1 failed, 1 warning, 10 errors in 0.06s` (exit 1).

Expected causes: `ImportError: cannot import name 'gpt' from 'app.label'` for module-dependent tests, and `FileNotFoundError` for `prompts/gpt_label.q1.md`. All six named brief tests were present before implementation: first-line context, no domain examples, partial requeue, two batches plus real-runner retries, default Codex selection, and usage-limit pause. Additional tests covered explicit API/fake routing and an empty input batch.

### Initial GREEN

Command:
```sh
cd backend && .venv/bin/python -m pytest tests/label/test_gpt.py tests/llm -q
```
Result: `36 passed, 1 warning in 1.73s` (exit 0).

### Self-review RED → refactor → GREEN

A typed `GptItem` construction regression was added before fixing its validator normalization:
```sh
cd backend && .venv/bin/python -m pytest tests/label/test_gpt.py::test_batch_accepts_typed_items -q
```
RED: `1 failed, 1 warning in 0.20s`; expected `['a']`, got `[]`. Refactored normalization before counting IDs. The focused suite then reported `43 passed, 1 warning in 1.80s`.

A real-runner regression demonstrated that a cached empty answer could never recover:
```sh
cd backend && .venv/bin/python -m pytest tests/label/test_gpt.py::test_empty_answer_can_retry_same_batch -q
```
RED: `1 failed, 1 warning in 0.30s`; retry still returned no votes. Added quarantine for zero-usable-vote Codex answers.

Final focused command:
```sh
cd backend && .venv/bin/python -m pytest tests/label/test_gpt.py tests/llm -q
```
GREEN: `44 passed, 1 warning in 1.63s` (exit 0). Includes 19 label test cases and all 25 existing LLM tests. Tests set `settings.codex_bin` to the existing fake executable and use temporary data roots.

## Full suite

Command (run once, as requested):
```sh
cd backend && .venv/bin/python -m pytest -q --ignore=tests/prep --deselect tests/crawl/test_final_w5.py::test_finish_partial
```
Result: `934 passed, 2 deselected, 2 warnings in 99.62s (0:01:39)` (exit 0). Warnings: existing Pydantic class-based settings deprecation and joblib physical-core detection falling back to logical cores.

Timing note: the full suite was launched after the 43-test focused GREEN. The cached-empty-answer regression and fix were added while that run was active. The final focused 44-test GREEN verifies the final implementation; the full-suite collection does not include that final new regression. The full suite was not rerun, honoring the request to run it once.

## Self-review and concerns

- Confirmed exact shared definitions are used by testing a runtime mutation of the loaded definition text; verified the banned domain nouns are absent from both template and shared JSON.
- Confirmed independent batches, subset retries, context changes, and order-insensitive resumption through the real manifest-enforcing runner with the fake executable.
- Confirmed missing IDs, duplicate IDs, foreign IDs, missing semantic fields, malformed envelopes, empty inputs, explicit backend choice, and usage-limit recovery.
- The existing shared LLM transport prepends its own system context/output-file instructions. The label task's instruction text and prompt template begin with the one-liner; changing the transport wrapper would require edits outside T07 ownership.
- Usage-limit recognition depends on human-readable Codex log markers because the shared runner does not expose a structured quota error. Unknown quota wording still pauses safely with the generic execution-failure message.
- The caller must keep `ctx_key` aligned with context/question/model changes; changed inputs/settings under the same identity intentionally remain a runner failure. The caller also owns batch-size scheduling and persistence of pending work after `LabelerPaused`.
- Partial responses retain valid votes and requeue ambiguous/missing IDs as the brief's Review Focus 2 requires. They are not rejected wholesale as the older design paragraph suggested.
- Existing Pydantic settings deprecation warnings remain outside T07 scope.
- `git diff --check` passed. Parallel T04 changes were preserved.
