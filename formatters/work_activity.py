#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Work-activity-only report formatter.

Generates a report containing ONLY work-related activities,
excluding personal data (app usage, browsing history, full chat logs).
Intended as a "second brain" data source for wiki-agent.
"""

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from config import CONFIG
from fetchers import (
    fetch_today_todos,
    extract_ticket_keys,
    tag_yesterday_tickets,
    score_and_group,
)


def create_work_activity_report(data, target_date) -> str:
    """Builds a markdown report with work-related sections only.

    Included:
        - Calendar events
        - Jira tickets
        - Claude sessions (title, goal, files -- NO full_messages)
        - Antigravity commits & files (NO user_queries)
        - Slack topic titles only (NO content)
        - Cowork sessions (intent, result, urls)
        - Firebender tasks

    Excluded:
        - App durations
        - Domain / URL details
        - Claude CLI history
        - Claude full_messages
        - Detailed activity list

    Args:
        data (FetchedData): fetch_all() result
        target_date (datetime): target date

    Returns:
        str: markdown report
    """
    calendar_events = data.calendar_events
    cowork_sessions = data.cowork_sessions
    claude_context = data.claude_context
    firebender_tasks = data.firebender_tasks
    antigravity_data = data.antigravity_data
    slack_summary = data.slack_summary

    report = f"# {target_date.strftime('%m/%d')} Work Activity\n\n"

    # ── 📅 미팅 일정 ──────────────────────────────────────
    report += f"**📅 미팅 일정** ({len(calendar_events)}건)\n" if calendar_events else "**📅 미팅 일정**\n"
    if calendar_events:
        for ev in calendar_events:
            start_str = ev["start"].strftime("%H:%M")
            end_str = ev["end"].strftime("%H:%M")
            report += f"- {start_str}~{end_str} {ev['title']} ({ev['duration_min']}분)\n"
    else:
        report += "- (데이터 없음)\n"
    report += "\n"

    # ── 📌 Jira 티켓 ─────────────────────────────────────
    raw_tickets = fetch_today_todos()
    if raw_tickets:
        yesterday_keys = extract_ticket_keys(data)
        tagged_tickets = tag_yesterday_tickets(raw_tickets, yesterday_keys)
        grouped = score_and_group(tagged_tickets)

        total_count = len(grouped["urgent"]) + len(grouped["this_week"]) + len(grouped["backlog"])
        if total_count > 0:
            report += f"**📌 Jira 티켓** ({total_count}건)\n\n"

            group_config = [
                ("urgent", "🔴 오늘 집중"),
                ("this_week", "🟡 이번주 내"),
                ("backlog", "⚪ 백로그"),
            ]
            for group_key, group_label in group_config:
                items = grouped[group_key]
                if items:
                    report += f"{group_label} ({len(items)}건)\n"
                    for ticket in items:
                        tags_str = ", ".join(ticket["tags"]) if ticket["tags"] else ""
                        line = f"- [{ticket['key']}] {ticket['summary']}"
                        if tags_str:
                            line += f" — {tags_str}"
                        report += line + "\n"
                    report += "\n"

    # ── 🤖 Claude 활동 ───────────────────────────────────
    report += f"**🤖 Claude 활동** ({len(claude_context)}건)\n" if claude_context else "**🤖 Claude 활동**\n"
    if claude_context:
        for session in claude_context:
            title = session.get("title", "세션")
            duration = session.get("duration_min", 0)
            count = session.get("interaction_count", 0)

            report += f"### 📂 {title}\n"
            report += f"> ⏱️ **{duration}분** 동안 **{count}번**의 상호작용\n\n"

            report += "**🎯 작업 목표**\n"
            report += f"{session['goal']}\n\n"

            has_changes = False
            if session["files_created"]:
                report += f"- 🆕 **생성된 파일**: {', '.join(session['files_created'])}\n"
                has_changes = True
            if session["files_modified"]:
                report += f"- 📝 **수정된 파일**: {', '.join(session['files_modified'])}\n"
                has_changes = True

            if not has_changes:
                report += "- ⚠️ 파일 변경 사항 없음\n"

            report += "\n"
    else:
        report += "- (데이터 없음)\n\n"

    # ── 🤖 Antigravity 활동 ──────────────────────────────
    commit_messages = antigravity_data.get("commit_messages", []) if antigravity_data else []
    files = antigravity_data.get("files_modified", []) if antigravity_data else []
    has_antigravity = bool(commit_messages or files)

    report += "**🤖 Antigravity 활동**\n"
    if not has_antigravity:
        report += "- (데이터 없음)\n"
    else:
        if commit_messages:
            report += f"- 📝 **커밋 메시지** ({len(commit_messages)}건)\n"
            for msg in commit_messages:
                report += f"  - {msg}\n"

        if files:
            report += f"- 🛠️ **수정된 파일** ({len(files)}개)\n"
            for f in files[:10]:
                report += f"  - `{f}`\n"
            if len(files) > 10:
                report += f"  - ...외 {len(files) - 10}개\n"
    report += "\n"

    # ── 📬 Slack 토픽 제목 ────────────────────────────────
    if slack_summary and slack_summary.get("topics"):
        topic_count = len(slack_summary["topics"])
        report += f"**📬 Slack 토픽** ({topic_count}건)\n"
        for t in slack_summary["topics"]:
            report += f"- {t['title']}\n"
        report += "\n"

    # ── 🤖 Cowork 세션 ───────────────────────────────────
    report += f"**🤖 Cowork** ({len(cowork_sessions)}건)\n" if cowork_sessions else "**🤖 Cowork**\n"
    if cowork_sessions:
        for task in cowork_sessions[:7]:
            line = f"- {task['intent']}"
            if task["result"]:
                line += f" — {task['result']}"
            report += line + "\n"
            if task["urls"]:
                domains = [urlparse(u).netloc for u in task["urls"]]
                report += f"  📎 {', '.join(domains)}\n"
        if len(cowork_sessions) > 7:
            report += f"- ...외 {len(cowork_sessions) - 7}건\n"
    else:
        report += "- (데이터 없음)\n"
    report += "\n"

    # ── 🤖 Firebender 활동 ───────────────────────────────
    report += f"**🤖 Firebender (Android Studio)** ({len(firebender_tasks)}건)\n" if firebender_tasks else "**🤖 Firebender (Android Studio)**\n"
    if firebender_tasks:
        by_project = defaultdict(list)
        for t in firebender_tasks:
            by_project[t["project"]].append(t["query"])

        for project, queries in by_project.items():
            report += f"### 📂 {project}\n"
            for q in queries:
                report += f"- {q}\n"
            report += "\n"
    else:
        report += "- (데이터 없음)\n\n"

    return report


def save_work_activity_report(content, target_date) -> Path:
    """Save work-activity report to the work-activity directory.

    Output path: {CONFIG["output_dir"]}/../work-activity/YYYY-MM-DD-work-activity.md

    Args:
        content (str): markdown content
        target_date (datetime): target date

    Returns:
        Path: saved file path
    """
    output_dir = Path(CONFIG["output_dir"]).parent / "work-activity"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{target_date.date().isoformat()}-work-activity.md"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
