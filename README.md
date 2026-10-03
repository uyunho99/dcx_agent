# DCX Agent

Naver Cafe 데이터 기반 소비자 인사이트 분석 파이프라인.
키워드 생성부터 크롤링, ML 분류, 클러스터링, 페르소나 도출까지 8단계 자동화 시스템.

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | FastAPI · Gunicorn · Scikit-learn |
| Frontend | Next.js 16 · React 19 · Zustand · Tailwind CSS · D3.js |
| AI/ML | Jev · GPT(Codex/API) · PyTorch 앙상블 · Voyage AI(임베딩) · 로컬 float16 벡터 검색 |
| 인프라 | AWS S3 · Naver Cafe API · Nginx · systemd |

## 프로젝트 구조

```
dcx_agent/
├── backend/                  # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py           # 앱 진입점
│   │   ├── config.py         # 환경변수 설정
│   │   ├── models/           # Pydantic 스키마
│   │   ├── routers/          # API 엔드포인트
│   │   ├── services/         # 비즈니스 로직
│   │   ├── jobs/             # 비동기 작업 관리
│   │   └── utils/            # 유틸리티
│   └── requirements.txt
│
├── frontend/                 # Next.js 프론트엔드
│   ├── src/
│   │   ├── app/pipeline/     # 8단계 파이프라인 페이지
│   │   ├── components/       # UI 컴포넌트
│   │   ├── lib/              # API 클라이언트, 타입
│   │   └── stores/           # Zustand 상태 관리
│   └── package.json
│
├── nginx/                    # Nginx 리버스 프록시 설정
├── scripts/                  # 배포·운영 스크립트
│   ├── deploy.sh             # EC2 원클릭 배포
│   ├── encrypt-env.sh        # .env 암호화
│   ├── decrypt-env.sh        # .env 복호화
│   └── systemd/              # 서비스 파일
└── .env.enc                  # 암호화된 환경변수
```

## 파이프라인 흐름

```
시작 → 키워드 → 크롤링 → 전처리 → 라벨링 → 학습 → 클러스터링 → 페르소나
```

| 단계 | 설명 |
|------|------|
| 시작 | 세션 생성, 제품명·문제 정의·타겟 입력 |
| 키워드 | Claude AI로 4라운드 키워드 생성·수렴 |
| 크롤링 | Naver Cafe에서 소비자 게시글 대량 수집 |
| 전처리 | 광고·중복·노이즈 필터링 |
| 라벨링 | 2% 샘플 수동 라벨링 (관련/무관) |
| 학습 | 3모델 앙상블로 전체 데이터 자동 분류 |
| 클러스터링 | Voyage AI 임베딩 + K-means 주제 그룹화 |
| 페르소나 | Claude AI가 클러스터별 소비자 페르소나 도출 |

---

# 로컬 설치 가이드

## 사전 요구사항

- **Python 3.12** (`python3.12`)
- **Node.js 20+** / npm
- **Git**

## 1. 레포지토리 클론

```bash
git clone https://github.com/uyunho99/dcx_agent.git
cd dcx_agent
```

## 2. 환경변수 설정

레포지토리 루트에서 예제 파일을 복사하고 필요한 외부 API 설정을 입력합니다.

```bash
cp .env.example .env
```

저장소 기본값은 `STORAGE=local`입니다. AWS 키 없이 로컬 디스크를 사용하며,
`LOCAL_DATA_DIR=data`가 데이터 경로입니다(백엔드에서 실행하면 `backend/data/`).
API 키는 필요한 연동에만 설정하고 `.env`는 커밋하지 않습니다.
OpenAI를 사용하려면 `OPENAI_API_KEY`와 `OPENAI_MODEL`을 지정합니다.

## 3. 백엔드 설치 및 실행

레포지토리 루트에서 Python 3.12 가상환경 `backend/.venv`를 생성합니다.

```bash
python3.12 -m venv backend/.venv
cd backend
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
crawl4ai-setup
uvicorn app.main:app --reload --port 8000
```

`crawl4ai-setup`은 크롤링에 필요한 Playwright Chromium을 설치합니다.
백엔드: `http://localhost:8000`, 헬스체크: `http://localhost:8000/health`.

## 4. 프론트엔드 설치 및 실행

별도 터미널에서 레포지토리 루트를 기준으로 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

브라우저에서 `http://localhost:3000`에 접속하여 파이프라인 시작 페이지를 확인합니다.

## 5. 테스트

테스트는 실제 `.env`, API 키, 네트워크, codex 설치 없이 실행됩니다.
레포지토리 루트에서:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

또는 `backend/`에서:

```bash
cd backend
.venv/bin/python -m pytest -q
```

