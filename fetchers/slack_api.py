#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack Web API helpers.

EOD 리포트 전송 흐름에서 사용한다: DM 채널 열기, 메시지 전송, 스레드 답글 조회.
(슬랙 토픽 md 갱신·요약은 외부 스킬 slack-mention-daily-update가 담당한다.)
"""

import sys
import time

import requests


_SLACK_API = "https://slack.com/api"


def _get(endpoint, token, params=None):
    """Slack API GET 호출. rate-limit(429) 시 자동 재시도."""
    url = f"{_SLACK_API}/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"  ⏳ Slack rate-limit, {retry_after}s 대기...")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            print(f"  ⚠️ Slack API 오류 ({endpoint}): {data.get('error')}")
            return None
        return data
    return None


def _get_thread_replies(bot_token, channel_id, thread_ts):
    """conversations.replies로 스레드 전체 메시지 조회."""
    messages = []
    cursor = None

    while True:
        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor

        data = _get("conversations.replies", bot_token, params)
        if not data:
            break

        for msg in data.get("messages", []):
            messages.append({
                "user": msg.get("user", ""),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", ""),
            })

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return messages


# ---------------------------------------------------------------------------
# EOD helpers
# ---------------------------------------------------------------------------

def open_dm_channel(bot_token: str, user_id: str) -> str | None:
    """conversations.open으로 DM 채널을 열거나 기존 채널 ID 반환."""
    url = f"{_SLACK_API}/conversations.open"
    headers = {"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json={"users": user_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data.get("channel", {}).get("id")
    except Exception as e:
        print(f"⚠️ conversations.open 실패: {e}", file=sys.stderr)
    return None


def post_message(
    bot_token: str,
    channel_id: str,
    text: str,
    thread_ts: str | None = None,
) -> tuple[str, str] | tuple[None, None]:
    """Slack 채널에 메시지 전송. (channel_id, ts) 반환."""
    url = f"{_SLACK_API}/chat.postMessage"
    headers = {"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"}
    payload: dict = {"channel": channel_id, "text": text, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    for attempt in range(3):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", 5)))
            continue
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data["channel"], data["ts"]
        print(f"⚠️ chat.postMessage 실패: {data.get('error')}", file=sys.stderr)
        return None, None
    return None, None


def read_thread_replies(bot_token: str, channel_id: str, thread_ts: str) -> list[dict]:
    """스레드 답글 반환 (루트 메시지 제외)."""
    messages = _get_thread_replies(bot_token, channel_id, thread_ts)
    return messages[1:] if messages else []
