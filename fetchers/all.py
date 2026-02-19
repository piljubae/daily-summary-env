#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모든 fetcher를 한 곳에서 관리합니다.

✅ 새 fetcher 추가 방법:
    1. fetchers/ 하위에 새 파이썬 파일 작성
    2. fetchers/__init__.py에 함수 export 추가
    3. 이 파일의 FetchedData에 필드 추가
    4. fetch_all() 함수에 호출 추가
    ─ daily_summary.py / markdown.py는 수정 불필요 ─
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .activitywatch import fetch_window_events, fetch_web_events
from .cowork import fetch_cowork_sessions
from .claude import fetch_claude_context, fetch_claude_cli_history
from .firebender import fetch_firebender_activity
from .antigravity import fetch_antigravity_activity
from .calendar import fetch_calendar_events


@dataclass
class FetchedData:
    """모든 fetcher 결과를 담는 컨테이너.

    ✅ 새 fetcher를 추가하면 여기에 필드를 추가하세요.
    """

    # ActivityWatch (start_iso/end_iso 기반)
    app_durations: dict = field(default_factory=dict)
    domain_durations: dict = field(default_factory=dict)
    url_details: list = field(default_factory=list)

    # 날짜 기반 fetcher들
    cowork_sessions: list = field(default_factory=list)
    claude_context: list = field(default_factory=list)
    firebender_tasks: list = field(default_factory=list)
    antigravity_data: dict = field(default_factory=dict)
    calendar_events: list = field(default_factory=list)
    claude_cli_history: list = field(default_factory=list)

    # ── 여기에 새 필드 추가 ──────────────────────────────


def fetch_all(target_date: datetime, start_iso: str, end_iso: str) -> FetchedData:
    """모든 데이터 소스에서 데이터를 수집하여 FetchedData로 반환합니다.

    ✅ 새 fetcher를 추가하면 여기에 호출을 추가하세요.

    Args:
        target_date: 요약 대상 날짜 (datetime)
        start_iso: 조회 시작 시각 (ISO 8601)
        end_iso: 조회 종료 시각 (ISO 8601)

    Returns:
        FetchedData: 수집된 모든 데이터
    """
    app_durations, (domain_durations, url_details) = (
        fetch_window_events(start_iso, end_iso),
        fetch_web_events(start_iso, end_iso),
    )

    return FetchedData(
        app_durations=app_durations,
        domain_durations=domain_durations,
        url_details=url_details,
        cowork_sessions=fetch_cowork_sessions(target_date),
        claude_context=fetch_claude_context(target_date),
        firebender_tasks=fetch_firebender_activity(target_date),
        antigravity_data=fetch_antigravity_activity(target_date),
        calendar_events=fetch_calendar_events(target_date),
        claude_cli_history=fetch_claude_cli_history(target_date),
        # ── 여기에 새 fetcher 호출 추가 ─────────────────
    )
