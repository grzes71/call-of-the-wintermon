"""Automated py65 integration test suite for Atari 8-bit In-Game Status Line.

Validates:
1. Status line display buffer (status_line_vram) is 40 bytes in ANTIC Mode 2.
2. Initial player lives: 3 characters of decimal code 64 (heart glyphs) at columns 0..2.
3. Middle area (columns 3..N) is blank space (scene name is only displayed on the
   scene title card, dlist_scene_title).
4. Collected *special* secrets as disc glyphs (code 61) at the right end, filled from
   column 39 leftwards; the icons survive scene changes and only a new game clears them.
5. Decrementation of player lives (clearing hearts).
6. Full scene change integration (Scene 0 vs Scene 1).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine
from scripts.compile_scenes import (
    STATUS_LINE_WIDTH,
    text_to_screencodes_line,
)
from tests.scene_expectations import (
    load_scene,
    scene_files,
    scene_index_with_secrets,
    scene_special_secret_count,
    scene_symbol,
    special_secret_total,
)


# The status line tests need a scene with at least one "special" secret (its icon area) and a
# second, different scene for the "icons survive a scene change" check (Rule 05: the fixture
# must not depend on which scene happens to be first in scenes/scenes.json).
SCENE = scene_index_with_secrets(special=True)
SCENE_NEXT = scene_index_with_secrets(exclude=(SCENE,))

STATUS_GLYPH_SPECIAL = 61


def test_status_line_reset_and_init_scene0():
    """Verify status_line_init sets up hearts, blank middle and no icons."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Reset game status line
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    assert mem[labels["PLAYER_LIVES"]] == 3, "Initial player lives must be 3"
    assert mem[labels["PLAYER_SPECIALS"]] == 0, "No special secret collected yet"

    # Initialize for the fixture scene (its name is derived from the scene JSON below)
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    vram = labels["STATUS_LINE_VRAM"]
    status_bytes = list(mem[vram : vram + 40])
    assert len(status_bytes) == 40

    # 1. Left: 3 hearts of code 64 (decimal 64 = $40)
    assert status_bytes[0] == 64, f"Column 0 must be heart glyph (64), got {status_bytes[0]}"
    assert status_bytes[1] == 64, f"Column 1 must be heart glyph (64), got {status_bytes[1]}"
    assert status_bytes[2] == 64, f"Column 2 must be heart glyph (64), got {status_bytes[2]}"
    assert status_bytes[3] == 0, "Column 3 must be space"

    # 2. Middle: columns 3..name_end must be blank spaces (scene name is not displayed in HUD)
    scene_name = load_scene(scene_files()[SCENE])["scene"]["name"]
    capacity = special_secret_total()
    name_end = STATUS_LINE_WIDTH - capacity
    assert status_bytes[3:name_end] == [0] * (name_end - 3), "Middle of HUD must be empty spaces"

    # The centred variant is still compiled for the scene title card.
    exp_title = text_to_screencodes_line(scene_name, width=40)
    name_line_label = labels[f"SCENE_{scene_symbol(scene_files()[SCENE]).upper()}_NAME_LINE"]
    title_bytes = list(mem[name_line_label : name_line_label + 40])
    assert title_bytes == exp_title

    # 3. Nothing collected yet: the special-secret icon area at the right end is blank.
    assert status_bytes[name_end:] == [0] * capacity


def test_status_line_init_scene1():
    """Verify the collected special icons survive a scene change (Scene 1)."""
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

    vram = labels["STATUS_LINE_VRAM"]
    status_bytes = list(mem[vram : vram + 40])

    # Left: 3 hearts
    assert status_bytes[0:3] == [64, 64, 64]

    # Middle: columns 3..39-collected are spaces (no scene name displayed)
    assert status_bytes[3:STATUS_LINE_WIDTH - collected] == [0] * (STATUS_LINE_WIDTH - collected - 3)

    # Right end: one disc glyph (61) per collected special secret, filled right to left.
    icon_area = status_bytes[STATUS_LINE_WIDTH - collected:]
    assert icon_area == [STATUS_GLYPH_SPECIAL] * collected, (
        "special icons collected in an earlier scene must stay visible"
    )


