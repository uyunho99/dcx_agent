# T5 report

Status: COMPLETE — reason priority and exact Korean strings implemented; all 62 model tests pass.

Changed only `backend/app/routers/training_v2.py`, `backend/tests/model/test_monitor_reason.py`, and this required report. No commits or package installs.

Reason priority: run detail.reason → saved training.monitor.reason (the source exported as stage5.monitor.reason) → `감시 중 오류가 났습니다(<종류>).` → `감시를 완료하지 못했습니다.` for failed/interrupted runs. Saved reasons are not overwritten with None. Tests block socket connections.

## RED

Executed before implementation: `backend/.venv/bin/python -m pytest backend/tests/model/test_monitor_reason.py -q`

```text
FF.FFFF.....                                                             [100%]
=================================== FAILURES ===================================
_ test_monitor_reason_priority[done-detail0-\uac10\uc2dc \ud45c\ubcf8 2\uac74\uc744 \uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.-None-\uac10\uc2dc \ud45c\ubcf8 2\uac74\uc744 \uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_d0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x115ffb230>
state = 'done', detail = {}, saved = '감시 표본 2건을 완료하지 못했습니다.', error = None
expected = '감시 표본 2건을 완료하지 못했습니다.'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert None == '감시 표본 2건을 완료하지 못했습니다.'

backend/tests/model/test_monitor_reason.py:45: AssertionError
_ test_monitor_reason_priority[done-detail1-\uc800\uc7a5\ub41c \uc0ac\uc720-None-\uc800\uc7a5\ub41c \uc0ac\uc720] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_d1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1160264b0>
state = 'done', detail = {'reason': None}, saved = '저장된 사유', error = None
expected = '저장된 사유'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert None == '저장된 사유'

backend/tests/model/test_monitor_reason.py:45: AssertionError
_ test_monitor_reason_priority[failed-detail3-\uc800\uc7a5\ub41c \uc0ac\uc720-ValueError-\uc800\uc7a5\ub41c \uc0ac\uc720] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_f1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1160267b0>
state = 'failed', detail = {}, saved = '저장된 사유', error = 'ValueError'
expected = '저장된 사유'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert 'ValueError' == '저장된 사유'
E         
E         - 저장된 사유
E         + ValueError

backend/tests/model/test_monitor_reason.py:45: AssertionError
_ test_monitor_reason_priority[interrupted-detail4-\uc800\uc7a5\ub41c \uc0ac\uc720-None-\uc800\uc7a5\ub41c \uc0ac\uc720] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_i0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x116026a20>
state = 'interrupted', detail = {}, saved = '저장된 사유', error = None
expected = '저장된 사유'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert '감시를 완료하지 못했습니다.' == '저장된 사유'
E         
E         - 저장된 사유
E         + 감시를 완료하지 못했습니다.

backend/tests/model/test_monitor_reason.py:45: AssertionError
_ test_monitor_reason_priority[failed-detail5-None-ValueError-\uac10\uc2dc \uc911 \uc624\ub958\uac00 \ub0ac\uc2b5\ub2c8\ub2e4(ValueError).] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_f2')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x116026390>
state = 'failed', detail = {}, saved = None, error = 'ValueError'
expected = '감시 중 오류가 났습니다(ValueError).'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert 'ValueError' == '감시 중 오류가 났습니다(ValueError).'
E         
E         - 감시 중 오류가 났습니다(ValueError).
E         + ValueError

backend/tests/model/test_monitor_reason.py:45: AssertionError
_ test_monitor_reason_priority[interrupted-detail6-None-KeyboardInterrupt-\uac10\uc2dc \uc911 \uc624\ub958\uac00 \ub0ac\uc2b5\ub2c8\ub2e4(KeyboardInterrupt).] _

data_dir = PosixPath('/private/var/folders/4w/d2l0tfps1q799p4nlh6r07kr0000gn/T/pytest-of-persona1/pytest-526/test_monitor_reason_priority_i1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x116027ce0>
state = 'interrupted', detail = {}, saved = None, error = 'KeyboardInterrupt'
expected = '감시 중 오류가 났습니다(KeyboardInterrupt).'

    @pytest.mark.parametrize('state,detail,saved,error,expected', [
        ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
         '감시 표본 2건을 완료하지 못했습니다.'),
        ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
        ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
        ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
        ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
        ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
        ('interrupted', {}, None, 'KeyboardInterrupt',
         '감시 중 오류가 났습니다(KeyboardInterrupt).'),
        ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
        ('done', {}, None, None, None),
        ('running', {}, None, None, None),
    ])
    def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
        monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
        data = {'schemaVersion': 2, 'version': 'v1',
                'training': {'monitorRunId': 'm', 'monitor': monitor}}
        work = {'runId': 'm', 'kind': 'monitor', 'state': state,
                'detail': detail, 'error': error}
        original = deepcopy(data)
        monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
        monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])
    
        result = training_v2.status('monitor-session')['monitor']
    
>       assert result['reason'] == expected
E       AssertionError: assert 'KeyboardInterrupt' == '감시 중 오류가 났습니...rdInterrupt).'
E         
E         - 감시 중 오류가 났습니다(KeyboardInterrupt).
E         + KeyboardInterrupt

backend/tests/model/test_monitor_reason.py:45: AssertionError
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[done-detail0-\uac10\uc2dc \ud45c\ubcf8 2\uac74\uc744 \uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.-None-\uac10\uc2dc \ud45c\ubcf8 2\uac74\uc744 \uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.]
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[done-detail1-\uc800\uc7a5\ub41c \uc0ac\uc720-None-\uc800\uc7a5\ub41c \uc0ac\uc720]
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[failed-detail3-\uc800\uc7a5\ub41c \uc0ac\uc720-ValueError-\uc800\uc7a5\ub41c \uc0ac\uc720]
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[interrupted-detail4-\uc800\uc7a5\ub41c \uc0ac\uc720-None-\uc800\uc7a5\ub41c \uc0ac\uc720]
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[failed-detail5-None-ValueError-\uac10\uc2dc \uc911 \uc624\ub958\uac00 \ub0ac\uc2b5\ub2c8\ub2e4(ValueError).]
FAILED backend/tests/model/test_monitor_reason.py::test_monitor_reason_priority[interrupted-detail6-None-KeyboardInterrupt-\uac10\uc2dc \uc911 \uc624\ub958\uac00 \ub0ac\uc2b5\ub2c8\ub2e4(KeyboardInterrupt).]
6 failed, 6 passed, 1 warning in 2.87s
```

## GREEN

`backend/.venv/bin/python -m pytest backend/tests/model -q` (exit 0)

```text
..............................................................           [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
62 passed, 1 warning in 7.57s
```
