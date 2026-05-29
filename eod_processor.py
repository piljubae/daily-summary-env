#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EOD Review Processor.

Usage:
    python eod_processor.py --send     # 6pm: DM 전송
    python eod_processor.py --process  # 6:30pm: 스레드 읽어서 처리
"""

import argparse
import json
import os
import sys
from datetime import date
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
    return bot


def _open_pending_slack_topics() -> list[str]:
    """종결되지 않은 Slack .md 파일 제목 반환."""
    topics = []
    slack_path = Path(_SLACK_DIR)
    if not slack_path.exists():
        return topics
    for p in sorted(slack_path.glob("[0-9]*.md")):
        try:
            content = p.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue
        if "종결" in content:
            continue
        title = content.split("\n")[0].lstrip("# ").strip()
        if title:
            topics.append(f"• {title} (`{p.name}`)")
    return topics


def cmd_send():
    """6pm: 오늘 항목을 DM으로 전송하고 state 저장."""
    bot_token = _slack_tokens()
    if not bot_token:
        print("❌ SLACK_BOT_TOKEN 미설정", file=sys.stderr)
        return 1

    my_user_id = CONFIG.get("slack_my_user_id") or os.environ.get("SLACK_MY_USER_ID", "U0AD2U8TEES")
    channel_id = open_dm_channel(bot_token, my_user_id)
    if not channel_id:
        print("❌ DM 채널 열기 실패", file=sys.stderr)
        return 1

    today = date.today()
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = f"{today.month}/{today.day}({weekday_names[today.weekday()]})"

    tickets = fetch_today_todos()
    jira_lines = [f"• [{t['key']}] {t['summary'][:50]}" for t in tickets[:10]]

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
    """6:30pm: 스레드 읽어서 Jira + .md 업데이트."""
    bot_token = _slack_tokens()
    if not bot_token:
        print("❌ SLACK_BOT_TOKEN 미설정", file=sys.stderr)
        return 1

    if not _STATE_FILE.exists():
        print("❌ ~/.eod_state.json 없음 — --send 먼저 실행하세요", file=sys.stderr)
        return 1

    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ state 파일 읽기 실패: {e}", file=sys.stderr)
        return 1
    if state.get("date") != date.today().isoformat():
        print("⚠️ 오늘 state 없음 — --send가 오늘 실행됐는지 확인", file=sys.stderr)
        return 1

    replies = read_thread_replies(bot_token, state["channel_id"], state["ts"])
    if not replies:
        _post_summary(bot_token, state, "오늘 EOD 리뷰 표시 없음.")
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
    _post_summary(bot_token, state, summary)
    print(f"✅ 처리 완료: {len(results)}건")
    return 0


def _post_summary(bot_token: str, state: dict, summary_text: str):
    ch, ts = post_message(bot_token, state["channel_id"], summary_text, thread_ts=state["ts"])
    if not ch:
        print("⚠️ 요약 메시지 전송 실패", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="EOD Review Processor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--send", action="store_true", help="6pm: DM 전송")
    group.add_argument("--process", action="store_true", help="6:30pm: 스레드 처리")
    args = parser.parse_args()

    if args.send:
        sys.exit(cmd_send())
    elif args.process:
        sys.exit(cmd_process())


if __name__ == "__main__":
    main()
