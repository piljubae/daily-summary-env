# 데일리 할일 추천 개선 구현 플랜

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Jira 데이터 확장 + 액션 기반 그룹핑 + 어제 작업 연결 + Gemini 프롬프트 구조화로 데일리 할일 추천 품질을 개선한다.

**Architecture:** `todo.py`(데이터 수집) → `todo_matcher.py`(어제 연결) → `todo_scorer.py`(그룹 분류/정렬) → `markdown.py`(렌더링+프롬프트). 3개 모듈로 책임을 분리하고, `markdown.py`에서 순서대로 호출한다.

**Tech Stack:** Python 3.14, requests, Jira REST API v3, Gemini API

**Design doc:** `docs/plans/2026-03-09-daily-todo-enhancement-design.md`

**Testing:** 프로젝트에 pytest 미설치 상태. Task 0에서 설치 후 TDD 진행.

---

### Task 0: 테스트 환경 셋업

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_todo_scorer.py` (빈 파일)
- Create: `tests/test_todo_matcher.py` (빈 파일)

**Step 1: pytest 설치**

```bash
cd /Users/pilju.bae/daily-summary-env
source venv/bin/activate
pip install pytest
```

**Step 2: tests 디렉토리 생성**

```bash
mkdir -p tests
touch tests/__init__.py
touch tests/test_todo_scorer.py
touch tests/test_todo_matcher.py
```

**Step 3: pytest 실행 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/ -v`
Expected: `no tests ran` (0 collected)

**Step 4: Commit**

```bash
git add tests/ && git commit -m "chore: 테스트 환경 셋업 (pytest + tests 디렉토리)"
```

---

### Task 1: todo.py — Jira 필드 확장 + changelog 파싱

**Files:**
- Modify: `fetchers/todo.py`
- Test: `tests/test_todo.py`

**Step 1: 파싱 로직 테스트 작성**

`tests/test_todo.py`:

```python
"""todo.py의 Jira 응답 파싱 로직 테스트."""
from datetime import datetime, timezone


def _make_issue(key="KMA-1", summary="test", status="진행 중",
                priority="High", duedate=None, updated="2026-03-08T10:00:00.000+0900",
                comment_body=None, changelog_status_date=None):
    """테스트용 Jira issue dict 생성 헬퍼."""
    issue = {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "priority": {"name": priority} if priority else None,
            "duedate": duedate,
            "updated": updated,
            "comment": {
                "total": 1 if comment_body else 0,
                "comments": [
                    {"body": {"content": [{"content": [{"text": comment_body}]}]},
                     "updated": "2026-03-09T08:00:00.000+0900"}
                ] if comment_body else [],
            },
        },
        "changelog": {
            "histories": [
                {
                    "created": changelog_status_date or "2026-03-06T09:00:00.000+0900",
                    "items": [{"field": "status", "toString": status}],
                }
            ] if changelog_status_date or True else [],
        },
    }
    return issue


class TestParseIssue:
    def test_basic_fields(self):
        from fetchers.todo import parse_issue
        issue = _make_issue(key="KMA-100", summary="로그인 개선",
                            status="진행 중", priority="High",
                            duedate="2026-03-12")
        result = parse_issue(issue)
        assert result["key"] == "KMA-100"
        assert result["summary"] == "로그인 개선"
        assert result["status"] == "진행 중"
        assert result["priority"] == "High"
        assert result["duedate"] == "2026-03-12"

    def test_none_priority(self):
        from fetchers.todo import parse_issue
        issue = _make_issue(priority=None)
        result = parse_issue(issue)
        assert result["priority"] is None

    def test_latest_comment_truncated(self):
        from fetchers.todo import parse_issue
        long_comment = "A" * 100
        issue = _make_issue(comment_body=long_comment)
        result = parse_issue(issue)
        assert len(result["latest_comment"]) <= 50

    def test_no_comments(self):
        from fetchers.todo import parse_issue
        issue = _make_issue(comment_body=None)
        result = parse_issue(issue)
        assert result["latest_comment"] is None

    def test_status_changed_at_from_changelog(self):
        from fetchers.todo import parse_issue
        issue = _make_issue(changelog_status_date="2026-03-07T14:00:00.000+0900")
        result = parse_issue(issue)
        assert "2026-03-07" in result["status_changed_at"]
```

