# T15 구현 보고서 — 버전 · 활동 배지 · 통합 테스트

## 범위와 상태

- 작업 디렉터리: `/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5`.
- 사용자 brief 및 `02-design-r2.md` 2.1, 2.4, 7, 9.1을 기준으로 구현했다.
- 외부 네트워크, git 쓰기 명령, 커밋, 하위 에이전트를 사용하지 않았다.
- 소유 범위 밖 프로덕션 수정: **없음**. 병렬 T14/T16 작업 파일은 변경하지 않았다.

## 정확한 변경 파일

1. `backend/app/routers/sessions.py`
   - `/save-session` 서버 소유 키에 `prep`, `labeling`, `training` 추가. 기존 소유 키를 유지한다.
2. `backend/app/context/store.py`
   - `session_activities`에 `app.work.runner.status` 결과를 포함한다.
   - `state`를 기존 활동 계약의 `status`로 투영하고 `runId`, `progress`, `updatedAt`, `label`을 제공한다.
   - `판정 62%`, `학습 중`, `중단됨 · 이어서 진행` 문구를 검증했다.
   - 기존 활동 우선순위와 실행 중 버전 생성 방지 경로를 재사용한다.
3. `backend/app/context/versions.py`
   - `*.sqlite`는 read-only source connection의 `backup`으로 복사하고 SQLite WAL/SHM/journal 보조 파일을 제외한다. 연결을 명시적으로 닫는다.
   - stage3 재시작: `prep.status=stale`, 설정 및 `derivedRef` 유지. 같은 규칙은 실제 prep 파이프라인의 캐시로 재사용한다.
   - stage4 이하 재시작: `human` 보존, `final`/`queue`를 `stale_final`/`stale_queue`에 보관하고 활성 projection을 비운다. 캐시 reconciliation cursor, 검수 완료 기록, 감사 snapshot, 모델 projection을 초기화한다.
   - `labeling.started=False`로 방식을 다시 고를 수 있게 하고 공용 `judgeRefs`는 보존한다. 이전 run ID와 이전 감사 집계는 승계하지 않는다.
   - 안내 필드 `labeling.restartMessage`: `이 라벨은 v1 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.` (버전명은 복사 원본).
   - stage5 이하 재시작: `training.status=stale`, 과거 모델/실행/내보내기 참조를 활성 training에서 제거한다. 원본 버전 및 외부 모델/내보내기 파일은 보존한다.
   - prep/judge/train/infer running 시 API 409, paused judge 허용.
   - stage3 비교는 `stage_3.before/after`, stage4/5 비교는 `stage_5.before/after`를 반환한다. stage3의 실제 derived 저장 위치도 읽는다. 보고서가 없으면 null이다.
4. `backend/tests/context/test_versions_stage3_5.py`
   - 저장 보호, 워커별 409, paused judge, 활동 배지, 단계별 stale 처리, 수치 비교, SQLite 동시 제출 snapshot 검증.
5. `backend/tests/test_integration_stage3_5.py`
   - fixture 수집본 → 실제 prep(fake embedder) → POST `/label/{sid}/start` → fake Jev HTTP transport + fake codex 실행 → 고정 사람 응답 → 감사 한 라운드 → 실제 앙상블 학습/저장/추론 → 기본 export → 실제 KMeans 군집.
   - stage4의 실제 버전 생성 후 Jev 추가 호출 0회, codex invocation 파일 변화 0회, 같은 cache 경로, 원본 human projection 및 새 버전 human 이력 보존을 검증한다.
   - stage3의 실제 버전 생성 및 prep 재실행 후 추가 embedding 0회, 같은 derived root, 실제 stage3 수치 비교를 검증한다.
6. 이 보고서와 증거 로그:
   - `.superpowers/sdd/03-plan/task-T15-report.md`
   - `.superpowers/sdd/03-plan/task-T15-red.log`
   - `.superpowers/sdd/03-plan/task-T15-integration-red.log`
   - `.superpowers/sdd/03-plan/task-T15-green.log`
   - `.superpowers/sdd/03-plan/task-T15-full-tests.log`

## TDD 증거

### RED

프로덕션 수정 전에 버전 테스트를 작성하고 루트에서 실행했다:

```text
backend/.venv/bin/python -m pytest backend/tests/context/test_versions_stage3_5.py -q
15 failed, 1 passed
```

실패는 `/save-session` 덮어쓰기, 네 종류 워커 생성 차단 누락, 배지 누락, stage3/4/5 stale 누락, 수치 비교 누락, SQLite backup API 미사용이었다. paused judge 허용은 기존 코드에서도 통과했다.

통합 fixture의 첫 실행은 crawl shard 이름이 기존 reader 규칙과 맞지 않아 setup에서 실패했다. 이를 `shard-0001.jsonl`로 수정했다. 이 setup 오류를 기능 RED 증거로 취급하지 않았다. 수정된 fixture를 원래 HEAD의 `versions.py`로 재검증한 뒤 구현 파일을 finally에서 복구했다(git show 읽기만 사용):

```text
backend/.venv/bin/python -m pytest backend/tests/test_integration_stage3_5.py -q
2 failed, 1 passed
```

stage4의 started reset, stage3의 prep stale이 실패했다. 기본 end-to-end는 기존 T05~T14 동작을 연결한 회귀 테스트이므로 baseline에서도 통과했다.

### GREEN 및 정리

