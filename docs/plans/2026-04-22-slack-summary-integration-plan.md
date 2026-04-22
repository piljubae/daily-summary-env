# Slack 요약 fetcher 통합 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `~/Documents/Claude Cowork/Slack/` 디렉토리의 Slack 스레드 요약 .md 파일들을 daily-summary에 통합하여, markdown 리포트에 간략 섹션을 추가하고 Gemini 요약에 전체 컨텍스트를 제공한다.

**Architecture:** 기존 fetcher 패턴(pure function → FetchedData 필드 → formatter 소비)을 그대로 따른다. 새 fetcher는 디렉토리 내 .md 파일을 읽어 dict로 반환하고, formatter는 README의 "이번 주 포커스"만 간략 표시하되, Gemini prompt에는 전체 텍스트를 전달한다.

**Tech Stack:** Python 3, pathlib, 기존 config/fetcher/formatter 패턴

---

### Task 1: config.py에 slack_summary_dir 설정 추가

**Files:**
- Modify: `config.py:35-86` (CONFIG dict)

**Step 1: 설정 추가**

`config.py`의 CONFIG dict에 다음 항목을 추가한다 (gcal 설정 블록 아래):

```python
    # Slack 요약 파일 디렉토리
    # 외부 자동화가 매일 오전 9시에 Slack 멘션 스레드 요약을 .md 파일로 생성
    # 빈 문자열이면 Slack 요약 섹션 생략
    "slack_summary_dir": os.environ.get("SLACK_SUMMARY_DIR", str(Path.home() / "Documents" / "Claude Cowork" / "Slack")),
```

**Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add slack_summary_dir config setting"
```

---

### Task 2: fetchers/slack_summary.py 작성

**Files:**
- Create: `fetchers/slack_summary.py`

**Step 1: fetcher 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slack 스레드 요약 파일 fetcher."""

import re
from pathlib import Path

from config import CONFIG


def fetch_slack_summary() -> dict:
    """Slack 요약 디렉토리에서 .md 파일을 읽어 반환한다.

    Returns:
        dict: {
            "topics": [{"filename": str, "title": str, "content": str}, ...],
            "readme_content": str,
            "focus_lines": list[str],  # "이번 주 포커스" 불릿 라인
            "full_text": str,          # 모든 파일 합친 텍스트 (Gemini용)
        }
        디렉토리가 없거나 빈 경우 빈 dict 반환.
    """
    summary_dir = CONFIG.get("slack_summary_dir", "")
    if not summary_dir:
        return {}

    dir_path = Path(summary_dir)
    if not dir_path.is_dir():
        return {}

    md_files = sorted(dir_path.glob("*.md"))
    if not md_files:
        return {}

    readme_content = ""
    topics = []
    all_parts = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, PermissionError):
            continue

        if md_file.name.lower() == "readme.md":
            readme_content = content
            all_parts.append(content)
            continue

        # 첫 번째 H1에서 제목 추출
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        topics.append({
            "filename": md_file.name,
            "title": title,
            "content": content,
        })
        all_parts.append(content)

    # README에서 "이번 주 포커스" 섹션 추출
    focus_lines = []
    if readme_content:
        focus_match = re.search(
            r"##\s*이번\s*주\s*포커스\s*\n((?:- .+\n?)+)",
            readme_content,
        )
        if focus_match:
            for line in focus_match.group(1).strip().splitlines():
                line = line.strip()
                if line.startswith("- "):
                    focus_lines.append(line[2:])

    return {
        "topics": topics,
        "readme_content": readme_content,
        "focus_lines": focus_lines,
        "full_text": "\n\n---\n\n".join(all_parts),
    }
```

**Step 2: Commit**

```bash
git add fetchers/slack_summary.py
git commit -m "feat: add Slack summary fetcher"
```

---

### Task 3: FetchedData 및 fetch_all에 통합

**Files:**
- Modify: `fetchers/all.py:18` (import 추가)
- Modify: `fetchers/all.py:46` (필드 추가)
- Modify: `fetchers/all.py:77` (fetch 호출 추가)
- Modify: `fetchers/__init__.py` (export 추가)

**Step 1: all.py에 import 추가**

line 24 (calendar import 아래)에 추가:

```python
from .slack_summary import fetch_slack_summary
```

**Step 2: FetchedData에 필드 추가**

