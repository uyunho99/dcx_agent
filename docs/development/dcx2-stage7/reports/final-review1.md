# 묶음 ② (7단계 근거 탐색) 최종 브랜치 리뷰 1

- 범위: `69dcf91..a92f2f3` (feature/dcx2-stage7, T1~T16), 리뷰 패키지 `.superpowers/sdd/03-plan/review-69dcf91..a92f2f3.diff`
- 기준: `dcx2-stage7/02-design.md` · `03-plan.md`(계약 · Review Focus), `dcx2-stage6-8/02-design.md` 2.3 · 2.4 · 4 · 6~11 · 14, D-201~D-258
- 실행 확인(읽기 전용):
  - `backend/.venv/bin/python -m pytest backend/tests/evidence backend/tests/segment -q` → **435 passed, 2 deselected**(perf)
  - `npm --prefix frontend test` → **56 files / 522 tests passed**
  - 통합 테스트 산출 `package.json`(test_stage5_to_stage7_offline)을 묶음 ③ 리더 `app/persona/package.py`(dcx_agent-stage8-impl HEAD 7ce3215)로 검증 → **114 validation errors**

## 판정: **Ready with fixes**

핵심 파이프라인(필터 강제 검색 · 쿼리 검증 · 지연 태깅 캐시 · DPP · 탭 · 워커 동시성 · partial · stale/409 · 버전 7부터 다시)은 설계대로이고 테스트도 촘촘하다. 다만 7→8 유일한 계약인 Evidence Package가 지금 상태로는 묶음 ③에서 읽히지 않고(Critical 1), 화면과 백엔드 사이 필드 이름이 어긋난 곳이 둘(진행 표시 · 라벨링 배너), 문장형 Known Insight가 끝난 Context에 반영되지 않는 설계 누락이 있다. 모두 국소 수정으로 고칠 수 있다.

| 등급 | 건수 |
|---|---|
| Critical | 1 |
| Important | 8 |
| Minor | 11 |

---

## Critical

### C1. Evidence Package가 묶음 ③ 리더에서 검증 실패 (2.4 계약 불일치)
- 위치: `backend/app/evidence/assemble.py:143-154`(Context quality), `:284-285`(Persona quality), `:220-229`(`_item` quote · polarity · novelty), `backend/app/evidence/package.py:15-86` ↔ `dcx_agent-stage8-impl/backend/app/persona/package.py:19-71`
- 실제 실패: 통합 테스트가 만든 package.json을 ③ `Package.model_validate_json`에 넣으면 114건 오류.
  - ② 쪽 원인(설계 2.4 위반): Context `metrics.quality`가 6단계 값 그대로라 `{cohesion, npmi}`만 있고 2.4가 정한 `boundary` · `stability` 키가 없다(합성 세션 출력 `{'cohesion': 0.8955, 'npmi': None}`). Persona `quality.cohesion/boundary`는 항상 null. `quote`가 없으면 `null`(2.4 예시는 항상 객체).
  - ③ 쪽 원인: `polarity: str`(②는 float −1~1), `novelty: str` 필수(②는 전체 탭 전용 · 반례 · 희소에서 null), `RareEvidence.dist_centroid/combo_rarity: float` 필수(②는 null 가능), `Metrics.importance/satisfaction/odi: float` 필수(②는 관측 없으면 null), `ContextQuality` 4키 모두 float 필수.
- 실패 시나리오: ② merge 뒤 ③ T17 rebase에서 실제 7단계 결과로 8단계를 돌리면 `load_package`가 첫 Persona에서 예외 → 8단계 전체 불가. 각 묶음은 자기 픽스처로만 테스트해 둘 다 초록이다.
- 수정:
  1. ②: `_context_metrics`에서 quality를 `{cohesion, boundary, stability, npmi}` 4키로 고정(없으면 null), `ContextMetrics.quality`를 해당 4키 모델로. `quote`가 없을 때 정책을 2.4에 한 줄로 확정(권장: `null` 허용을 명시).
  2. ③: `polarity: float | None`, `novelty: str | None`, rare 두 값 · metrics · quality 전부 `float | None`, `quote: Quote | None`.
  3. 2.4 jsonc에 nullable 표기 추가(decision-log에 D-259 등으로 기록), 공용 계약 테스트 하나: ② 통합 테스트 산출물을 ③과 같은 엄격 모델(혹은 공용 JSON Schema 픽스처)로 검증.

