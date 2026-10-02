# 경험 디자인 컨셉 — insight.concept v1

주어진 대상 인사이트와 Evidence Package 근거만 사용하여 경험 디자인 컨셉을 작성한다.
제공된 출력 스키마의 JSON만 반환한다.

- persona_profile은 경험을 설명하는 합성 프로필이다. 확인된 사실이나 실제 인물로 서술하지 않는다.
  Persona 이름, Desire, Goal은 입력의 확정값을 유지하고 새 Persona를 만들지 않는다.
  등급과 "합성값" 표시는 코드가 채운다.
- pain_points는 입력 evidence의 근거 번호 세 개만 선택한다. 여러 Persona의 번호는
  persona_id:E1 형식을 그대로 사용한다. 원문, 채널, 위치, Context ID를 작성하거나 바꾸지 않는다.
- journey의 각 행은 AS-IS context_id, action, feeling과 TO-BE service, service_action을 짝지어 작성한다.
  context_id는 반드시 대상 insight.context_ids 중 하나여야 한다. cx_4d는
  정신적, 물리적, 문화적, 시스템 중 하나다. TO-BE 서비스의 "처방" 표시는 코드가 채운다.
- 사내 constraints, analysisGoal, keyMetrics를 고려하여 TO-BE 서비스를 제안한다.
  constraint_check는 생략한다. 별도의 persona.constraint_check가 제약을 검사한다.
- invalid_context_ids가 있으면 대상 인사이트의 Context만 사용하여 다시 작성한다.
  violations가 있으면 previous_concept의 위반을 해소하는 컨셉으로 다시 작성한다.
- 숫자 지표, basis, 근거 원문, 등급, 4D-CX 분포는 출력하지 않는다. 모두 코드가 채운다.
