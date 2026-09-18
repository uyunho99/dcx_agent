# Lane B 골든 데이터 계약

**이 픽스처는 스키마 계약이며, T6~T11 구현이 이 필드 이름과 타입을 그대로 따라야 한다.**
동일한 결과 문장·점수를 강제하는 알고리즘 테스트가 아니라 구조·참조·산식의 계약이다.
기준은 `docs/development/dcx-step07-11/02-design.md`, `03-plan.md` 전체 및
`resources/DCX_STEP07-11_개발안_데이터계약.md`의 상세 중첩 구조다.

## 파일과 공통 타입

`session_a/`, `session_b/` 각각 다음 9개 JSON을 포함한다. A/B는 동일 원문 30건,
8차원 임베딩, 군집 3개, 페르소나 3개를 사용한다. A는 known_insights 5개,
B는 빈 배열(QA-EDGE-002)이다. ID의 범위는 세션 내부다.

| 파일 | 실제 저장 키 / 사용법 |
| --- | --- |
| classified.json | 테스트 묶음. records를 classified/{sid}/relevant_{ts}.jsonl에 한 행씩, run을 classified/{sid}/run_{ts}.json에, known_insights를 세션에 저장 |
| clusters.json | clusters/{sid}/result_{ts}.json |
| personas.json | personas/{sid}/result_{ts}.json, v2 |
| evidence_CL0-P1.json, evidence_CL1-P1.json, evidence_CL2-P1.json | evidence/{sid}/{persona_id}_{ts}.json |
| cam_CL0-P1.json, cam_CL1-P1.json, cam_CL2-P1.json | cam/{sid}/{persona_id}_{ts}.json, 10-A 원천 + 10-B 집계 |

모든 루트는 `sid: string`(golden-a/golden-b), `timestamp: string`(20260918_120000)을
갖는다. 아래 필드는 모두 필수이며 `| null`로 표시한 값만 null을 허용한다.
number는 유한한 JSON 정수/실수, int는 bool이 아닌 정수다.
`[string, number][]`는 2원소 JSON 배열의 목록이다.

## 06: classified.json

루트: 공통 필드 + `records: Record[]`, `known_insights: KnownInsight[]`, `run: Run`.

| Record 필드 | 타입 | 의미 |
| --- | --- | --- |
| doc_id | string | d_000001~d_000030, link와 1:1인 고정 합성 ID. A/B 동일 |
| author_hash | string 또는 null | 합성 salt·작성자 번호 SHA-256의 앞 8 hex 문자(4바이트). 군집 첫 문서는 null |
| date | string | YYYY-MM-DD |
| decision | string | auto / escalated / human, 각 12/9/9건 |
| label | int | 1, 통과 문서만 제공 |
| reviewed_by | string 또는 null | human이면 golden-reviewer, 그 외 null |
| relevance_score | number | 06 앙상블 확률 [0,1]; 09 relevance와 별개 |
| kw, title, desc, body, link, cafe | string | 기존 수집 필드. example.invalid 합성 URL |
| text | string | body와 동일한 원문 |
| keywords | string[] | 공백 분리 명사 3개 |
| embedding | number[8] | 오프라인 벡터 조회 대체용. 운영 API의 차원을 정의하지 않음 |

KnownInsight: `id: string`, `text: string`, `embedding: number[8]`.
실제 세션 필드는 id/text이며 embedding은 05 벡터 조회를 대체하는 테스트 입력이다.

Run 필드:
- `alpha: number` = .03, `escalate_threshold: number` = .62.
- `calibration: {n: int, agreement: number, disagreements: int}` = 30/.9/3.
- `ensemble: {models: string[], scores: object<string, number>, combined: number}`.
- `counts: {total: int, auto: int, escalated: int, human: int}`. 이 fixture는 decision을 배타적으로 집계한다.

