현재 판 JSON과 사용자의 message를 읽고 요청한 target만 수정하세요.
insights 대상은 기존 insight.derive와 같은 {items: [...]} 스키마로 답하세요.
concept:{id} 대상은 editable의 insight.concept 스키마(persona_profile 문자열,
pain_points 근거 번호 3개, journey)를 유지하세요. 다른 컨셉은 수정하지 마세요.
입력에 존재하는 Context ID와 근거 번호만 사용하세요. 컨셉의 AS-IS context_id는
대상 인사이트의 context_ids에 속해야 합니다. 변경하지 않는 내용은 보존하세요.
레이더, ODI, 막대, 백분위, basis, 근거 원문, 출처, 등급, 4D 개수와 제약 판정은
코드가 채웁니다. 이 값이나 숫자를 만들어 답하지 마세요. JSON만 반환하세요.
