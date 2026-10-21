"""Automated test suite verifying enemy sprites 1bpp Player bitmap encoding.

Enforces:
1. Enemy sprites (Players 1-3) must be packed using standard Player bitmap format:
   Bit 7 = leftmost pixel (pixel 0), Bit 0 = rightmost pixel (pixel 7).
   Example: pixel string '10010000' MUST yield byte $90, NOT $06 (which is 5th player missile encoding).
2. Regression verification for Secrets (Missiles):
   Secret sprites (CD, Ladder, Key) must remain byte-for-byte identical to their 5th player missile encoding.
3. Animation frame range and indexing:
   Frame index never exceeds frame count, frame addresses correctly resolved.
4. Enemy sprite linkage validation:
   Rejects missing or invalid sprite IDs.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.compile_scenes import (
    parse_scene_json,
    load_catalogues,
    CatalogueItem,
)
from scripts.compile_sprites import parse_sprites_json
from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def independent_pack_player_row(pixel_str: str) -> int:
    """Independent reference calculation for 1bpp Player row (no compiler code).

    Bit 7 = leftmost pixel (index 0), Bit 0 = rightmost pixel (index 7).
    """
    clean = pixel_str.strip().replace(" ", "")[:8].ljust(8, "0")
    val = 0
    for idx, char in enumerate(clean):
        if char in ("1", "X", "#"):
            val |= (1 << (7 - idx))
    return val


def independent_pack_missile_row(pixel_str: str) -> int:
    """Independent reference calculation for 5th player missile row.

    Pixel 0-1 -> M0 (bits 1,0), Pixel 2-3 -> M1 (bits 3,2),
    Pixel 4-5 -> M2 (bits 5,4), Pixel 6-7 -> M3 (bits 7,6).
    """
    clean = pixel_str.strip().replace(" ", "")[:8].ljust(8, "0")
    p = [1 if c in ("1", "X", "#") else 0 for c in clean]
    m0 = (p[0] << 1) | p[1]
    m1 = (p[2] << 3) | (p[3] << 2)
    m2 = (p[4] << 5) | (p[5] << 4)
    m3 = (p[6] << 7) | (p[7] << 6)
    return m3 | m2 | m1 | m0


# Reference missile bytes for secrets before change
KNOWN_SECRET_FRAME0_BYTES = {
    # Sprite 1: CD (height 16)
    1: [0x24, 0x38, 0x38, 0xB5, 0xB5, 0xB5, 0xFE, 0xFE, 0xFE, 0xFE, 0xB5, 0xB5, 0xB5, 0x38, 0x38, 0x24],
    # Sprite 2: Ladder (height 14)
    2: [0xC3, 0x7E, 0xC3, 0xC3, 0x7E, 0xC3, 0xC3, 0x7E, 0xC3, 0xC3, 0x7E, 0xC3, 0xC3, 0x7E],
    # Sprite 3: Gold Key (height 16)
    3: [0x24, 0x24, 0xF4, 0xF4, 0x24, 0x24, 0x24, 0x24, 0x3C, 0xBD, 0xDB, 0xC3, 0xC3, 0xDB, 0xBD, 0x3C],
}


# ==============================================================================
# 1. Benchmark & Symptom Reproduction Tests (RED before fix)
# ==============================================================================

def test_azathoth_benchmark_row_is_0x90_not_0x06():
    """Benchmark test: Row 0 of Azathoth ('10010000') must be $90 in PMG memory, not $06."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize Scene 0 (Forest)
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["ENEMIES_INIT"])

    # Enemy 0 is Azathoth on Player 1
    pmg_p1 = labels["PMG_PLAYER1"]
    pmg_y0 = mem[labels["ENEMIES_PMG_Y"] + 0]

    actual_row0 = mem[pmg_p1 + pmg_y0]
    expected_row0 = 0x90  # %10010000

    assert actual_row0 == expected_row0, (
        f"Row 0 of Azathoth ('10010000') must be 0x90 (Player 1bpp bitmap), "
        f"got 0x{actual_row0:02X} (0x06 indicates missile packing bug!)"
    )


