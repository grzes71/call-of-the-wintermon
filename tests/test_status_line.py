"""Automated py65 integration test suite for Atari 8-bit In-Game Status Line.

Validates:
1. Status line display buffer (status_line_vram) is 40 bytes in ANTIC Mode 2.
2. Initial player lives: 3 characters of decimal code 64 (heart glyphs) at columns 0..2.
3. Scene name left-aligned from column 4 (the centred variant is reserved for the
   scene title card, dlist_scene_title).
4. Collected CDs counter on far right (columns 38..39) as 2 decimal digits ($10..$19).
5. Incrementation and clamping of CD count (max 99).
6. Decrementation of player lives (clearing hearts).
7. Full scene change integration (Scene 0 vs Scene 1).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine
from scripts.compile_scenes import (
    STATUS_NAME_COL,
    STATUS_NAME_MAX,
    text_to_screencodes_line,
    text_to_screencodes_line_at,
)
from tests.scene_expectations import load_scene, scene_files


def test_status_line_reset_and_init_scene0():
    """Verify status_line_init correctly sets up hearts, centered scene name, and 00 CDs for Scene 0."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Reset game status line
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    assert mem[labels["PLAYER_LIVES"]] == 3, "Initial player lives must be 3"
    assert mem[labels["PLAYER_CDS"]] == 0, "Initial CD count must be 0"

    # Initialize for Scene 0 (Forest: "The Forest Whispers My Name")
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    vram = labels["STATUS_LINE_VRAM"]
    status_bytes = list(mem[vram : vram + 40])
    assert len(status_bytes) == 40

    # 1. Left: 3 hearts of code 64 (decimal 64 = $40)
    assert status_bytes[0] == 64, f"Column 0 must be heart glyph (64), got {status_bytes[0]}"
    assert status_bytes[1] == 64, f"Column 1 must be heart glyph (64), got {status_bytes[1]}"
    assert status_bytes[2] == 64, f"Column 2 must be heart glyph (64), got {status_bytes[2]}"
    assert status_bytes[3] == 0, "Column 3 must be space"

    # 2. Scene name: left-aligned from column 4 (columns 0..2 lives, column 3 spacer).
    #    Expected bytes come from the scene JSON through the compiler helper (Rule 05).
    scene_name = load_scene(scene_files()[0])["scene"]["name"]
    exp_hud = text_to_screencodes_line_at(
        scene_name, start_col=STATUS_NAME_COL, width=40, max_len=STATUS_NAME_MAX
    )
    assert status_bytes[4:38] == exp_hud[4:38]
    assert status_bytes[4] == exp_hud[4] != 0, (
        "the scene name must start exactly at column 4 (no leading blank)"
    )

    # The centred variant is still compiled for the scene title card.
    exp_title = text_to_screencodes_line(scene_name, width=40)
    title_bytes = list(
        mem[labels["SCENE_SC_01_FOREST_NAME_LINE"] : labels["SCENE_SC_01_FOREST_NAME_LINE"] + 40]
    )
    assert title_bytes == exp_title

    # 3. Far right: 2 digits "00" in screen codes ($10, $10)
    assert status_bytes[38] == 0x10, f"Column 38 must be '0' ($10), got ${status_bytes[38]:02X}"
    assert status_bytes[39] == 0x10, f"Column 39 must be '0' ($10), got ${status_bytes[39]:02X}"


def test_status_line_init_scene1():
    """Verify status_line_init correctly sets up centered scene name for Scene 1 (Be Quick or Be Dead)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["PLAYER_CDS"]] = 7
    mem[labels["ACTIVE_SCENE_ID"]] = 1
    mpu.a = 1
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    vram = labels["STATUS_LINE_VRAM"]
    status_bytes = list(mem[vram : vram + 40])

    # Left: 3 hearts
    assert status_bytes[0:3] == [64, 64, 64]

    # Scene name: left-aligned from column 4 (no leading blank there)
    scene_name = load_scene(scene_files()[1])["scene"]["name"]
    exp_hud = text_to_screencodes_line_at(
        scene_name, start_col=STATUS_NAME_COL, width=40, max_len=STATUS_NAME_MAX
    )
    assert status_bytes[4:38] == exp_hud[4:38]
    assert status_bytes[4] == exp_hud[4] != 0

    # Right: 07 CDs ($10, $17)
    assert status_bytes[38] == 0x10  # '0'
    assert status_bytes[39] == 0x17  # '7'


def test_status_line_cd_counter_and_clamping():
    """Verify CD collection increments score up to 99 and correctly displays digits."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    vram = labels["STATUS_LINE_VRAM"]

    # Initial: 00
    assert mem[vram + 38] == 0x10 and mem[vram + 39] == 0x10

    # Add 1 CD
    run_subroutine(mpu, labels["STATUS_LINE_ADD_CD"])
    assert mem[labels["PLAYER_CDS"]] == 1
    assert mem[vram + 38] == 0x10 and mem[vram + 39] == 0x11  # "01"

    # Set CDs to 42 and refresh
    mem[labels["PLAYER_CDS"]] = 42
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_CDS"])
    assert mem[vram + 38] == 0x14  # '4'
    assert mem[vram + 39] == 0x12  # '2'

    # Set CDs to 98 and add 1
    mem[labels["PLAYER_CDS"]] = 98
    run_subroutine(mpu, labels["STATUS_LINE_ADD_CD"])
    assert mem[labels["PLAYER_CDS"]] == 99
    assert mem[vram + 38] == 0x19  # '9'
    assert mem[vram + 39] == 0x19  # '9'

    # Add 1 more CD: must clamp to 99
    run_subroutine(mpu, labels["STATUS_LINE_ADD_CD"])
    assert mem[labels["PLAYER_CDS"]] == 99
    assert mem[vram + 38] == 0x19
    assert mem[vram + 39] == 0x19


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
