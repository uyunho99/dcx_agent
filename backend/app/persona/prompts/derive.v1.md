모든 Persona 카드의 Context 요약과 pain point 인용, Context ID, ODI,
Known Insight 목록을 읽고 공통된 불편을 인사이트 3~8개로 묶으세요.
각 인사이트는 고유 id, title, pain_point(2~3줄), context_ids,
known_ki_id(같은 내용의 Known Insight ID 또는 null)만 반환하세요.
입력에 있는 Context ID만 사용하고 각 목록에서 중복하지 마세요.
Persona 이름, Desire, Goal은 확정된 입력 그대로 유지하세요.
레이더, 코사인, 백분위, ODI 막대, 평균, 대상 여부 등의 숫자나 계산 필드를
생성하지 마세요. 근거 원문을 새로 쓰거나 만들어 내지 마세요.
출력 스키마의 items 배열에 결과를 담으세요.
