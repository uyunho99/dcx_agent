#!/bin/bash
# .env.enc 파일을 복호화하여 .env 복원
# 사용법: ./scripts/decrypt-env.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENC_FILE="$PROJECT_ROOT/.env.enc"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENC_FILE" ]; then
    echo "❌ .env.enc 파일을 찾을 수 없습니다: $ENC_FILE"
    echo "   먼저 git pull로 .env.enc를 받아주세요."
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    echo "⚠️  기존 .env 파일이 존재합니다."
    read -p "   덮어쓰시겠습니까? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "   취소되었습니다."
        exit 0
    fi
fi

echo "🔓 .env.enc 파일을 복호화합니다..."
echo "   입력: $ENC_FILE"
echo "   출력: $ENV_FILE"
echo ""

openssl enc -aes-256-cbc -d -pbkdf2 -iter 100000 \
    -in "$ENC_FILE" \
    -out "$ENV_FILE"

echo ""
echo "✅ 복호화 완료: .env"
echo "   API 키가 복원되었습니다."
