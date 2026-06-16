#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown report formatter."""

import os
import re
import sys
import json
import time
import requests
from datetime import date
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

from config import CONFIG
from utils import format_seconds
from fetchers import (
    fetch_today_todos,
    extract_ticket_keys,
    tag_yesterday_tickets,
    score_and_group,
)


def categorize_apps(app_durations):
    """앱을 카테고리별로 분류

    Args:
        app_durations: {'앱이름': 시간_초} 딕셔너리

    Returns:
        dict: 카테고리별 앱 정보
    """
    categories = {
        "개발": {
            "keywords": ["vscode", "visual studio", "android studio", "terminal", "iterm",
                        "cmd", "powershell", "intellij", "pycharm", "sublime"],
            "apps": defaultdict(float)
        },
        "브라우저": {
            "keywords": ["chrome", "firefox", "safari", "edge", "brave"],
            "apps": defaultdict(float)
        },
        "커뮤니케이션": {
            "keywords": ["slack", "teams", "discord", "telegram", "zoom", "mail"],
            "apps": defaultdict(float)
        },
    }

    categorized = {cat: {"apps": {}} for cat in categories}
    uncategorized = {}

    for app_name, duration in app_durations.items():
        found = False
        for category, info in categories.items():
            for keyword in info["keywords"]:
                if keyword.lower() in app_name.lower():
                    categorized[category]["apps"][app_name] = duration
                    found = True
                    break
            if found:
                break

        if not found:
            uncategorized[app_name] = duration

    # 카테고리별 소계 계산
    for category in categories:
        total = sum(categorized[category]["apps"].values())
        categorized[category]["total"] = total

    categorized["기타"] = {
        "apps": uncategorized,
        "total": sum(uncategorized.values())
    }

    return categorized


def calculate_active_time(app_durations, domain_durations):
    """전체 활동 시간 계산

    Returns:
        tuple: (총_활동_시간_초, 시간대별_활동_시간)
    """
    total = sum(app_durations.values())

    # 시간대별 활동 시간 계산 (간단한 추정)
    hourly_activity = defaultdict(float)
    if app_durations:
        avg_per_app = total / len(app_durations)
        for i, (app, duration) in enumerate(sorted(app_durations.items(), key=lambda x: x[1], reverse=True)):
            hour = i % 24
            hourly_activity[hour] += duration

    return total, dict(hourly_activity)


def generate_productivity_summary(hourly_activity):
    """생산성 시간대 요약 생성"""
    productive_time = 0

    for start_hour, end_hour in CONFIG["productive_hours"]:
        for hour in range(start_hour, end_hour):
            productive_time += hourly_activity.get(hour, 0)

    return productive_time


def generate_one_liner(app_durations, domain_durations, total_time):
    """한줄 요약 생성 (AI 없이 규칙 기반)"""
    if not app_durations:
        return "오늘은 컴퓨터를 사용하지 않았습니다."

    top_app = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)[0]
    app_name = top_app[0]
    duration = format_seconds(top_app[1])

    if "chrome" in app_name.lower() or "firefox" in app_name.lower() or "safari" in app_name.lower():
        return f"주로 웹 브라우징에 {duration} 시간을 사용했습니다."
    elif "code" in app_name.lower() or "studio" in app_name.lower():
        return f"주로 코딩에 {duration} 시간을 사용했습니다."
    elif "slack" in app_name.lower() or "teams" in app_name.lower():
        return f"주로 협업 도구 사용에 {duration} 시간을 사용했습니다."
    else:
        return f"{app_name}에 {duration} 시간을 사용했습니다."


