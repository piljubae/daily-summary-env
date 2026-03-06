#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown report formatter."""

import os
import sys
import json
import requests
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

from config import CONFIG
from utils import format_seconds
from fetchers import (
    fetch_cowork_sessions,
    fetch_claude_context,
    fetch_firebender_activity,
    fetch_antigravity_activity,
    fetch_today_todos,
    fetch_calendar_events,
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


def create_markdown_report(app_durations, domain_durations, url_details, target_date):
    """5줄 이내 핵심 요약 보고서 생성

    Returns:
        str: 마크다운 형식의 간결한 보고서
    """
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

    # 3~4줄: Cowork 작업 요약 (의도 + 결과 + 참고 리소스)
    cowork_tasks = fetch_cowork_sessions(target_date)
    if cowork_tasks:
        report += f"**🤖 Cowork** ({len(cowork_tasks)}건)\n"
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
        report += "\n"

    # 🤖 Claude 활동 (Local Agent)
    claude_context = fetch_claude_context(target_date)
    if claude_context:
        report += f"**🤖 Claude 활동**\n"
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

    # 🤖 Firebender 활동 (Android Studio)
    firebender_tasks = fetch_firebender_activity(target_date)
    if firebender_tasks:
        report += f"**🤖 Firebender (Android Studio)**\n"
        # 프로젝트별로 그룹화하여 표시
        by_project = defaultdict(list)
        for t in firebender_tasks:
            by_project[t["project"]].append(t["query"])
            
        for project, queries in by_project.items():
            report += f"### 📂 {project}\n"
            for q in queries[:10]: # 프로젝트별 상위 10개만
                report += f"- {q}\n"
            if len(queries) > 10:
                report += f"- ...외 {len(queries) - 10}건\n"
            report += "\n"


    # 🤖 Antigravity 활동 (Self-Improvement)
    antigravity_data = fetch_antigravity_activity(target_date)
    if antigravity_data and (antigravity_data.get('files_modified') or antigravity_data.get('commit_messages') or antigravity_data.get('user_queries')):
         report += f"**🤖 Antigravity 활동 (Self-Improvement)**\n"
         
         # AI 프롬프트 (사용자 질문)
         user_queries = antigravity_data.get('user_queries', [])
         if user_queries:
             report += f"- 💬 **AI 프롬프트** ({len(user_queries)}건)\n"
             for query in user_queries[:5]:  # 최대 5개만 표시
                 report += f"  - {query}\n"
             if len(user_queries) > 5:
                 report += f"  - ...외 {len(user_queries) - 5}건\n"
         
         # 커밋 메시지 (활동 내역)
         commit_messages = antigravity_data.get('commit_messages', [])
         if commit_messages:
             report += f"- 📝 **활동 내역** ({len(commit_messages)}건)\n"
             for msg in commit_messages[:5]:  # 최대 5개만 표시
                 report += f"  - {msg}\n"
             if len(commit_messages) > 5:
                 report += f"  - ...외 {len(commit_messages) - 5}건\n"
         
         # 수정된 파일
         files = antigravity_data.get('files_modified', [])
         if files:
             report += f"- 🛠️ **수정된 파일** ({len(files)}개)\n"
             for f in files[:10]:
                 report += f"  - `{f}`\n"
             if len(files) > 10:
                 report += f"  - ...외 {len(files) - 10}개\n"
         report += "\n"

    # 📌 오늘의 할일 (Jira)
    jira_todos = fetch_today_todos()
    if jira_todos.get("available"):
        total_count = len(jira_todos["in_progress"]) + len(jira_todos["review"]) + len(jira_todos["todo"])
        if total_count > 0:
            report += f"**📌 오늘의 할일** ({total_count}건)\n"
            for ticket in jira_todos["in_progress"]:
                report += f"- 🔵 [{ticket['key']}] {ticket['summary']} ({ticket['status']})\n"
            for ticket in jira_todos["review"]:
                report += f"- 🟡 [{ticket['key']}] {ticket['summary']} ({ticket['status']})\n"
            for ticket in jira_todos["todo"]:
                report += f"- ⚪ [{ticket['key']}] {ticket['summary']} ({ticket['status']})\n"
            report += "\n"

    # 📅 오늘 미팅
    calendar_events = fetch_calendar_events(target_date)
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


def summarize_with_gemini(md_content, api_key):
    """Gemini API를 사용하여 일일 요약을 5가지 핵심 포인트로 요약"""
    if not api_key:
        return None
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 바탕으로 두 파트로 나누어 요약해주세요.

## 파트 1: 어제의 핵심 활동 (5가지)

요구사항:
1. **타이틀(Title)**: 활동의 핵심 내용을 명확하게 요약 (예: "로그인 페이지 UI 구현")
2. **설명(Description)**: 구체적인 작업 내용, 성과, 또는 이슈 (한 문장)
3. **관련 링크(Related Links)**: 해당 활동과 직접 관련된 URL (없으면 생략)
4. **번호 매기기**: 1번부터 5번까지 중요도 순으로 나열
5. **언어**: 한국어
6. **링크 형식 필수 준수**: 반드시 `[링크 제목](URL)` 형식을 사용할 것. (예: `[GitHub PR](https://...)`)

## 파트 2: 오늘의 할일 플랜

리포트에 "📌 오늘의 할일" 섹션과 "📅 오늘 미팅" 섹션이 있다면, 이를 바탕으로 오늘의 우선순위 플랜을 3~5개 항목으로 제안해주세요.
- 어제의 활동 맥락과 오늘의 Jira 티켓, 미팅 일정을 종합적으로 고려
- 미팅 시간을 감안한 현실적인 작업 우선순위 제안
- 해당 섹션이 없으면 이 파트는 생략

출력 형식 (반드시 준수):

**📊 어제의 핵심 활동**

1. **[타이틀]**
   [설명]
   - 🔗 [링크 제목](URL)

2. **[타이틀]**
   [설명]
   ...

**📌 오늘의 플랜**

1. [우선순위 항목 + 간단한 이유]
2. [우선순위 항목 + 간단한 이유]
...

리포트 내용:
{md_content}

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
        
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']
        
    except Exception as e:
        print(f"⚠️ Gemini API 요약 실패: {e}", file=sys.stderr)
        return None
