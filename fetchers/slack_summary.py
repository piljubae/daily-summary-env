#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack 스레드 요약 파일 fetcher."""

import os
import re
import time
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

    참고: ``full_text``는 Gemini 일일 요약 입력으로 쓰이므로 비용에 직결된다.
    거의 변하지 않는 오래된 팀노트까지 매일 재전송하지 않도록, 최근
    ``SLACK_CONTEXT_DAYS``일(기본 7) 이내에 수정된 파일만 ``full_text``에
    포함한다. ``topics``/``focus_lines``는 리포트 표시용이라 전체를 유지한다.
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

    # full_text(=Gemini 입력)에 포함할 최근 수정 파일 기준. 0 이하이면 전체 포함.
    try:
        context_days = int(os.environ.get("SLACK_CONTEXT_DAYS", "7"))
    except ValueError:
        context_days = 7
    cutoff = time.time() - context_days * 86400 if context_days > 0 else None

    def _is_recent(path: Path) -> bool:
        if cutoff is None:
            return True
        try:
            return path.stat().st_mtime >= cutoff
        except OSError:
            return False

    readme_content = ""
    topics = []
    all_parts = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, PermissionError):
            continue

        recent = _is_recent(md_file)

        if md_file.name.lower() == "readme.md":
            readme_content = content
            if recent:
                all_parts.append(content)
            continue

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        topics.append({
            "filename": md_file.name,
            "title": title,
            "content": content,
        })
        if recent:
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
