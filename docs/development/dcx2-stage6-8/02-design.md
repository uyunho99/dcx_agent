# 02 · 설계 — DCX 2.0 6~8단계 (클러스터링 · 근거 탐색 · 페르소나 · 인사이트)

- 기준: [`01-brainstorm.md`](01-brainstorm.md) · 결정 원장 [`decision-log.md`](decision-log.md) D-201~
- 0~2단계 설계(저장 · UI 규칙 10절)와 3~5단계 설계 r2(버전 밖 모듈 · 워커 · 로컬 검색 · Known Insight)를 그대로 이어받는다. 여기서는 새로 생기거나 달라지는 것만 적는다.
- 표기: `AC-xx` = 01 수용 기준, `D-2xx` = 결정 기록. 이 문서에서 새로 정한 것은 13절에 모으고 decision-log D-211~로 옮긴다.
- 화면 이름: 기획안의 "아는 얘기"는 화면에서 **Known Insight**로 쓴다(D-135). 버튼은 "Known Insight에 추가".

---

## 1. 전체 구조

```
[프론트 Next.js]  … training ─ 클러스터링(6-A·6-B·6-C) ─ 근거 탐색(7) ─ 페르소나(8 카드 · 맵) ─ 인사이트(8-E · 8-F)
                  공통: KnownInsightsDrawer
        │ REST
[백엔드 FastAPI]
  app/segment/   6단계: 입력 적재 · L1 Ward/K-means · L2 네트워크 모듈성 · L3 LDA · 품질 · 신호 · 6.5 dims 표본 · 초안 · 확정
  app/evidence/  7단계: 쿼리 생성 · 코드 검증 · 필터 검색 · 지연 태깅 · 리랭킹(DPP) · 탭 · novelty · Evidence Package
  app/persona/   8단계: 지표(Importance · Satisfaction · ODI) · 카드(8-A~D) · 등급 판정 · 맵 · 트리 · 8-E · 8-F · 채팅 수정
  app/lexicon/   KNU 감성사전 로더 · 문서 감성 점수
  (재사용) app/vectors · app/known · app/llm · app/work · app/context(versions · stale)
        │
[로컬 디스크 data/]
  sessions/{sid}/versions/vN/segment/     6단계 결과(버전 안) — segment.sqlite · stage_6.json
  sessions/{sid}/versions/vN/evidence/    7단계 결과(버전 안) — queries.json · evidence.sqlite · package.json · stage_7.json
  sessions/{sid}/versions/vN/persona/     8단계 결과(버전 안) — cards.json · map.json · insights.json · concepts.json · chat.jsonl · stage_8.json
  llmcache/{sid}/{prepKey}/               LLM 결과 = 버전 밖 모듈(D-120 원리) — dims-{pver}.sqlite · tag-{pver}.sqlite
```

**원칙 (0~5단계와 같음 + 추가)**
- 판단이 필요 없는 일(군집 · 지표 · 밴드 · 희소성 · 리랭킹 · 등급 판정 · 인용 확인)은 결정론적 코드다. LLM은 쿼리 문장 · 이름 초안 · 태깅 · novelty · 서술 · 처방만 한다.
- LLM 호출은 모두 `app/llm` 레지스트리(`run_task` + Pydantic 출력 스키마)를 쓴다. 백엔드는 설정(D-076, 기본 GPT). 레거시 `call_claude` 경로는 새 세션에서 쓰지 않는다.
- 비싼 LLM 결과(dims · 지연 태깅)는 버전 밖 캐시. 버전을 새로 만들어도 다시 사지 않는다. 사람이 확정한 이름 · Desire는 버전 안(D-209).
- 미결 산식 · 튜닝값은 `app/segment/params.py`, `app/evidence/params.py`, `app/persona/params.py` 한곳에 두고, 결과 JSON에 쓰인 값을 같이 남긴다. 미결 산식이 쓰인 수치에는 화면에 "잠정" 배지(D-211).
- 사람 확정은 층마다 막는다: 6-A 이름 전부 → 6-B 열림, 6-B Desire · Goal 전부 → 6-C 열림, 6-C 이름 · 행동 전부 → 7단계 실행 가능(AC-03 · AC-04).

---

## 2. 데이터 모델

### 2.1 `session.json` 추가 키
```jsonc
{
  "segment":  { "status": "none|running|review|done|failed", "params": {…}, "k": {"L1": 5, "suggested": 5},
                "confirm": { "clusters": "3/5", "personas": "0/12", "contexts": "0/31" }, "savedAt": "…" },
  "evidence": { "status": "none|running|done|failed", "contexts": {"done": 12, "total": 31}, "savedAt": "…" },
  "persona":  { "status": "none|running|done|failed", "savedAt": "…" },
  "insight":  { "status": "none|running|done|failed", "revision": 3, "confirmed": ["in_2", "in_4"], "savedAt": "…" },
  "drafts":   { "segment": {…}, "persona": {…} }
}
```
- 확정값(이름 · Desire · Goal · Context 이름 · 행동 요약)과 문서 배정은 `segment.sqlite`에 둔다. 31만 행을 JSON에 넣지 않는다.

### 2.2 `segment/segment.sqlite` (버전 안)
| 테이블 | 열 |
|---|---|
| `docs` | `doc_id` PK · `cluster_id` · `persona_id` · `context_id` · `theta`(배정 Context 확률) · `theta_json`(Persona 안 전체 토픽 분포) · `dist_centroid` · `band`(core/fringe/edge) · `combo_rarity` · `emerging` · `lexical_surprise` · `sentiment`(KNU, −1~1) · `pred_entropy` · `evidence_level` · `source` · `author_hash` · `date` |
| `clusters` | `cluster_id` · `name_draft` · `name` · `keywords_json` · `reps_json` · `metrics_json` · `quality_json` · `channels_json` · `requests_json`(분리 · 병합 요청 메모) · `confirmed_at` |
| `personas` | `persona_id` · `cluster_id` · `name_draft` · `name` · `desire_draft` · `desire` · `goals_draft_json` · `goals_json` · `centrality_json`(상위 16) · `network_json`(노드 · 엣지, 화면용 상위 60) · `similar_json`(다른 클러스터 Desire 유사 배지) · `reps_json` · `confirmed_at` |
| `contexts` | `context_id` · `persona_id` · `name_draft` · `name` · `action_draft` · `action` · `keywords_json` · `dominant_constraint` · `dims_summary_json` · `quality_json` · `flags_json`(반례 · 문서 부족 · 미분화 후보) · `centroid`(BLOB float32) · `confirmed_at` |
| `combos` | `pair`(tg_rc / env_ar) · `a_code` · `b_code` · `count` |
| `codes` | `dim` · `code` · `label`(대표 문구) · `count` — dims 자유 문구의 정규화 코드(3.6) |

### 2.3 버전 밖 LLM 캐시 `llmcache/{sid}/{prepKey}/`
| 파일 | 키 | 값 |
|---|---|---|
| `dims-{pver}.sqlite` | `doc_id` | `context_dims{environment, internal_state, task_goal, activity_response, resource_constraint}`(각 문구 또는 null) · `origin`(sample/lazy) · `model` |
| `tag-{pver}.sqlite` `tags` | `doc_id` | `relevant` · `reason_code` · `polarity` · `pain_point{text, quote}` · `unmet_need` · `situation` · `artifacts[]` · `quotes[]` · `model` |
| `tag-{pver}.sqlite` `known` | `(doc_id, ki_id)` | `match` 0/1 · `model` |
- `pver` = 프롬프트 파일 해시. 프롬프트를 바꾸면 새 캐시. Known Insight를 추가하면 그 `ki_id`에 대해서만 캐시된 문서를 다시 판정하고, 삭제하면 행을 지운다(D-212).

### 2.4 Evidence Package `evidence/package.json` (7 → 8의 유일한 계약)
기획안 10절 스키마를 따르되 다음을 확정한다.
```jsonc
{ "schema": "evidence-package/1", "version": "v2", "params": {…},
  "personas": [{
    "persona_evidence": { "cluster_id", "persona_id", "persona_name", "desire", "goal": [],
      "desire_support": [{ "doc_id", "source", "quote": {"field","idx","start","end","text"}, "tags": [] }],
      "artifacts": [{ "name", "mention_count" }],
      "metrics": { "importance", "satisfaction", "odi", "doc_count", "author_count", "provisional": ["odi","importance","satisfaction"] },
      "quality": { "cohesion", "boundary", "stability_ari" } },
    "context_evidence": [{ "context_id", "context_name", "action", "situation": {"state","emotion","barrier"},
      "situation_origin": "dims|tag", "dominant_constraint", "keywords": [],
      "metrics": { …, "quality": {"cohesion","boundary","stability","npmi"} },
      "evidence": [{ "doc_id", "source", "quote", "tags", "polarity", "novelty", "known_match", "tab": ["all","new"], "role": "support" }],
      "counter_evidence": [ … "role": "counter" ], "rare_evidence": [ …, "dist_centroid", "combo_rarity", "role": "rare" ],
      "flags": ["counter_context", "few_docs", "undifferentiated_candidate"] }]
  }] }
```
- `quote.field` ∈ `title|body|comment`, `idx` = 댓글 순번(0부터, 본문 · 제목은 null), `start/end` = 원문 문자 위치. 원문 = 크롤 문서의 `title` · `body` · `comments[].text`(벡터용 2,000자 자르기 전, D-213).
- `trace`는 8단계가 채운다(근거가 어느 필드를 지지하는지는 8단계 서술이 생긴 뒤에 알 수 있다).

