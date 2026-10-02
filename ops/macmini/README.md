# DCX 2.0 맥미니 운영

운영 기본 루트는 `$HOME/srv/dcx-agent`, API는 `127.0.0.1:8400`, 웹은 `127.0.0.1:3400`입니다. 모든 진입점은 `APP_ROOT`를 지원하며 macOS 기본 `/bin/bash` 3.2에서 실행합니다. 운영 잡은 사용자 `UserName`과 `HOME`을 가진 LaunchDaemon 세 개입니다. 배포 잡은 로그인 여부와 관계없이 120초마다 main CI 결과를 조회합니다.

## 설치 준비와 미리보기

먼저 대상 루트의 `shared/app.env`에 서버 키를, `shared/data/`에 사용할 데이터를 준비합니다. 기존 작성자 해시를 유지하려면 기존 `.author_salt`를 `shared/data/.author_salt`에 복사해야 합니다. 설치기는 다른 앱이나 데모 데이터의 위치를 추측해서 복사하지 않습니다. 두 파일이 없으면 실제 설치는 중단됩니다. 키와 salt 권한은 600으로 설정합니다.

```bash
APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/install.sh \
  --dry-run --output-dir /tmp/dcx-install-plan
```

미리보기는 지정한 폴더에 plist 3개, `runtime.env`, `launch.env`만 렌더링합니다. 기존 배포 루트의 설정을 바꾸거나 sudo·launchctl·프로세스 종료를 실행하지 않습니다. 실제 실행은 터미널에서 소문자 `y`로 확인해야 합니다. 다른 입력과 EOF는 변경 없이 끝나고, 파이프로 전달한 `y`는 거부합니다.

```bash
sudo APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/install.sh
```

첫 설치는 main 머리 커밋을 정식 빌드합니다. 손 clone의 가상환경을 이동해 재사용하지 않습니다. 빌드는 대상 사용자로 실행하고, 서버 키를 빌드 환경에 싣지 않습니다. `shared/maintenance` hold 파일로 api/web 시작을 막고 서버와 릴리스 Python 작업자를 종료한 다음 sessions와 work를 스냅샷으로 저장합니다. 새 current를 연결하고 잡을 등록한 뒤 hold를 제거합니다. 상태 확인이 성공해야 손 clone을 삭제하고 fetch용 clone으로 교체합니다. 실패하면 손 clone과 스냅샷을 보존하며 로그를 확인해야 합니다. 실제 설치·재부팅 검증은 별도의 운영 QA입니다.

운영 공개 접속은 Cloudflare 터널을 통해 `https://dcx.person-a.ai` → `127.0.0.1:3400`(웹), `https://dcx-api.person-a.ai` → `127.0.0.1:8400`(API)로 연결됩니다. 브라우저가 사용할 API 주소는 공개 HTTPS 주소여야 합니다. 설치가 쓰는 운영 runtime 기본값은 다음과 같습니다.

```dotenv
AUTHOR_SALT_PATH=/배포루트/shared/data/.author_salt
STORAGE=local
LOCAL_DATA_DIR=/배포루트/shared/data
LABEL_GPT_BACKEND=codex_exec
JEV_BACKEND=fake
CORS_ORIGINS=https://dcx.person-a.ai,http://localhost:3400
NEXT_PUBLIC_API_URL=https://dcx-api.person-a.ai
```

설치 시 `DCX_PUBLIC_API_URL`과 `DCX_PUBLIC_WEB_URL` 환경변수로 공개 API·웹 주소를 바꿀 수 있습니다. 웹 주소는 CORS에 지정 웹 포트의 localhost origin과 함께 들어갑니다. 예: `sudo APP_ROOT="$HOME/srv/dcx-agent" DCX_PUBLIC_API_URL=https://api.example.com DCX_PUBLIC_WEB_URL=https://example.com /bin/bash ops/macmini/install.sh`. `--qa`는 이 공개 주소 환경변수를 사용하지 않고 `NEXT_PUBLIC_API_URL=http://localhost:8401`, `CORS_ORIGINS=http://localhost:3401`을 기본값으로 사용합니다. QA 포트 변경 시 localhost URL도 함께 바뀝니다.

