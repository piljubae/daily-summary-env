#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""액션 기반 할일 그룹 분류, 태그 계산, 정렬."""

from datetime import date, datetime, timedelta, timezone

# 진행중 상태 목록
IN_PROGRESS_STATUSES = {"진행 중", "In Progress", "개발 중", "Testing"}
# 리뷰 상태 목록
REVIEW_STATUSES = {"검토", "코드리뷰", "리뷰 대기", "In Review"}
# 높은 우선순위
HIGH_PRIORITIES = {"Highest", "High"}

KST = timezone(timedelta(hours=9))

# 상태 → 표시용 카테고리명
STATUS_DISPLAY = {}
for s in IN_PROGRESS_STATUSES:
    STATUS_DISPLAY[s] = "진행중"
for s in REVIEW_STATUSES:
    STATUS_DISPLAY[s] = "리뷰"


def _parse_date(date_str: str | None) -> date | None:
    """ISO 날짜 문자열에서 date만 추출."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _days_between(target: date, today: date) -> int:
    return (target - today).days


def _is_recent_comment(ticket: dict, today: date) -> bool:
    """24시간 내 코멘트가 있는지 확인."""
    comment_updated = ticket.get("latest_comment_updated")
    if not comment_updated or not ticket.get("latest_comment"):
        return False
    comment_date = _parse_date(comment_updated)
    if not comment_date:
        return False
    return (today - comment_date).days <= 1


def compute_tags(ticket: dict, today: date) -> list[str]:
    """티켓에 대한 태그 목록을 계산한다."""
    tags = []

    # D-N (마감일)
    due = _parse_date(ticket.get("duedate"))
    if due:
        days = _days_between(due, today)
        if days >= 0:
            tags.append(f"D-{days}")
        else:
            tags.append(f"D+{abs(days)} 초과")

    # 📍 우선순위
    priority = ticket.get("priority")
    if priority in HIGH_PRIORITIES:
        tags.append(f"📍{priority}")

    # 💬 최근 코멘트
    if _is_recent_comment(ticket, today):
        tags.append("💬코멘트")

    # 💤 방치 (updated 7일 이상)
    updated = _parse_date(ticket.get("updated"))
    if updated:
        stale_days = (today - updated).days
        if stale_days >= 7:
            tags.append(f"💤{stale_days}일방치")

    # 🔄 어제이어서
    if ticket.get("yesterday"):
        tags.append("🔄어제이어서")

    # N일째 (상태 진행 기간)
    status_date = _parse_date(ticket.get("status_changed_at"))
    status = ticket.get("status", "")
    if status_date:
        days_in = (today - status_date).days
        display = STATUS_DISPLAY.get(status, "할일")
        if days_in == 0:
            tags.append(f"{display} 오늘시작")
        else:
            tags.append(f"{display} {days_in}일째")

    return tags


def _is_urgent(ticket: dict, today: date) -> bool:
    """🔴 오늘 집중 조건."""
    # 마감 내일 이내
    due = _parse_date(ticket.get("duedate"))
    if due and _days_between(due, today) <= 1:
        return True

    # High/Highest + 진행중
    status = ticket.get("status", "")
    priority = ticket.get("priority")
    if priority in HIGH_PRIORITIES and status in IN_PROGRESS_STATUSES:
        return True

    # 24시간 내 코멘트
    if _is_recent_comment(ticket, today):
        return True

    return False


def _is_this_week(ticket: dict, today: date) -> bool:
    """🟡 이번주 내 조건."""
    # 마감 2~5일 이내
    due = _parse_date(ticket.get("duedate"))
    if due:
        days = _days_between(due, today)
        if 2 <= days <= 5:
            return True

    # 진행중·리뷰 상태
    status = ticket.get("status", "")
    if status in IN_PROGRESS_STATUSES or status in REVIEW_STATUSES:
        return True

    return False


def _sort_key(ticket: dict, today: date):
    """그룹 내 정렬키: 마감 임박 → 우선순위 → 최신 업데이트."""
    # 마감일 (없으면 9999로 뒤로)
    due = _parse_date(ticket.get("duedate"))
    due_days = _days_between(due, today) if due else 9999

    # 우선순위 (Highest=0, High=1, 나머지=9)
    priority = ticket.get("priority", "")
    priority_order = {"Highest": 0, "High": 1}.get(priority, 9)

    # 업데이트 역순 (최신이 위)
    updated = _parse_date(ticket.get("updated"))
    updated_days = (today - updated).days if updated else 9999

    return (due_days, priority_order, updated_days)


def score_and_group(tickets: list[dict], today: date | None = None) -> dict:
    """티켓을 액션 그룹으로 분류하고 정렬한다.

    각 티켓에 'tags' 필드가 추가된다.

    Returns:
        {"urgent": [...], "this_week": [...], "backlog": [...]}
    """
    if today is None:
        today = date.today()

    urgent = []
    this_week = []
    backlog = []

    for ticket in tickets:
        tagged = {**ticket, "tags": compute_tags(ticket, today)}

        if _is_urgent(ticket, today):
            urgent.append(tagged)
        elif _is_this_week(ticket, today):
            this_week.append(tagged)
        else:
            backlog.append(tagged)

    urgent.sort(key=lambda t: _sort_key(t, today))
    this_week.sort(key=lambda t: _sort_key(t, today))
    backlog.sort(key=lambda t: _sort_key(t, today))

    return {"urgent": urgent, "this_week": this_week, "backlog": backlog}
