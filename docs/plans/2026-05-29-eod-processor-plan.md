# EOD Processor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 매일 6pm에 Slack DM으로 오늘 Jira/Slack 리뷰 항목을 물어보고, 6:15pm에 답글을 읽어서 Jira 업데이트 + 로컬 .md 파일 자동 반영.

**Architecture:** `eod_processor.py` 단일 스크립트에 `--send` / `--process` 두 모드. 상태(channel_id + ts)는 `~/.eod_state.json`에 저장. 두 개의 launchd plist가 각각 6:00pm/6:15pm(KST)에 실행.

**Tech Stack:** Python 3, Slack Web API (bot/user token), Jira REST API v3, launchd

---

### Task 1: Jira 헬퍼 — 티켓 Done 전환 + 코멘트 추가

**Files:**
- Modify: `fetchers/todo.py`

**Step 1: 실패 테스트 작성**

```python
# tests/test_todo_jira_update.py
from unittest.mock import patch, MagicMock
from fetchers.todo import transition_to_done, add_jira_comment

def test_transition_to_done_calls_correct_endpoints():
    transitions = {"transitions": [{"id": "31", "name": "완료"}]}
    with patch("fetchers.todo.requests.get") as mock_get, \
         patch("fetchers.todo.requests.post") as mock_post:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: transitions)
        mock_post.return_value = MagicMock(status_code=204)
        result = transition_to_done("KMA-7382")
    assert result is True
    mock_post.assert_called_once()

def test_add_jira_comment():
    with patch("fetchers.todo.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {"id": "123"})
        result = add_jira_comment("KMA-7382", "인수인계 완료 → 박지은님 (EOD 리뷰)")
    assert result is True
```

**Step 2: 테스트 실패 확인**
```bash
./venv/bin/python3 -m pytest tests/test_todo_jira_update.py -v
```
Expected: FAIL — `transition_to_done` not found

**Step 3: 구현**

`fetchers/todo.py` 하단에 추가:

```python
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
    """Jira 티켓에 텍스트 코멘트 추가."""
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
```

**Step 4: 테스트 통과 확인**
```bash
./venv/bin/python3 -m pytest tests/test_todo_jira_update.py -v
```

**Step 5: 커밋**
```bash
git add fetchers/todo.py tests/test_todo_jira_update.py
git commit -m "feat: add transition_to_done and add_jira_comment to todo fetcher"
```

---

### Task 2: Slack 헬퍼 — DM 전송 + 스레드 읽기 + 스레드 답글 달기

**Files:**
- Modify: `fetchers/slack_api.py`

**Step 1: 실패 테스트 작성**

```python
# tests/test_slack_eod.py
from unittest.mock import patch, MagicMock
from fetchers.slack_api import open_dm_channel, post_message, get_thread_replies_today

def test_open_dm_channel():
    with patch("fetchers.slack_api._get") as mock_get:
        mock_get.return_value = {"channel": {"id": "D12345"}}
        result = open_dm_channel("xoxb-token", "U0AD2U8TEES")
    assert result == "D12345"

def test_post_message_returns_ts():
    with patch("fetchers.slack_api.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "channel": "D12345", "ts": "1234567890.123"}
        )
        channel, ts = post_message("xoxb-token", "D12345", "안녕")
    assert channel == "D12345"
    assert ts == "1234567890.123"
```

**Step 2: 테스트 실패 확인**
```bash
./venv/bin/python3 -m pytest tests/test_slack_eod.py -v
```

**Step 3: 구현**

`fetchers/slack_api.py` 하단에 추가:

```python
def open_dm_channel(bot_token: str, user_id: str) -> str | None:
    """자신과의 DM 채널 ID 조회 (conversations.open)."""
    data = _get("conversations.open", bot_token, {"users": user_id})
    if data:
        return data.get("channel", {}).get("id")
    return None


def post_message(bot_token: str, channel_id: str, text: str,
                 thread_ts: str | None = None) -> tuple[str, str] | tuple[None, None]:
    """Slack 채널에 메시지 전송. (channel_id, ts) 반환."""
    import requests as _requests
    url = f"{_SLACK_API}/chat.postMessage"
    headers = {"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"}
    payload = {"channel": channel_id, "text": text, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    for attempt in range(3):
        resp = _requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 429:
            import time
            time.sleep(int(resp.headers.get("Retry-After", 5)))
            continue
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data["channel"], data["ts"]
        print(f"⚠️ chat.postMessage 실패: {data.get('error')}", file=sys.stderr)
        return None, None
    return None, None


def read_thread_replies(bot_token: str, channel_id: str, thread_ts: str) -> list[dict]:
    """스레드 답글 조회. 루트 메시지 제외, user/text/ts만 반환."""
    messages = _get_thread_replies(bot_token, channel_id, thread_ts)
    # 첫 번째(루트) 메시지 제외
    return messages[1:] if len(messages) > 1 else []
```