### 2.5 8단계 저장 (`persona/`)
- `cards.json`: Persona별 카드(4.2), `map.json`: Opportunity Map 점 · 기준선 · 구역(6.4), `tree.json`: 제품 → Cluster → Persona → Context.
- `insights.json` · `concepts.json`: `{revision, items, history: [{revision, at, by: "generate|chat", message}]}`. 이전 판은 `history`에 통째로 남기고 "이 판으로 되돌리기"가 가능하다(MODIFIED_DATA 역할, D-208).
- `chat.jsonl`: 인사이트 화면 채팅 기록.

---

## 3. 6단계 · 구획 (묶음 ①)

### 3.1 입력
- 5단계 `exportRef`(relevant.jsonl = Core + Supporting) 문서 · 3단계 벡터(`derivedRef`) · 3단계 토큰(`tokens/`) · 라벨 `tagProbs`.
- 제외하고 센다: 0벡터(`ids.jsonl failed`) · 토큰 0개. `stage_6.json`에 잘림(벡터 텍스트 2,000자 초과) 문서 수 · 0벡터 제외 수 · 채널별 문서 수.
- 옛 세션(`derivedRef` 없음): 기존 `services/clustering.py` 경로를 열람 전용으로 둔다(3~5단계 규칙과 같음).

### 3.2 L1 Cluster (D-205)
1. 벡터를 L2 정규화한다.
2. 표본(기본 20,000건, 층화 없이 무작위 · 시드 고정)으로 Ward 연결(`scipy.cluster.hierarchy.linkage`)을 만들어 덴드로그램 요약(상위 30 병합)을 저장한다.
3. 같은 표본에서 k = 3~8(Granularity 규약)마다 K-means를 돌려 실루엣 · 관성(Elbow)을 계산한다. 제안 k = 실루엣 최대.
4. 전체 문서에 K-means(문서 10만 건 이하 `KMeans(n_init=10)`, 초과 `MiniBatchKMeans(batch=4096, n_init=5)`), 시드 고정.
5. 키워드 = 클러스터별 c-TF-IDF(명사 토큰, 상위 10). 대표 원문 = 센트로이드에 가장 가까운 5건.
- 6-A에서 사람이 k를 바꿔 L1만 다시 돌릴 수 있다("k 바꿔 다시 나누기"). 이때 L2 · L3 · 확정값이 지워진다는 확인을 받는다.

### 3.3 L2 Persona (1.0 Actor, D-204 · D-206)
1. 클러스터 안 문서의 명사 토큰에서 문서빈도 상위 300개 어휘를 고른다(불용어 · 제품명 `bk`는 제외).
2. 같은 문서에 함께 나온 횟수로 가중 무방향 그래프를 만든다. 가중치 하위 엣지는 문서 수 0.5% 미만이면 버린다.
3. Louvain 모듈성 분할(`networkx.community.louvain_communities`, 시드 고정, resolution 1.0).
4. 공동체를 Persona로 만든다. Granularity(클러스터당 2~3):
   - 4개 이상이면 가장 작은 공동체를 엣지 가중합이 가장 큰 이웃 공동체에 합치기를 반복한다.
   - 1개면 resolution을 1.2 → 1.5 → 2.0으로 올려 다시 나눈다. 그래도 1개면 Persona 1개 + `flags: few_communities`.
5. 문서 배정: 문서의 명사 집합과 공동체마다 겹치는 어휘의 centrality 합이 가장 큰 공동체. 겹침이 없으면 그 클러스터에서 가장 큰 Persona(배정 사유 `fallback` 기록, 비율을 `stage_6.json`에).
6. Persona마다 공동체 부분 그래프의 Eigenvector centrality 상위 16개(최댓값 = 1로 정규화). 정규화 방식은 잠정(D-211).
7. 클러스터 간 Desire 유사: Desire 초안 문장을 임베딩해 다른 클러스터 Persona와 코사인 ≥ 0.85면 `similar_json`에 배지만 남긴다(D-206).

### 3.4 L3 Context (1.0 Action/LDA)
1. Persona 안 문서의 토큰(명사 · 동사 · 형용사 어간)으로 gensim `Dictionary`(no_below=3, no_above=0.5)와 BoW를 만든다.
2. 토픽 수 2~4(Granularity Context 2~4)마다 `LdaModel(passes=10, random_state 고정)`을 학습하고 C_v Coherence · Perplexity를 계산한다. 선택 = C_v 최대(동점이면 작은 수). 기획안의 2~10 스캔은 표시용으로 2~10 값을 같이 저장한다. L3 k 결정은 잠정(D-211).
3. 문서 수가 30건 미만인 Persona는 LDA를 돌리지 않고 Context 1개 + `flags: few_docs`.
4. 문서 배정 = θ 최대 토픽(`context_id`), `theta` = 그 확률. Importance가 이 θ를 쓴다(D-204).
5. Context 센트로이드 = 배정 문서 Voyage 벡터 평균(정규화). `dist_centroid` = 1 − cos(문서, 센트로이드). 밴드: Context 안 P50 이하 core, P50~P90 fringe, P90 초과 edge(D-214).
6. 반례 Context 표시(`counter_context`): 소속 문서 평균 KNU 감성이 Persona 평균보다 낮고(−0.2 이하 차이) 문서 수가 Persona의 15% 미만인 Context. 표시만 하고 Granularity 하한 예외로 남긴다.

### 3.5 품질 · 신호 (기획안 3절 · 8절, 1.0 재현성 제외)
| 지표 | 층 | 계산 |
|---|---|---|
| Cohesion | L1 · L3 | 문서와 센트로이드 평균 코사인. 0.6 미만 → "분리 검토" 배지 |
| Boundary | L1 | 표본 실루엣 음수 비율. 15% 초과 → "경계 검토" |
| Stability ARI | L1 · L2 | 80% 재표집 재군집(L1 5회, L2 3회)과 원래 배정의 ARI 평균. L1 0.7 · L2 0.6 미만 → "불안정" |
| NPMI | L3 | Context 상위 10어휘 쌍의 NPMI 평균(말뭉치 = 그 Persona 문서) |
| 채널 분포 | L1 | `source` 비율, 한 채널 80% 이상 → "한 채널 편중" |
| `pred_entropy` | 문서 | 5단계 값을 그대로. 단 라벨 경로의 0 고정을 고친다(3.8) |
| `emerging` | 문서 | 수집 기간 최근 20% 구간에서 빈도가 이전 구간의 3배 이상인 어휘(전체 빈도 5 이상)를 포함하면 그 어휘들의 증가율 최댓값을 0~1로. 잠정 |
| `lexical_surprise` | 문서 | 문서 안 TF-IDF 상위 어휘 중 클러스터 c-TF-IDF 순위가 하위 50%인 어휘의 비중. 잠정 |
| `sentiment` | 문서 | KNU 감성사전 토큰 극성 평균(−1~1). `app/lexicon/` |
- 지표는 진단만 한다. 분리 · 병합은 실행하지 않고 "분리 요청" 메모만 남긴다(AC-02).

### 3.6 6.5 · Core dims 표본 추출과 조합 희소성 (D-207 · D-215)
1. Context마다 `evidence_level = core` 문서를 θ 순으로 최대 100건 고른다.
2. LLM `segment.dims`(10건씩 묶음): 원문(제목 · 본문 · 댓글 앞부분)에서 **관측된 것만** 5키를 짧은 명사구(12자 이내)로, 없으면 null. 결과는 `dims-{pver}.sqlite`에 캐시.
3. 자유 문구를 세기 위해 코드로 정규화한다: 차원별로 문구를 임베딩해 코사인 ≥ 0.85끼리 탐욕 묶음 → `codes`(대표 문구 = 가장 흔한 문구). 예: "정수기 온도 고정" · "정수기 온수 온도가 안 바뀜" → 한 코드.
4. 조합 빈도: (task_goal, resource_constraint) · (environment, activity_response) 쌍의 공출현 수를 `combos`에 센다(표본 기준).
5. `combo_rarity` = 두 쌍 각각의 −log(쌍 빈도 + 1 / 표본 수)를 세션 안 min-max한 값 중 큰 쪽. 표본 밖 Core는 7단계 지연 추출 때 같은 코드표 · 빈도표로 계산한다(새 코드는 빈도 0으로 본다). 임계는 분포 확인 후(잠정).
6. Context 요약: `dominant_constraint` = 가장 흔한 resource_constraint 코드 대표 문구, `dims_summary` = 차원별 상위 3 코드, "목적 · 제약이 빈 Core 비율".
7. 구조 충실도 추적(기획안 5절): Core마다 채워진 키 수 · 목적 · 제약 유무 기록. Act 태그 ↔ activity_response 불일치 플래그(라벨 sem.act ≥ 0.5인데 activity_response null, 또는 그 역)를 `stage_6.json`에 건수로.

