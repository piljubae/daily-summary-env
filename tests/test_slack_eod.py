from unittest.mock import patch, MagicMock
from fetchers.slack_api import open_dm_channel, post_message, read_thread_replies

def test_open_dm_channel():
    with patch("fetchers.slack_api.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "channel": {"id": "D12345"}}
        )
        result = open_dm_channel("xoxb-token", "U0AD2U8TEES")
    assert result == "D12345"

def test_open_dm_channel_failure():
    with patch("fetchers.slack_api.requests.post") as mock_post:
        mock_post.side_effect = Exception("network error")
        result = open_dm_channel("xoxb-token", "U0AD2U8TEES")
    assert result is None

def test_post_message_returns_ts():
    with patch("fetchers.slack_api.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "channel": "D12345", "ts": "1234567890.123"}
        )
        channel, ts = post_message("xoxb-token", "D12345", "안녕")
    assert channel == "D12345"
    assert ts == "1234567890.123"

def test_read_thread_replies_excludes_root():
    messages = [
        {"user": "U1", "text": "root", "ts": "1.0"},
        {"user": "U2", "text": "reply", "ts": "2.0"},
    ]
    with patch("fetchers.slack_api._get_thread_replies", return_value=messages):
        result = read_thread_replies("xoxb-token", "D12345", "1.0")
    assert len(result) == 1
    assert result[0]["text"] == "reply"
