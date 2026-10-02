# T2 report

Status: implemented; focused tests pass. Full persona suite attempted once and blocked during collection by concurrent tasks' missing modules.

## Owned files

- `backend/app/persona/params.py`: exact parameter values from the brief.
- `backend/app/persona/store.py`: `PersonaStore.open/read/write/new_revision/revert/append_chat`, using `version_dir(sid, version) / 'persona'`.
- `backend/tests/persona/test_store.py`: 20 cases covering parameters, all six JSON files, version/session isolation, atomic failures, full history, reverts, missing revisions, failed revisions, chat appends, and invalid file names.

## Decisions and integration contract

- JSON writes reuse `app.context.store.write_json`: a unique temporary file in the destination directory, flush/fsync, `os.replace`, directory fsync, and temporary-file cleanup.
- History includes every revision, including the current one. Each entry contains `{revision, items, at, by, message}`. `items` is the full JSON snapshot; timestamps are timezone-aware UTC. Revision numbering starts at 1.
- Revert copies the selected snapshot into the next revision with `by: 'revert'` and `message: null`, preserving all prior entries. A missing revision raises `StoreError` with status 404 and kind `not_found`, without changing the JSON file.
- All mutations acquire the existing session lock internally. Callers must not already hold `sessions.locked(sid)` (the flock is not reentrant). Writable-version/run/content validation stays with callers, following SegmentStore's separation of responsibilities.
- Logical names are restricted to `cards`, `map`, `tree`, `insights`, `concepts`, and `stage_8`; invalid names raise 400 `validation`. Chat uses the dedicated append method.
- Chat rows serialize before the append stream is opened, preserve Unicode and escaped newlines, and are flushed/fsynced under the session lock. Chat append is not a transactional replacement: an OS failure during append can leave a partial final row.
- Atomic replacement guarantees apply before the replace commit point. As with the shared helper, a directory-fsync failure after replacement can report an error after the new file is already visible.

## TDD and verification

1. Wrote `test_store.py` before implementation.
2. RED: `backend/.venv/bin/python -m pytest backend/tests/persona/test_store.py -q` exited 2 on missing `app.persona.params` during collection.
3. Implemented params and store.
4. GREEN: same focused command — **20 passed**, one existing Pydantic configuration deprecation warning.
5. Refactored the test's Path handling and cleaned the module docstring.
6. Ran `backend/.venv/bin/python -m pytest backend/tests/persona -q` exactly once — exited 2 with three collection errors: missing `app.persona.grade`, `app.persona.opportunity`, and `app.persona.tree`. These belong to the parallel T3/T4 workers and were not modified.
7. Because full-suite collection did not exercise the cleanup, reran the focused command — **20 passed**, one existing warning.
8. `git diff --check` passed; new owned files were also reviewed directly.

No git add or commit. No subagents. No changes to other workers' files.

## Concerns

The controller must rerun the combined suite after T3/T4 modules land. Integrators must observe the internal-lock contract above. No unresolved T2 implementation failures.
