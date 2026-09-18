# STEP 07~11 개발안 — 데이터 계약 기준

> 목적: 07~11을 개발하려면 **06이 무엇을 건네주는지**가 먼저 확정돼야 한다. 그런데 06의 산출 스키마는 코드에 존재하지 않는다(`schemas.py`는 요청 모델만 있다). 그래서 이 문서는 ① 01~06의 **실제** 데이터 형태를 코드에서 확인해 적고, ② 06 산출을 **계약으로 확정**한 뒤, ③ 그 위에서 07~11을 설계한다.

---

## 0. 지금 저장소에 실제로 있는 것

`app/services/s3.py` 기준. 로컬(`data/`) / S3 동일 키.

| 키 | 형식 | 쓰는 곳 |
|---|---|---|
| `sessions/{sid}/session.json` | json | 세션 전체 상태 |
| `crawl/{sid}/{ts}.jsonl` | jsonl | STEP 04 수집 원본 |
| `preprocessed/{sid}/{ts}.jsonl` | jsonl | STEP 05 전처리 |
| `classified/{sid}/relevant_{ts}.jsonl` | jsonl | **STEP 06 산출** |
| `classified/{sid}/irrelevant_{ts}.jsonl` | jsonl | STEP 06 탈락분 |
| `clusters/{sid}/cluster_{cid}_{ts}.jsonl` | jsonl | STEP 07 군집별 문서 |
| `clusters_refined/{sid}/data_{ts}.jsonl` | jsonl | STEP 07 정제 후 |
| `personas/{sid}/result_{ts}.json` | json | STEP 08 산출 |
| Pinecone `dcx-{sid}` | 벡터 1024D cosine | STEP 05 임베딩 |

**07~11용 키는 하나도 없다.** `evidence/`, `cam/`, `insights/`, `concepts/`가 전부 신설 대상이다.

---

## 1. 데이터가 흘러가는 실제 형태 (01 → 06)

### STEP 01·02 — 선언
`sessions/{sid}/session.json` 안. 요청 모델에서 확인되는 필드: `bk`(제품군), `problemDef`(한줄 정의), `ages` · `ageRange` · `gens`(타겟). 설계 문서가 요구하는 `known_insights`는 **아직 없다 — 신설**.

### STEP 03 — 키워드
`KeywordGenRequest` / `ScoreKeywordsRequest` 기준 `{"kw": str, "cat": str}`. 점수는 `naver.py`가 `{"kw", "cat", "score", "total"}`로 돌려준다.

### STEP 04 — 수집 (`crawl/{sid}/{ts}.jsonl`)
```jsonc
{ "kw": "심박 측정", "title": "...", "desc": "...", "link": "https://cafe.naver.com/...",
  "cafe": "애플사용자모임", "date": "20260502",
  "body": "..."        // api_crawl4ai 모드에서만 채워짐
}
```
`author`는 `crawl4ai_svc`가 수집하지만 **레코드에 남지 않는다**(집합으로만 씀). 설계 문서의 "작성자 수" 표기는 이 필드가 있어야 성립한다 — **신설 대상**.

### STEP 05 — 전처리 / 임베딩
전처리는 `title`·`desc`·`body`·`link`·`cafe` 기준 필터링만 하고 **필드를 추가하지 않는다**. 임베딩은 Pinecone에 1024D로 올리며 메타데이터는 `{title, desc, kw, cafe, cluster}` 5개뿐이다. `dist_centroid`·`max_sim_to_known`·`combo_rarity` 등 09가 요구하는 값은 **전부 없다**.

### STEP 06 — 판정 (`classified/{sid}/relevant_{ts}.jsonl`)
`training.py`가 앙상블 확률로 0.5에서 자르고, 통과분에 **필드 하나만** 붙인다.
```jsonc
{ ...STEP 04 레코드 그대로..., "relevance_score": 0.87 }
```
job 상태로만 남고 파일에 안 남는 것: `scores`(모델별 정확도), `models`, `total/relevant/irrelevant`.

---

## 2. STEP 06 산출 계약 (예측 · 확정 대상)

07~11이 물고 갈 최소 계약. **06-A(모델 학습)와 06-B(근거 판정) 화면이 이 값을 만든다.**

### 2.1 레코드 — `classified/{sid}/relevant_{ts}.jsonl`
```jsonc
{
  "doc_id": "d_000123",          // 신설 · 이후 전 단계의 인용 단위
  "kw": "심박 측정",
  "title": "...", "desc": "...", "body": "...",
  "link": "https://cafe.naver.com/...",
  "cafe": "애플사용자모임",
  "author_hash": "a_9f21",       // 신설 · 원문 식별 없이 작성자 수만 세기 위함
  "date": "2026-05-02",          // ISO 로 정규화

  "relevance_score": 0.87,       // 기존 · 앙상블 확률
  "decision": "auto",            // 신설 · auto | escalated | human
  "label": 1,                    // 신설 · 최종 확정 라벨
  "reviewed_by": null            // 신설 · human 일 때만
}
```

