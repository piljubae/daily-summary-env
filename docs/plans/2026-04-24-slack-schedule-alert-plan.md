# Slack 일정 알림 섹션 분리 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Gemini 출력에 슬랙 임박 일정 섹션(파트 0)을 추가하고, Slack 메시지를 "일정 → 작업 플랜" 순으로 분리해 노출

**Architecture:** Gemini 프롬프트에 파트 0 추가 → 반환된 텍스트에서 섹션별 파싱 함수 도입 → Slack 메시지에서 일정+플랜만 조합 전송 (어제 핵심활동은 MD 파일에만)

**Tech Stack:** Python 3.14, Gemini 2.5 Flash API, Slack Incoming Webhook

---

### Task 1: AI 요약 텍스트 섹션 파싱 함수 작성 (TDD)

**Files:**
- Create: `tests/test_summary_parser.py`
- Modify: `formatters/markdown.py` (함수 추가)

**Step 1: 테스트 작성**

`tests/test_summary_parser.py`:
```python
from formatters.markdown import parse_ai_summary_sections

SAMPLE = """**⚠️ 오늘/이번주 챙길 일정**

- [오늘 4/24] CS 챗봇 SDK 수령

**📊 어제의 핵심 활동**

1. **KMA-6460 작업**
   설명

**📌 오늘의 플랜**

1. **KMA-6460 마무리**
   └ PR 리뷰 대기 중
"""

def test_parse_schedule_section():
    sections = parse_ai_summary_sections(SAMPLE)
    assert "⚠️" in sections["schedule"]
    assert "CS 챗봇 SDK" in sections["schedule"]

def test_parse_plan_section():
    sections = parse_ai_summary_sections(SAMPLE)
    assert "📌" in sections["plan"]
    assert "KMA-6460 마무리" in sections["plan"]

def test_parse_activity_section():
    sections = parse_ai_summary_sections(SAMPLE)
    assert "📊" in sections["activity"]

def test_no_schedule_returns_empty():
    text = "**📊 어제의 핵심 활동**\n\n1. 작업\n\n**📌 오늘의 플랜**\n\n1. 플랜"
    sections = parse_ai_summary_sections(text)
    assert sections["schedule"] == ""

def test_no_plan_returns_empty():
    text = "**📊 어제의 핵심 활동**\n\n1. 작업"
    sections = parse_ai_summary_sections(text)
    assert sections["plan"] == ""
```

**Step 2: 테스트 실행해 실패 확인**

```bash
cd /Users/pilju.bae/daily-summary-env
python -m pytest tests/test_summary_parser.py -v
```
Expected: `ImportError` 또는 `AttributeError` (함수 미존재)

**Step 3: `formatters/markdown.py` 하단에 파싱 함수 추가**

`summarize_with_gemini` 함수 아래에 추가:
```python
def parse_ai_summary_sections(text):
    """AI 요약 텍스트에서 섹션별로 분리.

    Returns:
        dict with keys: "schedule", "activity", "plan"
        각 값은 해당 섹션 전체 텍스트 (헤더 포함). 없으면 빈 문자열.
    """
    import re

    # 섹션 구분자 패턴: **⚠️..**, **📊..**, **📌..**
    section_pattern = re.compile(
        r'(\*\*(?:⚠️[^*]+|📊[^*]+|📌[^*]+)\*\*)',
    )

    # 헤더 키워드 → dict 키 매핑
    def _key(header):
        if "⚠️" in header:
            return "schedule"
        if "📊" in header:
            return "activity"
        if "📌" in header:
            return "plan"
        return None

    parts = section_pattern.split(text)
    sections = {"schedule": "", "activity": "", "plan": ""}

    i = 0
    while i < len(parts):
        part = parts[i]
        key = _key(part)
        if key and i + 1 < len(parts):
            sections[key] = part + parts[i + 1]
            i += 2
        else:
            i += 1

    return sections
```

**Step 4: 테스트 실행해 통과 확인**

```bash
python -m pytest tests/test_summary_parser.py -v
```
Expected: 5개 모두 PASS

**Step 5: 커밋**

```bash
git add tests/test_summary_parser.py formatters/markdown.py
git commit -m "feat: add parse_ai_summary_sections to split Gemini output by section"
```

---

### Task 2: Gemini 프롬프트에 파트 0(임박 일정) 추가

**Files:**
- Modify: `formatters/markdown.py:425-488` (프롬프트 수정)

**Step 1: 프롬프트 앞부분 교체**

`formatters/markdown.py`의 `prompt = f"""...` 부분에서 첫 줄을 수정:

기존:
```python
    prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 바탕으로 두 파트로 나누어 요약해주세요.
```

