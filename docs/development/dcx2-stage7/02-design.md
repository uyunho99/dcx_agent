# 02 · 설계 — 묶음 ② 7단계 근거 탐색

- 기준(승인됨): [`../dcx2-stage6-8/02-design.md`](../dcx2-stage6-8/02-design.md) **4절 전체** · 2.3(tag) · 2.4 · 7 · 8 · 9 · 10(화면 7) · 11(7) · 14절 디자인 리뷰(D-223 · D-227) · 목업 s4. 이 문서는 그 설계를 바꾸지 않고, (1) 묶음 ① 구현에서 정해진 실제 규칙 (2) D-246 불용어 (3) 설계가 비워 둔 저장 구조 · 실행 규칙만 정한다.
- 결정: 공통 원장 D-249~.

## 1. 묶음 ①에서 이어받는 규칙 (구현 기준)

| 항목 | 묶음 ① 실제 | 7단계 적용 |
|---|---|---|
| 워커 | `app/work/worker.py` KINDS에 `segment`, args `{'k', 'fresh'}` · `k=None ∧ fresh=False`면 이어 하기 | `evidence` 추가, args `{'fresh': bool, 'contexts': [id] \| None}`(None = 전체, 목록 = 실패 행 다시 시도) |
| 실행 세대 | `segment.run` + 오래된 화면 확정 409 `stale_run`(D-239) | `evidence.run` 같은 방식. 6단계를 다시 나누면(새 segment run) `evidence/` 무효 → `{status: 'stale'}` |
| 저장 | `segment/segment.sqlite` WAL · 스키마 DDL 1회 · 세대와 행을 한 스냅샷으로 읽기 | `evidence/evidence.sqlite` 같은 패턴(2절) |
| LLM | `app/llm` 레지스트리 · 작업 이름별 `tests/fixtures/llm/{task}.json` 가짜 응답 · 전부 backend/timeout 실패면 `interrupted` + LLM_REASON | 작업 `evidence.queries` · `evidence.tag` · `evidence.novelty`, 같은 중단 규칙 |
| 완료 표시 | 서버 `completion.segmentDone`(status done ∧ stage6 not stale) → `completedThrough` 6 | `completion.evidenceDone`(evidence.status done ∧ stage7 not stale) → 7 |
| 버전 | 3~6부터 다시 시 `evidence/` 삭제 · `evidence.status = stale`(versions.py 이미 구현) | 7부터 다시: `segment/` 유지, `evidence/` · `persona/` 삭제(설계 6절) — 테스트로 고정 |
| 비교 | `compare(stage6)` = 보고서 + 층별 확정 요약(QA fix 4 지표 표) | `compare(stage7)` = `stage_7.json` 요약 + Context별 선택 doc_id 차이 수 |

## 2. 저장 구조 `versions/vN/evidence/` (설계가 비워 둔 부분)

`evidence.sqlite`(버전 안):
| 테이블 | 열 |
|---|---|
| `meta` | `run` · `params_json` · `started_at` |
| `queries` | `owner`(`persona:{id}` · `context:{id}`) · `dim`(desire_check_0/1 · artifact · Sense · Feel · Think · Act · Relate · Outcome · Counter · Residual) · `text` · `origin`(llm/regen/fallback) |
| `candidates` | `context_id` · `doc_id` · `relevance` · `dims_hit_json` · `band` · `known_excluded`(null/handed/match/dup) · `round`(0 초기, 1~3 새 발견 확장, `cov` Coverage 보충) |
| `selected` | `context_id` · `tab`(all/new) · `rank` · `doc_id` · `role`(support/counter/rare) · `quality` · `novelty` · `novelty_reason` |
| `contexts` | `context_id` · `persona_id` · `status`(queued/running/done/failed/skipped) · `error` · `coverage` · `counts_json` · `updated_at` |
| `persona_support` | `persona_id` · `rank` · `doc_id` · `kind`(desire/artifact) |

버전 밖 캐시 `llmcache/{sid}/{prepKey}/tag-{pver}.sqlite`(설계 2.3 그대로) — 표 `tags`, `known`.
결과 파일: `queries.json`(사람이 읽는 쿼리 사본) · `package.json`(2.4) · `stage_7.json`(4.8).

## 3. 실행 순서와 동시성

```
적재(segment 확정값 · 원문 · 벡터) → Persona별 쿼리(4.1) → Context마다 [검색(4.2) → 태깅(4.3) → 선택(4.4) → 탭(4.5) → novelty(4.6)] → 조립(4.7) → stage_7.json
```
- Context 단위 체크포인트: `contexts.status = done`이면 이어 하기에서 건너뜀. 하트비트는 Context · 태깅 묶음마다.
- **LLM 동시 호출(D-250):** 태깅 묶음(8건)과 Context 처리를 `ThreadPoolExecutor(max_workers = EVIDENCE_LLM_CONCURRENCY = 4)`로. 설정 `settings.evidence_llm_concurrency`(기본 4, 1이면 순차). SQLite 쓰기는 메인 스레드 한 곳에서만(결과를 모아 씀).
- 실패 규칙: Context 하나의 예외 → 그 행 `failed` + 사유, 다른 Context 계속(9.1 "다시 시도 · 건너뛰고 진행"). 한 단계의 LLM 호출이 전부 backend/timeout이면 `interrupted`.
- Known Insight 추가(실행 중 포함, D-223): 저장 후 아직 안 돈 Context는 바로 반영, `done` Context는 `known_changed` 표시 → "새 발견 다시 계산" = `POST .../refresh-new`(LLM 0회, 설계 4.5).