```text
backend/.venv/bin/python -m pytest backend/tests/context/test_versions_stage3_5.py backend/tests/test_integration_stage3_5.py -q
19 passed, 2 warnings in 4.12s
```

SQLite 복사/재시작 처리를 작은 함수로 분리하고 SQLite 연결을 명시적으로 닫도록 정리했다. 기존 DB schema를 바꾸지 않아 positional final INSERT 계약을 유지한다. 이후 원본 버전과 derived 보고서 검증을 추가했다.

첫 전체 회귀 실행:

```text
backend/.venv/bin/python -m pytest backend/tests -q
1157 passed, 2 warnings in 117.59s
```

최종 전체 회귀 실행 (최종 코드·검증 추가 후, 저장소 루트):

```text
backend/.venv/bin/python -m pytest backend/tests -q
1168 passed, 2 warnings in 119.04s (0:01:59)
```

실패 0건. 첫 실행 이후 병렬 T14 측 테스트가 추가되어 총 개수가 11개 증가했다. T15가 추가한 테스트는 19개이며 최종 전체 실행에도 모두 포함된다. 소유 프로덕션 파일의 `git diff --check`도 통과했다.

## 통합 검증의 구체적인 조건

- 문서 40개, fake embedding 1 batch, embedding 모델 식별/차원은 기존 설정을 따른다.
- fake Jev는 짝수 문서에 Core 합의, 홀수 문서에 등급 불일치를 만들어 실제 검수 큐 20건을 생성한다.
- 사람 답은 Core/Supporting/Non 고정 순환으로 실제 submit API에 제출한다.
- `settings.audit_first=2`, `audit_size=2`, `audit_every=10000`을 monkeypatch하여 감사 1라운드 2건을 제출한다.
- 실제 training worker를 실행하되 `train_ensemble(max_epochs=1)`로 제한한다. 4개 멤버의 학습·저장 및 저장 모델 추론을 실행한다.
- 기본 export의 Core+Supporting과 군집 출력 doc ID 집합이 정확히 일치한다. KMeans에 전달된 matrix가 3단계 VectorStore에서 같은 순서로 읽은 matrix와 정확히 일치한다.
- 군집의 embedding API 호출 수 0, prep fake embedder 호출 수 증가 0을 별도로 검증한다.
- 통합 테스트에서 socket connect/create_connection을 차단한다. Jev는 MockTransport, codex는 기존 offline executable fake이다. detached worker launch만 기록형 fake로 바꾸고 실제 worker 함수를 순서대로 호출한다.
- SQLite 테스트는 WAL 모드 source를 열어둔 상태에서 backup을 관찰한다. snapshot 완료 직후 버전 복사가 반환되기 전에 별도 thread가 `LabelStore.submit`을 커밋한다. 복사본 integrity_check=ok, 복사본 human 행 수=snapshot 행 수=1, source 행 수=2를 확인한다.

## 자체 검토 및 선택 사항

- `final`에는 status 컬럼이 없고 기존 코드가 위치 기반 INSERT를 사용한다. 따라서 schema 확장 대신 `stale_final`/`stale_queue` 보관 테이블을 선택했다. 활성 테이블은 비워 기존 캐시 합치기를 그대로 재사용한다. 원본 버전은 수정하지 않는다.
- 이전 human 응답은 이력으로 유지하며 새 버전 projection에는 자동으로 재적용하지 않는다. 새 버전에서 사람 검수를 다시 한다는 설계 안내에 맞춘 선택이다. 새 감사의 human_floor가 기존 응답을 이번 감사의 정답으로 잘못 채택하지 않게 한다.
- stage3 이전 단계 재시작에도 downstream stale 규칙을 적용한다.
- stage4 수치는 별도 stage4 보고서가 없으므로 stage5 보고서를 사용한다. 아직 export하지 않아 stage5 파일이 없으면 null로 표현한다.
- snapshot은 SQLite DB 단위로 일관성을 보장한다. 외부 공용 judge cache를 복제하거나 collection/vector/model 파일을 중복 생성하지 않는다.
- 변경이 기존 0~2단계 버전·수집 차단·readonly 계약을 깨지 않는지 전체 테스트로 확인한다.
- calibration/α/τ API나 별도 단계를 추가하지 않았다. 기존 모델 내부 temperature 구현 등은 이 작업에서 변경하지 않았다.

## 우려 및 후속 연결

- 백엔드 배지 문구는 `activity.label`, 재시작 안내는 `labeling.restartMessage`로 제공한다. 확인 시점의 `frontend/src/components/SessionList.tsx`는 자체 activityLabel 함수를 사용하며 새 label을 읽지 않았다. 해당 UI 연결은 frontend 소유자(T16)가 처리해야 한다. 이 작업에서는 frontend를 수정하지 않았다.
- 소형 학습 fixture에서도 기존 head 최소 표본 30 규칙을 완화하지 않았다. 표본이 부족한 head의 기존 unavailable/final fallback이 적용될 수 있다. 실제 데이터 품질 평가를 대체하는 테스트는 아니다.
- full suite 경고는 기존 Pydantic class Config deprecated와 joblib의 macOS 물리 코어 수 탐지 fallback이다. 테스트 실패는 아니다.
- 공유 workspace에서 T14 관련 `known/*`, `services/personas.py`, 관련 테스트 및 T16 frontend 변경이 관찰됐다. 이는 이 보고서의 소유 변경 목록에 포함하지 않는다. 최종 전체 실행은 그 시점 공유 트리를 대상으로 한다.