---

## Important

### I1. 문장형 Known Insight를 Context 완료 뒤 추가하면 판정이 영영 돌지 않음 (D-212 · 4.5)
- 위치: `backend/app/evidence/pipeline.py:123-137`(`_refresh_cached`), `:506-518`(`refresh_new`), `:228-247`(`reconcile`). `tagging.judge_known` 호출은 `pipeline.py:279` 한 곳(실행 중 `prepare` 안, 새로 준비하는 문서만).
- 시나리오: 7단계 완료 → 사용자가 서랍에서 문장 "전기료가 걱정된다"를 추가 → 행에 "Known Insight가 바뀌었습니다 · 새 발견 다시 계산" → 누르면 `refresh-new`가 LLM 0회로 캐시만 투영. 새 KI의 `(doc, ki)` 쌍이 없으니 `known_match`는 전부 none → 그 문장과 같은 원문이 새 발견 탭에 그대로 남는다. 실행 중에 추가해도 이미 끝난 Context는 같은 결과.
- 설계: 4.5 "문장형 Known Insight를 추가하면 그 항목에 대해 캐시 문서 `known` 판정을 다시 돈다(D-212)". LLM 0회 규칙은 "넘긴 원문" 추가에만 해당한다.
- 수정: `refresh_new`에서 `knownIds`에 없던 **statement** KI만 골라 그 Context 후보(`ev.candidates(cid)`)에 `judge_known`을 돌린 뒤(LLM 호출 수 기록) `_refresh_cached`. doc KI만 바뀌었으면 지금처럼 0회. 테스트: `test_statement_ki_after_done_rejudged_only_that_item`(호출 = 후보 수/8 묶음, 기존 KI 재호출 0) + 기존 `test_refresh_new_zero_llm`은 doc KI로 한정.

### I2. 근거 탐색을 한 번도 안 돌린 세션 · "7단계부터 다시" 버전에 "6단계가 다시 나뉘어…" 경고가 뜸
- 위치: `backend/app/segment/pipeline.py:68`(새 6단계 실행마다 `data['evidence'] = {'status': 'stale'}`), `backend/app/context/versions.py:160-162`(7부터 다시 → evidence 디렉터리 삭제 + `stale`), `frontend/src/components/evidence/EvidenceScreen.tsx:19,55`.
- 시나리오: 새 세션에서 6단계 첫 실행 · 전부 확정 → 화면 7 진입 → 실행 전인데 경고 배너 "6단계가 다시 나뉘어 이 근거는 이전 결과 기준입니다. 다시 실행하세요." QA-E8(7부터 다시 → "7단계 빈 화면")도 같은 배너가 뜬다. 통합 테스트(`test_integration.py:112-113`)가 `'stale'`을 허용해서 가려졌다.
- 수정: 세그먼트 reset은 기존 evidence 결과가 있을 때만(`evidence.status ∉ {none, 없음}` 또는 `evidence/evidence.sqlite` 존재) stale. `_restart` 7은 디렉터리를 지우므로 `{'status': 'none'}`. 프런트는 `status === 'stale' && status.run !== null`일 때만 staleCopy. 테스트: 6단계 첫 실행 뒤 `/evidence/status`가 `none`.

