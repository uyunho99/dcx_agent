# Task T06 report

## Status

Implementation complete. Focused tests pass. The requested full suite was run exactly once and was blocked during collection by concurrently introduced prep tests outside T06 ownership. No commits or git write commands were performed; no packages were installed and no network calls were made.

## Implementation

- `Tags` provides anchor, the six required binary semantic fields, situation, reason_code and signal. `Label` adds all design §2.3 fields, constrained confidence/source/route, and r1/q1 defaults. Rule definitions are imported from the existing rule module; it was not modified. `JevVote` provides probabilities, reason probabilities, returned model and truncation metadata.
- The Korean q1 template defines all tags plus reason_code/signal for sharing with the GPT labeler. Every instruction is within 1,800 characters. It contains positive conditions and form-only negative examples, including the exact phrases “감정어 단독은 0” and “대상과 무관한 행동은 0”, with no requested forbidden domain nouns. `jev_questions(one_liner)` selects the exact eight wire questions; context is placed in state rather than interpolated into the shared template.
- Synchronous `JevClient(keys, model, transport=None)` posts to the supplied public HTTP contract using Bearer authentication and `{doc_id}:q1` idempotency keys. It supports context-manager cleanup and explicit `close()`.
- Request state starts with `[맥락] {one_liner}`, followed by title/body/comments. Legacy desc is accepted as a body fallback. The JSON-serialized string budget includes quotes and escaping, with UTF-8 JSON (`ensure_ascii=False`, matching httpx). A binary search removes comment suffixes before body suffixes. Oversized context/title prefixes and multiline context are rejected as bad rather than silently losing context.
- Each distinct key gets a ChannelLimiter at the configured rate, capped at the public 120/minute limit. Keys rotate between documents. All attempts for one judgment retain the selected key and idempotency key, and each retry passes through the limiter.
- 401 maps to `JevError.code='unconnected'`; 402 to `insufficient` with “Jev 잔액이 부족합니다”; 422 and invalid/incomplete responses to `bad`. 429/502 receive five retries after the initial attempt (six total attempts), with 1/2/4/8/16-second exponential backoff. Exhaustion is bad so the caller can quarantine/requeue it. Network failures become safe bad errors without copying provider bodies or keys.
- Choice distributions must contain exactly the expected option names and finite nonnegative probabilities with positive total. They are normalized by their sum before recovering relate/outcome marginals. Missing questions, malformed payloads and invalid noul values are bad. The response model is retained.
- FakeJev is an offline MockTransport handler with SHA-256 text-seeded deterministic responses and optional caller-supplied fixed responses.

## Exact files created/modified by this task

All implementation/test files below were created, not modifications to pre-existing code:

1. `backend/app/label/schema.py`
2. `backend/app/label/questions.py`
3. `backend/app/label/questions.q1.json`
4. `backend/app/label/jev.py`
5. `backend/tests/label/test_jev.py`
6. `backend/tests/fakes/fake_jev.py`
7. `backend/tests/fixtures/jev/success.json`
8. `.superpowers/sdd/03-plan/task-T06-report.md` — this requested report.

Neither `backend/app/label/rule.py` nor `__init__.py` was modified. No vector, Voyage, prep or preprocessing files were edited. Concurrent changes were preserved.

## TDD evidence

### RED — tests written before implementation

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_jev.py -q
```

Exit 2, expected missing implementation:

```text
ERROR collecting tests/label/test_jev.py
from app.label.jev import JevClient, JevError, build_state
E   ModuleNotFoundError: No module named 'app.label.jev'
ERROR tests/label/test_jev.py
Interrupted: 1 error during collection
1 warning, 1 error in 0.09s
```

### GREEN — minimum implementation

Same focused command, exit 0:

```text
......................................... [100%]
41 passed, 1 warning in 0.08s
```

### Review and refactor

Added nine coverage cases for malformed top-level payloads, non-JSON responses, safe transport errors, untruncated state and configured rate. Focused run: `50 passed, 1 warning in 0.08s`.

Refactored the Label question-version default to import QVER instead of duplicating its literal. The final focused command was again:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_jev.py -q
```

Exit 0:

```text
.................................................. [100%]
50 passed, 1 warning in 0.08s
```

The warning is the existing Pydantic class-based Config deprecation in `app/config.py:12`.

## Full suite — exactly one invocation

Command:

```sh
cd backend && .venv/bin/python -m pytest -q --ignore=tests/vectors
```