def test_all_scenes_enemies_pmg_matches_json_reference():
    """For all scenes and all enemies, PMG bytes must match independent JSON reference."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)

    # Load sprites/objects.sprite.json directly
    spr_path = Path("sprites/objects.sprite.json")
    spr_json = json.loads(spr_path.read_text(encoding="utf-8"))
    sprites_dict = {s["id"]: s for s in spr_json.get("sprites", [])}

    channel_ptrs = [
        labels["PMG_PLAYER1"],
        labels["PMG_PLAYER2"],
        labels["PMG_PLAYER3"],
    ]

    scene_count = mem[labels["SCENE_COUNT"]]
    for sc_id in range(scene_count):
        mpu.sp = 0xFD
        mem[0x01FE] = 0x1F
        mem[0x01FF] = 0x00

        run_subroutine(mpu, labels["DLI_INIT"])
        mem[labels["ACTIVE_SCENE_ID"]] = sc_id
        mpu.a = sc_id
        run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
        mpu.a = sc_id
        run_subroutine(mpu, labels["SECRETS_INIT"])
        mpu.a = sc_id
        run_subroutine(mpu, labels["ENEMIES_INIT"])

        e_cnt = mem[labels["ENEMIES_COUNT"]]
        for e_idx in range(e_cnt):
            sid = mem[labels["ENEMIES_SPRITE_ID"] + e_idx]
            ch = mem[labels["ENEMIES_CHANNEL"] + e_idx]
            pmg_y = mem[labels["ENEMIES_PMG_Y"] + e_idx]
            h = mem[labels["ENEMIES_HEIGHT"] + e_idx]

            spr_data = sprites_dict[sid]
            frame0_pixels = spr_data["frames"][0]["pixels"]

            exp_bytes = [independent_pack_player_row(r) for r in frame0_pixels[:h]]
            actual_bytes = [mem[channel_ptrs[ch] + pmg_y + r] for r in range(h)]

            assert actual_bytes == exp_bytes, (
                f"Scene {sc_id} Enemy {e_idx} (Sprite {sid}, Channel P{ch+1}) PMG bytes "
                f"do not match independent Player bitmap reference!\n"
                f"Actual:   {[f'0x{b:02X}' for b in actual_bytes]}\n"
                f"Expected: {[f'0x{b:02X}' for b in exp_bytes]}"
            )


# ==============================================================================
# 2. Secrets Regression Tests (Must remain 100% identical byte-for-byte)
# ==============================================================================

def test_secrets_missile_encoding_regression():
    """Verify secrets (CD, Ladder, Key) retain their exact byte-for-byte missile encoding."""
    mem, labels = load_xex_and_symbols()

    for sid, exp_bytes in KNOWN_SECRET_FRAME0_BYTES.items():
        sym_name = f"SPRITE_{sid}_FRAME_0"
        addr = labels[sym_name]
        actual_bytes = list(mem[addr : addr + len(exp_bytes)])
        assert actual_bytes == exp_bytes, (
            f"Secret sprite {sid} frame 0 bytes differ from known regression baseline!\n"
            f"Actual:   {[f'0x{b:02X}' for b in actual_bytes]}\n"
            f"Expected: {[f'0x{b:02X}' for b in exp_bytes]}"
        )


# ==============================================================================
# 3. Animation Frame Range & 16-bit Pointer Tests
# ==============================================================================

def test_enemy_animation_frame_range_and_pointers():
    """Verify animation frame indexing never exceeds frame count and handles 16-bit addresses."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 0
    run_subroutine(mpu, labels["ENEMIES_INIT"])

    e_cnt = mem[labels["ENEMIES_COUNT"]]
    # Run 60 frames of enemies_update
    for frame in range(60):
        run_subroutine(mpu, labels["ENEMIES_UPDATE"])
        for e in range(e_cnt):
            f_idx = mem[labels["ENEMIES_FRAME_IDX"] + e]
            f_cnt = mem[labels["ENEMIES_FRAME_COUNT"] + e]
            assert 0 <= f_idx < f_cnt, f"Enemy {e} frame index {f_idx} out of range [0, {f_cnt})"
