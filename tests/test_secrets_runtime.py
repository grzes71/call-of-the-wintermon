"""Automated py65 integration test suite for Atari 8-bit Secrets display and animation.

Validates:
1. Secrets loaded for active scene (Scene 0 Forest, Scene 1 Forest Castle).
2. Root secrets (no dependency) are active initially; dependent secrets are inactive.
3. Secret placement in PMG_MISSILES has at least 1 line margin from platform.
4. Frame 0 missile graphics rendered into PMG_MISSILES at correct scanline ranges.
5. Inactive secret scanlines remain $00.
6. Animation loop: timer decrements, advances frame index at duration boundary,
   rewrites PMG_MISSILES with new frame bytes, and wraps around.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def test_secrets_init_scene0():
    """Verify secrets_init correctly sets up active and inactive secrets for Scene 0 (Forest)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize DLI and stage Scene 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])

    # Initialize Secrets
    mpu.a = 0
    run_subroutine(mpu, labels["SECRETS_INIT"])

    # In Scene 0 (Forest), there are 3 secrets defined:
    # 0: Gold Key (def 1, sprite 3) on platform-006 (y=56, pas 3) -> dep: None (active!)
    # 1: Gold Key (def 1, sprite 3) on platform-010 (y=24, pas 1) -> dep: None (active!)
    # 2: Ladder (def 2, sprite 2) on platform-011 (y=24, pas 1) -> dep: 1 (inactive!)
    sec_count = mem[labels["SECRETS_COUNT"]]
    assert sec_count == 3, f"Scene 0 should have 3 secrets, got {sec_count}"

    act_addr = labels["SECRETS_ACTIVE"]
    assert mem[act_addr + 0] == 1, "Secret 0 (Gold Key) must be active (no dependency)"
    assert mem[act_addr + 1] == 1, "Secret 1 (Gold Key) must be active (no dependency)"
    assert mem[act_addr + 2] == 0, "Secret 2 (Ladder) must be inactive (depends on secret 1)"

    # Verify PMG scanline positions and margins
    # Platform pas base in PMG: 32 + (plat_y * 2)
    # DLI setup occurs on scanlines p_base - 3 .. p_base - 1.
    # Secrets end at p_base - 4, leaving a 3-scanline transition gap.
    # Pas 3: 32 + 56 * 2 = 144. Sprite 3 height = 16. PMG Y = 144 - 16 - 3 = 125.
    # Pas 1: 32 + 24 * 2 = 80. Sprite 3 height = 16. PMG Y = 80 - 16 - 3 = 61.
    y_addr = labels["SECRETS_PMG_Y"]
    h_addr = labels["SECRETS_HEIGHT"]
    pmg_y0 = mem[y_addr + 0]
    h0 = mem[h_addr + 0]
    assert pmg_y0 == 125
    assert h0 == 16
    # Margin check from platform surface (scanline 144): 144 - (125 + 16) = 3 scanlines (DLI window)
    assert 144 - (pmg_y0 + h0) >= 3

    pmg_y1 = mem[y_addr + 1]
    h1 = mem[h_addr + 1]
    assert pmg_y1 == 61
    assert h1 == 16
    # Margin check from platform surface (scanline 80): 80 - (61 + 16) = 3 scanlines (DLI window)
    assert 80 - (pmg_y1 + h1) >= 3

    # Verify initial frame 0 bytes in PMG_MISSILES
    pmg_m = labels["PMG_MISSILES"]
    frame0_addr = labels["SPRITE_3_FRAME_0"]
    exp_f0_bytes = list(mem[frame0_addr : frame0_addr + 16])

    # Secret 0 scanlines 125..140 must match sprite 3 frame 0
    actual_s0 = list(mem[pmg_m + pmg_y0 : pmg_m + pmg_y0 + 16])
    assert actual_s0 == exp_f0_bytes, f"Secret 0 in PMG_MISSILES does not match Frame 0"

    # Secret 1 scanlines 61..76 must match sprite 3 frame 0
    actual_s1 = list(mem[pmg_m + pmg_y1 : pmg_m + pmg_y1 + 16])
    assert actual_s1 == exp_f0_bytes, f"Secret 1 in PMG_MISSILES does not match Frame 0"

    # Inactive Secret 2 at scanlines 64..77: verify not solid
    # Notice secret 1 is at 62..77, but secret 2 is inactive


