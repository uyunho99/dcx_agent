# 리뷰 (Claude, fc3107a)
- 설계 1절: `qa`(QA 환경) / `agent_domain`(등록 방식) 분리 확인. 데몬 · QA 렌더 결과 불변(기존 테스트 통과), `--agent` 렌더는 운영 runtime.env와 동일(실제 운영 runtime.env와 diff 없음).
- 설계 2절: 가드가 드라이런 제외 · 확인 프롬프트 전에 실행, 양방향, QA 제외. 안내 명령의 `$job`이 리터럴로 출력됨.
- sudo 거부가 HOME 해석 전에 실행됨(--agent 실제 설치).
- dcxctl/deploy.sh는 launchctl을 쓰지 않아 변경 불필요 — launch.env 동일 확인.
- 발견 없음.