### 3.7 초안 생성 (LLM)
| 작업 | 입력 | 출력 | 호출 수 |
|---|---|---|---|
| `segment.cluster_name` | 0단계 `oneLiner` · c-TF-IDF 10 · 대표 원문 5 | 이름 초안(15자 이내) | 클러스터당 1 |
| `segment.persona_draft` | `oneLiner` · `targetScope`(힌트, D-210) · centrality 16 · 대표 원문 5 · 클러스터 이름 | Persona 이름 · Desire 1문장 · Goal 1~3 | Persona당 1 |
| `segment.context_draft` | LDA 상위 10어휘 · 대표 원문 5 · `dominant_constraint` · Persona Desire | Context 이름 · 행동 요약 1문장 | Context당 1 |
- 초안은 `*_draft`에 저장되고 화면 입력칸을 채운다. 사람이 "확정"을 눌러야 `name/desire/...`에 들어간다. 초안을 그대로 확정해도 된다.

### 3.8 5단계 보정 (기획안 11절 "코드 수정")
- `model/export.py`의 라벨 경로 `pred_entropy=0.` → 라벨 `tagProbs`로 등급 확률(`rule.grade_probs`)을 계산해 엔트로피. 사람 라벨은 0 유지. 기존 내보내기는 그대로 두고 새 내보내기부터 반영(5단계 결과를 다시 만들 필요 없음: 6단계가 `tagProbs`로 같은 값을 계산해 `docs.pred_entropy`에 쓴다).

### 3.9 `stage_6.json`
```jsonc
{ "input": { "relevant": 93210, "zero_vector": 12, "no_tokens": 40, "truncated": 18044, "by_channel": {…} },
  "L1": { "k": 5, "suggested": 5, "silhouette": {"3":0.08,…}, "inertia": {…}, "sample": 20000 },
  "clusters": [{ "id":"CL0", "docs":1240, "cohesion":0.71, "boundary":0.09, "ari":0.78, "channels":{…}, "channel_skew":false }],
  "personas": [{ "id":"CL0-P1", "docs":45, "ari":0.66, "fallback_assign":0.04 }],
  "contexts": [{ "id":"CL0-P1-C1", "docs":11, "cohesion":0.68, "npmi":0.12, "topics_scanned":{"2":0.41,…}, "flags":[] }],
  "bands": { "core":0.5, "fringe":0.4, "edge":0.1 },
  "dims": { "sampled": 3100, "empty_goal_or_constraint": 0.18, "act_mismatch": 42, "codes": {…} },
  "llm_calls": { "cluster_name":5, "persona_draft":12, "context_draft":31, "dims":310 },
  "params": {…}, "at": "…" }
```

### 3.10 화면 6-A · 6-B · 6-C (`/pipeline/clustering`, 하위 탭 3개)
```
6-A Cluster                                              [k: 5 ▾ 다시 나누기] [6-B로 →](primary, 이름 전부 확정 시)
┌ 덴드로그램 요약 · 실루엣/Elbow 미니 차트 (k 제안 근거) ┐
├ CL0 [러닝 중 착용 · 측정        ] 문서 1,240  [확정]
│     응집 0.71 · 경계 9% · 안정 0.78     채널 카페 52 · 유튜브 31 · 더쿠 17
│     키워드 #러닝 #심박 …   대표 "러닝할 때 워치랑 이어폰 둘 다…" [더 보기]   [분리 요청]
├ CL1 [통화 · 마이크 품질] 문서 860   채널 카페 88 ⚠ 한 채널 편중
└ 이름 3/5 확정
6-B Persona (클러스터 선택 → 그 안 Persona 2~3)
  [어휘 네트워크(상위 60노드, 공동체 색)]  centrality 심박 0.81 · 워치 0.78 …
  CL0-P1 이름[ ] Desire[ 운동 중 몸 상태를 최소한의 기기로 확인받고 싶다 ] Goal 1.[ ] 2.[ ] [+]  근거 45건 · 대표 원문 3 [보기]  [확정]
  ⇄ CL2-P1과 Desire 유사 0.86 (통합은 지원하지 않음 · 기록만)    초안 힌트: 0단계 대상 선언
6-C Context (Persona 선택 → Context 2~4)
  C1 이름[기기 중복 착용의 번거로움] 행동[러닝 중 워치와 이어팟을 함께 착용] 주된 제약: 손목·귀 동시 착용 부담  문서 11 [확정]
  C3 … ⚠ 반례    C? ⚠ 문서 부족(23건 · Context 1개)
  Core 중 목적 · 제약 빈 비율 18%   [근거 탐색 실행](primary, 전부 확정 시)
```
- **일괄 확정 (디자인 리뷰 3A, D-224):** 6-C는 Persona를 고르면 그 Persona의 Context 2~4개가 한 화면에 모두 펼쳐지고, 아래에 "이 Persona의 Context 모두 확정" 버튼이 있다(개별 확정 버튼도 유지). 반례 · 문서 부족 Context가 섞여 있으면 버튼 옆에 "반례 1개 포함" 같은 경고를 보인다. 세션 전체 일괄 확정은 두지 않는다. 6-A · 6-B는 개별 확정만.
- 하위 탭은 앞 층이 확정돼야 열린다(잠긴 탭은 이유 툴팁). 저장은 확정 버튼마다 즉시, 입력 중 내용은 `drafts.segment`로 임시 저장(0~2단계 규칙).

---

## 4. 7단계 · 근거 탐색 (묶음 ②)

### 4.1 쿼리 생성 (LLM `evidence.queries`, Persona당 1회)
- 입력 헤더: `oneLiner`. 본문: Persona 이름 · Desire · Goal · Artifact 후보(키워드) · Context 목록 행 `{context_id} · {action} · 주된 제약: {dominant_constraint} · 키워드: …`.
- 출력: `persona_query { desire_check: [2문장], artifact: [1문장] }`, Context마다 `context_query { Sense, Feel, Think, Act, Relate, Outcome, Counter, Residual }`(소비자 1인칭 문장) · `anchor_context_ids[]`.
- 코드 검증(기획안 6절): (a) `anchor_context_ids` 합집합 = Persona의 Context 전체 (b) Context마다 8키 모두 비어 있지 않음 (c) 금지어 정규식 `페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은` 없음 (d) 미달이면 부족 항목을 적어 1회 재생성 → 그래도 미달이면 해당 Context에 대체 쿼리(Context 이름 + 키워드)를 쓰고 `query_gen_fail` 기록.

### 4.2 후보 검색 (로컬, D-202)
- 질의 임베딩: Voyage `input_type="query"`(문서는 3단계 `document`). 가짜 임베더는 구분 없음.
- 허용 집합(필수 필터): `segment.docs`에서 `context_id = C`(persona_query는 `persona_id = P`). 필터 없는 검색 함수는 이 모듈에서 부르지 않는다(AC-06, 테스트로 고정).
- 선택 필터: task_goal · resource_constraint 코드(dims가 있는 Core에만 적용 가능, 기본 끔).
- Counter 쿼리만 허용 집합을 `core ∪ supporting` 그대로 두고, 나머지 쿼리는 같은 집합에서 Core를 0.05 가산(Core 우선, 완전 제외는 하지 않음).
- Context마다 8쿼리 각 top 15 → 합집합 · 중복 제거 → relevance(쿼리별 코사인 최댓값) 상위 M = 50. 문서마다 걸린 쿼리 차원을 기록한다.

### 4.3 지연 태깅 (LLM `evidence.tag`, 미캐시 후보만, 8건씩 묶음)
- 입력: 문서별 제목 · 본문(앞 1,500자) · 댓글(번호 붙여 앞 10개, 각 300자) · 채널 · `context_dims`(있으면) · Known Insight 목록(`#1` 문장 / `#2` 넘긴 원문 요약 200자).
- 출력(문서별): `relevant` · `reason_code`(relevant=false일 때 `ad|no_needs|pure_criticism|other`) · `polarity`(−1~1) · `pain_point{text, quote}` · `unmet_need` · `situation{state, emotion, barrier}`(**dims가 없을 때만**, 기획안 9절 ①) · `context_dims`(Core인데 dims가 없을 때만, D-207) · `artifacts[]` · `known_match`("#k" | "none") · `quotes[{field, idx, text}]`.
- 6차원 태그는 출력하지 않는다(4단계 값 사용, 기획안 9절 ④).
- 코드 후처리: `quotes[].text`를 원문에서 공백 정규화 후 정확히 찾아 `start/end`를 채운다. 못 찾으면 `verified: false`(8단계 등급 하향, D-213). `situation`은 dims가 있으면 매핑으로 채운다(state ← environment + task_goal, emotion ← internal_state, barrier ← resource_constraint).
- 되먹임: `relevant=false` 건수 · `reason_code` 분포 · Act 불일치 건수를 `stage_7.json`에 남기고, 라벨링 화면에 "7단계에서 무관 판정 N건 — 4단계 재점검 참고" 배너를 띄운다(자동 재판정 없음).