**Step 4: 테스트 통과 확인**
```bash
./venv/bin/python3 -m pytest tests/test_slack_eod.py -v
```

**Step 5: 커밋**
```bash
git add fetchers/slack_api.py tests/test_slack_eod.py
git commit -m "feat: add DM open/post/thread-read helpers to slack_api"
```

---

### Task 3: 답글 파서 — 텍스트 → 액션 변환

**Files:**
- Create: `eod_parser.py`

**Step 1: 실패 테스트 작성**

```python
# tests/test_eod_parser.py
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
```

**Step 2: 테스트 실패 확인**
```bash
./venv/bin/python3 -m pytest tests/test_eod_parser.py -v
```

**Step 3: 구현**

```python
# eod_parser.py
import re

_JIRA_KEY = re.compile(r'\b(KMA-\d+)\b', re.IGNORECASE)
_DONE_KW = re.compile(r'완료|done|finish|닫기', re.IGNORECASE)
_CONTINUE_KW = re.compile(r'계속|continue|skip|유지', re.IGNORECASE)
_HANDOFF_KW = re.compile(r'인수인계|handoff|넘김|넘겼', re.IGNORECASE)
_HANDOFF_TARGET = re.compile(r'(?:→|->|에게|께)\s*(.+)', re.IGNORECASE)


def parse_reply(text: str) -> dict | None:
    """한 줄 답글 텍스트를 액션 dict로 변환.

    Returns:
        dict with keys: type (done|handoff|continue), jira_key (str|None),
                        topic_hint (str|None), to (str, handoff only), raw (str)
        인식 불가 시 None.
    """
    text = text.strip()
    jira_match = _JIRA_KEY.search(text)
    jira_key = jira_match.group(1).upper() if jira_match else None

    # topic_hint: Jira 키 제거 후 액션 키워드 앞 텍스트
    topic_hint = None
    if not jira_key:
        # 액션 키워드 앞부분 추출
        for kw_pat in [_DONE_KW, _CONTINUE_KW, _HANDOFF_KW, _HANDOFF_TARGET]:
            m = kw_pat.search(text)
            if m:
                hint = text[:m.start()].strip()
                if hint:
                    topic_hint = hint
                break

    if _HANDOFF_KW.search(text):
        target_match = _HANDOFF_TARGET.search(text)
        to = target_match.group(1).strip() if target_match else ""
        return {"type": "handoff", "jira_key": jira_key, "topic_hint": topic_hint,
                "to": to, "raw": text}

    if _DONE_KW.search(text):
        return {"type": "done", "jira_key": jira_key, "topic_hint": topic_hint, "raw": text}

    if _CONTINUE_KW.search(text):
        return {"type": "continue", "jira_key": jira_key, "topic_hint": topic_hint, "raw": text}

    return None
```

**Step 4: 테스트 통과 확인**
```bash
./venv/bin/python3 -m pytest tests/test_eod_parser.py -v
```

**Step 5: 커밋**
```bash
git add eod_parser.py tests/test_eod_parser.py
git commit -m "feat: add EOD reply parser"
```

---

### Task 4: Slack .md 파일 업데이터 — 종결/인수인계 기록

**Files:**
- Create: `eod_md_updater.py`

**Step 1: 실패 테스트 작성**

```python
# tests/test_eod_md_updater.py
import tempfile, os
from pathlib import Path
from eod_md_updater import find_md_file, append_closure_note, append_handoff_note

def _make_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)

def test_find_md_file_by_keyword(tmp_path):
    (tmp_path / "07_노출표준화_QA.md").write_text("# 노출표준화\n## Next\n- 확인", encoding="utf-8")
    result = find_md_file("노출표준화", str(tmp_path))
    assert result is not None
    assert "노출표준화" in str(result)

def test_append_closure_note():
    p = _make_md("# 테스트\n## Next\n- 확인\n")
    append_closure_note(p, "2026-05-29")
    content = p.read_text(encoding="utf-8")
    assert "종결" in content
    assert "필주님 이후 추가 팔로업 없음" in content

def test_append_handoff_note():
    p = _make_md("# 테스트\n## Next\n- 확인\n")
    append_handoff_note(p, "박지은", "2026-05-29")
    content = p.read_text(encoding="utf-8")
    assert "박지은" in content
    assert "인수인계" in content
```

