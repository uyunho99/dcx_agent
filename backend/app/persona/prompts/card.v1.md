주어진 Context마다 이 Context에서 관측되는 담론을 서술한다.
출력은 contexts 배열이며 각 항목은 context_id, state, emotion, barrier만 포함한다.
각 칸은 {text: 문자열 또는 null, cite: 근거 번호 배열}이다.
입력의 모든 Context를 정확히 한 번씩 반환한다. 다른 Context를 만들지 않는다.
각 Context의 지지 근거, 반례, 희소 근거를 함께 검토하고 상충하는 근거를 숨기지 않는다.
인용은 해당 Context에 속한 입력 evidence의 E 번호만 사용한다. 번호는 이 묶음에서만 유효하다.
근거가 없거나 부족하면 text는 null, cite는 빈 배열로 반환한다.
situation_origin이 dims이고 situation 값이 있으면 의미와 범위를 유지하며 표현만 다듬는다.
Action은 6-C 확정값을 코드가 채우므로 생성하지 않는다.
이름, Desire, Goal은 확정된 입력이며 바꾸지 않는다.
지표, 등급, 근거 원문, basis, 수치 계산은 출력하지 않는다.
