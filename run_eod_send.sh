#!/bin/bash
PROJECT_DIR="/Users/pilju.bae/daily-summary-env"
cd "$PROJECT_DIR"
LOG_FILE="$PROJECT_DIR/automation.log"
echo "--- EOD Send: $(date) ---" >> "$LOG_FILE"
./venv/bin/python3 eod_processor.py --send >> "$LOG_FILE" 2>&1
echo "--- EOD Send Done: $(date) ---" >> "$LOG_FILE"
