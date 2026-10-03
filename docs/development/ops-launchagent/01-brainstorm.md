# 운영 서비스를 사용자 세션(LaunchAgent)으로 전환 — 기획

## 문제
- 운영 API가 LaunchDaemon(system 도메인)으로 돌아서 `codex exec`가 `Failed to synchronize managed preferences`로 즉시 실패한다. 4단계 GPT 판정(Codex)이 운영에서 0건으로 멈춘다(세라젬 세션, 2026-10-03).
- 같은 Codex 프로필(`dcx-worker`)을 사용자 세션 LaunchAgent로 돌리면 정상 응답(임시 에이전트 실험, exit 0).
- QA 설치(`install.sh --qa`)는 이미 LaunchAgent 방식이다.

## 결정 (사용자, 2026-10-03) — D-342
- **B. 운영도 사용자 세션 LaunchAgent로 돌린다.** cvc-agent처럼 Codex를 로그인 세션에서 실행.

## 대안
| 안 | 설명 | 판단 |
|---|---|---|
| A. 라벨링만 OpenAI API | 설정 한 줄 | 비용 · 사용자 거절 |
| B. 운영 LaunchAgent (선택) | `install.sh --agent`: 운영 경로 · 포트 · 공개 주소 + gui 도메인 | 사용자 선택 |
| C. 데몬 안에서 `launchctl asuser`로 Codex만 사용자 세션 실행 | 데몬이 root가 아니라 불가 | 불가 |

## 동작 (예시)
1. 사용자가 터미널에서 기존 데몬 3개를 내린다(sudo 1회, 명령은 안내문 그대로 복사).
2. `install.sh --agent` 실행(sudo 없음, `y` 확인) → 기존 current 릴리스 · 데이터 그대로, 잡만 `~/Library/LaunchAgents`에 등록, 8400/3400 재기동.
3. 세라젬 세션에서 "이어서 진행" → Codex 판정이 진행된다.
4. 맥미니 재부팅 → 자동 로그인과 함께 세 잡이 뜨고, 배포 잡도 계속 120초마다 main을 확인한다.

## 수용 기준
- AC1: `install.sh --agent --dry-run --output-dir D`가 운영 라벨(`ai.person-a.dcx-agent`) · 포트 8400/3400 · 공개 주소(`https://dcx-api.person-a.ai` 등) · `UserName` 없는 plist 3개와 runtime.env · launch.env를 렌더링한다.
- AC2: 실제 `--agent` 설치는 sudo로 실행하면 거부, 기존 운영 LaunchDaemon이 `/Library/LaunchDaemons`에 있거나 system 도메인에 등록돼 있으면 내리는 sudo 명령을 안내하고 변경 없이 중단한다.
- AC3: 설치 후 `dcxctl status`/`deploy`/`rollback`이 그대로 동작한다(launch.env 라벨 · 포트 동일).
- AC4: 기존 운영 데몬 설치 · QA 설치 동작과 테스트는 그대로.
- AC5: ops README에 전환 절차(데몬 내리기 → `--agent` 설치 → 확인)와 운영 조건 변화(자동 로그인 필요)를 적는다.
- AC6: 실제 전환 뒤 운영 API에서 Codex 판정이 1건 이상 성공한다(UAT에서 사용자 작업 후 확인).
- AC7: 백엔드 pytest(ops 테스트 포함) · 프런트 lint · build · test 통과.

## 제외 범위
- Codex 자체 수정, OpenAI API 경로 전환, QA 설치 변경, Cloudflare 터널 설정.

## 위험
- 로그아웃하면 서비스 중단 → 자동 로그인 유지 필요, README에 명시.
- 전환 중 짧은 중단(데몬 내림 → 에이전트 기동, 1~2분) → 판정이 멈춰 있는 지금 실행.
- 데몬과 에이전트가 동시에 같은 포트를 잡는 경우 → AC2 가드로 막는다.