### I3. 실행 중 "태깅 호출 N회"가 항상 0
- 위치: `frontend/src/components/evidence/EvidenceScreen.tsx:59`(`status.stage7?.tag_calls`), `backend/app/evidence/assemble.py:175-186`(`tag_calls` 키 없음, `llm_calls` 합계만), `pipeline.py:190`(fresh 실행 시 `stage_7.json` 삭제 → 실행 중엔 없음), `pipeline.py:222-224`(실제 값은 `session.evidence.detail.tagCalls`에만), `routers/evidence.py:85-98`(detail 미노출).
- 시나리오: 02 §7 "Context 12/31 · 태깅 호출 84회"가 실행 내내 "태깅 호출 0회". 이어서 진행이면 이전 실행 보고서 값이 보일 수도 있다. 프런트 테스트(`evidenceScreen.test.ts:16`)는 백엔드가 만들지 않는 `stage7.tag_calls`를 가짜로 넣어 통과.
- 수정: status 응답에 `tagCalls: evidence.detail.tagCalls`(또는 `progressDetail`) 추가, 타입 `EvidenceStatus.tagCalls?: number`, 화면은 그 값 사용. 백엔드 API 테스트에서 실행 중 값 > 0 확인.

### I4. 라벨링 화면 배너가 절대 안 뜸 (키 이름 불일치)
- 위치: `frontend/src/app/pipeline/labeling/page.tsx:53`(`result.stage7?.irrelevant`) ↔ `backend/app/evidence/assemble.py:176,272`(`relevant_false`).
- 시나리오: 7단계에서 무관 판정 12건 → 라벨링 화면에 "7단계에서 무관 판정 12건 — 4단계 재점검 참고"가 나와야 하는데(02 §6, QA-E7) 키가 없어 항상 0.
- 수정: 프런트를 `stage7.relevant_false`로(또는 백엔드 보고서에 `irrelevant` 별칭). T15 테스트를 실제 `stage_report` 출력 형태로.

### I5. 인용 하이라이트가 다른 필드 텍스트에 적용됨 (D-213 · D-258)
- 위치: `frontend/src/components/evidence/EvidenceCard.tsx:11`(`highlight(item.text, quote.start, quote.end)`), `backend/app/routers/evidence.py:126`(`text = (body or title)[:600]`), `pipeline.py:490`.
- 시나리오: 인용이 `comment` idx 3의 5~20번째 글자 → 카드 본문(본문 앞 600자)의 5~20번째 글자에 `<mark>`가 칠해지고, 하이라이트가 "있으니" 실제 인용 blockquote는 숨겨진다(`EvidenceCard.tsx:15`). 제목 인용도 같다. 화면이 원문에 없는 위치를 근거로 강조 — 근거 화면에서 가장 신뢰가 중요한 부분.
- 수정: API `EvidenceItemView`에 `fieldText`(quote.field의 원문: 제목 · 본문 앞 N자 · 해당 댓글)를 넣고 하이라이트는 그 텍스트에만. 또는 프런트에서 `location.field === 'body'`일 때만 `item.text`에 하이라이트하고 나머지는 blockquote + 위치 배지. Vitest: 댓글 인용 카드에 본문 mark 없음.

### I6. refresh-new 뒤 전체 탭 행에 옛 novelty가 남음 (4.6 위반)
- 위치: `backend/app/evidence/pipeline.py:128-133`(new 탭만 다시 씀, `all` 행의 novelty는 compute 당시 값 유지), `assemble.py:311-317`(어느 탭 행이든 novelty를 아이템에 복사).
- 실제 관측: 통합 테스트 패키지 첫 근거 `{"doc_id":"d000056", "novelty":"high", "tab":["all"], ...}` — 새 발견 탭에서 빠진 문서가 전체 탭 전용인데 novelty high.
- 시나리오: 카드 [Known Insight에 추가] → 새 발견 다시 계산 → 그 문서는 새 발견에서 빠지지만 전체 탭 카드 · Evidence Package에는 "새로움 high"가 남아 8단계가 이미 아는 얘기를 새 발견으로 서술할 수 있다.
- 수정: `_refresh_cached`에서 같은 Context `all` 행을 다시 써 novelty = (새 new 탭 소속이면 그 값, 아니면 None). `assemble`은 `tab == 'new'` 행에서만 novelty를 가져온다. 테스트: refresh 뒤 tab=['all'] 아이템 novelty null.

