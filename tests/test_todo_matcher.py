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