**Step 2: 테스트 실패 확인**
```bash
./venv/bin/python3 -m pytest tests/test_eod_md_updater.py -v
```

**Step 3: 구현**

```python
# eod_md_updater.py
from pathlib import Path
from datetime import date


def find_md_file(topic_hint: str, slack_dir: str) -> Path | None:
    """topic_hint와 파일명이 가장 잘 매칭되는 .md 파일 반환."""
    if not topic_hint or not slack_dir:
        return None
    hint_lower = topic_hint.lower().replace(" ", "")
    candidates = list(Path(slack_dir).glob("[0-9]*.md"))
    for p in candidates:
        if hint_lower in p.name.lower().replace(" ", ""):
            return p
    # 파일 내용에서 검색 (제목 줄)
    for p in candidates:
        try:
            first_line = p.read_text(encoding="utf-8").split("\n")[0].lower()
            if hint_lower in first_line.replace(" ", ""):
                return p
        except (IOError, UnicodeDecodeError):
            continue
    return None


def _already_closed(p: Path) -> bool:
    return "종결" in p.read_text(encoding="utf-8")


def append_closure_note(p: Path, today: str | None = None) -> bool:
    """파일 하단에 종결 섹션 추가. 이미 종결된 경우 스킵."""
    if _already_closed(p):
        return False
    today = today or date.today().isoformat()
    note = f"\n## 종결 ({today})\n\n- 필주님 이후 추가 팔로업 없음 (EOD 리뷰 완료 처리)\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(note)
    return True


def append_handoff_note(p: Path, to: str, today: str | None = None) -> bool:
    """파일 하단에 인수인계 섹션 추가."""
    if _already_closed(p):
        return False
    today = today or date.today().isoformat()
    note = (
        f"\n## 종결 ({today})\n\n"
        f"- **{to}님에게 인수인계 완료** — 필주님 이후 추가 팔로업 없음 (EOD 리뷰)\n"
    )
    with open(p, "a", encoding="utf-8") as f:
        f.write(note)
    return True
```

**Step 4: 테스트 통과 확인**
```bash
./venv/bin/python3 -m pytest tests/test_eod_md_updater.py -v
```

**Step 5: 커밋**
```bash
git add eod_md_updater.py tests/test_eod_md_updater.py
git commit -m "feat: add EOD Slack .md file updater"
```

---

### Task 5: 메인 스크립트 — `eod_processor.py` (`--send` / `--process`)

**Files:**
- Create: `eod_processor.py`

**Step 1: 수동 테스트 준비** (단위 테스트 대신 실행 흐름 확인)

아직 토큰 없이도 `--help` 가 동작하는지 확인:
```bash
./venv/bin/python3 eod_processor.py --help
```

**Step 2: 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EOD Review Processor.

Usage:
    python eod_processor.py --send     # 6pm: DM 전송
    python eod_processor.py --process  # 6:15pm: 스레드 읽어서 처리
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from config import CONFIG
from fetchers.todo import fetch_today_todos, transition_to_done, add_jira_comment
from fetchers.slack_api import open_dm_channel, post_message, read_thread_replies
from eod_parser import parse_reply
from eod_md_updater import find_md_file, append_closure_note, append_handoff_note

_STATE_FILE = Path.home() / ".eod_state.json"
_SLACK_DIR = CONFIG.get("slack_summary_dir", str(Path.home() / "Documents" / "Claude Cowork" / "Slack"))


def _slack_tokens():
    bot = CONFIG.get("slack_bot_token") or os.environ.get("SLACK_BOT_TOKEN", "")
    user = CONFIG.get("slack_user_token") or os.environ.get("SLACK_USER_TOKEN", "")
    return bot, user


def _open_pending_slack_topics() -> list[str]:
    """종결되지 않은 Slack .md 파일의 Next Action 요약 반환."""
    topics = []
    for p in sorted(Path(_SLACK_DIR).glob("[0-9]*.md")):
        try:
            content = p.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue
        if "종결" in content:
            continue
        # Next 섹션에서 첫 번째 항목 추출
        for line in content.split("\n"):
            if line.startswith("- Next:") or (line.startswith("- ") and "Next" in content):
                pass
        # 파일 제목(첫 줄 # 제거)만 표시
        title = content.split("\n")[0].lstrip("# ").strip()
        if title:
            topics.append(f"• {title} (`{p.name}`)")
    return topics


