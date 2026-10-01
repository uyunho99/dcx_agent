# T05 — 3단계 API · 워커 연결

## 구현

- `PUT /prep/{sid}/config`: T04 `PrepConfig`의 기본값/검증을 재사용한다. 알 수 없는 입력, 음수 최소 길이, 서버 임베딩 모델·차원과 다른 설정을 거절한다. 설정 저장 시 이전 결과 연결과 실행 ID를 비우고 `prep.status=none`으로 저장한다. 진행 중/일시 정지 작업의 설정 변경은 409이다.
- `POST /prep/{sid}/run`: 활성 쓰기 가능 버전을 검증하고, 설정과 수집본으로 T04의 동일한 `prep_key`를 계산한다. 이미 실행 중인 작업은 기존 상태를 반환한다. 완료 manifest, stage_3 결과, 호환 출력이 모두 있는 캐시는 새 워커 없이 `done`, `reused=true`, `stage3`를 반환한다. 새 버전에서도 동일 캐시를 재사용한다. 새 실행은 `runner.start(sid, version, 'prep', {'config': ...})`를 사용한다.
- `GET /prep/{sid}/status`: prep 실행 ID에 해당하는 워커의 진행률/상세/오류와 `stage_3.json`을 `stage3`로 반환한다. 활성 세션의 실패·중단 상태를 세션에 반영한다. 선택 버전 열람도 지원하며 다른 활성 버전에는 상태를 쓰지 않는다.
- `KINDS['prep']`를 지연 import하는 진입점으로 등록하고 FastAPI에 라우터를 포함했다. 실제 detached subprocess로 T04 `run_prep`를 실행한다.
- Voyage 미연결은 워커 진입점에서 `VoyageEmbedder()`가 내는 `EmbedderUnconnected`를 T01 실행기에 전달한다. 따라서 runs.sqlite는 `failed`와 예외 종류만 저장하며 API는 `kind=embedder_unconnected`와 정확한 문구를 반환한다: **임베딩 API가 연결되지 않았습니다. 연결하거나 내부용 설정에서 가짜 임베더로 바꾸세요.** 원래 예외 메시지나 키는 반환하지 않는다. fake는 연결 검사를 통과한다.
- 구버전 세션은 세 경로 모두 409 및 `{status: 'error', error: {kind: 'legacy_session', message: ...}}`로 거절한다. 기존 `ContextRoute`로 요청 검증/저장소 오류 envelope를 재사용한다.

## 세션 쓰기 및 리팩터링

세션 검사와 쓰기를 `store.locked(sid)`로 직렬화하며 `_session`, `_root`, `_save`, `_view`로 공통 처리를 모았다. 상태 부분 갱신은 `update_session`의 lock-held 구현인 `_update_locked`를 사용한다. 설정을 포함하는 저장은 같은 잠금 안에서 최신 세션의 `prep`만 교체하고 `store.write_json`으로 한 번 원자적으로 쓴다. 이는 `update_session`의 재귀 병합이 PUT에서 삭제한 `boilerplate` 키를 되살리는 것을 방지하기 위한 처리다. `drafts`, Known Insight 등 다른 세션 필드는 보존된다. `savedAt` 및 `updatedAt`도 기록한다.

**pipeline.py 수정 없음.** T04의 직접 호출에 대한 기존 오프라인 동작은 변경하지 않고, T05 worker 진입점에서 미연결을 먼저 거절하여 잘못된 완료/0벡터 생성을 막았다.

## 생성/수정 파일

생성:
- `backend/app/routers/prep.py`
- `backend/tests/prep/test_prep_api.py`
- `.superpowers/sdd/03-plan/task-T05-report.md`

수정:
- `backend/app/main.py` — prep import 및 router include만 추가.
- `backend/app/work/worker.py` — prep 지연 진입점 및 KINDS 등록만 추가.

## TDD 증거

### RED — 구현 전

명령:
```text
cd backend && .venv/bin/python -m pytest tests/prep/test_prep_api.py -q
```

