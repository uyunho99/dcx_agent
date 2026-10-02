# 결정 기록 — 묶음 ③ (`dcx2-stage8`)

- 공통 원장: [`../dcx2-stage6-8/decision-log.md`](../dcx2-stage6-8/decision-log.md) D-201~ (묶음 ①·②가 이어 씀). 묶음 ③은 병행 브랜치라 merge 충돌을 피하려고 이 파일에 D-301~로 남긴다.

## 기획 (2026-10-02)

### D-301 ③은 Evidence Package를 픽스처 + 읽기 검증 모델로만 쓰고, 생성 모델은 ② 소유 · 판단 (Claude, R1)
- ③을 ② 위로 rebase할 때 ②의 모델로 바꾸고 픽스처 ↔ ② 실제 출력 대조 테스트를 추가한다. 비용: rebase 때 모델 교체 1회.
### D-302 Persona 카드 생성은 Context 최대 4개씩 나눠 호출 + 8-B · 8-C 요약 1회 · 판단 (Claude, R2)
- D-235로 Persona당 Context가 최대 10개라 한 번에 넣으면 입력이 너무 크다. CCM 화면은 설계대로 4열 넘으면 2단.
### D-303 새 세션은 새 8단계 화면, 옛 세션은 기존 페르소나 · 인사이트 화면 그대로 · 판단 (Claude, R3)
### D-304 ③ 픽스처 Evidence Package는 구역 A~F · ★ 마커가 모두 나오도록 따로 만든다 · 판단 (Claude, R4)

## 설계 (2026-10-02)

### D-305 확정 인사이트 추천은 별도 API(`/known/{sid}/suggestions`) + 서랍 접힘 구역, 기존 prev_session 자동 복사에 섞지 않음 · 판단 (Claude)
- 이유: 기존 `known.store.initialize`가 이전 세션 Known 문장을 자동 복사하므로, 그 경로에 넣으면 D-217(추천만)을 어긴다. 비용: API 1개 · 서랍 구역 1개.
### D-306 기존 `/insights` 경로를 `/pipeline/insights`로 옮기고 옛 세션은 그 경로에서 기존 화면 · 판단 (Claude)
- 사이드바 단계 경로를 한 체계(`/pipeline/*`)로 맞춘다. 옛 링크 `/insights`는 새 경로로 넘김.
### D-307 Opportunity 기준선 위 정확히 놓인 점은 위쪽 구역 · 판단 (Claude)