**Step 2: 테스트 실패 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_issue'`

**Step 3: todo.py 리팩토링 — parse_issue 함수 추출 + 필드 확장**

`fetchers/todo.py` 전체 재작성:

```python
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
                "expand": ["changelog"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        return [parse_issue(issue) for issue in resp.json().get("issues", [])]

    except Exception as e:
        print(f"⚠️ Jira API 조회 실패: {e}", file=sys.stderr)
        return []
```

**Step 4: 테스트 통과 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add fetchers/todo.py tests/test_todo.py
git commit -m "refactor(todo): Jira 필드 확장 + parse_issue 함수 추출

fields에 priority, duedate, updated, comment 추가.
expand=changelog로 상태 변경일 추출.
기존 3-bucket 분류 로직은 제거 — todo_scorer로 이관 예정."
```

---

### Task 2: todo_matcher.py — 어제 작업 티켓키 매칭

**Files:**
- Create: `fetchers/todo_matcher.py`
- Test: `tests/test_todo_matcher.py`

**Step 1: 테스트 작성**

`tests/test_todo_matcher.py`:

```python
"""todo_matcher.py 테스트 — 어제 데이터에서 티켓키 추출 + 매칭."""
from fetchers.todo_matcher import extract_ticket_keys, tag_yesterday_tickets


class TestExtractTicketKeys:
    def test_from_git_commits(self):
        """antigravity_data의 커밋 메시지에서 티켓키를 추출한다."""
        fetched = _mock_fetched_data(
            antigravity_data={
                "commits": [
                    {"message": "feat(KMA-1234): 로그인 개선"},
                    {"message": "fix: typo"},
                    {"message": "KMA-5678 결제 버그 수정"},
                ]
            }
        )
        keys = extract_ticket_keys(fetched)
        assert "KMA-1234" in keys
        assert "KMA-5678" in keys

    def test_from_claude_context(self):
        """claude_context의 goal/summary에서 티켓키를 추출한다."""
        fetched = _mock_fetched_data(
            claude_context=[
                {"goal": "KMA-999 리팩토링 작업", "summary": "완료"},
            ]
        )
        keys = extract_ticket_keys(fetched)
        assert "KMA-999" in keys

    def test_from_cli_history(self):
        """claude_cli_history의 command에서 티켓키를 추출한다."""
        fetched = _mock_fetched_data(
            claude_cli_history=[
                {"command": "/commit KMA-100 fix login", "timestamp": "2026-03-08"},
            ]
        )
        keys = extract_ticket_keys(fetched)
        assert "KMA-100" in keys

    def test_empty_data(self):
        fetched = _mock_fetched_data()
        keys = extract_ticket_keys(fetched)
        assert keys == set()

    def test_deduplication(self):
        fetched = _mock_fetched_data(
            antigravity_data={"commits": [
                {"message": "KMA-1 first"},
                {"message": "KMA-1 second"},
            ]}
        )
        keys = extract_ticket_keys(fetched)
        assert keys == {"KMA-1"}


class TestTagYesterdayTickets:
    def test_matching_ticket_gets_flag(self):
        tickets = [
            {"key": "KMA-1", "summary": "task1"},
            {"key": "KMA-2", "summary": "task2"},
        ]
        result = tag_yesterday_tickets(tickets, {"KMA-1"})
        assert result[0]["yesterday"] is True
        assert result[1]["yesterday"] is False

    def test_no_mutation_of_original(self):
        tickets = [{"key": "KMA-1", "summary": "task1"}]
        original_keys = set(tickets[0].keys())
        tag_yesterday_tickets(tickets, {"KMA-1"})
        # 원본 dict가 변경되지 않아야 함 (shallow copy)
        # 참고: 구현에서 copy를 쓰든 in-place를 쓰든 결과만 맞으면 됨


