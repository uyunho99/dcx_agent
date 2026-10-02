# DCX 2.0 개발 문서 모음

작업 묶음마다 폴더 하나. 폴더 안 순서는 `01-brainstorm`(기획) → `02-design`(설계) → `03-plan`(구현 · QA 계획) → `decision-log`(결정 기록) → `reports/` · `qa/`(build · review · QA · 검증 보고서).

정리 기준일 2026-10-02.

## 방법론

- [dcx1-vs-dcx2-methodology.md](dcx1-vs-dcx2-methodology.md) — DCX 1.0 → 2.0 단계별 방법론 변화

## 파이프라인 단계

| 폴더 | 내용 | 코드 main 반영 |
|---|---|---|
| [dcx2-stage0-2](dcx2-stage0-2/) | 0~2단계 프로젝트 설정 · 키워드 · 크롤링 | 반영(PR #2) |
| [dcx2-stage0-task-mode](dcx2-stage0-task-mode/) | 0단계 과제 유형 분기 · 생각하는 페르소나 | 반영(PR #5) |
| [dcx2-stage3-5](dcx2-stage3-5/) | 3~5단계 전처리 · 라벨링 · 학습 + Known Insight | 반영(PR #3) |
| [dcx2-stage6-8](dcx2-stage6-8/) | 6~8단계 전체 기획 · 설계, 묶음 ① 6단계 클러스터링. 결정 D-2xx 원장 | 아직(`feature/dcx2-stage8`) |
| [dcx2-stage7](dcx2-stage7/) | 묶음 ② 7단계 근거 탐색(RAG). 결정은 dcx2-stage6-8 원장에 기록 | 아직(`feature/dcx2-stage8`) |
| [dcx2-stage8](dcx2-stage8/) | 묶음 ③ 8단계 페르소나 · 인사이트 · 컨셉 | 아직(`feature/dcx2-stage8`) |

## 백로그 · 운영

| 폴더 | 내용 | 코드 main 반영 |
|---|---|---|
| [dcx2-backlog-1](dcx2-backlog-1/) | 백로그 1차(안정화 · 표시 · 키 없는 커버리지), B-115~B-117, 아산병원 데모 결정(DEMO-01~03) | 1차 반영(PR #4). B-115 · B-116은 아직(`feature/yt-subtitles-spacing`) |
| [dcx2-cicd](dcx2-cicd/) | GitHub Actions + 맥미니 자동 배포 | 반영(PR #6) |

## 키워드 화면 수정

| 폴더 | 내용 | 코드 main 반영 |
|---|---|---|
| kw-short-form (문서 없음) | 키워드를 맥락어 + 핵심어 두 단어 이하로 | 반영(PR #7) |
| [kw-skip-r2](kw-skip-r2/) | R2 잠금 · R1→R3 · R3 수렴 / R4 마지막 발산 | 반영(PR #8) |
| [kw-popover-spacing](kw-popover-spacing/) | 거절 팝오버 가림 · 표시 띄어쓰기 | 반영(PR #9) |
| [kw-round-view](kw-round-view/) | 고른 라운드의 단어만 보기 | 반영(PR #10) |
| [kw-round-carry](kw-round-carry/) | 이전 라운드 승인 누적 + 라운드 표시 | 반영(PR #11) |
