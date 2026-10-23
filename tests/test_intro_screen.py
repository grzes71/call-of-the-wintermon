"""Unit and py65 emulation tests for Intro screen generation, display list, and colors."""

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.gen_intro_text import (
    INTRO_TEXT_COLS,
    INTRO_TEXT_LINES,
    INTRO_TEXT_SIZE,
    POLISH_CHARS,
    char_to_atari_screencode,
    generate_intro_text_binary,
)
from tests.test_state_machine_and_fade import load_xex_into_memory, parse_labels, run_subroutine


def test_polish_char_mappings():
    """Verify user requested character codes for Polish diacritics."""
    expected_upper = {
        "Ą": 65, "Ć": 66, "Ę": 67, "Ł": 68, "Ń": 69,
        "Ó": 70, "Ś": 71, "Ź": 72, "Ż": 73,
    }
    expected_lower = {
        "ą": 81, "ć": 82, "ę": 83, "ł": 84, "ń": 85,
        "ó": 86, "ś": 87, "ź": 88, "ż": 89,
    }
    for char, code in expected_upper.items():
        assert POLISH_CHARS[char] == code
        assert char_to_atari_screencode(char) == code

    for char, code in expected_lower.items():
        assert POLISH_CHARS[char] == code
        assert char_to_atari_screencode(char) == code