## 4. 질의 임베딩

- `Embedder.embed(texts, input_type='document')`로 인자 추가(기존 호출은 그대로 document). Voyage는 `input_type` 전달, 가짜 임베더는 무시. 7단계 질의만 `'query'`.
- 검색은 기존 `app/vectors/search.cosine_topk(store, queries, top_k, allow, exclude)`를 쓰되, 7단계 모듈은 `allow`가 `None`이면 `ValueError`를 내는 얇은 래퍼 `evidence.search.filtered_topk`만 부른다(AC-06, 설계 4.2). 테스트: 허용 집합 밖 문서가 절대 안 나옴 + `cosine_topk`를 직접 import하지 않음(정적 검사).

## 5. 불용어 (D-246)

- `app/segment/stopwords.py`: `STOPWORDS: frozenset[str]` — 흔한 한국어 명사 약 100개(예: 사용 · 생각 · 정도 · 경우 · 제품 · 사람 · 문제 · 부분 · 이번 · 때문 · 진짜 · 정말 · 하나 · 자체 · 이상 · 이하 · 정보 · 내용 · 방법 · 상황 · 느낌 · 필요 · 가능 · 시간 · 처음 · 지금 · 요즘 · 마음 · 후기 · 리뷰 …), 파일 한 곳에서 편집.
- 제외 함수 `is_stopword(word, bk)`: 목록 · 1글자 · 숫자만 · 제품명(`bk`, 공백 제거 비교) · 제품명을 포함한 복합어.
- 적용 위치(D-249): 6-A 클러스터 키워드(c-TF-IDF) · 6-B 어휘 네트워크(L2 어휘 300개 선정 전) · 6-C Context 키워드(LDA 상위 어휘 표시 · 7단계로 넘기는 키워드) · 7단계 쿼리 입력 키워드 · Artifact 집계. **LDA 학습 어휘는 그대로**(C_v 선택 결과가 바뀌지 않게, 표시 · 전달 키워드만 거름).
- `stage_6.json` params에 `stopwords: {count, hash}` 기록. 기존 6단계 결과는 다시 실행 전까지 그대로(안내 없음 — 결과 JSON의 hash로 구분).

## 6. 곁가지 UI

- 6-C Context 카드: `undifferentiated_candidate`면 경고 배지 "새 Context 후보 — 원문 3건"(펼치면 원문 3건, 생성 버튼 없음).
- 라벨링 화면 상단 배너(정보): "7단계에서 무관 판정 N건 — 4단계 재점검 참고" (N > 0일 때만, 자동 재판정 없음).
- 사이드바: 7 "근거 탐색" 경로 `/pipeline/evidence`, 완료 = `evidenceDone`. 클러스터링 화면의 기존 "근거 탐색 실행" 버튼이 이 화면으로 이동 + 실행.

## 7. 화면 7 상태 (설계 4.9 · 9.1 그대로 + 문구 확정)

| 상태 | 문구 |
|---|---|
| 6-C 미확정 | "6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요." (실행 버튼 비활성) |
| 실행 중 | 행 배지 `완료 · 진행 중 · 대기 · 실패`, 상단 "Context 12/31 · 태깅 호출 84회" |
| 실패 행 | "이 Context의 근거를 찾지 못했습니다: {사유}" + [다시 시도] [건너뛰고 진행] |
| 결과 stale | 클러스터링 결과가 바뀐 경우 "6단계가 다시 나뉘어 이 근거는 이전 결과 기준입니다. 다시 실행하세요." |

## 8. 디자인 리뷰

화면 7은 묶음 ① 설계의 디자인 리뷰(02-design 14절, 결정 2A · 6A = D-223 · D-227, 목업 s4)에서 이미 검토 · 승인됐다. 이 문서에서 새로 생긴 UI는 6절의 배지 · 배너 두 개와 7절 문구뿐이며 기존 `Badge` · `Banner` 컴포넌트를 그대로 쓴다(새 레이아웃 없음).

## 9. 테스트 추가분 (설계 11절 7단계 + 이 문서)

- 불용어: 6-B 중심 어휘 · Context 키워드 · 7단계 키워드에 목록 단어 · 제품명 없음, LDA 토픽 수 선택은 불용어 전후 동일(합성 픽스처).
- 동시성: `concurrency=4`와 `=1` 결과(선택 doc_id · 순서)가 같다. 태깅 캐시 쓰기 경합 없음.
- 실행 세대: 6단계 재실행 후 evidence 상태 stale, 오래된 화면의 refresh-new 409.
- 7부터 다시: segment 확정값 유지 · evidence 삭제 · tag 캐시 재사용(LLM 0회).
