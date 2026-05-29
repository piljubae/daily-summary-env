#!/bin/bash
PROJECT_DIR="/Users/pilju.bae/daily-summary-env"
cd "$PROJECT_DIR"
LOG_FILE="$PROJECT_DIR/automation.log"
echo "--- EOD Process: $(date) ---" >> "$LOG_FILE"
./venv/bin/python3 eod_processor.py --process >> "$LOG_FILE" 2>&1
echo "--- EOD Process Done: $(date) ---" >> "$LOG_FILE"
