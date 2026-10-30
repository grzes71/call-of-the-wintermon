"""Automated py65 integration test suite for Atari 8-bit In-Game Mode D HUD.

Validates:
1. Status line display buffer:
   - status_line_chars (16 bytes, narrow Mode D columns 0..15).
   - HUD_VRAM (256 bytes, 32 bytes/line * 8 lines).
2. Initial player lives: 3 characters of decimal code 64 (heart glyphs) at columns 0..2.
3. Middle area (columns 3..7 if unused, col 8..11) are blank space.
4. Collected specials represented as a counter:
   - Column 12: Disc glyph (code 61, gold).
   - Column 13: 'X' glyph (code 56, white).
   - Columns 14..15: Specials count digits ('0'..'9', 2-digit format, white).
5. Decrementation of player lives (clearing hearts).
6. Preserved registers across refresh calls.
7. Support for up to STATUS_MAX_LIVES (8 hearts).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine
from tests.scene_expectations import (
    load_scene,
    scene_files,
    scene_index_with_secrets,
    scene_special_secret_count,
    scene_symbol,
    special_secret_total,
)
from scripts.compile_scenes import text_to_screencodes_line

SCENE = scene_index_with_secrets(special=True)
SCENE_NEXT = scene_index_with_secrets(exclude=(SCENE,))

STATUS_GLYPH_HEART   = 64
STATUS_GLYPH_SPECIAL = 61
STATUS_GLYPH_STAR    = 10
STATUS_GLYPH_X       = STATUS_GLYPH_STAR
STATUS_GLYPH_DIGIT0  = 16


def test_status_line_reset_and_init_scene0():
    """Verify status_line_init sets up hearts, counter icons, and renders HUD_VRAM."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Reset game status line
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    assert mem[labels["PLAYER_LIVES"]] == 3, "Initial player lives must be 3"
    assert mem[labels["PLAYER_SPECIALS"]] == 0, "No special secret collected yet"

    # Initialize for the fixture scene
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    chars_addr = labels["STATUS_LINE_CHARS"]
    status_chars = list(mem[chars_addr : chars_addr + 16])
    assert len(status_chars) == 16

    # 1. Left: 3 hearts of code 64, cols 3..11 blank space
    assert status_chars[0:3] == [STATUS_GLYPH_HEART, STATUS_GLYPH_HEART, STATUS_GLYPH_HEART]
    assert status_chars[3:12] == [0] * 9

    # 2. Right: Special counter: [col 12: disc 61] [col 13: 'X' 56] [col 14: '0' 16] [col 15: 0]
    assert status_chars[12] == STATUS_GLYPH_SPECIAL
    assert status_chars[13] == STATUS_GLYPH_X
    assert status_chars[14] == STATUS_GLYPH_DIGIT0
    assert status_chars[15] == 0

    # 3. Check HUD_VRAM has rendered bitmap data across the 8 rows
    hud_vram = labels["HUD_VRAM"]
    assert any(mem[hud_vram + row * 32 + col * 2] != 0 for col in (0, 1, 2) for row in range(8)), "Hearts must be rendered to HUD_VRAM"
    assert any(mem[hud_vram + row * 32 + 12 * 2] != 0 for row in range(8)), "Disc icon must be rendered to HUD_VRAM"
    assert any(mem[hud_vram + row * 32 + 13 * 2] != 0 for row in range(8)), "'*' icon must be rendered to HUD_VRAM"
    assert any(mem[hud_vram + row * 32 + 14 * 2] != 0 for row in range(8)), "Digit '0' must be rendered to HUD_VRAM"

    # Verify column 13 uses color %01 (hearts color COLPF0) and column 14 uses color %10 (text color COLPF1)
    col13_bytes = [mem[hud_vram + r * 32 + 13 * 2 + b] for r in range(8) for b in (0, 1)]
    col14_bytes = [mem[hud_vram + r * 32 + 14 * 2 + b] for r in range(8) for b in (0, 1)]
    assert any(col13_bytes) and all((b & 0xAA) == 0 for b in col13_bytes), "Col 13 must use color %01 (hearts color COLPF0)"
    assert any(col14_bytes) and all((b & 0x55) == 0 for b in col14_bytes), "Col 14 must use color %10 (text color COLPF1)"

    # Scene title name line check (for scene title card)
    scene_name = load_scene(scene_files()[SCENE])["scene"]["name"]
    exp_title = text_to_screencodes_line(scene_name, width=40)
    name_line_label = labels[f"SCENE_{scene_symbol(scene_files()[SCENE]).upper()}_NAME_LINE"]
    title_bytes = list(mem[name_line_label : name_line_label + 40])
    assert title_bytes == exp_title


