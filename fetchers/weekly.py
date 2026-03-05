#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 요약용 데이터 fetcher.

- 데일리 요약 마크다운 파일 파싱 (활동 시간, 사이트 수, 미팅 수, Gemini 요약)
- Jira REST API로 티켓 조회 (완료/진행중/미착수 분류)
"""

import os
import re
import sys
import base64
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import CONFIG


def _parse_active_minutes(line):
    """'**💻 6시간 32분**' 또는 '**💻 32분**' 패턴에서 분(minutes)을 추출합니다."""
    m = re.search(r'💻\s*(\d+)시간\s*(\d+)분', line)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r'💻\s*(\d+)분', line)
    if m:
        return int(m.group(1))
    return 0


def _parse_site_count(line):
    """'**🌐 사이트** — 1. ... / 2. ... / 3. ...' 에서 사이트 개수를 반환합니다."""
    # '🌐 사이트' 뒤의 ' — ' 이후 부분에서 ' / ' 구분자 수 + 1로 개수 결정
    m = re.search(r'🌐.*?—\s*(.+)', line)
    if m:
        entries = m.group(1).strip()
        if not entries:
            return 0
        return entries.count(' / ') + 1
    return 0


def _parse_meeting_count(line):
    """'**📅 미팅/일정** (3건)' 에서 건수를 추출합니다."""
    m = re.search(r'📅.*?(\d+)건', line)
    if m:
        return int(m.group(1))
    return 0


def _extract_gemini_items(content):
    """## 🤖 AI 요약 (Gemini) 섹션에서 번호 항목을 추출합니다."""
    items = []
    in_gemini = False
    for line in content.splitlines():
        if '## 🤖 AI 요약 (Gemini)' in line:
            in_gemini = True
            continue
        if in_gemini:
            # 새로운 ## 섹션이 나오면 종료
            if line.startswith('## ') or line.startswith('---'):
                break
            # 번호 항목: "1. **타이틀**" 또는 "1.  **타이틀**"
            m = re.match(r'^\s*\d+\.\s+\*\*(.+?)\*\*', line)
            if m:
                items.append(m.group(1))
    return items


def fetch_daily_summaries(week_start, week_end):
    """월~금 데일리 요약 파일을 읽어 주간 데이터를 집계합니다.

    Args:
        week_start: 주 시작일 (datetime, 월요일)
        week_end: 주 종료일 (datetime, 금요일)

    Returns:
        dict: {
            days: [{ date, active_minutes, sites, meetings, gemini_items }],
            total_active_minutes, total_sites, total_meetings,
            all_gemini_items: [str]
        }
    """
    output_dir = Path(CONFIG["output_dir"])
    days = []
    total_active_minutes = 0
    total_sites = 0
    total_meetings = 0
    all_gemini_items = []

    current = week_start
    while current <= week_end:
        filename = f"{current.strftime('%Y-%m-%d')}-daily-summary.md"
        filepath = output_dir / filename

        day_info = {
            "date": current.strftime('%Y-%m-%d'),
            "weekday": ["월", "화", "수", "목", "금", "토", "일"][current.weekday()],
            "active_minutes": 0,
            "sites": 0,
            "meetings": 0,
            "gemini_items": [],
            "found": False,
        }

        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8")
                day_info["found"] = True

                for line in content.splitlines():
                    if '💻' in line and '**' in line and day_info["active_minutes"] == 0:
                        day_info["active_minutes"] = _parse_active_minutes(line)
                    if '🌐 사이트' in line and day_info["sites"] == 0:
                        day_info["sites"] = _parse_site_count(line)
                    if '📅' in line and '미팅' in line and day_info["meetings"] == 0:
                        day_info["meetings"] = _parse_meeting_count(line)

                day_info["gemini_items"] = _extract_gemini_items(content)
                all_gemini_items.extend(day_info["gemini_items"])

                total_active_minutes += day_info["active_minutes"]
                total_sites += day_info["sites"]
                total_meetings += day_info["meetings"]

            except Exception as e:
                print(f"⚠️ {filename} 읽기 실패: {e}", file=sys.stderr)

        days.append(day_info)
        current += timedelta(days=1)

    return {
        "days": days,
        "total_active_minutes": total_active_minutes,
        "total_sites": total_sites,
        "total_meetings": total_meetings,
        "all_gemini_items": all_gemini_items,
    }