def _mock_fetched_data(antigravity_data=None, claude_context=None,
                       claude_cli_history=None):
    """FetchedData를 흉내내는 간단한 객체."""
    class MockFetched:
        pass
    m = MockFetched()
    m.antigravity_data = antigravity_data or {}
    m.claude_context = claude_context or []
    m.claude_cli_history = claude_cli_history or []
    return m
```

**Step 2: 테스트 실패 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo_matcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetchers.todo_matcher'`

**Step 3: todo_matcher.py 구현**

`fetchers/todo_matcher.py`:

```python
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
```

**Step 4: 테스트 통과 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo_matcher.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add fetchers/todo_matcher.py tests/test_todo_matcher.py
git commit -m "feat(todo_matcher): 어제 작업 티켓키 추출 + 오늘 할일 매칭

git commits, Claude 세션, CLI 히스토리에서 티켓키를 추출하고
오늘 할일 티켓에 'yesterday' 플래그를 부여한다."
```

---

### Task 3: todo_scorer.py — 액션 그룹 분류 + 태그 + 정렬

**Files:**
- Create: `fetchers/todo_scorer.py`
- Test: `tests/test_todo_scorer.py`

**Step 1: 테스트 작성**

`tests/test_todo_scorer.py`:

```python
"""todo_scorer.py 테스트 — 액션 기반 그룹 분류, 태그, 정렬."""
from datetime import date
from fetchers.todo_scorer import score_and_group, compute_tags


def _ticket(key="KMA-1", status="할일", priority=None, duedate=None,
            updated="2026-03-08T10:00:00.000+0900", yesterday=False,
            latest_comment=None, latest_comment_updated=None,
            status_changed_at="2026-03-06T09:00:00.000+0900"):
    return {
        "key": key, "summary": f"ticket {key}", "status": status,
        "priority": priority, "duedate": duedate, "updated": updated,
        "yesterday": yesterday, "latest_comment": latest_comment,
        "latest_comment_updated": latest_comment_updated,
        "status_changed_at": status_changed_at,
    }


class TestScoreAndGroup:
    """그룹 분류 테스트."""

    def test_due_tomorrow_is_urgent(self):
        """마감이 내일이면 '오늘 집중' 그룹."""
        today = date(2026, 3, 9)
        t = _ticket(duedate="2026-03-10")
        result = score_and_group([t], today=today)
        assert len(result["urgent"]) == 1

    def test_high_priority_in_progress_is_urgent(self):
        """High + 진행중이면 '오늘 집중' 그룹."""
        today = date(2026, 3, 9)
        t = _ticket(priority="High", status="진행 중")
        result = score_and_group([t], today=today)
        assert len(result["urgent"]) == 1

    def test_recent_comment_is_urgent(self):
        """24시간 내 코멘트가 달린 티켓은 '오늘 집중' 그룹."""
        today = date(2026, 3, 9)
        t = _ticket(latest_comment="리뷰 부탁",
                    latest_comment_updated="2026-03-09T08:00:00.000+0900")
        result = score_and_group([t], today=today)
        assert len(result["urgent"]) == 1

    def test_due_in_3_days_is_this_week(self):
        """마감이 3일 후면 '이번주 내' 그룹."""
        today = date(2026, 3, 9)
        t = _ticket(duedate="2026-03-12")
        result = score_and_group([t], today=today)
        assert len(result["this_week"]) == 1

    def test_in_progress_not_urgent_is_this_week(self):
        """진행중이지만 긴급 조건 아닌 것은 '이번주 내' 그룹."""
        today = date(2026, 3, 9)
        t = _ticket(status="진행 중", priority="Medium")
        result = score_and_group([t], today=today)
        assert len(result["this_week"]) == 1

    def test_no_conditions_is_backlog(self):
        """아무 조건도 해당 안 되면 '백로그'."""
        today = date(2026, 3, 9)
        t = _ticket(status="할일")
        result = score_and_group([t], today=today)
        assert len(result["backlog"]) == 1

    def test_sorting_within_group(self):
        """그룹 내 정렬: 마감 임박 → 우선순위 → 최신."""
        today = date(2026, 3, 9)
        t1 = _ticket(key="KMA-1", duedate="2026-03-11", priority="High", status="진행 중")
        t2 = _ticket(key="KMA-2", duedate="2026-03-10", priority="Medium", status="진행 중")
        result = score_and_group([t1, t2], today=today)
        urgent = result["urgent"]
        # KMA-2(D-1)이 KMA-1(D-2)보다 먼저
        assert urgent[0]["key"] == "KMA-2"