Run은 T5에서 전달받았다고 가정한 스냅샷이다. .62는 원천 문서의 예시이며
alpha→임계 추정 알고리즘을 구현하거나 검증하지 않는다. 직접 주입 가능한 공개 입력으로
해석하면 안 된다. T5 자체 RED에서 alpha 기반 계산을 검증해야 한다.

## 07: clusters.json

루트: 공통 필드 + `primary_method: string` = embedding, `clusters: Cluster[]`.

| Cluster 필드 | 타입 | 의미 |
| --- | --- | --- |
| cluster_id, label, dominant_constraint | string | CL0/CL1/CL2, 명칭, 지배 제약 |
| c_tfidf | [string, number][] | 어휘와 class TF-IDF. 이 데이터는 동점이므로 어휘순 |
| size, authors | int | 문서 수, null 제외 distinct author_hash 수 |
| centroid | number[8] | 멤버 벡터의 산술평균 |
| silhouette | number | 군집 멤버의 Euclidean silhouette 평균 [-1,1] |
| k_scan | [int, number][] | k=3..14 각각의 전체 데이터 평균 silhouette. 모든 군집에 동일 |
| bands | {core: number, fringe: number, edge: number} | 밴드 비율, 합 1 |
| band_thresholds | {p50: number, p90: number} | 군집 내 거리의 선형 보간 백분위수 |
| documents | {doc_id: string, dist_centroid: number, band: string}[] | 원문 순서 멤버십, Euclidean 거리, core/fringe/edge |

거리 ≤ P50은 core, P50 < 거리 ≤ P90은 fringe, P90 초과는 edge.
문서 30건을 중복·누락 없이 보존한다. 군집당 core 5 / fringe 4 / edge 1.
KMeans(random_state=42, n_init=10), k=3을 선택하고 첫 원문 등장 순서로 ID를 정규화했다.
Ward 비교 fixture는 없으며 Ward는 ID를 발급하면 안 된다.

c-TF-IDF는 군집별 keywords를 합쳐
`(군집 내 단어 빈도 / 군집 총 토큰 수) × log(1 + 평균 군집 토큰 수 / 전체 단어 빈도)`.
여기서는 군집당 고유어 3개, 30토큰, 각 어휘 전체 빈도 10이다.

## 08: personas.json

루트: 공통 필드 + `schema_version: int` = 2, `personas: Persona[]`.

Persona 필드:
- `persona_id: string`: CL0-P1/CL1-P1/CL2-P1. `cluster_id: string`: 실제 07 ID.
- `name: string`, `desire: string`, `goals: string[]`.
- `centrality_top: [string, number][]`: 명사와 L2 정규화 eigenvector 중심성.
- `modularity_q: number`: 군집 내 키워드 삼각형을 한 커뮤니티로 두어 Q=0.
- `size: int`, `authors: int`, `status: string` = confirmed(합성 사람 확정 상태).
- `doc_ids: string[]`: 해당 07 군집에만 속하는 문서. 군집당 페르소나 1개.

`situation`, `pain_point`, `insight`는 **존재하면 안 된다**.
같은 3개 명사가 매번 함께 등장하는 완전 그래프이므로 중심성은 각각 1/√3이다.

## 09: evidence_{persona_id}.json

루트: 공통 필드 + `persona_id: string`, `cluster_id: string`, `actions: Action[]`,
`centroid_sentence: CentroidSentence`, `evidence: Evidence[]`, `coverage: Coverage`, `warnings: string[]`.

Action 필드: `action_id: string`(CL0-P1-A1 형식), `context_id: string`(CL0-P1-C1 형식),
`sentence: string`, `lda_topic: int`, `topic_weight: number`, `docs: int`, `doc_ids: string[]`.
centroid 제외 원문 9건을 A1 7건/A2 2건으로 분할한다. LDA 토픽은 수작업 합성
입력이지 LDA 알고리즘의 기대 결과가 아니다. topic_weight는 각각 7/9, 2/9다.

