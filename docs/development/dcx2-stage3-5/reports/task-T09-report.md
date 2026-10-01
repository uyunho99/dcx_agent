# T09 implementation report

Status: implemented; all 19 focused tests pass. The required full label suite was run once and has 10 failures outside T09 (details below). No commit or other git write command was performed. Branch: `feature/dcx2-stage3-5`.

## Requirements and scope

Read `task-T09-brief.md`, design r2 sections 2.3, 2.4 and 4.7, and the existing rule, schema, Jev, GPT, votes and judge modules. Also checked adjacent task briefs to understand audit and routing integration. No calibration table or calibration behavior was introduced (D-145).

Created exactly these implementation/test files:

- `backend/app/label/store.py`
- `backend/app/label/merge.py`
- `backend/tests/label/test_merge.py`

Created this requested report:

- `.superpowers/sdd/03-plan/task-T09-report.md`

No other files were edited by this implementation. In particular, the T04 files and existing T06–T08 code/tests were not edited. Concurrent, unowned changes appeared in `backend/tests/label/test_gpt.py`, `test_jev.py`, `test_judge.py`, and `test_judge_resume.py`; these were inspected read-only and preserved. After the full suite run, final status also showed concurrent modifications to `backend/app/label/gpt.py`, `jev.py`, `judge.py`, and `votes.py`. Those changes were likewise left untouched; the recorded suite results describe the state at execution time, not these later edits.

## Implementation

### Merge

`merge(jev: JevVote, gpt: GptVote) -> MergedLabel` returns the final tags, `evidence_level`, `confidence`, a `disagree` list of field names, and `grade_mismatch`.

- Grade fields use Jev's `p >= 0.5` binary value. This is both the common value on agreement and the specified Jev tie-break on disagreement.
- `reason_code` uses the Jev argmax, with `not_non` mapped to `None`. A difference from GPT is included in `disagree`, but cannot affect the eight-field confidence numerator.
- `signal` is copied verbatim from GPT, including `None` and `none`.
- Confidence is `(matching grade fields / 8) * min(max(p, 1-p))`, with the minimum taken over all eight grade fields, including mismatched fields.
- Both the merged grade and the independent labeler grades use `rule.grade`; no grade rules are duplicated.
- `grade_mismatch` is distinct from field disagreement. Same-grade disagreement is accepted even at low confidence.

### Store

`LabelStore(version_dir)` creates `labels.sqlite` with exactly the four requested tables: `final`, `human`, `audit_set`, and `queue`. It includes the design's main columns and adds `questions_version`, `votes_json`, `disagree_json`, and `grade_mismatch` to `final` for invalidation, comparisons, and routing. `queue(status, priority, doc_id)` and human-document indexes support downstream workflows.

`submit(doc_id, labeler, mode, tags)` validates a complete `Tags` payload and one of `escalate|audit|reissue`, then appends exactly one human row in an immediately committed transaction. It accepts either a Tags model or a mapping. Repeated judgments remain separate rows. It does not apply audit/escalation overrides; those belong to T10/T11. `get(doc_id)` reads a persisted `Label`, returning `None` for an absent final.

### Incremental rebuild

`rebuild_final(store, jev_cache, gpt_cache)` accepts the existing `VoteCache` instances and returns the number of merged documents. It attaches their SQLite files read-only, joins `done` rows by document ID, and excludes documents already in `final` before deserializing or merging. Only newly paired votes are merged on ordinary calls, including after reopening the store. No labeler/provider is invoked, and cache bytes remain unchanged.

Stored `rule_version` and `questions_version` are compared against the current rule/questions modules. A mismatch invalidates automatic finals and recomputes all currently paired automatic documents atomically. Human final overrides and human submission history are preserved. A failure midway rolls the entire rebuild back, including version invalidation.

Final rows retain raw votes and disagreement metadata. Grade mismatches receive `escalated:grade_mismatch`; other paired votes receive `accepted`. Terminal `bad` votes enter `labeler_failed` review without requiring the other vote. Failure priority is 0; mismatch priority is `1 + confidence`, giving reason-first, then increasing-confidence order. Repeated rebuilds retain done/skipped queue rows. This supplies the persistence/routing data for the later T11 routing/API layer, without creating or modifying T11 files.

## TDD evidence

Tests were written before either implementation file existed. All five required test names are present: `test_agree_confidence`, `test_disagree_takes_jev_and_flags`, `test_grade_mismatch`, `test_signal_from_gpt_only`, and `test_waits_until_both`.

