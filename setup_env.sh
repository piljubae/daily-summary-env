#!/bin/bash
# Gemini API 키 설정 스크립트

echo "🔑 Gemini API 키 설정"
echo ""
echo "API 키를 발급받으세요: https://aistudio.google.com/app/apikey"
echo ""
read -p "Gemini API Key를 입력하세요: " api_key

if [ -z "$api_key" ]; then
    echo "❌ API 키가 입력되지 않았습니다."
    exit 1
fi

read -p "Slack Webhook URL을 입력하세요 (엔터 시 생략): " slack_webhook

# .env 파일 생성
cat > .env << ENVEOF
# Gemini API Key
GEMINI_API_KEY=$api_key

# Slack Webhook URL
SLACK_WEBHOOK_URL=$slack_webhook
ENVEOF

echo "✅ .env 파일이 생성되었습니다."
echo ""
echo "사용 방법:"
echo "  source .env"
echo "  python3 daily_summary.py --today"
echo ""
echo "또는 직접 실행:"
echo "  GEMINI_API_KEY=\$GEMINI_API_KEY python3 daily_summary.py --today"