변경:
```python
    prompt = f"""다음은 하루 동안의 활동 요약 리포트입니다. 이 내용을 바탕으로 세 파트로 나누어 요약해주세요.

## 파트 0: 오늘/이번주 챙길 일정 (슬랙 기반)

아래 Slack 컨텍스트에서 **날짜가 명시된 임박 이벤트**만 추출하라.

추출 기준:
- 오늘 날짜({today}) 언급 → `[오늘]` 태그
- 내일 날짜 언급 → `[내일]` 태그
- 이번 주 내 날짜 언급 → `[N/N 요일]` 태그 (예: `[4/27 월]`)
- 주로 Next Action, 배포일, 입사일, SDK 수령일, QA 일정 등을 우선 스캔
- 슬랙 컨텍스트가 없거나 임박 일정이 없으면 이 파트 전체 생략 (안내 문구 없이)

출력 형식:
**⚠️ 오늘/이번주 챙길 일정**

- [오늘] 항목 설명 → 필요한 액션
- [4/27 월] 항목 설명 → 필요한 액션

임박 순 정렬 (오늘 → 내일 → 이번 주).
항목이 없으면 이 섹션 자체를 출력하지 말 것.

```

이어서 기존 `## 파트 1:` 부분은 그대로 유지.

**Step 2: 출력 형식 블록에 파트 0 헤더 추가**

기존 출력 형식:
```
출력 형식 (반드시 준수):

**📊 어제의 핵심 활동**
...
```

변경 후 (파트 0 섹션 앞에 추가):
```
출력 형식 (반드시 준수):

(파트 0이 있을 경우에만)
**⚠️ 오늘/이번주 챙길 일정**

- [태그] 항목 → 액션
...

**📊 어제의 핵심 활동**
...
```

**Step 3: `today` 변수 주입**

`summarize_with_gemini` 함수 시작 부분에 추가:
```python
from datetime import date
today = date.today().strftime("%Y-%m-%d")
```
그리고 프롬프트 f-string 안에서 `{today}` 사용.

**Step 4: 수동 테스트 (실제 API 호출 없이 프롬프트 출력 확인)**

```bash
cd /Users/pilju.bae/daily-summary-env
python -c "
from formatters.markdown import summarize_with_gemini
import inspect
src = inspect.getsource(summarize_with_gemini)
print('파트 0' in src, '오늘/이번주 챙길 일정' in src)
"
```
Expected: `True True`

**Step 5: 커밋**

```bash
git add formatters/markdown.py
git commit -m "feat: add part 0 schedule alert to Gemini prompt"
```

---

### Task 3: Slack 메시지 구조 변경 — 일정 → 작업 플랜 순 전송

**Files:**
- Modify: `daily_summary.py:147-154`

**Step 1: Slack 메시지 조립 로직 교체**

`daily_summary.py`의 `if ai_summary:` 블록을 다음으로 교체:

기존:
```python
        if ai_summary:
            # AI 요약만 Slack으로 전송
            print("📤 AI 요약만 Slack으로 전송 중...")
            summary_message = f"*📊 {target_date.strftime('%m/%d')} 일일 요약 (AI 생성)*\n\n{ai_summary}\n\n---\n*상세 리포트*: `{filepath}`"
            if send_to_slack(summary_message):
                print("✅ Slack 전송 완료!")
            else:
                print("⚠️ Slack 전송 실패")
```

변경:
```python
        if ai_summary:
            from formatters.markdown import parse_ai_summary_sections
            sections = parse_ai_summary_sections(ai_summary)

            # 슬랙 메시지: 일정 섹션(있을 때만) + 작업 플랜 섹션
            parts = [f"*📅 {target_date.strftime('%m/%d')} 일일 브리핑*"]
            if sections["schedule"]:
                parts.append(sections["schedule"])
            if sections["plan"]:
                parts.append(sections["plan"])
            parts.append(f"---\n*상세 리포트*: `{filepath}`")

            print("📤 AI 요약만 Slack으로 전송 중...")
            if send_to_slack("\n\n".join(parts)):
                print("✅ Slack 전송 완료!")
            else:
                print("⚠️ Slack 전송 실패")
```

**Step 2: 파싱 결과 단위 테스트로 검증**

```bash
python -m pytest tests/test_summary_parser.py -v
```
Expected: 5개 모두 PASS (Task 1에서 작성한 테스트)

**Step 3: 커밋**

```bash
git add daily_summary.py
git commit -m "feat: restructure Slack message to show schedule first, then work plan"
```

---

### Task 4: 통합 확인

**Step 1: 더미 슬랙 컨텍스트로 프롬프트 출력 확인**

```bash
cd /Users/pilju.bae/daily-summary-env
python -c "
from formatters.markdown import summarize_with_gemini, parse_ai_summary_sections

# API 키 없이 프롬프트 구조만 검증
import formatters.markdown as m
import inspect
src = inspect.getsource(m)
assert '파트 0' in src
assert 'parse_ai_summary_sections' in src
print('OK: 프롬프트 파트 0 존재, 파싱 함수 존재')
"
```

**Step 2: 전체 테스트 실행**

```bash
python -m pytest tests/ -v
```
Expected: 전체 PASS

**Step 3: 최종 커밋 (필요 시)**

변경사항이 있다면:
```bash
git add -p
git commit -m "fix: integrate schedule alert section end-to-end"
```
