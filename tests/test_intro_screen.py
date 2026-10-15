"""Unit and py65 emulation tests for Intro screen generation, display list, and colors."""

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.gen_intro_text import (
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

    out_file = tmp_path / "intro_text.bin"
    ret = generate_intro_text_binary(txt_file, out_file)
    assert ret == 0
    assert out_file.exists()

    data = out_file.read_bytes()
    assert len(data) == 400  # 10 lines * 40 columns

    # Verify first line: "To miał być rutynowy koncert." (29 chars)
    # Centered in 40 chars: left pad 5, right pad 6
    line1 = data[0:40]
    assert line1[0:5] == bytes([0] * 5)  # 5 spaces
    assert line1[34:40] == bytes([0] * 6)  # 6 spaces

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
