#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ActivityWatch 일일 요약 생성기
매일 어제의 활동 데이터를 분석하여 마크다운 요약 파일을 생성합니다.

라이선스: MPL-2.0
"""

import json
import glob
import os
import re
import argparse
import requests
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

# ============================================================================
# 설정 섹션 (커스터마이징 가능)
# ============================================================================

def load_env():
    """로컬 .env 파일이 있으면 환경변수로 로드 (GitHub에는 올라가지 않음)"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        loaded_count = 0
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # 따옴표 제거 (예: "value" -> value)
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value
                    loaded_count += 1
        if loaded_count > 0:
            print(f"✅ .env 파일에서 {loaded_count}개의 설정을 로드했습니다.")
        return True
    return False

# 스크립트 실행 시 즉시 .env 로드
load_env()

CONFIG = {
    # ActivityWatch API 연결 정보
    "api_host": "127.0.0.1",
    "api_port": 5600,

    # 출력 디렉토리 (기본값: 홈 디렉토리/daily-summaries/)
    "output_dir": str(Path.home() / "daily-summaries"),

    # 최소 표시 기간 (초 단위, 이보다 작은 활동은 제외)
    "min_duration_seconds": 10,

    # 상위 표시 개수
    "top_apps_count": 15,
    "top_urls_count": 10,

    # 생산성 시간대 정의 (시간 범위, 24시간 형식)
    "productive_hours": [(9, 12), (14, 18)],  # 9-12시, 14-18시

    # Cowork 세션 로그 디렉토리
    # macOS: ~/Library/Application Support/Claude/projects/
    # Linux: ~/.config/Claude/projects/
    # 빈 문자열이면 Cowork 요약 생략
    "cowork_log_dir": str(Path.home() / "Library" / "Application Support" / "Claude" / "projects"),

    # Slack Incoming Webhook URL
    # Slack 앱 → Incoming Webhooks 에서 발급
    # 빈 문자열이면 Slack 전송 생략 (마크다운 파일만 생성)
    "slack_webhook_url": "",  # 환경변수 SLACK_WEBHOOK_URL 또는 직접 입력
    
    # Gemini API Key (AI 요약용)
    # 빈 문자열이면 AI 요약 생략
    "gemini_api_key": "",  # 환경변수 GEMINI_API_KEY 또는 직접 입력
}

# ============================================================================
# 유틸리티 함수
# ============================================================================

def format_seconds(seconds):
    """초를 시간:분 형식으로 변환"""
    if seconds < 60:
        return f"{int(seconds)}초"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)

    if hours > 0:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"


def get_api_url(endpoint):
    """ActivityWatch API URL 생성"""
    return f"http://{CONFIG['api_host']}:{CONFIG['api_port']}/api/0/{endpoint}"


def get_bucket_id(bucket_type):
    """지정된 타입의 첫 번째 버킷 ID 반환"""
    try:
        # 버킷 목록 조회 (trailing slash 필수)
        url = get_api_url("buckets/")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        buckets = response.json()
        for bucket_id, bucket in buckets.items():
            if bucket.get("type") == bucket_type:
                return bucket_id
                
    except Exception as e:
        print(f"⚠️ 버킷 조회 실패 ({bucket_type}): {e}", file=sys.stderr)
    
    return None


def get_bucket_ids(bucket_type):
    """지정된 타입의 모든 버킷 ID 리스트 반환"""
    try:
        url = get_api_url("buckets/")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        buckets = response.json()
        matching_buckets = []
        for bucket_id, bucket in buckets.items():
            if bucket.get("type") == bucket_type:
                matching_buckets.append(bucket_id)
        
        return matching_buckets
                
    except Exception as e:
        print(f"⚠️ 버킷 조회 실패 ({bucket_type}): {e}", file=sys.stderr)
    
    return []


def get_daterange(target_date):
    """지정된 날짜의 시작과 끝 시간을 ISO 형식으로 반환"""
    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    return start.isoformat(), end.isoformat()