### 2.2 사이드카 — `classified/{sid}/run_{ts}.json` (신설)
```jsonc
{
  "alpha": 0.03,                  // 목표 오류율 — 검수량을 정하는 입력
  "escalate_threshold": 0.62,     // alpha 에서 계산된 값. 사람이 직접 만지지 않는다
  "calibration": { "n": 412, "agreement": 0.930, "disagreements": 29 },
  "ensemble": { "models": ["LSTM","CNN","GRU","LLM"],
                "scores": {"LSTM":0.887,"CNN":0.862,"GRU":0.879,"LLM":0.934},
                "combined": 0.951 },
  "counts": { "total": 385400, "auto": 384220, "escalated": 1180, "human": 412 }
}
```

### 2.3 07~11이 요구하지만 06 이전에 만들어야 하는 값
| 값 | 만드는 곳 | 없으면 막히는 것 |
|---|---|---|
| `doc_id` | 04 수집 시 부여 | 09 인용 추적 · 10 Reviews · 11 계보 |
| `author_hash` | 04 수집 시 | 08·10의 "작성자 N명" 전부 |
| `known_insights[]` + 임베딩 | 01 선언 | **09 랭킹의 감점 항 전체** |
| Pinecone 메타 확장 | 05 임베딩 | 09 filter 3키 · 밴드 |

> **이게 07~11 개발의 선결 조건이다.** 특히 `known_insights`가 없으면 09의 `quality = relevance × (1 − α·max_sim_to_known) × (1 + β·combo_rarity)`에서 **감점 항이 항상 1**이 되어, 설계의 핵심(아는 이야기 내리기)이 무력화된다.

---

## 3. STEP 07~11 개발 순서

### 07 — 군집 → Touch Point
**입력** `classified/.../relevant_*.jsonl` + Pinecone 벡터
**신설 산출** `clusters/{sid}/result_{ts}.json`
```jsonc
{ "primary_method": "embedding",   // embedding | ward — ID는 한쪽에서만 발급
  "clusters": [{ "cluster_id": "CL0", "label": "운동 중 신체 신호 확인",
    "c_tfidf": [["심박",0.704],["워치",0.695]],
    "size": 14820, "authors": 6231,
    "silhouette": 0.31, "k_scan": [[3,0.21],[6,0.31]],
    "bands": {"core": 0.52, "fringe": 0.36, "edge": 0.12},
    "dominant_constraint": "기기를 늘려야 함" }] }
```
**작업** ① 문서별 `dist_centroid` 계산 후 Pinecone 메타에 기록 → 밴드 부여 ② c-TF-IDF ③ k 3~14 스캔 곡선 저장 ④ Ward 갈래는 비교용으로만 실행, ID 발급 금지
**의존** 2.3의 `doc_id`

### 08 — SNA → 페르소나
**입력** 07 결과 + 클러스터별 문서
**신설 산출** `personas/{sid}/result_{ts}.json` — **기존 파일을 덮어쓰지 말고 스키마를 교체**
```jsonc
{ "personas": [{ "persona_id": "CL0-P1", "cluster_id": "CL0",
    "name": "귀로 건강 재는 러너",
    "desire": "운동 중 몸 상태를 최소한의 기기로 확인받고 싶다",
    "goals": ["...","..."],
    "centrality_top": [["심박",0.812]],
    "modularity_q": 0.42, "size": 4120, "authors": 2318,
    "status": "confirmed" }] }
```
**작업** ① 명사 공출현 행렬 + 아이겐벡터 중심성 → 모듈 분할 ② Desire 초안은 LLM(`persona.generate`), **확정은 사람** ③ 클러스터를 가로지르는 통합 금지
**주의** 현재 `personas.py`는 `{cluster_id, cluster_name, personas:[{name, situation, pain_point, insight}]}`를 뱉는다. 이건 10이 할 일을 08에서 하는 구조라 **분리해야 한다**.

