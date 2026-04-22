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

    # 출력 디렉토리 (환경변수 OUTPUT_DIR 또는 기본값 ~/daily-summaries)
    "output_dir": os.environ.get("OUTPUT_DIR", str(Path.home() / "daily-summaries")),

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

    # Jira 설정 (할일 조회용)
    "jira_url": os.environ.get("JIRA_URL", ""),
    "jira_email": os.environ.get("JIRA_EMAIL", ""),
    "jira_api_token": os.environ.get("JIRA_API_TOKEN", ""),
    "jira_project_key": os.environ.get("JIRA_PROJECT_KEY", "KMA"),

    # macOS Calendar 설정
    # 업무 캘린더 이름 목록 (macOS 캘린더 앱에 표시되는 이름)
    # 비어있으면 최초 실행 시 사용자에게 선택을 요청하고 .env에 저장
    "gcal_work_calendar_names": [n.strip() for n in os.environ.get("GCAL_WORK_CALENDARS", "").split(",") if n.strip()],

    # 반복(정규) 이벤트 기본 제외 여부
    # True: 매일/매주 반복되는 정규 미팅 제외 (데일리스크럼 등)
    "gcal_exclude_recurring": os.environ.get("GCAL_EXCLUDE_RECURRING", "true").lower() != "false",

    # 반복 이벤트라도 포함할 이벤트 이름 키워드 (화이트리스트)
    # 예: ["1:1", "주간OKR"] — 해당 키워드가 포함된 반복 미팅은 포함
    "gcal_recurring_whitelist": [],

    # Slack 요약 파일 디렉토리
    # 외부 자동화가 매일 오전 9시에 Slack 멘션 스레드 요약을 .md 파일로 생성
    # 빈 문자열이면 Slack 요약 섹션 생략
    "slack_summary_dir": os.environ.get("SLACK_SUMMARY_DIR", str(Path.home() / "Documents" / "Claude Cowork" / "Slack")),

    # Slack API 설정 (직접 연동)
    # search.messages는 User Token 필요 (Bot Token으로 불가)
    "slack_user_token": os.environ.get("SLACK_USER_TOKEN", ""),
    "slack_bot_token": os.environ.get("SLACK_BOT_TOKEN", ""),
    # 모니터링할 채널 ID 목록 (콤마 구분)
    "slack_watch_channels": [c.strip() for c in os.environ.get("SLACK_WATCH_CHANNELS", "").split(",") if c.strip()],
}
