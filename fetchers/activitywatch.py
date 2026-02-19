#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ActivityWatch data fetchers."""

import sys
import requests
from collections import defaultdict
from urllib.parse import urlparse

from config import CONFIG
from utils import get_api_url, get_bucket_id, get_bucket_ids


def fetch_window_events(start_iso, end_iso):
    """윈도우 활동 데이터 조회

    Returns:
        dict: {'앱이름': 총_시간_초} 형식의 딕셔너리
    """

    bucket_id = get_bucket_id("currentwindow")
    if not bucket_id:
        print("⚠️ 윈도우 활동 버킷을 찾을 수 없습니다.", file=sys.stderr)
        return {}

    try:
        url = get_api_url(f"buckets/{bucket_id}/events")
        params = {
            "start": start_iso,
            "end": end_iso,
            "limit": -1,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        events = response.json()
        app_durations = defaultdict(float)

        for event in events:
            if "data" in event and "app" in event["data"]:
                app_name = event["data"]["app"]
                # loginwindow는 자리비움(Lock Screen) 상태이므로 제외
                if app_name.lower() == "loginwindow":
                    continue

                duration = event.get("duration", 0)

                if duration > CONFIG["min_duration_seconds"]:
                    app_durations[app_name] += duration

        return dict(app_durations)

    except Exception as e:
        print(f"⚠️ 윈도우 활동 데이터 조회 실패: {e}", file=sys.stderr)
        return {}


def fetch_web_events(start_iso, end_iso):
    """웹 브라우징 활동 데이터 조회

    Returns:
        dict: {'도메인': 총_시간_초} 형식의 딕셔너리
    """

    bucket_ids = get_bucket_ids("web.tab.current")
    if not bucket_ids:
        print("⚠️ 웹 활동 버킷을 찾을 수 없습니다.", file=sys.stderr)
        return {}, []

    domain_durations = defaultdict(float)
    url_details = []

    # 모든 웹 버킷에서 데이터 수집
    for bucket_id in bucket_ids:
        try:
            url = get_api_url(f"buckets/{bucket_id}/events")
            params = {
                "start": start_iso,
                "end": end_iso,
                "limit": -1,
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            events = response.json()

            for event in events:
                if "data" in event:
                    data = event["data"]
                    event_url = data.get("url", "")
                    duration = event.get("duration", 0)

                    if duration > CONFIG["min_duration_seconds"] and event_url:
                        try:
                            domain = urlparse(event_url).netloc or event_url
                            domain_durations[domain] += duration
                            url_details.append({
                                "url": event_url,
                                "domain": domain,
                                "duration": duration,
                                "title": data.get("title", "")
                            })
                        except Exception:
                            pass

        except Exception as e:
            print(f"⚠️ 웹 활동 데이터 조회 실패 (버킷: {bucket_id}): {e}", file=sys.stderr)
            continue

    return dict(domain_durations), url_details