### 4.4 리랭킹과 선택
- 대상: `relevant = true` 후보.
- `quality = relevance × (1 + w_r · combo_rarity)`, `w_r = 0.3`(잠정). 아는 얘기 감점 없음(기획안 7절).
- 다양성 커널: `S_ij = exp(−(1 − cos_ij)² / σ²)`, σ = 0.3(잠정). `L = diag(quality) · S · diag(quality)`.
- DPP 탐욕 MAP(Chen et al., 2018 빠른 탐욕 알고리즘)로 10건 선택.
- Coverage: 선택 세트의 6차원 태그(`tagProbs ≥ 0.5`) 합집합 / 6이 4/6 미만이면 빠진 차원의 쿼리로 후보를 15건 더 가져와(1회) 다시 선택.
- rare 정의: `band = edge` ∧ `relevant` ∧ (`pain_point` 있음 ∨ `unmet_need` 있음). DPP 결과에 rare가 2건 미만이고 후보에 rare가 남아 있으면, quality가 가장 낮은 비rare를 quality가 가장 높은 rare로 바꾼다(fallback, 발동 횟수 기록).
- Representative Richness(태그 수 0~6)는 카드 표시 · 동점 처리에만 쓴다.

### 4.5 전체 / 새 발견 탭
- **전체 탭:** 4.4 선택 결과. Known Insight와 겹치는 원문에는 "Known Insight #2와 같은 내용" 배지.
- **새 발견 탭:** 후보에서 ⓐ Known Insight로 넘긴 `doc_id` ⓑ `known_match ≠ none` ⓒ 넘긴 원문과 코사인 ≥ 0.95 를 뺀 뒤 4.4를 다시 적용. 10건 미만이면 relevance 다음 순위 50건을 더 가져와 태깅 · 판정(최대 3회). "N건이 Known Insight와 같아 빠졌습니다 → 전체 탭에서 보기".
- 기본 탭: Context 근거(경험 가설 · Residual) = 새 발견, Persona Desire 근거 · 반례 = 전체(기획안 7절).
- 화면에서 "Known Insight에 추가"를 누르면 기존 Known Insight API로 저장되고(`origin: rag`), 그 Context의 새 발견 탭만 즉시 다시 계산한다(LLM 재호출 없음: 넘긴 원문 · 코사인만 바뀜). 문장형 Known Insight를 추가하면 그 항목에 대해 캐시 문서 `known` 판정을 다시 돈다(D-212).

### 4.6 novelty 교차 확인 (LLM `evidence.novelty`, Context당 1회)
- 입력: 새 발견 탭 최종 10건 + Context 대표 Core 5건(센트로이드 최근접) + Known Insight 목록.
- 출력: 문서별 `novelty ∈ {none, low, medium, high, very_high}` + 한 줄 이유. `high` 이상이 "새 발견" 표시(잠정 임계).
- 전체 탭에만 있는 문서는 `novelty: null`.

### 4.7 에스컬레이션 · 반례 · Evidence Package 조립
- 미분화 Context 후보: 한 Context의 rare 후보 중 서로 코사인 ≥ 0.8로 묶이는 무리가 3건 이상이면 `undifferentiated_candidate` 플래그 → 6-C 해당 Context에 "새 Context 후보 — 원문 3건" 표시(생성은 하지 않음).
- `counter_evidence` = Counter 쿼리로 걸린 relevant 문서 중 polarity가 Context 평균보다 0.3 이상 낮은 것 상위 5. `rare_evidence` = rare 후보 상위 5(선택 여부 무관).
- `desire_support` = persona_query 결과 상위 5(전체 탭 규칙), `artifacts` = Persona 소속 태깅 문서 `artifacts[]` 집계(이름 정규화 = 소문자 · 공백 제거).
- metrics(Context): `importance` = Σθ(배정 문서) / 그 Persona 문서 수 → 세션 안 min-max, `satisfaction` = 문서 KNU 감성 평균을 0~1로 바꾼 뒤 세션 안 min-max, `odi` = I + max(I − S, 0)(잠정), `doc_count`, `author_count` = 문서 작성자 `author_hash` 중복 제거 수(댓글 작성자 제외, D-216). Persona metrics = 소속 Context의 문서 수 가중 평균(잠정).
- 1.0 장표 수치와 절대값은 비교하지 않는다(벡터 · 토큰화가 다름) — 화면 설명 문구에 한 줄.

### 4.8 `stage_7.json`
기획안 11절 항목 그대로: Context별 Coverage(x/6) · 보충 검색 발동 수 · 밴드별 노출 비율 · novelty 분포 · 에스컬레이션 후보 · `relevant=false` 건수와 `reason_code` · `query_gen_fail` · 탭별 건수 · `known_match` 분포 · 새 발견 확장 횟수 · rare fallback 횟수 · 지연 dims 추출 수 · LLM 호출 수 · 캐시 적중 수. 기획안의 "A–C 일치율"은 로컬 Re-ranker를 범위에서 뺐으므로(01 6절) 없음.

### 4.9 화면 7 (`/pipeline/evidence`)
```
[페르소나 생성](primary, 7단계 완료 시)
왼쪽: Persona 목록(클러스터별 묶음 · 진행 상태 배지, D-227) → 고른 Persona의 Context 목록(C1~C4, Coverage 5/6 · 새 발견 8 · ⚠ 미분화 후보)
오른쪽: CL0-P1-C1 기기 중복 착용      [ 전체 10 | 새 발견 10 ]   쿼리 보기 ▸(8문장 · 실패 표시)
  새 발견 · Known Insight와 같아 7건 빠짐 → 전체 탭에서 보기
  1 “러닝 크루에선 다 워치 차서 이어팟만…”  [더쿠 · 댓글 3] [Feel] [rare] [새 발견 high]   [Known Insight에 추가]
  2 “심박 보려고 멈추면 페이스가 무너져요”    [네이버 카페 · 본문]
  ── 반례 2 · 희소 3 (접힘)
  Persona 근거(Desire 검증 5 · Artifact) 접힘
```
- 카드 = 기존 `SourceCard` 확장: 인용 구간 하이라이트, 채널 배지, 위치(본문 / 댓글 n), 차원 태그, 밴드, novelty.
- **실행 중 열람 (디자인 리뷰 2A, D-223):** Context 목록 행마다 상태 배지 `완료 · 진행 중 · 대기 · 실패`. 완료 행은 실행 중에도 열리고 "Known Insight에 추가"가 된다. 추가한 항목은 아직 안 돈 Context 판정에 바로 들어가고, 이미 완료된 Context는 그 행에 "Known Insight가 바뀌었습니다 · 새 발견 다시 계산" 버튼이 붙는다(4.5 재계산, LLM 재호출 없음). "페르소나 만들기"는 전부 완료(또는 실패 행을 건너뛰기로 확정)될 때까지 잠긴다.

---

## 5. 8단계 · 페르소나 (묶음 ③)

### 5.1 원칙 (기획안 8단계)
- 페르소나 수 · 경계 · 이름 · Desire · Goal은 6단계 확정값을 **그대로 표시**한다. 8단계는 다시 만들지 않는다(AC-10).
- 서술 단위는 Context이고 문장은 "이 Context에서 이런 담론이 관측된다"로 쓴다. 근거 인용과 반례는 필수 동반.
- 입력은 Evidence Package 하나. 0단계 `targetScope`는 8-A · 8-C 프롬프트에 넣지 않는다(D-210). 사내 제약 · 핵심 지표 · 분석 목적은 8-D 처방 프롬프트에만.

### 5.2 페르소나 카드 생성 (LLM `persona.card`, Persona당 1회)
- 입력: `persona_evidence` + `context_evidence[]`(근거 · 반례 · 희소, 인용 문자열 포함, 근거마다 `E1…` 번호).
- 출력(스키마):
  - 8-A Context마다 `state · emotion · barrier` 각 `{text, cite: ["E3","E7"]}` (dims 매핑 값이 있으면 그 값을 다듬기만, `situation_origin`). Action은 6-C 확정값을 그대로 씀(생성 안 함).
  - 8-B `intent{text, basis_context_ids[], reserved_context_ids[]}`.
  - 8-C `usage_context{text, cite}` · `jtbd{text, cite}` · `journey{pre_purchase, purchase, post_purchase}`(비율 합 1 또는 null) · `sensitivity{price, brand, feature}` ∈ 상/중/하/null · `values` · `decision_style` (근거 부족 시 null).
