# 묶음 ③ 최종 수정 재리뷰 2 — `feature/dcx2-stage8` (7ce3215..d7478dd)

- 범위: 수정 2차 커밋 `d7478dd`만 봤습니다. 기준은 `final-rereview1.md`에서 일부 반영 · 반영 안 됨 · 새 결함(N1~N10)으로 남은 항목, `final-fix2-report.md`, 결정 D-312~D-316입니다.
- 실행(읽기 전용): `pytest backend/tests/persona backend/tests/known -q` → **324 passed**. `npm --prefix frontend test` → **58 files / 583 tests passed**.
- 방식: 코드 읽기와 테스트만 했습니다. 소스는 고치지 않았고, 이 파일만 썼습니다.

## 판정: merge 가능 — 새 Critical · Important 없음

| 구분 | 건수 |
|---|---|
| 반영됨 | 16 |
| 일부 반영 | 0 |
| 반영 안 됨 | 0 |
| **새 결함** | Critical 0 · Important 0 · Minor 4 |

D-316 보류 항목(M10, M13)은 이번 범위가 아니고, 그대로 보류입니다.

---

## 항목별 판정

| ID | 판정 | 근거 |
|---|---|---|
| **N1** (Critical) 첫 실행에서 생성 버튼이 없음 | 반영 | `types.ts:241`에 `package: boolean` 추가. `PersonaScreen.tsx:64`은 `status.package === false`이거나 카드 오류 kind가 `evidence_required`일 때만 빈 상태로 판단합니다. `needsEvidence`(`:25`)에서 `not_ready`는 뺐습니다. 문구 매칭(`missingCopy`)도 없앴습니다(`:73`, `:100`). 확인한 흐름: 패키지가 있고 확정값이 일치하면 `stage8.py:141`에서 `evidence_required=false`가 되고, 카드 409 `not_ready`이면 `:127-128` 분기를 건너뜁니다. 그러면 버튼(header, `:136`)이 "페르소나 만들기"로 보이고, `start`(`:129-135`)가 `{}`로 `startPersona`를 부릅니다. 테스트 `PersonaScreen.test.ts:51-58`이 package true/false 두 경우를 확인합니다. |
| **N2** (Important) 공용 `responseError` 우선순위 | 반영 | `errors.ts:30`은 `[code, kind]` 가운데 `messages`에 있는 첫 키를 고릅니다. code가 매핑되어 있으면 7ce3215 이전 동작(code만 봄, `763c83c:errors.ts`)과 같습니다. kind로 넘어가는 경우는 `stale`, `evidence_required`, `persona_required`뿐입니다. 이 세 kind는 페르소나 밖의 백엔드에서 쓰지 않습니다(`backend/app`에서 `routers/stage8.py:80`과 `persona/`에서만 나옴). crawl의 `kind:'conflict'`는 매핑이 없으니 지금도 code 문구가 나옵니다. label · keyword · crawl 클라이언트의 한글 문구는 그대로 유지됩니다. 회귀 테스트는 `errors.test.ts:48-53`입니다. |
| **N3** (Important) `worker.reason`에 예외 클래스 이름이 실림 | 반영 | `stage8.py:267`에서 감독자의 `work.error`를 더 이상 쓰지 않습니다(`reason if same else None`). `:281-282`(failed/interrupted 기본 문구)은 한글이 없는 reason을 failed/interrupted 기본 문구로 바꾸고, `:283-284`은 idle/running/done이면 reason을 지웁니다. 파이프라인 `insight_pipeline.py:129-135`도 `str(exc)` 대신 stale 문구나 `FAILURE_COPY`를 고르고, `:127`은 `LLM_REASON`을 씁니다. 이제 reason을 쓰는 곳은 이 세 곳뿐이고 모두 한글입니다. 그래서 `InsightError` · `_Unavailable` · `StoreError` 같은 클래스 이름이나 영문 `str(exc)`가 화면에 나올 수 없습니다. 테스트는 `test_final_fix2.py:48`입니다(실제 예외 3종으로 확인). |
| **N4** (Important) 컨셉 outdated 범위 | 반영 | `store.py:20-22` `_concept_identity` = `id`, `title`, `pain_point`, `context_ids`. 이것은 `InsightItem` 스키마의 원천 필드(`insights.py:28-35`)에서 `known_ki_id`만 뺀 것입니다. 쓸 때(`store.py:106`)와 읽을 때(`:130`) 모두 이 기준을 씁니다. radar · odi · 백분위 · 기본 대상은 이제 비교하지 않습니다. 테스트 `test_final_fix2.py:14`는 실제 채팅과 재계산 경로에서 I1 컨셉만 outdated가 되는지 확인합니다. |
| **N5** 확정 클릭이 숨은 ID를 지움 | 반영 | `insights.py:156-158`: `hidden = 기존 confirmed_ids − 현재 판`, 저장값은 `hidden + confirmed`. 테스트는 `test_final_fix2.py:24`입니다. |
| **N6** `displayValue` 숫자 규칙 | 반영 | `personaView.ts:53`은 숫자를 항상 `formatMetric`으로 씁니다. 개수 키(`mention_count` · `doc_count` · `author_count` · `idx` · `start` · `end`)만 `formatCount`를 씁니다(`:59`). |
| **N7** 실행 중 채팅 · 되돌리기 대기 | 반영 | `chat.py:34`, `:108`에서 `serialized`를 잡기 전에 `require_persona(assert_writable(...))`로 409를 빨리 돌려줍니다. 잠금 안의 `Source.check()`는 그대로 남아 있습니다. 테스트는 `test_final_fix2.py:36`입니다. |
| **N8** GET `/session` 500 · 비용 | 반영 | `routers/sessions.py:39-40`에서 `PackageMissing`이면 False를 돌려줍니다. 비싼 비교는 `lru_cache(128)`로 캐시하는데, 키는 cards · package · segment.sqlite · wal · journal의 inode · size · mtime_ns · ctime_ns입니다(`:20-44`, `:90-96`). 세션의 `stale` 표시는 캐시 밖(`:76-100`)에서 계속 보므로 캐시가 무효화를 막지 않습니다. 테스트는 `test_final_fix2.py:106`입니다. |
| **N9** fresh 재생성 뒤 옛 실행 상태가 보임 | 반영 | `stage8.py:261`: 감독자 행은 pipeline run과 같거나 running/paused일 때만 반영합니다. `:265`: 같은 run에서 pipeline이 done이면 done을 유지합니다(채팅이 성공한 뒤 배너가 지워짐). 테스트는 `test_final_fix2.py:74`, `:130`입니다. |
| **N10** `Source(...)`를 try 밖에서 만듦 | 반영 | `insight_pipeline.py:101`로 옮겨서 try 안에서 만듭니다. 대기 중에 upstream이 바뀌면 failed가 되고 한글 stale 문구가 실립니다. |
| **C1** 잔여(확정값만 바뀐 경우 · 확인 대화상자) | 반영 | 백엔드 `stage8.py:139-144`가 `evidence_required = not _confirmed_matches(...)`를 내보냅니다. 이 판정은 pipeline이 stale로 끝내는 조건과 같은 함수입니다. 프론트 `PersonaScreen.tsx:128`은 "근거 탐색을 다시 실행한 뒤 페르소나를 만드세요." 화면을 보여 주고 재생성 버튼은 보이지 않게 합니다. stale이면 버튼 문구가 "페르소나 다시 만들기"이고, `confirm('…인사이트와 컨셉도 지워집니다…')`를 거친 뒤에만 `{fresh:true}`를 보냅니다(`:132-134`). 테스트는 `PersonaScreen.test.ts:44,59,66`과 `test_final_fix2.py:93`입니다. |
| **I1** 잔여(패키지 플래그 미사용) | 반영 | N1과 같습니다. 이제 `status.package`가 판단 기준입니다(`PersonaScreen.tsx:64,127`). |
| **M6** 맵이 backend legend · 순서를 무시 | 반영 | 클러스터와 Persona를 자연 정렬합니다(`OpportunityMap.tsx:30,32`, `CL2` < `CL10`). shape · tone · persona_name · cluster_label은 backend `legend`에서 가져옵니다(`:31,43-47,57`). backend `opportunity.py:12-13,63-75`의 SHAPES · TONES 값('--ink' 같은 CSS 변수 이름)과 프론트 `var(${tone})`가 맞습니다. `types.ts:273-274`에서 legend 타입도 구체화했습니다. |
| **M7** 범례 칩이 필터가 아님 | 반영 | `hiddenPersonas`로 점을 걸러 냅니다(`OpportunityMap.tsx:42`). `aria-pressed`는 "보임"을 뜻합니다(`:57`). Context 표는 걸러 내지 않습니다. 테스트는 `PersonaScreen.test.ts:103`입니다. |
| **M8** 헤더 신뢰도 · 처방 요약 | 반영 | `PersonaScreen.tsx:120-124` 및 카드 헤더. 신뢰도는 `grade.py:64-82`의 `traceable_support` 평균으로 상(≥0.7) · 중(≥0.4) · 하로 나눕니다. 처방 · 제약은 ✓/⚠/✕로 요약합니다. 이 규칙은 fix 보고서 "Display rules"에 적혀 있습니다. |
| **M14** tablist 화살표 키 | 반영 | `PersonaScreen.tsx:151-157`: ←/→ 순환, Home/End, roving `tabIndex`, 포커스 이동. 테스트는 `PersonaScreen.test.ts:83`입니다. |