### I7. `undifferentiated_candidate` 플래그가 segment.sqlite에 영구히 붙음
- 위치: `backend/app/evidence/assemble.py:84-95,297-302`(추가만, 제거 없음), `versions.py:150-163`(7부터 다시는 `segment/` 유지).
- 시나리오: v1 7단계가 C2에 미분화 후보를 냄 → "7단계부터 다시"로 v2 → v2 6-C에 "새 Context 후보 — 원문 3건" 배지가 그대로, 펼치면 `getEvidenceContext`가 409 `not_ready`로 오류 배너(`ContextLayer.tsx` CandidateSources). 같은 버전에서 재실행 · refresh로 후보 무리가 사라져도 배지는 안 없어진다.
- 수정: assemble에서 Context마다 플래그를 set/remove 둘 다(이번 실행 결과 기준), `_restart` ≤7에서 contexts.flags_json의 이 플래그 제거. 또는 6-C가 evidence 상태(`counts.undifferentiated`)를 읽게 하고 segment에는 쓰지 않는다.

### I8. Persona 단위 위반 하나가 정상인 Context 쿼리까지 전부 대체 쿼리로 바꿈 (4.1 (d))
- 위치: `backend/app/evidence/queries.py:141`(`cid is None`인 위반이 있으면 `failed_ids = 전체`), `:153-156`(persona_rows 비움).
- 시나리오: 재생성 뒤에도 `persona_query.artifact`가 2문장(사소한 Persona 수준 위반) → 그 Persona의 Context 3개가 모두 "Context 이름 + 키워드 3개" 대체 쿼리로 검색되고 `query_gen_fail` 3건, 동시에 persona_rows가 비어 Desire 근거 0건인데 이건 어디에도 기록되지 않는다. 설계 (d)는 "해당 Context에 대체 쿼리".
- 수정: 위반을 세 범주로 나눈다 — 응답 자체 실패(전체 대체), Persona 쿼리 위반(Persona 쿼리만 대체: Desire 문장 + Goal → `origin: fallback`, `persona_query_fail` 기록), Context별 위반(그 Context만). 알 수 없는 context ID 추가는 그 ID를 무시하고 위반으로 세지 않아도 된다. 테스트 추가.

---

## Minor

