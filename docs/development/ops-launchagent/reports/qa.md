# QA (fc3107a, 2026-10-03)

UI 변경 없음 — 화면 시나리오 대신 운영 루트 대상 자동 확인 + UAT 수동 확인.

| ID | 결과 | 근거 |
|---|---|---|
| Q1 렌더 | PASS | `APP_ROOT=$HOME/srv/dcx-agent install.sh --agent --dry-run --output-dir <scratch>` → 등록 위치 `~/Library/LaunchAgents`, 잡 3개 `ai.person-a.dcx-agent.*`, plist에 `UserName` 없음, launch.env 포트 8400/3400 · 상태 확인 URL, runtime.env가 현재 운영 runtime.env와 정렬 diff 없음. 운영 서비스 무변경(`/health` release 818717a 유지). |
| Q2 가드 | PASS | 데몬이 등록된 현재 상태에서 `install.sh --agent`(실제 모드) → "운영 LaunchDaemon이 아직 등록돼 있습니다…" + 내리는 명령 출력 후 종료, 확인 프롬프트 전에 멈춤, 운영 `/health` 그대로. |
| Q3 전환 · Codex 판정 | UAT | 사용자: 데몬 내리기(sudo) → `--agent` 설치(y) → `dcxctl status` → 세라젬 라벨링 이어서 진행 → 판정 건수 증가. 이 PR이 main에 반영돼 운영 current에 `--agent`가 있어야 실행 가능. |

사전 확인(구현 전): 임시 LaunchAgent(gui 도메인)에서 `codex exec -p dcx-worker` → `ok`, exit 0. LaunchDaemon(운영 API)에서는 `Failed to synchronize managed preferences`.