### Initial RED

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_merge.py -q
```

Observed output excerpt:

```text
FFFFFFFFFFFFFFFF [100%]
E   ModuleNotFoundError: No module named 'app.label.merge'
16 failed, 1 warning in 0.33s
```

Exit code 1. All 16 cases failed because the required merge module did not exist; the failures were not caused by credentials, network, or fixtures.

### Initial GREEN

After the minimum store/merge implementation, the same command produced:

```text
................ [100%]
16 passed, 1 warning in 0.25s
```

Exit code 0.

### Self-review regression RED

Added tests for human final preservation alongside unrelated terminal failures, atomic rollback during version recomputation, read-only caches, and same-grade disagreement routing. The same focused command produced:

```text
................F.. [100%]
FAILED tests/label/test_merge.py::test_human_final_survives_rebuild_without_hiding_other_failures
E   AssertionError: assert [] == ['bad']
1 failed, 18 passed, 1 warning in 0.30s
```

The bad-vote SQL subquery's unqualified `doc_id` resolved to the inner final row, so any human final could hide unrelated failed documents. Qualified the outer candidate as `failed.doc_id` and refactored merge to reuse its calculated Jev/final grade.

### Final focused GREEN

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_merge.py -q
```

Output:

```text
................... [100%]
19 passed, 1 warning in 0.25s
```

Exit code 0. Coverage includes the exact 0.9 agreement example, inclusive 0.5 cutoff, zero agreement, Jev reason argmax, all GPT signal values, one-vote waiting, restart-safe incremental merging, independent rule and question version invalidation, durable per-item submissions, invalid mode rejection, no `calib_set`, terminal failures, queue-status preservation, human-final preservation, rollback, and read-only vote caches.

## Required full label suite (run once)

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/label -q
```

Final output:

```text
10 failed, 125 passed, 1 warning in 1.94s
```

Exit code 1. All T09 tests passed in this run. Failing tests and observed reasons:

| Test | Observed failure |
| --- | --- |
| `test_gpt.py::test_usage_limit_pauses` | `LabelerPaused.usage_limit` is absent. |
| `test_jev.py::test_retry_exhaustion[429]` | `JevError.transient` is absent. |
| `test_jev.py::test_retry_exhaustion[500]` | One HTTP attempt instead of six. |
| `test_jev.py::test_retry_exhaustion[502]` | `JevError.transient` is absent. |
| `test_jev.py::test_retry_exhaustion[503]` | One HTTP attempt instead of six. |
| `test_jev.py::test_retry_exhaustion[504]` | One HTTP attempt instead of six. |
| `test_jev.py::test_transport_failure_is_safe` | `JevError.transient` is absent. |
| `test_judge.py::test_transport_outage_releases_backoffs_and_pauses` | 300 provider mock requests instead of five. |
| `test_judge.py::test_usage_limit_never_consumes_attempts` | Pending documents have attempts 1 instead of 0. |
| `test_judge_resume.py::test_leases_prioritize_fewer_attempts` | Lease order is `a,b,c` instead of `b,c,a`. |

Read-only `git diff` confirmed all failing assertions/cases are in concurrent changes to the four unowned test files listed above. The suite's tests use mocks/fake executables; no network or real provider invocation was made. No changes were made outside T09 to address these failures, and the full suite was not rerun.

The warning in every run is the existing Pydantic class-based configuration deprecation at `app/config.py:12`.

## Self-review and concerns

- Verified the implementation against the brief and actual T03/T06/T07/T08 payload names; no changes to those interfaces were needed.
- Confirmed no calibration schema or confidence threshold routing was added.
- Confirmed incremental calls do not call `merge` for existing finals; version changes recompute paired automatic rows and preserve human data.
- Confirmed durable reads through separate SQLite connections and successful transaction rollback after a deliberately interrupted recompute.
- Reviewed the SQL and fixed the human-final correlation bug with RED/GREEN evidence.
- `git diff --check` completed successfully for the tracked workspace changes. The three T09 code/test files are new, untracked files and were also read/reviewed directly.
- Remaining validation concern: the shared label suite is not green due to the ten out-of-scope failures above; the controller should integrate their owning task's fixes before broader acceptance.
- Integration boundary: human submission only appends the durable row; audit correction, submission-driven final replacement, queue actions, and API orchestration remain T10/T11 work. Stored human finals are deliberately not overwritten by automatic rebuilds.
- Incrementality avoids re-merging/deserializing old finals but still scans/index-joins cache metadata to discover newly paired documents; no large-dataset timing benchmark was requested or performed. A rebuild uses one atomic SQLite transaction, which can hold locks for the duration of a large batch/full recompute.
- Per the explicit F6 requirement, automatic full recomputation is triggered only by rule/question version changes. Replacing context-specific caches under an unchanged rule/qver is not a separate full-rebuild trigger here; callers must manage the version-local store lifecycle.

No git write commands, commits, network access, or edits to the parallel implementer's files were performed.
