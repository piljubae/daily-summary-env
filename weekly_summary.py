#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 요약 생성기 (Weekly Summary Generator)

월~금 데일리 요약을 집계하고, Jira 티켓을 조회하여
주간 보고서를 마크다운으로 생성합니다.

사용법:
  python weekly_summary.py                    # 지난주 기준
  python weekly_summary.py --week 2026-W09    # 특정 주
  python weekly_summary.py --no-slack         # 슬랙 전송 건너뛰기
  python weekly_summary.py --no-gemini        # Gemini 요약 건너뛰기
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, timedelta

import requests

from config import CONFIG
from fetchers.weekly import fetch_daily_summaries, fetch_jira_tickets
from formatters.weekly_markdown import create_weekly_report, save_weekly_report
from formatters.slack import send_to_slack


def get_last_week_range():
    """지난주 월~금 날짜 범위를 반환합니다.

    Returns:
        tuple: (week_start(월요일), week_end(금요일))
    """
    today = datetime.now()
    # 지난주 월요일 = 이번주 월요일 - 7일
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_friday = last_monday + timedelta(days=4)
    return last_monday, last_friday


def parse_week_arg(week_str):
    """'2026-W09' 형식의 문자열을 월~금 날짜로 변환합니다.

    Args:
        week_str: 'YYYY-WNN' 형식 문자열

    Returns:
        tuple: (week_start(월요일), week_end(금요일))

    Raises:
        ValueError: 형식이 잘못된 경우
    """
    m = re.match(r'^(\d{4})-W(\d{2})$', week_str)
    if not m:
        raise ValueError(f"잘못된 형식: {week_str} (YYYY-WNN 형식 필요)")

    year = int(m.group(1))
    week = int(m.group(2))

    # ISO week → 월요일 날짜 계산
    monday = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
    # strptime %W는 0-indexed이므로 ISO week와 맞추기 위해 fromisocalendar 사용
    monday = datetime.fromisocalendar(year, week, 1)
    friday = monday + timedelta(days=4)

    return monday, friday


