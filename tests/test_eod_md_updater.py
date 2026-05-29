import tempfile, os
from pathlib import Path
from eod_md_updater import find_md_file, append_closure_note, append_handoff_note

def _make_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)

def test_find_md_file_by_keyword(tmp_path):
    (tmp_path / "07_노출표준화_QA.md").write_text("# 노출표준화\n## Next\n- 확인", encoding="utf-8")
    result = find_md_file("노출표준화", str(tmp_path))
    assert result is not None
    assert "노출표준화" in str(result)

def test_append_closure_note():
    p = _make_md("# 테스트\n## Next\n- 확인\n")
    append_closure_note(p, "2026-05-29")
    content = p.read_text(encoding="utf-8")
    assert "종결" in content
    assert "필주님 이후 추가 팔로업 없음" in content

def test_append_handoff_note():
    p = _make_md("# 테스트\n## Next\n- 확인\n")
    append_handoff_note(p, "박지은", "2026-05-29")
    content = p.read_text(encoding="utf-8")
    assert "박지은" in content
    assert "인수인계" in content