- 생성 실패(스키마 불량 2회) → 그 Persona 카드 `failed`, 다른 Persona는 계속.

### 5.3 인식론 등급 (코드 판정, D-213)
| 등급 | 조건 |
|---|---|
| 🟢 관측 | `cite`가 가리키는 근거 중 하나 이상의 인용이 `verified` 이고, 그 근거의 `pain_point` · `situation` · 인용 문장에서 온 필드(state · barrier · usage_context) |
| 🟡 추론 | `cite`는 있으나 인용이 미확인이거나, 필드 성격이 유도(emotion · jtbd · unmet_need 기반) |
| 🔴 추측 | `cite` 없음 · 존재하지 않는 근거 번호 · 8-B intent(항상) · 8-F 합성 프로필(항상) |
- Traceable Support = Context 안 `cite`가 유효한 필드 비율. 0.5 미만이면 그 Context 필드 등급을 한 단계씩 낮춘다(잠정 임계). `trace[]`를 Evidence Package 형식으로 카드에 저장.
- 8-B에는 "의도 ≠ 행동" 경고 고정 문구.

### 5.4 8-D 처방과 스코프 대조
- `persona.prescribe`(Persona당 1회): 입력 = 카드 요약 + `analysisGoal` · `keyMetrics` · `constraints`. 출력 = `{direction, target_metric, contribution(1문장), journey_hypothesis(ENTRY→EXPAND→COMMIT 가설)}`.
- 제약 검사 `persona.constraint_check`: 처방 × 사내 제약 목록 → 제약마다 `ok | violates | review` + 이유. `violates`가 있으면 그 이유를 붙여 1회 재처방, 그래도 위반이면 처방을 "차단됨"으로 표시하고 이유를 보인다.
- 스코프 대조 `persona.scope`: 0단계 `targetScope` · `productCategory` · `positioning` vs 카드 요약 → `in | outside` + 이유. `outside`면 헤더에 `[FUTURE]`. 이 호출은 카드 생성과 분리된 별도 호출(생성 오염 방지).

### 5.5 Opportunity Map · 트리
- 점 = Context(I, S). **표기 (디자인 리뷰 4A, D-225):** 클러스터 = 점 모양 5종(원 · 사각 · 삼각 · 마름모 · 오각, 클러스터가 6개 이상이면 6번째부터 원 + 클러스터 ID 라벨), Persona = 같은 모양 안에서 명도 3단계(`--ink-strong` · `--ink` · `--line-strong`), 선택하거나 범례 칩으로 고른 Persona만 `--blue`. 반례 Context = 속 빈 모양. 범례 칩(클러스터 → Persona 2단)을 눌러 켜고 끈다. 색만으로 구분하지 않는다. 페르소나 화면의 "전체 맵" 보기(D-222).
- 기준선(1.0 코드): 가로 S = 0.5, 사선① (0, S평균) → (1, 1), 사선② (I평균, 0) → (1, 1). 구역: 사선① 위 = Overserved(A Exciting · D Forgiven), 사선② 아래 = Underserved(C Competitive · F At-risk), 사이 = Well-served(B Experiencing · E Dangling), 가로선이 위아래(A/B/C 위, D/E/F 아래).
- **Context 표 (디자인 리뷰 5A, D-226):** 맵 아래에 ID · 이름 · Persona · 중요도 · 만족도 · 기회 · 구역 · ★ 열의 표(기본 기회 내림차순, 열 머리 눌러 정렬). 표 행에 포커스 · 호버하면 맵의 점이 강조되고, 점을 누르면 표 행이 강조된다. 행의 "카드 열기"로 Persona 카드로 간다. SVG에는 `role=img` + 요약 `aria-label`(구역별 Context 수)만 두고, 키보드 · 낭독기는 표를 쓴다.
- 마커: `novelty high 이상 근거가 2건 이상` ∧ `odi ≥ 세션 평균` → ★ "몰랐고 기회도 큰 지점".
- 산식이 잠정인 값(ODI · Persona 집계)은 축 · 툴팁에 "잠정".
- SNAGraph는 제품 → Cluster → Persona → Context 3층 트리로 바꾼다(새 `HierarchyTree` 컴포넌트, 노드 크기 = 문서 수). 어휘 네트워크는 6-B로 옮겼다.

### 5.6 8-E 인사이트 (LLM `insight.derive`, 세션당 1회 + 채팅 수정)
- 입력: 모든 카드의 Context 요약(8-A 행 · pain point 인용 1~2개 · Context ID · ODI) + Known Insight 목록.
- 출력: 인사이트 3~8개 `{id, title, pain_point(2~3줄), context_ids[], known_ki_id | null}`.
- 코드 계산:
  - 레이더(Computed · Connected · Shared): 축 대표 문장 3개("맞춤형 서비스가 필요해" · "실시간으로 직접 보고 싶어" · "함께 즐기고 싶어", 설정값)를 임베딩해 Context 센트로이드와 코사인 절댓값 → 인사이트 = 소속 Context의 문서 수 가중 평균. 원값과 세션 안 상대 위치(백분위)를 함께 표시(기획안 미결 3의 ② — 잠정 방식).
  - Opportunity 막대: 소속 Context ODI 평균, 전체 인사이트 평균선. 평균선 이상만 8-F 기본 대상(사람이 바꿀 수 있음).
  - "새 발견 / 이미 아는 것": `known_ki_id`가 있으면 "Known Insight #k와 같은 내용" 배지.
- 확정: 인사이트마다 "확정" 체크 → `insight.confirmed`. 확정 인사이트는 다음 세션 0단계 Known Insight 서랍에 "이전 세션 추천"으로 보인다(자동 추가 안 함, `origin: prev_session`) (D-217).

### 5.7 8-F 경험 디자인 컨셉 (LLM `insight.concept`, 대상 인사이트당 1회)
- 출력: `persona_profile`(합성 프로필, 항상 🔴 "합성값" 배지) · `basis`("근거 45건 · 작성자 26명에서 종합" — 코드가 채움) · `pain_points[3]`(근거 번호만 고르게 하고 원문 · 채널 · 위치 · Context ID는 코드가 Evidence Package에서 채움) · `journey[{context_id, action, feeling, service, service_action, cx_4d ∈ 정신적|물리적|문화적|시스템}]` · `constraint_check[]`(5.4와 같은 검사 재사용).
- AS-IS 행은 `context_id`가 그 인사이트의 Context 중 하나여야 한다(코드 검증, 아니면 1회 재생성). TO-BE Service는 ⚪ "처방" 표시.
- 4D-CX 분포(정신적 · 물리적 · 문화적 · 시스템 개수)를 표 아래에 표시해 비어 있는 장이 보이게 한다.

### 5.8 채팅 수정 (D-208)
- `POST /insight/{sid}/chat {target: "insights" | "concept:{id}", message}` → LLM `insight.edit`: 현재 판 JSON + 메시지 → 같은 스키마의 수정본. 스키마 · 코드 검증(근거 번호 존재 · AS-IS context_id) 통과 시 새 판으로 저장하고 `history`에 남긴다. 실패하면 "요청을 반영하지 못했습니다. 다르게 말해 주세요." + 현재 판 유지.
- 레이더 · 막대 · 근거 원문 같은 코드 계산 값은 수정본에서 다시 계산한다(LLM이 숫자를 쓰지 않는다).
- 판 목록에서 이전 판 보기 · "이 판으로 되돌리기".

### 5.9 화면
**페르소나 (`/pipeline/personas`) — 두 보기 (디자인 리뷰 1A, D-222)**
- 보기 전환 `[전체 맵 | Persona 카드]`. 들어오면 **전체 맵**이 먼저 보인다: 세션 전체 Context 점 · Persona 색 범례(클릭으로 필터) · ★ 마커 · 오른쪽에 선택한 점의 상세. 점을 누르면 그 Persona 카드로 간다.
- 카드 안에는 맵이 없다. 그 Persona Context의 구역 · 기회 값은 CCM "기회" 행에만 있다.
```
[Persona 목록(왼쪽, 클러스터별 묶음 · FUTURE · 카드 상태 배지, 6-B · 6-C · 7과 같은 자리, D-227)]   [인사이트 도출](primary)
헤더: [FUTURE] CL0-P1 · 귀로 건강 재는 러너   근거 45건 · 작성자 26명 · Context 4개 · 신뢰도 中
      Desire(6-B 확정)  ·  Goal 1. 2.          처방(8-D) · 제약 검사 ✓ ⚠
탭: [8-A CCM] [8-B 수렴] [8-C 속성] [8-D 처방] [구조 트리]
8-A 표: 열 = Context(C3 ⚠ 반례 붉은 열), 행 = Action / Context(🟢 상태 · 🟡 감정 · 🔴 장벽) / Keywords / Artifact / Satisfaction / Opportunity(잠정 · 구역)
      칸 클릭 → 근거 원문 펼침(채널 배지 · 위치 · 하이라이트 · Known Insight에 추가)
```
**인사이트 (`/pipeline/insights`, 기존 `/insights` 대체)**
```
왼쪽 2/3: 인사이트 카드 목록(제목 · pain point · 기여 Context ID 칩 · 레이더 · Known 배지 · 확정 체크)
          Opportunity 막대 + 평균선
          선택한 인사이트 → 8-F: 01 PERSONA(🔴 합성값) · 02 Pain Points(원문 · 채널 · 위치 · ID) · 03 JOURNEY 표 + 4D-CX 분포 + 제약 검사
오른쪽 1/3: 채팅(대상 선택: 인사이트 목록 / 선택 컨셉) · 판 목록
```

