# QA_PLAN — dcx-step07-11

독립 브라우저 QA용. 구현 세션이 아닌 **별도 Codex 세션**이 실행한다. 소스·Git은 읽기 전용이고, 이 계획의 QA ID별 근거(화면·로그·expected/actual)만 기록한다.

`[data]` 표시는 브라우저만으로 확인할 수 없는 단언이다. **화면 동작을 먼저 수행한 뒤** 승인된 읽기 도구로 아티팩트를 열어 근거를 보강한다.

---

## 0. Preflight — 전제

시작 전에 다음을 증명한다. **설치 확인만으로는 PASS가 아니다.**

| ID | 확인 | 증거 |
|---|---|---|
| `PRE-1` | 브라우저 도구가 런타임에 노출됨 | 도구 목록 |
| `PRE-2` | 실제 페이지로 이동 가능 | 앱 루트 스크린샷 |
| `PRE-3` | 클릭·입력이 반영됨 | 조작 전/후 스크린샷 |
| `PRE-4` | 콘솔·네트워크 로그 읽힘 | 로그 발췌 |

하나라도 실패하면 **QA 전체를 BLOCKED**로 보고하고 PASS를 만들지 않는다.

## 실행 환경 · 테스트 데이터

- 백엔드 `cd backend && uvicorn app.main:app --reload` · 프론트 `cd frontend && npm run dev`
- 인증 없음(미도입). 세션은 UI에서 새로 만든다.
- **시드 세션 A** 에어팟 프로 3 · 운동·건강 맥락 · 수집 목표 **2,000건**(실행 시간 단축)
- **시드 세션 B** 세션 A와 동일 선언이되 `known_insights`를 **비운** 세션 — `QA-EDGE-002` 용
- **구 세션 C** v1 페르소나 스키마로 생성된 기존 세션 — `QA-REG-002` 용
- 실패 주입: Pinecone 인덱스 삭제(`QA-NEG-008`), LLM 응답 스키마 파손(`QA-NEG-009`)

---

## QA-E2E — 정상 흐름

QA-E2E-001 수집 레코드 3필드
Given 세션 A · When 04 수집 실행 · Then `crawl/{sid}/*.jsonl` 레코드에 `doc_id`·`author_hash`·`date`(YYYY-MM-DD) 존재, 기존 필드 손실 없음 `[data]`

QA-E2E-002 known_insights 왕복
Given 세션 A · When 01 선언에서 3건 입력→저장→재진입 · Then 3건이 순서·내용 그대로 표시

QA-E2E-003 06 run 사이드카
Given 세션 A · When 06 판정 실행 · Then `classified/{sid}/run_{ts}.json`에 `alpha`·`escalate_threshold`·`calibration`·`ensemble`·`counts` 존재 `[data]`

QA-E2E-004 alpha가 임계를 정한다
Given 06-A 화면 · When alpha를 3%→5%로 바꾸고 재실행 · Then `escalate_threshold`가 따라 바뀌고, **임계를 직접 입력하는 UI가 존재하지 않음**

QA-E2E-005 06 판정 레코드
When 06 완료 · Then 각 레코드에 `decision`(auto|escalated|human)과 `label` 존재 `[data]`

QA-E2E-006 07 군집 화면
When 07 실행 · Then 실루엣 곡선(k 3~14) · 채택 k · c-TF-IDF 상위 어휘 · 밴드 분포가 표시됨

QA-E2E-007 08 페르소나 v2
When 08 실행 · Then 화면과 산출에 `desire`·`goals`·`centrality_top` 존재 `[data]`

QA-E2E-008 중심 문장 분리
When 09 진입 · Then 클러스터 중심 문장이 순위표 **바깥**에 고정 표시되고, 순위표 행으로도 중복 노출되지 않음

QA-E2E-009 랭킹 3항 분해
When 09 순위표 확인 · Then relevance · known · rarity · quality 4열이 모두 표시

QA-E2E-010 순위 이동 표기
When quality 정렬 · Then relevance 정렬 대비 이동량(▲N/▼N)이 행마다 표시되고, **관련성 1위였던 문서가 내려간 사례가 최소 1건** 확인됨

QA-E2E-011 정렬 토글
When relevance 단독으로 전환 · Then 순위가 재정렬되고 이동량 표기가 사라짐

QA-E2E-012 CAM 구조
When 10-A 진입 · Then 열이 Action(A1…), 행에 상황·**행동**·**장벽**·키워드·Artifact·Sentiment·Opportunity

QA-E2E-013 등급 배지와 인용
Then 각 셀에 관측/추론/추측 중 하나가 붙고, 관측에는 인용 `doc_id`가 연결됨

QA-E2E-014 Reviews 재검색 없음
When Action 상세 열기 · Then 인용이 09 Evidence Package와 동일하고, 네트워크 로그에 재검색 호출 없음

QA-E2E-015 ODI 검산
Then 표시된 ODI가 `I + max(I−S, 0)`와 일치

QA-E2E-016 인사이트 승격
When 11-A에서 인사이트 확정 · Then `known_insights`에 append되고, 다음 세션 09에서 감점에 반영됨 `[data]`

QA-E2E-017 컨셉 문장별 등급
When 11-B EXPERIENCE 확인 · Then 문장 단위로 관측/추측이 갈려 표시