class TestComputeTags:
    """태그 계산 테스트."""

    def test_due_date_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(duedate="2026-03-10")
        tags = compute_tags(t, today=today)
        assert "D-1" in tags

    def test_high_priority_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(priority="High")
        tags = compute_tags(t, today=today)
        assert "📍High" in tags

    def test_highest_priority_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(priority="Highest")
        tags = compute_tags(t, today=today)
        assert "📍Highest" in tags

    def test_comment_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(latest_comment="도와주세요",
                    latest_comment_updated="2026-03-09T08:00:00.000+0900")
        tags = compute_tags(t, today=today)
        assert "💬코멘트" in tags

    def test_stale_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(updated="2026-02-25T10:00:00.000+0900")
        tags = compute_tags(t, today=today)
        assert any("💤" in tag for tag in tags)

    def test_yesterday_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(yesterday=True)
        tags = compute_tags(t, today=today)
        assert "🔄어제이어서" in tags

    def test_days_in_status_tag(self):
        today = date(2026, 3, 9)
        t = _ticket(status="진행 중",
                    status_changed_at="2026-03-06T09:00:00.000+0900")
        tags = compute_tags(t, today=today)
        assert "진행중 3일째" in tags
```

**Step 2: 테스트 실패 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: todo_scorer.py 구현**

`fetchers/todo_scorer.py`:

```python
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
```

**Step 4: 테스트 통과 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/test_todo_scorer.py -v`
Expected: 14 passed

**Step 5: Commit**

```bash
git add fetchers/todo_scorer.py tests/test_todo_scorer.py
git commit -m "feat(todo_scorer): 액션 기반 그룹 분류 + 태그 계산 + 정렬

오늘집중/이번주내/백로그 3개 그룹으로 분류.
D-N, 📍High, 💬코멘트, 💤방치, 🔄어제이어서, N일째 태그 자동 계산.
그룹 내 마감임박→우선순위→최신 순 정렬."
```

---

### Task 4: fetchers/__init__.py 업데이트

**Files:**
- Modify: `fetchers/__init__.py`

**Step 1: export 추가**

`fetchers/__init__.py`에 새 모듈 추가:

```python
"""Fetchers package for daily summary data collection."""

from .activitywatch import fetch_window_events, fetch_web_events
from .claude import fetch_claude_context
from .cowork import fetch_cowork_sessions
from .firebender import fetch_firebender_activity
from .antigravity import fetch_antigravity_activity
from .todo import fetch_today_todos
from .todo_matcher import extract_ticket_keys, tag_yesterday_tickets
from .todo_scorer import score_and_group
from .calendar import fetch_calendar_events
from .all import FetchedData, fetch_all

__all__ = [
    # 개별 fetcher (직접 사용이 필요한 경우)
    'fetch_window_events',
    'fetch_web_events',
    'fetch_claude_context',
    'fetch_cowork_sessions',
    'fetch_firebender_activity',
    'fetch_antigravity_activity',
    'fetch_today_todos',
    'fetch_calendar_events',
    # 할일 추천 파이프라인
    'extract_ticket_keys',
    'tag_yesterday_tickets',
    'score_and_group',
    # 통합 인터페이스 (권장)
    'FetchedData',
    'fetch_all',
]
```

