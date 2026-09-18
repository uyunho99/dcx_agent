# 02 · Design — DCX STEP 07~11 + 선결 데이터 계약

실행 ID `dcx-step07-11` · 2026-09-18

---

## 1. UI 여부

**UI 있음.** 화면 15개를 Design 캔버스 아티팩트로 제작했다.

- 아티팩트: https://claude.ai/artifact/8mb7VfY8ZyX2s7w8xpbJTK (페이지 `Person A`)
- 소스: `docs/development/dcx-step07-11/mockup/parts/*.body.html` + `docs/development/dcx-step07-11/mockup/_shell.css` → `node build.mjs` → `docs/development/dcx-step07-11/mockup/project/*.dc.html`
- 목업 포인터: `docs/development/dcx-step07-11/mockup/README.md`

이번 범위의 화면은 **07 · 08 · 09 · 10-A · 10-B · 11-A · 11-B + 어드민** 8개이고, 나머지 7개(00~06-B)는 선결 조건이 닿는 부분만 바뀐다.

### 디자인 시스템

Person A 디자인 시스템을 단일 기준으로 쓴다. 핸드오프 번들의 토큰 파일(`tokens/{colors,typography,spacing,base}.css`)을 `_shell.css`에 그대로 인라인했고, Pretendard 4종(400/500/600/700)과 로고를 아티팩트 에셋으로 올려 `/_blob/` 주소로 참조한다.

준수 상태: 원시 hex·px 리터럴 **0건**(SVG 차트 색까지 `var(--토큰)`), uppercase 없음, 12px 미만 없음, 정적 카드 그림자 없음, 액션은 `--action #0a73b5`(브랜드 블루로 버튼을 채우지 않음). 표는 §7.5 `dense`(13px) 변형.

- 규칙 문서: `DESIGN.persona.md`
- 준수 규칙: 핸드오프 번들의 `_adherence.oxlintrc.json`

---

## 2. 데이터 구조

전체 계약은 `resources/DCX_STEP07-11_개발안_데이터계약.md`에 있다. 여기서는 **바뀌는 것**만 적는다.

### 2-1. 04 수집 레코드 — 필드 3종 추가

```jsonc
{ "doc_id": "d_000123",      // 신설 · 이후 전 단계의 인용 단위
  "author_hash": "a_9f21",   // 신설 · 원문 식별 없이 작성자 수만 세기 위함
  "date": "2026-05-02",      // ISO 정규화 (기존 "20260502")
  "kw": "...", "title": "...", "desc": "...", "body": "...",
  "link": "...", "cafe": "..." }
```

`author_hash`는 작성자 문자열의 salted SHA-256 앞 4바이트. 원문 식별자를 저장하지 않는다.

### 2-2. 01 선언 — `known_insights` 신설

```jsonc
{ "known_insights": [ { "id": "ki_01", "text": "러너는 심박을 보려고 워치를 추가로 착용한다" } ] }
```

실무자가 이미 아는 5~10문장. 05에서 임베딩해 09의 `max_sim_to_known` 기준선이 된다. 11에서 확정된 인사이트가 여기에 append되어 다음 세션의 기준선이 자동으로 올라간다.

### 2-3. 05 Pinecone 메타 확장

현재 `{title, desc, kw, cafe, cluster}` 5개 → `{doc_id, persona_id, context_id, dist_centroid, band, dims, author_hash, ...기존}`. 09의 filter 3키(`cluster_id`·`persona_id`·`context_id`)가 옵션이 아니라 **필수**다.

### 2-4. 06 산출 계약

레코드에 `doc_id` · `decision`(auto|escalated|human) · `label` · `reviewed_by` 추가. 사이드카 `classified/{sid}/run_{ts}.json`에 `alpha` · `escalate_threshold` · `calibration` · `ensemble` · `counts`.

**임계값은 사람이 정하지 않는다.** `escalate_threshold`는 목표 오류율 `alpha`에서 계산된 값이다.

### 2-5. 07~11 신설 아티팩트