def cmd_send():
    """6pm: 오늘 항목을 DM으로 전송하고 state 저장."""
    bot_token, _ = _slack_tokens()
    if not bot_token:
        print("❌ SLACK_BOT_TOKEN 미설정", file=sys.stderr)
        return 1

    my_user_id = "U0AD2U8TEES"
    channel_id = open_dm_channel(bot_token, my_user_id)
    if not channel_id:
        print("❌ DM 채널 열기 실패", file=sys.stderr)
        return 1

    today = date.today()
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = f"{today.month}/{today.day}({weekday_names[today.weekday()]})"

    # Jira 티켓
    tickets = fetch_today_todos()
    urgent = [t for t in tickets if t.get("priority") in ("Highest", "High") or "진행" in t.get("status", "")]
    others = [t for t in tickets if t not in urgent]

    jira_lines = []
    for t in (urgent + others)[:10]:
        jira_lines.append(f"• [{t['key']}] {t['summary'][:50]}")

    # 열린 Slack 토픽
    topic_lines = _open_pending_slack_topics()[:5]

    sections = [f"📋 *EOD 리뷰* | {date_str}", "스레드에 답글로 상태 알려주세요.\n"]
    if jira_lines:
        sections.append("*[Jira 활성 티켓]*\n" + "\n".join(jira_lines))
    if topic_lines:
        sections.append("*[이번주 Slack 토픽]*\n" + "\n".join(topic_lines))
    sections.append('\n답글 예시: `KMA-7382 완료` / `노출표준화 인수인계→박지은` / `KMA-6390 계속`')

    message = "\n\n".join(sections)
    ch, ts = post_message(bot_token, channel_id, message)
    if not ch:
        print("❌ 메시지 전송 실패", file=sys.stderr)
        return 1

    state = {"channel_id": ch, "ts": ts, "date": today.isoformat()}
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(f"✅ EOD 메시지 전송 완료 (ts={ts})")
    return 0


def cmd_process():
    """6:15pm: 스레드 읽어서 Jira + .md 업데이트."""
    bot_token, _ = _slack_tokens()
    if not bot_token:
        print("❌ SLACK_BOT_TOKEN 미설정", file=sys.stderr)
        return 1

    if not _STATE_FILE.exists():
        print("❌ ~/.eod_state.json 없음 — --send 먼저 실행하세요", file=sys.stderr)
        return 1

    state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    if state.get("date") != date.today().isoformat():
        print("⚠️ 오늘 state 없음 — --send가 오늘 실행됐는지 확인", file=sys.stderr)
        return 1

    replies = read_thread_replies(bot_token, state["channel_id"], state["ts"])
    if not replies:
        _post_summary(bot_token, state, [], "오늘 EOD 리뷰 표시 없음.")
        return 0

    results = []
    for msg in replies:
        text = msg.get("text", "").strip()
        if not text:
            continue
        action = parse_reply(text)
        if not action:
            continue

        jira_key = action.get("jira_key")
        topic_hint = action.get("topic_hint")
        atype = action["type"]

        result_line = f"• `{text}`"

        if atype == "done":
            if jira_key:
                ok = transition_to_done(jira_key)
                result_line += f" → {jira_key} {'Done 전환' if ok else '코멘트 추가'}"
            if topic_hint:
                p = find_md_file(topic_hint, _SLACK_DIR)
                if p:
                    append_closure_note(p)
                    result_line += f" → `{p.name}` 종결 기록"

        elif atype == "handoff":
            to = action.get("to", "")
            if jira_key:
                add_jira_comment(jira_key, f"인수인계 완료 → {to}님 (EOD 리뷰)")
                result_line += f" → {jira_key} 코멘트 추가"
            if topic_hint:
                p = find_md_file(topic_hint, _SLACK_DIR)
                if p:
                    append_handoff_note(p, to)
                    result_line += f" → `{p.name}` 인수인계 기록"

        elif atype == "continue":
            result_line += " → 그대로"

        results.append(result_line)

    summary = "✅ EOD 처리 완료\n" + "\n".join(results) if results else "처리된 항목 없음."
    _post_summary(bot_token, state, results, summary)
    print(f"✅ 처리 완료: {len(results)}건")
    return 0


