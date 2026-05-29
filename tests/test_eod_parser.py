from eod_parser import parse_reply

def test_parse_done_with_jira_key():
    action = parse_reply("KMA-7382 완료")
    assert action == {"type": "done", "jira_key": "KMA-7382", "raw": "KMA-7382 완료"}

def test_parse_handoff_with_name():
    action = parse_reply("KMA-6390 인수인계→박지은")
    assert action == {"type": "handoff", "jira_key": "KMA-6390", "to": "박지은", "raw": "KMA-6390 인수인계→박지은"}

def test_parse_continue():
    action = parse_reply("KMA-6390 계속")
    assert action == {"type": "continue", "jira_key": "KMA-6390", "raw": "KMA-6390 계속"}

def test_parse_no_jira_key_fuzzy():
    action = parse_reply("노출표준화 인수인계→최민규")
    assert action["type"] == "handoff"
    assert action["jira_key"] is None
    assert action["topic_hint"] == "노출표준화"
    assert action["to"] == "최민규"

def test_parse_unrecognized_returns_none():
    assert parse_reply("아무말") is None
