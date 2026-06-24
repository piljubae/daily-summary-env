#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack 스레드 요약 파일 fetcher."""

import re
from datetime import datetime
from pathlib import Path

from config import CONFIG


def _read_daily_slim(dir_path: Path, target_date) -> str:
    """``daily/YYYY-MM-DD.md`` 슬림 파일 내용을 반환한다(없으면 "").

    ``slack-mention-daily-update`` 스킬이 매일 그날 업데이트분만 모아 저장하는
    슬림 파일이다. Gemini 일일 요약 입력(``full_text``)은 이 한 파일만 사용해,
    7일치 토픽 전문을 매일 재전송하던 낭비를 없앤다.
    """
    if not isinstance(target_date, datetime):
        return ""
    daily_file = dir_path / "daily" / f"{target_date.strftime('%Y-%m-%d')}.md"
    if not daily_file.is_file():
        return ""
    try:
        return daily_file.read_text(encoding="utf-8")
    except (IOError, PermissionError):
        return ""


def fetch_slack_summary(target_date=None) -> dict:
    """Slack 요약 디렉토리에서 .md 파일을 읽어 반환한다.

    Args:
        target_date: 요약 대상 날짜(datetime). ``full_text``로 읽을
            ``daily/YYYY-MM-DD.md`` 슬림 파일을 결정한다. None이면 ``full_text``는 "".

    Returns:
        dict: {
            "topics": [{"filename": str, "title": str, "content": str}, ...],
            "readme_content": str,
            "focus_lines": list[str],
            "full_text": str,
        }
        디렉토리가 없거나 빈 경우 빈 dict 반환.

    참고: ``full_text``는 Gemini 일일 요약 입력이라 비용에 직결된다. 이제 7일치
    토픽 전문 대신 ``target_date``의 ``daily/`` 슬림 파일 하나만 담는다.
    ``topics``/``focus_lines``/``readme_content``는 리포트 표시용이라 루트의
    토픽 파일 전체에서 그대로 수집한다.
    """
    summary_dir = CONFIG.get("slack_summary_dir", "")
    if not summary_dir:
        return {}

    dir_path = Path(summary_dir)
    if not dir_path.is_dir():
        return {}

    md_files = sorted(dir_path.glob("*.md"))
    if not md_files:
        return {}

    readme_content = ""
    topics = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, PermissionError):
            continue

        if md_file.name.lower() == "readme.md":
            readme_content = content
            continue

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        topics.append({
            "filename": md_file.name,
            "title": title,
            "content": content,
        })

    focus_lines = []
    if readme_content:
        focus_match = re.search(
            r"##\s*이번\s*주\s*포커스\s*\n((?:- .+\n?)+)",
            readme_content,
        )
        if focus_match:
            for line in focus_match.group(1).strip().splitlines():
                line = line.strip()
                if line.startswith("- "):
                    focus_lines.append(line[2:])

    return {
        "topics": topics,
        "readme_content": readme_content,
        "focus_lines": focus_lines,
        "full_text": _read_daily_slim(dir_path, target_date),
    }