`# ── 여기에 새 필드 추가` 주석 위에:

```python
    slack_summary: dict = field(default_factory=dict)
```

**Step 3: fetch_all()에 호출 추가**

`# ── 여기에 새 fetcher 호출 추가` 주석 위에:

```python
        slack_summary=fetch_slack_summary(),
```

**Step 4: __init__.py에 export 추가**

import 블록에 추가:
```python
from .slack_summary import fetch_slack_summary
```

`__all__` 리스트의 `'fetch_calendar_events'` 아래에 추가:
```python
    'fetch_slack_summary',
```

**Step 5: Commit**

```bash
git add fetchers/all.py fetchers/__init__.py
git commit -m "feat: integrate slack_summary into FetchedData pipeline"
```

---

### Task 4: markdown 리포트에 간략 섹션 추가

**Files:**
- Modify: `formatters/markdown.py:128-148` (create_markdown_report 함수)

**Step 1: data에서 slack_summary 추출**

`create_markdown_report()` 함수 상단의 변수 추출 블록(line ~147)에 추가:

```python
    slack_summary = data.slack_summary
```

**Step 2: 간략 섹션 추가**

calendar_events 섹션(line ~189) 바로 아래에 Slack 토픽 섹션 삽입:

```python
    # 📬 Slack 주요 토픽
    if slack_summary and slack_summary.get("topics"):
        topic_count = len(slack_summary["topics"])
        report += f"**📬 Slack 주요 토픽** ({topic_count}건)\n"
        for line in slack_summary.get("focus_lines", []):
            report += f"- {line}\n"
        if not slack_summary.get("focus_lines"):
            for t in slack_summary["topics"][:5]:
                report += f"- {t['title']}\n"
            if topic_count > 5:
                report += f"- ...외 {topic_count - 5}건\n"
        report += "\n"
```

**Step 3: Commit**

```bash
git add formatters/markdown.py
git commit -m "feat: add Slack topics section to markdown report"
```

---

### Task 5: Gemini prompt에 Slack 컨텍스트 전달

**Files:**
- Modify: `formatters/markdown.py:392-498` (summarize_with_gemini 함수)

**Step 1: 함수 시그니처 변경**

```python
def summarize_with_gemini(md_content, api_key, slack_context=""):
```

**Step 2: prompt에 Slack 컨텍스트 삽입**

prompt 문자열 내, `리포트 내용:` 바로 위에 Slack 컨텍스트 블록 추가:

```python
    slack_block = ""
    if slack_context:
        slack_block = f"""

## Slack 스레드 요약 (이번 주 주요 토픽)

아래는 이번 주 Slack에서 논의된 주요 토픽의 상세 내용입니다.
오늘의 플랜을 세울 때 이 맥락을 반영하세요 — 테스트 상태, 임박 일정, 액션 아이템 등.

{slack_context}
"""
```

그리고 prompt의 `리포트 내용:` 부분을:

```python
리포트 내용:
{md_content}
{slack_block}
```

**Step 3: 호출부 수정**

`daily_summary.py` 또는 `markdown.py` 내에서 `summarize_with_gemini()`를 호출하는 곳을 찾아, `slack_context` 인자를 전달하도록 수정.

`daily_summary.py`에서 호출하는 경우:
```python
slack_text = data.slack_summary.get("full_text", "") if data.slack_summary else ""
summary = summarize_with_gemini(md_content, api_key, slack_context=slack_text)
```

**Step 4: Commit**

```bash
git add formatters/markdown.py daily_summary.py
git commit -m "feat: pass Slack context to Gemini for richer daily plan"
```

---

### Task 6: 수동 검증

**Step 1: dry-run 실행**

```bash
cd /Users/pilju.bae/daily-summary-env
python daily_summary.py --today 2>&1 | head -50
```

출력된 markdown에서:
- `📬 Slack 주요 토픽` 섹션이 표시되는지 확인
- Gemini 요약의 "오늘의 플랜"에 Slack 맥락이 반영되는지 확인

**Step 2: 빈 디렉토리 케이스 확인**

`SLACK_SUMMARY_DIR`를 존재하지 않는 경로로 설정 후 실행 → 에러 없이 Slack 섹션만 생략되는지 확인.

**Step 3: Commit (최종)**

```bash
git add -A
git commit -m "docs: add slack summary integration design and plan"
```