---

# AWS EC2 배포 가이드

## 권장 사양

| 항목 | 권장 | 비고 |
|------|------|------|
| 인스턴스 | t3.small (2vCPU, 2GB) + 2GB swap | ML 앙상블 + 크롤링 실행 |
| 스토리지 | 20GB gp3 | OS + 런타임 + 빌드 산출물 |
| OS | Ubuntu 22.04 LTS | |
| 보안 그룹 | 인바운드 80, 443, 22 | Nginx가 내부 포트 프록시 |

## 1. EC2 인스턴스 생성

1. AWS 콘솔 → EC2 → **인스턴스 시작**
2. AMI: **Ubuntu Server 22.04 LTS**
3. 인스턴스 유형: **t3.small**
4. 키 페어 생성 또는 기존 키 선택
5. 보안 그룹 설정:

| 유형 | 포트 | 소스 | 용도 |
|------|------|------|------|
| SSH | 22 | 내 IP | SSH 접속 |
| HTTP | 80 | 0.0.0.0/0 | 웹 서비스 |
| HTTPS | 443 | 0.0.0.0/0 | SSL 웹 서비스 |

> 3000, 8000 포트는 열지 않습니다. Nginx가 80번 포트에서 내부로 프록시합니다.

## 2. EC2 접속 및 초기 설정

```bash
ssh -i your-key.pem ubuntu@<EC2-퍼블릭-IP>

# Swap 2GB 추가 (t3.small 메모리 보완 — sklearn 학습 시 필요)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 레포 클론
git clone https://github.com/uyunho99/dcx_agent.git ~/dcx_agent
cd ~/dcx_agent
```

## 3. 원클릭 배포

```bash
./scripts/deploy.sh
```

이 스크립트가 자동으로 수행하는 작업:

| 순서 | 작업 | 설명 |
|------|------|------|
| 1 | 시스템 업데이트 | `apt update && upgrade` |
| 2 | Python 3.12 설치 | deadsnakes PPA |
| 3 | Node.js 20 설치 | NodeSource |
| 4 | Nginx 설치 및 설정 | 리버스 프록시 구성 |
| 5 | 백엔드 설정 | venv 생성 + pip install |
| 6 | 프론트엔드 빌드 | npm install + next build (standalone) |
| 7 | .env 설정 | .env.enc 복호화 또는 안내 |
| - | systemd 등록 | 백엔드/프론트 자동 시작 + 자동 재시작 |

## 4. .env 프로덕션 설정

배포 스크립트 실행 후, `.env`에 **프로덕션 CORS** 설정을 추가합니다:

```bash
# .env.enc 복호화가 안 된 경우 직접 생성
nano ~/.dcx_agent/.env

# CORS_ORIGINS 추가 (본인 도메인 또는 EC2 IP)
echo "CORS_ORIGINS=http://<EC2-퍼블릭-IP>" >> ~/dcx_agent/.env

# 백엔드 재시작하여 반영
sudo systemctl restart dcx-backend
```

## 5. 접속 확인

```bash
# 서비스 상태 확인
sudo systemctl status dcx-backend
sudo systemctl status dcx-frontend

# 브라우저에서 접속
# http://<EC2-퍼블릭-IP>
```

## 아키텍처

```
사용자 브라우저
      │
      ▼
   [ Nginx :80 ]
      │
      ├── /          → Next.js (127.0.0.1:3000)
      ├── /api/*     → FastAPI (127.0.0.1:8000)
      └── /health    → FastAPI 헬스체크
```

---

## 운영 명령어

### 서비스 관리

```bash
# 상태 확인
sudo systemctl status dcx-backend
sudo systemctl status dcx-frontend

# 재시작
sudo systemctl restart dcx-backend
sudo systemctl restart dcx-frontend

# 중지 / 시작
sudo systemctl stop dcx-backend
sudo systemctl start dcx-backend
```

### 로그 확인

```bash
# 백엔드 로그 (실시간)
sudo journalctl -u dcx-backend -f

# 프론트엔드 로그
sudo journalctl -u dcx-frontend -f

# Nginx 로그
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 코드 업데이트 (재배포)

```bash
cd ~/dcx_agent

# 최신 코드 가져오기
git pull origin main

# 백엔드 의존성 변경 시
cd backend && source venv/bin/activate && pip install -r requirements.txt && deactivate

# 프론트엔드 변경 시
cd ~/dcx_agent/frontend && npm install && npm run build
cp -r public .next/standalone/ 2>/dev/null || true
cp -r .next/static .next/standalone/.next/ 2>/dev/null || true

