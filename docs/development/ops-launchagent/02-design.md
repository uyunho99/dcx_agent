# 운영 서비스를 사용자 세션(LaunchAgent)으로 전환 — 설계

기준: 01-brainstorm.md(승인), D-342.

## 1. 설치 방식 세 가지 (`ops/macmini/install.sh`)
| 방식 | 플래그 | 라벨 | 도메인 · 위치 | 포트 기본 | 공개 주소 | 권한 |
|---|---|---|---|---|---|---|
| 운영 데몬(기존) | 없음 | `ai.person-a.dcx-agent` | `system` · `/Library/LaunchDaemons` | 8400/3400 | 운영 | sudo 필수 |
| **운영 에이전트(신규)** | `--agent` | `ai.person-a.dcx-agent` | `gui/<uid>` · `~/Library/LaunchAgents` | 8400/3400 | 운영 | sudo 금지 |
| QA(기존) | `--qa` | `ai.person-a.dcx-agent-qa` | `gui/<uid>` · `~/Library/LaunchAgents` | 8401/3401 | localhost | sudo 금지 |

- `--agent`와 `--qa`는 같이 쓸 수 없다(사용법 오류, exit 2).
- 내부 변수: `qa`(QA 전용 동작: 경로 · 포트 · localhost 주소 · ASSUME_YES 허용)와 새 `agent_domain`(gui 도메인 등록: `--qa` 또는 `--agent`)을 분리한다. 지금 `$qa`로 묶인 것 중 **등록 방식에 관한 것**(도메인 · 위치 · plist `UserName` 제거 · `chown root:wheel` 생략 · sudo 거부 · `as_user` 분기)은 `agent_domain`으로, **QA 환경에 관한 것**(APP_ROOT · 포트 기본값 · localhost 주소 · ASSUME_YES)은 `qa`로 둔다.
- `--agent`의 확인 프롬프트는 운영과 같이 대화형 `y` 필수(ASSUME_YES 무시, 파이프 `y` 거부).
- 렌더 결과(runtime.env · launch.env)는 운영 데몬과 같은 값. launch.env의 라벨 · 포트 · 상태 확인 URL이 같으므로 `dcxctl`/`deploy.sh`는 변경 없음(둘 다 launchctl을 쓰지 않음, hold 파일 + KeepAlive 계약).

## 2. 데몬 → 에이전트 전환 가드
- `--agent` 실제 설치(드라이런 제외) 시작 전, 아래 중 하나라도 있으면 **아무것도 바꾸지 않고** exit 1:
  - `/Library/LaunchDaemons/ai.person-a.dcx-agent.{deploy,api,web}.plist` 파일
  - `launchctl print system/ai.person-a.dcx-agent.<job>` 성공
- 안내 문구(그대로 복사해 실행 가능):
  ```
  운영 LaunchDaemon이 아직 등록돼 있습니다. 아래를 터미널에서 실행한 뒤 다시 설치하세요.
  for job in deploy api web; do sudo launchctl bootout system/ai.person-a.dcx-agent.$job; sudo rm -f /Library/LaunchDaemons/ai.person-a.dcx-agent.$job.plist; done
  ```
- 반대 방향(운영 데몬 설치 시 같은 라벨 LaunchAgent가 있음)도 같은 방식으로 막고 `launchctl bootout gui/<uid>/…` + `rm ~/Library/LaunchAgents/…` 안내. 두 방식이 같은 포트를 동시에 잡지 않게 한다.
- 데몬을 내린 뒤 남은 8400/3400 프로세스는 기존 `restart_services stop`이 정리한다(설치 흐름 그대로).

## 3. 운영 문서 (`ops/macmini/README.md`)
- "운영 사용자 에이전트(권장)" 절 추가: 왜(Codex는 사용자 세션에서만 동작, D-342) · 조건(자동 로그인 유지, 로그아웃 시 중단) · 전환 3단계(데몬 내리기 sudo → `APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/install.sh --agent` → `dcxctl status`) · 드라이런 명령.
- 기존 "LaunchDaemon 세 개" 문단에 "Codex 판정이 필요하면 `--agent` 사용" 한 줄.

## 4. 실패 상태
| 상황 | 동작 |
|---|---|
| `--agent`를 sudo로 실행 | "운영 에이전트 설치는 sudo 없이 실행하세요", exit 1 |
| 데몬 잔존 | 2절 안내, exit 1, 변경 없음 |
| `--agent --qa` | 사용법 오류 exit 2 |
| 설치 중 상태 확인 실패 | 기존 흐름(손 clone · 스냅샷 보존, 로그) |

## 5. UI
화면 변경 없음 — 서버 프로세스 등록 방식만 바뀐다. 브라우저 QA는 운영 전환 뒤 라벨링 화면에서 Codex 판정이 진행되는지 확인하는 것으로 대신한다(UAT, 사용자 sudo 필요).
