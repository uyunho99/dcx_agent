# 03 · Plan — DCX STEP 07~11 + 선결 데이터 계약

실행 ID `dcx-step07-11` · base `1ff09c8`

---

## 0. 원칙

- **TDD.** 모든 Task는 RED(실패하는 테스트) → GREEN(통과) → 리팩터 순서. 스키마 계약은 테스트가 먼저 고정한다.
- **파일 소유권은 겹치지 않는다.** 아래 표의 `소유 파일`이 배타적이다. 다른 Task의 파일을 고치지 않는다.
- **커밋은 Controller가 한다.** 구현자는 `READY_FOR_COMMIT` + 변경 파일 목록 + 제안 커밋 메시지를 반환한다.
- 순번은 의존 순서다. **P0를 건너뛰고 P1로 가면 T9에서 막힌다.**

---

## P0 — 선결 데이터 계약 (5 Task)

### T1 · 수집 레코드에 doc_id · author_hash · ISO date
- 소유 `backend/app/services/crawling.py` · `naver.py` · `crawl4ai_svc.py`
- RED `tests/test_crawl_record.py` — 레코드에 세 필드가 있고, `doc_id`가 `link` 기준 안정적(같은 링크 재수집 시 동일), `author_hash`가 salted SHA-256 앞 4바이트이며 원문 작성자 문자열을 저장하지 않음
- GREEN 구현
- 수용 기준 기존 필드 하나도 제거하지 않음 · `date`는 `YYYY-MM-DD`

### T2 · 기존 세션 마이그레이션
- 소유 `scripts/migrate_doc_id.py` · `tests/test_migrate.py`
- RED 구 레코드(`doc_id` 없음)를 읽어 같은 규칙으로 부여하고, 두 번 돌려도 결과가 같음(멱등)
- 수용 기준 `author_hash`는 원문이 없으면 `null` — 추측해서 채우지 않는다

### T3 · known_insights 입력 (STEP 01)
- 소유 `backend/app/models/schemas.py` · `backend/app/routers/sessions.py` · `frontend/src/app/pipeline/start/page.tsx`
- RED 세션 저장/조회 왕복에서 `known_insights[{id,text}]`가 보존됨 · 5~10개 범위 밖이면 경고(차단 아님)
- 수용 기준 목업 `Declare` 화면의 입력 위치와 일치

### T4 · known_insights 임베딩 + Pinecone 메타 확장
- 소유 `backend/app/services/embedding.py` · `backend/app/services/pinecone_svc.py`
- RED 메타에 `doc_id`·`cluster_id`·`persona_id`·`context_id`·`dist_centroid`·`band`·`author_hash`가 들어가고, filter 3키로 조회 시 **다른 클러스터 문서가 섞이지 않음**
- RED `known_insights`가 별도 네임스페이스에 저장되고 `max_sim_to_known` 계산이 0~1 범위
- 수용 기준 `known_insights`가 비면 `max_sim_to_known = 0` (감점 없음) — 이 경우 quality == relevance임을 테스트가 명시

### T5 · 06 산출 계약
- 소유 `backend/app/services/training.py` · `backend/app/routers/training.py`
- RED 레코드에 `decision`·`label`·`reviewed_by` · 사이드카 `classified/{sid}/run_{ts}.json`에 `alpha`·`escalate_threshold`·`calibration`·`ensemble`·`counts`
- RED **`escalate_threshold`는 `alpha`에서 계산된다** — 같은 alpha면 같은 임계, 직접 주입 불가
- 수용 기준 기존 `relevance_score` 유지 · 0.5 하드코딩 제거

---

## P1 — STEP 07~09 (3 Task)

### T6 · 07 군집 → Touch Point
- 소유 `backend/app/services/clustering.py` · `backend/app/routers/clustering.py`
- RED `clusters/{sid}/result_{ts}.json` 스키마 · k 3~14 스캔 곡선 저장 · 문서별 `dist_centroid`로 Core/Fringe/Edge 밴드 부여(P50/P90) · c-TF-IDF 상위 어휘
- RED **ID는 임베딩 갈래에서만 발급** — Ward 갈래 실행 결과에 `cluster_id`가 없음
- 수용 기준 Edge 밴드 문서가 삭제되지 않고 보존됨

### T7 · 08 SNA → 페르소나 (v2 스키마)
- 소유 `backend/app/services/personas.py` · `backend/app/routers/personas.py`
- RED v2 스키마(`persona_id`·`desire`·`goals`·`centrality_top`·`modularity_q`·`status`)에 **`situation`·`pain_point`·`insight` 필드가 없음** (10-A로 이관)
- RED 공출현 행렬 → 아이겐벡터 중심성 → 모듈 분할 · 클러스터를 가로지르는 통합이 발생하지 않음
- 수용 기준 구 세션의 v1 결과는 읽기 가능(마이그레이션 없음, 읽기 전용)