def create_markdown_report(data, target_date):
    """수집된 모든 데이터를 마크다운 보고서로 변환합니다.

    Args:
        data (FetchedData): fetch_all()이 반환한 데이터 컨테이너
        target_date (datetime): 요약 대상 날짜

    Returns:
        str: 마크다운 형식의 보고서
    """
    app_durations = data.app_durations
    domain_durations = data.domain_durations
    url_details = data.url_details
    cowork_sessions = data.cowork_sessions
    claude_context = data.claude_context
    firebender_tasks = data.firebender_tasks
    antigravity_data = data.antigravity_data
    calendar_events = data.calendar_events
    claude_cli_history = data.claude_cli_history
    slack_summary = data.slack_summary

    total_time, _ = calculate_active_time(app_durations, domain_durations)

    report = f"# {target_date.strftime('%m/%d')} 일일 요약\n\n"

    # 1줄: 총 활동 시간 + 가장 많이 쓴 앱 상위 3개
    if app_durations:
        top_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)[:3]
        apps_str = ", ".join(f"{name} {format_seconds(dur)}" for name, dur in top_apps)
        report += f"**💻 {format_seconds(total_time)}** — {apps_str}\n\n"

    # 2줄: 주요 방문 사이트 + 핵심 페이지 제목
    if domain_durations:
        top_domains = sorted(domain_durations.items(), key=lambda x: x[1], reverse=True)[:3]
        site_parts = []
        for rank, (domain, dur) in enumerate(top_domains, 1):
            # 해당 도메인에서 가장 오래 본 페이지 제목 1개
            domain_pages = [u for u in url_details if u["domain"] == domain and u.get("title")]
            page_durations = defaultdict(float)
            for p in domain_pages:
                title = p["title"].strip()
                if title:
                    page_durations[title] += p["duration"]
            if page_durations:
                top_page = sorted(page_durations.items(), key=lambda x: x[1], reverse=True)[0][0]
                # 페이지 제목이 너무 길면 자르기
                if len(top_page) > 40:
                    top_page = top_page[:40] + "..."
                site_parts.append(f"{rank}. {domain} ({top_page})")
            else:
                site_parts.append(f"{rank}. {domain}")
        report += f"**🌐 사이트** — {' / '.join(site_parts)}\n\n"

    # 📅 오늘 예정 미팅 (macOS Calendar)
    report += f"**📅 오늘 예정 미팅** ({len(calendar_events)}건)\n" if calendar_events else "**📅 오늘 예정 미팅**\n"
    if calendar_events:
        for ev in calendar_events:
            start_str = ev["start"].strftime("%H:%M")
            end_str = ev["end"].strftime("%H:%M")
            report += f"- {start_str}~{end_str} {ev['title']} ({ev['duration_min']}분)\n"
    else:
        report += "- (데이터 없음)\n"
    report += "\n"

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

    # 3~4줄: Cowork 작업 요약 (의도 + 결과 + 참고 리소스)
    cowork_tasks = cowork_sessions
    report += f"**🤖 Cowork** ({len(cowork_tasks)}건)\n" if cowork_tasks else "**🤖 Cowork**\n"
    if cowork_tasks:
        for task in cowork_tasks[:7]:
            line = f"- {task['intent']}"
            if task["result"]:
                line += f" — {task['result']}"
            report += line + "\n"
            # 참고한 URL이 있으면 도메인만 간결하게 표시
            if task["urls"]:
                domains = [urlparse(u).netloc for u in task["urls"]]
                report += f"  📎 {', '.join(domains)}\n"
        if len(cowork_tasks) > 7:
            report += f"- ...외 {len(cowork_tasks) - 7}건\n"
    else:
        report += "- (데이터 없음)\n"
    report += "\n"

    # 🤖 Claude 활동 (Local Agent)
    report += f"**🤖 Claude 활동** ({len(claude_context)}건)\n" if claude_context else "**🤖 Claude 활동**\n"
    if claude_context:
        for session in claude_context:
            title = session.get('title', '세션')
            duration = session.get('duration_min', 0)
            count = session.get('interaction_count', 0)
            
            report += f"### 📂 {title}\n"
            report += f"> ⏱️ **{duration}분** 동안 **{count}번**의 상호작용\n\n"
            
            report += f"**🎯 작업 목표**\n"
            report += f"{session['goal']}\n\n"
            
            has_changes = False
            if session['files_created']:
                report += f"- 🆕 **생성된 파일**: {', '.join(session['files_created'])}\n"
                has_changes = True
            if session['files_modified']:
                report += f"- 📝 **수정된 파일**: {', '.join(session['files_modified'])}\n"
                has_changes = True
            
            if not has_changes:
                report += "- ⚠️ 파일 변경 사항 없음\n"
                
            report += "\n"
    else:
        report += "- (데이터 없음)\n\n"

    # 🤖 Firebender 활동 (Android Studio)
    report += f"**🤖 Firebender (Android Studio)** ({len(firebender_tasks)}건)\n" if firebender_tasks else "**🤖 Firebender (Android Studio)**\n"
    if firebender_tasks:
        # 프로젝트별로 그룹화하여 표시
        by_project = defaultdict(list)
        for t in firebender_tasks:
            by_project[t["project"]].append(t["query"])
            
        for project, queries in by_project.items():
            report += f"### 📂 {project}\n"
            for q in queries:
                report += f"- {q}\n"

            report += "\n"
    else:
        report += "- (데이터 없음)\n\n"


    # 🤖 Antigravity 활동 (Self-Improvement)
    report += "**🤖 Antigravity 활동 (Self-Improvement)**\n"
    user_queries = antigravity_data.get('user_queries', []) if antigravity_data else []
    commit_messages = antigravity_data.get('commit_messages', []) if antigravity_data else []
    files = antigravity_data.get('files_modified', []) if antigravity_data else []
    has_antigravity = bool(user_queries or commit_messages or files)

    if not has_antigravity:
        report += "- (데이터 없음)\n"
    else:
        # AI 프롬프트 (사용자 질문)
        if user_queries:
            report += f"- 💬 **AI 프롬프트** ({len(user_queries)}건)\n"
            for query in user_queries:
                report += f"  - {query}\n"

        # 커밋 메시지 (활동 내역)
        if commit_messages:
            report += f"- 📝 **활동 내역** ({len(commit_messages)}건)\n"
            for msg in commit_messages:
                report += f"  - {msg}\n"

        # 수정된 파일
        if files:
            report += f"- 🛠️ **수정된 파일** ({len(files)}개)\n"
            for f in files[:10]:
                report += f"  - `{f}`\n"
            if len(files) > 10:
                report += f"  - ...외 {len(files) - 10}개\n"
    report += "\n"

    # 🖥️ Claude CLI (터미널 기록)
    if claude_cli_history:
        report += "---\n\n"
        report += f"## 🖥️ Claude CLI ({len(claude_cli_history)}건)\n\n"
        for item in claude_cli_history:
            timestamp = item['timestamp']
            cmd = item['command']
            time_str = timestamp.strftime("%H:%M:%S")
            report += f"- `{time_str}` `{cmd}`\n"
        report += "\n"

    # 📌 오늘의 할일 (Jira) — 액션 기반 그룹핑
    raw_tickets = fetch_today_todos()
    if raw_tickets:
        yesterday_keys = extract_ticket_keys(data)
        tagged_tickets = tag_yesterday_tickets(raw_tickets, yesterday_keys)
        grouped = score_and_group(tagged_tickets)

        total_count = len(grouped["urgent"]) + len(grouped["this_week"]) + len(grouped["backlog"])
        if total_count > 0:
            report += f"**📌 오늘의 할일** ({total_count}건)\n\n"

            group_config = [
                ("urgent", "🔴 오늘 집중"),
                ("this_week", "🟡 이번주 내"),
                ("backlog", "⚪ 백로그"),
            ]
            for group_key, group_label in group_config:
                items = grouped[group_key]
                if items:
                    report += f"{group_label} ({len(items)}건)\n"
                    for ticket in items:
                        tags_str = ", ".join(ticket["tags"]) if ticket["tags"] else ""
                        line = f"- [{ticket['key']}] {ticket['summary']}"
                        if tags_str:
                            line += f" — {tags_str}"
                        report += line + "\n"
                    report += "\n"

    # 📅 오늘 미팅 (fetch_all에서 오늘 날짜로 가져온 data.calendar_events 재사용)
    if calendar_events:
        report += f"**📅 오늘 미팅** ({len(calendar_events)}건)\n"
        for event in calendar_events:
            start_str = event["start"].strftime("%H:%M")
            end_str = event["end"].strftime("%H:%M")
            report += f"- {start_str}~{end_str} {event['title']} ({event['duration_min']}분)\n"
        report += "\n"

    # 상세 활동 목록 (Detailed Lists)
    report += "---\n\n"
    report += "## 📋 상세 활동 목록\n\n"
    
    # Claude 전체 대화 목록
    if claude_context:
        for session in claude_context:
            title = session.get('title', '세션')
            full_messages = session.get('full_messages', [])
            
            if full_messages:
                report += f"### 💬 Claude: {title}\n"
                for idx, msg in enumerate(full_messages, 1):
                    # Truncate very long messages
                    display_msg = msg[:150] + "..." if len(msg) > 150 else msg
                    display_msg = display_msg.replace("\n", " ")
                    report += f"{idx}. {display_msg}\n"
                report += "\n"
    
    # 웹사이트 타이틀 목록
    if url_details:
        report += "### 🌐 방문한 웹페이지\n"
        # Collect unique titles with URLs
        unique_pages = {}
        for u in url_details:
            title = u.get("title", "").strip()
            url = u.get("url", "")
            if title and url and title not in unique_pages:
                unique_pages[title] = url
        
        for idx, (title, url) in enumerate(sorted(unique_pages.items()), 1):
            display_title = title[:100] + "..." if len(title) > 100 else title
            report += f"{idx}. [{display_title}]({url})\n"
        report += "\n"

    # 4줄: 한줄 요약
    one_liner = generate_one_liner(app_durations, domain_durations, total_time)
    report += f"> {one_liner}\n"

    return report


