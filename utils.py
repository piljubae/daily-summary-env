#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utility functions for daily summary."""

import sys
import requests
from datetime import date, timedelta
from config import CONFIG


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


# ──────────────────────────────────────────────────────────────
# 한국 공휴일 데이터 (대체공휴일 포함)
# ──────────────────────────────────────────────────────────────
_KR_HOLIDAYS: dict[int, set[tuple[int, int]]] = {
    2025: {
        (1, 1),   # 신정
        (1, 28),  # 설날 연휴
        (1, 29),  # 설날
        (1, 30),  # 설날 연휴
        (3, 1),   # 삼일절
        (5, 5),   # 어린이날
        (5, 6),   # 어린이날 대체공휴일
        (6, 6),   # 현충일
        (8, 15),  # 광복절
        (10, 3),  # 개천절
        (10, 5),  # 추석 연휴
        (10, 6),  # 추석
        (10, 7),  # 추석 연휴
        (10, 8),  # 추석 대체공휴일
        (10, 9),  # 한글날
        (12, 25), # 크리스마스
    },
    2026: {
        (1, 1),   # 신정
        (2, 17),  # 설날 연휴
        (2, 18),  # 설날
        (2, 19),  # 설날 연휴
        (3, 1),   # 삼일절
        (3, 2),   # 삼일절 대체공휴일
        (5, 5),   # 어린이날
        (5, 25),  # 부처님오신날
        (6, 6),   # 현충일
        (8, 15),  # 광복절
        (8, 17),  # 광복절 대체공휴일
        (9, 24),  # 추석 연휴
        (9, 25),  # 추석
        (9, 26),  # 추석 연휴
        (10, 3),  # 개천절
        (10, 9),  # 한글날
        (12, 25), # 크리스마스
    },
}


def is_holiday(dt) -> bool:
    """주말 또는 한국 공휴일이면 True를 반환합니다.

    Args:
        dt: datetime 또는 date 객체

    Returns:
        True if the date is a weekend or Korean public holiday.
    """
    d = dt.date() if hasattr(dt, "date") else dt

    # 토요일(5) 또는 일요일(6)
    if d.weekday() >= 5:
        return True

    # 공휴일 데이터 조회
    year_holidays = _KR_HOLIDAYS.get(d.year)
    if year_holidays is None:
        # 해당 연도 데이터 없으면 주말만 체크
        return False

    return (d.month, d.day) in year_holidays