QA-E2E-018 인터뷰 stance
When 반박 인터뷰 입력 · Then `stance:"refute"`로 집계되고 컨셉 수정 요청으로 남음

QA-E2E-019 반례 계보 추적
Then 07 Edge 밴드 → 09 counter 인용 → 10 반례 담론 → 11 service_bullet이 동일 `doc_id`로 이어짐 `[data]`

QA-E2E-020 상수 변경 파급
When 어드민에서 `alpha_known_penalty` 변경 · Then 영향 단계가 재실행 대기로 내려가고, 지난 세션 결과는 당시 값으로 동결

QA-E2E-021 감사 로그
When 프롬프트·상수를 편집 · Then `admin/audit/{ts}.jsonl`에 누가·언제·이전값→새값 기록 `[data]`

## QA-NEG — 거부·차단

QA-NEG-001 작성자 원문 비저장
When 레코드 전체를 검사 · Then 작성자 원문 문자열이 어디에도 없고 `author_hash`에서 역산 불가 `[data]`

QA-NEG-002 Ward 갈래 ID 미발급
When 07 비교 갈래 결과 확인 · Then Ward 결과에 `cluster_id`가 없음 `[data]`

QA-NEG-003 클러스터 가로지르기 차단
Then 모든 페르소나가 정확히 한 클러스터에 속함 `[data]`

QA-NEG-004 filter 3키 필수
When 09 검색 API를 filter 없이 직접 호출 · Then 요청 거부(4xx), 결과가 반환되지 않음

QA-NEG-005 LLM 자기판정 무시
Given LLM 출력에 "관측" 문자열을 강제 주입 · When 10-A 재실행 · Then 등급이 그 문자열을 따르지 않고, 가드레일 경고가 기록됨

QA-NEG-006 변수 린트 차단
When 어드민에서 호출부가 넘기지 않는 변수를 넣고 저장 시도 · Then 활성화 버튼이 잠기고 저장되지 않음

QA-NEG-007 미외부화 프롬프트 편집 불가
When f-string 7건 중 하나를 편집 시도 · Then 읽기 전용으로 차단

QA-NEG-008 Pinecone 부재
Given 인덱스 삭제 · When 09 실행 · Then 요청 거부 + 05 재실행 안내. 빈 결과를 성공으로 처리하지 않음

QA-NEG-009 LLM 스키마 파손
Given 스키마를 깨는 응답 주입 · When 10-A 실행 · Then 1회 재생성 후 실패 시 `*_gen_fail` 기록하고 **다음 단계로 넘기지 않음**

## QA-EDGE — 경계

QA-EDGE-001 doc_id 안정성
When 동일 키워드로 재수집 · Then 같은 `link`의 `doc_id`가 동일 `[data]`

QA-EDGE-002 known_insights 비어 있음
Given 세션 B · When 09까지 진행 · Then 오류 없이 동작하고 quality == relevance이며 화면에 "감점 항 비활성" 경고

QA-EDGE-003 밴드 분포 합
Then Core+Fringe+Edge = 100%

QA-EDGE-004 Edge 보존
Then Edge 밴드 문서 수가 0이 아니고, 07 전후 전체 문서 수가 줄지 않음 `[data]`

QA-EDGE-005 작성자 수 상한
Then 작성자 수 ≤ 문서 수

QA-EDGE-006 커버리지 하한
Given 경험차원 4/6 미만 Context · Then 자동 보충 검색 발동 흔적이 로그에 있음

QA-EDGE-007 추측 비율 상한
When 추측 비율을 30% 초과로 유도 · Then 페르소나 신뢰도가 하향되고 화면에 표시

QA-EDGE-008 표본 부족
Given 표본 20건 미만 Action · Then Satisfaction null, ODI 미산출, "표본 부족" 표기

QA-EDGE-009 동시성 — 진행 중 세션 격리
Given 세션 A 실행 중 · When 어드민에서 프롬프트 편집 · Then 진행 중 세션의 결과가 바뀌지 않고, 시작 시점 `prompt_set` 버전을 유지

QA-EDGE-010 대비 4.5:1
Then 07~11 신규 화면의 텍스트/배경 대비가 전부 4.5:1 이상

QA-EDGE-011 12px 하한
Then 12px 미만 텍스트 없음

QA-EDGE-012 포커스 링
Then 포커스 링이 제거되지 않음

QA-EDGE-013 색 단독 금지
Then 상태가 색만으로 전달되지 않고 배지 텍스트를 동반

## QA-REG — 회귀

| ID | 시나리오 | Expected |
|---|---|---|
| QA-REG-001 | 01→06 전체 흐름 재실행 | 필드 추가 외 동작 변화 없음 |
| QA-REG-002 | 구 세션 C(v1 페르소나) 열기 | 읽기 가능, 크래시 없음 |
| QA-REG-003 | 03 키워드 · 04 수집 화면 조작 | 기존 기능 그대로 |

---

## 보고 형식

QA ID별 `PASS` / `FAIL` / `BLOCKED` + 근거(스크린샷 경로 · 로그 발췌 · expected/actual).
**실행 불가를 PASS로 처리하지 않는다.** 승인 후 시나리오를 빼거나 기대 결과를 약화하지 않는다.
