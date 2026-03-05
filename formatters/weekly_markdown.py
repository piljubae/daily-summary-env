#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 요약 마크다운 보고서 생성.

W09 샘플(~/daily-summaries/2026-W09-weekly-summary.md)과 동일한 구조를 생성합니다.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import CONFIG


def create_weekly_report(
    daily_data,
    jira_data,
    week_start,
    week_end,
    author="배필주",
    team="프로덕트앱개발",
):
    """주간 요약 마크다운 보고서를 생성합니다.

    Args:
        daily_data: fetch_daily_summaries() 반환값
        jira_data: fetch_jira_tickets() 반환값
        week_start: 주 시작일 (datetime, 월요일)
        week_end: 주 종료일 (datetime, 금요일)
        author: 작성자 이름
        team: 팀명

    Returns:
        str: 마크다운 형식의 주간 보고서
    """
    year = week_start.year
    week_number = week_start.isocalendar()[1]
    start_str = week_start.strftime("%m/%d")
    end_str = week_end.strftime("%m/%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_weekday = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]

    report = f"# 주간 요약 — {year}년 W{week_number:02d} ({start_str} ~ {end_str})\n\n"
    report += f"> 작성일: {today_str} ({today_weekday})\n"
    report += f"> 작성자: {author} ({team})\n\n"
    report += "---\n\n"

    # ── 📊 지난주 작업 현황 ──────────────────────────────
    report += "## 📊 지난주 작업 현황\n\n"

    if jira_data.get("available"):
        # ✅ 완료
        report += "### ✅ 완료\n\n"
        if jira_data["completed"]:
            report += "| 티켓 | 작업 내용 | 비고 |\n"
            report += "|------|----------|------|\n"
            for t in jira_data["completed"]:
                report += f"| {t['key']} | {t['summary']} | {t['status']} |\n"
        else:
            report += "- (완료된 티켓 없음)\n"
        report += "\n"

        # 🔄 진행 중
        report += "### 🔄 진행 중\n\n"
        if jira_data["in_progress"]:
            report += "| 티켓 | 작업 내용 | 상태 |\n"
            report += "|------|----------|------|\n"
            for t in jira_data["in_progress"]:
                report += f"| {t['key']} | {t['summary']} | {t['status']} |\n"
        else:
            report += "- (진행 중인 티켓 없음)\n"
        report += "\n"

        # 🔍 검토 (코드리뷰)
        report += "### 🔍 검토 (코드리뷰)\n\n"
        if jira_data["review"]:
            report += "| 티켓 | 작업 내용 | 상태 |\n"
            report += "|------|----------|------|\n"
            for t in jira_data["review"]:
                report += f"| {t['key']} | {t['summary']} | {t['status']} |\n"
        else:
            report += "- (검토 중인 티켓 없음)\n"
        report += "\n"

        # ⏸️ 미착수
        report += "### ⏸️ 미착수 / 대기\n\n"
        if jira_data["todo"]:
            report += "| 티켓 | 작업 내용 | 비고 |\n"
            report += "|------|----------|------|\n"
            for t in jira_data["todo"]:
                report += f"| {t['key']} | {t['summary']} | {t['status']} |\n"
        else:
            report += "- (미착수 티켓 없음)\n"
        report += "\n"
    else:
        # Jira 미설정 → 데일리 Gemini 요약으로 대체
        report += "> ℹ️ Jira 미설정 — 데일리 AI 요약 기반으로 작업 현황을 표시합니다.\n\n"
        gemini_items = daily_data.get("all_gemini_items", [])
        if gemini_items:
            for i, item in enumerate(gemini_items, 1):
                report += f"{i}. **{item}**\n"
        else:
            report += "- (데일리 AI 요약 데이터 없음)\n"
        report += "\n"

    report += "---\n\n"

    # ── 📈 주간 활동 요약 ──────────────────────────────
    report += "## 📈 주간 활동 요약\n\n"

    total_minutes = daily_data["total_active_minutes"]
    hours = total_minutes // 60
    mins = total_minutes % 60
    report += f"- **총 활동 시간**: 약 {hours}시간 {mins}분 ({len([d for d in daily_data['days'] if d['found']])}일간)\n"
    report += f"- **방문 사이트**: 총 {daily_data['total_sites']}개 도메인\n"
    report += f"- **미팅/일정**: 총 {daily_data['total_meetings']}건\n\n"

    # 일별 요약
    report += "### 일별 요약\n\n"
    report += "| 날짜 | 요일 | 활동 시간 | 사이트 | 미팅 |\n"
    report += "|------|------|----------|--------|------|\n"
    for day in daily_data["days"]:
        if day["found"]:
            h = day["active_minutes"] // 60
            m = day["active_minutes"] % 60
            time_str = f"{h}시간 {m}분" if h > 0 else f"{m}분"
            report += f"| {day['date']} | {day['weekday']} | {time_str} | {day['sites']}개 | {day['meetings']}건 |\n"
        else:
            report += f"| {day['date']} | {day['weekday']} | - | - | - |\n"
    report += "\n"

    report += "---\n\n"

    # ── 🎯 이번 주 할일 제안 ──────────────────────────────
    next_week_start = week_end + timedelta(days=3)  # 다음주 월요일
    next_week_end = next_week_start + timedelta(days=4)
    next_wn = next_week_start.isocalendar()[1]
    report += f"## 🎯 이번 주 할일 제안 (W{next_wn:02d}: {next_week_start.strftime('%m/%d')} ~ {next_week_end.strftime('%m/%d')})\n\n"

    if jira_data.get("available") and (jira_data["in_progress"] or jira_data["review"] or jira_data["todo"]):
        # 🔴 높은 우선순위: 진행 중 + 검토 중 티켓
        report += "### 🔴 높은 우선순위\n\n"
        priority_num = 1
        for t in jira_data["in_progress"]:
            report += f"{priority_num}. **{t['key']} {t['summary']}**\n"
            report += f"   - 현재 상태: {t['status']}\n\n"
            priority_num += 1
        for t in jira_data["review"]:
            report += f"{priority_num}. **{t['key']} {t['summary']}**\n"
            report += f"   - 현재 상태: {t['status']} (코드리뷰)\n\n"
            priority_num += 1

        # 🟡 중간 우선순위: 미착수 티켓 앞쪽
        if jira_data["todo"]:
            report += "### 🟡 중간 우선순위\n\n"
            for t in jira_data["todo"][:3]:
                report += f"{priority_num}. **{t['key']} {t['summary']}**\n"
                report += f"   - 현재 상태: {t['status']}\n\n"
                priority_num += 1

            # 🟢 낮은 우선순위: 나머지 미착수 티켓
            remaining = jira_data["todo"][3:]
            if remaining:
                report += "### 🟢 낮은 우선순위\n\n"
                for t in remaining:
                    report += f"{priority_num}. **{t['key']} {t['summary']}**\n"
                    report += f"   - 현재 상태: {t['status']}\n\n"
                    priority_num += 1
    else:
        report += "> ℹ️ Jira 미설정 — 데일리 요약 기반으로 할일을 제안합니다.\n\n"
        gemini_items = daily_data.get("all_gemini_items", [])
        if gemini_items:
            # 마지막 날의 Gemini 항목을 기반으로 다음 주 제안
            report += "### 🔴 진행 필요\n\n"
            seen = set()
            num = 1
            for item in gemini_items:
                if item not in seen:
                    seen.add(item)
                    report += f"{num}. **{item}**\n"
                    num += 1
                    if num > 7:
                        break
            report += "\n"
        else:
            report += "- (제안할 항목 없음)\n\n"

    report += "---\n\n"

    # ── 📝 메모 ──────────────────────────────────────────
    report += "## 📝 메모\n\n"
    report += "- (메모를 추가하세요)\n"

    return report


def save_weekly_report(markdown_content, week_start):
    """주간 보고서를 파일로 저장합니다.

    Args:
        markdown_content: 마크다운 내용
        week_start: 주 시작일 (datetime)

    Returns:
        Path: 저장된 파일 경로
    """
    output_dir = Path(CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    year = week_start.year
    week_number = week_start.isocalendar()[1]
    filename = f"{year}-W{week_number:02d}-weekly-summary.md"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return filepath
