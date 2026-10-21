"""Unit tests for legacy scroll text compiler utility (scripts/compile_scroll_text.py).

Note: Emulation tests for title scroller have been superseded by
tests/test_title_vscroll.py for the vertical scroll window implementation.
"""

from __future__ import annotations

from pathlib import Path
from scripts.compile_scroll_text import char_to_screencode, compile_scroll_text


# ==============================================================================
# Unit Tests for compile_scroll_text.py
# ==============================================================================


def test_char_to_screencode():
    assert char_to_screencode(" ") == 0
    assert char_to_screencode("A") == 33
    assert char_to_screencode("C") == 35
    assert char_to_screencode("!") == 1
    assert char_to_screencode("-") == 13
    assert char_to_screencode("0") == 16
    assert char_to_screencode("a") == 97


def test_compile_scroll_text_output(tmp_path: Path):
    in_file = tmp_path / "test_scroll.txt"
    in_file.write_text("HELLO WORLD!", encoding="utf-8")
    out_file = tmp_path / "test_scroll.asm"

    ret = compile_scroll_text(in_file, out_file, min_trailing_spaces=10)
    assert ret == 0
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "TITLE_SCROLL_TEXT_LEN = 22" in content  # 12 chars + 10 spaces
    assert "title_scroll_text" in content
