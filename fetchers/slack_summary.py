#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack 스레드 요약 파일 fetcher."""

import re
from pathlib import Path

from config import CONFIG


def fetch_slack_summary() -> dict:
    """Slack 요약 디렉토리에서 .md 파일을 읽어 반환한다.

    Returns:
        dict: {
            "topics": [{"filename": str, "title": str, "content": str}, ...],
            "readme_content": str,
            "focus_lines": list[str],
            "full_text": str,
        }
        디렉토리가 없거나 빈 경우 빈 dict 반환.
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
    all_parts = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, PermissionError):
            continue

        if md_file.name.lower() == "readme.md":
            readme_content = content
            all_parts.append(content)
            continue

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        topics.append({
            "filename": md_file.name,
            "title": title,
            "content": content,
        })
        all_parts.append(content)

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
        "full_text": "\n\n---\n\n".join(all_parts),
    }