**Step 2: import 확인**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -c "from fetchers import score_and_group, extract_ticket_keys; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add fetchers/__init__.py
git commit -m "chore: fetchers __init__에 todo_matcher, todo_scorer export 추가"
```

---

### Task 5: markdown.py — 할일 렌더링 재작성

**Files:**
- Modify: `formatters/markdown.py` (lines 15-18, 296-308)

**Step 1: import 변경**

`formatters/markdown.py` 상단 import를 수정:

```python
# Before (lines 15-18):
from fetchers import (
    fetch_today_todos,
    fetch_calendar_events,
)

# After:
from fetchers import (
    fetch_today_todos,
    fetch_calendar_events,
    extract_ticket_keys,
    tag_yesterday_tickets,
    score_and_group,
)
```

**Step 2: 할일 섹션 렌더링 교체**

`formatters/markdown.py`의 lines 296-308 (📌 오늘의 할일 섹션)을 교체:

```python
    # 📌 오늘의 할일 (Jira) — 액션 기반 그룹핑
    raw_tickets = fetch_today_todos()
    if raw_tickets:
        yesterday_keys = extract_ticket_keys(fetched_data)
        tagged_tickets = tag_yesterday_tickets(raw_tickets, yesterday_keys)
        grouped = score_and_group(tagged_tickets)

        total_count = len(grouped["urgent"]) + len(grouped["this_week"]) + len(grouped["backlog"])
        if total_count > 0:
            report += f"**📌 오늘의 할일** ({total_count}건)\n\n"

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
```

주의: `create_markdown_report` 함수에 `fetched_data` 파라미터가 전달되어야 함. 현재 시그니처를 확인하고 필요시 추가.

**Step 3: create_markdown_report 시그니처 확인 및 수정**

현재 `formatters/markdown.py`의 `create_markdown_report` 함수 시그니처와 `daily_summary.py`에서 호출부를 확인해서, `fetched_data`를 인자로 받도록 조정. (현재 `fetched_data`의 개별 필드들을 인자로 받고 있다면, `fetched_data` 객체 자체를 추가 인자로 전달.)

**Step 4: 수동 테스트**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python daily_summary.py --today`

마크다운 파일을 열어서 `📌 오늘의 할일` 섹션이 `🔴 오늘 집중` / `🟡 이번주 내` / `⚪ 백로그` 그룹으로 나뉘는지 확인.

**Step 5: Commit**

```bash
git add formatters/markdown.py daily_summary.py
git commit -m "feat(markdown): 오늘의 할일 섹션 액션 기반 그룹핑으로 재작성

상태 기반 3-bucket(진행중/리뷰/할일) → 액션 기반 3-group(오늘집중/이번주내/백로그).
각 티켓에 D-N, 📍High, 💬코멘트, 💤방치, 🔄어제이어서, N일째 태그 표시."
```

---

### Task 6: Gemini 프롬프트 구조화

**Files:**
- Modify: `formatters/markdown.py` (lines 396-424, `summarize_with_gemini` 함수 내 프롬프트)

**Step 1: 프롬프트 파트 2 교체**

`formatters/markdown.py`의 프롬프트 (lines 396-419)에서 파트 2 부분을 교체:

