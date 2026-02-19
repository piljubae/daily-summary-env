#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ActivityWatch 일일 요약 생성기
매일 어제의 활동 데이터를 분석하여 마크다운 요약 파일을 생성합니다.

라이선스: MPL-2.0
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Import configuration and utilities
from config import CONFIG
from utils import get_daterange, is_holiday

# Import data fetchers
from fetchers import fetch_all

# Import formatters
from formatters import (
    create_markdown_report,
    save_report,
    summarize_with_gemini,
    send_to_slack,
)


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

    # 주말 / 한국 공휴일 체크 (날짜를 직접 지정한 경우에는 건너뜀)
    if not args.date and is_holiday(target_date):
        weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
        day_name = weekday_names[target_date.weekday()]
        print(f"🗓️  {target_date.strftime('%Y-%m-%d')}({day_name})은 주말 또는 공휴일입니다 — 요약을 생략합니다.")
        return 0

    start_iso, end_iso = get_daterange(target_date)

    print(f"🔄 ActivityWatch {date_label}({target_date.strftime('%Y-%m-%d')}) 요약 생성 중...")
    print(f"📍 API 연결: {CONFIG['api_host']}:{CONFIG['api_port']}")

    # 데이터 조회 — 모든 소스를 fetch_all() 한 번으로 수집
    print("📥 활동 데이터 조회 중...")
    data = fetch_all(target_date, start_iso, end_iso)

    if not data.app_durations and not data.domain_durations:
        print("⚠️ 조회된 활동 데이터가 없습니다.")
        print("   ActivityWatch가 실행 중인지 확인하세요.")
        return 1

    print(f"✅ 앱 {len(data.app_durations)}개, 웹 {len(data.domain_durations)}개, "
          f"Cowork {len(data.cowork_sessions)}건, Claude {len(data.claude_context)}건, "
          f"Firebender {len(data.firebender_tasks)}건, "
          f"Antigravity {len(data.antigravity_data.get('user_queries', []))}건, "
          f"캘린더 {len(data.calendar_events)}건 조회됨")

    # 보고서 생성
    print("📝 마크다운 보고서 생성 중...")
    markdown_content = create_markdown_report(data, target_date)


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
