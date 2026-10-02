# Task T1 구현 보고서

- 작업 위치: `/Users/persona1/Desktop/dcx_agent-stage0-task-mode`
- 브랜치: `feature/dcx2-stage0-task-mode`
- 시작 커밋: `4ec7719bb79d5bb2214fc4582e34a99b90870551`
- 범위: T1 모델, 양쪽 라벨, Markdown 렌더링, API 검증, R1 이후 변경 경고.
- 작업 시작 시 worktree는 깨끗했다. 다른 에이전트를 사용하지 않았다.

## 1. 소스 수정 전 golden 생성

아래 명령을 소스 및 새 테스트 편집 전에 실행했다. 시작 커밋의 `make_context()`와 렌더러를 사용했다.

```sh
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
import hashlib
import runpy
from pathlib import Path
from app.context.render import render_context_md
make_context = runpy.run_path('backend/tests/context/test_render.py')['make_context']
path = Path('backend/tests/context/fixtures/legacy_context.md')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(render_context_md(make_context(), ['두 번째 발견', '첫 번째 발견']).encode())
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
```

SHA-256: `fca9a707f3fc08e5158803b40006c4ac5ee0d83deae754867bc4b738b719221d`

최종 검토 때 `shasum -a 256 backend/tests/context/fixtures/legacy_context.md`로 동일 해시를 재확인했다.

## 2. RED

```sh
LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/context/test_models_task_mode.py backend/tests/context/test_api_task_mode.py backend/tests/context/test_render_task_mode.py -q -p no:cacheprovider
```

소스 수정 전 최종 RED 결과: **24 failed, 3 passed, 1 warning in 3.64s**.

- 새 모델과 필드가 없어서 구조 지표/페르소나 검증이 실패하거나 새 taskMode가 무시되었다.
- 선택 필드가 기존에는 필수여서 metric/explore의 최소 POST가 422였다.
- 새 taskMode/keyMetrics/personaSeeds 경고가 없었고, 구조 지표를 API가 거부했다.
- 새 Markdown 줄과 페르소나 섹션이 없었다.
- `test_legacy_bytes_identical`은 PASS였다.
- 이미 존재하는 `researchQuestion`, `oneLiner`의 R1 변경 경고 회귀 사례 2개도 PASS였다. 기존 동작을 검증하는 테스트이므로 실패를 인위적으로 만들지 않았다.
- 첫 RED 실행은 22 failed / 5 passed였다. 포지셔닝 충돌 거부 테스트가 기존의 다른 축 필수 검증 때문에 통과하는 것을 발견해, 단일 축 입력은 먼저 유효해야 한다는 전제를 추가하고 다시 RED를 실행했다.

추가 경계 사례 RED:

```sh
LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/context/test_render_task_mode.py::test_legacy_metric_whitespace_preserved -q -p no:cacheprovider
```

결과: **1 failed, 1 warning in 0.05s**. 이름을 strip하면 기존 지표의 공백이 사라져 Markdown 바이트가 달라졌다. 공백뿐인 지표는 거부하되 유효한 지표명의 원문은 보존하도록 고쳤다.

## 3. 구현 및 GREEN

- `TaskMode`, `KeyMetric`, `PersonaDimension`, `PersonaSeed`, `PersonaSeeds` 추가.
- 문자열/구조 혼합 지표를 지원하고 schemaVersion=1을 유지한다.
- taskMode 누락/null은 기존의 지표·분석 목적·가격/시장 기본 포지셔닝 필수 규칙을 유지한다.
- metric은 지표 필수, explore는 지표 선택. 두 유형 모두 분석 목적과 포지셔닝 선택.
- 빈 분석 목적 객체를 None으로 정규화한다. 포지셔닝의 빈 선택지는 None으로 변환하며 직접 입력은 strip 및 40자 제한, 같은 축의 이중 입력은 거부한다.
- 페르소나는 strip 후 1~40자, 20개 제한, 선택 태그, exploreBeyond 기본 True이다. 중복 제거는 화면 책임이며 서버는 입력 순서를 보존한다.
- 과제 유형 줄, 구조 지표 상세, 선택/직접 입력 포지셔닝, 페르소나 목록과 디멘션 지시문을 렌더링한다. 기존 줄 문구 및 golden 바이트는 보존한다.
- R1 이후 경고 대상은 oneLiner/researchQuestion/taskMode/keyMetrics/personaSeeds이다. 이전 ProjectContext를 검증하고 `model_dump(mode='json')`으로 정규화해 새 저장값과 필드별 비교한다. 검증 실패 시 원래 dict 비교로 돌아간다.
- 동일 이름의 문자열→구조 지표 변환은 경고하지 않는다. null→explore는 경고한다. 같은 값 재저장 및 R1 이전 변경은 경고하지 않는다.
- 모델 검증 실패 fallback 테스트의 입력에 researchQuestion.template=None을 명시했다. raw 비교 시 누락된 template이 별도 차이로 감지되는 것을 피하고 의도한 두 필드의 fallback 비교를 검증하기 위한 fixture 보정이다.
- 렌더링의 지표/페르소나 처리를 작은 함수로 나누고 기존 렌더링 순서는 유지했다. 불필요한 공통 추상화나 관련 없는 리팩터링은 하지 않았다.

