## 임무
프롬프트 버전: r3.v3
리서치 질문: 귀농·귀촌인은 왜 내려왔고, 내려온 뒤 집에서 몸과 생활이 언제 기대와 어긋나는가?
제품 분류: {"l1": "", "l2": "", "l3": "", "source": "user"}. 이 제품군 안에서 승인 키워드를 비슷한 주제로 모아 그 주제를 깊게 채우고, 부족한 축은 보조로 보완한다.
첨부 project_context.md 전체와 keyword_feedback.md가 있으면 함께 참고한다.

## 사고 절차
1. 승인 키워드와 사용자가 직접 추가 · 이동한 키워드를 의미가 비슷한 주제 묶음으로 나눈다(예: 같은 상황 · 같은 불편을 가리키는 단어끼리). 묶음은 출력하지 않는다.
2. 승인이 많거나 직접 추가 · 이동이 있는 주제를 우선한다. 같은 상황 안에서 아직 없는 다른 사물 · 현상 · 행동 단어로 채운다.
3. 앞말인 맥락어만 바꾼 변형은 같은 단어로 본다. 예: 「맥락어A+핵심어X」와 「맥락어B+핵심어X」는 같은 단어로 본다. 기존 승인 키워드의 맥락어만 바꾼 단어도 만들지 않는다.
4. 생성량의 약 7할은 주제 수렴(2단계)에, 약 3할은 축 분포에서 가장 적은 축 보완에 쓴다. 커버리지 신호가 있으면 이 3할에 우선 반영한다. 커버리지가 없으면 검색량을 추정하지 않는다.
5. 거절 사유에 해당하는 표현과 과거 0건 키워드의 반복을 피한다.

축 분포:
- physical: 0.40298507462686567
- psychological: 0.29850746268656714
- behavioral: 0.29850746268656714

거절 신호:
전원축사냄새: {"tags": ["irrelevant"], "note": ""}
농촌아이돌봄: {"tags": ["irrelevant"], "note": ""}
시골집맨발: {"tags": ["irrelevant"], "note": ""}
귀촌휴식죄책감: {"tags": [], "note": ""}
농가미완성감: {"tags": ["irrelevant"], "note": ""}
귀촌부부온도차: {"tags": ["irrelevant"], "note": ""}
귀촌실패낙인: {"tags": [], "note": ""}
귀촌직업상실: {"tags": [], "note": ""}
귀촌성소수자: {"tags": [], "note": ""}
귀촌경력단절: {"tags": [], "note": ""}
귀촌난임: {"tags": [], "note": ""}
귀촌감각과부하: {"tags": [], "note": ""}
귀촌운동공백: {"tags": [], "note": ""}
농가방분리: {"tags": [], "note": ""}
시골집실내텐트: {"tags": [], "note": ""}
농가귀마개: {"tags": [], "note": ""}
귀촌냉동식: {"tags": [], "note": ""}
재택카페출근: {"tags": [], "note": ""}
귀촌영상통화: {"tags": [], "note": ""}
귀촌마을단톡: {"tags": [], "note": ""}

사용자가 직접 추가 · 이동한 키워드(원하는 방향)
직접 추가 없음.
첨부 keyword_feedback.md의 "원하는 방향" · "오분류 이동" 항목도 원하는 방향으로 본다.

커버리지 신호:
커버리지 정보 없음 — 축 분포 균형에 집중.

과거 0건 키워드:
없음.