def fetch_jira_tickets(week_start, week_end):
    """Jira REST API v3로 티켓을 조회하여 완료/진행중/미착수로 분류합니다.

    Args:
        week_start: 주 시작일 (datetime)
        week_end: 주 종료일 (datetime)

    Returns:
        dict: {
            completed: [{ key, summary, status }],
            in_progress: [{ key, summary, status }],
            todo: [{ key, summary, status }],
            available: bool
        }
    """
    jira_url = CONFIG.get("jira_url") or os.environ.get("JIRA_URL", "")
    jira_email = CONFIG.get("jira_email") or os.environ.get("JIRA_EMAIL", "")
    jira_token = CONFIG.get("jira_api_token") or os.environ.get("JIRA_API_TOKEN", "")
    project_key = CONFIG.get("jira_project_key") or os.environ.get("JIRA_PROJECT_KEY", "KMA")

    if not jira_url or not jira_email or not jira_token:
        print("ℹ️ Jira 설정 미완료 — Jira 티켓 조회 생략", file=sys.stderr)
        return {"completed": [], "in_progress": [], "todo": [], "available": False}

    # Basic Auth 헤더
    credentials = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    start_str = week_start.strftime("%Y-%m-%d")
    end_str = week_end.strftime("%Y-%m-%d")
    base_url = jira_url.rstrip("/")

    completed = []
    in_progress = []
    todo = []

    # 진행중 상태 목록
    IN_PROGRESS_STATUSES = {
        "진행 중", "In Progress", "개발 중", "코드리뷰", "리뷰 대기", "In Review", "Testing"
    }

    try:
        search_url = f"{base_url}/rest/api/3/search/jql"

        # 1) 완료 티켓: 해당 기간에 "완료" 상태로 변경된 것
        completed_jql = (
            f'project = {project_key} AND '
            f'status changed to "완료" DURING ("{start_str}", "{end_str}")'
        )
        resp = requests.post(
            search_url,
            headers=headers,
            json={"jql": completed_jql, "maxResults": 50, "fields": ["summary", "status"]},
            timeout=15,
        )
        resp.raise_for_status()
        for issue in resp.json().get("issues", []):
            completed.append({
                "key": issue["key"],
                "summary": issue["fields"]["summary"],
                "status": issue["fields"]["status"]["name"],
            })

        # 2) 미완료 티켓: 완료/Done/Closed/CLOSE 제외
        active_jql = (
            f'project = {project_key} AND '
            f'assignee = currentUser() AND '
            f'status NOT IN ("완료", "Done", "Closed", "CLOSE")'
        )
        resp = requests.post(
            search_url,
            headers=headers,
            json={"jql": active_jql, "maxResults": 50, "fields": ["summary", "status"]},
            timeout=15,
        )
        resp.raise_for_status()
        for issue in resp.json().get("issues", []):
            status_name = issue["fields"]["status"]["name"]
            ticket = {
                "key": issue["key"],
                "summary": issue["fields"]["summary"],
                "status": status_name,
            }
            if status_name in IN_PROGRESS_STATUSES:
                in_progress.append(ticket)
            else:
                todo.append(ticket)

    except Exception as e:
        print(f"⚠️ Jira API 조회 실패: {e}", file=sys.stderr)
        return {"completed": [], "in_progress": [], "todo": [], "available": False}

    return {
        "completed": completed,
        "in_progress": in_progress,
        "todo": todo,
        "available": True,
    }
