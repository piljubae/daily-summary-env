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