### 5.10 `stage_8.json`
카드 수 · 실패 수 · 등급 분포(🟢/🟡/🔴) · null 속성 수 · 제약 위반 · 재처방 · 차단 수 · FUTURE 수 · 구역 분포 · ★ 마커 수 · 인사이트 수 · 평균선 이상 수 · 컨셉 수 · 채팅 수정 판 수 · LLM 호출 수 · 쓰인 잠정 파라미터.

---

## 6. 버전 · 단계 표시

- 사이드바 단계: 시작 · 키워드 · 크롤링 · 전처리 · 라벨링 · 학습 · **클러스터링(6) · 근거 탐색(7) · 페르소나(8) · 인사이트(8-E·F)**. 기존 "임베딩" 단계 표시는 없앤다(D-121로 이미 완료 처리만 남아 있던 것).
- `completedThrough`: 6 = 6-C 전부 확정, 7 = `evidence.status = done`, 8 = 카드 생성 완료, 인사이트 = 8-E 생성 완료.
- "6단계부터 다시" · "7단계부터 다시"를 버전 만들기 선택지에 추가한다. 6부터: `segment/`·`evidence/`·`persona/` 삭제, 확정값 없음(D-209). 7부터: `segment/` 유지(확정값 포함), `evidence/`·`persona/` 삭제. 8부터: `persona/`만 삭제. LLM 캐시(`llmcache/`)는 버전 밖이라 그대로 재사용.
- stale 배너: 앞 단계가 바뀐 버전에서 6~8단계 결과는 "이 결과는 vN의 K단계 기준입니다"(backlog-1 `stale.py` 규칙). 완료 시 `clear_stale` 호출.
- 옛 세션: 기존 클러스터링 · 페르소나 · `/insights` 화면을 열람 전용으로 남긴다.

---

## 7. 워커

- 새 종류(`app/work/worker.py` KINDS): `segment`(3.1~3.9, 단계: 적재 → L1 → L2 → L3 → 품질 → dims 표본 → 초안), `evidence`(Context 단위로 이어 하기), `persona`(Persona 단위), `insight`(8-E 생성 · 8-F 대상별).
- 각 워커는 단계 · Context · Persona 단위 체크포인트를 남겨 중단 뒤 "이어서 진행"이 이미 끝난 단위를 다시 하지 않는다(LLM 캐시 덕에 호출 중복도 없음).
- 버전 만들기 제한: 이 네 워커가 실행 중이면 새 버전을 막는다(3~5단계 규칙 확장).
- 채팅 수정 · 확정 · Known Insight 추가 후 새 발견 재계산은 요청 안에서 동기로 한다(수 초).

---

