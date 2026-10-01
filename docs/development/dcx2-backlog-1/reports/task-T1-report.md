# T1 report

Status: COMPLETE — RED confirmed before implementation; GREEN confirmed before and after refactoring (213 passed).

Implemented only T1-owned source, tests, fixtures, and the explicitly requested report:
- `backend/app/external/naver_autocomplete.py`
- `backend/app/config.py` (one setting line)
- `backend/tests/fixtures/autocomplete/suggestions.json`
- `backend/tests/keywords/test_autocomplete.py`

The brief's `AutocompleteResult(queries, failed, total)` contract takes precedence over the older list-only design signature. Requests use the specified endpoint and all parameters, an explicit User-Agent, 10-second timeout, and injected one-second pauses between HTTP requests (including failed requests). Queries use existing normalization and retain their best rank within 1–10. Invalid or empty responses fail that seed atomically; no usable results raises `AutocompleteUnavailable`. Fake mode reads a fixed fixture independent of seed text and performs no HTTP or sleep. Caller-owned clients stay open; adapter-owned clients close in `finally`.

Tests block socket connections and use MockTransport or fixtures; no packages were installed and no commits were made. Other jobs' files were not edited.

## RED

Command from repository root:
```sh
backend/.venv/bin/python -m pytest backend/tests/keywords -q
```

Output captured before any adapter/config implementation. The 19 T1 cases errored because the new module was absent. Six additional failures came from concurrently added rank-coverage tests outside T1 ownership; those files were left untouched.

