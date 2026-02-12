#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Firebender (Android Studio) activity fetcher."""

import re
from datetime import datetime
from pathlib import Path


def fetch_firebender_activity(target_date):
    """지정된 날짜의 Firebender (Android Studio) 활동 추출"""
    firebender_dir = Path.home() / ".firebender" / "message-dumps"
    activity_data = []

    if not firebender_dir.exists():
        return activity_data

    # 프로젝트별로 탐색
    for project_dir in firebender_dir.iterdir():
        if not project_dir.is_dir():
            continue
            
        latest_dir = project_dir / "latest"
        if not latest_dir.exists():
            continue
            
        project_name = project_dir.name
        
        for md_file in latest_dir.glob("*.md"):
            try:
                # 파일 수정 시간으로 해당 날짜 활동인지 확인
                mod_time = datetime.fromtimestamp(md_file.stat().st_mtime).date()
                if mod_time != target_date.date():
                    continue
                
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # <user_query> 태그 내용 추출
                queries = re.findall(r'<user_query>(.*?)</user_query>', content, re.DOTALL)
                for query in queries:
                    query_text = query.strip()
                    if query_text:
                        # 너무 긴 쿼리는 생략하거나 자르기
                        display_query = query_text[:150] + "..." if len(query_text) > 150 else query_text
                        activity_data.append({
                            "project": project_name,
                            "query": display_query
                        })
            except Exception:
                continue
                
    return activity_data