기존 승인 키워드(중복 제외):
- 시골집결로 (physical/space)
- 전원집곰팡이 (physical/sense)
- 농촌꽃가루 (physical/body)
- 시골집벌레 (physical/sense)
- 농가농약냄새 (physical/sense)
- 시골집장작연기 (physical/sense)
- 전원주택잔향 (physical/sense)
- 농촌개짖음 (physical/time)
- 시골집새벽소음 (physical/time)
- 주말집냉기 (physical/space)
- 빈집먼지 (physical/sense)
- 시골집온도차 (physical/space)
- 다락열기 (physical/space)
- 마당눈부심 (physical/sense)
- 농가진흙 (physical/space)
- 시골집문턱 (physical/product_physical)
- 전원욕실추위 (physical/body)
- 농가수압 (physical/product_physical)
- 시골집정전 (physical/product_physical)
- 귀촌손님방 (physical/space)
- 귀촌방문객 (physical/social)
- 마을불시방문 (physical/social)
- 귀촌품앗이 (physical/social)
- 귀촌생리용품 (physical/space)
- 전원벌쏘임 (physical/body)
- 귀촌수면분절 (physical/body)
- 농가손갈라짐 (physical/body)
- 귀촌건강환상 (psychological/belief)
- 전원청정믿음 (psychological/belief)
- 전원관리압박 (psychological/emotion)
- 귀촌후회 (psychological/emotion)
- 주말집의무감 (psychological/emotion)
- 귀촌도시향수 (psychological/emotion)
- 마을거절불안 (psychological/perceived_risk)
- 귀촌사생활 (psychological/perceived_risk)
- 시골집야간공포 (psychological/perceived_risk)
- 전원화재불안 (psychological/perceived_risk)
- 귀촌빈집불안 (psychological/perceived_risk)
- 반려견탈출불안 (psychological/perceived_risk)
- 귀촌이방인 (psychological/identity)
- 귀촌비농업인 (psychological/identity)
- 귀촌비혼여성 (psychological/identity)
- 귀촌회복공간 (psychological/goal_ladder)
- 전원혼자시간 (psychological/goal_ladder)
- 귀촌생활주도권 (psychological/goal_ladder)
- 귀촌관계거리 (psychological/goal_ladder)
- 귀촌아이안심 (psychological/goal_ladder)
- 귀촌알레르기 (behavioral/trigger)
- 귀촌이혼 (behavioral/trigger)
- 귀촌사별 (behavioral/trigger)
- 귀촌반려동물 (behavioral/trigger)
- 귀촌층간소음 (behavioral/trigger)
- 재택통신끊김 (behavioral/constraint)
- 농촌택배제한 (behavioral/constraint)
- 귀촌배달공백 (behavioral/constraint)
- 농가쓰레기 (behavioral/constraint)
- 농촌돌봄공백 (behavioral/constraint)
- 주말집도착청소 (behavioral/coping)
- 전원제습기 (behavioral/coping)
- 귀촌도시장보기 (behavioral/coping)
- 농가방문잠금 (behavioral/coping)
- 귀촌체험숙박 (behavioral/info_search)
- 전원겨울살이 (behavioral/info_search)
- 귀촌도시왕복 (behavioral/switching)
- 귀촌역귀촌 (behavioral/switching)
- 전원마당포기 (behavioral/switching)
- 귀촌분리거주 (behavioral/switching)

## 키워드 형태 규칙
- 사물·현상을 나타내는 짧은 명사형 검색어로 쓴다. 좋은 형태: 명사형 / 나쁜 형태: "후기 · 비교"형.
- 검색어는 두 단어 이하로 쓴다: 대상·장면을 좁히는 맥락어 하나 + 사물·현상을 가리키는 핵심어 하나. 맥락어는 첨부 맥락의 대상 집단 · 생활 장면 · 제품군에서 가져오고, 한두 개에 몰지 말고 여러 맥락어를 고르게 바꿔 쓴다.
- 공백 제거 기준 8자 이하로 쓴다. 조사 · 어미나 "~후 · ~때 · ~중" 같은 수식구를 붙인 구절형은 쓰지 않는다.
- 맥락어 없이 일반어 핵심어 하나만 단독으로 쓰지 않는다. 검색 범위가 지나치게 넓어진다.
- 문장형과 평가용 일반어를 피한다. 금지 단독 키워드: 가격 · 고민 · 리뷰 · 만족 · 불만 · 비교 · 선택 · 장단점 · 추천 · 평가 · 후기.
- 공백 제거 기준 2자 이상으로 쓰고, 대소문자·공백만 다른 중복과 기존 승인 키워드를 제외한다.
- 채널별 검색 문법을 따른다. 수집 채널: 네이버 카페, 네이버 블로그, 유튜브. 구어 · 줄임말 표현도 허용.

## 분류
물리(physical) · 심리(psychological) · 행동(behavioral) 중 한 축과 해당 sub 코드를 고른다.
| axis | sub 코드 |
|---|---|
| physical | time · space · social · sense · body · product_physical |
| psychological | emotion · goal_ladder · perceived_risk · belief · identity |
| behavioral | trigger · constraint · coping · info_search · switching |
시간(time) · 공간(space) · 사회적 환경(social) · 감각(sense) · 신체 상태(body) · 제품-물리 상호작용(product_physical).
감정(emotion) · 표면 목표→기능적 결과→숨은 니즈(goal_ladder) · 심리적 장벽(인지된 위험)(perceived_risk) · 인지·신념(belief) · 자아·정체성(identity).
기존 행동·문제 발생·트리거(trigger) · 제약(constraint) · 대처·우회(coping) · 정보탐색(info_search) · 전환·이탈(switching).
경험 단계(구매 전 · 중 · 후)는 축이 아니다. 사용자가 만든 custom: 코드는 기존 입력에 있을 때만 해당 축에서 사용한다.

