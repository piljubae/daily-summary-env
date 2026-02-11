#!/bin/bash

# 프로젝트 디렉토리 설정
PROJECT_DIR="/Users/pilju.bae/daily-summary-env"
cd "$PROJECT_DIR"

# 로그 파일 경로 설정
LOG_FILE="$PROJECT_DIR/automation.log"

echo "------------------------------------------" >> "$LOG_FILE"
echo "Daily Summary Automation Started: $(date)" >> "$LOG_FILE"

# 가상 환경의 Python으로 스크립트 실행
# 어제 날짜를 기본값으로 실행하므로 별도 인자 불필요
./venv/bin/python3 daily_summary.py >> "$LOG_FILE" 2>&1

echo "Daily Summary Automation Finished: $(date)" >> "$LOG_FILE"
echo "------------------------------------------" >> "$LOG_FILE"