# 서비스 재시작
sudo systemctl restart dcx-backend dcx-frontend
```

### HTTPS 설정 (선택)

도메인이 있는 경우 Let's Encrypt로 무료 SSL 인증서 발급:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 자동 갱신 확인
sudo certbot renew --dry-run
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `S3_BUCKET` | O | AWS S3 버킷 이름 |
| `S3_REGION` | O | S3 리전 |
| `NAVER_CLIENT_ID` | O | Naver 개발자 Client ID |
| `NAVER_CLIENT_SECRET` | O | Naver 개발자 Client Secret |
| `CLAUDE_API_KEY` | O | Anthropic Claude API 키 |
| `VOYAGE_API_KEY` | O | Voyage AI 임베딩 API 키 |
| `CORS_ORIGINS` | - | 허용 도메인 (기본: `*`, 프로덕션: 도메인 지정) |
| `STORAGE` / `LOCAL_DATA_DIR` | - | 저장 방식 (`local`) / 로컬 데이터 경로 (`data`); 3~5단계와 검색은 로컬 벡터 재사용 |
| `EMBED_BACKEND` | - | `voyage` (기본) 또는 오프라인 `fake` |
| `EMBED_MODEL` / `EMBED_DIM` | - | `voyage-4` / `1024` |
| `JEVMODEL_API_KEY` | Jev HTTP 사용 시 | Jev API 키; 여러 키는 쉼표로 구분 |
| `JEV_BACKEND` / `JEV_MODEL` | - | `http` 또는 오프라인 `fake` / `jev-latest` |
| `JEV_RATE_PER_MIN` | - | 키당 분당 요청 수 (`120`) |
| `LABEL_FAKE_JEV_CROSS` | - | 기본 `false`; 테스트 · 오프라인 QA 전용: fake Jev를 실제 교차 판정 라벨러로 취급 |
| `LABEL_GPT_BACKEND` | - | `codex_exec` (기본), `openai_api`, 오프라인 `fake` |
| `LABEL_BATCH_SIZE` / `LABEL_CONCURRENCY` | - | GPT 배치 문서 수 (`20`) / 동시 실행 수 (`4`) |
| `EVIDENCE_LLM_CONCURRENCY` | - | 7단계 근거 탐색 LLM 동시 호출 수 (`4`, `1`이면 순차 실행) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI API 사용 시 | API 인증 및 모델 선택 |
| `CODEX_BIN` / `CODEX_PROFILE` / `CODEX_TIMEOUT_S` | Codex 사용 시 | 실행 파일 (`codex`), 프로필 (`dcx-worker`), 제한 시간 (`600`초) |
| `KNOWN_THETA` | - | Known Insight 유사도 제외 기준 (`0.85`) |
| `MODEL_CUT_LOW` / `MODEL_CUT_HIGH` | - | 모델의 사람 검수 구간 (`0.2` / `0.8`) |
| `MONITOR_RATE` / `MONITOR_WARN` | - | 모델 감시 비율 (`0.01`) / 괴리 경고 기준 (`0.15`) |
| `HEAD_MIN_SAMPLES` | - | 헤드별 최소 학습 표본 수 (`30`) |
| `AUDIT_FIRST` / `AUDIT_EVERY` | - | 첫 감사 채택 수 (`1000`) / 이후 간격 (`10000`) |
| `AUDIT_SIZE` / `AUDIT_REISSUE` | - | 감사 표본 수 (`50`) / 재판정 수 (`2`) |
| `KAPPA_FLOOR` | - | 태그 정의 점검 기준 (`0.75`) |

Jev 키가 없거나 `JEV_BACKEND=fake`이면 라벨링은 GPT 단독 판정으로 시작합니다(D-340). Jev 실행 없이 GPT 판정을 그대로 채택하고 confidence는 비웁니다. Jev를 연결한 뒤 새 버전에서 라벨링을 시작하면 교차 판정합니다.

3단계에서 만든 로컬 벡터로 Core · Supporting 문서를 검색하며, Known Insight 필터를 적용합니다.
별도의 벡터 DB 업로드나 API 키가 필요하지 않습니다. 오프라인 판정·임베딩 점검에는
`EMBED_BACKEND=fake`, `JEV_BACKEND=fake`, `LABEL_GPT_BACKEND=fake`를 함께 설정하세요.

### .env 암호화/복호화

```bash
# 암호화 (.env → .env.enc)
./scripts/encrypt-env.sh

# 복호화 (.env.enc → .env)
./scripts/decrypt-env.sh
```

---

## 상세 문서

- [파이프라인 단계별 구성](frontend/PIPELINE.md) — 8단계 파이프라인 상세 설명
- [백엔드 구조](backend/BACKEND.md) — 폴더 구조, 함수 시그니처, API 엔드포인트
