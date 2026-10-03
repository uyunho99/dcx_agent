# Jev 미연결 시 GPT 단독 라벨링 — 설계

기준: 01-brainstorm.md(승인), D-340 · D-341.

## 1. 판정 방식 결정과 저장
- `app/label/jev.py`에 `jev_available() -> bool` 추가.
  - `jev_backend == 'http'` 이고 `jev_api_keys`가 비어 있지 않으면 True.
  - `jev_backend == 'fake'` 이면 `settings.label_fake_jev_cross`(새 설정, 기본 False, 환경변수 `LABEL_FAKE_JEV_CROSS`)일 때만 True. 테스트 · 오프라인 QA에서 교차 흐름을 돌릴 때만 켠다.
- 라벨링 시작(`POST /{sid}/start`, LLM 방식) 때 방식을 정해 세션에 저장한다: `labeling.labelerMode = 'cross' | 'gpt_only'`.
  - 시작 후에는 설정이 바뀌어도 그 버전의 방식은 그대로다(진행 중에 규칙이 바뀌지 않게).
  - 저장값이 없는 옛 세션은 `'cross'`로 읽는다(기존 동작 유지).
- 방식 조회 헬퍼 `labeler_mode(data)`: 저장값 → 없으면 시작 전 미리보기는 `jev_available()`로 계산.

## 2. 시작 · 제어 API (`routers/labeling_v2.py`)
- `start`: `gpt_only`면 `gpt` 실행만 만든다. `judgeRuns`에 `jev` 없음. 응답 `workers`에 `gpt`만.
- `control(labeler='jev', ...)`: 세션이 `gpt_only`면 409 `"Jev가 연결되지 않아 GPT 단독으로 판정합니다."`.
- 판정 워커(`judge.run_worker`): 방어용으로 `labeler == 'jev'`인데 세션이 `gpt_only`면 즉시 실패(사유 같은 문구).
- Jev 키가 나중에 생겼을 때: 같은 버전은 `gpt_only` 유지. **새 버전에서 라벨링을 시작하면 교차 방식**이 된다. GPT 판정 캐시는 버전 간 공유라 GPT 비용 없이 Jev만 돈다. 새 버전에 복사된 `gpt_only` 행은 교차 합의로 대체된다(3절).

## 3. 최종 라벨 합치기 (`label/route.py`)
- `rebuild_final(store, jev_cache, gpt_cache, mode)`:
  - `gpt_only`: GPT 캐시의 변경 기록만 읽는다(커서 이름 `gpt`, 기존 방식 그대로). 대상 = GPT 표 `done` · 최종 행 없음. 행 값:
    - tags = GPT `anchor` · `sem` · `situation`, `reason_code` · `signal` = GPT 값
    - `level = rule.grade(gpt_tags)`, `confidence = NULL`, `source = 'gpt_only'`, `route = 'accepted'`, `grade_mismatch = 0`, `disagree = []`
    - `votes_json = {"jev": null, "gpt": <GPT 표>}`
  - `cross`: 기존 동작 + 기존 행이 `source='gpt_only'`인 글도 대상에 넣어 교차 합의 행으로 바꾼다(`INSERT OR REPLACE`; `human` · `model` 행은 건드리지 않음).
  - 규칙 · 질문 버전 변경 시 비우기는 기존 조건(`source NOT IN ('human','model')`)이 `gpt_only`도 포함한다.
- `sync` · `rebuild_queue`는 세션 방식을 받아 넘긴다. 큐: `gpt_only`에서는 `grade_mismatch`가 생기지 않고, `labeler_failed`는 GPT 캐시만 본다.
- 4단계 완료(`context/stale._judges_complete`): 그 버전 세션의 `labelerMode`가 `gpt_only`면 최신 `gpt` 실행 done만 확인. 세션 방식은 `_judges_complete` 호출부(`judge_done`, `reconcile_judge_done`)에서 session.json을 읽어 넘긴다.

