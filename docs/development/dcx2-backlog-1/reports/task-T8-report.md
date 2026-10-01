# T8 — Manual audit separation

Status: COMPLETE — T8 / AC-04 implemented; RED confirmed, GREEN 205 passed.

## RED (before implementation)

Command: `backend/.venv/bin/python -m pytest backend/tests/label/test_audit_kind.py -q`

Exit status: 1. Full output:

```text
FFF                                                                      [100%]
=================================== FAILURES ===================================
______________ test_manual_at_500_does_not_delay_automatic_round _______________

client = <starlette.testclient.TestClient object at 0x10aeb45f0>
data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-529/test_manual_at_500_does_not_de0')

    def test_manual_at_500_does_not_delay_automatic_round(client, data_dir):
        sid = 'audit-kind'
        sessions.update_session(sid, {'schemaVersion': 2})
        labels = LabelStore(sessions.session_dir(sid))
        seed(labels, 0, 500)
        assert audit.maybe_new_round(labels, 500) is None
        response = client.post(f'/label/{sid}/audit')
        assert response.status_code == 200, response.text
        assert response.json() == {'round': 1}
    
        seed(labels, 500, 1000)
        labels = LabelStore(labels.path.parent)
        assert audit.maybe_new_round(labels, 999) is None
>       assert audit.maybe_new_round(labels, 1000) == 2
E       assert None == 2
E        +  where None = <function maybe_new_round at 0x10b0f8680>(<app.label.store.LabelStore object at 0x10aeac4d0>, 1000)
E        +    where <function maybe_new_round at 0x10b0f8680> = audit.maybe_new_round

backend/tests/label/test_audit_kind.py:43: AssertionError
______________ test_existing_database_migrates_and_reopens[None] _______________

tmp_path = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-529/test_existing_database_migrate0')
legacy_round = None

    @pytest.mark.parametrize('legacy_round', [None, 7])
    def test_existing_database_migrates_and_reopens(tmp_path, legacy_round):
        with sqlite3.connect(tmp_path / 'labels.sqlite') as db:
            db.execute('''CREATE TABLE audit_set (
                round INTEGER NOT NULL, doc_id TEXT NOT NULL, picked_at REAL NOT NULL,
                PRIMARY KEY(round, doc_id))''')
            if legacy_round is not None:
                db.executemany('INSERT INTO audit_set VALUES (?,?,?)',
                               [(legacy_round, 'old-a', 123.0), (legacy_round, 'old-b', 124.0)])
    
        labels = LabelStore(tmp_path)
        with labels._db() as db:
            columns = {row['name']: row for row in db.execute('PRAGMA table_info(audit_set)')}
>           assert 'kind' in columns
E           AssertionError: assert 'kind' in {'round': <sqlite3.Row object at 0x118fada20>, 'doc_id': <sqlite3.Row object at 0x118faf280>, 'picked_at': <sqlite3.Row object at 0x118fae770>}

backend/tests/label/test_audit_kind.py:66: AssertionError
________________ test_existing_database_migrates_and_reopens[7] ________________

tmp_path = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-529/test_existing_database_migrate1')
legacy_round = 7

    @pytest.mark.parametrize('legacy_round', [None, 7])
    def test_existing_database_migrates_and_reopens(tmp_path, legacy_round):
        with sqlite3.connect(tmp_path / 'labels.sqlite') as db:
            db.execute('''CREATE TABLE audit_set (
                round INTEGER NOT NULL, doc_id TEXT NOT NULL, picked_at REAL NOT NULL,
                PRIMARY KEY(round, doc_id))''')
            if legacy_round is not None:
                db.executemany('INSERT INTO audit_set VALUES (?,?,?)',
                               [(legacy_round, 'old-a', 123.0), (legacy_round, 'old-b', 124.0)])
    
        labels = LabelStore(tmp_path)
        with labels._db() as db:
            columns = {row['name']: row for row in db.execute('PRAGMA table_info(audit_set)')}
>           assert 'kind' in columns
E           AssertionError: assert 'kind' in {'round': <sqlite3.Row object at 0x119289150>, 'doc_id': <sqlite3.Row object at 0x11928a950>, 'picked_at': <sqlite3.Row object at 0x11928bd30>}

backend/tests/label/test_audit_kind.py:66: AssertionError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/label/test_audit_kind.py::test_manual_at_500_does_not_delay_automatic_round
FAILED backend/tests/label/test_audit_kind.py::test_existing_database_migrates_and_reopens[None]
FAILED backend/tests/label/test_audit_kind.py::test_existing_database_migrates_and_reopens[7]
3 failed, 1 warning in 2.32s
```

## Implementation

- `backend/app/label/store.py`: new databases include `audit_set.kind TEXT DEFAULT 'auto'`; existing databases add it with `ALTER TABLE` only when absent, inside the existing transaction. Existing rows become `auto`; reopening is safe.
- `backend/app/label/audit.py`: automatic thresholds use `COUNT(DISTINCT round)` filtered to `kind='auto'`. Both kinds retain global `MAX(round)+1` numbering and the existing atomic sample/snapshot/reissue behavior. Manual creation bypasses the automatic threshold.
- `backend/app/routers/labeling_v2.py`: only the manual-round path changed; it passes the actual accepted count with `kind='manual'` and retains its existing guards.
- `backend/tests/label/test_audit_kind.py`: offline tests cover a manual API round at 500 followed by automatic rounds at 1,000 and 11,000, duplicate prevention, persisted kinds, empty/populated legacy migration, repeat opening, and sparse historical round numbering.

## GREEN

Command: `backend/.venv/bin/python -m pytest backend/tests/label/test_audit_kind.py -q`

Exit status: 0. Full output:

```text
...                                                                      [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3 passed, 1 warning in 2.17s
```

Required command: `backend/.venv/bin/python -m pytest backend/tests/label -q`

Exit status: 0. Full output:

```text
........................................................................ [ 35%]
........................................................................ [ 70%]
.............................................................            [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
205 passed, 1 warning in 6.02s
```

## Scope and checks

`git diff --check` passed. Only the four T8-owned code/test files and this requested report were edited by this task. Concurrent jobs' changes were left intact. No packages installed; no commits created. The test runs report one existing Pydantic class-based-config deprecation warning.
