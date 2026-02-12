#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Antigravity (Git) activity fetcher."""

import subprocess
from datetime import timedelta
from pathlib import Path


def fetch_antigravity_activity(target_date):
    """해당 날짜의 Antigravity 활동 추출 (Git 이력 기반)"""
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
