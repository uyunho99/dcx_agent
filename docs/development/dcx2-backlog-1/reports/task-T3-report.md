# T3 report

Status: BLOCKED ON SCOPE CLARIFICATION — 225 tests pass; the remaining GET stale-loading check requires one router line beyond the explicit edit allowance.

## Changes

- R2 commit schedules coverage with the existing `rounds.execute` pattern after persisting `loading` and `startedAt`.
- Search-ad remains preferred with volume weighting; `Unconnected` falls back to T1's exact `suggestions(seeds)` / `AutocompleteResult` signature and T2's `compute(..., weighting='rank')`.
- Autocomplete seeds are the product name followed by the first 20 approved LLM keywords in round/display order. Metadata, human queries, axes, metrics, and rank-sorted missing queries are persisted.
- Cached coverage is returned unchanged except stale-loading interpretation. Only explicit `refresh=true` refetches existing data, and active work is deduplicated. Refresh fetches new queries and reclassifies their axes.
- Adapter failures become `unavailable`, preserving round progression. Worker completion checks its loading timestamp and version before writing.
- Added the requested tests plus real-thread response timing, refresh query/axis invalidation, duplicate refresh, and superseded worker checks.

## Scope clarification resolved

Controller ruling: YES. Applied the authorized one-line GET response normalization using `rounds.coverage_status`; loading older than 120 seconds reads as unavailable. The prior pending request below is retained as history.

The task restricted `backend/app/routers/keywords_v2.py` to adding the refresh parameter, but GET stale-loading interpretation requires an additional one-line call there. Requested permission for `data['coverage'] = rounds.coverage_status(data.get('coverage') or {})` before GET response assembly. This line has NOT been applied pending a reply. The helper already handles cached POST reads and R3 inputs. No other out-of-scope files were edited; T1/T2 implementations were used without modification. No packages installed or commits made.

## RED

Tests were written and run before implementation. Command (fake backend prevents external requests in the entire keyword suite; T3 tests also block socket connections):

```sh
AUTOCOMPLETE_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/keywords -q
```

