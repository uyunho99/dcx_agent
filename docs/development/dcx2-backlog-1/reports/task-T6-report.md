# T6 — Vote lease refresh

Status: implementation complete; required work/label verification GREEN (220 passed).

Judge entry point registers a heartbeat callback and clears it on exit. Background pulses and checkpoint heartbeats renew only that run's pending leases, after the work transaction closes. Refresh errors log the exception type and retry on the next heartbeat. The 10-second interval and 600-second reclaim threshold are unchanged.

Changed only `backend/app/work/worker.py`, `backend/app/label/votes.py`, the new `backend/tests/label/test_lease_refresh.py`, and this requested report. No commits or package installation.

## RED (before implementation)

Command: `backend/.venv/bin/python -m pytest backend/tests/label/test_lease_refresh.py -q`

```text
FFFFF                                                                    [100%]
=================================== FAILURES ===================================
_________ test_heartbeat_refreshes_only_own_pending_lease[background] __________

lease_env = (Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first'), <app.label.votes.VoteCache object at 0x10e6de060>, [1010.0])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e6dfe90>
pulse = True

    @pytest.mark.parametrize('pulse', [True, False], ids=['background', 'checkpoint'])
    def test_heartbeat_refreshes_only_own_pending_lease(lease_env, monkeypatch, pulse):
        ctx, cache, now = lease_env
    
        def judge_work(context):
            now[0] += 10
            if pulse:
                context._pulse()
            else:
                context.heartbeat(.5, {})
            snapshot = rows(cache)
            assert snapshot['a']['at'] == now[0]
            assert {key: snapshot[key]['at'] for key in ('b', 'c', 'd')} == {
                'b': 1000.0, 'c': 1000.0, 'd': 1000.0}
    
        monkeypatch.setattr(judge, 'run_worker', judge_work)
>       worker._judge(ctx)

backend/tests/label/test_lease_refresh.py:65: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
backend/app/work/worker.py:65: in _judge
    run_worker(context)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

context = Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first')

    def judge_work(context):
        now[0] += 10
        if pulse:
            context._pulse()
        else:
            context.heartbeat(.5, {})
        snapshot = rows(cache)
>       assert snapshot['a']['at'] == now[0]
E       assert 1000.0 == 1010.0

backend/tests/label/test_lease_refresh.py:60: AssertionError
_________ test_heartbeat_refreshes_only_own_pending_lease[checkpoint] __________

lease_env = (Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first'), <app.label.votes.VoteCache object at 0x10e708e30>, [1010.0])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e7098b0>
pulse = False

    @pytest.mark.parametrize('pulse', [True, False], ids=['background', 'checkpoint'])
    def test_heartbeat_refreshes_only_own_pending_lease(lease_env, monkeypatch, pulse):
        ctx, cache, now = lease_env
    
        def judge_work(context):
            now[0] += 10
            if pulse:
                context._pulse()
            else:
                context.heartbeat(.5, {})
            snapshot = rows(cache)
            assert snapshot['a']['at'] == now[0]
            assert {key: snapshot[key]['at'] for key in ('b', 'c', 'd')} == {
                'b': 1000.0, 'c': 1000.0, 'd': 1000.0}
    
        monkeypatch.setattr(judge, 'run_worker', judge_work)
>       worker._judge(ctx)

backend/tests/label/test_lease_refresh.py:65: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
backend/app/work/worker.py:65: in _judge
    run_worker(context)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

context = Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first')

    def judge_work(context):
        now[0] += 10
        if pulse:
            context._pulse()
        else:
            context.heartbeat(.5, {})
        snapshot = rows(cache)
>       assert snapshot['a']['at'] == now[0]
E       assert 1000.0 == 1010.0

backend/tests/label/test_lease_refresh.py:60: AssertionError
________________ test_live_lease_survives_650_seconds[running] _________________

lease_env = (Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first'), <app.label.votes.VoteCache object at 0x10e70b470>, [1650.0])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e70bcb0>
state = 'running'

    @pytest.mark.parametrize('state', ['running', 'paused'])
    def test_live_lease_survives_650_seconds(lease_env, monkeypatch, state):
        ctx, cache, now = lease_env
        with transaction(ctx.sid) as db:
            db.execute('UPDATE runs SET state=? WHERE run_id=?', (state, ctx.run_id))
    
        def judge_work(context):
            for _ in range(65):
                now[0] += 10
                context._pulse()
            competitor = VoteCache(cache.path.parent)
            assert competitor.lease(4, 'other') == ['d']
            assert rows(cache)['a']['run_id'] == 'first'
    
        monkeypatch.setattr(judge, 'run_worker', judge_work)
>       worker._judge(ctx)

backend/tests/label/test_lease_refresh.py:87: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
backend/app/work/worker.py:65: in _judge
    run_worker(context)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

context = Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first')

    def judge_work(context):
        for _ in range(65):
            now[0] += 10
            context._pulse()
        competitor = VoteCache(cache.path.parent)
>       assert competitor.lease(4, 'other') == ['d']
E       AssertionError: assert ['a', 'd'] == ['d']
E         
E         At index 0 diff: 'a' != 'd'
E         Left contains one more item: 'd'
E         Use -v to get more diff

backend/tests/label/test_lease_refresh.py:83: AssertionError
_________________ test_live_lease_survives_650_seconds[paused] _________________

lease_env = (Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first'), <app.label.votes.VoteCache object at 0x10e70aa50>, [1650.0])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e70adb0>
state = 'paused'

    @pytest.mark.parametrize('state', ['running', 'paused'])
    def test_live_lease_survives_650_seconds(lease_env, monkeypatch, state):
        ctx, cache, now = lease_env
        with transaction(ctx.sid) as db:
            db.execute('UPDATE runs SET state=? WHERE run_id=?', (state, ctx.run_id))
    
        def judge_work(context):
            for _ in range(65):
                now[0] += 10
                context._pulse()
            competitor = VoteCache(cache.path.parent)
            assert competitor.lease(4, 'other') == ['d']
            assert rows(cache)['a']['run_id'] == 'first'
    
        monkeypatch.setattr(judge, 'run_worker', judge_work)
>       worker._judge(ctx)

backend/tests/label/test_lease_refresh.py:87: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
backend/app/work/worker.py:65: in _judge
    run_worker(context)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

context = Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first')

    def judge_work(context):
        for _ in range(65):
            now[0] += 10
            context._pulse()
        competitor = VoteCache(cache.path.parent)
>       assert competitor.lease(4, 'other') == ['d']
E       AssertionError: assert ['a', 'd'] == ['d']
E         
E         At index 0 diff: 'a' != 'd'
E         Left contains one more item: 'd'
E         Use -v to get more diff

backend/tests/label/test_lease_refresh.py:83: AssertionError
__________________ test_refresh_failure_is_logged_and_retried __________________

lease_env = (Context(sid='s1', version='v1', kind='judge', args={'labeler': 'gpt'}, run_id='first'), <app.label.votes.VoteCache object at 0x10df1da00>, [1000.0])
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e7084d0>
caplog = <_pytest.logging.LogCaptureFixture object at 0x10e726ba0>

    def test_refresh_failure_is_logged_and_retried(lease_env, monkeypatch, caplog):
        ctx, cache, now = lease_env
>       original = VoteCache.refresh
                   ^^^^^^^^^^^^^^^^^
E       AttributeError: type object 'VoteCache' has no attribute 'refresh'

backend/tests/label/test_lease_refresh.py:97: AttributeError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/label/test_lease_refresh.py::test_heartbeat_refreshes_only_own_pending_lease[background]
FAILED backend/tests/label/test_lease_refresh.py::test_heartbeat_refreshes_only_own_pending_lease[checkpoint]
FAILED backend/tests/label/test_lease_refresh.py::test_live_lease_survives_650_seconds[running]
FAILED backend/tests/label/test_lease_refresh.py::test_live_lease_survives_650_seconds[paused]
FAILED backend/tests/label/test_lease_refresh.py::test_refresh_failure_is_logged_and_retried
5 failed, 1 warning in 1.92s
```