```text
EEEEEEEEEEEEEEEEEEE.............FFFFFF.................................. [ 33%]
........................................................................ [ 67%]
.....................................................................    [100%]
==================================== ERRORS ====================================
___________ ERROR at setup of test_parses_suggestions_in_rank_order ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b92600>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
___________ ERROR at setup of test_dedupes_keeping_best_rank[False] ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b6a3c0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
____________ ERROR at setup of test_dedupes_keeping_best_rank[True] ____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b92210>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
__ ERROR at setup of test_partial_failure_returns_received_and_counts_failed ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b936b0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
__________ ERROR at setup of test_all_failed_raises_unavailable[None] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118ba8500>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body1] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118baab70>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body2] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118bab890>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body3] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118baa8d0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body4] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118ba87a0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body5] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b6a990>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body6] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b92a50>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body7] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b93cb0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_all_failed_raises_unavailable[body8] __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118b927e0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
___ ERROR at setup of test_http_and_json_errors_raise_unavailable[response0] ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118bab0b0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
___ ERROR at setup of test_http_and_json_errors_raise_unavailable[response1] ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118babfe0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_____________ ERROR at setup of test_empty_seeds_raise_unavailable _____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118ba9f10>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
_________ ERROR at setup of test_http_backend_builds_expected_request __________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118ba92b0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
______________ ERROR at setup of test_fake_backend_makes_no_http _______________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1186a18e0>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
__________________ ERROR at setup of test_limits_ranks_to_ten __________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x118c06660>

    @pytest.fixture
    def adapter(monkeypatch):
>       from app.external import naver_autocomplete
E       ImportError: cannot import name 'naver_autocomplete' from 'app.external' (/Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/external/__init__.py)

backend/tests/keywords/test_autocomplete.py:21: ImportError
=================================== FAILURES ===================================
____________________________ test_rank_weighting_m1 ____________________________

    def test_rank_weighting_m1():
        human = [('alpha', 1), ('beta', 2), ('gamma', 4)]
>       assert compute(human, [keyword('alpha'), keyword('gamma')], weighting='rank').m1 == pytest.approx(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            (1 + 0.25) / (1 + 0.5 + 0.25)
        )
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:93: TypeError
__________________ test_rank_bands_three_with_empty_band_none __________________

    def test_rank_bands_three_with_empty_band_none():
        human = [('alpha', 1), ('beta', 3), ('gamma', 7), ('delta', 10)]
>       result = compute(human, [keyword('alpha'), keyword('delta')], weighting='rank')
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:100: TypeError
______________________ test_rank_mode_m7_none_with_reason ______________________

    def test_rank_mode_m7_none_with_reason():
>       result = compute([('human', 1)], [keyword('low', 5), keyword('zero', 0)], weighting='rank')
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:112: TypeError
________________ test_rank_missing_top_sorted_by_rank_limit_20 _________________

    def test_rank_missing_top_sorted_by_rank_limit_20():
        human = [(f'q{i:02}', rank) for i, rank in enumerate(list(range(10, 0, -1)) * 3)]
>       result = compute(human, [keyword('q09')], weighting='rank')
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:120: TypeError
____________________ test_volume_mode_rank_fields_are_none _____________________

sample = ([('에어컨 소음', 100), ('에어컨 냄새', 50), ('실외기', 30), ('리모컨', 20)], [Keyword(id='소음', kw='소음', axis='physical', sub='test', ... axis='physical', sub='test', round=1, origin='llm', status='pending', reject=None, volume={'monthly': 5}, badges=[])])

    def test_volume_mode_rank_fields_are_none(sample):
>       for result in (compute(*sample), compute(*sample, weighting='volume')):
                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:127: TypeError
_______________________ test_rank_empty_and_axis_counts ________________________

sample = ([('에어컨 소음', 100), ('에어컨 냄새', 50), ('실외기', 30), ('리모컨', 20)], [Keyword(id='소음', kw='소음', axis='physical', sub='test', ... axis='physical', sub='test', round=1, origin='llm', status='pending', reject=None, volume={'monthly': 5}, badges=[])])

    def test_rank_empty_and_axis_counts(sample):
>       empty = compute([], [], weighting='rank')
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: compute() got an unexpected keyword argument 'weighting'

backend/tests/keywords/test_coverage.py:134: TypeError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/keywords/test_coverage.py::test_rank_weighting_m1 - Type...
FAILED backend/tests/keywords/test_coverage.py::test_rank_bands_three_with_empty_band_none
FAILED backend/tests/keywords/test_coverage.py::test_rank_mode_m7_none_with_reason
FAILED backend/tests/keywords/test_coverage.py::test_rank_missing_top_sorted_by_rank_limit_20
FAILED backend/tests/keywords/test_coverage.py::test_volume_mode_rank_fields_are_none
FAILED backend/tests/keywords/test_coverage.py::test_rank_empty_and_axis_counts
ERROR backend/tests/keywords/test_autocomplete.py::test_parses_suggestions_in_rank_order
ERROR backend/tests/keywords/test_autocomplete.py::test_dedupes_keeping_best_rank[False]
ERROR backend/tests/keywords/test_autocomplete.py::test_dedupes_keeping_best_rank[True]
ERROR backend/tests/keywords/test_autocomplete.py::test_partial_failure_returns_received_and_counts_failed
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[None]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body1]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body2]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body3]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body4]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body5]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body6]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body7]
ERROR backend/tests/keywords/test_autocomplete.py::test_all_failed_raises_unavailable[body8]
ERROR backend/tests/keywords/test_autocomplete.py::test_http_and_json_errors_raise_unavailable[response0]
ERROR backend/tests/keywords/test_autocomplete.py::test_http_and_json_errors_raise_unavailable[response1]
ERROR backend/tests/keywords/test_autocomplete.py::test_empty_seeds_raise_unavailable
ERROR backend/tests/keywords/test_autocomplete.py::test_http_backend_builds_expected_request
ERROR backend/tests/keywords/test_autocomplete.py::test_fake_backend_makes_no_http
ERROR backend/tests/keywords/test_autocomplete.py::test_limits_ranks_to_ten
6 failed, 188 passed, 1 warning, 19 errors in 9.84s
```

## GREEN

Command from repository root:
```sh
backend/.venv/bin/python -m pytest backend/tests/keywords -q
```

Output after implementation:

```text
........................................................................ [ 33%]
........................................................................ [ 67%]
.....................................................................    [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
213 passed, 1 warning in 10.05s
```

## Refactor verification

Extracted response loading into `_load`, keeping parsing and aggregation separate without changing behavior.

Command from repository root:
```sh
backend/.venv/bin/python -m pytest backend/tests/keywords -q
```

Output:

```text
........................................................................ [ 33%]
........................................................................ [ 67%]
.....................................................................    [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
213 passed, 1 warning in 8.88s
```

The remaining warning is the existing Pydantic class-based config deprecation.
