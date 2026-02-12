#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration management for daily summary."""

import os
from pathlib import Path


def load_env():
    """로컬 .env 파일이 있으면 환경변수로 로드 (GitHub에는 올라가지 않음)"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        loaded_count = 0
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # 따옴표 제거 (예: "value" -> value)
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value
                    loaded_count += 1
        if loaded_count > 0:
            print(f"✅ .env 파일에서 {loaded_count}개의 설정을 로드했습니다.")
        return True
    return False


# 스크립트 실행 시 즉시 .env 로드
load_env()

CONFIG = {
    # ActivityWatch API 연결 정보
    "api_host": "127.0.0.1",
    "api_port": 5600,

    # 출력 디렉토리 (기본값: 홈 디렉토리/daily-summaries/)
    "output_dir": str(Path.home() / "daily-summaries"),

    # 최소 표시 기간 (초 단위, 이보다 작은 활동은 제외)
    "min_duration_seconds": 10,

    # 상위 표시 개수
    "top_apps_count": 15,
    "top_urls_count": 10,

    # 생산성 시간대 정의 (시간 범위, 24시간 형식)
    "productive_hours": [(9, 12), (14, 18)],  # 9-12시, 14-18시

    # Cowork 세션 로그 디렉토리
    # macOS: ~/Library/Application Support/Claude/projects/
    # Linux: ~/.config/Claude/projects/
    # 빈 문자열이면 Cowork 요약 생략
    "cowork_log_dir": str(Path.home() / "Library" / "Application Support" / "Claude" / "projects"),

    # Slack Incoming Webhook URL
    # Slack 앱 → Incoming Webhooks 에서 발급
    # 빈 문자열이면 Slack 전송 생략 (마크다운 파일만 생성)
    "slack_webhook_url": "",  # 환경변수 SLACK_WEBHOOK_URL 또는 직접 입력
    
    # Gemini API Key (AI 요약용)
    # 빈 문자열이면 AI 요약 생략
    "gemini_api_key": "",  # 환경변수 GEMINI_API_KEY 또는 직접 입력
}