## GREEN

Command: `backend/.venv/bin/python -m pytest backend/tests/label/test_lease_refresh.py -q`

```text
.....                                                                    [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
5 passed, 1 warning in 0.37s
```

Command: `backend/.venv/bin/python -m pytest backend/tests/work backend/tests/label -q`

```text
........................................................................ [ 32%]
........................................................................ [ 65%]
........................................................................ [ 98%]
....                                                                     [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
220 passed, 1 warning in 24.45s
```

The first full verification overlapped another job's audit API edits and returned `4 failed, 216 passed, 1 warning in 25.33s` (three `test_audit_kind.py` cases and `test_manual_audit_and_reissue_rounds`). The audit implementation on disk then included the new `kind` argument; the unchanged T6 implementation passed the full rerun above. No other job's files were edited.

Coverage: background/checkpoint renewal, other-run isolation, unchanged done/bad rows, running/paused leases surviving 650 simulated seconds, expiry without heartbeats, callback cleanup, and logged failure followed by successful retry. Tests block network connections.

Whitespace verification: `git diff --check -- backend/app/work/worker.py backend/app/label/votes.py backend/tests/label/test_lease_refresh.py` passed.

## Stage 0–2 crawl regression verification

Command: `backend/.venv/bin/python -m pytest backend/tests/crawl backend/tests/test_integration_stage0_2.py -q`

```text
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 49%]
........................................................................ [ 66%]
........................................................................ [ 83%]
........................................................................ [ 99%]
.                                                                        [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

tests/test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/.venv/lib/python3.12/site-packages/joblib/externals/loky/backend/context.py:134: UserWarning: Could not find the number of physical cores for the following reason:
  invalid literal for int() with base 10: ''
  Returning the number of logical cores instead. You can silence this warning by setting LOKY_MAX_CPU_COUNT to the number of cores you want to use.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
433 passed, 2 warnings in 75.83s (0:01:15)
```
