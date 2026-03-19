#!/bin/bash
# ============================================================
# DCX Agent — EC2 배포 스크립트 (Ubuntu 22.04)
# 사용법: ssh ubuntu@ec2-ip 접속 후 실행
#   git clone <repo> ~/dcx_agent
#   cd ~/dcx_agent && ./scripts/deploy.sh
# ============================================================

set -e

APP_DIR="$HOME/dcx_agent"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"

echo "============================================"
echo "  DCX Agent EC2 배포 시작"
echo "============================================"

# ──────────────────────────────────────────
# 1. 시스템 패키지 업데이트
# ──────────────────────────────────────────
echo ""
echo "📦 [1/7] 시스템 패키지 업데이트..."
sudo apt update && sudo apt upgrade -y

# ──────────────────────────────────────────
# 2. Python 3.12 설치
# ──────────────────────────────────────────
echo ""
echo "🐍 [2/7] Python 3.12 설치..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# ──────────────────────────────────────────
# 3. Node.js 20 LTS 설치
# ──────────────────────────────────────────
echo ""
echo "📗 [3/7] Node.js 20 LTS 설치..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi
echo "   Node.js: $(node --version)"
echo "   npm: $(npm --version)"

# ──────────────────────────────────────────
# 4. Nginx 설치
# ──────────────────────────────────────────
echo ""
echo "🌐 [4/7] Nginx 설치 및 설정..."
sudo apt install -y nginx

# Nginx 설정 복사
sudo cp "$APP_DIR/nginx/dcx-agent.conf" /etc/nginx/sites-available/dcx-agent
sudo ln -sf /etc/nginx/sites-available/dcx-agent /etc/nginx/sites-enabled/dcx-agent
sudo rm -f /etc/nginx/sites-enabled/default

# Nginx 설정 검증
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# ──────────────────────────────────────────
# 5. 백엔드 설정
# ──────────────────────────────────────────
echo ""
echo "⚙️  [5/7] 백엔드 설정..."
cd "$BACKEND_DIR"

# venv 생성 + 의존성 설치
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# ──────────────────────────────────────────
# 6. 프론트엔드 빌드
# ──────────────────────────────────────────
echo ""
echo "🏗️  [6/7] 프론트엔드 빌드..."
cd "$FRONTEND_DIR"
npm install
npm run build

# standalone에 static/public 복사 (Next.js standalone 요구사항)
if [ -d ".next/standalone" ]; then
    cp -r public .next/standalone/ 2>/dev/null || true
    cp -r .next/static .next/standalone/.next/ 2>/dev/null || true
fi

# ──────────────────────────────────────────
# 7. .env 복호화 (암호화된 파일이 있는 경우)
# ──────────────────────────────────────────
echo ""
echo "🔐 [7/7] 환경변수 설정..."
cd "$APP_DIR"

if [ -f ".env.enc" ] && [ ! -f ".env" ]; then
    echo "   .env.enc 발견. 복호화합니다..."
    ./scripts/decrypt-env.sh
elif [ -f ".env" ]; then
    echo "   .env 파일이 이미 존재합니다."
else
    echo "   ⚠️  .env 파일이 없습니다!"
    echo "   .env.enc를 복호화하거나, 직접 .env 파일을 생성해주세요."
    echo "   필요한 환경변수:"
    echo "     S3_BUCKET, S3_REGION"
    echo "     NAVER_CLIENT_ID, NAVER_CLIENT_SECRET"
    echo "     CLAUDE_API_KEY"
    echo "     PINECONE_API_KEY"
    echo "     VOYAGE_API_KEY"
    echo "     CORS_ORIGINS (프론트엔드 도메인)"
fi

# ──────────────────────────────────────────
# systemd 서비스 등록
# ──────────────────────────────────────────
echo ""
echo "🚀 systemd 서비스 등록..."
sudo cp "$APP_DIR/scripts/systemd/dcx-backend.service" /etc/systemd/system/
sudo cp "$APP_DIR/scripts/systemd/dcx-frontend.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dcx-backend dcx-frontend
sudo systemctl restart dcx-backend dcx-frontend

# ──────────────────────────────────────────
# 완료
# ──────────────────────────────────────────
echo ""
echo "============================================"
echo "  ✅ 배포 완료!"
echo "============================================"
echo ""
echo "  서비스 상태 확인:"
echo "    sudo systemctl status dcx-backend"
echo "    sudo systemctl status dcx-frontend"
echo ""
echo "  로그 확인:"
echo "    sudo journalctl -u dcx-backend -f"
echo "    sudo journalctl -u dcx-frontend -f"
echo ""
echo "  Nginx 로그:"
echo "    sudo tail -f /var/log/nginx/access.log"
echo "    sudo tail -f /var/log/nginx/error.log"
echo ""
echo "  접속: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'EC2-PUBLIC-IP')"
echo ""