## 출력
JSON 객체 하나만 출력한다. 설명이나 코드 블록을 덧붙이지 않는다.
최소 60개를 목표로 생성한다. keywords의 각 항목은 kw, axis, sub, why를 모두 포함한다.
kw/sub/why는 문자열, axis는 physical | psychological | behavioral 중 하나다.
why에는 리서치 질문과의 관련성을 짧게 적는다. id, round, origin, status는 서버가 부여한다.
JSON 구조(아래 타입 표기를 실제 값으로 바꾼다):
{"keywords": [{"kw": "string", "axis": "physical|psychological|behavioral", "sub": "string", "why": "string"}]}


=== ATTACHMENTS ===
--- project_context.md ---
## 0-A 프로젝트 개요

- 제품명: 세라젬 AI 웰니스 모듈러하우스
- 과제 유형: 탐색·기획형 — 아직 드러나지 않은 맥락과 기회를 찾는 과제. 넓게 탐색
- 한줄 정의: 건강을 이유로 또는 건강을 기대하며 귀농·귀촌한 사람들이, 결심부터 시골집에 정착하기까지 몸과 생활에서 겪는 맥락을 찾는다
- 리서치 질문: 귀농·귀촌인은 왜 내려왔고, 내려온 뒤 집에서 몸과 생활이 언제 기대와 어긋나는가?
- 프로젝트 유형: 신규기획 (상품 기획 · 컨셉 발굴. 기기 연결이 아니라 생활 서비스 전반의 경험)
- 분석 목표: 컨셉발굴
- 핵심 지표 (방향 지시자, 측정값 아님): 없음
- 사내 제약: 진단·치료 판단 제외(웰니스 범위), 건설 제외(파트너 영역), 귀농 지원금 · 토지 · 영농 기술은 제외
- 수집 채널: 네이버 카페, 네이버 블로그, 유튜브
- 제품 분류: 
- 제품 분류 출처: 사용자 입력

## 생각하는 페르소나 · 디멘션

- 속세가 싫어 내려온 은퇴자 (사회적 외부 페르소나)
- 번아웃으로 회사를 그만두고 내려온 40대 (사회적 외부 페르소나)
- 도시 전문직 출신, 집만 시골로 옮긴 사람 (사회적 외부 페르소나)
- 농부가 되려고 내려온 사람 (개인 취향·활동)
- 농사 없이 원격근무하는 귀촌인 (개인 취향·활동)
- 5도2촌 주말 생활자 (신체 외부 동선)
- 건강 신호(진단·수술) 후 회복하러 내려온 사람 (내부 바이오)
- 만성 통증이 있던 사람 (내부 바이오)

디멘션: 사회적 외부 페르소나 · 개인 취향·활동 · 신체 외부 동선 · 내부 바이오
예시는 출발점일 뿐이다. 네 디멘션 각각에서 예시와 비슷한 페르소나에 머물지 말고, 예시와 다른 페르소나와 맥락을 우선 발굴할 것

## 0-B 분석 대상 · 초기 기준선

분석 대상 초기 기준선 — 우선 탐색하되 범위 밖 발견도 배제하지 말 것, 해석을 조정하지 말 것

- 연령대: 전체
- 성별: 전체
- 가구 유형: 전체
- 생애 단계: 전체
- 분석 대상 메모: 귀농·귀촌 준비 중 ~ 정착 5년 이내
- 미래 고객: 전체

## 이미 아는 것

- 육체노동으로 근골격 부하가 누적됨
- 병원까지 멀어 의료 공백이 있음
- 고령 부모 동거 가구가 있음
- 도시 네트워크가 끊겨 고립감이 있음
- 일출·일몰과 기상에 하루가 종속됨
- 자급 식생활로 영양이 불규칙함
- 페르소나: 은퇴 부부(문서)
- 페르소나: 고령 부모 동거 가구(문서)
- 페르소나: 청년 귀농 가구(문서)
- 교통 불편함
- 고령 운전으로 어두운 시골 운전이 힘듬
- 도시에 사는게 이제는 힘들어서 귀농을 하면서 평화롭게 살고 싶음


--- keyword_feedback.md ---
## 방향 지시
- 없음

## 거절 사유
### irrelevant (관련성 낮음) · 5건
- 전원축사냄새
- 농촌아이돌봄
- 시골집맨발
- 농가미완성감
- 귀촌부부온도차
### 기타 · 15건
- 귀촌휴식죄책감
- 귀촌실패낙인
- 귀촌직업상실
- 귀촌성소수자
- 귀촌경력단절
- 귀촌난임
- 귀촌감각과부하
- 귀촌운동공백
- 외 7건

## 원하는 방향
- 없음

## 오분류 이동
- 없음
