# T2 report

Status: COMPLETE — rank metrics implemented; 19 tests pass, including all 13 existing volume tests.

## Scope

Changed only `backend/app/keywords/coverage.py`, `backend/tests/keywords/test_coverage.py`, and this requested report. No commits or package installations. Other jobs' changes were preserved.

Implemented reciprocal-rank M1, three labeled rank bands with empty bands returning None, rank-mode m2=None, M7=None with reason `no_volume`, empty LLM-only IDs, and ascending-rank missing queries capped at 20. M6 retains its existing calculation. Volume mode keeps its behavior and returns None for both new report fields.

Command used in every phase:

```sh
backend/.venv/bin/python -m pytest backend/tests/keywords/test_coverage.py -q
```

## RED

Added the four required named tests plus explicit/default volume compatibility and empty-rank/M6/purity coverage before implementation. All six new tests failed for the expected missing `weighting` parameter; all 13 existing tests passed. Captured pytest output:

```text
.............FFFFFF                                                      [100%]
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
6 failed, 13 passed, 1 warning in 0.06s
```

## GREEN

Implemented the rank path and report fields. Full-file output:

```text
...................                                                      [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 1 warning in 0.03s
```

## Refactor and final verification

Consolidated repeated mode comparisons into a local `rank_mode` flag without changing metric behavior. Re-ran the full file:

```text
...................                                                      [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 1 warning in 0.02s
```

`git diff --check` passed. The sole warning is the existing Pydantic class-based configuration deprecation in `backend/app/config.py`.