def test_status_line_init_scene1():
    """Verify collected special count survives a scene change."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    collected = scene_special_secret_count(SCENE)
    assert collected > 0, "scene 0 must place at least one special secret"

    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["PLAYER_SPECIALS"]] = collected
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE_NEXT
    mpu.a = SCENE_NEXT
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    chars_addr = labels["STATUS_LINE_CHARS"]
    status_chars = list(mem[chars_addr : chars_addr + 16])

    # Left: 3 hearts
    assert status_chars[0:3] == [STATUS_GLYPH_HEART, STATUS_GLYPH_HEART, STATUS_GLYPH_HEART]

    # Right: disc, 'X', and digits (2-digit counter)
    assert status_chars[12] == STATUS_GLYPH_SPECIAL
    assert status_chars[13] == STATUS_GLYPH_X
    if collected < 10:
        assert status_chars[14] == STATUS_GLYPH_DIGIT0 + collected
        assert status_chars[15] == 0
    else:
        assert status_chars[14] == STATUS_GLYPH_DIGIT0 + 1
        assert status_chars[15] == STATUS_GLYPH_DIGIT0 + (collected - 10)


def test_status_line_special_counter_increments():
    """status_line_add_special increments specials and updates columns 14..15 digits."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    capacity = special_secret_total()
    assert capacity > 0

    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    chars_addr = labels["STATUS_LINE_CHARS"]

    for count in range(1, capacity + 1):
        run_subroutine(mpu, labels["STATUS_LINE_ADD_SPECIAL"])
        assert mem[labels["PLAYER_SPECIALS"]] == count
        if count < 10:
            assert mem[chars_addr + 14] == STATUS_GLYPH_DIGIT0 + count
            assert mem[chars_addr + 15] == 0
        else:
            assert mem[chars_addr + 14] == STATUS_GLYPH_DIGIT0 + 1
            assert mem[chars_addr + 15] == STATUS_GLYPH_DIGIT0 + (count - 10)

    # Reset clears counter
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    assert mem[labels["PLAYER_SPECIALS"]] == 0
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    assert mem[chars_addr + 14] == STATUS_GLYPH_DIGIT0
    assert mem[chars_addr + 15] == 0


def test_status_line_refresh_specials_preserves_registers():
    """The icon refresh documents 'Preserves: X, Y' - callers rely on it."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["PLAYER_SPECIALS"]] = special_secret_total()
    mpu.x = 0x5A
    mpu.y = 0x3C
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_SPECIALS"])
    assert mpu.x == 0x5A, f"X must be preserved, got ${mpu.x:02X}"
    assert mpu.y == 0x3C, f"Y must be preserved, got ${mpu.y:02X}"


def test_status_line_player_lives_and_loss():
    """Verify player life loss removes hearts from left to right."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    chars_addr = labels["STATUS_LINE_CHARS"]
    assert list(mem[chars_addr : chars_addr + 3]) == [STATUS_GLYPH_HEART] * 3

    # Lose 1 life -> 2 lives remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 2
    assert list(mem[chars_addr : chars_addr + 3]) == [STATUS_GLYPH_HEART, STATUS_GLYPH_HEART, 0]

    # Lose 1 life -> 1 life remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 1
    assert list(mem[chars_addr : chars_addr + 3]) == [STATUS_GLYPH_HEART, 0, 0]

    # Lose 1 life -> 0 lives remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 0
    assert list(mem[chars_addr : chars_addr + 3]) == [0, 0, 0]

    # Lose life at 0 -> does not underflow
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 0
    assert list(mem[chars_addr : chars_addr + 3]) == [0, 0, 0]


def test_status_line_lives_up_to_max_limit_8():
    """Verify player lives display supports up to STATUS_MAX_LIVES (8 hearts) and caps display."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    chars_addr = labels["STATUS_LINE_CHARS"]
    max_lives = labels["STATUS_MAX_LIVES"]
    assert max_lives == 8

    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    # 1. Test 4 lives: columns 0..3 are hearts (64), columns 4..7 are spaces (0)
    mem[labels["PLAYER_LIVES"]] = 4
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[chars_addr : chars_addr + 4]) == [STATUS_GLYPH_HEART] * 4
    assert list(mem[chars_addr + 4 : chars_addr + 8]) == [0] * 4

    # 2. Test 8 lives (max capacity): all 8 columns are hearts
    mem[labels["PLAYER_LIVES"]] = 8
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[chars_addr : chars_addr + 8]) == [STATUS_GLYPH_HEART] * 8

    # 3. Test life loss from 8 to 7: column 7 cleared to space
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 7
    assert list(mem[chars_addr : chars_addr + 7]) == [STATUS_GLYPH_HEART] * 7
    assert mem[chars_addr + 7] == 0

    # 4. Test lives exceeding 8 (e.g. 12): display strictly caps at 8 hearts
    mem[labels["PLAYER_LIVES"]] = 12
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[chars_addr : chars_addr + 8]) == [STATUS_GLYPH_HEART] * 8
    assert mem[chars_addr + 8] == 0  # Col 8 remains spacer