CentroidSentence: `doc_id: string`, `text: string`, `dist_centroid: number`.
최소 거리의 실제 문서(동점이면 doc_id순)이며 **evidence/랭킹/Action doc_ids에서 제외**한다.

| Evidence 필드 | 타입 | 의미 |
| --- | --- | --- |
| doc_id, quote | string | 06 원문 ID와 text 그대로 |
| cluster_id, persona_id, context_id | string | 필수 검색 filter 3키, Action과 동일 scope |
| action_id | string | 이 패키지 actions[].action_id |
| role | string | support / refute, 군집 마지막 문서는 반례 |
| relevance | number | [0,1] 합성 검색 점수 |
| known, max_sim_to_known | number | 동일값 필수. [0,1] 기존 인사이트와 최대 cosine, 음수는 0 |
| rarity, combo_rarity | number | 동일값 필수. [0,1] 합성 희소성 입력 |
| quality | number | 아래 산식. 1을 넘을 수 있으므로 clamp하지 않음 |
| rank_relevance, rank_quality | int | 패키지 내 1-based 내림차순 순위, 동점은 doc_id순 |
| dims | string[] | Sense / Feel / Think / Act / Relate / Outcome 중 일부 |
| band | string | 07과 같은 core/fringe/edge |
| source | string | auto |

문서별 표기가 달라 known/max_sim_to_known, rarity/combo_rarity를 모두 저장한다.
canonical 이름은 max_sim_to_known, combo_rarity이며 별칭과 다른 값을 저장하면 안 된다.

A: `quality = relevance × (1 − .50 × known) × (1 + .30 × rarity)`.
B: `known=0`, **quality=relevance**, warnings=`["KNOWN_INSIGHTS_EMPTY"]`.
빈 known_insights에서는 rarity 보너스도 비활성화한다(이번 요청/계획 QA-EDGE-002 우선).
B의 비영 rarity를 보존하여 이 예외 분기를 검증한다. A의 warnings는 빈 배열이다.
합성 점수는 centroid 제외 doc_id 순 j=0..8에 대해 relevance=.95−.01j, rarity=j/10.
A에는 실제 relevance/quality 순위 이동이 있다. evidence 배열은 quality 순이다.

Coverage: `dims: string[]`는 evidence dims 합집합(문자열 정렬), `min: int`=4.
두 세션 모두 6/6. 자동 보충 검색과 filter 3키 누락 거부는 T8 자체 RED의 책임이다.

## 10-A/10-B: cam_{persona_id}.json

루트: 공통 필드 + `persona_id: string`, `columns: Column[]`,
`constants: {satisfaction_min_n: int}`, `grades: Grades`.

Column 필드:
- `action_id: string`, `context_id: string`: 09 Action의 ID.
- `context: Cell`, `action: Cell`, `barrier: Cell | null`: 키는 항상 존재.
- `barrier_gen_fail: bool`: null이면 true, 서술이 있으면 false.
- `measurements: {doc_id: string, importance: number, satisfaction: number | null}[]`:
  해당 Action의 evidence별 10-A 합성 평가(0..10). 중복 표본 없음.
- `importance: number`: measurements importance 평균.
- `satisfaction_n: int`: null 아닌 satisfaction 표본 수.
- `satisfaction: number | null`: 표본 수 ≥ satisfaction_min_n이면 평균, 아니면 null.
- `odi: number | null`: S=null이면 null, 그 외 **I + max(I−S, 0)**.

Cell: `text: string`, `grade: string` = confirmed / speculated, `cites: string[]`.
confirmed는 Action evidence의 원문 그대로라 검색 hit/어휘중첩이 성립한다.
speculated는 근거 없는 가설(cites=[]). cites는 **해당 Action** doc_id만 허용한다.
centroid는 이 CAM의 cite에서 제외한다.

Grades: `confirmed: int`, `speculated: int`, `ratio_spec: number`.
null 제외 셀 집계. 파일당 confirmed 4, speculated 1, ratio_spec=.2.
null barrier는 추측 문장으로 집계하지 않는다.