```python
        prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 바탕으로 두 파트로 나누어 요약해주세요.

## 파트 1: 어제의 핵심 활동 (5가지)

요구사항:
1. **타이틀(Title)**: 활동의 핵심 내용을 명확하게 요약 (예: "로그인 페이지 UI 구현")
2. **설명(Description)**: 구체적인 작업 내용, 성과, 또는 이슈 (한 문장)
3. **관련 링크(Related Links)**: 해당 활동과 직접 관련된 URL (없으면 생략)
4. **번호 매기기**: 1번부터 5번까지 중요도 순으로 나열
5. **언어**: 한국어
6. **링크 형식 필수 준수**: 반드시 `[링크 제목](URL)` 형식을 사용할 것. (예: `[GitHub PR](https://...)`)

## 파트 2: 오늘의 플랜

리포트에 "📌 오늘의 할일" 섹션과 "📅 오늘 미팅" 섹션이 있다면, 이를 바탕으로 오늘 실제로 실행할 플랜을 3~5개 제안하라.

### 우선순위 판단 기준 (반드시 적용):
1. 🔴 오늘 집중 그룹 → 최우선. 마감/코멘트 응답 등 이유 명시
2. 🔄어제이어서 태그가 붙은 티켓 → 연속성 유지 관점에서 우선 추천
3. 미팅 전후 시간 활용 → 미팅 시간대를 피한 집중 작업 블록 제안
4. 🟡 이번주 내 그룹 → 여유 시간에 착수 권장
5. ⚪ 백로그 → 시간 남을 때만 언급
6. "N일째" 수치가 큰 티켓은 장기화 → 마무리 가능하면 우선 완료 권장

해당 섹션이 없으면 이 파트는 생략.

출력 형식 (반드시 준수):

**📊 어제의 핵심 활동**

1. **[타이틀]**
   [설명]
   - 🔗 [링크 제목](URL)

2. **[타이틀]**
   [설명]
   ...

**📌 오늘의 플랜**

1. **[티켓번호 + 액션 동사]**
   └ [근거 1줄: 왜 지금 해야 하는지]

2. **[티켓번호 + 액션 동사]**
   └ [근거 1줄]

3. **[HH:MM 미팅명]** (N시간)

4. **[티켓번호 + 액션 동사]**
   └ [근거 1줄]

...

주의사항:
- 번호 + **볼드 타이틀** (티켓번호 + 액션 동사) 형식 필수
- 다음 줄에 └ 근거 1줄 (왜 지금 해야 하는지)
- 미팅은 시간과 소요시간만 간결하게 (근거 줄 불필요)
- 단순 티켓 나열 금지. 반드시 "무엇을 할지" 액션 동사 포함 (예: ✗ "로그인 리팩토링" → ✓ "로그인 리팩토링 마무리")
- 미팅이 있으면, 미팅 시간을 기준으로 작업 순서를 배치

리포트 내용:
{md_content}

요약:"""
```

**Step 2: 수동 테스트**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python daily_summary.py --today`

생성된 마크다운 파일의 AI 요약 섹션에서:
- `📌 오늘의 플랜` 항목이 **볼드 타이틀 + └ 근거** 형식인지 확인
- 🔴 오늘 집중 그룹 항목이 최우선으로 추천되는지 확인
- 미팅이 시간순으로 배치되는지 확인

**Step 3: Commit**

```bash
git add formatters/markdown.py
git commit -m "feat(gemini): 오늘의 플랜 프롬프트 구조화

우선순위 판단 기준 6가지 명시, 볼드 타이틀 + └ 근거 출력 형식 강제,
액션 동사 필수, 미팅 시간 기반 작업 순서 배치."
```

---

### Task 7: 전체 통합 테스트 + 최종 확인

**Step 1: 전체 유닛 테스트**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests passed

**Step 2: 실제 실행 (E2E)**

Run: `cd /Users/pilju.bae/daily-summary-env && source venv/bin/activate && python daily_summary.py --today`

확인 항목:
1. `📌 오늘의 할일` — 🔴/🟡/⚪ 그룹으로 나뉘는지
2. 각 티켓에 태그(D-N, 📍, 💬, 💤, 🔄, N일째)가 표시되는지
3. `📌 오늘의 플랜` — 볼드 타이틀 + └ 근거 형식인지
4. 에러 없이 완료되는지

**Step 3: 최종 Commit**

```bash
git add -A
git commit -m "feat: 데일리 할일 추천 개선 완료

- Jira 필드 확장 (priority, duedate, comment, changelog)
- 액션 기반 3그룹 분류 (오늘집중/이번주내/백로그)
- 어제 작업 티켓 자동 매칭 (🔄어제이어서)
- 진행 기간 표시 (N일째)
- Gemini 프롬프트 구조화 (우선순위 기준 + 출력 형식)"
```
