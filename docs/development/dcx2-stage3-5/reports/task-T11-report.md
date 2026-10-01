# T11 — 라우팅 · 큐 · 라벨 API 구현 보고서

## 상태와 범위

- 구현 완료. 브랜치: `feature/dcx2-stage3-5`.
- 컨트롤러의 D-136/139/143/144/145 및 T09/T10 이월 지시를 적용했다.
- 네트워크, git 쓰기 명령, 커밋, 하위 에이전트를 사용하지 않았다.
- `backend/app/routers/labeling.py`와 기존 `/sample`은 수정하지 않았다.
- T12 소유 `backend/app/model/*`, `backend/tests/model/*`은 수정하지 않았다.
- 기존 작업 트리에 있던 `docs/development/dcx2-stage3-5/decision-log.md` 변경은 건드리지 않았다.

## 정확한 변경 파일

1. `backend/app/label/route.py` — 신규: 라우팅, 큐 재구축, blind next, 원자적 건별 제출.
2. `backend/app/label/overview.py` — 신규: 버전별 개요, 원문 인덱스, 감사·진행·ETA·변화 집계.
3. `backend/app/label/report.py` — 신규: `label_part(sid, version=None)` 라벨 보고서 반환.
4. `backend/app/routers/labeling_v2.py` — 신규: `/label` API 및 오류 envelope.
5. `backend/app/main.py` — 신규 라우터 import/include 두 줄만 추가.
6. `backend/tests/label/test_route.py` — 신규: 라우팅 및 실패 큐 회복 테스트.
7. `backend/tests/label/test_label_api.py` — 신규: API·성능·감사·내구성·보고서 회귀 테스트.
8. `.superpowers/sdd/03-plan/task-T11-report.md` — 이 보고서.
9. `.superpowers/sdd/03-plan/t11-evidence/` — RED/GREEN 및 전체 테스트 출력 증거.

## 구현

### 큐와 건별 검수

- `route(label)` 사유는 `labeler_failed` → `grade_mismatch` → `accepted`뿐이다. confidence는 사유를 만들지 않는다.
- `rebuild_queue(store, jev_cache=None, gpt_cache=None)`는 T09 `rebuild_final`과 연결한다. 어느 캐시든 terminal `bad`인 문서는 다른 라벨러 완료를 기다리지 않고 실패 큐에 들어간다.
- 실패 후 두 표가 합쳐져 채택된 문서의 open 행은 닫힌다. 등급 불일치로 회복된 경우에는 사유와 confidence 순서를 갱신한다. 이미 처리한 행을 다시 열지 않는다.
- `/next`는 `queue_next(status, priority, doc_id)` 인덱스와 `LIMIT 1`을 사용한다. 합치기, 원문 파일 스캔, 전체 큐 materialization은 이 경로에서 하지 않는다.
- 원문은 start/overview 시 파일별 변경 시각·크기로 갱신하는 SQLite 인덱스에 저장한다. next는 문서 기본키로 원문 한 건을 조회한다. 원문 body/댓글을 포함하며 AI 필드는 whitelist로 제외한다.
- 제출은 human 추가, final 갱신, 큐 종료, 라운드 처리 기록을 한 SQLite 트랜잭션에서 커밋한다. 저장 실패 시 모두 롤백한다. 계산 등급과 Jev/GPT 비교는 커밋 후에만 응답한다.
- 실패 문서에 한 라벨러의 성공 표만 남아 있어도 해당 표를 캐시에서 보존하여 제출 후 비교에 포함한다.

### 감사와 라운드 연결

- T10 `maybe_new_round`, `kappa_ai`, `labeler_accuracy`, `self_consistency`, `definition_signal`을 재사용한다.
- audit/reissue next는 `round`를 포함한다. submit은 round 필수·샘플 소속·최신 샘플·중복 완료를 검증한다.
- T10 human 테이블에 round 컬럼은 없다. 기존 `audit_snapshot.human_floor` 워터마크 방식을 유지하고, 진행 중 라운드 완료 전에 다음 라운드를 만들지 않는다. 별도 `review_done(mode, round, doc_id)`는 API의 재발행 완료와 소요 시간만 기록한다.
- audit submit은 커밋 후 `apply_audit_overrides`를 호출하여 다른 사람 값을 `source=human`으로 반영한다. T10은 재개 시에도 durable human 행에서 보정을 복구한다.
- 자동 라운드는 설정의 첫 1,000건·이후 10,000건 기준을 사용한다. 수동 생성은 채택 표본 수가 `audit_size` 이상이면 T10 샘플러의 스케줄 문턱만 우회한다.

