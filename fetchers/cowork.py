#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cowork session log fetcher."""

import os
import glob
import json
import re
from datetime import datetime
from urllib.parse import urlparse

from config import CONFIG


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
        print(f"⚠️ Cowork 로그 조회 실패: {e}")

    raw_messages.sort(key=lambda x: x["timestamp"])

    # 사용자 메시지 기준으로 작업 단위 묶기
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
