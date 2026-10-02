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

첫 설치는 main 머리 커밋을 정식 빌드합니다. 손 clone의 가상환경을 이동해 재사용하지 않습니다. 빌드는 대상 사용자로 실행하고, 서버 키를 빌드 환경에 싣지 않습니다. api/web KeepAlive를 끄고 서버와 릴리스 Python 작업자를 종료한 다음 sessions와 work를 스냅샷으로 저장합니다. 새 current를 연결하고 잡을 등록한 뒤 상태 확인이 성공해야 손 clone을 삭제하고 fetch용 clone으로 교체합니다. 실패하면 손 clone과 스냅샷을 보존하며 로그를 확인해야 합니다. 실제 설치·재부팅 검증은 별도의 운영 QA입니다.

설치가 쓰는 runtime 설정은 다음과 같습니다. 포트를 바꾸면 두 localhost URL도 함께 바뀝니다.

```dotenv
AUTHOR_SALT_PATH=/배포루트/shared/data/.author_salt
STORAGE=local
LOCAL_DATA_DIR=/배포루트/shared/data
LABEL_GPT_BACKEND=codex_exec
JEV_BACKEND=fake
CORS_ORIGINS=http://localhost:3400
NEXT_PUBLIC_API_URL=http://localhost:8400
```

운영 스크립트는 `$APP_ROOT/ops/`에 복사되어 코드 롤백과 독립적으로 남습니다. `ops_outdated: true` 로그가 나오면 새 릴리스의 `ops/macmini/install.sh`로 재설치합니다. 기존 current가 있으면 설치기는 코드를 바꾸지 않고 스크립트·잡을 갱신합니다. NEXT_PUBLIC 값 변경은 프론트 재빌드가 필요하므로 다른 커밋을 정식 배포해야 합니다.

## 수동 명령

```bash
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" status
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" deploy
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" deploy <sha>
APP_ROOT="$HOME/srv/dcx-agent" "$HOME/srv/dcx-agent/ops/dcxctl" rollback
```

`status`는 current, `/health`, last-failed-sha, 이력 마지막 3줄, 배포 로그 마지막 5줄을 출력합니다. `deploy`는 지정 커밋(생략하면 origin/main)의 실패 표시를 지운 후 기존 배포 흐름과 CI 판정을 실행합니다. 단축 SHA도 정규화합니다. 다른 배포가 잠금을 가진 동안에는 실패 표시를 지우지 않습니다.

`rollback`은 현재 이력의 바로 전 릴리스와 **현재 릴리스 배포 직전** 스냅샷을 사용합니다. 중지 → sessions/work 복원 → current 전환 → 시작 → 상태 확인 순서입니다. 롤백 전 SHA를 last-failed-sha에 기록하고 이력 마지막 행을 제거하므로 반복 호출로 이전 단계에 되돌아갈 수 있습니다. 이전 릴리스나 스냅샷이 없으면 변경 없이 `되돌릴 버전이 없습니다`로 실패합니다. 복원한 버전도 상태 확인에 실패하면 `unhealthy-both`를 남깁니다.

롤백은 코드와 sessions/work만 되돌립니다. 큰 파일·캐시·모델은 복원하지 않습니다. 롤백 뒤 화면이 이상하면 그 세션을 새 버전으로 다시 시작하세요. 배포 중 작업자는 종료되며, 기존 죽은 작업자 감지 로직이 상태를 갱신합니다.

**운영 권한 확인 필요:** 현재 공용 lib.sh는 `launchctl disable/enable/kickstart system/...`을 직접 호출합니다. UserName으로 권한을 낮춘 운영 deploy 잡이 이 동작을 수행할 수 있는지 해결·검증해야 합니다. T3에서 T2 파일을 수정하지 않았으며, 이 문제를 해결하기 전 운영 자동 배포가 정상이라고 간주하면 안 됩니다. QA 사용자 에이전트는 자신의 gui 도메인을 사용합니다.

## QA 사용자 에이전트

```bash
APP_ROOT="$HOME/srv/dcx-agent-qa" /bin/bash ops/macmini/install.sh \
  --qa --dry-run --output-dir /tmp/dcx-qa-plan
# 데이터와 app.env, salt 준비 후 별도 QA에서만 실행:
APP_ROOT="$HOME/srv/dcx-agent-qa" /bin/bash ops/macmini/install.sh --qa
```

QA는 sudo 없이 `~/Library/LaunchAgents/ai.person-a.dcx-agent-qa.{deploy,api,web}.plist`를 등록합니다. 기본 포트는 8401/3401, 도메인은 `gui/<uid>`입니다. API 잡 시작 로그에 `codex --version`을 남기므로 launchd 아래 PATH와 사용자 로그인 환경을 확인할 수 있습니다. 설치된 `shared/launch.env`는 dcxctl에 같은 도메인·포트를 전달합니다. 테스트 개발 중에는 실제 QA 설치나 아래 정리 명령을 실행하지 않습니다.

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

종료 대상은 해당 api/web PID 자손, 지정 포트의 리스너, 배포 루트 releases 아래에서 실행 중인 Python 작업자입니다. 3000·3310·3311·8310·8311 포트는 설치 대상에서 제외합니다. internal-app 및 사용자 데모 서버는 건드리지 않습니다.

테스트 훅은 T2의 `DCX_BUILD_CMD`, `DCX_RESTART_CMD`, `DCX_CI_API`, `DCX_HEALTH_API`, `DCX_HEALTH_WEB`, `DCX_HEALTH_TIMEOUT`, `DCX_REPO_URL`, `DCX_API_PORT`, `DCX_WEB_PORT`, `DCX_FORCE_UNHEALTHY_SHA`, `DCX_BASH`, `DCX_PATH`를 사용합니다. 실제 설치에서는 가짜 훅을 사용하지 않습니다.

```bash
DCX_BASH=/bin/bash backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider
backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
```