| 키 | 내용 |
|---|---|
| `clusters/{sid}/result_{ts}.json` | cluster_id · c_tfidf · silhouette · k_scan · bands · dominant_constraint |
| `personas/{sid}/result_{ts}.json` **v2** | persona_id · desire · goals · centrality_top · modularity_q · status |
| `evidence/{sid}/{persona_id}_{ts}.json` | actions · centroid_sentence · evidence[] (relevance/known/rarity/quality + 양쪽 순위) · coverage |
| `cam/{sid}/{persona_id}_{ts}.json` | columns[] (context/action/barrier + grade + cites) · grades 집계 |
| `insights/{sid}/{ts}.json` | insight_id · pain_points · contributing · actions · odi_sum |
| `concepts/{sid}/{ts}.json` | concept_id · service_bullets · experience(문장별 grade) · interviews(stance) · cx_4d |

### 2-6. 계층 ID

```
CL0            클러스터
CL0-P1         페르소나
CL0-P1-A1      Action
d_000123       원문 문서
```

모든 서술은 이 ID로 접지된다. 최종 컨셉의 임의 문장에서 `doc_id`까지 역추적되는 것이 성공 기준 2번이다.

---

## 3. API

신설 라우터 3개, 기존 수정 4개.

| 메서드 | 경로 | 상태 |
|---|---|---|
| POST | `/api/evidence/collect` | 신설 — `{sid, persona_id}` → job |
| GET | `/api/evidence/{sid}/{persona_id}` | 신설 |
| POST | `/api/evidence/search` | 신설 — 09 직접 찾기 (filter 3키 필수) |
| POST | `/api/cam/describe` | 신설 — `{sid, persona_id}` → job |
| GET | `/api/cam/{sid}/{persona_id}` | 신설 |
| POST | `/api/insight/synthesize` | 신설 |
| POST | `/api/concept/generate` | 신설 |
| GET/PUT | `/api/admin/prompts` · `/api/admin/constants` | 신설 |
| POST | `/api/cluster` | 수정 — 산출 스키마 교체 |
| POST | `/api/personas` | 수정 — v2 스키마, 서술 필드 제거 |
| POST | `/api/train` | 수정 — alpha 입력, run 사이드카 |
| POST | `/api/crawl` | 수정 — doc_id/author_hash/ISO date |

모든 장기 작업은 기존 `job_manager` 패턴(`status`/`progress`/`phase`)을 따른다.

---

## 4. 권한

현재 앱에 인증이 없다. 이번 범위에서 인증을 도입하지 않는다.

다만 **어드민 화면(프롬프트 · 파이프라인 상수)은 분석 결과를 바꾸는 행위**라 최소한의 구분이 필요하다.

- 이번 범위: 모든 편집에 **감사 로그**(누가·언제·무엇을·이전값→새값)를 남긴다. `admin/audit/{ts}.jsonl`
- 범위 밖 (미결): 편집 권한을 운영자 단일 역할로 둘지 단계별로 나눌지

세션은 시작 시점의 `prompt_set` 버전과 상수 스냅샷을 붙들고 끝까지 간다. 편집은 다음 세션부터 적용된다.

---

## 5. 열려 있는 결정 — 잠정값으로 시작

전부 어드민 "파이프라인 상수"에 `잠정` 배지로 노출한다. **`잠정`은 "기본값"이 아니라 "실측으로 정해질 값"이라는 뜻이다.**

| STEP | 상수 | 시작값 |
|---|---|---|
| 06 | `alpha` 목표 오류율 | 0.03 |
| 07 | `k_scan_range` | 3–14 |
| 07 | `edge_percentile` | P90 |
| 07 | `combo_rarity_threshold` | 0.60 |
| 09 | `alpha_known_penalty` | 0.50 |
| 09 | `beta_rarity_bonus` | 0.30 |
| 09 | `coverage_min` | 4 / 6 |
| 10 | `lexical_overlap_min` | 0.40 |
| 10 | `speculation_max` | 30% |
| 10-B | `satisfaction_min_n` | 20 |

산식이 아예 없는 것 두 개: **A~F 구역 경계**, **레이더 3축 · 4D-CX 4분면**. 후자는 1.0에도 산출 근거가 문서화되어 있지 않다. 화면에 "산식 없음"으로 명시하고 값은 사람이 배정한다.

---

## 6. 검증한 것

- 15개 아트보드 레이아웃 넘침 **0건** (`.mbody` flex 자식 scrollHeight 검사)
- 대비비: `--ink` 15.6:1 · `--ink-secondary` 6.7:1 · `--ink-subtle` 5.1:1 — 전부 4.5:1 이상
- SVG가 `var(--action)` → `rgb(10,115,181)`로 해석됨을 브라우저에서 확인 (토큰이 차트까지 전파)
- 원시 색 리터럴 0건