Exit 2:

```text
ERROR collecting tests/prep/test_pipeline.py
from app.prep import pipeline
E   ImportError: cannot import name 'pipeline' from 'app.prep'
    (.../backend/app/prep/__init__.py)
ERROR tests/prep/test_pipeline.py
Interrupted: 1 error during collection
1 warning, 1 error in 1.83s
```

This is outside T06 ownership: prep files/tests appeared during parallel work. The full suite did not execute tests, so this report does not claim a full-suite pass. No second full-suite invocation was made.

## Self-review

- Exact question names, request URL/method/model/headers, state first line and serialized size tested.
- Recovery from {.1, .2, .6, .1} yields relate .3 / outcome .7; both choice distributions normalize a .97 total.
- Each of eight missing answers is independently covered. Out-of-range, NaN, nonnumeric and boolean probabilities are rejected, as are missing/zero/negative choice distributions.
- Comment-before-body truncation, escaped characters, desc fallback and oversized context covered.
- Authentication/credit/request errors, retry success on the fifth retry, exhaustion, stable retry key, distinct-key deduplication/rotation and configured limiter interval covered.
- Schema roundtrip and invalid confidence/semantic tags covered. Fake determinism and fixed fixture override covered.
- `git diff --check` exited 0 for tracked changes. Final status also showed concurrent prep/preprocessing changes; those were not touched.

## Concerns and integration notes

1. Full regression status is unknown until the concurrent prep implementation is complete. Controller should run the suite afterward.
2. Rate limiting is scoped to a JevClient/key pool, using the existing in-process ChannelLimiter. Workers should reuse one client per pool. Multiple independent clients/processes sharing the same real key need coordination at the worker level to enforce the aggregate provider quota.
3. `bad` is surfaced to the caller; document quarantine/requeue, worker pause/stop, settings-based backend selection and persistence are downstream worker responsibilities, not T06 mutations.
4. The fake is deliberately supplied as a test transport in `tests/fakes/fake_jev.py`; no production factory or configuration module was changed.
5. Real-provider smoke testing was not performed under the no-network constraint. The supplied 2026-09-30 contract was used verbatim as the HTTP source of truth.
6. Long or non-ASCII/control-containing document identifiers that cannot satisfy the <=100-character HTTP idempotency-key contract are rejected as bad. Oversized context/title prefixes are also rejected after exhausting the permitted comment/body truncation.

## Fix round 1

- Added keyword-only `idempotency_key: str | None = None` to `JevClient.judge()`. Omitted/None values retain `{doc_id}:{QVER}`; caller values are sent unchanged on every attempt. Validation retains the existing ASCII 33–126 and 100-character maximum constraints and rejects empty/non-string overrides before sending a request.
- Moved limiter ownership to a process-wide pool keyed only by SHA-256 API-key fingerprints. A lock protects lookup/creation, so clients sharing a key share the same ChannelLimiter and request-start schedule. Distinct keys remain independent. `reset_limiter_pool()` clears test state and must only be used with no active clients; test fixtures reset before and after each case. Rates are configured when each pooled limiter is first created.
- This supersedes integration note 2 above for clients within one process. Separate processes still require external coordination.
- Added 13 regression cases: exact custom headers across all six attempts for both 429 and 502, including the 100-character boundary; invalid caller keys rejected without transport calls; and two clients alternating requests under a fake clock at both 60/min and 120/min, checking request spacing, every rolling minute, and hashed pool keys. Existing default-header, key-rotation and configured-rate coverage remains green.
- Files changed: `backend/app/label/jev.py`, `backend/tests/label/test_jev.py`, and this report. No parallel-owned files were edited, no network was used, and no git write commands or commits were performed.

Command for both RED and GREEN:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_jev.py -q
```

RED output (exit 1, relevant excerpts):

```text
..................................................FFFFFFFFFFFFF          [100%]
E   TypeError: JevClient.judge() got an unexpected keyword argument 'idempotency_key'
E   assert False
    assert all(b - a >= 60 / rate for a, b in zip(starts, starts[1:]))
13 failed, 50 passed, 1 warning in 0.18s
```

The 11 override cases failed on the missing keyword parameter; both fake-clock cases failed because separate clients started requests without aggregate spacing.

GREEN output (exit 0):

```text
...............................................................          [100%]
63 passed, 1 warning in 0.11s
```

Both runs emitted the existing Pydantic class-based Config deprecation warning at `app/config.py:12`.
