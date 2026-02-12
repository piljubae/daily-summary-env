#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Antigravity (Git) activity fetcher."""

import os
import glob
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def fetch_antigravity_activity(target_date):
    """해당 날짜의 Antigravity 활동 추출 (Git 이력 기반 + 대화 로그)"""
    start = target_date.replace(hour=0, minute=0, second=0)
    end = start + timedelta(days=1)
    since = start.strftime("%Y-%m-%d 00:00:00")
    until = end.strftime("%Y-%m-%d 23:59:59")
    
    files_modified = set()
    commit_messages = []
    user_queries = []
    work_dirs = [Path.home() / "daily-summary-env"]
    
    # Git 활동 추출
    for work_dir in work_dirs:
        if not work_dir.exists():
            continue
        try:
            # 파일 변경 내역 추출
            result = subprocess.run(
                ["git", "log", f"--since={since}", f"--until={until}", "--name-only", "--pretty=format:"],
                cwd=str(work_dir), capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and ('/' in line or '.' in line):
                        files_modified.add(line)
            
            # 커밋 메시지 추출 (질문/활동 내역)
            msg_result = subprocess.run(
                ["git", "log", f"--since={since}", f"--until={until}", "--pretty=format:%s"],
                cwd=str(work_dir), capture_output=True, text=True, timeout=5
            )
            if msg_result.returncode == 0 and msg_result.stdout:
                for msg in msg_result.stdout.strip().split('\n'):
                    msg = msg.strip()
                    if msg:
                        commit_messages.append(msg)
        except Exception:
            continue
    
    # Antigravity 대화 로그에서 사용자 질문 추출
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if brain_dir.exists():
        try:
            # 해당 날짜의 대화 찾기
            for conv_dir in brain_dir.iterdir():
                if not conv_dir.is_dir():
                    continue
                
                # 대화 디렉토리의 수정 시간 확인
                try:
                    mod_time = datetime.fromtimestamp(conv_dir.stat().st_mtime)
                    if mod_time.date() != target_date.date():
                        continue
                except Exception:
                    continue
                
                # overview.txt에서 사용자 요청 추출
                overview_path = conv_dir / ".system_generated" / "logs" / "overview.txt"
                if overview_path.exists():
                    try:
                        with open(overview_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # "USER Objective:" 섹션 찾기
                            if "USER Objective:" in content:
                                lines = content.split('\n')
                                for i, line in enumerate(lines):
                                    if "USER Objective:" in line and i + 1 < len(lines):
                                        objective = lines[i + 1].strip()
                                        if objective and len(objective) > 5:
                                            user_queries.append(objective)
                                            break
                    except Exception:
                        continue
        except Exception:
            pass
    
    return {
        'files_modified': sorted(list(files_modified))[:20],
        'commit_messages': commit_messages[:10],  # 최대 10개
        'user_queries': user_queries[:10]  # 최대 10개
    }