def _post_summary(bot_token, state, results, summary_text):
    post_message(bot_token, state["channel_id"], summary_text, thread_ts=state["ts"])


def main():
    parser = argparse.ArgumentParser(description="EOD Review Processor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--send", action="store_true", help="6pm: DM 전송")
    group.add_argument("--process", action="store_true", help="6:15pm: 스레드 처리")
    args = parser.parse_args()

    if args.send:
        sys.exit(cmd_send())
    elif args.process:
        sys.exit(cmd_process())


if __name__ == "__main__":
    main()
```

**Step 3: 수동 smoke test**
```bash
# 토큰 확인
./venv/bin/python3 eod_processor.py --send
# Slack DM 확인 후
./venv/bin/python3 eod_processor.py --process
```

**Step 4: 커밋**
```bash
git add eod_processor.py
git commit -m "feat: add eod_processor.py with --send and --process modes"
```

---

### Task 6: launchd plist 2개 + 실행 스크립트

**Files:**
- Create: `com.piljubae.eod.send.plist`
- Create: `com.piljubae.eod.process.plist`
- Create: `run_eod_send.sh`
- Create: `run_eod_process.sh`

**Step 1: 실행 스크립트 생성**

`run_eod_send.sh`:
```bash
#!/bin/bash
PROJECT_DIR="/Users/pilju.bae/daily-summary-env"
cd "$PROJECT_DIR"
LOG_FILE="$PROJECT_DIR/automation.log"
echo "--- EOD Send: $(date) ---" >> "$LOG_FILE"
./venv/bin/python3 eod_processor.py --send >> "$LOG_FILE" 2>&1
echo "--- EOD Send Done: $(date) ---" >> "$LOG_FILE"
```

`run_eod_process.sh`:
```bash
#!/bin/bash
PROJECT_DIR="/Users/pilju.bae/daily-summary-env"
cd "$PROJECT_DIR"
LOG_FILE="$PROJECT_DIR/automation.log"
echo "--- EOD Process: $(date) ---" >> "$LOG_FILE"
./venv/bin/python3 eod_processor.py --process >> "$LOG_FILE" 2>&1
echo "--- EOD Process Done: $(date) ---" >> "$LOG_FILE"
```

**Step 2: plist 생성**

`com.piljubae.eod.send.plist` (6:00pm KST = 09:00 UTC):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.piljubae.eod.send</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/pilju.bae/daily-summary-env/run_eod_send.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/pilju.bae/daily-summary-env/eod_send_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/pilju.bae/daily-summary-env/eod_send_stderr.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/pilju.bae/daily-summary-env</string>
</dict>
</plist>
```

`com.piljubae.eod.process.plist` (6:15pm KST = 09:15 UTC):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.piljubae.eod.process</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/pilju.bae/daily-summary-env/run_eod_process.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>15</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/pilju.bae/daily-summary-env/eod_process_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/pilju.bae/daily-summary-env/eod_process_stderr.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/pilju.bae/daily-summary-env</string>
</dict>
</plist>
```

**Step 3: 실행 권한 + launchd 등록**
```bash
chmod +x run_eod_send.sh run_eod_process.sh

cp com.piljubae.eod.send.plist ~/Library/LaunchAgents/
cp com.piljubae.eod.process.plist ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.piljubae.eod.send.plist
launchctl load ~/Library/LaunchAgents/com.piljubae.eod.process.plist

# 등록 확인
launchctl list | grep piljubae.eod
```

**Step 4: 커밋**
```bash
git add com.piljubae.eod.send.plist com.piljubae.eod.process.plist run_eod_send.sh run_eod_process.sh
git commit -m "feat: add launchd plists for EOD send (6pm) and process (6:15pm)"
```

---

### Task 7: 전체 smoke test

**Step 1: --send 수동 실행**
```bash
./venv/bin/python3 eod_processor.py --send
```
Expected: Slack DM에 EOD 리뷰 메시지 수신, `~/.eod_state.json` 생성

**Step 2: 스레드에 테스트 답글 달기**
Slack DM 스레드에 직접 답글:
```
KMA-7382 완료
KMA-6390 계속
```

**Step 3: --process 수동 실행**
```bash
./venv/bin/python3 eod_processor.py --process
```
Expected: 스레드에 처리 결과 요약 달림, KMA-7382 Jira 코멘트 추가 확인

**Step 4: 최종 커밋**
```bash
git add -A
git commit -m "chore: EOD processor integration complete"
```
