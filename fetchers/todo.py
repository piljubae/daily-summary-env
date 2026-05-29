#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jira REST API 기반 오늘의 할일 (활성 티켓) 조회."""

import os
import sys
import base64

import requests

from config import CONFIG


def parse_issue(issue: dict) -> dict:
    """Jira issue JSON을 정규화된 dict로 변환한다.

    비즈니스 로직 없음 — 데이터 정제만 담당.
    """
    fields = issue["fields"]

    # priority
    priority_obj = fields.get("priority")
    priority = priority_obj["name"] if priority_obj else None

    # latest_comment (최근 1개, 50자 자르기)
    comment_field = fields.get("comment", {})
    comments = comment_field.get("comments", [])
    latest_comment = None
    latest_comment_updated = None
    if comments:
        last = comments[-1]
        # ADF body에서 텍스트 추출 시도
        try:
            text_parts = []
            for block in last.get("body", {}).get("content", []):
                for inline in block.get("content", []):
                    if inline.get("text"):
                        text_parts.append(inline["text"])
            raw = " ".join(text_parts)
            latest_comment = raw[:50] if raw else None
        except (KeyError, TypeError):
            latest_comment = None
        latest_comment_updated = last.get("updated")

    # status_changed_at — changelog에서 status 변경의 마지막 날짜
    status_changed_at = None
    for history in reversed(issue.get("changelog", {}).get("histories", [])):
        for item in history.get("items", []):
            if item.get("field") == "status":
                status_changed_at = history["created"]
                break
        if status_changed_at:
            break

    return {
        "key": issue["key"],
        "summary": fields["summary"],
        "status": fields["status"]["name"],
        "priority": priority,
        "duedate": fields.get("duedate"),
        "updated": fields.get("updated"),
        "latest_comment": latest_comment,
        "latest_comment_updated": latest_comment_updated,
        "status_changed_at": status_changed_at,
    }


def fetch_today_todos() -> list[dict]:
    """Jira에서 본인에게 할당된 활성 티켓을 조회한다.

    Returns:
        list[dict]: parse_issue 결과 리스트. API 실패 시 빈 리스트.
    """
    jira_url = CONFIG.get("jira_url") or os.environ.get("JIRA_URL", "")
    jira_email = CONFIG.get("jira_email") or os.environ.get("JIRA_EMAIL", "")
    jira_token = CONFIG.get("jira_api_token") or os.environ.get("JIRA_API_TOKEN", "")
    project_key = CONFIG.get("jira_project_key") or os.environ.get("JIRA_PROJECT_KEY", "KMA")

    if not jira_url or not jira_email or not jira_token:
        print("ℹ️ Jira 설정 미완료 — 할일 조회 생략", file=sys.stderr)
        return []

    credentials = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    base_url = jira_url.rstrip("/")

    try:
        resp = requests.post(
            f"{base_url}/rest/api/3/search/jql",
            headers=headers,
            json={
                "jql": (
                    f'project = {project_key} AND '
                    f'assignee = currentUser() AND '
                    f'status NOT IN ("완료", "Done", "Closed", "CLOSE")'
                ),
                "maxResults": 50,
                "fields": ["summary", "status", "priority", "duedate", "updated", "comment"],
                "expand": "changelog",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return [parse_issue(issue) for issue in resp.json().get("issues", [])]

    except Exception as e:
        print(f"⚠️ Jira API 조회 실패: {e}", file=sys.stderr)
        return []


def _jira_headers() -> dict:
    """Jira Basic Auth 헤더 반환."""
    jira_email = CONFIG.get("jira_email") or os.environ.get("JIRA_EMAIL", "")
    jira_token = CONFIG.get("jira_api_token") or os.environ.get("JIRA_API_TOKEN", "")
    credentials = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def transition_to_done(issue_key: str) -> bool:
    """Jira 티켓을 Done/완료 상태로 전환.

    Available transitions 중 name이 done/완료/closed/close인 것을 찾아 전환.
    없으면 add_jira_comment로 fallback.

    Returns:
        bool: 성공 시 True, 실패 시 False.
    """
    base_url = (CONFIG.get("jira_url") or os.environ.get("JIRA_URL", "")).rstrip("/")
    headers = _jira_headers()

    try:
        resp = requests.get(
            f"{base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])
        done_ids = [
            t["id"] for t in transitions
            if t["name"].lower() in ("done", "완료", "closed", "close")
        ]
        if not done_ids:
            print(f"⚠️ {issue_key}: Done 전환 없음 — 코멘트만 추가", file=sys.stderr)
            return add_jira_comment(issue_key, "✅ EOD 리뷰 완료 확인")

        resp2 = requests.post(
            f"{base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=headers,
            json={"transition": {"id": done_ids[0]}},
            timeout=15,
        )
        resp2.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ {issue_key} 전환 실패: {e}", file=sys.stderr)
        return False


def add_jira_comment(issue_key: str, text: str) -> bool:
    """Jira 티켓에 텍스트 코멘트 추가 (ADF 형식)."""
    base_url = (CONFIG.get("jira_url") or os.environ.get("JIRA_URL", "")).rstrip("/")
    headers = _jira_headers()
    body = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }
    }
    try:
        resp = requests.post(
            f"{base_url}/rest/api/3/issue/{issue_key}/comment",
            headers=headers, json=body, timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ {issue_key} 코멘트 실패: {e}", file=sys.stderr)
        return False
