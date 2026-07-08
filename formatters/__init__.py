"""Formatters package for daily summary output formatting."""

from .markdown import (
    create_markdown_report,
    categorize_apps,
    calculate_active_time,
    generate_productivity_summary,
    generate_one_liner,
    save_report,
    summarize_with_gemini,
    summarize_with_claude,
    summarize_ai,
    parse_ai_summary_sections,
)
from .work_activity import (
    create_work_activity_report,
    save_work_activity_report,
)
from .slack import send_to_slack

__all__ = [
    'create_markdown_report',
    'categorize_apps',
    'calculate_active_time',
    'generate_productivity_summary',
    'generate_one_liner',
    'save_report',
    'summarize_with_gemini',
    'summarize_with_claude',
    'summarize_ai',
    'parse_ai_summary_sections',
    'create_work_activity_report',
    'save_work_activity_report',
    'send_to_slack',
]
