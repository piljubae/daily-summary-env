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
