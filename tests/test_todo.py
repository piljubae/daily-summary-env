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
