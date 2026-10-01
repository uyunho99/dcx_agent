# Task T10 — 감사 통계 implementation report

Status: implemented and verified within the assigned file scope. No commit, git write operation, network access, or subprocess-based test was added.

## Requirements read

- `.superpowers/sdd/03-plan/task-T10-brief.md`
- `docs/development/dcx2-stage3-5/02-design-r2.md`, sections 4.8 and 4.10 (and neighboring routing/UI context)
- Existing `backend/app/label/store.py`, `merge.py`, `rule.py`, `votes.py`, `schema.py`, `backend/app/config.py`, and merge tests.

## Exact files created/modified by this task

Created:

1. `backend/app/label/audit.py`
2. `backend/tests/label/test_audit.py`
3. `.superpowers/sdd/03-plan/task-T10-report.md` (this report)

No existing implementation or test file was modified. In particular, `store.py`, `merge.py`, `backend/app/model/*`, `backend/tests/model/*`, and other label/prep test files were not edited. Concurrent model files appeared in git status and were left untouched.

## Implementation

- `maybe_new_round(store, accepted_count)`: first round at 1,000, then 11,000, 21,000, etc., using `settings.audit_first` and `audit_every`. Creates at most one due round per call; repeated calls catch up crossed thresholds. Round identity persists in `audit_set`, preventing duplicate creation at an already handled threshold across restarts.
- Samples `route='accepted'` only, up to `settings.audit_size` (default 50). Uses fixed-seed reservoir sampling over sorted document IDs, with bounded sample memory. Sample selection, snapshots, and reissue selection commit in one store transaction. An empty eligible pool creates no round.
- `reissue_items(store, round)`: persisted selection of up to `settings.audit_reissue` previously answered audit documents (default two), distinct from that round's fresh sample. First round has none. Returns IDs only, without prior answers.
- Adds version-local auxiliary SQLite tables from `audit.py`: `audit_snapshot` (original tags, grade, votes, and submission watermark) and `audit_reissue` (round/document membership). Existing store tables are unchanged.
- `kappa_ai(store, round)`: per-field and grade accuracy/Cohen's κ against independent audit answers. Keeps the original sampled AI values even after human overrides. Original recorded grade is preserved; human grades use the single `rule.grade` implementation.
- `labeler_accuracy(store)`: cumulative unique audited documents, latest audit answer per document; separately reports Jev and GPT fields and grade. `relate` and `outcome` are distinct. Jev uses the existing `>= .5` binary threshold. Uses persisted `votes_json`, which `rebuild_final` copied from done `VoteCache` payloads; a real cache→merge→audit integration test verifies this path. No provider or cache writes are performed. Missing provider payloads are omitted from that provider's n.
- Shared metrics return `{n, accuracy, kappa}`. Empty metrics have `accuracy=None, kappa=None`; constant identical labels have accuracy 1 but undefined κ (`None`), avoiding NaN and fabricated agreement estimates. Summary shape is `{n, fields: {...}, grade: {...}}`; provider summaries are keyed by `jev` and `gpt`.
- `self_consistency(store)`: cumulative exact-answer agreement of reissues against the same person's initial audit. Exact agreement includes reason and signal; field and grade summaries are also returned. Different-person and unpaired submissions are excluded. n counts paired reissue answers.
- `definition_signal(history)`: consumes chronological round summaries from `kappa_ai`; requires three latest finite κ values, two strict successive decreases, and latest grade κ strictly below `settings.kappa_floor` (0.75). Equality, missing values, insufficient history, and reversals do not trigger. Returns `{needed, reason}` with the design's Korean banner text when needed; does not stop processing.
- `apply_audit_overrides(store)`: explicit idempotent reconciliation helper. Applies latest eligible independent audit corrections to final tags, grade, reason/signal, source=`human`, route=`audited`, and rule version. Preserves original confidence, provider votes, and disagreement metadata. Ignores unsampled submissions, reissues, and later explicit escalation judgments. Both statistics entry points also reconcile saved submissions for resume recovery.

## TDD evidence

All seven named brief tests were written before `audit.py` existed, along with edge cases. Tests use temporary local SQLite stores, fixed inputs, and no subprocesses.

### RED — required tests first

From repository root:

```text
backend/.venv/bin/python -m pytest backend/tests/label/test_audit.py -q
FFFFFFFFFFFFFFFFF                                                        [100%]
E   ModuleNotFoundError: No module named 'app.label.audit'
17 failed, 1 warning in 0.19s
Exit code: 1
```

