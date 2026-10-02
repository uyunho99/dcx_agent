프로젝트의 원문 근거를 찾을 검색 문장을 작성하세요.
입력의 첫 줄은 프로젝트 oneLiner입니다. 이어지는 Persona 이름, Desire, Goal,
Artifact 후보(키워드)와 다음 형식의 모든 Context 행을 함께 읽으세요.
{context_id} · {action} · 주된 제약: {dominant_constraint} · 키워드: …

입력의 경험과 제약을 반영하여 소비자가 직접 말하는 자연스러운 1인칭 문장으로 쓰세요.
관찰자를 주어로 쓰거나 분석 용어로 설명하지 마세요. 출력 검색 문장에 다음
금지어 정규식에 해당하는 표현을 절대 넣지 마세요:
페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은

출력은 스키마에 맞는 JSON 객체 하나입니다.
- persona_query: desire_check에 Desire를 확인할 서로 다른 2문장,
  artifact에 실제 사용한 물건이나 도구를 찾을 1문장을 배열로 작성하세요.
- context_queries: 입력의 context_id를 키로 하여 각각 정확히 아래 8키를 넣으세요.
  모든 값은 비어 있지 않은 검색 문장 하나여야 합니다.
  Sense: 감각 경험, Feel: 감정, Think: 판단과 고민, Act: 실제 행동,
  Relate: 다른 사람과의 관계, Outcome: 원하는 결과,
  Counter: 기대와 반대되는 경험, Residual: 남아 있는 욕구와 다른 방법.
- anchor_context_ids: 입력에 있는 모든 context_id를 빠짐없이 나열하세요.
  알 수 없는 ID를 추가하지 마세요. 모든 Context를 검색 문장에 반영하세요.

재생성 요청에 위반 목록이 있으면 전부 수정하고, 수정한 일부만이 아니라
persona_query, context_queries, anchor_context_ids 전체를 다시 반환하세요.