## 중점 확인 결과

- **공용 `errors.ts`**: 위 N2 행과 같습니다. crawl · label · keyword · prep 클라이언트는 `code`가 매핑되어 있으면 7ce3215 이전과 같은 문구를 받습니다. code가 매핑되어 있지 않고 kind만 새 3종에 해당하는 응답은 persona 밖에서 나오지 않습니다. 회귀 없습니다.
- **첫 실행 흐름**: package가 true이고, status가 none이고, 카드가 `not_ready`이고, `evidence_required`가 false이면 "페르소나 만들기"가 활성으로 보입니다(`blocked`는 readonly · busy · pending · running일 때만 true). 누르면 `startPersona(sid, {}, version)`을 보냅니다. 백엔드 `start_persona`(`stage8.py:107-117`)는 `_package`만 확인하므로 통과합니다. 동작합니다.
- **worker.reason**: 위 N3 행과 같습니다. 클래스 이름이 화면에 갈 수 있는 경로는 남아 있지 않습니다.
- **컨셉 outdated 범위**: 위 N4 행과 같습니다. 원천 필드만 비교합니다.

## 새 결함 (Minor만, merge를 막지 않음)

- **m1 실행이 `running`을 기록하기 전에 실패하면 화면에 실패가 보이지 않음.** 위치는 `insight_pipeline.py:65-81`과 `stage8.py:261`입니다. `assert_writable`, mode 검증, target 검증은 `publish_status('running')`보다 먼저 일어나고 try 밖에 있습니다. 여기서 예외가 나면 감독자 행만 failed가 되고 pipeline의 `run`은 예전 값으로 남습니다. 그런데 N9 필터는 run이 다른 terminal 행을 무시하므로, 화면에는 직전 상태(idle/done)가 그대로 보이고 폴링이 멈춥니다. 시작 API(`stage8.py:201-208`)가 같은 조건을 미리 검사하므로, 이 일은 시작과 실행 사이에 경합이 있을 때만 생깁니다(버전 전환, 인사이트 교체).
- **m2 `GET /persona/status`가 매 폴링마다 segment.sqlite를 읽음.** 위치는 `stage8.py:141`입니다. sqlite 오류가 나면(테이블 없음, 열기 실패) `PackageMissing`만 잡으므로 상태 API가 500이 됩니다. 이전에는 이 API에서 sqlite를 읽지 않았습니다. 정상적인 세션에서는 일어나지 않습니다.
- **m3 읽기 전용 버전에서도 `evidence_required` 화면이 "근거 탐색으로" 버튼을 보여 줌.** 위치는 `PersonaScreen.tsx:128`입니다. 이 버튼은 활성 버전의 근거 탐색 화면으로 이동합니다. 과거 버전은 package와 segment가 함께 고정되어 있으므로 실제로 이 화면이 뜰 일은 드뭅니다.
- **m4 `known_ki_id`만 바뀐 경우 컨셉이 무효화되지 않음.** 위치는 `store.py:21`입니다. 컨셉 프롬프트에는 insight 행 전체가 들어가지만(`concepts.py:171`), Known 연결만 바뀌었을 때는 컨셉 결과를 다시 만들지 않습니다. 이는 리뷰 1의 권고(계산 · 배지 필드 제외)와 맞는 의도적 범위로 보입니다. 결정 로그에 한 줄 남기기를 권장합니다.

## 합계

- 재확인 대상 16건(C1, I1, M6, M7, M8, M14, N1~N10): **반영 16 · 일부 0 · 반영 안 됨 0**
- 새 Critical/Important: **없음**. Minor 4건(m1~m4)은 후속 작업으로 처리해도 됩니다.
