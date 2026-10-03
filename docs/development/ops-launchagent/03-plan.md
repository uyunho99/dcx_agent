# 운영 서비스를 사용자 세션(LaunchAgent)으로 전환 — 구현 · QA 계획

기획 [01](01-brainstorm.md) · 설계 [02](02-design.md) 승인(2026-10-03). 구현 담당: Codex(`codex:codex-rescue`, 쓰기 모드). Claude는 위임 · 리뷰 · QA만.

## 0. 작업 환경
- 계획 승인 후 `development-harness worktree /Users/persona1/Desktop/dcx_agent-ops-agent-impl feature/ops-launchagent`.
- 준비: `python3.12 -m venv backend/.venv && pip install -r backend/requirements.txt -r backend/requirements-dev.txt`, `npm --prefix frontend ci`(main 체크아웃 venv는 낡음).
- 기준 검사: `harness.config.json` 4개 명령.

## 1. Task

| ID | 내용 | 담당 파일 | 의존 | AC |
|---|---|---|---|---|
| T1 | `--agent` 플래그 · 변수 분리(`qa` / `agent_domain`) · 렌더 · sudo 거부 · 확인 프롬프트 | `ops/macmini/install.sh`, `backend/tests/ops/test_install.py` | — | AC1, AC4 |
| T2 | 데몬 ↔ 에이전트 전환 가드 | `ops/macmini/install.sh`, `backend/tests/ops/test_install.py` | T1(같은 파일 → 순차) | AC2 |
| T3 | 운영 문서 | `ops/macmini/README.md` | T2(문구 일치) | AC5 |

### T1 세부
- 인자: `--agent`; `--agent`와 `--qa` 동시 → 사용법 오류 exit 2. 사용법 문구에 `[--agent|--qa]`.
- `agent_domain=true` if `--qa` or `--agent`. 등록 관련 분기(도메인 `gui/$(id -u)`, 위치 `$HOME/Library/LaunchAgents`, plist `UserName` 제거, `chown root:wheel` 생략, sudo 거부, `as_user`의 sudo 분기)를 `agent_domain` 기준으로. QA 환경 분기(APP_ROOT/포트 기본값, localhost 주소, ASSUME_YES)는 `qa` 기준 유지.
- `--agent` 라벨은 `ai.person-a.dcx-agent`, 공개 주소 · CORS는 운영 규칙(DCX_PUBLIC_* 우선, 기존 runtime.env 보존).
- sudo로 `--agent` 실제 설치 → "운영 에이전트 설치는 sudo 없이 실행하세요" exit 1.
- RED 테스트(`test_install.py`, 기존 패턴 · `forbid_services` 사용):
  - `--agent --dry-run`: 라벨 `ai.person-a.dcx-agent`, 출력에 `Library/LaunchAgents`(and not `/Library/LaunchDaemons`), plist 3개에 `UserName` 없음, runtime.env의 NEXT_PUBLIC_API_URL = `https://dcx-api.person-a.ai`, launch.env 포트 = 지정값.
  - `--agent --qa` → exit 2.
  - `--agent`는 `DCX_INSTALL_ASSUME_YES=1`이어도 `y 입력` 프롬프트를 띄운다(운영과 동일), 파이프 `y` 거부.
  - 기존 데몬/QA 드라이런 테스트 그대로 통과(파라미터에 agent 추가 가능).
- 명령: `backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider`

### T2 세부
- 테스트 가능하도록 경로를 환경변수로 덮어쓸 수 있게: `DCX_DAEMON_DIR`(기본 `/Library/LaunchDaemons`), `DCX_AGENT_DIR`(기본 `$HOME/Library/LaunchAgents`). 등록 위치(`destination`)도 같은 변수를 쓴다.
- 가드는 드라이런이 아닐 때, **확인 프롬프트 전에** 실행(변경 없이 끝나야 하므로):
  - `--agent`: `$DCX_DAEMON_DIR/ai.person-a.dcx-agent.<job>.plist` 존재 또는 `launchctl print system/ai.person-a.dcx-agent.<job>` 성공 → 설계 2절 안내 문구(stderr) + exit 1.
  - 운영 데몬(플래그 없음): `$DCX_AGENT_DIR/ai.person-a.dcx-agent.<job>.plist` 존재 또는 `launchctl print gui/$(id -u)/ai.person-a.dcx-agent.<job>` 성공 → 반대 방향 안내 + exit 1. sudo 아래에서도 대상 사용자 uid(`id -u "$TARGET_USER"`)와 TARGET_HOME 기준.
  - QA는 가드 없음(라벨이 다름).
- RED 테스트: 가짜 데몬 plist 디렉터리 → `--agent` exit 1, 안내 문구에 `sudo launchctl bootout system/ai.person-a.dcx-agent.` 포함, `m.root/'ops'` 미생성; launchctl 스텁이 `print system/...`에 0 반환 → 같은 결과; 깨끗하면 프롬프트까지 진행(`y 입력` 출력). 반대 방향 1건.
- 명령: 위와 동일.

### T3 세부
- README "운영 사용자 에이전트(권장)" 절: 이유(D-342) · 자동 로그인 조건 · 전환 3단계 명령 · 드라이런 · 되돌리기(에이전트 내리고 sudo 데몬 설치).

## 2. TDD 규칙 (Codex에 전달)
RED → GREEN → 리팩터링, 담당 외 파일 수정 금지, Task별 보고서 `docs/development/ops-launchagent/reports/T<n>.md`. 실제 launchctl · sudo · 서비스 조작 금지(테스트는 스텁만).

## 3. 리뷰
- Task별 설계 일치, 기존 데몬 · QA 경로 불변(diff에서 `$qa` 분기 이동 전수 확인).
- 브랜치 전체: Codex 읽기 전용 리뷰.

## 4. QA
- UI 변경 없음 → 브라우저 시나리오는 운영 전환 뒤 확인(사용자 sudo 필요).
- Q1(자동): `--agent --dry-run --output-dir <scratch>`를 실제 운영 루트(`APP_ROOT=$HOME/srv/dcx-agent`)로 렌더 → plist · runtime.env가 현재 운영 값(포트 8400/3400, 공개 주소)과 일치, 서비스 무변경.
- Q2(자동): 데몬이 등록된 현재 상태에서 `--agent` 실제 실행 → 가드가 안내 후 exit 1, 변경 없음(`dcxctl status` 동일).
- Q3(UAT, 사용자): 안내 명령으로 데몬 내리기 → `install.sh --agent`(y) → `dcxctl status` healthy → 세라젬 라벨링 "이어서 진행" → GPT 판정 건수 증가(`https://dcx.person-a.ai/pipeline/labeling`).
- 보고서 `docs/development/ops-launchagent/reports/qa.md`.

## 5. 수용 기준 연결
AC1→T1,Q1 · AC2→T2,Q2 · AC3→Q3 · AC4→T1(기존 테스트) · AC5→T3 · AC6→Q3 · AC7→검증 명령 4개.

## 6. 되돌리기
코드는 커밋 revert. 운영은 `for job in deploy api web; do launchctl bootout gui/$(id -u)/ai.person-a.dcx-agent.$job; rm ~/Library/LaunchAgents/ai.person-a.dcx-agent.$job.plist; done` 후 `sudo APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/install.sh`(데몬 재설치). 데이터 · 릴리스 무변경.