## 8. API

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /segment/{sid}/run` · `GET /segment/{sid}/status` | 6단계 실행(`{k?}`) · 진행 · `stage_6.json` |
| `GET /segment/{sid}/clusters` · `/personas?cluster=` · `/contexts?persona=` | 층별 목록 · 지표 · 초안 · 확정값 |
| `PUT /segment/{sid}/clusters/{id}` · `/personas/{id}` · `/contexts/{id}` | 확정값 저장(`{name, desire?, goals?, action?, confirm: true}`) — 앞 층 미확정이면 409 |
| `POST /segment/{sid}/personas/{id}/confirm-contexts` | 그 Persona의 Context 일괄 확정(`{contexts: [{id, name, action}]}`, 한 트랜잭션, D-224) |
| `POST /segment/{sid}/requests` | 분리 · 병합 요청 메모 |
| `GET /segment/{sid}/docs?context=&band=` | 층별 원문(대표 · 전체, 페이지) |
| `POST /evidence/{sid}/run` · `GET /evidence/{sid}/status` | 7단계 실행(6-C 전부 확정 전 409) · 진행 · `stage_7.json` |
| `GET /evidence/{sid}/contexts/{id}?tab=all\|new` | 근거 목록 · 반례 · 희소 · 쿼리 |
| `POST /evidence/{sid}/contexts/{id}/refresh-new` | Known Insight 변경 뒤 새 발견 탭 재계산 |
| `GET /evidence/{sid}/package` | Evidence Package |
| `POST /persona/{sid}/run` · `GET /persona/{sid}/status` · `GET /persona/{sid}/cards` · `/map` · `/tree` | 8단계 |
| `POST /insight/{sid}/run` · `GET /insight/{sid}` · `POST /insight/{sid}/concept/{id}` · `POST /insight/{sid}/chat` · `POST /insight/{sid}/revert {target, revision}` · `PUT /insight/{sid}/confirm` | 8-E · 8-F · 채팅 수정 · 되돌리기 · 확정 |
- Known Insight는 기존 `/known/{sid}` API. 오류 응답은 기존 `{status: "error", error: {kind, message}}`.
- 레거시 `/cluster`, `/cluster-refine`, `/persona`, `/sna-data`, `/insight-chat`은 옛 세션 열람용으로 남기고 새 세션에서는 부르지 않는다.

---

## 9. 실패 상태

| 상황 | 동작 | 화면 문구 |
|---|---|---|
| 5단계 결과 없음 | 6단계 실행 409 | "학습 단계에서 결과를 저장한 뒤 클러스터링을 실행하세요." |
| 토큰 없음(3단계 구버전) | 실행 중단 | "형태소 토큰이 없습니다. 3단계 전처리를 다시 실행하세요." |
| 문서 수 부족(<300) | L1 k=3 고정 · 경고 | "문서가 적어(212건) 군집이 불안정할 수 있습니다." |
| Persona 문서 <30 | Context 1개 | 6-C "문서가 적어 Context를 나누지 않았습니다(23건)." |
| 공동체 1개 | Persona 1개 | 6-B "어휘 네트워크가 하나로 묶여 Persona를 나누지 않았습니다." |
| LLM 미연결 · 한도 | 워커 일시 정지 | 3~5단계 문구 재사용 + "이어서 진행" |
| 초안 생성 실패 | 빈 입력칸 | "초안을 만들지 못했습니다. 직접 입력하세요." |
| 쿼리 생성 실패 | 대체 쿼리 | 7 쿼리 보기 "자동 쿼리 생성에 실패해 Context 이름과 키워드로 검색했습니다." |
| 후보 0건 | Context 결과 비움 | "이 Context에서 근거로 쓸 원문을 찾지 못했습니다." |
| 새 발견 0건 | 탭 비움 | "Known Insight를 빼니 남는 원문이 없습니다. 전체 탭에서 보세요." |
| 인용 미확인 | 등급 하향 | 칸 툴팁 "인용 문장을 원문에서 찾지 못해 추론으로 낮췄습니다." |
| 카드 생성 실패 | 그 Persona만 실패 | "이 페르소나 카드를 만들지 못했습니다. [다시 만들기]" |
| 처방 제약 위반 지속 | 처방 차단 | "사내 제약 '의료적 효과 표현 금지'를 지키는 처방을 만들지 못했습니다." |
| 채팅 수정 실패 | 현재 판 유지 | "요청을 반영하지 못했습니다. 다르게 말해 주세요." |
| 워커 비정상 종료 | interrupted | "이어서 진행" |

### 9.1 화면 상태 표
| 기능 | 로딩 | 빈 결과 | 오류 | 성공 | 부분 성공 |
|---|---|---|---|---|---|
| 6단계 실행 | 단계별 진행(적재 → L1 → L2 → L3 → 품질 → dims → 초안) | 문서 0건 → "클러스터링할 문서가 없습니다." | 9절 | 6-A 열림 | 초안 일부 실패 |
| 6-A/B/C 확정 | 저장 중 버튼 비활성 | – | 저장 실패 → 입력 유지 + 재시도 | "확정됨" 배지 · 진행 n/N | – |
| 7단계 실행 | Context별 진행(12/31), 완료 행은 바로 열람(D-223) | – | 9절 | Context 목록 | 일부 Context 실패 → 그 행 "다시 시도" · "건너뛰고 진행" |
| 근거 목록 | 카드 스켈레톤 | 9절 | 검색 실패 | 카드 | 새 발견 < 10 |
| 카드 생성 | Persona별 진행 | – | 9절 | 카드 | 일부 실패 |
| 인사이트 | 생성 중 | 인사이트 0개 → "인사이트를 만들지 못했습니다. 다시 시도하세요." | 9절 | 카드 · 막대 | 컨셉 일부 실패 |
| 채팅 수정 | 응답 대기(입력 잠금) | – | 실패 문구 | 새 판 하이라이트 | – |

---

## 10. UI

- 0~2단계 10절 규칙(Person A Design System · 문구 · 접근성 · 내부용 표시)과 3~5단계 D-137(화면당 파란 주요 버튼 하나)을 따른다.
- 새 공용 컴포넌트: `LayerTabs`(6-A/B/C 잠금 탭), `QualityBadges`, `ChannelBar`, `WordNetwork`(6-B, 기존 `SNAGraph` force 그래프 재사용), `EvidenceCard`(`SourceCard` 확장: 인용 하이라이트 · 위치 · 밴드 · novelty), `GradeMark`(🟢🟡🔴 + 글자 "관측/추론/추측", 색만으로 구분하지 않음), `CCMTable`, `OpportunityMap`(SVG), `HierarchyTree`, `InsightCard`(기존 ds 재사용), `Radar`, `OpportunityBars`, `JourneyTable`, `RevisionList`, `ProvisionalBadge`("잠정").
- 기획안 8단계 문서가 지적한 와이어프레임 불일치를 반영: 상태 · 감정 · 장벽 옆 배지는 인식론 등급, 감도는 상/중/하.
- 목업: [`mockups/index.html`](mockups/index.html) 8화면(6-A · 6-B · 6-C · 7 근거 탐색 · 8 전체 맵 · 8 Persona 카드 · 8-E·F 인사이트 · 상태 모음). Person A 규칙으로 직접 그린 HTML, 예시 데이터는 LG 에어컨.
- 내부용: params 원값 · 캐시 경로 · LLM 호출 수 · 쿼리 원문 · 덴드로그램 원자료.
- 반응형 · 접근성: 최소 1024px. CCM 칸 열기는 칸 안의 버튼(키보드 Enter · Space, `aria-expanded`). 전체 맵은 아래 Context 표가 키보드 · 낭독기 대체(D-226). CCM 표 · JOURNEY 표는 가로 스크롤 대신 Context 열이 4개 넘으면 2단으로 접는다. 키보드: 탭 전환 · 확정 버튼 · 카드 펼침 · 채팅 입력.

---

## 11. 테스트 전략

- **합성 픽스처(D-218):** 군집 구조를 일부러 넣은 데이터 생성기 `tests/fixtures/segment_synth.py` — 5개 방향 가우시안 벡터(1024D) × 클러스터마다 서로 다른 어휘 집합 2~3개(Persona용 공동체) × 공동체마다 토픽 어휘 2~3개(LDA용) + 채널 · 날짜 · 작성자 · 댓글. 기대 구조(k=5, Persona 2~3, Context 2~3)를 테스트가 알고 있다.
- 백엔드 pytest(네트워크 · 키 없이): 임베더 `fake`(질의는 픽스처 어휘 방향으로 매핑하는 테스트용 임베더), LLM `llm/fake.py`(작업 이름별 고정 응답).
  - 6: k 제안 = 5, Persona 2~3 규칙, Context 배정 = θ 최대, 밴드 비율, combo_rarity 단조성(희소 쌍 > 흔한 쌍), 문서 부족 · 공동체 1개 분기, 앞 층 미확정 409, pred_entropy 계산.
  - 6.5: 표본 상한 100, 캐시 적중 시 LLM 0회, 코드 정규화(0.85 묶음).
  - 7: 필터 없는 검색 금지(허용 집합 밖 문서가 절대 안 나옴), 쿼리 검증 (a)~(d) · 재생성 1회 · `query_gen_fail`, 지연 태깅 캐시, 인용 위치 계산 · 미확인 처리, DPP가 같은 문서 중복을 피함, rare fallback, Coverage 보충, 탭 규칙(넘긴 원문 · known_match · 0.95 복붙), 새 발견 확장, Known Insight 추가 후 재계산(LLM 0회) · 문장 추가 시 그 항목만 재판정.
  - 8: Desire · Goal이 6-B 값과 같음, 등급 판정 표 전 경우, Traceable 하향, null 허용, 감도 서수만, 처방 제약 위반 → 재처방 → 차단, 스코프 FUTURE, Opportunity 구역 판정(기준선 경계값), ★ 마커, 레이더 가중 평균, 채팅 수정 판 · 되돌리기 · 코드 값 재계산, AS-IS context_id 검증.
  - 버전: 6/7/8부터 다시 시 삭제 범위 · 캐시 재사용 · stale 해제.
  - 통합: 합성 세션 5단계 결과 → 6 → (가짜 확정) → 7 → 8 → 8-E/F, 외부 호출 0회.
- 프론트 Vitest: 잠금 탭 · 확정 흐름, 근거 탭 전환 · Known Insight 추가, 등급 표시(글자 포함), Opportunity 구역 계산 함수, 판 되돌리기.
- 브라우저 QA: 03-plan에서 정의(합성 세션 · 가짜 백엔드, 실데이터 세션은 사용자 확인 후).
- 의존성 추가: `gensim`, `networkx`, `scipy`(이미 scikit-learn 의존). KNU 감성사전 파일(`app/lexicon/knu_senti.json`).

---

## 12. 묶음 경계 (D-201)

| 묶음 | 포함 절 | 끝났다는 기준 |
|---|---|---|
| ① | 2.1 · 2.2 · 2.3(dims) · 3 · 6(6단계 부분) · 7(segment) · 8(segment) · 9 · 10(6-A/B/C) · 11(6) | AC-01~05 · AC-14 |
| ② | 2.3(tag) · 2.4 · 4 · 7(evidence) · 8(evidence) · 10(7) · 11(7) | AC-06~09 · AC-14 |
| ③ | 2.5 · 5 · 6(8단계 부분) · 7(persona · insight) · 8(persona · insight) · 10(8) · 11(8) | AC-10~14 |
- ③은 2.4 스키마로 만든 가짜 Evidence Package(테스트 픽스처)로 ②와 병행할 수 있다.

---

## 13. 새 설계 결정 요약 (decision-log D-211~)

- D-211 미결 산식 · 튜닝값은 params 모듈 + 결과 JSON 기록 + 화면 "잠정" 배지.
- D-212 Known Insight 판정 캐시는 (문서, 항목) 단위 — 추가 시 그 항목만 재판정, 넘긴 원문 추가는 LLM 재호출 없이 새 발견 탭만 재계산.
- D-213 인용은 원문 기준(제목 · 본문 · 댓글 n, 문자 위치) · 원문에서 정확히 찾지 못하면 `verified: false` → 등급 하향.
- D-214 LDA Context의 센트로이드 = 배정 문서 Voyage 벡터 평균, `dist_centroid` · 밴드 · 레이더가 공유.
- D-215 dims 자유 문구는 임베딩 코사인 ≥ 0.85 탐욕 묶음으로 코드화한 뒤 조합 빈도를 센다.
- D-216 `author_count` = 문서 작성자 `author_hash` 중복 제거(댓글 작성자 제외).
- D-217 확정 인사이트는 다음 세션 Known Insight 서랍에 "이전 세션 추천"으로만(자동 추가 없음).
- D-218 군집 구조를 넣은 합성 픽스처로 6~8단계를 결정적으로 시험한다.
- D-219 사이드바를 클러스터링 · 근거 탐색 · 페르소나 · 인사이트 4단계로 바꾸고 "임베딩" 표시를 없앤다. 버전 만들기에 6 · 7 · 8단계부터 다시를 추가.
- D-220 L2 Persona 문서 배정 = 겹치는 어휘 centrality 합 최대 공동체, 없으면 가장 큰 Persona(사유 기록).
- D-221 LLM 호출은 `app/llm` 레지스트리 + 출력 스키마만(레거시 `call_claude` 미사용).

---

## 14. 디자인 리뷰 (plan-design-review, 2026-10-02)

대상은 이 문서의 3.10 · 4.9 · 5.5 · 5.9 · 9.1 · 10절과 [`mockups/index.html`](mockups/index.html)(8화면). 3~5단계와 같이 Person A 규칙으로 직접 그린 HTML 목업을 쓰고 AI 변형 목업은 만들지 않았다. 외부 의견(Codex · 서브에이전트)은 사용자 선택으로 돌리지 않았다(D2).

### 결정 (6건, 모두 사용자 개별 승인)
| # | 이슈 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | Opportunity Map이 Persona 카드 안 탭이라 세션 전체 비교가 안 됨 | A "전체 맵 \| Persona 카드" 두 보기, 전체 맵 먼저 | 5.5 · 5.9 · D-222 · 목업 s6 · s5 |
| 2 | 근거 탐색 실행 중(수십 분) 화면 미정 | A 끝난 Context부터 열람 · Known Insight 추가, 완료 행 재계산 버튼 | 4.9 · 9.1 · D-223 · 목업 s4 |
| 3 | 6-C 확정 31번 클릭 피로 | A Persona 단위 일괄 확정 + 개별 확정, 반례 포함 경고 | 3.10 · 8 · D-224 · 목업 s3 |
| 4 | 전체 맵 Persona 12개 색 미정 | A 클러스터 = 점 모양, Persona = 명도, 선택만 파랑 | 5.5 · D-225 · 목업 s6 |
| 5 | 맵 점을 키보드 · 낭독기로 못 씀, 점 겹침 | A 맵 아래 정렬 가능한 Context 표, 표↔점 서로 강조 | 5.5 · 10 · D-226 · 목업 s6 |
| 6 | 설계(왼쪽 목록)와 목업(드롭다운) 불일치 | A 왼쪽 Persona 목록(6-B · 6-C · 7 · 8 같은 자리) | 4.9 · 5.9 · D-227 · 목업 s4 · s5 |

### 점검별 점수
| 점검 | 전 | 후 | 남은 것 |
|---|---|---|---|
| 1 정보 구조 | 6 | 8 | 실데이터 길이(긴 이름 · Persona 12개)는 브라우저 QA에서 확인 |
| 2 상태 | 7 | 9 | 문구 · 모양은 브라우저 QA에서 확인 |
| 3 여정 | 6 | 8 | 6단계 실행 대기 중 알림(macOS)은 범위 밖 |
| 4 뻔한 AI 디자인 | 8 | 8 | 새 수정 없음. 인식론 등급은 이모지 대신 모양 + 글자(`GradeMark`) |
| 5 디자인 시스템 | 7 | 9 | 새 컴포넌트 규격은 구현 때 `components/ds/` 규칙 표를 따른다 |
| 6 반응형 · 접근성 | 6 | 8 | 데스크톱 전용(0~2단계 D-069) |

### 뻔한 AI 디자인 점검 (작업 도구 화면 기준)
- 즉시 탈락 패턴: 없음. 카드는 편집 단위(6-B · 6-C)와 선택 단위(인사이트)에만.
- 판정 기준: 브랜드 식별 YES · 시각 중심 하나 YES(층 탭 / CCM 표 / 맵) · 제목만 훑어도 이해 YES · 영역마다 역할 하나 YES · 카드 필요 YES · 모션 없음 · 그림자 없이도 성립 YES.

### 여정 (storyboard)
| 단계 | 사용자가 하는 일 | 느끼는 것 | 설계가 지원하는 것 |
|---|---|---|---|
| 1 | 6단계 실행 → 수 분 대기 | 언제 끝나지? | 단계별 진행 · 예상 시간 · 닫아도 계속 |
| 2 | 6-A 클러스터 이름 확정 | 데이터 감 잡기 | 품질 배지 · 채널 막대 · 대표 원문 · k 근거 |
| 3 | 6-B Desire · Goal 확정 | 핵심 판단, 집중 | 어휘 네트워크 · centrality · 초안 · 유사 배지 |
| 4 | 6-C Context 확정 | 반복 피로 | Persona 단위 일괄 확정(D-224) |
| 5 | 7 근거 탐색 대기 · 먼저 끝난 근거 열람 | 발견의 재미 | 완료 행 열람 · Known Insight 추가(D-223) |
| 6 | 전체 맵 → 카드 → CCM 근거 | 믿을 만한가? | 인식론 등급 · 인용 확인 · 반례 열 |
| 7 | 인사이트 · 컨셉 → 채팅 수정 · 확정 | 쓸 만한 결과물 | 판 목록 · 되돌리기 · 사내 제약 검사 |

### 이전 학습 반영
- `dcx-full-session-save`(2026-09-29): 새 화면은 세션 통째 저장(`/save-session`)을 쓰지 않고 기능별 API + `drafts`만 쓴다(2.1 · 8절).
- `bg-job-stale-window-vs-fetch-duration`(2026-10-01): 6~8단계 워커는 Context · Persona 단위로 하트비트 · 진행을 남겨 긴 LLM 호출 중 "멈춤"으로 오판되지 않게 한다(7절).

### 범위 밖 (이번 리뷰에서 결정하지 않음)
- macOS 알림(6 · 7단계 완료): 세션 목록 작업 배지로 대신한다.
- 다크 테마 · 모바일: 0~2단계와 같음.
- 클러스터 6개 이상일 때 점 모양 확장 방식의 세부(라벨로 대신함, D-225).

### 이미 있는 것 (재사용)
- `components/ds/` 21종(Tabs · Segmented · Badge · Banner · InsightCard · ProgressBar · Table · Skeleton · Popover 등), `SourceCard` · `KnownInsightsDrawer`, `SNAGraph`(force 그래프 → 6-B 어휘 네트워크), `ChatPanel`, `usePolling`, `StepBar` · `completedThrough`(backlog-1), 세션 목록 작업 배지.

### TODOS.md
- 새로 미룬 디자인 부채 없음.

## Implementation Tasks
Synthesized from this review's findings. 03-plan으로 넘긴다.

- [ ] **T-D1 (P1, human: ~1d / CC: ~30min)** — 클러스터링 화면 — 6-A · 6-B · 6-C 층 탭 · 잠금 · 확정 흐름 + Persona 단위 일괄 확정
  - Surfaced by: Pass 3 — 6-C 확정 피로(D-224)
  - Files: `frontend/src/app/pipeline/clustering/page.tsx`, `backend/app/segment/` 확정 API
  - Verify: Vitest(잠금 · 일괄 확정) + pytest(409 · 트랜잭션) + 브라우저 QA
- [ ] **T-D2 (P1, human: ~1d / CC: ~30min)** — 근거 탐색 화면 — 왼쪽 Persona · Context 목록 상태 배지, 실행 중 완료 행 열람, 재계산 버튼
  - Surfaced by: Pass 2 · Pass 7 — 실행 중 상태(D-223), Persona 선택(D-227)
  - Files: `frontend/src/app/pipeline/evidence/page.tsx`, `backend/app/evidence/`
  - Verify: Vitest(행 상태 · 잠금) + 브라우저 QA
- [ ] **T-D3 (P1, human: ~1d / CC: ~30min)** — 페르소나 화면 — 전체 맵 / Persona 카드 두 보기, 점 모양 · 명도 표기, Context 표↔점 강조
  - Surfaced by: Pass 1 · 5 · 6 — D-222 · D-225 · D-226
  - Files: `frontend/src/app/pipeline/personas/page.tsx`, `OpportunityMap` · `CCMTable` 컴포넌트
  - Verify: Vitest(구역 판정 · 표 정렬 · 강조) + 브라우저 QA(키보드로 표 → 카드)
- [ ] **T-D4 (P1, human: ~4h / CC: ~15min)** — 공통 — `GradeMark`(모양 + 글자) · `ProvisionalBadge` · CCM 칸 버튼(`aria-expanded`)
  - Surfaced by: Pass 4 · 6
  - Files: `frontend/src/components/ds/`
  - Verify: Vitest(글자 포함 렌더) + 브라우저 QA
- [ ] **T-D5 (P1, human: ~4h / CC: ~15min)** — 9.1 상태 표 문구 · 모양 전부(목업 s8)
  - Surfaced by: Pass 2
  - Verify: 상태별 브라우저 QA

### 완료 요약
```
+====================================================================+
|         DESIGN PLAN REVIEW — COMPLETION SUMMARY                    |
+====================================================================+
| System Audit         | DESIGN.md 없음 → 0~2단계 10절 규칙, UI 8화면  |
| Step 0               | 5/10, 7개 항목 전부                           |
| Pass 1  (Info Arch)  | 6/10 → 8/10 after fixes                       |
| Pass 2  (States)     | 7/10 → 9/10 after fixes                       |
| Pass 3  (Journey)    | 6/10 → 8/10 after fixes                       |
| Pass 4  (AI Slop)    | 8/10 → 8/10 (no new fixes)                    |
| Pass 5  (Design Sys) | 7/10 → 9/10 after fixes                       |
| Pass 6  (Responsive) | 6/10 → 8/10 after fixes                       |
| Pass 7  (Decisions)  | 1 resolved, 0 deferred                        |
+--------------------------------------------------------------------+
| NOT in scope         | written (3 items)                             |
| What already exists  | written                                       |
| TODOS.md updates     | 0 items proposed                              |
| Approved Mockups     | HTML 목업 8화면 (mockups/index.html)          |
| Decisions made       | 6 added to plan                               |
| Decisions deferred   | 0                                             |
| Overall design score | 6/10 → 8/10                                   |
+====================================================================+
```

### Unresolved Decisions
- 없음.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | — | Independent 2nd opinion | 0 | skipped (사용자 선택 D2) | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 6/10 → 8/10, 6 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** design 단계 외부 의견 — 사용자가 건너뜀(skipped). 커버리지 없음.
- **VERDICT:** DESIGN CLEARED — eng review required (계획 단계에서 `plan-eng-review`).

NO UNRESOLVED DECISIONS
