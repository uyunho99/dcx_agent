#!/bin/bash
# .env 파일을 AES-256-CBC로 암호화하여 .env.enc 생성
# 사용법: ./scripts/encrypt-env.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
ENC_FILE="$PROJECT_ROOT/.env.enc"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env 파일을 찾을 수 없습니다: $ENV_FILE"
    exit 1
fi

echo "🔐 .env 파일을 암호화합니다..."
echo "   입력: $ENV_FILE"
echo "   출력: $ENC_FILE"
echo ""

openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
    -in "$ENV_FILE" \
    -out "$ENC_FILE"

echo ""
echo "✅ 암호화 완료: .env.enc"
echo "   이 파일을 git에 커밋할 수 있습니다."
echo "   복호화: ./scripts/decrypt-env.sh"
