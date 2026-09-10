#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""macOS Calendar fetcher — AppleScript 기반 업무 미팅 일정 조회."""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from config import CONFIG

# AppleScript가 느린 캘린더(대규모 CalDAV)를 처리하기 위한 충분한 타임아웃
_APPLESCRIPT_TIMEOUT = 200  # 초


def _save_calendar_names_to_env(names: list):
    """선택한 캘린더 이름을 .env 파일에 저장."""
    env_path = Path(__file__).parent.parent / ".env"
    value = ",".join(names)
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GCAL_WORK_CALENDARS="):
                    lines.append(f"GCAL_WORK_CALENDARS={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"\n# macOS 업무 캘린더 이름 (쉼표로 구분)\nGCAL_WORK_CALENDARS={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"✅ 캘린더 설정 저장됨: {value}")


def _get_all_calendar_names() -> list:
    """AppleScript로 macOS 캘린더 이름 목록 조회."""
    script = '''
tell application "Calendar"
    set output to ""
    repeat with c in every calendar
        set output to output & (name of c) & "\\n"
    end repeat
    return output
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        names = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
        return [{"name": n, "account": ""} for n in names]
    except Exception as e:
        print(f"⚠️ 캘린더 목록 조회 실패: {e}", file=sys.stderr)
        return []


def _prompt_user_to_select_calendars(cal_list: list) -> list:
    """사용자에게 캘린더 목록을 보여주고 선택을 받는다."""
    print("\n📅 macOS에서 사용 가능한 캘린더 목록:")
    for i, cal in enumerate(cal_list, 1):
        print(f"  [{i}] {cal['name']}")
    print("\n업무 캘린더 번호를 선택하세요.")
    print("  예) 2,5   → 2번과 5번 선택")
    print("  예) 0     → 캘린더 기능 사용 안 함")
    while True:
        try:
            raw = input("\n번호 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            return []
        if raw == "0":
            return []
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected = []
            valid = True
            for idx in indices:
                if 1 <= idx <= len(cal_list):
                    selected.append(cal_list[idx - 1]["name"])
                else:
                    print(f"  ❌ 잘못된 번호: {idx}")
                    valid = False
                    break
            if valid and selected:
                return selected
        except ValueError:
            print("  ❌ 숫자를 입력해주세요.")


def _get_work_calendar_names() -> list:
    """업무 캘린더 이름 결정: config → 환경변수 → 사용자 선택."""
    names = CONFIG.get("gcal_work_calendar_names", [])
    if names:
        return names
    env_val = os.environ.get("GCAL_WORK_CALENDARS", "").strip()
    if env_val:
        return [n.strip() for n in env_val.split(",") if n.strip()]
    # 사용자 대화형 선택
    cal_list = _get_all_calendar_names()
    if not cal_list:
        print("⚠️ 캘린더 목록을 가져올 수 없습니다.", file=sys.stderr)
        print("   시스템 설정 → 개인 정보 보호 및 보안 → 캘린더에서 Terminal을 허용해주세요.", file=sys.stderr)
        return []
    selected = _prompt_user_to_select_calendars(cal_list)
    if selected:
        _save_calendar_names_to_env(selected)
    return selected


def _ensure_calendar_running():
    """Calendar.app을 실행 상태로 보장.

    launchd/cron 등 백그라운드 컨텍스트에서 첫 AppleScript 조회 시
    Calendar.app이 떠 있지 않으면 -600(응용 프로그램이 실행 중이 아닙니다)
    오류로 조회가 통째로 실패한다. 조회 전에 명시적으로 실행해 방지한다.

    -g: 앱을 앞으로 가져오지 않음(포커스 뺏지 않음), -j: 숨긴 채 실행.
    UI 창이 화면에 뜨지 않아도 프로세스만 살아있으면 조회는 정상 동작한다.
    """
    try:
        subprocess.run(["open", "-g", "-j", "-a", "Calendar"], capture_output=True, timeout=15)
    except Exception as e:
        print(f"⚠️ Calendar.app 실행 시도 실패: {e}", file=sys.stderr)


def fetch_calendar_events(target_date: datetime) -> list:
    """macOS 캘린더에서 업무 미팅 이벤트 조회 (AppleScript).

    필터:
    - 업무 캘린더만 (사용자 설정 or 최초 실행 시 선택)
    - 종일 이벤트 제외
    - 반복 이벤트 제외 (gcal_exclude_recurring=True)

    Returns:
        list[dict]: 정렬된 미팅 이벤트 목록
    """
    work_calendar_names = _get_work_calendar_names()
    if not work_calendar_names:
        print("ℹ️ 업무 캘린더가 선택되지 않아 캘린더 조회를 건너뜁니다.", file=sys.stderr)
        return []

    # Calendar.app이 실행 중이 아니면 -600 오류로 실패하므로 먼저 실행 보장
    _ensure_calendar_running()

    # 캘린더 이름 목록을 AppleScript 리스트로 변환
    cal_names_as = "{" + ", ".join(f'"{n}"' for n in work_calendar_names) + "}"

    # target_date의 연/월/일을 AppleScript에 직접 전달 (locale 무관)
    year = target_date.year
    month = target_date.month
    day = target_date.day

    script = f'''
-- 대상 날짜 시작/끝 설정 (locale 무관 방식)
set dayStart to current date
set year of dayStart to {year}
set month of dayStart to {month}
set day of dayStart to {day}
set hours of dayStart to 0
set minutes of dayStart to 0
set seconds of dayStart to 0
set dayEnd to dayStart + (24 * 60 * 60) - 1

set workCalNames to {cal_names_as}
set output to ""

tell application "Calendar"
    set metaCount to 0
    repeat with calName in workCalNames
        try
            set theCalendar to calendar calName
            -- 진단용: 대상 캘린더의 전체 이벤트 수 (접근 실패/오설정 감지)
            set metaCount to metaCount + (count of events of theCalendar)
            set theEvents to (every event of theCalendar whose start date >= dayStart and start date <= dayEnd)
            repeat with e in theEvents
                set eTitle to summary of e
                set eStart to start date of e
                set eEnd to end date of e
                set eAllDay to allday event of e
                set eRecur to (recurrence of e) is not ""

                if eAllDay is false then
                    set output to output & eTitle & "|||" & ¬
                        (hours of eStart) & ":" & (minutes of eStart) & "|||" & ¬
                        (hours of eEnd) & ":" & (minutes of eEnd) & "|||" & ¬
                        eRecur & "|||" & calName & "###"
                end if
            end repeat
        end try
    end repeat
end tell
return "META|||" & metaCount & "###" & output
'''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=_APPLESCRIPT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        print(
            f"⚠️ 캘린더 조회 시간 초과 ({_APPLESCRIPT_TIMEOUT}초). "
            "캘린더 이벤트를 건너뜁니다.",
            file=sys.stderr
        )
        return []
    except Exception as e:
        print(f"⚠️ 캘린더 조회 실패: {e}", file=sys.stderr)
        return []

    if result.returncode != 0:
        err = result.stderr.strip()
        if err:
            print(f"⚠️ 캘린더 AppleScript 오류: {err}", file=sys.stderr)
        return []

    raw = result.stdout.strip()
    if not raw:
        # 정상이면 최소 META 헤더가 있어야 한다. 빈 출력 = 접근 실패 가능성.
        print(
            "⚠️ 캘린더: 빈 응답 (Calendar 접근 실패 가능). "
            "시스템 설정 → 개인정보 보호 및 보안 → 자동화/캘린더 권한을 확인하세요.",
            file=sys.stderr,
        )
        return []

    # 진단 헤더(META) 파싱: 대상 캘린더 전체 이벤트 수
    meta_total = None
    if raw.startswith("META|||"):
        head, _, rest = raw[len("META|||"):].partition("###")
        try:
            meta_total = int(head.strip())
        except ValueError:
            meta_total = None
        raw = rest.strip()

    # 대상 캘린더에서 이벤트를 하나도 읽지 못함 = 권한/앱 상태/오설정 문제.
    # (해당 날짜에 일정이 없는 정상 케이스와 구분해 조용히 0으로 묻히지 않게 한다)
    if meta_total == 0:
        print(
            f"⚠️ 캘린더: 업무 캘린더({work_calendar_names})에서 이벤트를 "
            "하나도 읽지 못했습니다. macOS 자동화/캘린더 접근 권한, "
            "Calendar.app 실행 상태, 또는 캘린더 이름 설정을 확인하세요.",
            file=sys.stderr,
        )
        return []

    if not raw:
        # META는 정상(이벤트 존재)이지만 해당 날짜 매칭 0건 = 진짜 일정 없는 날
        return []

    exclude_recurring = CONFIG.get("gcal_exclude_recurring", True)
    recurring_whitelist = CONFIG.get("gcal_recurring_whitelist", [])

    result_list = []
    for entry in raw.split("###"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|||")
        if len(parts) < 5:
            continue

        title = parts[0].strip()
        start_raw = parts[1].strip()   # "H:M"
        end_raw = parts[2].strip()     # "H:M"
        is_recurring = parts[3].strip().lower() == "true"
        calendar_name = parts[4].strip()

        # 반복 이벤트 처리
        if is_recurring and exclude_recurring:
            if recurring_whitelist and any(kw.lower() in title.lower() for kw in recurring_whitelist):
                pass  # 화이트리스트: 포함
            else:
                continue  # 제외

        try:
            sh, sm = [int(x) for x in start_raw.split(":")]
            eh, em = [int(x) for x in end_raw.split(":")]
            # 반복 이벤트의 경우 start date가 원래 날짜이므로 target_date 날짜를 사용
            start_dt = target_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_dt = target_date.replace(hour=eh, minute=em, second=0, microsecond=0)
            duration_min = max(1, int((end_dt - start_dt).total_seconds() / 60))
        except Exception:
            continue

        result_list.append({
            "title": title,
            "start": start_dt,
            "end": end_dt,
            "duration_min": duration_min,
            "calendar": calendar_name,
        })

    result_list.sort(key=lambda x: x["start"])
    return result_list
