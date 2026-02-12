#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack message formatter."""

import re
import sys
import requests

from config import CONFIG


def send_to_slack(markdown_content):
    """Slack Incoming Webhook으로 보고서 전송

    마크다운을 Slack mrkdwn 형식으로 변환하여 전송합니다.
    """
    webhook_url = CONFIG.get("slack_webhook_url", "")
    if not webhook_url:
        return False

    # 마크다운 → Slack mrkdwn 변환
    slack_text = markdown_content
    
    # [텍스트](URL) -> <URL|텍스트> 변환 (Slack 형식)
    # 괄호 사이 공백 허용 및 URL 매칭 개선
    slack_text = re.sub(r'\[([^\]]+)\]\s*\(([^)]+)\)', r'<\2|\1>', slack_text)
    
    # Fallback: [Title](URL) 형식이 아니라 Title (URL) 형식으로 온 경우 (주로 AI 요약)
    # 예: - 🔗 GitHub PR (https://...) -> - 🔗 <https://...|GitHub PR>
    slack_text = re.sub(r'(🔗.*?)\s*\((https?://[^)]+)\)', r'<\2|\1>', slack_text)
    
    slack_text = re.sub(r'^# (.+)$', r'*\1*', slack_text, flags=re.MULTILINE)       # h1 → bold
    slack_text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', slack_text)                       # **bold** → *bold*
    slack_text = re.sub(r'^\- ', '• ', slack_text, flags=re.MULTILINE)               # - → •
    slack_text = re.sub(r'^  📎', '    📎', slack_text, flags=re.MULTILINE)          # 들여쓰기 보정

    payload = {
        "text": slack_text,
        "unfurl_links": False,
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ Slack 전송 실패: {e}", file=sys.stderr)
        return False