def test_generate_intro_text_from_file(tmp_path: Path):
    txt_file = Path("texts/intro.txt")
    assert txt_file.exists(), "texts/intro.txt must exist"

    # The source text must match the number of ANTIC Mode 2 lines in dlist_intro.
    source_lines = [ln.strip() for ln in txt_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(source_lines) == INTRO_TEXT_LINES, (
        f"texts/intro.txt must hold exactly {INTRO_TEXT_LINES} non-empty lines, "
        f"got {len(source_lines)}"
    )

    out_file = tmp_path / "intro_text.bin"
    ret = generate_intro_text_binary(txt_file, out_file)
    assert ret == 0
    assert out_file.exists()

    data = out_file.read_bytes()
    assert len(data) == INTRO_TEXT_SIZE  # INTRO_TEXT_LINES * INTRO_TEXT_COLS

    # Verify first line centering: the padding must be derived from the source text
    # (Rule 05) instead of hardcoded column numbers.
    line1 = data[0:INTRO_TEXT_COLS]
    text1 = source_lines[0]
    left_pad = (INTRO_TEXT_COLS - len(text1)) // 2
    right_pad = INTRO_TEXT_COLS - len(text1) - left_pad
    assert line1[0:left_pad] == bytes([0] * left_pad)
    assert line1[INTRO_TEXT_COLS - right_pad:] == bytes([0] * right_pad)

    # Every line of the file must be encoded somewhere in the buffer.
    for line in source_lines:
        encoded = bytes(char_to_atari_screencode(c) for c in line)
        assert encoded in data, f"line '{line}' missing from the generated intro binary"

    # Check that 'ł' (84) and 'ć' (82) are in line1
    assert 84 in line1  # 'ł' in 'miał'
    assert 82 in line1  # 'ć' in 'być'


def test_intro_init_py65():
    """Verify intro_init sets light green color, black background, font pointer, and DLIST."""
    xex_file = Path("call_of_the_wintermon.xex")
    lab_file = Path("gen/main.lab")
    assert xex_file.exists()
    assert lab_file.exists()

    mem = bytearray(65536)
    load_xex_into_memory(xex_file, mem)
    labels = parse_labels(lab_file)
    mpu = MPU(memory=mem)
    run_subroutine(mpu, labels["INTRO_INIT"])

    # Color checks
    assert mpu.memory[labels["COLOR1"]] == 0xCA  # Light green text
    assert mpu.memory[labels["COLPF1"]] == 0xCA
    assert mpu.memory[labels["COLOR2"]] == 0x00  # Black playfield background
    assert mpu.memory[labels["COLBK"]] == 0x00   # Black border

    # Font pointer check: FONT_ADDR = $2400 -> page $24
    assert mpu.memory[labels["CHBAS"]] == 0x24
    assert mpu.memory[labels["CHBASE"]] == 0x24

    # DLIST pointer check: SDLSTL/SDLSTH -> DLIST_INTRO
    dlist_intro_addr = labels["DLIST_INTRO"]
    assert mpu.memory[labels["SDLSTL"]] == (dlist_intro_addr & 0xFF)
    assert mpu.memory[labels["SDLSTH"]] == (dlist_intro_addr >> 8)



# ==============================================================================
# Intro display list structure (main.asm, dlist_intro)
# ==============================================================================

DL_MODE_2 = 0x02
DL_LMS = 0x40
DL_JVB = 0x41
DL_BLANK_BASE = 0x70        # DL_BLANK1 = $70 .. DL_BLANK8 = $77


def _walk_display_list(mem: bytearray, start: int) -> list[tuple[int, int | None]]:
    """Return (instruction byte, operand word) pairs until the JVB instruction.

    Only *mode* instructions ($01..$0F) can carry an LMS modifier (bit 6); on blank
    instructions ($70..$77) bit 6 is part of the blank-line count, not an operand.
    """
    instructions: list[tuple[int, int | None]] = []
    pc = start
    while True:
        ins = mem[pc]
        if (ins & 0x0F) != 0 and (ins & 0x40):   # LMS on a mode instruction
            operand = mem[pc + 1] | (mem[pc + 2] << 8)
            pc += 3
        else:
            operand = None
            pc += 1
        instructions.append((ins, operand))
        if ins == DL_JVB:
            return instructions
        assert len(instructions) < 200, "intro display list is not terminated by JVB"


def test_intro_display_list_matches_text_lines():
    """dlist_intro must hold exactly one ANTIC Mode 2 line per intro text line.

    The expected count comes from the generator constant (Rule 05), so extending the
    intro text without extending the display list fails here instead of on screen.
    """
    xex_file = Path("call_of_the_wintermon.xex")
    lab_file = Path("gen/main.lab")
    assert xex_file.exists(), "Binary not found. Run 'make all' first."
    assert lab_file.exists(), "Symbol file not found. Run 'make all' first."

    mem = bytearray(65536)
    load_xex_into_memory(xex_file, mem)
    labels = parse_labels(lab_file)

    instructions = _walk_display_list(mem, labels["DLIST_INTRO"])

    mode2 = [ins for ins, _ in instructions if (ins & 0x0F) == DL_MODE_2]
    assert len(mode2) == INTRO_TEXT_LINES, (
        f"dlist_intro has {len(mode2)} ANTIC Mode 2 lines, expected {INTRO_TEXT_LINES}"
    )

    # Exactly one LMS and it must point at the intro text VRAM.
    lms_operands = [
        operand for ins, operand in instructions
        if (ins & 0x0F) == DL_MODE_2 and (ins & DL_LMS)
    ]
    assert lms_operands == [labels["INTRO_TEXT"]], (
        f"the intro display list must have a single LMS to intro_text, got {lms_operands}"
    )

    # Height accounting: ANTIC Mode 2 shows 8 scanlines per text line, blank
    # instructions 1..8. The block must fit the PAL screen and stay centred.
    height = 0
    blank_gaps = 0
    for ins, _ in instructions:
        if ins == DL_JVB:
            continue
        if (ins & 0x0F) == DL_MODE_2:
            height += 8
        else:
            assert ins >= DL_BLANK_BASE, f"unexpected instruction ${ins:02X} in the intro display list"
            height += ((ins >> 4) & 0x07) + 1
            blank_gaps += 1

    assert height <= 240, f"the intro display list ({height} scanlines) must fit the PAL screen"
    assert 240 - height <= 16, (
        f"the intro text block must stay vertically centred, {240 - height} scanlines of slack"
    )
    assert blank_gaps >= INTRO_TEXT_LINES - 1, "text lines must be separated by blank scanlines"
