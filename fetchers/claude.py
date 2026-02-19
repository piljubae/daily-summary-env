#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude session log fetcher."""

import json
from datetime import datetime
from pathlib import Path


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


def fetch_claude_cli_history(target_date):
    """지정된 날짜의 Claude CLI 명령어 실행 이력을 추출"""
    history_path = Path.home() / ".claude/history.jsonl"
    cli_history = []

    if not history_path.exists():
        return cli_history

    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = entry.get('timestamp')
                    if not timestamp:
                        continue

                    # 타임스탬프가 밀리초 단위일 수 있음
                    entry_date = datetime.fromtimestamp(timestamp / 1000)
                    if entry_date.date() != target_date.date():
                        continue
                    
                    display_cmd = entry.get('display', '')
                    if not display_cmd:
                        continue

                    cli_history.append({
                        'timestamp': entry_date,
                        'command': display_cmd,
                        'session_id': entry.get('sessionId')
                    })
                except Exception:
                    continue

        # 시간순 정렬
        cli_history.sort(key=lambda x: x['timestamp'])

    except Exception:
        pass

    return cli_history