결과:
```text
FFFFFFFF                                                                 [100%]
8 failed, 1 warning in 1.20s
```

필수 네 테스트 이름을 먼저 작성했다:
- `test_run_then_status_done`
- `test_reuse_returns_done_immediately`
- `test_embed_unconnected_stops_with_reason`
- `test_legacy_session_rejected` (PUT/POST/GET 세 경우)

추가로 설정 검증·오래된 버전 거절 및 정형 문구 삭제 보존을 검증했다. 모든 RED는 아직 등록되지 않은 `/prep` 경로가 404 `{"detail":"Not Found"}`를 반환하기 때문이었다. import 오류나 외부 연결 오류가 아니었다.

### 구현 중 검증

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
2 failed, 23 passed, 1 warning in 10.17s
```

새 버전 재사용 fixture의 crawl queue에 완료된 detail run이 없어 기존 버전 생성 guard가 거절했다. fixture에 실제 로컬 완료 queue를 추가했다. 또한 쓰기 요청에서 존재하지 않는 version 파일을 먼저 읽어 404가 나던 순서를 활성 버전 쓰기 검증 우선으로 고쳐 409를 반환하게 했다.

### GREEN — 집중 테스트

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
.........................                                                [100%]
25 passed, 1 warning in 10.32s
```

T04 기존 테스트 17개와 T05 API 테스트 8개가 통과했다. API 성공·미연결 테스트는 실제 detached Python worker와 runs.sqlite를 사용한다. 자식 프로세스는 로컬 저장소·고정 fake 설정 또는 빈 Voyage 키를 환경변수로 받으며 네트워크 호출이 필요하지 않다. 성공 결과의 `stage3.embedded`, `derivedRef`, 세션 보존을 확인했다. 미연결은 API/워커 모두 failed이고 벡터 파일이 없음을 확인했다. 재사용 테스트는 새 버전을 만든 뒤 `runner.start` 호출 자체를 금지하여 동기 재사용을 검증했다.

### 전체 스위트 (한 번 실행)

```text
cd backend && .venv/bin/python -m pytest -q
962 passed, 2 warnings in 107.75s (0:01:47)
```

전체 스위트를 한 번 실행했고 실패 없이 종료했다. 경고는 기존 Settings의 Pydantic class Config deprecation과 joblib의 물리 코어 수 감지 실패에 따른 논리 코어 fallback이었다. 테스트 완료 이후 구현 코드는 변경하지 않았다.

## 자체 검토

- 현재 브랜치 `feature/dcx2-stage3-5` 확인. 시작 시 git 작업 트리는 깨끗했다.
- 소유 파일과 요청된 보고서만 변경했다. pipeline 및 다른 구현 파일은 변경하지 않았다.
- `git diff --check` 통과.
- 결과 캐시 키는 별도 구현하지 않고 T04 함수를 사용한다. provider 생성 없이 캐시 키를 계산하므로 완료 결과 재사용에 API 호출이 없다.
- 세션 잠금 안에서 최신 상태를 검사하여 설정/실행 요청이 서로 엇갈리는 것을 막는다. 워커는 버전과 설정 snapshot을 전달받는다.
- 오류 응답에는 고정 안내문과 예외 클래스 기반 분류만 사용한다.
- git 쓰기 명령과 커밋을 실행하지 않았다.

## 우려/경계

- T04 `run_prep`를 T05 워커 밖에서 직접 부르면 기존의 미연결→0벡터 완료 동작이 유지된다. 새 API 및 등록된 prep worker는 사전 연결 검사를 반드시 거친다.
- 미연결은 pipeline의 토큰/벡터 처리에 들어가기 전에 실패한다. 따라서 미연결 실행에서는 중간 정제본도 새로 만들지 않는다.
- 실패·중단에 대한 session `prep.status` 동기화는 상태 조회 시 수행하며, 워커의 확정 상태는 runs.sqlite에 즉시 기록된다.
- 설정 교체는 위에 설명한 잠금 내 원자 저장을 사용한다(`update_session`의 재귀 병합만으로 삭제 의미를 표현할 수 없음).
