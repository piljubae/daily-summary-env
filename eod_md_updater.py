from pathlib import Path
from datetime import date


def find_md_file(topic_hint: str, slack_dir: str) -> Path | None:
    """topic_hint와 파일명이 가장 잘 매칭되는 .md 파일 반환."""
    if not topic_hint or not slack_dir:
        return None
    hint_lower = topic_hint.lower().replace(" ", "")
    candidates = list(Path(slack_dir).glob("[0-9]*.md"))
    for p in candidates:
        if hint_lower in p.name.lower().replace(" ", ""):
            return p
    # 파일 내용에서 검색 (제목 줄)
    for p in candidates:
        try:
            first_line = p.read_text(encoding="utf-8").split("\n")[0].lower()
            if hint_lower in first_line.replace(" ", ""):
                return p
        except (IOError, UnicodeDecodeError):
            continue
    return None


def _already_closed(p: Path) -> bool:
    try:
        return "종결" in p.read_text(encoding="utf-8")
    except OSError:
        return False


def append_closure_note(p: Path, today: str | None = None) -> bool:
    """파일 하단에 종결 섹션 추가. 이미 종결된 경우 스킵."""
    if _already_closed(p):
        return False
    today = today or date.today().isoformat()
    note = f"\n## 종결 ({today})\n\n- 필주님 이후 추가 팔로업 없음 (EOD 리뷰 완료 처리)\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(note)
    return True


def append_handoff_note(p: Path, to: str, today: str | None = None) -> bool:
    """파일 하단에 인수인계 섹션 추가."""
    if _already_closed(p):
        return False
    today = today or date.today().isoformat()
    note = (
        f"\n## 종결 ({today})\n\n"
        f"- **{to}님에게 인수인계 완료** — 필주님 이후 추가 팔로업 없음 (EOD 리뷰)\n"
    )
    with open(p, "a", encoding="utf-8") as f:
        f.write(note)
    return True