def test_status_line_special_icons_fill_right_to_left():
    """status_line_add_special draws one disc glyph (code 61) per special secret.

    Contract (engine/status_line.asm): the icons fill the right end of the status line
    from column 39 leftwards - the first one collected ends up rightmost.
    """
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    capacity = special_secret_total()
    assert capacity > 0, "the project must place at least one special secret"
    name_end = STATUS_LINE_WIDTH - capacity

    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    vram = labels["STATUS_LINE_VRAM"]
    assert list(mem[vram + 3:vram + name_end]) == [0] * (name_end - 3), "Middle must be blank"

    # 1. Collect icons one by one: they appear from column 39 leftwards.
    for count in range(1, capacity + 1):
        run_subroutine(mpu, labels["STATUS_LINE_ADD_SPECIAL"])
        assert mem[labels["PLAYER_SPECIALS"]] == count
        rightmost = list(mem[vram + STATUS_LINE_WIDTH - count:vram + STATUS_LINE_WIDTH])
        assert rightmost == [STATUS_GLYPH_SPECIAL] * count, f"{count} icons must sit at the right end"
        # The icon row is exactly `count` wide - while slots remain, the slot left of it stays blank.
        if count < capacity:
            assert mem[vram + STATUS_LINE_WIDTH - count - 1] == 0
        # The middle area remains blank
        assert list(mem[vram + 3:vram + name_end]) == [0] * (name_end - 3)

    # 2. A new game clears the icons again (a scene change must not).
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    assert mem[labels["PLAYER_SPECIALS"]] == 0
    mpu.a = SCENE
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    assert list(mem[vram + name_end:vram + STATUS_LINE_WIDTH]) == [0] * capacity


def test_status_line_refresh_specials_preserves_registers():
    """The icon refresh documents "Preserves: X, Y" - secret_collect relies on it."""
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

    vram = labels["STATUS_LINE_VRAM"]
    assert list(mem[vram : vram + 3]) == [64, 64, 64]

    # Lose 1 life -> 2 lives remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 2
    assert list(mem[vram : vram + 3]) == [64, 64, 0]

    # Lose 1 life -> 1 life remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 1
    assert list(mem[vram : vram + 3]) == [64, 0, 0]

    # Lose 1 life -> 0 lives remaining
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 0
    assert list(mem[vram : vram + 3]) == [0, 0, 0]

    # Lose life at 0 -> does not underflow
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 0
    assert list(mem[vram : vram + 3]) == [0, 0, 0]


def test_status_line_lives_up_to_max_limit_20():
    """Verify player lives display supports up to STATUS_MAX_LIVES (20 hearts) and caps display."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    vram = labels["STATUS_LINE_VRAM"]
    max_lives = labels["STATUS_MAX_LIVES"]
    assert max_lives == 20

    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    # 1. Test 4 lives: columns 0..3 are hearts (64), columns 4..19 are spaces (0)
    mem[labels["PLAYER_LIVES"]] = 4
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[vram : vram + 4]) == [64, 64, 64, 64]
    assert list(mem[vram + 4 : vram + 20]) == [0] * 16

    # 2. Test 10 lives: columns 0..9 are hearts, columns 10..19 are spaces
    mem[labels["PLAYER_LIVES"]] = 10
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[vram : vram + 10]) == [64] * 10
    assert list(mem[vram + 10 : vram + 20]) == [0] * 10

    # 3. Test 20 lives (max capacity): all 20 columns are hearts, column 20 is space
    mem[labels["PLAYER_LIVES"]] = 20
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[vram : vram + 20]) == [64] * 20
    assert mem[vram + 20] == 0

    # 4. Test life loss from 20 to 19: column 19 cleared to space
    run_subroutine(mpu, labels["STATUS_LINE_LOSE_LIFE"])
    assert mem[labels["PLAYER_LIVES"]] == 19
    assert list(mem[vram : vram + 19]) == [64] * 19
    assert mem[vram + 19] == 0
    assert mem[vram + 20] == 0

    # 5. Test lives exceeding 20 (e.g. 25): display strictly caps at 20 hearts, column 20 is untouched
    mem[labels["PLAYER_LIVES"]] = 25
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])
    assert list(mem[vram : vram + 20]) == [64] * 20
    assert mem[vram + 20] == 0