def save_report(markdown_content, target_date):
    """보고서를 파일로 저장"""
    output_dir = Path(CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{target_date.date().isoformat()}-daily-summary.md"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return filepath


def summarize_with_gemini(md_content, api_key, slack_context=""):
    """Gemini API를 사용하여 일일 요약을 5가지 핵심 포인트로 요약"""
    if not api_key:
        return None

    today = date.today().strftime("%Y-%m-%d")

    slack_block = ""
    if slack_context:
        slack_block = f"""

## Slack 스레드 요약 (이번 주 주요 토픽)

아래는 이번 주 Slack에서 논의된 주요 토픽의 상세 내용입니다.
오늘의 플랜을 세울 때 이 맥락을 반영하세요 — 테스트 상태, 임박 일정, 액션 아이템 등.

{slack_context}
"""

    part0_block = ""
    if slack_context:
        part0_block = f"""
## 파트 0: 오늘/이번주 챙길 일정 (슬랙 기반)

아래 Slack 컨텍스트에서 **날짜가 명시된 임박 이벤트**만 추출하라.
오늘 날짜는 {today}이다.

추출 기준:
- 오늘 날짜 언급 → `[오늘]` 태그
- 내일 날짜 언급 → `[내일]` 태그
- 이번 주 내 날짜 언급 → `[N/N 요일]` 태그 (예: `[4/27 월]`)
- Next Action, 배포일, 입사일, SDK 수령일, QA 일정 등을 우선 스캔
- 슬랙 컨텍스트가 없거나 임박 일정이 없으면 이 파트 전체 생략 (안내 문구 없이)
"""

    prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 바탕으로 세 파트로 나누어 요약해주세요.
{part0_block}
## 파트 1: 어제의 핵심 활동 (5가지)

요구사항:
1. **타이틀(Title)**: 활동의 핵심 내용을 명확하게 요약 (예: "로그인 페이지 UI 구현")
2. **설명(Description)**: 구체적인 작업 내용, 성과, 또는 이슈 (한 문장)
3. **관련 링크(Related Links)**: 해당 활동과 관련된 GitHub PR, Jira 티켓, Confluence, Figma 등 작업 관련 URL을 **반드시 포함**할 것. 리포트 본문의 URL 목록, Claude CLI 히스토리, 웹 브라우징 기록에서 각 활동과 관련된 링크를 적극적으로 매칭하여 포함. 링크가 많으면 여러 개 나열해도 됨.
4. **번호 매기기**: 1번부터 5번까지 중요도 순으로 나열
5. **언어**: 한국어
6. **링크 형식 필수 준수**: 반드시 `[링크 제목](URL)` 형식을 사용할 것. (예: `[GitHub PR #1234](https://...)`)

## 파트 2: 오늘의 플랜

리포트에 "📌 오늘의 할일" 섹션과 "📅 오늘 미팅" 섹션이 있다면, 이를 바탕으로 오늘 실제로 실행할 플랜을 3~5개 제안하라.

### 우선순위 판단 기준 (반드시 적용):
1. 🔴 오늘 집중 그룹 → 최우선. 마감/코멘트 응답 등 이유 명시
2. 🔄어제이어서 태그가 붙은 티켓 → 연속성 유지 관점에서 우선 추천
3. 미팅 전후 시간 활용 → 미팅 시간대를 피한 집중 작업 블록 제안
4. 🟡 이번주 내 그룹 → 여유 시간에 착수 권장
5. ⚪ 백로그 → 시간 남을 때만 언급
6. "N일째" 수치가 큰 티켓은 장기화 → 마무리 가능하면 우선 완료 권장

해당 섹션이 없으면 이 파트는 생략. 생략 시 별도 안내 문구 없이 조용히 생략할 것.

출력 형식 (반드시 준수):

(파트 0: 임박 일정이 있을 경우에만 출력)
**⚠️ 오늘/이번주 챙길 일정**

- [태그] 항목 설명 → 필요한 액션

임박 순 정렬 (오늘 → 내일 → 이번 주). 슬랙 컨텍스트가 없거나 임박 일정이 없으면 이 섹션 전체 생략 (안내 문구 없이).

**📊 어제의 핵심 활동**

1. **[타이틀]**
   [설명]
   - 🔗 [링크 제목](URL)

2. **[타이틀]**
   [설명]
   ...

**📌 오늘의 플랜**

1. **[티켓번호 + 액션 동사]**
   └ [근거 1줄: 왜 지금 해야 하는지]

2. **[티켓번호 + 액션 동사]**
   └ [근거 1줄]

3. **[HH:MM 미팅명]** (N시간)

4. **[티켓번호 + 액션 동사]**
   └ [근거 1줄]

...

주의사항:
- 번호 + **볼드 타이틀** (티켓번호 + 액션 동사) 형식 필수
- 다음 줄에 └ 근거 1줄 (왜 지금 해야 하는지)
- 미팅은 시간과 소요시간만 간결하게 (근거 줄 불필요)
- 단순 티켓 나열 금지. 반드시 "무엇을 할지" 액션 동사 포함 (예: ✗ "로그인 리팩토링" → ✓ "로그인 리팩토링 마무리")
- 미팅이 있으면, 미팅 시간을 기준으로 작업 순서를 배치

리포트 내용:
{md_content}
{slack_block}
요약:"""

    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }

    headers = {
        "Content-Type": "application/json"
    }

    # 예약 실행 시간대(오전 피크)에 503(모델 과부하)이 잦아 재시도 budget을 ~7분으로 확대.
    # 마지막 시도에는 sleep 없이 즉시 종료한다.
    retry_delays = [15, 30, 60, 120, 240]
    total_attempts = len(retry_delays) + 1

    def _call_model(model):
        """단일 모델로 재시도 루프를 돌려 요약 텍스트를 반환. 모두 실패하면 None."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        last_error = None
        for attempt in range(1, total_attempts + 1):
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
                response.raise_for_status()
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                last_error = e
                retryable = status in (429, 500, 503)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                # 503만큼 흔한 일시 장애. HTTPError가 아니므로 별도로 잡아 재시도한다.
                last_error = e
                retryable = True
            except Exception as e:
                last_error = e
                retryable = False

            if retryable and attempt < total_attempts:
                delay = retry_delays[attempt - 1]
                print(f"⚠️ Gemini API({model}) 오류 (시도 {attempt}/{total_attempts}), {delay}초 후 재시도... [{type(last_error).__name__}]", file=sys.stderr)
                time.sleep(delay)
            else:
                break

        print(f"⚠️ Gemini API({model}) 요약 실패: {last_error}", file=sys.stderr)
        return None

    # flash가 과부하(503)일 때를 대비해 pro로 폴백한다. pro는 부하 분산이 달라 통과하는 경우가 잦다.
    models = ("gemini-2.5-flash", "gemini-2.5-pro")
    for i, model in enumerate(models):
        text = _call_model(model)
        if text is not None:
            return text
        if i < len(models) - 1:
            print(f"↩️ {model} 실패 → {models[i + 1]}로 폴백", file=sys.stderr)

    print("⚠️ Gemini API 요약 실패: 모든 모델/재시도 소진", file=sys.stderr)
    return None


def parse_ai_summary_sections(text: str) -> dict:
    """AI 요약 텍스트에서 섹션별로 분리.

    Returns:
        dict with keys: "schedule", "activity", "plan"
        각 값은 해당 섹션 전체 텍스트 (헤더 포함). 없으면 빈 문자열.
    """
    # 전제: 섹션 헤더(⚠️/📊/📌)는 줄 시작에만 등장. 섹션 본문 안에 같은 이모지가 인라인 볼드로 있으면 오분류 가능.
    header_pattern = re.compile(r'(?=\*\*[⚠️📊📌])')
    parts = header_pattern.split(text)

    result = {"schedule": "", "activity": "", "plan": ""}

    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if stripped.startswith("**⚠️"):
            result["schedule"] = stripped
        elif stripped.startswith("**📊"):
            result["activity"] = stripped
        elif stripped.startswith("**📌"):
            result["plan"] = stripped

    return result