```text
........................................................................ [ 32%]
........................................................................ [ 64%]
..............FF...............F.........................FFFFFFFFF...... [ 97%]
......                                                                   [100%]
=================================== FAILURES ===================================
_______________________ test_r2_commit_triggers_coverage _______________________

client = <starlette.testclient.TestClient object at 0x11a9125a0>

    def test_r2_commit_triggers_coverage(client):
        through(client, 2)
>       assert store.load_session('test')['coverage']['source'] == 'autocomplete'
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'source'

backend/tests/keywords/test_rounds_api.py:115: KeyError
___________________________ test_r3_inputs_recorded ____________________________

client = <starlette.testclient.TestClient object at 0x11a899910>
backend = <test_rounds_api.backend.<locals>.RecordingFake object at 0x11a973530>

    def test_r3_inputs_recorded(client, backend):
        through(client, 2)
        start(client, 3)
        inputs = store.load_session('test')['keywordRounds']['3']['inputs']
>       assert inputs == {'rejection': 'empty:no_rejections', 'coverage': 'ok',
                          'prior_session': 'empty:no_prior_session', 'promptVersion': 'r3.v1'}
E       AssertionError: assert {'rejection':...ion': 'r3.v1'} == {'rejection':...ion': 'r3.v1'}
E         
E         Omitting 3 identical items, use -vv to show
E         Differing items:
E         {'coverage': 'empty:searchad_unconnected'} != {'coverage': 'ok'}
E         Use -v to get more diff

backend/tests/keywords/test_rounds_api.py:122: AssertionError
______________ test_coverage_preserves_old_failure_until_refresh _______________

client = <starlette.testclient.TestClient object at 0x11acc9c40>

    def test_coverage_preserves_old_failure_until_refresh(client):
        store.update_session('test', {'coverage': {'status': 'failed', 'error': {'kind': 'request_failed'}}})
>       assert client.post('/keywords/test/coverage').json() == {
            'status': 'failed', 'error': {'kind': 'request_failed'}}
E       AssertionError: assert {'status': 'unconnected'} == {'status': 'f...uest_failed'}}
E         
E         Differing items:
E         {'status': 'unconnected'} != {'status': 'failed'}
E         Right contains 1 more item:
E         {'error': {'kind': 'request_failed'}}
E         Use -v to get more diff

backend/tests/keywords/test_rounds_api.py:301: AssertionError
__________________ test_coverage_uses_searchad_when_connected __________________

client = <starlette.testclient.TestClient object at 0x11ad50170>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11ad50d70>
autocomplete_calls = []

    def test_coverage_uses_searchad_when_connected(client, monkeypatch, autocomplete_calls):
        monkeypatch.setattr(rounds.naver_searchad, 'related_queries',
                            lambda hints: [('냉방1단어0', 100), ('누락', 20)])
        through(client, 2)
        saved = client.get('/keywords/test').json()['coverage']
>       assert saved['source'] == 'searchad' and saved['weighting'] == 'volume'
               ^^^^^^^^^^^^^^^
E       KeyError: 'source'

backend/tests/keywords/test_rounds_api.py:510: KeyError
__________ test_coverage_falls_back_to_autocomplete_when_unconnected ___________

client = <starlette.testclient.TestClient object at 0x11ab4bf80>
autocomplete_calls = []

    def test_coverage_falls_back_to_autocomplete_when_unconnected(client, autocomplete_calls):
        through(client, 1)
        # Seed order follows displayed generation order, excluding manual/rejected items.
        data = store.load_session('test')
        kws = data['keywords']
        kws[0]['status'] = 'rejected'
        kws[1]['origin'] = 'manual'
        store.update_session('test', {'keywords': kws})
        state = start(client, 2)
        assert commit(client, 2, state).status_code == 200
        saved = client.get('/keywords/test').json()['coverage']
        expected = [k['kw'] for k in kws if k['status'] == 'approved' and k['origin'] == 'llm'][:20]
>       assert autocomplete_calls == [[''] + expected]
E       AssertionError: assert [] == [['', '냉방1단어2...냉방1단어6', ...]]
E         
E         Right contains one more item: ['', '냉방1단어2', '냉방1단어3', '냉방1단어4', '냉방1단어5', '냉방1단어6', ...]
E         Use -v to get more diff

backend/tests/keywords/test_rounds_api.py:528: AssertionError
________________ test_coverage_autocomplete_unavailable_status _________________

client = <starlette.testclient.TestClient object at 0x11ab94e90>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11ab95700>

    def test_coverage_autocomplete_unavailable_status(client, monkeypatch):
        def unavailable(seeds):
            raise naver_autocomplete.AutocompleteUnavailable('private failure detail')
        monkeypatch.setattr(naver_autocomplete, 'suggestions', unavailable)
        through(client, 2)
        saved = client.get('/keywords/test').json()['coverage']
>       assert saved['status'] == 'unavailable'
E       AssertionError: assert 'unconnected' == 'unavailable'
E         
E         - unavailable
E         + unconnected

backend/tests/keywords/test_rounds_api.py:542: AssertionError
_________________ test_coverage_cached_once_refresh_refetches __________________

client = <starlette.testclient.TestClient object at 0x11aaaed50>
autocomplete_calls = []

    def test_coverage_cached_once_refresh_refetches(client, autocomplete_calls):
        through(client, 2)
        before = client.get('/keywords/test').json()['coverage']
        for _ in range(2):
            assert client.post('/keywords/test/coverage').json() == before
>       assert len(autocomplete_calls) == 1
E       assert 0 == 1
E        +  where 0 = len([])

backend/tests/keywords/test_rounds_api.py:555: AssertionError
_______________________ test_missing_top_feeds_r3_inputs _______________________

client = <starlette.testclient.TestClient object at 0x11a89a990>
backend = <test_rounds_api.backend.<locals>.RecordingFake object at 0x11a899610>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11a89b980>

    def test_missing_top_feeds_r3_inputs(client, backend, monkeypatch):
        human = [(f'누락검색어{i:02}', 10 - i % 10) for i in range(25)]
        monkeypatch.setattr(naver_autocomplete, 'suggestions', lambda seeds:
                            naver_autocomplete.AutocompleteResult(human, 0, len(seeds)))
        through(client, 2)
        missing = sorted(human, key=lambda row: row[1])[:20]
>       assert client.get('/keywords/test').json()['coverage']['missing_top'] == [list(row) for row in missing]
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'missing_top'

backend/tests/keywords/test_rounds_api.py:566: KeyError
_____________ test_r2_commit_returns_before_autocomplete_finishes ______________

client = <starlette.testclient.TestClient object at 0x11ab94260>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11ab974a0>
autocomplete_calls = []

    def test_r2_commit_returns_before_autocomplete_finishes(client, monkeypatch, autocomplete_calls):
        through(client, 1)
        state = start(client, 2)
        queued = []
        def execute(fn):
            saved = store.load_session('test')
            assert saved['keywordRounds']['2']['committed']
            assert saved['coverage']['status'] == 'loading'
            assert saved['coverage']['startedAt']
            queued.append(fn)
        monkeypatch.setattr(rounds, 'execute', execute)
        assert commit(client, 2, state).status_code == 200
        assert not autocomplete_calls
>       assert client.get('/keywords/test').json()['coverage']['status'] == 'loading'
E       AssertionError: assert 'unconnected' == 'loading'
E         
E         - loading
E         + unconnected

backend/tests/keywords/test_rounds_api.py:584: AssertionError
_________ test_stale_loading_over_2min_reads_unavailable[119-loading] __________

client = <starlette.testclient.TestClient object at 0x11aaaf1d0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11aaad8b0>
autocomplete_calls = [], age = 119, status = 'loading'

    @pytest.mark.parametrize('age,status', [(119, 'loading'), (121, 'unavailable')])
    def test_stale_loading_over_2min_reads_unavailable(client, monkeypatch, autocomplete_calls, age, status):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        monkeypatch.setattr(store, 'now', lambda: now.isoformat())
        saved = {'status': 'loading', 'startedAt': (now - timedelta(seconds=age)).isoformat()}
        store.update_session('test', {'coverage': saved})
        assert client.get('/keywords/test').json()['coverage']['status'] == status
>       assert client.post('/keywords/test/coverage').json()['status'] == status
E       AssertionError: assert 'unconnected' == 'loading'
E         
E         - loading
E         + unconnected

backend/tests/keywords/test_rounds_api.py:597: AssertionError
_______ test_stale_loading_over_2min_reads_unavailable[121-unavailable] ________

client = <starlette.testclient.TestClient object at 0x11aaad340>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11aaac6b0>
autocomplete_calls = [], age = 121, status = 'unavailable'

    @pytest.mark.parametrize('age,status', [(119, 'loading'), (121, 'unavailable')])
    def test_stale_loading_over_2min_reads_unavailable(client, monkeypatch, autocomplete_calls, age, status):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        monkeypatch.setattr(store, 'now', lambda: now.isoformat())
        saved = {'status': 'loading', 'startedAt': (now - timedelta(seconds=age)).isoformat()}
        store.update_session('test', {'coverage': saved})
>       assert client.get('/keywords/test').json()['coverage']['status'] == status
E       AssertionError: assert 'loading' == 'unavailable'
E         
E         - unavailable
E         + loading

backend/tests/keywords/test_rounds_api.py:596: AssertionError
_________________ test_refresh_param_refetches_only_when_true __________________

client = <starlette.testclient.TestClient object at 0x11aaaf200>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11aaaf0e0>
autocomplete_calls = []

    def test_refresh_param_refetches_only_when_true(client, monkeypatch, autocomplete_calls):
        through(client, 2)
        before = client.get('/keywords/test').json()['coverage']
        assert client.post('/keywords/test/coverage?refresh=false').json() == before
>       assert client.post('/keywords/test/coverage?refresh=invalid').status_code == 422
E       AssertionError: assert 200 == 422
E        +  where 200 = <Response [200 OK]>.status_code
E        +    where <Response [200 OK]> = post('/keywords/test/coverage?refresh=invalid')
E        +      where post = <starlette.testclient.TestClient object at 0x11aaaf200>.post

backend/tests/keywords/test_rounds_api.py:605: AssertionError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/keywords/test_rounds_api.py::test_r2_commit_triggers_coverage
FAILED backend/tests/keywords/test_rounds_api.py::test_r3_inputs_recorded - A...
FAILED backend/tests/keywords/test_rounds_api.py::test_coverage_preserves_old_failure_until_refresh
FAILED backend/tests/keywords/test_rounds_api.py::test_coverage_uses_searchad_when_connected
FAILED backend/tests/keywords/test_rounds_api.py::test_coverage_falls_back_to_autocomplete_when_unconnected
FAILED backend/tests/keywords/test_rounds_api.py::test_coverage_autocomplete_unavailable_status
FAILED backend/tests/keywords/test_rounds_api.py::test_coverage_cached_once_refresh_refetches
FAILED backend/tests/keywords/test_rounds_api.py::test_missing_top_feeds_r3_inputs
FAILED backend/tests/keywords/test_rounds_api.py::test_r2_commit_returns_before_autocomplete_finishes
FAILED backend/tests/keywords/test_rounds_api.py::test_stale_loading_over_2min_reads_unavailable[119-loading]
FAILED backend/tests/keywords/test_rounds_api.py::test_stale_loading_over_2min_reads_unavailable[121-unavailable]
FAILED backend/tests/keywords/test_rounds_api.py::test_refresh_param_refetches_only_when_true
12 failed, 210 passed, 1 warning in 8.96s
```

