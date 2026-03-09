#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""어제 작업 데이터에서 Jira 티켓키를 추출하고 오늘 할일과 매칭한다."""

import re

TICKET_KEY_PATTERN = re.compile(r"[A-Z]+-\d+")


def extract_ticket_keys(fetched_data) -> set[str]:
    """어제 수집된 FetchedData에서 Jira 티켓키를 추출한다.

    소스: antigravity_data(git commits), claude_context, claude_cli_history
    """
    keys = set()
    texts = []

    # git commit 메시지
    for commit in fetched_data.antigravity_data.get("commits", []):
        texts.append(commit.get("message", ""))

    # Claude 세션 goal/summary
    for session in fetched_data.claude_context:
        texts.append(session.get("goal", ""))
        texts.append(session.get("summary", ""))

    # Claude CLI 명령어
    for item in fetched_data.claude_cli_history:
        texts.append(item.get("command", ""))

    for text in texts:
        keys.update(TICKET_KEY_PATTERN.findall(text))

    return keys


def tag_yesterday_tickets(tickets: list[dict],
                          yesterday_keys: set[str]) -> list[dict]:
    """어제 작업한 티켓에 'yesterday': True 플래그를 부여한다.

    원본 리스트를 변경하지 않고 새 리스트를 반환한다.
    """
    result = []
    for ticket in tickets:
        tagged = {**ticket, "yesterday": ticket["key"] in yesterday_keys}
        result.append(tagged)
    return result
