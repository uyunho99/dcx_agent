8-A Context 결과와 Persona 전체 근거에서 8-B 의도와 8-C 속성을 요약한다.
이름, Desire, Goal과 Context 경계는 확정값이며 재생성하지 않는다.
intent는 {text, basis_context_ids, reserved_context_ids}로 반환한다.
의도는 행동과 같지 않으며 가설이다. 반례와 유보할 Context를 reserved_context_ids에 명시한다.
usage_context와 jtbd는 {text, cite}이며 cite는 입력 evidence의 Persona 전체 E 번호만 사용한다.
journey는 {pre_purchase, purchase, post_purchase}이며 근거가 충분한 비율의 합은 1이다.
비율을 뒷받침할 근거가 부족하면 세 값 모두 null로 반환한다.
sensitivity는 {price, brand, feature}이며 각 값은 상, 중, 하, null 중 하나다.
values와 decision_style은 근거로 뒷받침되는 문자열 또는 null이다.
근거가 부족한 칸은 null로, 해당 인용과 Context ID 배열은 빈 배열로 반환한다.
지표, 레이더, 막대, 등급, 근거 원문, basis는 코드가 채우므로 생성하지 않는다.
