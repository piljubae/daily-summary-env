#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jira REST API 기반 오늘의 할일 (활성 티켓) 조회."""

import os
import sys
import base64

import requests

from config import CONFIG


# 진행중 상태 목록
IN_PROGRESS_STATUSES = {
    "진행 중", "In Progress", "개발 중", "Testing"
}
# 검토(코드리뷰) 상태 목록
REVIEW_STATUSES = {
    "검토", "코드리뷰", "리뷰 대기", "In Review"
}


def fetch_today_todos():
    """Jira에서 본인에게 할당된 활성 티켓을 조회합니다.

    Returns:
        dict: {
            in_progress: [{ key, summary, status }],
            review: [{ key, summary, status }],
            todo: [{ key, summary, status }],
            available: bool
        }
    """
    jira_url = CONFIG.get("jira_url") or os.environ.get("JIRA_URL", "")
    jira_email = CONFIG.get("jira_email") or os.environ.get("JIRA_EMAIL", "")
    jira_token = CONFIG.get("jira_api_token") or os.environ.get("JIRA_API_TOKEN", "")
    project_key = CONFIG.get("jira_project_key") or os.environ.get("JIRA_PROJECT_KEY", "KMA")

    empty_result = {"in_progress": [], "review": [], "todo": [], "available": False}

    if not jira_url or not jira_email or not jira_token:
        print("ℹ️ Jira 설정 미완료 — 할일 조회 생략", file=sys.stderr)
        return empty_result

    # Basic Auth 헤더
    credentials = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    base_url = jira_url.rstrip("/")
    in_progress = []
    review = []
    todo = []

    try:
        search_url = f"{base_url}/rest/api/3/search/jql"

        # 미완료 티켓: 완료/Done/Closed/CLOSE 제외, 본인 할당
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
            elif status_name in REVIEW_STATUSES:
                review.append(ticket)
            else:
                todo.append(ticket)

    except Exception as e:
        print(f"⚠️ Jira API 조회 실패: {e}", file=sys.stderr)
        return empty_result

    return {
        "in_progress": in_progress,
        "review": review,
        "todo": todo,
        "available": True,
    }