- **M1. Act 불일치 건수 누락** — 4.3 되먹임("relevant=false 건수 · reason_code 분포 · Act 불일치 건수를 stage_7.json에")에서 Act 불일치가 `assemble.stage_report`(`assemble.py:175-186`)에 없다. 수정: 태깅 relevant 문서의 `tagProbs.act ≥ .5`와 LLM `context_dims.activity_response` 유무 불일치를 세어 `act_mismatch` 추가(6단계 `dims._summary`와 같은 정의).
- **M2. 반례 기준 평균이 화면과 패키지에서 다름** — API(`routers/evidence.py:145-146`, `pipeline.py:496-497`)는 후보 풀의 polarity 평균, 패키지(`assemble.py:318-320`)는 Context 배정 문서 전체 중 캐시된 것의 평균. 같은 Context의 화면 반례 목록 ≠ package `counter_evidence`일 수 있다. 수정: 한 함수(`context_polarity_mean(context_id)`)로 통일.
- **M3. 첫 인용만 사용** — `assemble._item`(`assemble.py:222-223`)이 `quotes[0]`만 본다. 첫 인용이 미확인이고 둘째가 확인이면 등급이 불필요하게 하향. 수정: 첫 `verified` 인용, 없으면 첫 인용.
- **M4. novelty 입력이 과대** — `pipeline.py:344`가 문서 전체(본문 전체 · 모든 댓글 · `_input` · `theta_json` 등 내부 필드)를 넣고 core_reps도 원본 행 그대로. 실제 LLM에서 토큰 비용 · 한도 위험. 수정: 태깅과 같은 발췌(본문 1,500자 · 댓글 10×300 · 인용 · pain_point · unmet_need)만.
- **M5. novelty 배지 임계 미적용** — `EvidenceCard.tsx:21`이 none/low도 "새로움 low · 잠정"으로 표시. 4.6은 high 이상만 "새 발견" 표시. API에 `showNovelty`(이미 `apply_novelty`가 계산)를 실어 그때만 강조, 나머지는 보조 텍스트.
- **M6. 6단계 "근거 탐색 실행"은 이동만** — `SegmentScreen.tsx`의 버튼은 `/pipeline/evidence`로 가기만 한다. 02 §6 "이 화면으로 이동 + 실행". 의도적으로 바꿨다면 decision-log에 기록, 아니면 `?start=1` 같은 신호로 진입 시 실행.
- **M7. 공유 캐시에서 `drop_known`** — 태그 캐시는 버전 밖(prepKey 단위)인데 KI는 버전마다 복사된다. v2에서 KI를 지우면(`pipeline.py:235,515`) 같은 id를 쓰는 v1 · v3의 판정 쌍도 사라져 조용히 "일치 없음"이 된다(I1 때문에 다시 판정되지도 않음). 수정: 삭제는 캐시 행을 지우지 말고 투영에서만 무시(이미 `_project`가 현재 KI만 봄), 또는 버전별 참조 집합을 둔다. 설계 D-212 문구와 다르므로 결정 기록 필요.
- **M8. refresh-new가 세션 전체를 다시 읽음** — `pipeline._load`(`:48-73`)는 segment 문서 전부 · 전처리 jsonl 전부 · 벡터 전부, 이어서 `_assemble`(패키지 전체 재조립, Context마다 VectorStore 열기)을 세션 잠금 안에서 한다. 설계 7 "요청 안에서 동기로(수 초)". 합성 세션 perf 테스트는 리랭킹 · 탭만 측정. 수정: 그 Context 후보 문서 · 벡터만 적재, 조립은 해당 Persona 블록만 갱신하거나 `GET /package` 시 지연 조립. 실세션 크기로 한 번 측정해 보고서에 기록.
- **M9. doc 형 KI도 LLM 판정** — `pipeline.py:279`가 모든 KI id로 `judge_known`을 불러 넘긴 원문(doc) KI도 문서×KI LLM 판정을 한다(D-212: 넘긴 원문은 LLM 없이 handed/0.95로 처리). 또 `_pairs`(`tagging.py:167-177`)는 `#k` 일치 시 다른 KI 쌍을 비워 두어 KI마다 추가 호출이 생긴다. 수정: `judge_known` 대상은 statement KI만.
- **M10. stale 상태에서 완료 행 선택 시 영원한 스켈레톤** — `EvidenceScreen.tsx:141`이 stale이면 상세 요청을 안 하는데 `ContextList`는 done 행 선택을 허용 → 오른쪽이 "근거 불러오는 중" 스켈레톤으로 고정. 수정: stale이면 행 선택을 막거나 "다시 실행 후 열람할 수 있습니다." 문구.
- **M11. 작은 표시 누락** — Artifact가 이름만 보이고 `mention_count`가 빠짐(`EvidenceScreen.tsx:73`), "Known Insight #2와 같은 내용"(4.5)이 번호 없이 "Known Insight와 같은 내용", `partial` 상태에 안내 문구 없음(실패 행으로만 알 수 있음).

---

## 설계 항목별 점검 요약