최종 새 테스트 GREEN 명령:

```sh
LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/context/test_models_task_mode.py backend/tests/context/test_api_task_mode.py backend/tests/context/test_render_task_mode.py -q -p no:cacheprovider
```

결과: **28 passed, 1 warning in 2.41s**.

커밋 전 전체 검증 명령:

```sh
LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/context backend/tests/known backend/tests/test_integration_stage0_2.py backend/tests/keywords -q -p no:cacheprovider
```

최종 결과: **540 passed, 2 warnings in 23.85s**. 공백 보존 사례 추가 전 첫 전체 검증도 **539 passed, 2 warnings in 26.13s**였다.

`git diff --check`도 통과했다. 기존 테스트 및 기대값은 수정하지 않았다. labels parity 및 모든 Enum 라벨 커버리지는 기존 테스트로 검증했다. 네트워크 없이 fake 백엔드 환경에서 실행했다.

## 4. 변경 파일

1. `backend/app/context/models.py`
2. `backend/app/context/labels.py`
3. `backend/app/context/render.py`
4. `backend/app/routers/context.py` — `_save_context` 경고 비교 부분만
5. `frontend/src/lib/contextLabels.ts`
6. `backend/tests/context/fixtures/legacy_context.md`
7. `backend/tests/context/test_models_task_mode.py`
8. `backend/tests/context/test_render_task_mode.py`
9. `backend/tests/context/test_api_task_mode.py`

요청된 보고서는 `.superpowers/sdd/03-plan/task-T1-report.md`에 작성했다. `.superpowers`는 저장소의 ignore 대상이므로 보고서는 로컬 파일로 남긴다.

## 5. 커밋

상태: **BLOCKED (커밋만 차단)**. 생성된 커밋 없음. HEAD는 시작 커밋 `4ec7719bb79d5bb2214fc4582e34a99b90870551` 그대로다.

전체 검증 통과 후 소유 파일 9개만 명시한 `git add`를 실행했으나 다음 오류로 실패했다:

```text
fatal: Unable to create '/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-stage0-task-mode/index.lock': Operation not permitted
```

worktree의 `.git` 파일이 가리키는 메타데이터 경로가 현재 세션의 쓰기 허용 범위 밖이다. 승인 정책은 never라 권한 승격을 요청하거나 샌드박스를 우회하지 않았다. 다른 작업 디렉터리에서 작업하거나 별도 저장소를 만들지 않았다. 구현 파일은 모두 지정된 worktree에 보존했다.

권한이 있는 환경에서 소유 파일 9개를 stage한 뒤 사용할 예정이었던 커밋 메시지:

```text
feat(context): 과제 유형 · 구조 지표 · 생각하는 페르소나 모델과 렌더링 (T1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## 6. 우려 및 범위 제한

- 구현 관련 미해결 사항 없음. 단, Git 메타데이터 쓰기 권한 때문에 요청된 커밋을 만들지 못했다.
- 기존 설정 모델의 Pydantic class Config deprecated 경고와 joblib의 물리 코어 수 감지 경고가 있다. 테스트 실패는 아니다.
- 설계 D-311대로 `backend/app/context/versions.py`는 수정하지 않았다. 버전 비교 화면에서 문자열 지표→구조 지표 변환이 한 번 변경으로 표시될 수 있는 알려진 제한은 그대로다. R1 변경 경고 비교에서는 이를 정규화해 해결했다.
- R1 프롬프트 및 화면 변경은 T3/T4/T5/T6 범위이므로 이 커밋에 포함하지 않았다.
