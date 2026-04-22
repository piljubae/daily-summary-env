# Slack API Direct Fetcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Slack Web API로 내 멘션 스레드 + 지정 채널 메시지를 직접 가져와, Gemini로 요약하고 .md 파일로 저장하는 2모듈 파이프라인 구축.

**Architecture:** `slack_api.py`가 Slack API를 호출하여 raw 스레드를 수집하고, `slack_summarizer.py`가 Gemini로 요약한 뒤 .md 파일을 생성/업데이트한다. 기존 `fetch_slack_summary.py`는 .md 파일 읽기 전담으로 그대로 유지. 스레드-파일 매핑은 `.slack_meta.json`으로 관리.

**Tech Stack:** Python 3, requests (이미 사용 중), Slack Web API, Gemini API (기존 패턴)

**토큰 정보:**
- `SLACK_USER_TOKEN` (`xoxp-`) — `search.messages` 전용 (Bot Token으로는 검색 불가)
- `SLACK_BOT_TOKEN` (`xoxb-`) — `conversations.history`, `conversations.replies`, `users.info`
- 둘 다 `.env`에 이미 존재

---

### Task 1: config.py에 Slack API 설정 추가

**Files:**
- Modify: `config.py:86-90` (CONFIG dict 끝부분)

**Step 1: 설정 추가**

`slack_summary_dir` 설정 아래에 추가:

```python
    # Slack API 설정 (직접 연동)
    # search.messages는 User Token 필요 (Bot Token으로 불가)
    "slack_user_token": os.environ.get("SLACK_USER_TOKEN", ""),
    "slack_bot_token": os.environ.get("SLACK_BOT_TOKEN", ""),
    # 모니터링할 채널 ID 목록 (콤마 구분)
    "slack_watch_channels": [c.strip() for c in os.environ.get("SLACK_WATCH_CHANNELS", "").split(",") if c.strip()],
```

**Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add Slack API token and watch channel config"
```

---

### Task 2: fetchers/slack_api.py — Slack API raw 수집

**Files:**
- Create: `fetchers/slack_api.py`

**Step 1: 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack Web API를 통한 스레드 수집.

User Token(xoxp-)으로 멘션 검색, Bot Token(xoxb-)으로 스레드 조회.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import CONFIG


_SLACK_API = "https://slack.com/api"


def _get(endpoint, token, params=None):
    """Slack API GET 호출. rate-limit(429) 시 자동 재시도."""
    url = f"{_SLACK_API}/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"  ⏳ Slack rate-limit, {retry_after}s 대기...")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            print(f"  ⚠️ Slack API 오류 ({endpoint}): {data.get('error')}")
            return None
        return data
    return None


def _get_my_user_id(user_token):
    """auth.test로 내 User ID 조회."""
    data = _get("auth.test", user_token)
    return data["user_id"] if data else None


def _search_mentions(user_token, user_id, since_date):
    """search.messages로 내 멘션 검색.

    Args:
        user_token: xoxp- 토큰
        user_id: 내 Slack User ID
        since_date: 이 날짜 이후의 메시지 검색 (YYYY-MM-DD)

    Returns:
        list[dict]: [{"channel_id": str, "thread_ts": str}, ...]
    """
    query = f"<@{user_id}> after:{since_date}"
    threads = []
    page = 1

    while True:
        data = _get("search.messages", user_token, {
            "query": query,
            "sort": "timestamp",
            "sort_dir": "asc",
            "count": 100,
            "page": page,
        })
        if not data:
            break

        matches = data.get("messages", {}).get("matches", [])
        if not matches:
            break

        for msg in matches:
            channel_id = msg.get("channel", {}).get("id", "")
            # 스레드의 root ts: thread_ts가 있으면 사용, 없으면 ts 자체가 root
            thread_ts = msg.get("thread_ts") or msg.get("ts", "")
            if channel_id and thread_ts:
                threads.append({
                    "channel_id": channel_id,
                    "thread_ts": thread_ts,
                })

        paging = data.get("messages", {}).get("paging", {})
        if page >= paging.get("pages", 1):
            break
        page += 1

    # 중복 제거 (같은 스레드에서 여러 멘션 가능)
    seen = set()
    unique = []
    for t in threads:
        key = (t["channel_id"], t["thread_ts"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def _get_channel_threads(bot_token, channel_id, oldest_ts):
    """conversations.history로 채널의 최근 메시지 → 스레드 루트 수집."""
    threads = []
    cursor = None

    while True:
        params = {
            "channel": channel_id,
            "oldest": oldest_ts,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        data = _get("conversations.history", bot_token, params)
        if not data:
            break

        for msg in data.get("messages", []):
            if msg.get("thread_ts") == msg.get("ts"):
                threads.append({
                    "channel_id": channel_id,
                    "thread_ts": msg["ts"],
                })

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return threads


def _get_thread_replies(bot_token, channel_id, thread_ts):
    """conversations.replies로 스레드 전체 메시지 조회."""
    messages = []
    cursor = None

    while True:
        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor

        data = _get("conversations.replies", bot_token, params)
        if not data:
            break

        for msg in data.get("messages", []):
            messages.append({
                "user": msg.get("user", ""),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", ""),
            })

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return messages


def _resolve_user_names(bot_token, messages):
    """메시지 내 user ID를 display name으로 치환."""
    user_ids = {m["user"] for m in messages if m["user"]}
    name_cache = {}

    for uid in user_ids:
        if uid in name_cache:
            continue
        data = _get("users.info", bot_token, {"user": uid})
        if data:
            profile = data.get("user", {}).get("profile", {})
            name_cache[uid] = (
                profile.get("display_name")
                or profile.get("real_name")
                or uid
            )
        else:
            name_cache[uid] = uid

    for msg in messages:
        msg["user_name"] = name_cache.get(msg["user"], msg["user"])

    return messages


def _get_channel_name(bot_token, channel_id):
    """conversations.info로 채널 이름 조회."""
    data = _get("conversations.info", bot_token, {"channel": channel_id})
    if data:
        return data.get("channel", {}).get("name", channel_id)
    return channel_id


def _load_meta(summary_dir):
    """스레드-파일 매핑 메타데이터 로드."""
    meta_path = Path(summary_dir) / ".slack_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_fetched_ts": "0", "threads": {}}


def _get_since_ts(meta):
    """마지막 조회 시점의 timestamp 반환."""
    ts = meta.get("last_fetched_ts", "0")
    if ts and ts != "0":
        return ts
    # 메타가 없으면 7일 전부터
    week_ago = datetime.now() - timedelta(days=7)
    return str(week_ago.timestamp())


def fetch_slack_threads():
    """Slack API로 내 멘션 + 지정 채널의 스레드를 수집한다.

    Returns:
        list[dict]: [{
            "channel_id": str,
            "channel_name": str,
            "thread_ts": str,
            "messages": [{"user": str, "user_name": str, "text": str, "ts": str}, ...],
        }]
        토큰 미설정 시 빈 리스트 반환.
    """
    user_token = CONFIG.get("slack_user_token", "")
    bot_token = CONFIG.get("slack_bot_token", "")
    watch_channels = CONFIG.get("slack_watch_channels", [])
    summary_dir = CONFIG.get("slack_summary_dir", "")

    if not user_token or not bot_token:
        return []

    meta = _load_meta(summary_dir)
    since_ts = _get_since_ts(meta)
    # search.messages용 날짜 문자열
    since_date = datetime.fromtimestamp(float(since_ts)).strftime("%Y-%m-%d")

    print(f"  📡 Slack 멘션 검색 (since {since_date})...")

    # 1. 내 멘션 스레드 수집
    my_id = _get_my_user_id(user_token)
    if not my_id:
        print("  ⚠️ Slack User ID 조회 실패")
        return []

    mention_threads = _search_mentions(user_token, my_id, since_date)
    print(f"  ✅ 멘션 스레드 {len(mention_threads)}건 발견")

    # 2. 지정 채널 스레드 수집
    channel_threads = []
    for ch_id in watch_channels:
        ch_threads = _get_channel_threads(bot_token, ch_id, since_ts)
        channel_threads.extend(ch_threads)
        print(f"  ✅ 채널 {ch_id}: 스레드 {len(ch_threads)}건")

    # 3. 중복 제거
    all_thread_keys = set()
    all_threads = []
    for t in mention_threads + channel_threads:
        key = (t["channel_id"], t["thread_ts"])
        if key not in all_thread_keys:
            all_thread_keys.add(key)
            all_threads.append(t)

    print(f"  📥 총 {len(all_threads)}개 스레드의 메시지 조회 중...")

    # 4. 각 스레드의 전체 replies 조회
    result = []
    channel_name_cache = {}
    for t in all_threads:
        ch_id = t["channel_id"]
        if ch_id not in channel_name_cache:
            channel_name_cache[ch_id] = _get_channel_name(bot_token, ch_id)

        messages = _get_thread_replies(bot_token, ch_id, t["thread_ts"])
        messages = _resolve_user_names(bot_token, messages)

        result.append({
            "channel_id": ch_id,
            "channel_name": channel_name_cache[ch_id],
            "thread_ts": t["thread_ts"],
            "messages": messages,
        })

    print(f"  ✅ Slack 스레드 {len(result)}건 수집 완료")
    return result
```