def fetch_window_events(start_iso, end_iso):
    """윈도우 활동 데이터 조회

    Returns:
        dict: {'앱이름': 총_시간_초} 형식의 딕셔너리
    """

    bucket_id = get_bucket_id("currentwindow")
    if not bucket_id:
        print("⚠️ 윈도우 활동 버킷을 찾을 수 없습니다.", file=sys.stderr)
        return {}

    try:
        url = get_api_url(f"buckets/{bucket_id}/events")
        params = {
            "start": start_iso,
            "end": end_iso,
            "limit": -1,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        events = response.json()
        app_durations = defaultdict(float)

        for event in events:
            if "data" in event and "app" in event["data"]:
                app_name = event["data"]["app"]
                duration = event.get("duration", 0)

                if duration > CONFIG["min_duration_seconds"]:
                    app_durations[app_name] += duration

        return dict(app_durations)

    except Exception as e:
        print(f"⚠️ 윈도우 활동 데이터 조회 실패: {e}", file=sys.stderr)
        return {}


def fetch_web_events(start_iso, end_iso):
    """웹 브라우징 활동 데이터 조회

    Returns:
        dict: {'도메인': 총_시간_초} 형식의 딕셔너리
    """

    bucket_ids = get_bucket_ids("web.tab.current")
    if not bucket_ids:
        print("⚠️ 웹 활동 버킷을 찾을 수 없습니다.", file=sys.stderr)
        return {}, []

    domain_durations = defaultdict(float)
    url_details = []

    # 모든 웹 버킷에서 데이터 수집
    for bucket_id in bucket_ids:
        try:
            url = get_api_url(f"buckets/{bucket_id}/events")
            params = {
                "start": start_iso,
                "end": end_iso,
                "limit": -1,
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            events = response.json()

            for event in events:
                if "data" in event:
                    data = event["data"]
                    event_url = data.get("url", "")
                    duration = event.get("duration", 0)

                    if duration > CONFIG["min_duration_seconds"] and event_url:
                        try:
                            domain = urlparse(event_url).netloc or event_url
                            domain_durations[domain] += duration
                            url_details.append({
                                "url": event_url,
                                "domain": domain,
                                "duration": duration,
                                "title": data.get("title", "")
                            })
                        except Exception:
                            pass

        except Exception as e:
            print(f"⚠️ 웹 활동 데이터 조회 실패 (버킷: {bucket_id}): {e}", file=sys.stderr)
            continue

    return dict(domain_durations), url_details


def fetch_cowork_sessions(target_date):
    """Cowork 세션 로그에서 해당 날짜의 대화를 작업 단위로 추출

    사용자 메시지 (작업 의도)와 어시스턴트 응답 (결과물, 참고 리소스)을
    함께 읽어서 "무엇을 하려 했고, 무엇을 참고했는지" 단위로 묶습니다.

    Returns:
        list: [{"intent": str, "result": str, "urls": list}] 형식
    """
    log_dir = CONFIG.get("cowork_log_dir", "")
    if not log_dir or not os.path.isdir(log_dir):
        return []

    raw_messages = []  # 시간순 전체 메시지 수집

    try:
        jsonl_files = glob.glob(os.path.join(log_dir, "**", "*.jsonl"), recursive=True)

        for filepath in jsonl_files:
            mod_time = datetime.fromtimestamp(os.path.getmtime(filepath)).date()
            # Original logic for processing jsonl files
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            entry_date = ts.date()
                        except (ValueError, TypeError):
                            continue
                        if entry_date != target_date.date():
                            continue

                        if entry.get("isMeta"):
                            continue

                        msg = entry.get("message", {})
                        role = msg.get("role", "")
                        if role not in ("user", "assistant"):
                            continue

                        content = msg.get("content", "")
                        if isinstance(content, list):
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                            content = " ".join(text_parts)

                        if not content or len(content.strip()) < 2:
                            continue

                        raw_messages.append({
                            "timestamp": ts.strftime("%H:%M"),
                            "role": role,
                            "content": content.strip(),
                        })

            except (IOError, PermissionError):
                continue

    except Exception as e:
        print(f"⚠️ Cowork 로그 조회 실패: {e}", file=sys.stderr)

    raw_messages.sort(key=lambda x: x["timestamp"])

    # 사용자 메시지 기준으로 작업 단위 묶기
    # 각 사용자 메시지 = 작업 의도, 이후 어시스턴트 응답에서 결과와 URL 추출
    tasks = []
    i = 0
    while i < len(raw_messages):
        if raw_messages[i]["role"] == "user":
            intent = raw_messages[i]["content"]
            if len(intent) > 100:
                intent = intent[:100] + "..."

            # 뒤따르는 어시스턴트 응답 수집
            result_text = ""
            urls = []
            j = i + 1
            while j < len(raw_messages) and raw_messages[j]["role"] == "assistant":
                resp = raw_messages[j]["content"]
                # 응답에서 URL 추출
                found_urls = re.findall(r'https?://[^\s\)\]>"]+', resp)
                for u in found_urls:
                    domain = urlparse(u).netloc
                    if domain and domain not in [urlparse(x).netloc for x in urls]:
                        urls.append(u)
                # 첫 응답의 첫 문장을 결과 요약으로 사용
                if not result_text:
                    first_line = resp.split("\n")[0].strip()
                    # 마크다운 기호 제거
                    first_line = re.sub(r'^[#*>\-\s]+', '', first_line)
                    if len(first_line) > 80:
                        first_line = first_line[:80] + "..."
                    result_text = first_line
                j += 1

            tasks.append({
                "intent": intent,
                "result": result_text,
                "urls": urls[:3],  # 도메인 기준 상위 3개
            })
            i = j
        else:
            i += 1

    # 같은 의도의 작업을 묶기 (연속된 짧은 후속 요청 통합)
    merged_tasks = []
    for task in tasks:
        # 너무 짧은 메시지(2글자 이하)는 이전 작업의 후속으로 간주
        if merged_tasks and len(task["intent"]) <= 10 and not task["urls"]:
            merged_tasks[-1]["urls"].extend(task["urls"])
        else:
            merged_tasks.append(task)

    return merged_tasks


def fetch_claude_context(target_date):
    """지정된 날짜의 Claude 세션 활동(의도 및 코드 변경)을 추출"""
    sessions_dir = Path.home() / "Library/Application Support/Claude/local-agent-mode-sessions"
    context_data = []

    if not sessions_dir.exists():
        return context_data

    # Find relevant sessions
    for json_path in sessions_dir.rglob("*.json"):
        try:
            if "todos" in str(json_path):
                 continue

            with open(json_path, 'r', encoding='utf-8') as f:
                try:
                    metadata = json.load(f)
                except json.JSONDecodeError:
                    continue

            last_activity = metadata.get('lastActivityAt')
            if not last_activity:
                continue

            activity_date = datetime.fromtimestamp(last_activity / 1000).date()
            if activity_date != target_date.date():
                continue

            session_id = metadata.get('sessionId')
            title = metadata.get('title', 'Untitled Session')
            audit_path = json_path.parent / json_path.stem / "audit.jsonl"
            
            if not audit_path.exists():
                continue

            # Stats trackers
            start_time = None
            end_time = None
            interaction_count = 0
            
            # Goal & Actions
            initial_goal = "No user input found"
            files_created = set()
            files_modified = set()
            full_messages = []  # For detailed reporting
            
            # Helper to extract file path from tool input
            def get_path(tool_input):
                 return tool_input.get('file_path') or tool_input.get('TargetFile') or tool_input.get('path') or tool_input.get('AbsolutePath')

            with open(audit_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts_str = entry.get('timestamp') # Assuming timestamp exists in audit logs or we use line order
                        
                        # Fallback for timestamp if not in audit log root, check message? 
                        # Actually audit logs usually have top-level timestamp or we just estimate from events.
                        # For simplicity, let's just use the order for first/last if timestamp isn't easy.
                        # If 'createdAt' in metadata is start, we might skip start_time here.
                        # But let's try to find timestamps in entry if available, else ignored for now.
                        
                        entry_type = entry.get('type')
                        
                        if entry_type == "user":
                            interaction_count += 1
                            msg = entry.get('message', {})
                            content = msg.get('content', '')
                            text_content = ""
                            
                            if isinstance(content, str):
                                text_content = content
                            elif isinstance(content, list):
                                for item in content:
                                    if item.get('type') == 'text':
                                        text_content = item.get('text', '')
                                        break
                            
                            if text_content:
                                if interaction_count == 1:
                                    initial_goal = text_content[:200] + "..." if len(text_content) > 200 else text_content
                                # Collect all messages for detailed list
                                full_messages.append(text_content.strip())

                        if entry_type == "assistant":
                            msg = entry.get('message', {})
                            content = msg.get('content', [])
                            if isinstance(content, list):
                                for item in content:
                                    if item.get('type') == 'tool_use':
                                        tool_name = item.get('name')
                                        tool_input = item.get('input', {})
                                        
                                        fpath = get_path(tool_input)
                                        if fpath:
                                            fname = Path(fpath).name
                                            if tool_name in ['write_to_file']:
                                                files_created.add(fname)
                                            elif tool_name in ['Edit', 'Replace', 'replace_file_content', 'multi_replace_file_content']:
                                                files_modified.add(fname)

                    except json.JSONDecodeError:
                        continue
            
            # Duration calculation (approximate using metadata if audit timestamps missing)
            # metadata has 'createdAt' and 'lastActivityAt'
            created_at = metadata.get('createdAt', 0)
            last_activity_at = metadata.get('lastActivityAt', 0)
            duration_minutes = 0
            if created_at and last_activity_at:
                duration_minutes = int((last_activity_at - created_at) / 1000 / 60)

            context_data.append({
                'session_id': session_id,
                'title': title,
                'duration_min': duration_minutes,
                'interaction_count': interaction_count,
                'goal': initial_goal,
                'files_created': sorted(list(files_created)),
                'files_modified': sorted(list(files_modified)),
                'full_messages': full_messages  # Add full conversation list
            })

        except Exception:
            continue

    return context_data


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
        return f"개발 작업에 {duration}을 집중했습니다."
    elif "slack" in app_name.lower() or "teams" in app_name.lower():
        return f"커뮤니케이션 도구에 {duration}을 사용했습니다."
    else:
        return f"{app_name}에 가장 많은 시간({duration})을 사용했습니다."


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


def send_to_slack(markdown_content):
    """Slack Incoming Webhook으로 보고서 전송

    마크다운을 Slack mrkdwn 형식으로 변환하여 전송합니다.
    """
    webhook_url = CONFIG.get("slack_webhook_url", "")
    if not webhook_url:
        return False

    # 마크다운 → Slack mrkdwn 변환
    slack_text = markdown_content
    
    # [텍스트](URL) -> <URL|텍스트> 변환 (Slack 형식)
    slack_text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<\2|\1>', slack_text)
    
    slack_text = re.sub(r'^# (.+)$', r'*\1*', slack_text, flags=re.MULTILINE)       # h1 → bold
    slack_text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', slack_text)                       # **bold** → *bold*
    slack_text = re.sub(r'^\- ', '• ', slack_text, flags=re.MULTILINE)               # - → •
    slack_text = re.sub(r'^  📎', '    📎', slack_text, flags=re.MULTILINE)          # 들여쓰기 보정

    payload = {
        "text": slack_text,
        "unfurl_links": False,
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ Slack 전송 실패: {e}", file=sys.stderr)
        return False


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
        import requests
        import json
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 읽고 **5가지 핵심 활동**으로 요약해주세요.

요구사항:
1. 각 항목은 한 문장으로 간결하게 작성
2. 원본 리포트에 있는 중요한 링크는 반드시 포함 (마크다운 링크 형식 유지)
3. 시간 정보가 있으면 포함
4. 번호 매기기 (1. 2. 3. 4. 5.)
5. 한국어로 작성

리포트 내용:
{md_content}

5가지 핵심 활동:"""

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
def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="ActivityWatch Daily Summary Generator")
    parser.add_argument("date", nargs="?", help="요약할 날짜 (YYYYMMDD 형식). 생략 시 어제 또는 --today 옵션 사용")
    parser.add_argument("--today", action="store_true", help="오늘 날짜의 요약 생성 (기본값: 어제)")
    args = parser.parse_args()

    # 날짜 설정
    target_date = None

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d")
            date_label = f"{args.date}"
        except ValueError:
            print("❌ 날짜 형식이 올바르지 않습니다. YYYYMMDD 형식으로 입력해주세요. (예: 20260210)", file=sys.stderr)
            return 1
    elif args.today:
        target_date = datetime.now()
        date_label = "오늘"
    else:
        target_date = datetime.now() - timedelta(days=1)
        date_label = "어제"

    start_iso, end_iso = get_daterange(target_date)

    print(f"🔄 ActivityWatch {date_label}({target_date.strftime('%Y-%m-%d')}) 요약 생성 중...")
    print(f"📍 API 연결: {CONFIG['api_host']}:{CONFIG['api_port']}")

    # 데이터 조회
    print("📥 활동 데이터 조회 중...")
    app_durations = fetch_window_events(start_iso, end_iso)
    domain_durations, url_details = fetch_web_events(start_iso, end_iso)

    if not app_durations and not domain_durations:
        print("⚠️ 조회된 활동 데이터가 없습니다.")
        print("   ActivityWatch가 실행 중인지 확인하세요.")
        return 1

    cowork_count = len(fetch_cowork_sessions(target_date))
    print(f"✅ 앱 활동 {len(app_durations)}개, 웹 활동 {len(domain_durations)}개, Cowork 요청 {cowork_count}건 조회됨")

    # 보고서 생성
    print("📝 마크다운 보고서 생성 중...")
    markdown_content = create_markdown_report(app_durations, domain_durations, url_details, target_date)

    # 파일 저장
    print("💾 파일 저장 중...")
    filepath = save_report(markdown_content, target_date)
    print(f"✅ 보고서 저장: {filepath}")

    # AI 요약 생성 및 추가
    gemini_api_key = CONFIG.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
    ai_summary = None
    
    if gemini_api_key:
        print("🤖 AI 요약 생성 중...")
        ai_summary = summarize_with_gemini(markdown_content, gemini_api_key)
        
        if ai_summary:
            print("✅ AI 요약 생성 완료!")
            # MD 파일에 AI 요약 추가
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(f"\n\n---\n\n## 🤖 AI 요약 (Gemini)\n\n{ai_summary}\n")
            print("✅ AI 요약을 MD 파일에 추가했습니다")
        else:
            print("⚠️ AI 요약 생성 실패")
    else:
        print("ℹ️ Gemini API Key 미설정 — AI 요약 생략")

    # Slack 전송
    slack_webhook_url = CONFIG.get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL", "")
    if slack_webhook_url:
        # CONFIG["slack_webhook_url"]이 함수 내부에서 사용되므로 업데이트
        CONFIG["slack_webhook_url"] = slack_webhook_url
        
        if ai_summary:
            # AI 요약만 Slack으로 전송
            print("📤 AI 요약만 Slack으로 전송 중...")
            summary_message = f"*📊 {target_date.strftime('%m/%d')} 일일 요약 (AI 생성)*\n\n{ai_summary}\n\n---\n*상세 리포트*: `{filepath}`"
            if send_to_slack(summary_message):
                print("✅ Slack 전송 완료!")
            else:
                print("⚠️ Slack 전송 실패")
        else:
            # AI 요약이 없으면 간단한 알림만 전송
            print("📤 요약 알림을 Slack으로 전송 중...")
            
            if gemini_api_key:
                # 키는 있는데 요약 생성에 실패한 경우
                reason = "Gemini API 호출 중 오류가 발생했습니다. (로그 확인 필요)"
            else:
                # 키 자체가 없는 경우
                reason = "Gemini API 키가 설정되지 않아 AI 요약은 생략되었습니다."
                
            alert_message = f"✅ *{target_date.strftime('%m/%d')}* 일일 리포트가 생성되었습니다.\n\n*위치*: `{filepath}`\n({reason})"
            if send_to_slack(alert_message):
                print("✅ Slack 알림 전송 완료!")
            else:
                print("⚠️ Slack 전송 실패")
    else:
        print("ℹ️ Slack Webhook 미설정 — 파일만 저장됨")

    return 0


if __name__ == "__main__":
    sys.exit(main())

def fetch_antigravity_activity(target_date):
    """해당 날짜의 Antigravity 활동 추출 (Git 이력 기반)"""
    import subprocess
    
    start = target_date.replace(hour=0, minute=0, second=0)
    end = start + timedelta(days=1)
    since = start.strftime("%Y-%m-%d 00:00:00")
    until = end.strftime("%Y-%m-%d 23:59:59")
    
    files_modified = set()
    work_dirs = [Path.home() / "daily-summary-env"]
    
    for work_dir in work_dirs:
        if not work_dir.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "log", f"--since={since}", f"--until={until}", "--name-only", "--pretty=format:"],
                cwd=str(work_dir), capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and ('/' in line or '.' in line):
                        files_modified.add(line)
        except Exception:
            continue
    
    return {'files_modified': sorted(list(files_modified))[:20]}