### API·개요·보고서

- 구현 API: mode, start, judge, judge/{jev|gpt}/{pause|resume}, overview, next, submit, rule/preview, audit.
- start는 정확히 `runner.start(sid, version, 'judge', {'labeler': 'jev'})`와 GPT 대응 호출을 한다. 각 성공한 run ID를 저장하여 부분 시작과 재시도에도 대응한다.
- 시작 후 mode는 정확히 409 `새 버전에서 방식을 바꾸세요`를 반환한다. alpha/calibration endpoint는 없다.
- 변경은 `store.locked` + `assert_writable` + `_update_locked`를 사용하며 전체 세션 저장 API를 호출하지 않는다.
- 과거 버전 overview는 최신 판정 캐시를 다시 합치지 않고 `lastSeenAt`도 바꾸지 않는다. legacy는 기존 label 0/1을 anchor로 읽고 새 작업은 차단한다.
- 개요: queue/merged 불일치율, 등급 분포, 사유별 큐, 큐 예상 시간(평균 제출 시간, 초기 10초), 라벨러별 캐시 진척·T08 estimate, 감사 κ, 표본 n을 포함한 라벨러 정확도, 자기 일관성, 정의 점검 신호를 제공한다.
- now 카드: before-start와 우선순위 1..6(멈춤 → 정의 점검 → 큐 → 감사 → 진행 → 완료)을 구현했다.
- 변화 집계: 캐시의 판정 시각과 버전 SQLite의 최초 합치기·채택·큐 이벤트를 `labeling.lastSeenAt`과 비교한다. 현재 버전 overview 조회 후 lastSeenAt와 감사 요약 키를 갱신한다.
- label_part는 라벨 부분만 반환하며 `stage_5.json`을 쓰지 않는다. 분포 비율, 실제 Jev/GPT 쌍의 필드별 κ와 등급 합의율을 계산한다. 사람 정답 대비 정확도를 라벨러끼리의 κ로 혼동하지 않는다.

## TDD 증거

1. 구현 파일을 만들기 전에 필수 테스트 이름을 포함한 12개 테스트를 작성했다. 실행 결과 **12 failed**: module 미존재와 API 404를 확인했다. `t11-evidence/red.txt`.
2. 최소 구현 후 같은 테스트 **12 passed**.
3. 추가 회귀 테스트에서 원문 body/댓글 누락, 과거 버전 재합치기를 RED로 확인했다. `refactor-red.txt`: **2 failed, 22 passed** (동일 의도적 pytest 실패가 TestClient 종료에도 전달되어 teardown error 1개 포함). 수정 후 **24 passed**.
4. 저장 장애 envelope/롤백 및 보고서 pairwise κ 테스트를 먼저 실패시켰다. `storage-report-red.txt`: **2 failed, 21 passed**. 수정 후 route/API **26 passed**.
5. 한 라벨러만 성공한 실패 문서의 제출 후 비교 테스트를 추가해 RED를 확인했다. `partial-vote-red.txt`: **1 failed**. 수정 후 최종 라벨 전체 검증에 포함했다.
6. 필수 `test_queue_large_next_is_constant_time`: 실제 FastAPI GET 요청으로 **40,000 queue 행에서 50ms 미만**을 검증한다. `test_failed_doc_reaches_queue`: Jev 3회 실패 → 실패 큐 → 사람 제출 → durable final → 재구축 후 재개방 없음.
7. 새 테스트는 subprocess를 직접 생성하지 않는다. 워커 시작은 mock으로 정확한 인자를 검증한다. T01 실제 runner의 subprocess cwd 설정은 기존 구현을 그대로 사용한다.