The failures included every required name:

- `test_first_round_at_1000_then_every_10k`
- `test_round_samples_accepted_only`
- `test_reissue_two_per_round`
- `test_self_consistency`
- `test_labeler_accuracy_from_audit`
- `test_definition_signal` (eight parameter cases)
- `test_audit_override_sets_human`

### GREEN — minimum implementation

Same root command after implementing the module:

```text
.................                                                        [100%]
17 passed, 1 warning in 0.24s
Exit code: 0
```

### Review/refactor regression cycle

Added actual VoteCache/merge integration, configurable schedule/sample behavior, and a balanced 100-document κ test. The last test also changes the grade function to ensure historical AI grades come from the stored snapshot.

```text
backend/.venv/bin/python -m pytest backend/tests/label/test_audit.py -q
FAILED ...::test_kappa_ai_balanced_errors_and_stored_grade
E   assert 1.0 == 0.5
1 failed, 19 passed, 1 warning in 0.41s
Exit code: 1
```

Refactored the shared summary helper to accept recorded grade pairs and made round κ use the sampled grade. Kept all rule computation in `rule.grade`.

### Final required GREEN runs

From repository root:

```text
backend/.venv/bin/python -m pytest backend/tests/label/test_audit.py -q
....................                                                     [100%]
20 passed, 1 warning in 0.38s
Exit code: 0
```

From backend (equivalent to `cd backend && .venv/bin/python -m pytest tests/label -q`):

```text
.venv/bin/python -m pytest tests/label -q
158 passed, 1 warning in 2.20s
Exit code: 0
```

The warning in all runs is the pre-existing Pydantic class-based Settings config deprecation in `app/config.py`.

Read-only `git diff --check` exited 0. New files are untracked pending the controller's commit; this check does not itself lint untracked content.

## Self-review

- Verified exact first/recurring boundaries, persisted round idempotency, fixed-seed selection, accepted-only eligibility, and distinct reissues.
- Verified exactly 100 independent reference answers: Jev relate/outcome accuracy .8/.6 with κ .6/.2; GPT .9/.7 with κ .8/.4. Duplicate audit answers do not inflate n; reissues do not replace audit truth.
- Verified balanced round agreement .8 and κ .6 for every field and grade.
- Verified `source=human` corrections survive reopened stores, original votes survive, and repeated statistics do not inflate agreement or repeat updates.
- Verified repeated sampling does not reuse an earlier round's answer. Submission rowid watermarks avoid relying on timestamp precision to distinguish rounds.
- Verified empty/degenerate metrics, same-labeler consistency, threshold equality, insufficient signal history, and settings overrides.
- No duplicated grade formula, new dependency, calibration/τ/α logic, network call, or out-of-scope edit.

## Concerns / integration contract

1. **Immediate override integration:** the existing `LabelStore.submit` only appends a human row. Changing it was explicitly prohibited. T11's audit submission handler must call `apply_audit_overrides(store)` immediately after `store.submit(..., mode='audit', ...)`, or call a statistics entry point that already reconciles. A bare `store.submit` alone does not update final. Human submissions remain immediately durable; if execution stops before reconciliation, the next helper/statistics call recovers them. Strict atomicity between human append and final update would require a small store-level transaction helper/change outside T10 ownership. No store/merge changes were made.
2. **Round association:** `human` has no explicit round ID. An audit answer is associated with the most recent sampling of that document using stored human rowid watermarks. If the same document is sampled again while an older audit page remains open, a later submission cannot identify the older intended round under the existing schema. An explicit submission round identifier would remove that ambiguity and needs store/API coordination. Current tests cover sequential rounds and avoid stale-answer reuse.
3. **Reissue availability:** fewer than two previously answered documents yields fewer reissues; first round yields none. Reissue IDs are fixed when the round is created, so they do not change as old answers arrive. Tiny eligible pools yield fewer than 50 fresh samples. Callers should pass the cumulative newly accepted count (not a count that shrinks when corrections move rows to route=`audited`).
4. **Manual rounds:** the design mentions a manual create-round UI, but the T10 brief specifies only the automatic `maybe_new_round` signature. This implementation provides the specified automatic API; a manual-force endpoint/helper is not added.

Controller owns commit/publication.