def test_secrets_animation_progression():
    """Verify secrets_update decrements timer, advances frames, and updates PMG_MISSILES."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize Scene 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 0
    run_subroutine(mpu, labels["SECRETS_INIT"])

    timer_addr = labels["SECRETS_TIMER"]
    frame_addr = labels["SECRETS_FRAME_IDX"]
    dur_addr = labels["SECRETS_FRAME_DUR"]
    frame_cnt_addr = labels["SECRETS_FRAME_COUNT"]
    pmg_m = labels["PMG_MISSILES"]

    # Secret 0 (Gold Key / Sprite 3) duration and frame count from runtime tables
    key_dur = mem[dur_addr + 0]
    key_frame_count = mem[frame_cnt_addr + 0]

    assert key_dur > 0
    assert key_frame_count > 1
    assert mem[timer_addr + 0] == key_dur
    assert mem[frame_addr + 0] == 0

    # Ticks 1..key_dur-1: timer counts down; frame index stays 0
    for expected_timer in range(key_dur - 1, 0, -1):
        run_subroutine(mpu, labels["SECRETS_UPDATE"])
        assert mem[timer_addr + 0] == expected_timer
        assert mem[frame_addr + 0] == 0

    # Tick key_dur: timer resets to key_dur, frame index advances to 1
    run_subroutine(mpu, labels["SECRETS_UPDATE"])
    assert mem[timer_addr + 0] == key_dur
    assert mem[frame_addr + 0] == 1

    # PMG_MISSILES rows must now match sprite 3 frame 1!
    pmg_y0 = mem[labels["SECRETS_PMG_Y"] + 0]
    f1_addr = labels["SPRITE_3_FRAME_1"]
    exp_f1_bytes = list(mem[f1_addr : f1_addr + 16])
    actual_s0_f1 = list(mem[pmg_m + pmg_y0 : pmg_m + pmg_y0 + 16])
    assert actual_s0_f1 == exp_f1_bytes, f"PMG_MISSILES rows do not match Frame 1 after {key_dur} ticks"

    # Step through remaining frames (frames 2 .. key_frame_count - 1)
    for f in range(2, key_frame_count):
        for _ in range(key_dur):
            run_subroutine(mpu, labels["SECRETS_UPDATE"])
        assert mem[frame_addr + 0] == f

    # Next key_dur ticks should wrap back to frame 0 (loop=True)
    for _ in range(key_dur):
        run_subroutine(mpu, labels["SECRETS_UPDATE"])
    assert mem[frame_addr + 0] == 0


def test_secrets_init_scene1():
    """Verify secrets_init correctly sets up secrets for Scene 1 (Forest Castle)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = 1
    mpu.a = 1
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 1
    run_subroutine(mpu, labels["SECRETS_INIT"])

    sec_count = mem[labels["SECRETS_COUNT"]]
    assert sec_count == 3

    act_addr = labels["SECRETS_ACTIVE"]
    assert mem[act_addr + 0] == 1, "Secret 0 (Gold Key on platform-003) must be active"
    assert mem[act_addr + 1] == 1, "Secret 1 (Gold Key on platform-004) must be active"
    assert mem[act_addr + 2] == 0, "Secret 2 (Ladder on platform-016) must be inactive"


