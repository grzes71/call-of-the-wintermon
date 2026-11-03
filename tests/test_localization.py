"""Unit and py65 emulation tests for game localization (Polish and English versions)."""

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.gen_intro_text import (
    INTRO_TEXT_COLS,
    INTRO_TEXT_LINES,
    INTRO_TEXT_SIZE,
    char_to_atari_screencode,
    generate_intro_text_binary,
)
from scripts.convert_gameover_texts import (
    GAMEOVER_MAX_LINES,
    GAMEOVER_LINE_WIDTH,
    parse_text_file,
    compile_gameover_texts,
)
from scripts.compile_title_vscroll import compile_title_vscroll
from tests.test_state_machine_and_fade import load_xex_into_memory, parse_labels, run_subroutine


def test_english_intro_text_contract():
    """Verify texts/intro-en.txt satisfies ANTIC Mode 2 screen limits (12 lines x <=40 chars)."""
    src_file = Path("texts/intro-en.txt")
    assert src_file.is_file(), "texts/intro-en.txt must exist"

    lines = [line.strip() for line in src_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == INTRO_TEXT_LINES, f"Expected {INTRO_TEXT_LINES} lines, got {len(lines)}"

    for idx, line in enumerate(lines, 1):
        assert len(line) <= INTRO_TEXT_COLS, f"Line {idx} exceeds {INTRO_TEXT_COLS} chars ({len(line)}): '{line}'"


def test_english_gameover_texts_contract():
    """Verify failure-en.txt and success-en.txt satisfy Game Over screen constraints."""
    failure_file = Path("texts/failure-en.txt")
    success_file = Path("texts/success-en.txt")
    assert failure_file.is_file(), "texts/failure-en.txt must exist"
    assert success_file.is_file(), "texts/success-en.txt must exist"

    failure_lines = parse_text_file(failure_file)
    success_lines = parse_text_file(success_file)

    assert len(failure_lines) <= GAMEOVER_MAX_LINES
    assert len(success_lines) <= GAMEOVER_MAX_LINES
    assert len(failure_lines) == 7
    assert len(success_lines) == 18


def test_english_scroll_text_contract():
    """Verify scroll/title-en.txt satisfies vertical scroller width constraints."""
    scroll_file = Path("scroll/title-en.txt")
    assert scroll_file.is_file(), "scroll/title-en.txt must exist"

    lines = [line.strip() for line in scroll_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 4
    for idx, line in enumerate(lines, 1):
        assert len(line) <= 40, f"Line {idx} exceeds 40 chars: '{line}'"


def test_both_xex_binaries_exist():
    """Verify both Polish and English XEX binaries are built."""
    xex_pl = Path("call_of_the_wintermon_pl.xex")
    xex_en = Path("call_of_the_wintermon_en.xex")
    xex_default = Path("call_of_the_wintermon.xex")

    assert xex_pl.is_file(), "call_of_the_wintermon_pl.xex must exist"
    assert xex_en.is_file(), "call_of_the_wintermon_en.xex must exist"
    assert xex_default.is_file(), "call_of_the_wintermon.xex must exist"


def test_intro_vram_content_in_py65_distinguishes_pl_and_en():
    """Verify that PL and EN binaries load their respective intro narrative texts into VRAM."""
    xex_pl = Path("call_of_the_wintermon_pl.xex")
    xex_en = Path("call_of_the_wintermon_en.xex")
    lab_pl = Path("gen/main.lab")
    lab_en = Path("gen/main_en.lab")

    assert xex_pl.is_file() and lab_pl.is_file()
    assert xex_en.is_file() and lab_en.is_file()

    labels_pl = parse_labels(lab_pl)
    labels_en = parse_labels(lab_en)

    intro_vram_pl_addr = labels_pl["INTRO_VRAM"]
    intro_vram_en_addr = labels_en["INTRO_VRAM"]
    assert intro_vram_pl_addr == 0x2800
    assert intro_vram_en_addr == 0x2800

    # Load Polish binary into emulated memory
    mem_pl = bytearray(65536)
    load_xex_into_memory(xex_pl, mem_pl)
    vram_pl = bytes(mem_pl[0x2800:0x2800 + INTRO_TEXT_SIZE])

    # Load English binary into emulated memory
    mem_en = bytearray(65536)
    load_xex_into_memory(xex_en, mem_en)
    vram_en = bytes(mem_en[0x2800:0x2800 + INTRO_TEXT_SIZE])

    # Polish check: 'koncert' screencodes: k(11), o(15), n(14), c(3), e(5), r(18), t(20)
    koncert_screencodes = bytes([char_to_atari_screencode(c) for c in "koncert"])
    assert koncert_screencodes in vram_pl
    assert koncert_screencodes not in vram_en

    # English check: 'routine gig' screencodes
    gig_screencodes = bytes([char_to_atari_screencode(c) for c in "routine gig"])
    assert gig_screencodes in vram_en
    assert gig_screencodes not in vram_pl