### T8 · 09 Evidence Package
- 소유 `backend/app/services/evidence.py`(신설) · `backend/app/routers/evidence.py`(신설)
- RED quality 산식 · `relevance`와 `quality` **양쪽 순위를 모두 보존**(순위 이동 표시용)
- RED `centroid_sentence`는 `evidence[]`에 포함되지 않고 별도 필드
- RED filter 3키 미적용 시 **요청 거부**(옵션이 아님)
- RED 경험차원 커버리지 < `coverage_min`이면 자동 보충 검색 발동
- 수용 기준 `known_insights`가 비었을 때 quality == relevance이고 경고가 기록됨

---

## P2 — STEP 10~11 (3 Task)

### T9 · 10-A CAM + 등급 기계 판정
- 소유 `backend/app/services/cam.py`(신설) · `backend/app/routers/cam.py`(신설)
- RED 등급이 `retrieve(문장, scope=이 Action의 evidence)` 히트 + 어휘중첩 ≥ `lexical_overlap_min`으로 결정 · **LLM 출력의 등급 문자열은 무시됨**
- RED 추측 비율 > `speculation_max`면 페르소나 `confidence`가 하향
- RED 추측 건이 삭제되지 않고 `grade:"speculated"`로 남음
- 수용 기준 `barrier` 행이 모든 열에 존재(비어도 명시적 null 아님 — 생성 실패 시 기록)

### T10 · 10-B 기회 영역 집계
- 소유 `backend/app/services/cam.py` 내 집계 함수 · `backend/app/routers/cam.py`
- RED `ODI = I + max(I − S, 0)` · `satisfaction_min_n` 미만이면 Satisfaction을 산출하지 않음(null)
- 수용 기준 **새로 계산하는 원천 값이 없음** — 10-A 산출의 집계뿐

### T11 · 11-A/11-B 인사이트 → 컨셉
- 소유 `backend/app/services/insight.py`(신설) · `backend/app/routers/insight.py`(신설)
- RED 확정 인사이트가 `known_insights`에 append됨 · 컨셉 `experience` 문장별 grade · 인터뷰 `stance`(support|refute) 집계
- 수용 기준 반례 Action에서 파생된 `service_bullet`이 추적 가능(`from_action`)

---

## P3 — 어드민 · 프론트엔드 (2 Task)

### T12 · 프롬프트 외부화 + 파이프라인 상수
- 소유 `backend/app/services/prompts.py`(신설) · `backend/app/routers/admin.py`(신설)
- RED 세션이 시작 시점의 `prompt_set` 버전과 상수 스냅샷을 붙듦 · 편집이 진행 중 세션에 영향 없음
- RED 변수 린트 — 호출부가 넘기지 않는 변수가 있으면 **활성화 거부**
- RED 모든 편집이 `admin/audit/{ts}.jsonl`에 이전값→새값으로 기록
- 수용 기준 미외부화 f-string 7곳은 읽기 전용으로 노출

### T13 · 프론트엔드 화면 07~11 + 어드민
- 소유 `frontend/src/app/pipeline/clustering|personas|evidence|cam|insight/**` · `frontend/src/app/admin/**` · `frontend/src/lib/types.ts` · `frontend/src/lib/api.ts`
- 목업 `mockups/parts/{Clustering,Persona,Evidence,ContextMap,Opportunity,Concept,Design,Admin}.body.html` 대응
- 수용 기준 Person A 토큰만 사용(원시 hex·px 금지) · 목업의 정보 구조와 일치

---

## 병렬 가능성

```
T1 → T2
T1 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11
                                      T12 (T5 이후 언제든)
                                      T13 (T8 이후 화면별 순차)
```

T2·T12는 다른 Task와 파일이 겹치지 않아 병렬 가능. 나머지는 스키마 의존이라 순차.

---

## 되돌리기

각 Task는 독립 커밋. P0는 데이터 형태를 바꾸므로 되돌릴 때 재수집이 필요하다 —
**T1 커밋 전에 `crawl/{sid}/` 스냅샷을 뜬다** (`scripts/snapshot_crawl.sh`, T2에 포함).

P1 이후는 신설 아티팩트 키라 파일 삭제로 되돌아간다.

---

## 실패 시나리오

| 상황 | 처리 |
|---|---|
| `known_insights`가 비어 있음 | 오류 아님. quality == relevance로 동작하고 09 화면에 "감점 항 비활성" 경고 |
| Pinecone 인덱스 없음 | 09 요청 거부 + 05 재실행 안내 |
| LLM 응답이 스키마를 깸 | 1회 재생성 → 실패 시 `stage_N.json`에 `*_gen_fail` 기록하고 다음으로 넘기지 않음 |
| 표본 < `satisfaction_min_n` | Satisfaction null, ODI 미산출, 화면에 "표본 부족" 표기 |
| 등급 판정에서 검색 히트 0 | 추측으로 확정. 비율이 상한을 넘으면 페르소나 신뢰도 하향 |

---

## 회귀

STEP 01~06은 기능이 바뀌지 않는다(필드 추가만). 기존 흐름이 깨지지 않음을 QA가 확인한다 — QA_PLAN의 `REG-*` 항목.