기존 `shared/runtime.env`에 `NEXT_PUBLIC_API_URL` 또는 `CORS_ORIGINS`가 있으면 각 값을 환경변수·기본값보다 우선하여 보존합니다. 일반 설치 계획과 `--dry-run` 모두 실제 사용할 두 값을 출력합니다. 기존 localhost 설정도 보존되므로 공개 주소로 전환할 때는 운영자가 해당 값을 직접 수정해야 합니다.

운영 스크립트는 `$APP_ROOT/ops/`에 복사되어 코드 롤백과 독립적으로 남습니다. `ops_outdated: true` 로그가 나오면 새 릴리스의 `ops/macmini/install.sh`로 재설치합니다. 기존 current가 있으면 설치기는 코드를 바꾸지 않고 스크립트·잡을 갱신합니다. NEXT_PUBLIC 값 변경은 프론트 재빌드가 필요하므로 다른 커밋을 정식 배포해야 합니다.

## 수동 명령

```bash
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" status
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" deploy
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" deploy <sha>
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" rollback
```

`status`는 maintenance hold 상태와 소유 PID/시작 이유, current, `/health`, last-failed-sha, 이력 마지막 3줄, 배포 로그 마지막 5줄을 출력합니다. `deploy`는 지정 커밋(생략하면 origin/main)의 실패 표시를 지운 후 기존 배포 흐름과 CI 판정을 실행합니다. 단축 SHA도 정규화합니다. 다른 배포가 잠금을 가진 동안에는 실패 표시를 지우지 않습니다.

`rollback`은 현재 이력의 바로 전 릴리스와 **현재 릴리스 배포 직전** 스냅샷을 사용합니다. 중지 → sessions/work 복원 → current 전환 → 시작 → 상태 확인 순서입니다. 롤백 전 SHA를 last-failed-sha에 기록하고 이력 마지막 행을 제거하므로 반복 호출로 이전 단계에 되돌아갈 수 있습니다. 이전 릴리스나 스냅샷이 없으면 변경 없이 `되돌릴 버전이 없습니다`로 실패합니다. 복원한 버전도 상태 확인에 실패하면 `unhealthy-both`를 남깁니다.

롤백은 코드와 sessions/work만 되돌립니다. 큰 파일·캐시·모델은 복원하지 않습니다. 롤백 뒤 화면이 이상하면 그 세션을 새 버전으로 다시 시작하세요. 배포 중 작업자는 종료되며, 기존 죽은 작업자 감지 로직이 상태를 갱신합니다.

배포와 수동 롤백은 `shared/maintenance` 파일을 먼저 만듭니다. api/web 진입점은 파일이 있으면 서버를 시작하지 않고 10초 대기 후 정상 종료합니다. launchd의 KeepAlive와 ThrottleInterval=10이 재시도하며, 시작 단계는 파일을 제거하고 정상 상태 확인을 기다립니다. 운영 LaunchDaemon과 QA LaunchAgent 모두 같은 계약을 쓰며 deploy/dcxctl은 launchctl이나 관리자 권한이 필요하지 않습니다. 등록·교체는 설치기만 담당합니다.

중지는 PID 파일의 자손·지정 포트 리스너·releases 및 repo 아래 Python 작업자와 APP_ROOT 아래 Node 프로세스에 TERM → 최대 20초 대기 → KILL을 적용한 뒤 포트와 작업자를 확인하고 1초 후 한 번 더 확인합니다. 남아 있거나 확인에 실패하면 error를 기록하고 hold를 유지하며 스냅샷·전환을 하지 않습니다. 다음 틱도 중지 검증을 통과해야 hold를 해제합니다. 이때 `deploy.log`와 `shared/deploy-state`를 확인하고 남은 프로세스 원인을 해결하세요. 복구 중 hold 파일을 임의로 삭제하면 안 됩니다.

수동 롤백도 동작 전에 `deploy-state` 첫 줄에 `rolling-back <from> <to> <snapshot>`을 기록합니다. 둘째 줄의 `manual` 표시는 복구가 끝날 때까지 유지됩니다. kill·재부팅 후 다음 deploy 틱은 fetch/CI보다 먼저 복원·전환·이력 확정을 마칩니다. 이력 갱신은 반복해도 이전 행을 더 지우지 않으며 매 복원 시 현재 sessions/work를 새 `<snapshot>-failed`, `<snapshot>-failed-1`, … 폴더로 옮깁니다. 재시작 후 생긴 쓰기도 별도 백업에 보존되며 이 백업들은 스냅샷 5개 정리 대상에서 제외됩니다.