작은 표본에서 정상/부족을 모두 검증하도록 **테스트 상수 satisfaction_min_n=6**을
명시했다. 운영 잠정값 20을 변경하지 않는다.
A1은 n=7/I=8/S=5/ODI=11. A2는 n=2/I=4/S=null/ODI=null(측정은 있어도 표본 부족).
10-B는 저장된 10-A measurements/집계에서만 읽으며 검색·LLM 평가를 추가하지 않는다.

이전 자료의 observed/inferred 등급과 계획 T9의 “null 아님”은 이번 요청과 충돌한다.
**이번 요청을 우선해 confirmed/speculated, 명시적 barrier:null + barrier_gen_fail:true**로
고정한다. zone/레이더 산식은 미정이라 만들지 않았다.

## 참조 연결과 T11

- classified.records.doc_id ← clusters.documents.doc_id ← personas.doc_ids ← evidence.doc_id 및 centroid.doc_id.
- clusters.cluster_id ← persona.cluster_id ← evidence.cluster_id.
- personas.persona_id ← evidence.persona_id ← cam.persona_id.
- evidence.actions.action_id/context_id ← evidence 항목 및 cam.columns.
- cam 셀 cites 및 measurements.doc_id는 해당 Action.doc_ids의 부분집합.

T11은 **CAM JSON을 그대로 입력**으로 쓴다. persona_id→08, action_id→09,
cites→06으로 역추적한다. 반례 원문은 각 패키지 A2에 남아 from_action 테스트에
사용할 수 있다. null ODI를 0점으로 꾸미지 말 것. 확정 인사이트 append 테스트의
초기 known_insights는 같은 세션의 classified.json에서 얻는다. T11 산출/로직은 만들지 않는다.

## 테스트 사용 및 재생성

```python
def test_lane(golden_classified, golden_clusters, golden_personas, golden_evidence, golden_cam):
    source = golden_classified(session="a")
    clusters = golden_clusters()  # 기본 세션 a
    personas = golden_personas()
    package = golden_evidence("CL0-P1", session="b")
    cam = golden_cam("CL0-P1", session="b")
```

`golden_load(stage, session="a", persona_id=None)`도 제공한다. 매 호출 새 객체를 반환한다.
`local_data_dir`는 autouse tmp_path fixture다. config/s3 import 전(수집 단계)에
STORAGE=local/임시 경로를 설정하고 테스트별 settings.local_data_dir와 s3._DATA_DIR를
같이 변경한다. DNS/TCP/UDP를 수집 단계부터 차단한다. SDK·검색·LLM은 monkeypatch 또는
unittest.mock으로 대체할 것. subprocess/외부 브라우저를 통한 네트워크 사용은 금지다.
pytest-mock은 필요 없다.

```sh
cd backend
python3 -m venv venv
source venv/bin/activate
python3 -m pip install pytest numpy scikit-learn pydantic-settings
python3 -m pytest tests/test_golden_fixtures.py -v
# 의도적으로 계약 데이터를 재작성할 때만:
python3 tests/fixtures/golden/build_fixtures.py
```

pytest.ini 위치가 backend rootdir을 결정하며 testpaths=tests, pythonpath=.이다.
빌더는 테스트 저작 도구이며 프로덕션에서 사용하지 않는다. 각 단계 JSON을 쓴 뒤
다시 읽어 다음 단계를 만든다. 테스트는 정적 JSON을 검증하며 빌더를 자동 실행하지 않는다.
수치 오차는 1e-7 수준으로 비교한다. 작성 환경: Python 3.13.13, numpy 2.5.3,
scikit-learn 1.9.1, pytest 9.1.1. 라이브러리 버전별 KMeans 스캔 오차가 커지면
원인을 검토하고 계약 변경으로 취급할 것(자동 재생성으로 실패를 숨기지 말 것).