| 항목 | 결과 |
|---|---|
| 4.1 쿼리 · 검증 (a)~(d) · 재생성 1회 · 대체 | (a)(b)(c) · 재생성 · 대체 문구 맞음. Persona 수준 위반 처리 I8 |
| 4.2 Context 필터 (AC-06) | `filtered_topk` None→ValueError, `cosine_topk` 직접 import 정적 테스트, allow = Context/Persona 문서, Counter 가산 제외, top15→합집합→50, dims_hit 기록 — 맞음 |
| D-256 Voyage input_type | 질의만 `query`, 문서 요청 그대로 — 맞음 |
| 4.3 지연 태깅 · 캐시 키 · pver | `tag-{pver}`(프롬프트 해시 12자) · doc_id 키 · `(doc, ki)` 쌍 표 · 8건 묶음 · 누락 1회 재시도 후 untagged(D-253) · lazy dims(같은 dims 캐시 파일) — 맞음. 완료 뒤 문장 KI 판정 누락 I1 |
| D-213/D-254/D-258 인용 위치 | 공백 정규화 후 원문 코드 포인트 위치, 댓글 idx = prepared 순서, 프런트 `Array.from` — 맞음. 하이라이트 대상 텍스트 I5 |
| 4.4 · D-257 DPP · Coverage · rare · dpp_fill | Chen 2018 증분 Cholesky, 커널 정의, 보충 1회(탭별), rare 교체, 0.95 미만 채움 + `dpp_fill` — 맞음 |
| 4.5 새 발견 (AC-08) | handed · match · 0.95 dup 제외, 확장 50×최대 3, refresh-new LLM 0회 — 맞음(문장 KI 제외, I1) |
| 4.6 novelty | Context당 1회 · 최종 ≤10 + Core 5 · 전체 탭 전용 null — refresh 뒤 위반 I6 |
| 4.7 지표 | importance · satisfaction min-max · odi · author_count(문서 작성자만) · Persona 가중 평균 — 산식 맞음 |
| 4.8 stage_7.json | 항목 대부분 있음, Act 불일치 M1, 화면이 기대하는 `tag_calls` · `irrelevant` 없음 I3 · I4 |
| 2.4 패키지 | ③과 불일치 C1 |
| D-250 동시성 | Context 계산은 풀, 태깅 · 모든 SQLite 쓰기는 rpc로 워커 메인 스레드, 공용 세마포어로 호출 상한, 순서대로 게시 → 1 vs 4 동일 테스트 — 맞음 |
| D-252 partial | 실패 행 있으면 partial, skip으로 전부 처리 시 done, `evidenceDone`은 done ∧ stage7 not stale — 맞음 |
| 세대 · stale · 409 | 매 실행 run 교체, refresh/skip `stale_run` 409, 6단계 재실행 → stale + 다음 실행 fresh — 맞음(첫 실행 오표시 I2) |
| 버전 7부터 다시 | segment 유지 · evidence 삭제 · 캐시 재사용 · evidenceDone 제거 — 맞음(플래그 잔존 I7, 문구 I2) |
| D-246/D-249 불용어 | c-TF-IDF · L2 · L3 표시 키워드 · 7단계 키워드 · Artifact에 적용, LDA 학습 어휘 불변(`show_topic` 뒤 거름), `stage_6.json` 서명 — 맞음 |
| API ↔ 프런트 | 경로 · 요청 · 응답 필드 1:1 일치. 어긋남은 `stage7` 보고서 키 두 곳(I3 · I4) |
| 화면 7 상태 · 문구 | 6-C 미확정 · 실행 중 · 실패 행 · stale · 빈 상태 3종 · 쿼리 실패 · 제외 안내 문구 모두 설계 그대로. 파란 버튼 하나(D-137) |
| 접근성 | nav/aria-label · aria-current · role=status · 탭 컴포넌트 · 1024px 2단 그리드 — 문제 없음. 미확인 인용 설명이 `title` 툴팁에만 있어 키보드로는 안 보임(배지 글자는 보임, 허용 범위) |

## 테스트 품질

- 단언 없는 테스트는 없다(evidence 테스트 전체 AST 확인). Review Focus 1~5에 각각 테스트가 있다(`test_comment_index_from_prepared_order`, `test_known_deleted_midrun` ×2, `test_small_context_returns_all`, `test_tag_response_id_mismatch`, `test_stale_ui_actions_409`).
- 빈 곳:
  - 프런트 테스트가 백엔드가 만들지 않는 응답 모양(`stage7.tag_calls`, `stage7.irrelevant`)을 가짜로 넣어 I3 · I4를 가렸다 → 계약 픽스처를 백엔드 `stage_report` 출력에서 생성하거나 키를 상수로 공유.
  - 묶음 간 패키지 계약 테스트 없음(C1).
  - 완료 뒤 문장형 KI 추가(I1), refresh 뒤 전체 탭 novelty(I6), 첫 6단계 실행 뒤 evidence 상태(I2), 댓글 인용 하이라이트(I5) 테스트 없음.
  - 통합 테스트 `test_integration.py:112-113`이 `'stale'`을 정상 상태로 허용 — I2 수정 뒤 `'none'`으로 좁힐 것.
