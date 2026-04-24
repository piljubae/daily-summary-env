#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack Web API를 통한 스레드 수집.

User Token(xoxp-)으로 멘션 검색, Bot Token(xoxb-)으로 스레드 조회.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import CONFIG


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


def _get_my_user_id(user_token):
    """auth.test로 내 User ID 조회."""
    data = _get("auth.test", user_token)
    return data["user_id"] if data else None


def _search_mentions(user_token, user_id, since_date):
    """search.messages로 내 멘션 검색.

    Args:
        user_token: xoxp- 토큰
        user_id: 내 Slack User ID
        since_date: 이 날짜 이후의 메시지 검색 (YYYY-MM-DD)

    Returns:
        list[dict]: [{"channel_id": str, "thread_ts": str}, ...]
    """
    query = f"<@{user_id}> after:{since_date}"
    threads = []
    page = 1

    while True:
        data = _get("search.messages", user_token, {
            "query": query,
            "sort": "timestamp",
            "sort_dir": "asc",
            "count": 100,
            "page": page,
        })
        if not data:
            break

        matches = data.get("messages", {}).get("matches", [])
        if not matches:
            break

        for msg in matches:
            channel_id = msg.get("channel", {}).get("id", "")
            # 스레드의 root ts: thread_ts가 있으면 사용, 없으면 ts 자체가 root
            thread_ts = msg.get("thread_ts") or msg.get("ts", "")
            if channel_id and thread_ts:
                threads.append({
                    "channel_id": channel_id,
                    "thread_ts": thread_ts,
                })

        paging = data.get("messages", {}).get("paging", {})
        if page >= paging.get("pages", 1):
            break
        page += 1

    # 중복 제거 (같은 스레드에서 여러 멘션 가능)
    seen = set()
    unique = []
    for t in threads:
        key = (t["channel_id"], t["thread_ts"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def _get_channel_threads(bot_token, channel_id, oldest_ts):
    """conversations.history로 채널의 최근 메시지 → 스레드 루트 수집."""
    threads = []
    cursor = None

    while True:
        params = {
            "channel": channel_id,
            "oldest": oldest_ts,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        data = _get("conversations.history", bot_token, params)
        if not data:
            break

        for msg in data.get("messages", []):
            if msg.get("thread_ts") == msg.get("ts"):
                threads.append({
                    "channel_id": channel_id,
                    "thread_ts": msg["ts"],
                })

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return threads


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


def _resolve_user_names(bot_token, messages):
    """메시지 내 user ID를 display name으로 치환."""
    user_ids = {m["user"] for m in messages if m["user"]}
    name_cache = {}

    for uid in user_ids:
        if uid in name_cache:
            continue
        data = _get("users.info", bot_token, {"user": uid})
        if data:
            profile = data.get("user", {}).get("profile", {})
            name_cache[uid] = (
                profile.get("display_name")
                or profile.get("real_name")
                or uid
            )
        else:
            name_cache[uid] = uid

    for msg in messages:
        msg["user_name"] = name_cache.get(msg["user"], msg["user"])

    return messages


def _get_channel_name(bot_token, channel_id):
    """conversations.info로 채널 이름 조회."""
    data = _get("conversations.info", bot_token, {"channel": channel_id})
    if data:
        return data.get("channel", {}).get("name", channel_id)
    return channel_id


def _load_meta(summary_dir):
    """스레드-파일 매핑 메타데이터 로드."""
    meta_path = Path(summary_dir) / ".slack_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_fetched_ts": "0", "threads": {}}


def _get_since_ts(meta, summary_dir):
    """마지막 조회 시점의 timestamp 반환."""
    ts = meta.get("last_fetched_ts", "0")
    if ts and ts != "0":
        return ts
    # 메타가 없지만 기존 .md 파일이 있으면 → 외부 자동화가 이미 관리 중
    # "지금"부터 시작하여 새 스레드만 수집
    if summary_dir:
        existing = list(Path(summary_dir).glob("[0-9]*.md"))
        if existing:
            return str(datetime.now().timestamp())
    # 완전 첫 실행: 1일 전부터
    yesterday = datetime.now() - timedelta(days=1)
    return str(yesterday.timestamp())


def fetch_slack_threads():
    """Slack API로 내 멘션 + 지정 채널의 스레드를 수집한다.

    Returns:
        list[dict]: [{
            "channel_id": str,
            "channel_name": str,
            "thread_ts": str,
            "messages": [{"user": str, "user_name": str, "text": str, "ts": str}, ...],
        }]
        토큰 미설정 시 빈 리스트 반환.
    """
    user_token = CONFIG.get("slack_user_token", "")
    bot_token = CONFIG.get("slack_bot_token", "")
    watch_channels = CONFIG.get("slack_watch_channels", [])
    summary_dir = CONFIG.get("slack_summary_dir", "")

    if not user_token or not bot_token:
        return []

    meta = _load_meta(summary_dir)
    since_ts = _get_since_ts(meta, summary_dir)
    # search.messages용 날짜 문자열
    since_date = datetime.fromtimestamp(float(since_ts)).strftime("%Y-%m-%d")

    print(f"  📡 Slack 멘션 검색 (since {since_date})...")

    # 1. 내 멘션 스레드 수집
    my_id = _get_my_user_id(user_token)
    if not my_id:
        print("  ⚠️ Slack User ID 조회 실패")
        return []

    mention_threads = _search_mentions(user_token, my_id, since_date)
    print(f"  ✅ 멘션 스레드 {len(mention_threads)}건 발견")

    # 2. 지정 채널 스레드 수집
    channel_threads = []
    for ch_id in watch_channels:
        ch_threads = _get_channel_threads(user_token, ch_id, since_ts)
        channel_threads.extend(ch_threads)
        print(f"  ✅ 채널 {ch_id}: 스레드 {len(ch_threads)}건")

    # 3. 중복 제거
    all_thread_keys = set()
    all_threads = []
    for t in mention_threads + channel_threads:
        key = (t["channel_id"], t["thread_ts"])
        if key not in all_thread_keys:
            all_thread_keys.add(key)
            all_threads.append(t)

    print(f"  📥 총 {len(all_threads)}개 스레드의 메시지 조회 중...")

    # 4. 각 스레드의 전체 replies 조회 (접근 불가 채널은 스킵)
    result = []
    skipped = 0
    channel_name_cache = {}
    for t in all_threads:
        ch_id = t["channel_id"]

        messages = _get_thread_replies(user_token, ch_id, t["thread_ts"])
        if not messages:
            skipped += 1
            continue

        if ch_id not in channel_name_cache:
            channel_name_cache[ch_id] = _get_channel_name(user_token, ch_id)

        messages = _resolve_user_names(bot_token, messages)

        result.append({
            "channel_id": ch_id,
            "channel_name": channel_name_cache[ch_id],
            "thread_ts": t["thread_ts"],
            "messages": messages,
        })

    if skipped:
        print(f"  ⏭️ {skipped}건 스킵 (DM 등 접근 불가)")
    print(f"  ✅ Slack 스레드 {len(result)}건 수집 완료")
    return result