### 09 — LDA → Action → 근거 수집
**입력** 08 페르소나 + Pinecone(확장 메타)
**신설 산출** `evidence/{sid}/{persona_id}_{ts}.json` (Evidence Package)
```jsonc
{ "persona_id": "CL0-P1",
  "actions": [{ "action_id": "CL0-P1-A1", "sentence": "워치와 이어폰을 함께 챙겨 나가며 둘 다 착용한다",
    "lda_topic": 7, "topic_weight": 0.38, "docs": 1566 }],
  "centroid_sentence": { "doc_id": "d_077930", "text": "...", "dist_centroid": 0.041 },
  "evidence": [{ "doc_id": "d_092418", "quote": "...", "role": "support",
    "relevance": 0.61, "max_sim_to_known": 0.14, "combo_rarity": 0.79, "quality": 0.70,
    "rank_quality": 1, "rank_relevance": 24,
    "dims": ["Think","Feel"], "band": "fringe", "source": "auto" }],
  "coverage": { "dims": ["Sense","Feel","Act","Outcome"], "min": 4 } }
```
**작업** ① LDA 토픽 → Action 문장 ② `known_insights` 임베딩 대비 `max_sim_to_known` ③ `combo_rarity` ④ quality 재정렬 + **relevance 순위 동시 보존**(순위 이동 표시용) ⑤ centroid 문장은 순위에서 제외하고 별도 필드
**선결** `known_insights` 없으면 이 단계 전체가 반쪽이다

### 10-A — CAM
**입력** 09 Evidence Package
**신설 산출** `cam/{sid}/{persona_id}_{ts}.json`
```jsonc
{ "persona_id": "CL0-P1",
  "columns": [{ "action_id": "CL0-P1-A1",
    "context": {"text":"...","grade":"observed","cites":["d_077930"]},
    "action":  {"text":"...","grade":"observed","cites":["d_092418"]},
    "barrier": {"text":"...","grade":"inferred","derived_from":["context","emotion"]},
    "keywords": ["#워치"], "artifacts": ["스마트워치"],
    "sentiment": 1.02, "odi": 14.98, "zone": "F" }],
  "grades": { "observed": 16, "inferred": 6, "speculated": 2, "ratio_spec": 0.083 } }
```
**작업** ① 서술 생성(`cam.describe`) ② **등급은 코드가 판정** — `retrieve(문장, scope=이 Action의 evidence)` 히트 + 어휘중첩 ≥ 0.40 → observed ③ 추측 비율 > 30% → 페르소나 신뢰도 하향
**핵심** LLM에게 등급을 묻지 않는다. 출력에 "관측"·"추론" 문자열이 섞이면 가드레일 경고.

### 10-B — 기회 영역
**입력** 10-A의 `sentiment` · 문서 수
**산출** 10-A에 이미 들어간 `odi`·`zone`의 **집계 뷰** — 새 계산 없음
**미결** A~F 구역 경계 산식, 페르소나 단위 집계 산식

### 11-A / 11-B — 인사이트 → 컨셉
**신설 산출** `insights/{sid}/{ts}.json`, `concepts/{sid}/{ts}.json`
```jsonc
// insight
{ "insight_id": "IN2", "headline": "귀로 재는 컨디션, 손목은 이제 그만",
  "pain_points": ["...","..."], "contributing": ["CL0-P1","CL2-P1"],
  "actions": ["CL0-P1-A1","CL0-P1-A2"], "odi_sum": 28.5 }
// concept
{ "concept_id": "CO-02", "from_insight": "IN2", "persona_id": "CL0-P1",
  "service_bullets": [{"text":"...","from_action":"CL0-P1-A3"}],
  "experience": [{"text":"...","grade":"observed"},{"text":"...","grade":"speculated"}],
  "interviews": [{"quote":"...","stance":"support"},{"quote":"...","stance":"refute"}],
  "cx_4d": {"physical":0.82,"system":0.61,"mental":0.30,"cultural":0.24} }
```
**작업** ① 페르소나 가로지르는 종합(대화형) ② 확정 인사이트 → `known_insights`에 append(다음 세션 기준선 상승) ③ 컨셉 서술도 문장 단위 등급 ④ 인터뷰 지지/반박 계수

---

## 4. 개발 순서 제안

| 순서 | 내용 | 이유 |
|---|---|---|
| 0 | `doc_id` · `author_hash` · ISO 날짜를 04에 추가하고 재수집 | 아래 전부가 여기 의존 |
| 1 | `known_insights` 입력 + 임베딩 (01·05) | 09 감점 항의 전제 |
| 2 | Pinecone 메타 확장 (`doc_id`·`persona_id`·`dist_centroid`·`band`) | 09 filter 3키 |
| 3 | 06 산출 계약 확정 (§2) | 07 입력 |
| 4 | 07 → 08 → 09 순차 | ID 계층이 순서대로 쌓인다 |
| 5 | 10-A → 10-B | 10-B는 집계뿐 |
| 6 | 11-A → 11-B | |

**0~2를 건너뛰고 07부터 손대면 09에서 반드시 막힌다.**

---

## 5. 열려 있는 결정

`resources/DCX_STEP07-11_기능설계_v1.md` §7과 동일 — 랭킹 계수 α·β, 어휘중첩 임계 0.40, 추측 비율 상한 30%, Edge P90, A~F 구역 경계, 레이더·4D-CX 산식. 전부 **잠정값**이며 어드민 화면의 "파이프라인 상수"에서 조정한다.
