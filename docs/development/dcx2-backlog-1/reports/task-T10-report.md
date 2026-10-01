# T10 — server stale clearing

Status: PASS — T10 implemented; RED recorded; focused and requested regression suites GREEN.

Implemented `clear_stale(sid, version, stage)` with version-local, idempotent deletion under the session lock. Prep completion (including reuse) clears stage3; successful export clears stage5. The judge completion hook publishes its own successful run as done and clears stage4 only when the latest run for each of Jev and GPT in that version is done. Historical failed attempts do not block successful retries. Stop/pause requests prevent completion. Other stages and versions are preserved.

Existing production files contain only an import and one completion call each. No changes were made by T10 to `versions.py`, the generic worker, or other tasks’ files. No packages were installed and no commit was created.

The generic worker normally publishes done after returning from the judge. The T10 hook publishes this terminal state at successful cache exhaustion so concurrent finishing workers can observe completion without a polling race. The generic worker’s final update only changes active rows. Prep/export pass `already_locked=True` because the existing filesystem lock is not reentrant.

## RED (before implementation)

Command: `backend/.venv/bin/python -m pytest backend/tests/context/test_stale_clear.py -q`

9 failed, 3 passed. Failures were stale markers remaining after success and the missing helper module. Full output:

```text
FF.FFFFF.F.F                                                             [100%]
=================================== FAILURES ===================================
________________ test_prep_completion_clears_only_stage3[False] ________________

setup = <function setup.<locals>.prepare at 0x119d222a0>, reuse = False

    @pytest.mark.parametrize('reuse', [False, True])
    def test_prep_completion_clears_only_stage3(setup, reuse):
        setup([doc()])
        if reuse:
            pipeline.run_prep(PrepContext(), 's', 'v1')
        version = versions.create_version('s', 'v1', 'stage3', '')
        mark('s', version)
        pipeline.run_prep(PrepContext(), 's', version)
        assert versions._data('s', version)['prep']['reused'] is reuse
>       assert_stale('s', version, 'stage3')

backend/tests/context/test_stale_clear.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 's', version = 'v2', cleared = 'stage3'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage4': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage3': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
________________ test_prep_completion_clears_only_stage3[True] _________________

setup = <function setup.<locals>.prepare at 0x119d219e0>, reuse = True

    @pytest.mark.parametrize('reuse', [False, True])
    def test_prep_completion_clears_only_stage3(setup, reuse):
        setup([doc()])
        if reuse:
            pipeline.run_prep(PrepContext(), 's', 'v1')
        version = versions.create_version('s', 'v1', 'stage3', '')
        mark('s', version)
        pipeline.run_prep(PrepContext(), 's', version)
        assert versions._data('s', version)['prep']['reused'] is reuse
>       assert_stale('s', version, 'stage3')

backend/tests/context/test_stale_clear.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 's', version = 'v2', cleared = 'stage3'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage4': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage3': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
__________________ test_judge_waits_for_both_workers[running] __________________

setup_judge = namespace(prepare=<function setup_judge.<locals>.prepare at 0x119d21580>, calls=['d000:q1-5046eeb2', 'd001:q1-5046eeb2...rivate/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_judge_waits_for_both_work0'))
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x119d66d20>
other_state = 'running'

    @pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
    def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
        setup_judge.prepare(version='v2')
        monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
        mark('session', 'v2')
        # A completed worker in another version cannot satisfy this version.
        add_run('gpt', 'done', 'v1', 'old-version')
        if other_state != 'missing':
            add_run('gpt', other_state)
        execute(add_run('jev'))
        assert_stale('session', 'v2')
        execute(add_run('gpt', run_id='gpt-retry'))
>       assert_stale('session', 'v2', 'stage4')

backend/tests/context/test_stale_clear.py:86: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'session', version = 'v2', cleared = 'stage4'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage4': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
__________________ test_judge_waits_for_both_workers[paused] ___________________

setup_judge = namespace(prepare=<function setup_judge.<locals>.prepare at 0x11a0ad300>, calls=['d000:q1-5046eeb2', 'd001:q1-5046eeb2...rivate/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_judge_waits_for_both_work1'))
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x119d66b40>
other_state = 'paused'

    @pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
    def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
        setup_judge.prepare(version='v2')
        monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
        mark('session', 'v2')
        # A completed worker in another version cannot satisfy this version.
        add_run('gpt', 'done', 'v1', 'old-version')
        if other_state != 'missing':
            add_run('gpt', other_state)
        execute(add_run('jev'))
        assert_stale('session', 'v2')
        execute(add_run('gpt', run_id='gpt-retry'))
>       assert_stale('session', 'v2', 'stage4')

backend/tests/context/test_stale_clear.py:86: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'session', version = 'v2', cleared = 'stage4'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage4': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
__________________ test_judge_waits_for_both_workers[failed] ___________________

setup_judge = namespace(prepare=<function setup_judge.<locals>.prepare at 0x11a0af560>, calls=['d000:q1-5046eeb2', 'd001:q1-5046eeb2...rivate/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_judge_waits_for_both_work2'))
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x119d66e40>
other_state = 'failed'

    @pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
    def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
        setup_judge.prepare(version='v2')
        monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
        mark('session', 'v2')
        # A completed worker in another version cannot satisfy this version.
        add_run('gpt', 'done', 'v1', 'old-version')
        if other_state != 'missing':
            add_run('gpt', other_state)
        execute(add_run('jev'))
        assert_stale('session', 'v2')
        execute(add_run('gpt', run_id='gpt-retry'))
>       assert_stale('session', 'v2', 'stage4')

backend/tests/context/test_stale_clear.py:86: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'session', version = 'v2', cleared = 'stage4'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage4': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
________________ test_judge_waits_for_both_workers[interrupted] ________________

setup_judge = namespace(prepare=<function setup_judge.<locals>.prepare at 0x11a0afce0>, calls=['d000:q1-5046eeb2', 'd001:q1-5046eeb2...rivate/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_judge_waits_for_both_work3'))
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x119d69cd0>
other_state = 'interrupted'

    @pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
    def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
        setup_judge.prepare(version='v2')
        monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
        mark('session', 'v2')
        # A completed worker in another version cannot satisfy this version.
        add_run('gpt', 'done', 'v1', 'old-version')
        if other_state != 'missing':
            add_run('gpt', other_state)
        execute(add_run('jev'))
        assert_stale('session', 'v2')
        execute(add_run('gpt', run_id='gpt-retry'))
>       assert_stale('session', 'v2', 'stage4')

backend/tests/context/test_stale_clear.py:86: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'session', version = 'v2', cleared = 'stage4'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage4': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
__________________ test_judge_waits_for_both_workers[missing] __________________

setup_judge = namespace(prepare=<function setup_judge.<locals>.prepare at 0x11a0ad300>, calls=['d000:q1-5046eeb2', 'd001:q1-5046eeb2...rivate/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_judge_waits_for_both_work4'))
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x119d6aab0>
other_state = 'missing'

    @pytest.mark.parametrize('other_state', ['running', 'paused', 'failed', 'interrupted', 'missing'])
    def test_judge_waits_for_both_workers(setup_judge, monkeypatch, other_state):
        setup_judge.prepare(version='v2')
        monkeypatch.setattr(settings, 'label_gpt_backend', 'fake')
        mark('session', 'v2')
        # A completed worker in another version cannot satisfy this version.
        add_run('gpt', 'done', 'v1', 'old-version')
        if other_state != 'missing':
            add_run('gpt', other_state)
        execute(add_run('jev'))
        assert_stale('session', 'v2')
        execute(add_run('gpt', run_id='gpt-retry'))
>       assert_stale('session', 'v2', 'stage4')

backend/tests/context/test_stale_clear.py:86: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'session', version = 'v2', cleared = 'stage4'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage4': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
________________________ test_export_clears_only_stage5 ________________________

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_export_clears_only_stage50')

    def test_export_clears_only_stage5(data_dir):
        sid, _ = prepared(data_dir)
        version = versions.create_version(sid, 'v1', 'stage5', '')
        seed(sid)
        mark(sid, version)
        result = export.write(sid, version, without_model=True)
        assert (data_dir / result['exportRef']).exists()
>       assert_stale(sid, version, 'stage5')

backend/tests/context/test_stale_clear.py:110: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

sid = 'modeltest', version = 'v2', cleared = 'stage5'

    def assert_stale(sid, version, cleared=None):
>       assert versions._data(sid, version)['stale'] == {
            key: value for key, value in STALE.items() if key != cleared}
E       AssertionError: assert {'stage3': 's...hanged in v2'} == {'stage3': 's...hanged in v2'}
E         
E         Omitting 3 identical items, use -vv to show
E         Left contains 1 more item:
E         {'stage5': 'stage3 changed in v2'}
E         Use -v to get more diff

backend/tests/context/test_stale_clear.py:38: AssertionError
__________________ test_clear_is_idempotent_and_version_local __________________

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-532/test_clear_is_idempotent_and_v0')

    def test_clear_is_idempotent_and_version_local(data_dir):
>       from app.context.stale import clear_stale
E       ModuleNotFoundError: No module named 'app.context.stale'

backend/tests/context/test_stale_clear.py:124: ModuleNotFoundError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/context/test_stale_clear.py::test_prep_completion_clears_only_stage3[False]
FAILED backend/tests/context/test_stale_clear.py::test_prep_completion_clears_only_stage3[True]
FAILED backend/tests/context/test_stale_clear.py::test_judge_waits_for_both_workers[running]
FAILED backend/tests/context/test_stale_clear.py::test_judge_waits_for_both_workers[paused]
FAILED backend/tests/context/test_stale_clear.py::test_judge_waits_for_both_workers[failed]
FAILED backend/tests/context/test_stale_clear.py::test_judge_waits_for_both_workers[interrupted]
FAILED backend/tests/context/test_stale_clear.py::test_judge_waits_for_both_workers[missing]
FAILED backend/tests/context/test_stale_clear.py::test_export_clears_only_stage5
FAILED backend/tests/context/test_stale_clear.py::test_clear_is_idempotent_and_version_local
9 failed, 3 passed, 1 warning in 2.82s

```

## GREEN — focused tests

```text
............                                                             [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 1 warning in 2.85s

```

## GREEN — required verification

Command: `backend/.venv/bin/python -m pytest backend/tests/context backend/tests/prep backend/tests/label backend/tests/model -q`

```text
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 48%]
........................................................................ [ 65%]
........................................................................ [ 81%]
........................................................................ [ 97%]
...........                                                              [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
443 passed, 1 warning in 32.10s

```

Validation: `git diff --check` passed for the T10 production/test paths. Regression ran against the shared working tree, including concurrent tasks’ changes.