**Step 2: Commit**

```bash
git add fetchers/slack_api.py
git commit -m "feat: add Slack API raw thread fetcher"
```

---

### Task 3: fetchers/slack_summarizer.py — AI 요약 + .md 저장

**Files:**
- Create: `fetchers/slack_summarizer.py`

**Step 1: 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack 스레드를 Gemini로 요약하고 .md 파일로 저장.

slack_api.py가 수집한 raw 스레드를 받아서:
1. Gemini로 구조화된 요약 생성
2. 스레드당 .md 파일 생성/업데이트
3. README.md 인덱스 갱신
4. .slack_meta.json 메타데이터 업데이트
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from config import CONFIG


def _summarize_thread_with_gemini(thread, api_key):
    """단일 스레드를 Gemini로 요약하여 markdown을 반환한다.

    Args:
        thread: {"channel_name": str, "thread_ts": str, "messages": [...]}
        api_key: Gemini API key

    Returns:
        str: 요약된 markdown 텍스트. 실패 시 None.
    """
    channel = thread["channel_name"]
    messages_text = ""
    for msg in thread["messages"]:
        ts = datetime.fromtimestamp(float(msg["ts"]))
        time_str = ts.strftime("%m/%d %H:%M")
        name = msg.get("user_name", msg.get("user", "unknown"))
        messages_text += f"[{time_str}] {name}: {msg['text']}\n"

    prompt = f"""다음은 Slack 채널 #{channel}의 스레드 대화입니다. 이 내용을 구조화된 마크다운으로 요약하세요.

요약 형식:
1. 제목: "# [번호]. [토픽 제목]" (대화의 핵심 주제를 한 줄로)
2. 메타데이터:
   - **채널**: #{channel}
   - **기간**: (대화 날짜 범위)
   - **관련 문서**: (대화에서 언급된 URL이 있으면 포함)
3. 본문:
   - 배경/이슈 설명
   - 결정 사항 또는 진행 상황
   - Next Action (있으면)

규칙:
- 한국어로 작성
- 불필요한 인사/잡담 제거
- 기술적 세부사항은 유지
- Jira 티켓, PR, 문서 링크는 반드시 포함
- 제목의 번호는 "00"으로 (나중에 재번호 부여)

스레드 내용:
{messages_text}

요약:"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    retry_delays = [10, 30, 60]
    for attempt, delay in enumerate(retry_delays, start=1):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (429, 500, 503) and attempt < len(retry_delays):
                print(f"    ⏳ Gemini {status}, {delay}s 대기...")
                time.sleep(delay)
            else:
                print(f"    ⚠️ Gemini 요약 실패: {e}")
                return None
        except Exception as e:
            print(f"    ⚠️ Gemini 요약 실패: {e}")
            return None
    return None


def _make_filename(title, index):
    """제목에서 파일명 생성. 예: '02_광고DSP_Phase2.md'"""
    # 특수문자 제거, 공백을 _로
    clean = re.sub(r"[^\w가-힣\s]", "", title)
    clean = re.sub(r"\s+", "_", clean.strip())
    if len(clean) > 30:
        clean = clean[:30]
    return f"{index:02d}_{clean}.md"


def _extract_title(markdown_content):
    """markdown에서 H1 제목 텍스트 추출."""
    match = re.search(r"^#\s+(.+)", markdown_content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # "00. " 접두사 제거
        title = re.sub(r"^\d+\.\s*", "", title)
        return title
    return "Untitled"


def _load_meta(summary_dir):
    """메타데이터 로드."""
    meta_path = Path(summary_dir) / ".slack_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_fetched_ts": "0", "threads": {}}


def _save_meta(summary_dir, meta):
    """메타데이터 저장."""
    meta_path = Path(summary_dir) / ".slack_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _regenerate_readme(summary_dir, meta):
    """README.md 인덱스를 재생성한다."""
    dir_path = Path(summary_dir)
    md_files = sorted(f for f in dir_path.glob("*.md") if f.name.lower() != "readme.md")

    if not md_files:
        return

    lines = ["# Slack 멘션 정리\n"]
    lines.append(f"> 자동 생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("## 인덱스\n")
    lines.append("| # | 토픽 | 채널 | 파일 |")
    lines.append("|---|---|---|---|")

    for idx, md_file in enumerate(md_files, 1):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, PermissionError):
            continue

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        channel_match = re.search(r"\*\*채널\*\*:\s*`?#?([\w\-_]+)", content)
        channel = channel_match.group(1) if channel_match else ""

        lines.append(f"| {idx:02d} | [{title}](./{md_file.name}) | #{channel} | {md_file.name} |")

    lines.append("")
    readme_path = dir_path / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")


def summarize_and_save(threads):
    """스레드 목록을 요약하여 .md 파일로 저장한다.

    Args:
        threads: fetch_slack_threads()의 반환값

    Returns:
        int: 생성/업데이트된 파일 수
    """
    summary_dir = CONFIG.get("slack_summary_dir", "")
    api_key = CONFIG.get("gemini_api_key") or __import__("os").environ.get("GEMINI_API_KEY", "")

    if not summary_dir or not threads:
        return 0

    if not api_key:
        print("  ⚠️ Gemini API Key 미설정 — Slack 요약 생략")
        return 0

    dir_path = Path(summary_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    meta = _load_meta(summary_dir)
    updated_count = 0

    # 기존 .md 파일 수 (새 파일 번호 매기기용)
    existing_files = sorted(dir_path.glob("[0-9]*.md"))
    next_index = len(existing_files) + 1

    for thread in threads:
        thread_key = f"{thread['channel_id']}_{thread['thread_ts']}"

        print(f"  🤖 요약 중: #{thread['channel_name']} ({len(thread['messages'])}건)...")

        # Gemini로 요약
        summary_md = _summarize_thread_with_gemini(thread, api_key)
        if not summary_md:
            continue

        # 기존 파일이 있는지 확인
        existing_filename = meta.get("threads", {}).get(thread_key, {}).get("filename")

        if existing_filename and (dir_path / existing_filename).exists():
            # 기존 파일 업데이트 (전체 재요약으로 교체)
            filepath = dir_path / existing_filename
            # 번호 유지: 기존 파일명에서 번호 추출
            num_match = re.match(r"(\d+)", existing_filename)
            if num_match:
                file_num = int(num_match.group(1))
                title = _extract_title(summary_md)
                # 번호를 기존 것으로 교체
                summary_md = re.sub(
                    r"^#\s+\d+\.\s*",
                    f"# {file_num:02d}. ",
                    summary_md,
                    count=1,
                    flags=re.MULTILINE,
                )
            filepath.write_text(summary_md, encoding="utf-8")
            print(f"    📝 업데이트: {existing_filename}")
        else:
            # 새 파일 생성
            title = _extract_title(summary_md)
            # 번호 부여
            summary_md = re.sub(
                r"^#\s+\d+\.\s*",
                f"# {next_index:02d}. ",
                summary_md,
                count=1,
                flags=re.MULTILINE,
            )
            filename = _make_filename(title, next_index)
            filepath = dir_path / filename
            filepath.write_text(summary_md, encoding="utf-8")

            meta.setdefault("threads", {})[thread_key] = {
                "filename": filename,
                "channel_id": thread["channel_id"],
                "channel_name": thread["channel_name"],
            }
            print(f"    🆕 생성: {filename}")
            next_index += 1

        updated_count += 1

    # 마지막 fetch 시점 업데이트
    if threads:
        max_ts = max(
            msg["ts"]
            for t in threads
            for msg in t["messages"]
        ) if any(t["messages"] for t in threads) else "0"
        meta["last_fetched_ts"] = max_ts

    _save_meta(summary_dir, meta)
    _regenerate_readme(summary_dir, meta)

    print(f"  ✅ Slack 요약 {updated_count}건 완료")
    return updated_count
```

**Step 2: Commit**

```bash
git add fetchers/slack_summarizer.py
git commit -m "feat: add Slack thread summarizer with Gemini"
```

---

### Task 4: daily_summary.py에 Slack API 단계 통합

**Files:**
- Modify: `daily_summary.py:20-21` (import 추가)
- Modify: `daily_summary.py:80-82` (fetch_all 호출 전에 Slack API 단계 삽입)
- Modify: `fetchers/__init__.py` (export 추가)

**Step 1: fetchers/__init__.py에 export 추가**

import 블록에:
```python
from .slack_api import fetch_slack_threads
from .slack_summarizer import summarize_and_save as summarize_slack_threads
```

`__all__` 리스트에:
```python
    'fetch_slack_threads',
    'summarize_slack_threads',
```

**Step 2: daily_summary.py에 import 추가**

line 20 (`from fetchers import fetch_all`) 을:
```python
from fetchers import fetch_all, fetch_slack_threads, summarize_slack_threads
```

**Step 3: fetch_all 호출 전에 Slack API 단계 삽입**

`data = fetch_all(target_date, start_iso, end_iso)` (line 82) 바로 위에:

```python
    # Slack API → .md 파일 업데이트 (fetch_all이 .md를 읽기 전에 실행)
    slack_bot_token = CONFIG.get("slack_bot_token") or os.environ.get("SLACK_BOT_TOKEN", "")
    slack_user_token = CONFIG.get("slack_user_token") or os.environ.get("SLACK_USER_TOKEN", "")
    if slack_bot_token and slack_user_token:
        print("📡 Slack API 스레드 수집 중...")
        CONFIG["slack_bot_token"] = slack_bot_token
        CONFIG["slack_user_token"] = slack_user_token
        raw_threads = fetch_slack_threads()
        if raw_threads:
            print("🤖 Slack 스레드 요약 중...")
            summarize_slack_threads(raw_threads)
    else:
        print("ℹ️ Slack API Token 미설정 — 기존 .md 파일만 사용")
```

**Step 4: Commit**

```bash
git add daily_summary.py fetchers/__init__.py
git commit -m "feat: integrate Slack API pipeline into daily_summary main flow"
```

---

### Task 5: 수동 검증

**Step 1: Slack API 연결 테스트**

```bash
cd /Users/pilju.bae/daily-summary-env
python3 -c "
from fetchers.slack_api import fetch_slack_threads
threads = fetch_slack_threads()
print(f'스레드 수: {len(threads)}')
for t in threads[:3]:
    print(f'  #{t[\"channel_name\"]}: {len(t[\"messages\"])}건 메시지')
"
```

Expected: 스레드가 조회되고 채널 이름과 메시지 수가 표시.

**Step 2: 요약 + 파일 저장 테스트**

```bash
python3 -c "
from fetchers.slack_api import fetch_slack_threads
from fetchers.slack_summarizer import summarize_and_save
threads = fetch_slack_threads()
if threads:
    # 첫 번째 스레드만 테스트
    count = summarize_and_save(threads[:1])
    print(f'저장된 파일: {count}건')
"
```

Expected: .md 파일이 생성/업데이트되고, `.slack_meta.json`이 생성됨.

**Step 3: 전체 파이프라인 dry-run**

```bash
python3 daily_summary.py --today 2>&1 | head -30
```

Expected: "📡 Slack API 스레드 수집 중..." → "🤖 Slack 스레드 요약 중..." → 정상 진행.
