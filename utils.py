#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utility functions for daily summary."""

import sys
import requests
from datetime import timedelta
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