## 4. 저장 구조 (`label/store.py`, `label/schema.py`)
- `final.confidence`를 `REAL` (NULL 허용)으로. 기존 DB는 1회 이전: 새 테이블 생성 → 행 복사 → 교체 → `final`에 걸린 인덱스 · 트리거(`event_merged`, `event_accepted` 등) 다시 생성. 이전 여부는 `PRAGMA table_info(final)`의 `notnull`로 판단(멱등). 한 트랜잭션.
- Pydantic: `confidence: Probability | None`, `source: Literal['agreed','human','model','gpt_only']`.

## 5. 5단계 · 내보내기
- 학습 대상(`model/dataset.TRAINING_WHERE`, `train.build_targets`): `source IN ('agreed','gpt_only') AND route='accepted'` 또는 `human`.
- 소프트 라벨: `votes.jev`가 null이면 이진 칸은 GPT 0/1 그대로, 사유 헤드는 GPT 원-핫만(Jev 사유 확률 섞지 않음).
- `export._label_entropy`: `gpt_only`는 0(불확실성 정보 없음). 내보내기 `confidence`는 null 그대로.
- `report` · `overview` · `audit` · `known/filter`: `confidence`/`source` 사용처 전수 확인, null 안전.

## 6. 개요 API (`label/overview.py`)
- 응답에 `labelerMode: 'cross' | 'gpt_only'` 추가.
- `gpt_only`면 `progress`에 `jev` 키 없음, `mismatchRate = null`, `labelerAccuracy.jev = null`.

## 7. 화면 (`components/label/*`, `lib/api/label.ts`)
- 상태
  - 시작 전 · `gpt_only`: 전량 판정 카드 위에 안내 상자 — 제목 "Jev 미연결 · GPT 단독 판정", 본문 "등급 불일치 검수 없이 GPT 판정을 그대로 채택합니다. 오류는 무작위 감사로 확인합니다. Jev를 연결한 뒤 새 버전에서 시작하면 교차 판정합니다."
  - 진행 중 · 완료: 같은 안내 유지. 전량 판정 카드는 GPT 하나만(그리드 1열), Jev 비용 문구 없음.
  - 교차 방식: 지금 화면 그대로.
- 숫자: 불일치율 · Jev 정확도 · 검수 카드의 "Jev 확률" 열은 `gpt_only`에서 "—". confidence 표시처는 null이면 "—".
- 검수 카드 비교표: Jev 열은 값이 없으면 "—".
- 반응형: 안내 상자는 기존 `ds` 안내 컴포넌트(Callout/Notice가 있으면 그것, 없으면 Card + `ds-t-caption`)로 폭 100%. 모바일에서도 1열이라 변화 없음.
- 접근성: 안내 상자 `role="status"`, 제목은 텍스트로(색만으로 구분하지 않음).

## 8. 실패 상태
| 상황 | 동작 |
|---|---|
| `gpt_only`에서 Jev 제어 요청 | 409 + 안내 문구 |
| GPT 판정 실패 문서 | 기존대로 `labeler_failed` 큐 |
| Codex 사용 한도 | 기존 GPT 일시정지 흐름 그대로 |
| 이전 중 오류 | 트랜잭션 롤백, 기존 테이블 유지, 다음 열기에서 재시도 |

## 9. 디자인 리뷰 (plan-design-review 기준 자체 점검)
- 정보 위계: 방식 안내를 진행 카드 **위**에 둬서 "왜 Jev 카드가 없는지"를 먼저 읽게 한다. — 반영
- 빈 상태 · 오류 상태 · 완료 상태: 세 상태 모두 같은 안내 유지(위 7절). — 반영
- 용어: "교차 판정", "단독 판정"만 쓰고 `gpt_only` 같은 코드값은 화면에 노출하지 않는다. — 반영
- 새 화면 · 새 레이아웃 없음, 기존 카드 재사용 → 목업 생략.