## 테스트 결과

- 초기 전체 라벨: `backend/.venv/bin/python -m pytest backend/tests/label -q` → **170 passed**, 3.19s.
- 초기 전체 백엔드: backend cwd에서 `.venv/bin/python -m pytest -q --ignore=tests/model` → **1047 passed**, 110.15s.
- 최종 루트 실행: `backend/.venv/bin/python -m pytest backend/tests/label -q` → **185 passed**, 3.37s (`label-final.txt`).
- 최종 전체 백엔드: backend cwd에서 `.venv/bin/python -m pytest -q --ignore=tests/model` → **1062 passed**, 110.36s (`backend-final.txt`).
- `git diff --check` 통과. main의 diff는 router import/include 두 줄뿐이다.
- 기존 경고: Pydantic class Config deprecation, 전체 테스트의 joblib 물리 코어 탐지 fallback.

## 자체 검토와 통합 참고

- 큐 조회 성능 경로와 재합치기/통계 경로를 분리했다. 운영 UI는 overview를 polling하여 진행 중 판정 캐시를 final/queue에 반영한다. 독립적인 `/next` 호출은 큐를 재구축하지 않는다.
- overview의 전체 통계·최초 원문 인덱싱은 문서 수에 비례한다. 이번 50ms 요구는 `/next`에 적용된다. 실제 대규모 overview 비용은 향후 집계 캐시 최적화 대상이다.
- 최초 이벤트 테이블 설치 이전 데이터는 최초 개요 생성 시점으로 backfill한다. 이후 신규 이벤트와 lastSeenAt 비교는 실제 저장 시각을 사용한다.
- GPT의 recent 처리 속도 또는 Jev 키가 없어 ETA를 추정할 수 없으면 T08 계약대로 seconds=null이며 수치를 지어내지 않는다.
- model 방식/modelId 선택값은 보존하지만 start는 컨트롤러 지시대로 두 judge를 시작한다. 분류 모델 추론·모델 저장소 기능은 T12 소유이며 이 구현에서 손대지 않았다.
- T10 감사 보정은 durable 제출 직후 별도 트랜잭션으로 실행된다. 그 사이 프로세스가 중단되어도 사람 판정은 남고 다음 T10 통계/보정 호출에서 복구된다.
- SQLite 오류 응답에는 내부 SQL/원문/키를 노출하지 않는다. HTTP 계층의 검수 mode와 round 검증, 버전 쓰기 가드를 확인했다.

## Fix round 1

### 변경 내용

- `backend/app/label/judge.py`: 워커 시작/재개 시와 각 커밋된 판정 배치 뒤에 해당 버전의 final·queue·감사를 동기화한다. GPT 오류로 실패 횟수를 저장하고 일시 정지하는 경로도 동기화한다. overview 폴링 없이 성공 쌍과 terminal bad 문서가 검수에 반영된다.
- `backend/app/label/route.py`: 공유 votes.sqlite에 최초 terminal 행을 한 번 bootstrap하는 변경 journal/trigger를 추가하고, 버전별 labels.sqlite에 처리 cursor를 저장한다. 증분 `rebuild_final`은 journal의 신규 doc_id만 대상으로 두 표를 기본키 조회하며, 결과와 cursor를 같은 트랜잭션에서 커밋한다. 먼저 도착한 한 표, 이후 도착한 상대 표, 재시작, 새 버전의 공유 캐시 사용을 지원한다. 규칙/질문 버전 변경은 자동 결과를 다시 합치되 human/model 결과를 보존한다. 최초 도입 시 기존 final의 규칙 버전도 검사한다.
- 이벤트 schema/backfill은 영속 migration guard로 한 번만 실행한다. 같은 reason/priority를 가진 open queue 행은 upsert에서 UPDATE하지 않는다. T13 `refresh_predictions` 모델 모드 분기는 유지했다.
- `backend/app/label/overview.py`, `backend/app/routers/labeling_v2.py`: overview 및 next가 session lock을 잡지 않는다. SQLite 쓰기는 기존 `LabelStore._db()`의 `BEGIN IMMEDIATE`로 보호된다. overview는 lastSeenAt와 세션 통계를 저장하지 않는다. 화면 최초 overview를 읽은 뒤 UI가 한 번 호출할 `POST /label/{sid}/seen`을 추가했으며, 현재 writable 버전에서만 lastSeenAt를 갱신한다. 변경 집계는 저장된 시각을 기준으로 하므로 polling에 의해 사라지지 않는다. 프론트엔드 파일은 이번 소유 범위 밖이므로 수정하지 않았다.
- ETA는 worker detail의 estimate를 우선 사용한다. 없을 때만 documents payload를 읽으며, 버전 DB 경로·labeler·counts·정의·원문 파일 stamp별로 최대 128개 추정을 캐시한다.
- 현재 버전 `GET /next`에서 항목을 찾지 못하면 증분 동기화 후 다시 조회한다. 과거 버전은 캐시를 합치지 않는다. `after=<priority>:<doc_id>`와 응답 item의 `cursor`를 추가했다. 기존 queue_next 인덱스의 `(priority, doc_id) > (?, ?)` keyset 조건으로 다음 항목을 찾고 끝에서는 item=null을 반환한다. 잘못된 cursor와 NaN/무한대는 422이다. 처음부터 다시 탐색하려면 after를 생략한다.
- T13 model start/compatibility 검사, 모델 progress/now 카드, 모델 결과 재계산 훅은 유지했다. T14 소유 파일, 네트워크, git 쓰기 명령, 커밋, 하위 에이전트는 사용하지 않았다.