## Earlier verification (before GET scope clarification)

Same command after implementation and additional concurrency checks:

```text
........................................................................ [ 31%]
........................................................................ [ 63%]
................................................................F....... [ 95%]
..........                                                               [100%]
=================================== FAILURES ===================================
_______ test_stale_loading_over_2min_reads_unavailable[121-unavailable] ________

client = <starlette.testclient.TestClient object at 0x1193688c0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11936a2a0>
autocomplete_calls = [], age = 121, status = 'unavailable'

    @pytest.mark.parametrize('age,status', [(119, 'loading'), (121, 'unavailable')])
    def test_stale_loading_over_2min_reads_unavailable(client, monkeypatch, autocomplete_calls, age, status):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        monkeypatch.setattr(store, 'now', lambda: now.isoformat())
        saved = {'status': 'loading', 'startedAt': (now - timedelta(seconds=age)).isoformat()}
        store.update_session('test', {'coverage': saved})
>       assert client.get('/keywords/test').json()['coverage']['status'] == status
E       AssertionError: assert 'loading' == 'unavailable'
E         
E         - unavailable
E         + loading

backend/tests/keywords/test_rounds_api.py:597: AssertionError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/keywords/test_rounds_api.py::test_stale_loading_over_2min_reads_unavailable[121-unavailable]
1 failed, 225 passed, 1 warning in 8.84s
```

`git diff --check` on all three allowed source/test files passed. The warning is the pre-existing Pydantic class-based config deprecation.


## Final GREEN

Applied `data['coverage'] = rounds.coverage_status(data.get('coverage') or {})` in the GET response assembly in `backend/app/routers/keywords_v2.py`. The existing helper interprets stale loading without persisting a change or fetching queries. The existing parametrized test now passes for both 119-second loading and 121-second unavailable responses. No helper or test changes were needed in this completion pass.

Verification from repository root, with the brief-required offline autocomplete backend:

```sh
AUTOCOMPLETE_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/keywords -q
# 226 passed, 1 warning in 9.09s

AUTOCOMPLETE_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests -q
# 1361 passed, 1 deselected, 2 warnings in 131.67s (0:02:11)
```

The initial keyword run without the fake-backend environment was interrupted after 101 passed because it used the live autocomplete default; the completed runs above use the required offline configuration. Warnings concern Pydantic class-based config deprecation and joblib physical-core detection falling back to logical cores.

`git diff --check` passed for all three allowed source/test files. This completion pass changed only the router and this explicitly requested report, preserving the RED section and existing work. No packages installed or commits made.
