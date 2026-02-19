"""Fetchers package for daily summary data collection."""

from .activitywatch import fetch_window_events, fetch_web_events
from .claude import fetch_claude_context
from .cowork import fetch_cowork_sessions
from .firebender import fetch_firebender_activity
from .antigravity import fetch_antigravity_activity
from .calendar import fetch_calendar_events
from .all import FetchedData, fetch_all

__all__ = [
    # 개별 fetcher (직접 사용이 필요한 경우)
    'fetch_window_events',
    'fetch_web_events',
    'fetch_claude_context',
    'fetch_cowork_sessions',
    'fetch_firebender_activity',
    'fetch_antigravity_activity',
    'fetch_calendar_events',
    # 통합 인터페이스 (권장)
    'FetchedData',
    'fetch_all',
]