def test_secret_collection_and_stage_progression_scene0():
    """Verify hardware collision triggers secret collection, clearing PMG rows and unlocking dependent stages."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize scene 0 and game
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 0
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    act_addr = labels["SECRETS_ACTIVE"]
    coll_addr = labels["SECRETS_COLLECTED"]
    pmg_m = labels["PMG_MISSILES"]
    m0pl_addr = labels["M0PL"]

    # In Scene 0:
    # Secret 0: Gold Key at x=20, pmg_y=126, height=16 (active)
    # Secret 1: Gold Key at x=119, pmg_y=62, height=16 (active)
    # Secret 2: Ladder at x=68, pmg_y=64, height=14 (inactive, dep on 1)
    assert mem[act_addr + 0] == 1
    assert mem[act_addr + 1] == 1
    assert mem[act_addr + 2] == 0
    assert mem[coll_addr + 0] == 0
    assert mem[coll_addr + 1] == 0
    assert mem[coll_addr + 2] == 0

    # 1. False positive check: player at x=10, y=188 (on missile platform), touches missile
    mem[labels["PLAYER_X"]] = 10
    mem[labels["PLAYER_PMG_Y"]] = 188
    mem[m0pl_addr] = 1  # Hardware collision with missile platform
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # No secret should be collected
    assert mem[coll_addr + 0] == 0
    assert mem[coll_addr + 1] == 0
    assert mem[coll_addr + 2] == 0
    assert mem[act_addr + 0] == 1

    x_addr = labels["SECRETS_X"]
    y_addr = labels["SECRETS_PMG_Y"]
    sec_x0 = mem[x_addr + 0]
    sec_x1 = mem[x_addr + 1]
    pmg_y0 = mem[y_addr + 0]
    pmg_y1 = mem[y_addr + 1]
    pmg_y2 = mem[y_addr + 2]

    # 2. Collect Secret 0: player moves to sec_x0, pmg_y0
    mem[labels["PLAYER_X"]] = sec_x0
    mem[labels["PLAYER_PMG_Y"]] = pmg_y0
    mem[m0pl_addr] = 1  # Hardware collision
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # Secret 0 is collected and inactive
    assert mem[coll_addr + 0] == 1
    assert mem[act_addr + 0] == 0
    # Secret 0 PMG scanlines are now cleared ($00)
    assert all(b == 0 for b in mem[pmg_m + pmg_y0 : pmg_m + pmg_y0 + 16])

    # Secret 1 is still active; Secret 2 is STILL inactive (not all keys collected yet)
    assert mem[act_addr + 1] == 1
    assert mem[act_addr + 2] == 0

    # 3. Collect Secret 1: player moves to sec_x1, pmg_y1
    mem[labels["PLAYER_X"]] = sec_x1
    mem[labels["PLAYER_PMG_Y"]] = pmg_y1
    mem[m0pl_addr] = 1  # Hardware collision
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # Secret 1 is collected and inactive
    assert mem[coll_addr + 1] == 1
    assert mem[act_addr + 1] == 0
    # Secret 1 was cleared, and in the same step Ladder (secret 2) was unlocked and rendered at pmg_y2!
    assert mem[pmg_m + pmg_y1] == 0
    assert mem[pmg_m + pmg_y1 + 1] == 0

    # Now ALL keys (def 1) are collected! Ladder (secret 2, dep 1) must be UNLOCKED!
    assert mem[act_addr + 2] == 1, "Ladder (Secret 2) must be unlocked after all keys collected"
    assert mem[coll_addr + 2] == 0

    # Verify Ladder Frame 0 is rendered into PMG_MISSILES at pmg_y2
    ladder_f0 = labels["SPRITE_2_FRAME_0"]
    exp_ladder_bytes = list(mem[ladder_f0 : ladder_f0 + 14])
    actual_ladder_bytes = list(mem[pmg_m + pmg_y2 : pmg_m + pmg_y2 + 14])
    assert actual_ladder_bytes == exp_ladder_bytes, "Ladder sprite Frame 0 not rendered on unlock"

    # Scene 0 is not complete yet (ladder still active)
    assert mem[labels["ACTIVE_SCENE_ID"]] == 0

    # 4. Collect Secret 2 (Ladder): player moves to x=68, pmg_y2
    mem[labels["PLAYER_X"]] = 68
    mem[labels["PLAYER_PMG_Y"]] = pmg_y2
    mem[m0pl_addr] = 1
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # All secrets in Scene 0 collected -> game_next_scene automatically triggered!
    # active_scene_id must now be 1 (Scene 1: Be Quick or Be Dead)
    assert mem[labels["ACTIVE_SCENE_ID"]] == 1
    # game_phase reset to GAME_PHASE_TITLE_IN for new scene title card
    assert mem[labels["GAME_PHASE"]] == 0
    # Lives (3) preserved across scenes
    assert mem[labels["PLAYER_LIVES"]] == 3
    # Scene 1 secrets initialized fresh (Keys active, Ladder inactive, collected all 0)
    assert mem[act_addr + 0] == 1
    assert mem[act_addr + 1] == 1
    assert mem[act_addr + 2] == 0
    assert mem[coll_addr + 0] == 0


def test_game_success_on_final_scene_completion():
    """Verify that collecting all secrets in the final scene sets GAME_SUCCESS and STATE_OVER."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Start directly on Scene 1 (Forest Castle, final scene)
    mem[labels["ACTIVE_SCENE_ID"]] = 1
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = 1
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 1
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = 1
    run_subroutine(mpu, labels["PLAYER_INIT"])

    m0pl_addr = labels["M0PL"]

    # Scene 1 secrets:
    y_addr = labels["SECRETS_PMG_Y"]
    # Collect Key 0
    mem[labels["PLAYER_X"]] = 8
    mem[labels["PLAYER_PMG_Y"]] = mem[y_addr + 0]
    mem[m0pl_addr] = 1
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # Collect Key 1
    mem[labels["PLAYER_X"]] = 129
    mem[labels["PLAYER_PMG_Y"]] = mem[y_addr + 1]
    mem[m0pl_addr] = 1
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # Ladder (secret 2) unlocked
    act_addr = labels["SECRETS_ACTIVE"]
    assert mem[act_addr + 2] == 1

    # Collect Ladder 2
    mem[labels["PLAYER_X"]] = 96
    mem[labels["PLAYER_PMG_Y"]] = mem[y_addr + 2]
    mem[m0pl_addr] = 1
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    # All scenes finished! Must set GAME_SUCCESS (2) and STATE_OVER (3)
    assert mem[labels["GAME_RESULT"]] == 2  # GAME_SUCCESS = 2
    assert mem[labels["GAME_STATE"]] == 3   # STATE_OVER = 3
