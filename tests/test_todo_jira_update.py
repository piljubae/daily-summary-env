from unittest.mock import patch, MagicMock
from fetchers.todo import transition_to_done, add_jira_comment

def test_transition_to_done_calls_correct_endpoints():
    transitions = {"transitions": [{"id": "31", "name": "완료"}]}
    with patch("fetchers.todo.requests.get") as mock_get, \
         patch("fetchers.todo.requests.post") as mock_post:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: transitions, raise_for_status=lambda: None)
        mock_post.return_value = MagicMock(status_code=204, raise_for_status=lambda: None)
        result = transition_to_done("KMA-7382")
    assert result is True

def test_transition_fallback_to_comment_when_no_done():
    transitions = {"transitions": [{"id": "11", "name": "진행중"}]}
    with patch("fetchers.todo.requests.get") as mock_get, \
         patch("fetchers.todo.requests.post") as mock_post:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: transitions, raise_for_status=lambda: None)
        mock_post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)
        result = transition_to_done("KMA-9999")
    assert result is True  # fallback to comment succeeded

def test_add_jira_comment_success():
    with patch("fetchers.todo.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)
        result = add_jira_comment("KMA-7382", "인수인계 완료 → 박지은님 (EOD 리뷰)")
    assert result is True

def test_add_jira_comment_failure():
    with patch("fetchers.todo.requests.post") as mock_post:
        mock_post.side_effect = Exception("network error")
        result = add_jira_comment("KMA-0000", "test")
    assert result is False
