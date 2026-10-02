# T1 implementation report — D-246 / D-249

Status: **DONE_WITH_CONCERNS** (nonblocking interrupted-resume limitation below).

## Scope and files changed

Worktree: `/Users/persona1/Desktop/dcx_agent-stage7`; branch: `feature/dcx2-stage7`.
Requirements read: `.superpowers/sdd/03-plan/task-T1-brief.md` and section 5 of `docs/development/dcx2-stage7/02-design.md`. No AGENTS.md files were found in the worktree or checked ancestor directories.

- `backend/app/segment/stopwords.py` (new): one editable `STOPWORDS: frozenset[str]` containing 115 entries; `is_stopword`, ordered `filter_words`, and deterministic `stopwords_signature`. Signature uses SHA-256 of sorted, newline-separated UTF-8 entries, truncated to 12 hex characters. Current signature: `{"count": 115, "hash": "e02196395444"}`.
- `backend/app/segment/l2.py`: filter before document-frequency vocabulary selection and graph construction; preserve `personas(cluster_ids, nouns, bk)` signature.
- `backend/app/segment/ctfidf.py`: preserve raw-token score calculation, filter the full ranking, then take `top` so lower-ranked eligible words fill gaps. Optional `bk=None` preserves existing two-argument callers.
- `backend/app/segment/l3.py`: add optional keyword-only `bk`; filter only ranked topic output after model selection and posterior inference. Training dictionary, corpus, coherence, model parameters and assignments are unchanged. This file is needed by the explicit L3 requirement despite its omission from the brief's ownership-table shorthand.
- `backend/app/segment/pipeline.py`: pass session `projectContext.bk` to cluster and Context keyword filtering; record stopword metadata in new checkpoints and `stage_6.json.params`. Completed resumes retain their original signature; legacy checkpoints are not falsely labeled with the current signature.
- `backend/tests/segment/test_stopwords.py` (new): all seven named acceptance tests, including real LDA comparisons for two fixed Personas, vocabulary-cap ordering, ranking refill, empty/all-filtered input, mutable-list fingerprinting, pipeline product propagation, and completed/legacy resume preservation.
- `backend/tests/segment/test_l1.py`: use two-character synthetic tokens so existing tie/corpus-frequency tests continue to test ranking under the new one-character exclusion rule.
- `backend/tests/segment/test_l2.py`: use two-character synthetic tokens so the existing edge-threshold test remains meaningful rather than passing because its tokens are now stopwords.
- `backend/tests/segment/test_pipeline.py`: update exact parameter contract for stopword metadata and forward optional `bk` through an existing L3 test wrapper.
- `.superpowers/sdd/03-plan/task-T1-report.md`: this report.

## TDD: RED

Wrote the seven requested tests before creating the implementation module.

Command:

```sh
backend/.venv/bin/python -m pytest backend/tests/segment/test_stopwords.py -q
```

Result: exit 2; **1 collection error, 1 warning, 39.81s**. Expected failure: `ImportError: cannot import name 'stopwords' from 'app.segment'` because the module did not exist.

## Implementation and GREEN

Same command:

```sh
backend/.venv/bin/python -m pytest backend/tests/segment/test_stopwords.py -q
```

Initial implementation run: 6 passed, 1 failed (8.63s). The L2 fixture used one small clique, which the existing resolution/unsupported-community behavior can eliminate. Replaced it with two supported noun communities; did not change L2 clustering behavior to satisfy the fixture.

First GREEN: **7 passed, 2 warnings, 7.44s**.

Strengthened self-review coverage for filtering before the vocabulary cap and preserving completed/legacy results on resume. The first added snapshot assertion encountered NumPy array equality ambiguity (6 passed, 1 failed, 7.11s); changed the test snapshot to use the existing JSON serializer.

Final GREEN: exit 0; **7 passed, 2 warnings, 7.44s**. Warnings are existing Pydantic class-config deprecation and joblib physical-core detection fallback in this environment.

Refactor review: kept filtering in the single shared module and ranking separate from filtering; no unrelated refactor was needed. Existing ranking/edge test tokens and test adapters were updated only where the new contract required it.

## Regression

Command (run once):

```sh
backend/.venv/bin/python -m pytest backend/tests/segment -q
```

Result: exit 0; **221 passed, 1 deselected, 2 warnings in 137.02s (0:02:17)**. The two warnings are the same Pydantic deprecation and joblib core-detection fallback noted above. No regression rerun was performed.

## Self-review

- All specified rules are exercised: common-list entries, one-character words, digit-only words, product names ignoring whitespace, and product-containing compounds. Empty/whitespace product names do not accidentally exclude every word.
- `filter_words` preserves order, spelling and duplicates and accepts an iterable.
- L2 removes noise before the vocabulary cap, centrality and network construction. Its public signature is unchanged.
- c-TF-IDF counts and scores retain raw tokens; only selected keywords change.
- Real LDA selection over 2–10 topics has exactly equal full scan results, topic IDs, hard assignments and full posterior vectors with output filtering disabled/enabled for each of two fixed Personas. This invariant is for fixed Persona membership; L2 filtering may intentionally change membership.
- Pipeline integration verifies product-name propagation and persisted report metadata using the offline fake backends and unchanged socket guard.
- Completed resumes preserve stored rows and their original fingerprint, including legacy results without stopword metadata.
- `git diff --check` passed.
- No subagents, external network calls, staging or commits. Parallel workers' embedder, evidence, fixtures, QA script and decision-log changes were not edited or reverted.

## Concerns

- Nonblocking resume limitation: if the stopword list is edited while a run is interrupted after some keyword-producing stages, a resume can combine cached output with newly filtered output; the checkpoint retains its original signature. Use a fresh stage-6 rerun after editing the list to ensure one filter version throughout. Completed cached results are explicitly covered and remain unchanged.
- Legacy checkpoints intentionally have no stopword metadata until a fresh run; assigning the new signature to their cached keywords would be misleading.
- Performance-marked tests are outside the requested default regression command.

## Fix round 1

Status: **DONE**. Removed domain-meaningful words `가격`, `구매`, `구입`, `추천`, and `사진` from `backend/app/segment/stopwords.py` so they remain eligible keywords and Artifact candidates. The list now contains 110 entries (within 80–150); no replacement words were necessary. Updated signature: `{"count": 110, "hash": "8a4b83a529a7"}`.

Added `test_domain_words_not_stopwords` in `backend/tests/segment/test_stopwords.py`, asserting `is_stopword(word, '') is False` for all ten requested words: 가격, 구매, 구입, 추천, 사진, 냉방, 소음, 전기료, 필터, 설치.

TDD verification:

- RED, before changing the list: `backend/.venv/bin/python -m pytest backend/tests/segment/test_stopwords.py -q` → **1 failed, 7 passed, 2 warnings in 7.89s**; the new test failed on 가격 as expected.
- GREEN, after removing the five words: same command → **8 passed, 2 warnings in 7.79s**.
- Regression, run once: `backend/.venv/bin/python -m pytest backend/tests/segment -q` → **222 passed, 1 deselected, 2 warnings in 144.16s**.

Concerns: no new concerns. Existing Pydantic deprecation and joblib physical-core detection warnings remain, as does the previously documented interrupted-resume limitation; use a fresh stage-6 run to apply the updated list consistently.

Only the stopword module, its test file, and this report were edited in this fix round. No parallel-worker files were touched, and no subagents, staging, or commits were used.