### TDD 및 검증

- 최초 신규 회귀 테스트 RED: `backend/.venv/bin/python -m pytest backend/tests/label/test_label_api.py backend/tests/label/test_judge.py -q` → **5 failed, 44 passed**, 2.82s. 방문 시각/ETA 반복 계산, 빈 큐 freshness, skip, 세션 잠금, 워커 final 반영의 실패를 확인했다.
- 추가 회귀 RED: `backend/.venv/bin/python -m pytest backend/tests/label/test_route.py backend/tests/label/test_judge.py -q` → **1 failed, 27 passed**, 1.84s. 기존 final의 첫 증분 동기화 시 규칙 버전 무효화 누락을 확인하고 수정했다.
- 신규 테스트는 배치별 final 반영, 자동 감사 생성, terminal bad 큐 반영, 두 표의 시간차 도착, 변경 없는 재실행, 새 버전 cursor, human 보존, 규칙 변경, 한 번만 수행하는 backfill, 불필요한 queue UPDATE 금지, 방문 시각 보존과 seen 쓰기 가드, ETA 캐시, skip/끝/잘못된 cursor를 검증한다.
- 성능 검증: 기존 실제 GET `/next`의 **40,000행·50ms 미만** 테스트 통과. 추가 40,000행 테스트는 session lock 진입을 실패 처리하여 `/next`와 overview/sync 양쪽이 session lock을 사용하지 않음을 검증한다. 이는 요청에서 허용한 잠금 미사용 검증이며, 동시 SQLite writer 아래 50ms를 보장하는 측정은 아니다.
- 최종 라벨 명령(저장소 루트): `backend/.venv/bin/python -m pytest backend/tests/label -q` → **194 passed**, 5.04s. 기존 Pydantic Config deprecation 경고 1개.
- 최종 전체 백엔드 명령: `cd backend && .venv/bin/python -m pytest -q --ignore=tests/known` → **1109 passed, 2 warnings**, 115.41s (0:01:55). T13 모델 회귀 테스트 포함. 기존 Pydantic deprecation 및 joblib 물리 코어 감지 fallback 경고만 발생했다.
- `git diff --check` 통과. 이번 변경 파일은 위 앱 4개, `backend/tests/label/{test_route,test_label_api,test_judge}.py` 3개, 본 보고서 1개이다. 전체 테스트 로그는 `/tmp/t11-fix-backend-final.txt`, 라벨 로그는 `/tmp/t11-fix-label-final.txt`, RED 로그는 `/tmp/t11-fix-red.txt`와 `/tmp/t11-fix-extra-red.txt`에 있다.