def summarize_weekly_with_gemini(md_content, api_key):
    """Gemini API로 주간 요약을 핵심 5항목으로 요약합니다.

    Args:
        md_content: 주간 보고서 마크다운
        api_key: Gemini API 키

    Returns:
        str or None: 요약 텍스트
    """
    if not api_key:
        return None

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        prompt = f"""다음은 한 주간의 활동 요약 리포트입니다. 이 내용을 바탕으로 **5가지 핵심 성과/활동**을 아래 형식에 맞춰 요약해주세요.

요구사항:
1. **타이틀**: 핵심 성과를 한 줄로 요약
2. **설명**: 구체적 내용 (한 문장)
3. 번호 매기기: 1~5번, 중요도순
4. 언어: 한국어

출력 형식:
1. **[타이틀]**
   [설명]

2. **[타이틀]**
   [설명]

리포트 내용:
{md_content}

주간 핵심 요약:"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print(f"⚠️ Gemini API 주간 요약 실패: {e}", file=sys.stderr)
        return None


def _convert_weekly_for_slack(markdown_content):
    """주간 보고서 마크다운을 Slack mrkdwn 형식으로 변환합니다.

    Slack은 마크다운 테이블, blockquote(> )를 지원하지 않으므로
    읽기 좋은 평문+mrkdwn 형식으로 변환합니다.
    """
    lines = markdown_content.splitlines()
    result = []
    table_headers = []
    in_table = False

    for line in lines:
        stripped = line.strip()

        # 테이블 구분선(|------|---...) 제거
        if re.match(r'^\|[-| ]+\|$', stripped):
            continue

        # 테이블 헤더 행 → 컬럼 이름 저장
        if stripped.startswith('|') and stripped.endswith('|') and not in_table:
            cols = [c.strip() for c in stripped.strip('|').split('|')]
            # 빈 헤더가 아닌지 확인
            if any(c for c in cols):
                table_headers = cols
                in_table = True
                continue

        # 테이블 데이터 행 → "• col1: val1 | col2: val2" 형태
        if stripped.startswith('|') and stripped.endswith('|') and in_table:
            cols = [c.strip() for c in stripped.strip('|').split('|')]
            if table_headers and len(cols) == len(table_headers):
                # 첫 번째 컬럼을 키로, 나머지를 값으로
                parts = []
                for h, v in zip(table_headers, cols):
                    if v and v != '-':
                        parts.append(f"{h}: {v}")
                result.append(f"  • {' | '.join(parts)}")
            else:
                result.append(f"  • {' | '.join(cols)}")
            continue

        # 테이블이 끝남
        if in_table and not stripped.startswith('|'):
            in_table = False
            table_headers = []

        # --- 수평선 → 빈 줄
        if stripped == '---':
            result.append('')
            continue

        # > blockquote → 일반 텍스트 (ℹ️는 유지)
        if stripped.startswith('> '):
            result.append(stripped[2:])
            continue

        result.append(line)

    return '\n'.join(result)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="Weekly Summary Generator")
    parser.add_argument("--week", help="요약할 주 (YYYY-WNN 형식, 예: 2026-W09). 생략 시 지난주")
    parser.add_argument("--no-slack", action="store_true", help="슬랙 전송 건너뛰기")
    parser.add_argument("--no-gemini", action="store_true", help="Gemini 요약 건너뛰기")
    args = parser.parse_args()

    # 1. 주 범위 결정
    if args.week:
        try:
            week_start, week_end = parse_week_arg(args.week)
            week_label = args.week
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
    else:
        week_start, week_end = get_last_week_range()
        week_number = week_start.isocalendar()[1]
        week_label = f"{week_start.year}-W{week_number:02d}"

    print(f"🔄 주간 요약 생성 중... [{week_label}] ({week_start.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')})")

    # 2. 데일리 요약 집계
    print("📥 데일리 요약 파일 읽는 중...")
    daily_data = fetch_daily_summaries(week_start, week_end)
    found_days = [d for d in daily_data["days"] if d["found"]]
    print(f"✅ {len(found_days)}일분 데이터 수집 완료 "
          f"(활동 {daily_data['total_active_minutes']}분, "
          f"사이트 {daily_data['total_sites']}개, "
          f"미팅 {daily_data['total_meetings']}건)")

    if not found_days:
        print("⚠️ 해당 주의 데일리 요약 파일이 없습니다.")
        print(f"   {CONFIG['output_dir']} 에 YYYY-MM-DD-daily-summary.md 파일이 있는지 확인하세요.")
        return 1

    # 3. Jira 티켓 조회
    print("📥 Jira 티켓 조회 중...")
    jira_data = fetch_jira_tickets(week_start, week_end)
    if jira_data["available"]:
        print(f"✅ Jira 티켓: 완료 {len(jira_data['completed'])}건, "
              f"진행중 {len(jira_data['in_progress'])}건, "
              f"검토 {len(jira_data['review'])}건, "
              f"미착수 {len(jira_data['todo'])}건")
    else:
        print("ℹ️ Jira 미설정 — 데일리 요약 기반으로 보고서 생성")

    # 4. 마크다운 보고서 생성
    print("📝 주간 보고서 생성 중...")
    markdown_content = create_weekly_report(daily_data, jira_data, week_start, week_end)

    # 5. Gemini AI 요약 (선택)
    gemini_api_key = CONFIG.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
    ai_summary = None

    if gemini_api_key and not args.no_gemini:
        print("🤖 AI 요약 생성 중...")
        ai_summary = summarize_weekly_with_gemini(markdown_content, gemini_api_key)

        if ai_summary:
            print("✅ AI 요약 생성 완료!")
            markdown_content += f"\n\n---\n\n## 🤖 AI 요약 (Gemini)\n\n{ai_summary}\n"
        else:
            print("⚠️ AI 요약 생성 실패")
    elif args.no_gemini:
        print("ℹ️ --no-gemini 옵션 — AI 요약 생략")
    else:
        print("ℹ️ Gemini API Key 미설정 — AI 요약 생략")

    # 6. 파일 저장
    print("💾 파일 저장 중...")
    filepath = save_weekly_report(markdown_content, week_start)
    print(f"✅ 보고서 저장: {filepath}")

    # 7. Slack 전송
    slack_webhook_url = CONFIG.get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL", "")
    if slack_webhook_url and not args.no_slack:
        CONFIG["slack_webhook_url"] = slack_webhook_url

        week_number = week_start.isocalendar()[1]
        slack_header = (
            f"📊 *주간 요약 W{week_number:02d}이 생성되었습니다*\n"
            f"📁 `{filepath}`\n\n"
        )
        slack_body = _convert_weekly_for_slack(markdown_content)
        slack_message = slack_header + slack_body

        print("📤 Slack으로 전송 중...")
        if send_to_slack(slack_message):
            print("✅ Slack 전송 완료!")
        else:
            print("⚠️ Slack 전송 실패")
    elif args.no_slack:
        print("ℹ️ --no-slack 옵션 — 슬랙 전송 생략")
    else:
        print("ℹ️ Slack Webhook 미설정 — 파일만 저장됨")

    return 0


if __name__ == "__main__":
    sys.exit(main())
