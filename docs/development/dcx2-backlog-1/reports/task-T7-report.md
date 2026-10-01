# T7 report

Status: COMPLETE — T7 implementation and regression tests pass.

Changes are limited to `backend/app/context/versions.py`, the new
`backend/tests/context/test_versions_backlog1.py`, and this requested report.
No packages installed; no commit created.

- `_idle` excludes monitor runs; running judge/prep/train/infer still return 409.
- After successful version activation and metadata persistence, paused judge/infer
  runs belonging to the previous active version atomically receive `action=stop`
  and `state=interrupted`. Active monitor runs receive `action=stop`.
- Finished runs remain unchanged. Cleanup targets the previous active version,
  including when restoring from older history. Failed activation does not stop workers.
- 12 new offline cases use the real SQLite worker registry and verify `should_stop`.

## RED (before implementation)

Command: `backend/.venv/bin/python -m pytest backend/tests/context/test_versions_backlog1.py -q`

```text
FFF.......FF                                                             [100%]
=================================== FAILURES ===================================
_______ test_paused_worker_is_interrupted_after_version_creation[judge] ________

client = <starlette.testclient.TestClient object at 0x10de9e6f0>, kind = 'judge'

    @pytest.mark.parametrize('kind', ['judge', 'infer'])
    def test_paused_worker_is_interrupted_after_version_creation(client, kind):
        sid = create(client)
        context = add_run(sid, kind, 'paused')
        assert versions.create_version(sid, 'v1', 'stage4', '') == 'v2'
        row = context._row()
>       assert row['state'] == 'interrupted'
E       AssertionError: assert 'paused' == 'interrupted'
E         
E         - interrupted
E         + paused

backend/tests/context/test_versions_backlog1.py:38: AssertionError
_______ test_paused_worker_is_interrupted_after_version_creation[infer] ________

client = <starlette.testclient.TestClient object at 0x11a2d43e0>, kind = 'infer'

    @pytest.mark.parametrize('kind', ['judge', 'infer'])
    def test_paused_worker_is_interrupted_after_version_creation(client, kind):
        sid = create(client)
        context = add_run(sid, kind, 'paused')
        assert versions.create_version(sid, 'v1', 'stage4', '') == 'v2'
        row = context._row()
>       assert row['state'] == 'interrupted'
E       AssertionError: assert 'paused' == 'interrupted'
E         
E         - interrupted
E         + paused

backend/tests/context/test_versions_backlog1.py:38: AssertionError
____________ test_running_monitor_allows_creation_and_receives_stop ____________

client = <starlette.testclient.TestClient object at 0x11a8f34a0>

    def test_running_monitor_allows_creation_and_receives_stop(client):
        sid = create(client)
        context = add_run(sid, 'monitor', 'running')
        response = client.post(f'/sessions/{sid}/versions', json={
            'from': 'v1', 'restartFrom': 'stage5'})
>       assert response.status_code == 201
E       assert 409 == 201
E        +  where 409 = <Response [409 Conflict]>.status_code

backend/tests/context/test_versions_backlog1.py:48: AssertionError
__________ test_restoring_history_stops_previous_active_workers_only ___________

client = <starlette.testclient.TestClient object at 0x11a913aa0>

    def test_restoring_history_stops_previous_active_workers_only(client):
        sid = create(client)
        versions.create_version(sid, 'v1', 'stage4', '')
        previous = add_run(sid, 'judge', 'paused', 'v2')
        unrelated = add_run(sid, 'infer', 'paused', 'v1')
        versions.create_version(sid, 'v1', 'stage4', '')
>       assert previous._row()['state'] == 'interrupted'
E       AssertionError: assert 'paused' == 'interrupted'
E         
E         - interrupted
E         + paused

backend/tests/context/test_versions_backlog1.py:82: AssertionError
__________________ test_failed_creation_does_not_stop_workers __________________

client = <starlette.testclient.TestClient object at 0x11a911f10>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11a911010>

    def test_failed_creation_does_not_stop_workers(client, monkeypatch):
        sid = create(client)
        contexts = [add_run(sid, 'judge', 'paused'), add_run(sid, 'monitor', 'running')]
        before = [dict(context._row()) for context in contexts]
        write_json = versions.write_json
    
        def fail_meta(path, data):
            if path.name == 'meta.json':
                raise OSError('metadata write failed')
            write_json(path, data)
    
        monkeypatch.setattr(versions, 'write_json', fail_meta)
        with pytest.raises(OSError, match='metadata write failed'):
>           versions.create_version(sid, 'v1', 'stage4', '')

backend/tests/context/test_versions_backlog1.py:100: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
backend/app/context/versions.py:146: in create_version
    _idle(sid, _data(sid, meta['activeVersion']))
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 's3fd4a1e89f24420db48e8103884692f1'
data = {'schemaVersion': 2, 'sid': 's3fd4a1e89f24420db48e8103884692f1', 'step': 'start', 'drafts': {}, ...}

    def _idle(sid, data):
        running = any((r.get('job') or {}).get('status') == 'running' for r in data.get('keywordRounds', {}).values())
        if running or any(a['status'] == 'running' for a in session_activities(sid, data)):
>           raise StoreError('진행 중인 작업이 끝난 뒤 다시 시도하세요')
E           app.context.store.StoreError: 진행 중인 작업이 끝난 뒤 다시 시도하세요

backend/app/context/versions.py:73: StoreError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/context/test_versions_backlog1.py::test_paused_worker_is_interrupted_after_version_creation[judge]
FAILED backend/tests/context/test_versions_backlog1.py::test_paused_worker_is_interrupted_after_version_creation[infer]
FAILED backend/tests/context/test_versions_backlog1.py::test_running_monitor_allows_creation_and_receives_stop
FAILED backend/tests/context/test_versions_backlog1.py::test_restoring_history_stops_previous_active_workers_only
FAILED backend/tests/context/test_versions_backlog1.py::test_failed_creation_does_not_stop_workers
5 failed, 7 passed, 1 warning in 1.96s
```

## GREEN (version regression suite)

Command: `backend/.venv/bin/python -m pytest backend/tests/context/test_versions.py backend/tests/context/test_versions_stage3_5.py backend/tests/context/test_versions_backlog1.py -q`

```text
.........................................                                [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
41 passed, 1 warning in 2.50s
```

## Required context verification

Command: `backend/.venv/bin/python -m pytest backend/tests/context -q`

Initial run: 9 failed, 129 passed, 1 warning in 4.40s. All nine failures were
in the concurrently added `test_stale_clear.py` (stages 3/4/5 clearing and a
missing `app.context.stale` module). No files owned by that task were edited.
After those parallel implementation files appeared, reran the required command:

```text
........................................................................ [ 52%]
..................................................................       [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
138 passed, 1 warning in 4.15s
```

`git diff --check` for T7 code returned no errors.