## QA 사용자 에이전트

```bash
APP_ROOT="$HOME/srv/dcx-agent-qa" /bin/bash ops/macmini/install.sh \
  --qa --dry-run --output-dir /tmp/dcx-qa-plan
# 데이터와 app.env, salt 준비 후 별도 QA에서만 실행:
APP_ROOT="$HOME/srv/dcx-agent-qa" /bin/bash ops/macmini/install.sh --qa
```

QA는 sudo 없이 `~/Library/LaunchAgents/ai.person-a.dcx-agent-qa.{deploy,api,web}.plist`를 등록합니다. 기본 포트는 8401/3401, 도메인은 `gui/<uid>`입니다. API 잡 시작 로그에 `codex --version`을 남기므로 launchd 아래 PATH와 사용자 로그인 환경을 확인할 수 있습니다. 설치된 `shared/launch.env`는 dcxctl에 같은 라벨·포트·상태 확인 URL을 전달합니다. 테스트 개발 중에는 실제 QA 설치나 아래 정리 명령을 실행하지 않습니다.

```bash
for job in deploy api web; do
  launchctl bootout "gui/$(id -u)/ai.person-a.dcx-agent-qa.$job"
done
# QA plist를 삭제해야 다음 로그인 때 다시 등록되지 않습니다.
for job in deploy api web; do
  rm "$HOME/Library/LaunchAgents/ai.person-a.dcx-agent-qa.$job.plist"
done
```

## 로그와 실행 확인

```bash
tail -n 20 "$HOME/srv/dcx-agent/logs/deploy.log"
tail -n 50 "$HOME/srv/dcx-agent/logs/api.log"
tail -n 50 "$HOME/srv/dcx-agent/logs/web.log"
APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/run-api.sh --print-cmd
APP_ROOT="$HOME/srv/dcx-agent" /bin/bash ops/macmini/run-web.sh --print-cmd
```

배포 로그는 at/sha/decision을 가진 JSON Lines입니다. 상태 확인은 API `/health`의 release, `/sessions` 200, 웹 `/pipeline/start` 200을 확인합니다. run-api는 app.env와 runtime.env를 데이터로 읽고 PID 및 DCX_RELEASE_SHA를 설정합니다. run-web은 HOME/PATH/TMPDIR와 NEXT_PUBLIC 값, PORT만 전달하며 app.env나 상속된 서버 키를 전달하지 않습니다. `--print-cmd`는 서버를 실행하거나 PID 파일을 쓰지 않습니다.

종료 대상은 해당 api/web PID 자손, 지정 포트의 리스너, 배포 루트 releases/repo 아래 Python 작업자와 APP_ROOT 아래 Node 프로세스입니다. 3000·3310·3311·8310·8311 포트는 설치기와 라이브러리의 리스너 조회/종료 경로에서 거부합니다. APP_ROOT가 `$HOME/srv/dcx-agent`가 아니면 3400/8400도 거부합니다. internal-app 및 사용자 데모 서버는 건드리지 않습니다.

테스트 훅은 T2의 `DCX_BUILD_CMD`, `DCX_RESTART_CMD`, `DCX_CI_API`, `DCX_HEALTH_API`, `DCX_HEALTH_WEB`, `DCX_HEALTH_TIMEOUT`, `DCX_REPO_URL`, `DCX_API_PORT`, `DCX_WEB_PORT`, `DCX_FORCE_UNHEALTHY_SHA`, `DCX_BASH`, `DCX_PATH`를 사용합니다. 실제 설치에서는 가짜 훅을 사용하지 않습니다.

```bash
DCX_BASH=/bin/bash backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider
backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
```

Hold 파일은 소유 PID와 시작 이유를 기록합니다. 설치 실패 시 설치기는 자신의 hold만 제거합니다. deploy 틱은 deploy-state가 없고 hold 소유 프로세스가 사라졌으면 hold를 제거하고 `hold-cleared`를 기록합니다. 빈 구형 hold도 이 조건에서 정리합니다. 진행 중인 트랜잭션의 hold는 복구 흐름에서 처리합니다.

QA 자동화에서만 `DCX_INSTALL_ASSUME_YES=1`과 `--qa`를 함께 사용해 y 질문을 건너뛸 수 있습니다. 운영 모드는 이 변수를 무시하며 터미널의 직접 y 확인을 계속 요구합니다.
