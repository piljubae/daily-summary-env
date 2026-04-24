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

    prompt = f"""다음 Slack 스레드를 마크다운 문서로 요약하라. 코드 펜스 없이 마크다운 원문만 출력하라.

# 00. [토픽 제목]

- **채널**: #{channel}
- **기간**: [대화 날짜 범위]
- **관련 문서**: [URL이 있으면 포함]

## 배경

[이슈/맥락 설명]

## 진행 상황

[결정 사항, 누가 무엇을 했는지]

## Next Action

[후속 조치가 있으면]

위 형식을 따라 작성하라. 규칙:
- 한국어
- 인사/잡담 제거, 기술적 세부사항 유지
- Jira 티켓, PR, 문서 링크는 반드시 포함
- 제목 번호는 00으로 유지 (나중에 재번호)
- 코드 펜스(```)로 감싸지 말 것

스레드:
{messages_text}"""

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
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            # 코드 펜스 제거 (```markdown ... ``` 등)
            text = re.sub(r"^```\w*\n?", "", text.strip())
            text = re.sub(r"\n?```$", "", text.strip())
            return text
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


def _regenerate_readme(summary_dir):
    """README.md 인덱스를 재생성한다. 외부 자동화가 관리하는 README는 덮어쓰지 않는다."""
    dir_path = Path(summary_dir)
    readme_path = dir_path / "README.md"
    # "이번 주 포커스" 섹션이 있으면 외부 자동화가 관리하는 파일 → 스킵
    if readme_path.exists():
        try:
            content = readme_path.read_text(encoding="utf-8")
            if "이번 주 포커스" in content:
                return
        except (IOError, PermissionError):
            pass

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
    _regenerate_readme(summary_dir)

    print(f"  ✅ Slack 요약 {updated_count}건 완료")
    return updated_count
