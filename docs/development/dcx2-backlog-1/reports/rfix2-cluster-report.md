Status: COMPLETE

Changes
- `backend/app/services/clustering.py`: capture the active writable version when loading clustering inputs. After all cluster outputs save successfully, persist `clustering: {status: 'done', version: <v>, at: <timestamp>}` and clear only `stale.stage6` with `clear_stale`, under the session lock. Recheck writability before publication so a version switch cannot complete the readonly source or a different active version.
- `backend/app/routers/sessions.py`: derive `clustersDone` exclusively from the selected session's persisted clustering status and absence of `stage6` stale. Protect the clustering milestone from generic client session saves.
- `backend/app/context/stale.py`: check selected-version writability under the lock before judge reconciliation can publish. Readonly reads remain fail-soft and unchanged.
- Updated only the two permitted context test files for these changes. No router change was necessary; successful publication happens in the clustering service. Did not edit `rounds.py` or the parallel job's files. No commit created.

Tests
- RED: targeted completion/stale suite initially produced 7 failures and 44 passes, demonstrating missing durable completion, session-scoped job leakage, missing stage6 clearing, wrong-version publication, and readonly reconciliation writes.
- RED: the additional session-save protection test failed before adding `clustering` to server-owned fields.
- GREEN: `backend/.venv/bin/python -m pytest backend/tests/context/test_session_completion.py backend/tests/context/test_stale_clear.py -q` — 52 passed, 2 warnings.
- Full verification: `backend/.venv/bin/python -m pytest backend/tests -q` — 1,446 passed, 1 deselected, 2 warnings in 142.30 seconds. This run started before the final save-protection test/change; the final targeted GREEN run covers that addition.
- `git diff --check` for the five modified implementation/test files — passed.
- Tests use local storage and deterministic local vectors; socket guards prohibit network access. Warnings concern Pydantic class-based configuration and joblib physical-core detection.

Results
- Stage3 and stage6 restarts start incomplete and become complete after a successful clustering run in v2.
- Completion survives replacing the in-memory job managers with fresh instances.
- Clustering in v2 leaves readonly v1 byte-for-byte unchanged and does not mark it complete. Prior v1 completion remains visible independently when it was already persisted.
- Failed output publication preserves stale state. A version switch during clustering cannot publish completion into either version.
- Judge reconciliation skips readonly versions, including when the selected version is inferred from session data; existing active-version recovery remains passing.
