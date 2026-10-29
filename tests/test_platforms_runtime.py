"""Automated py65 integration test suite for Atari 8-bit dynamic moving platforms.

Validates:
1. platforms_init across scenes:
   - Sets plat_count matching scene JSON.
   - Restores scene_plat_init_x into scene_plat_x.
   - Translates movement strategy (0..4) and derives initial direction:
     (1 & 3 start left = 1; 2 & 4 start right = 0; 0 starts right = 0).
   - Derives pas row index = (y - 8) >> 4.
   - Loads packed plat_hw_info (type, ch_start, ch_count).
   - Resets speed and pause timers to 0.
2. Speed cadence (1 pixel every 2 frames):
   - Frame divider counts down from PLATFORM_SPEED_FRAMES (1).
   - Moves on frame 1, waits on frame 2.
3. Screen boundary bouncing:
   - Left edge: X <= 0 reverses dir to 0 (right).
   - Right edge: X + width >= 160 reverses dir to 1 (left).
   - 50-frame pause triggered at boundary bounce for pause strategies (3 and 4).
4. 50-frame pause timing:
   - Position remains stationary while pause_timer counts down from 50 to 0.
   - Resumes movement on frame 51.
5. Inter-platform collision & bouncing:
   - Two platforms in the same row (same pas) touching reverse directions without overlap.
   - Triggers 50-frame pause if pause strategy is configured.
6. DLI hardware position synchronization:
   - Both active and inactive DLI buffers (buffer 0 and buffer 1) updated immediately
     to 48 + X for sprite channels (P1..P3) and missile channels (M0..M3).
7. Hero carrier mechanics:
   - Hero standing on moving platform (IDLE or WALK) is carried horizontally by dx.
   - Clamped to screen boundary [0, 152].
   - If Hero falls/jumps, platform moves independently without moving Hero.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.compile_scenes import PLAT_MOVEMENT_MAP, PLAT_SPEED_RELOAD_MAP
from tests.scene_expectations import (
    dli_enemy_hpos_slots,
    dli_secret_hpos_slots,
    scene_files,
    scene_objects,
    scene_platform_index,
    scene_platforms,
)
from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def _setup_mpu_and_scene(scene_id: int = 0) -> tuple[MPU, bytearray, dict[str, int]]:
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = scene_id
    mpu.a = scene_id
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = scene_id
    run_subroutine(mpu, labels["PLAYER_INIT"])
    return mpu, mem, labels


# ==============================================================================
# 1. Initialization Tests
# ==============================================================================


def test_platforms_init_all_scenes():
    """Verify platforms_init correctly sets up runtime SoA tables for all scenes."""
    for scene_id, scene_file in enumerate(scene_files()):
        expected_plats = scene_platforms(scene_id)
        mpu, mem, labels = _setup_mpu_and_scene(scene_id)

        plat_count = mem[labels["PLAT_COUNT"]]
        assert plat_count == len(expected_plats), (
            f"Scene {scene_id} ({scene_file}): plat_count {plat_count} != expected {len(expected_plats)}"
        )

        ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
        init_x_ptr = mem[labels["SCENE_PLAT_INIT_X_LO"] + scene_id] | (
            mem[labels["SCENE_PLAT_INIT_X_HI"] + scene_id] << 8
        )

        for i, plat in enumerate(expected_plats):
            # X position must match initial X
            assert mem[ptr_x + i] == mem[init_x_ptr + i] == plat["x"], (
                f"Scene {scene_id} plat {i} X mismatch"
            )

            # Movement code
            expected_mv = PLAT_MOVEMENT_MAP[plat.get("movement", "none")]
            assert mem[labels["PLAT_MOVEMENT"] + i] == expected_mv, (
                f"Scene {scene_id} plat {i} movement mismatch"
            )

            # Initial direction: 1 & 3 start left (1), 0, 2 & 4 start right (0)
            expected_dir = expected_mv & 1
            assert mem[labels["PLAT_DIR"] + i] == expected_dir, (
                f"Scene {scene_id} plat {i} initial dir mismatch"
            )

            # Row pas = (y - 8) >> 4
            expected_pas = (plat["y"] - 8) >> 4
            assert mem[labels["PLAT_PAS"] + i] == expected_pas, (
                f"Scene {scene_id} plat {i} pas index mismatch"
            )

            # Movement speed reload value (3=slow, 1=medium, 0=fast)
            expected_spd = PLAT_SPEED_RELOAD_MAP.get(
                plat.get("movement_speed", plat.get("speed", "medium")), 1
            )
            assert mem[labels["PLAT_SPEED"] + i] == expected_spd, (
                f"Scene {scene_id} plat {i} speed mismatch"
            )

            # Timers initialized to 0
            assert mem[labels["PLAT_SPEED_TIMER"] + i] == 0
            assert mem[labels["PLAT_PAUSE_TIMER"] + i] == 0


# ==============================================================================
# 2. Speed Cadence (1 px / 2 frames) Tests
# ==============================================================================


def test_platform_speed_medium():
    """Verify Medium platforms advance by 1 pixel every 2 frames (25 px/sec PAL)."""
    mpu, mem, labels = _setup_mpu_and_scene(0)

    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED"]] = 1     # Medium reload = 1
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Frame 1: moves to 41, speed_timer becomes 1
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 1

    # Frame 2: speed_timer decrements to 0, does not move
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0

    # Frame 3: moves to 42, speed_timer becomes 1
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 42
    assert mem[labels["PLAT_SPEED_TIMER"]] == 1


def test_platform_speed_slow():
    """Verify Slow platforms advance by 1 pixel every 4 frames (12.5 px/sec PAL)."""
    mpu, mem, labels = _setup_mpu_and_scene(0)

    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED"]] = 3     # Slow reload = 3
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Frame 1: moves to 41, speed_timer becomes 3
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 3

    # Frame 2: decrements to 2, stationary
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 2

    # Frame 3: decrements to 1, stationary
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 1

    # Frame 4: decrements to 0, stationary
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0

    # Frame 5: moves to 42, speed_timer becomes 3
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 42
    assert mem[labels["PLAT_SPEED_TIMER"]] == 3


def test_platform_speed_fast():
    """Verify Fast platforms advance by 1 pixel every 1 frame (50 px/sec PAL)."""
    mpu, mem, labels = _setup_mpu_and_scene(0)

    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED"]] = 0     # Fast reload = 0
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Frame 1: moves to 41, speed_timer remains 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 41
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0

    # Frame 2: moves to 42, speed_timer remains 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 42
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0

    # Frame 3: moves to 43, speed_timer remains 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 43
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0


# ==============================================================================
# 3. Screen Boundary Bouncing Tests
# ==============================================================================


def test_platform_left_boundary_bounce():
    """Verify platform bounces when reaching left edge (X <= 0) and reverses dir."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 1

    # Platform at X = 1 moving left (dir = 1), strategy left-right (1, no pause)
    mem[ptr_x] = 1
    mem[labels["PLAT_MOVEMENT"]] = 1
    mem[labels["PLAT_DIR"]] = 1
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    # Step: candidate X becomes 0 -> hits boundary, clamps to 0, reverses dir to 0 (right)
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 0
    assert mem[labels["PLAT_DIR"]] == 0
    assert mem[labels["PLAT_PAUSE_TIMER"]] == 0

    # Next step (2 frames later): moves right to X = 1
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 1
    assert mem[labels["PLAT_DIR"]] == 0


def test_platform_right_boundary_bounce():
    """Verify platform bounces when reaching right edge (X + width >= 160) and reverses dir."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 1

    # Platform width = 16, candidate X = 144 -> 144 + 16 = 160 (boundary)
    mem[ptr_w] = 16
    mem[ptr_x] = 143
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left (no pause)
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 144
    assert mem[labels["PLAT_DIR"]] == 1  # reversed to left
    assert mem[labels["PLAT_PAUSE_TIMER"]] == 0

    # Next step: moves left to X = 143
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 143
    assert mem[labels["PLAT_DIR"]] == 1


# ==============================================================================
# 4. 50-Frame Pause Timing Tests
# ==============================================================================


def test_platform_50_frame_pause_at_bounce():
    """Verify pause strategy triggers 50-frame pause at bounce, remaining stationary."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 1

    # Strategy 3: left-pause-right. Moving left towards X = 0
    mem[ptr_x] = 1
    mem[labels["PLAT_MOVEMENT"]] = 3  # left-pause-right
    mem[labels["PLAT_DIR"]] = 1       # left
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    # Trigger boundary bounce: X reaches 0, pause timer set to 50, dir reversed to 0 (right)
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 0
    assert mem[labels["PLAT_DIR"]] == 0
    assert mem[labels["PLAT_PAUSE_TIMER"]] == 50

    # Next 50 frames: platform must remain stationary at X = 0 while pause_timer counts down
    for frame in range(1, 51):
        run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
        expected_pause_left = 50 - frame
        assert mem[ptr_x] == 0, f"Platform moved during pause on frame {frame}"
        assert mem[labels["PLAT_PAUSE_TIMER"]] == expected_pause_left

    # On frame 51, pause timer is 0, so platform resumes moving right!
    assert mem[labels["PLAT_PAUSE_TIMER"]] == 0
    assert mem[labels["PLAT_SPEED_TIMER"]] == 0
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 1, "Platform did not resume movement after pause ended"
    assert mem[labels["PLAT_DIR"]] == 0


# ==============================================================================
# 5. Inter-Platform Collision Tests
# ==============================================================================


def test_inter_platform_collision_bounce():
    """Verify two platforms in the same pas bounce off each other without overlapping."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 2

    # Two platforms on pas = 1 (row y = 24)
    mem[labels["PLAT_PAS"] + 0] = 1
    mem[labels["PLAT_PAS"] + 1] = 1

    # Platform 0: X = 20, W = 16, moving right (dir = 0)
    mem[ptr_x + 0] = 20
    mem[ptr_w + 0] = 16
    mem[labels["PLAT_MOVEMENT"] + 0] = 1  # left-right
    mem[labels["PLAT_DIR"] + 0] = 0       # moving right
    mem[labels["PLAT_SPEED_TIMER"] + 0] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 0] = 0

    # Platform 1: X = 37, W = 16, moving left (dir = 1)
    # Notice: when plat 0 moves right to 21, 21 + 16 = 37 >= 37 (plat 1's X)!
    mem[ptr_x + 1] = 37
    mem[ptr_w + 1] = 16
    mem[labels["PLAT_MOVEMENT"] + 1] = 1  # left-right
    mem[labels["PLAT_DIR"] + 1] = 1       # moving left
    mem[labels["PLAT_SPEED_TIMER"] + 1] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 1] = 0

    # Execute update
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    # Plat 0 touched Plat 1:
    # Plat 0 reversed to left (dir = 1), clamped to 37 - 16 = 21
    assert mem[labels["PLAT_DIR"] + 0] == 1
    assert mem[ptr_x + 0] == 21

    # Plat 1 was bounced to right (dir = 0) and then moved right to 38
    assert mem[labels["PLAT_DIR"] + 1] == 0
    assert mem[ptr_x + 1] == 38

    # Ensure no overlap: plat 0 right edge (21 + 16 = 37) <= plat 1 left edge (38)
    assert mem[ptr_x + 0] + mem[ptr_w + 0] <= mem[ptr_x + 1]


def test_inter_platform_collision_with_pause():
    """Verify pause strategy on either platform triggers 50-frame pause on collision."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 2

    mem[labels["PLAT_PAS"] + 0] = 2
    mem[labels["PLAT_PAS"] + 1] = 2

    # Platform 0 has pause strategy 3 (left-pause-right)
    mem[ptr_x + 0] = 20
    mem[ptr_w + 0] = 16
    mem[labels["PLAT_MOVEMENT"] + 0] = 3
    mem[labels["PLAT_DIR"] + 0] = 0
    mem[labels["PLAT_SPEED_TIMER"] + 0] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 0] = 0

    # Platform 1 has pause strategy 4 (right-pause-left)
    mem[ptr_x + 1] = 37
    mem[ptr_w + 1] = 16
    mem[labels["PLAT_MOVEMENT"] + 1] = 4
    mem[labels["PLAT_DIR"] + 1] = 1
    mem[labels["PLAT_SPEED_TIMER"] + 1] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 1] = 0

    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    assert mem[labels["PLAT_PAUSE_TIMER"] + 0] == 50
    assert mem[labels["PLAT_PAUSE_TIMER"] + 1] == 50


# ==============================================================================
# 6. DLI Hardware Synchronization Tests
# ==============================================================================


def test_platform_dli_hardware_hpos_sync():
    """Verify moving platform updates both active and inactive DLI HPOS buffers."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["PLAT_COUNT"]] = 1

    pas = 2
    mem[labels["PLAT_PAS"]] = pas
    # Sprite platform, channel 0 (P1), 1 segment (width 32)
    # hw_info = (type << 7) | (ch_start << 4) | ch_count = (0 << 7) | (0 << 4) | 1 = 1
    mem[labels["PLAT_HW_INFO"]] = 1
    mem[ptr_x] = 50
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    # Step: moves from 50 to 51
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x] == 51

    # DLI HPOSP1 registers in buffer 0 and buffer 1 must be 48 + 51 = 99
    expected_hpos = 48 + 51
    buf0_addr = labels["DLI_HPOS_P1"] + pas
    buf1_addr = labels["DLI_HPOS_P1"] + 8 + pas
    assert mem[buf0_addr] == expected_hpos, f"Buffer 0 HPOS mismatch: {mem[buf0_addr]} != {expected_hpos}"
    assert mem[buf1_addr] == expected_hpos, f"Buffer 1 HPOS mismatch: {mem[buf1_addr]} != {expected_hpos}"


# ==============================================================================
# 7. Hero Carrier Mechanics Tests
# ==============================================================================


def test_hero_carrier_moving_right():
    """Verify Hero standing on a moving platform is carried to the right by dx."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    # Setup platform 0
    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[ptr_w] = 32
    mem[labels["PLAT_MOVEMENT"]] = 2  # right-left
    mem[labels["PLAT_DIR"]] = 0       # moving right
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    # Setup Hero standing on platform 0 in IDLE state
    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    hero_start_x = 50
    mem[labels["PLAYER_X"]] = hero_start_x

    # Update platform
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    # Platform moved from 40 to 41 (+1)
    assert mem[ptr_x] == 41
    # Hero carried from 50 to 51 (+1)
    assert mem[labels["PLAYER_X"]] == hero_start_x + 1
    # GTIA HPOSP0 updated to 48 + 51
    assert mem[labels["HPOSP0"]] == 48 + hero_start_x + 1


def test_hero_carrier_moving_left():
    """Verify Hero standing on a moving platform is carried to the left by dx."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[ptr_w] = 32
    mem[labels["PLAT_MOVEMENT"]] = 1  # left-right
    mem[labels["PLAT_DIR"]] = 1       # moving left
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_WALK"]
    hero_start_x = 50
    mem[labels["PLAYER_X"]] = hero_start_x

    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    assert mem[ptr_x] == 39
    assert mem[labels["PLAYER_X"]] == hero_start_x - 1
    assert mem[labels["HPOSP0"]] == 48 + hero_start_x - 1


def test_hero_carrier_screen_boundary_limits():
    """Verify Hero carrier respects screen boundaries [0, 152]."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 10
    mem[ptr_w] = 32
    mem[labels["PLAT_MOVEMENT"]] = 1
    mem[labels["PLAT_DIR"]] = 1
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    # Hero at left boundary X = 0
    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    mem[labels["PLAYER_X"]] = 0

    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    # Platform moved left to 9, but Hero cannot move past 0
    assert mem[ptr_x] == 9
    assert mem[labels["PLAYER_X"]] == 0


def test_hero_not_carried_when_jumping_or_falling():
    """Verify Hero is NOT carried when in airborne states (JUMP or FALL)."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    mem[labels["PLAT_COUNT"]] = 1
    mem[ptr_x] = 40
    mem[ptr_w] = 32
    mem[labels["PLAT_MOVEMENT"]] = 2
    mem[labels["PLAT_DIR"]] = 0
    mem[labels["PLAT_SPEED_TIMER"]] = 0
    mem[labels["PLAT_PAUSE_TIMER"]] = 0

    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_JUMP"]
    mem[labels["PLAYER_X"]] = 50

    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    # Platform moved right to 41, but Hero remained at 50
    assert mem[ptr_x] == 41
    assert mem[labels["PLAYER_X"]] == 50


# ==============================================================================
# 8. Secret & Enemy Carrier Mechanics Tests
# ==============================================================================


def test_scene_object_platform_indices_initialized():
    """Verify secrets_plat_idx, secrets_rel_x, and enemies_plat_idx match JSON across all scenes."""
    for scene_id, scene_file in enumerate(scene_files()):
        plats = scene_platforms(scene_id)
        mpu, mem, labels = _setup_mpu_and_scene(scene_id)
        mpu.a = scene_id
        run_subroutine(mpu, labels["SECRETS_INIT"])
        mpu.a = scene_id
        run_subroutine(mpu, labels["ENEMIES_INIT"])

        for i, sec in enumerate(scene_objects(scene_file, "secret")):
            expected_plat_idx = scene_platform_index(scene_id, sec["platform_id"])
            expected_rel_x = (sec["x"] - plats[expected_plat_idx]["x"]) & 0xFF
            assert mem[labels["SECRETS_PLAT_IDX"] + i] == expected_plat_idx, (
                f"Scene {scene_id} ({scene_file}) secret {i} plat_idx mismatch"
            )
            assert mem[labels["SECRETS_REL_X"] + i] == expected_rel_x, (
                f"Scene {scene_id} ({scene_file}) secret {i} rel_x mismatch"
            )

        for i, enm in enumerate(scene_objects(scene_file, "enemy")):
            expected_plat_idx = scene_platform_index(scene_id, enm["platform_id"])
            assert mem[labels["ENEMIES_PLAT_IDX"] + i] == expected_plat_idx, (
                f"Scene {scene_id} ({scene_file}) enemy {i} plat_idx mismatch"
            )


def test_secret_carrier_on_moving_platform():
    """Verify active and locked secrets on a moving platform move in lockstep with the platform."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["ENEMIES_COUNT"]] = 0

    # Setup 2 platforms: platform 0 moving right, platform 1 stationary
    mem[labels["PLAT_COUNT"]] = 2
    mem[ptr_x + 0] = 40
    mem[ptr_w + 0] = 32
    mem[labels["PLAT_MOVEMENT"] + 0] = 2  # right-left
    mem[labels["PLAT_DIR"] + 0] = 0       # moving right
    mem[labels["PLAT_SPEED"] + 0] = 0     # fast (1 px/frame)
    mem[labels["PLAT_SPEED_TIMER"] + 0] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 0] = 0

    mem[ptr_x + 1] = 100
    mem[ptr_w + 1] = 32
    mem[labels["PLAT_MOVEMENT"] + 1] = 0  # stationary

    # Setup 3 secrets:
    # Secret 0: active on moving platform 0 (5th player / missiles channel 3, zone 2, rel_x = 8)
    # Secret 1: dependency-locked (inactive) on moving platform 0 (zone 3, rel_x = 12)
    # Secret 2: active on stationary platform 1 (zone 4, rel_x = 8)
    mem[labels["SECRETS_COUNT"]] = 3

    mem[labels["SECRETS_PLAT_IDX"] + 0] = 0
    mem[labels["SECRETS_REL_X"] + 0] = 8
    mem[labels["SECRETS_ACTIVE"] + 0] = 1
    mem[labels["SECRETS_COLLECTED"] + 0] = 0
    mem[labels["SECRETS_X"] + 0] = 48
    mem[labels["SECRETS_ZONE"] + 0] = 2
    mem[labels["SECRETS_CHANNEL"] + 0] = 3

    mem[labels["SECRETS_PLAT_IDX"] + 1] = 0
    mem[labels["SECRETS_REL_X"] + 1] = 12
    mem[labels["SECRETS_ACTIVE"] + 1] = 0
    mem[labels["SECRETS_COLLECTED"] + 1] = 0
    mem[labels["SECRETS_X"] + 1] = 52
    mem[labels["SECRETS_ZONE"] + 1] = 3
    mem[labels["SECRETS_CHANNEL"] + 1] = 3

    mem[labels["SECRETS_PLAT_IDX"] + 2] = 1
    mem[labels["SECRETS_REL_X"] + 2] = 8
    mem[labels["SECRETS_ACTIVE"] + 2] = 1
    mem[labels["SECRETS_COLLECTED"] + 2] = 0
    mem[labels["SECRETS_X"] + 2] = 108
    mem[labels["SECRETS_ZONE"] + 2] = 4
    mem[labels["SECRETS_CHANNEL"] + 2] = 3

    # Step 1: Platform 0 moves right from 40 to 41 (+1)
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x + 0] == 41
    assert mem[labels["SECRETS_X"] + 0] == 49
    assert mem[labels["SECRETS_X"] + 1] == 53
    assert mem[labels["SECRETS_X"] + 2] == 108

    # Active Secret 0 DLI HPOSM0..M3 in zone 2 updated to 48 + 49 + 2*m
    for m in range(4):
        for slot in dli_secret_hpos_slots(labels, 2, m):
            assert mem[slot] == 48 + 49 + 2 * m

    # Step 2: Reverse platform 0 to move left (-1) from 41 to 40
    mem[labels["PLAT_DIR"] + 0] = 1
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x + 0] == 40
    assert mem[labels["SECRETS_X"] + 0] == 48
    assert mem[labels["SECRETS_X"] + 1] == 52
    assert mem[labels["SECRETS_X"] + 2] == 108

    for m in range(4):
        for slot in dli_secret_hpos_slots(labels, 2, m):
            assert mem[slot] == 48 + 48 + 2 * m


def test_enemy_carrier_on_moving_platform():
    """Verify enemies on a moving platform shift x, min_x, max_x, and DLI HPOS with the platform."""
    mpu, mem, labels = _setup_mpu_and_scene(0)
    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF
    mem[labels["SECRETS_COUNT"]] = 0

    # Setup 2 platforms: platform 0 moving right, platform 1 stationary
    mem[labels["PLAT_COUNT"]] = 2
    mem[ptr_x + 0] = 40
    mem[ptr_w + 0] = 32
    mem[labels["PLAT_MOVEMENT"] + 0] = 2  # right-left
    mem[labels["PLAT_DIR"] + 0] = 0       # moving right
    mem[labels["PLAT_SPEED"] + 0] = 0     # fast (1 px/frame)
    mem[labels["PLAT_SPEED_TIMER"] + 0] = 0
    mem[labels["PLAT_PAUSE_TIMER"] + 0] = 0

    mem[ptr_x + 1] = 100
    mem[ptr_w + 1] = 32
    mem[labels["PLAT_MOVEMENT"] + 1] = 0  # stationary

    # Setup 2 enemies:
    # Enemy 0 on moving platform 0 (bounds [40, 64], x=50, zone=2, channel=0)
    # Enemy 1 on stationary platform 1 (bounds [100, 124], x=110, zone=3, channel=1)
    mem[labels["ENEMIES_COUNT"]] = 2

    mem[labels["ENEMIES_PLAT_IDX"] + 0] = 0
    mem[labels["ENEMIES_ACTIVE"] + 0] = 1
    mem[labels["ENEMIES_X"] + 0] = 50
    mem[labels["ENEMIES_MIN_X"] + 0] = 40
    mem[labels["ENEMIES_MAX_X"] + 0] = 64
    mem[labels["ENEMIES_ZONE"] + 0] = 2
    mem[labels["ENEMIES_CHANNEL"] + 0] = 0

    mem[labels["ENEMIES_PLAT_IDX"] + 1] = 1
    mem[labels["ENEMIES_ACTIVE"] + 1] = 1
    mem[labels["ENEMIES_X"] + 1] = 110
    mem[labels["ENEMIES_MIN_X"] + 1] = 100
    mem[labels["ENEMIES_MAX_X"] + 1] = 124
    mem[labels["ENEMIES_ZONE"] + 1] = 3
    mem[labels["ENEMIES_CHANNEL"] + 1] = 1

    # Step 1: Platform 0 moves right from 40 to 41 (+1)
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x + 0] == 41
    assert mem[labels["ENEMIES_X"] + 0] == 51
    assert mem[labels["ENEMIES_MIN_X"] + 0] == 41
    assert mem[labels["ENEMIES_MAX_X"] + 0] == 65
    for slot in dli_enemy_hpos_slots(labels, 2, 0):
        assert mem[slot] == 48 + 51

    # Enemy 1 on platform 1 is unchanged
    assert mem[labels["ENEMIES_X"] + 1] == 110
    assert mem[labels["ENEMIES_MIN_X"] + 1] == 100
    assert mem[labels["ENEMIES_MAX_X"] + 1] == 124

    # Step 2: Reverse platform 0 to move left (-1) from 41 to 40
    mem[labels["PLAT_DIR"] + 0] = 1
    run_subroutine(mpu, labels["PLATFORMS_UPDATE"])
    assert mem[ptr_x + 0] == 40
    assert mem[labels["ENEMIES_X"] + 0] == 50
    assert mem[labels["ENEMIES_MIN_X"] + 0] == 40
    assert mem[labels["ENEMIES_MAX_X"] + 0] == 64
    for slot in dli_enemy_hpos_slots(labels, 2, 0):
        assert mem[slot] == 48 + 50


def test_hero_death_and_respawn_keeps_secrets_and_enemies_bound_to_moving_platforms():
    """Verify Hero respawn (player_init -> platforms_init) never desynchronizes objects on moving platforms."""
    # Find a scene with at least one secret on a moving platform
    target_scene_id = None
    for scene_id, scene_file in enumerate(scene_files()):
        plats = scene_platforms(scene_id)
        for sec in scene_objects(scene_file, "secret"):
            p_idx = scene_platform_index(scene_id, sec["platform_id"])
            if plats[p_idx].get("movement", "none") not in (None, "none"):
                target_scene_id = scene_id
                break
        if target_scene_id is not None:
            break
    assert target_scene_id is not None, "Expected at least one scene with a secret on a moving platform"

    scene_file = scene_files()[target_scene_id]
    plats = scene_platforms(target_scene_id)
    secrets = scene_objects(scene_file, "secret")

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize scene in the exact order of game_init
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = target_scene_id
    mpu.a = target_scene_id
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = target_scene_id
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = target_scene_id
    run_subroutine(mpu, labels["ENEMIES_INIT"])
    mpu.a = target_scene_id
    run_subroutine(mpu, labels["PLAYER_INIT"])

    ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)

    # Advance moving platforms for 30 frames so platforms and their secrets move away from init_x
    for _ in range(30):
        run_subroutine(mpu, labels["PLATFORMS_UPDATE"])

    # Verify every secret's X is still equal to plat_x[p] + rel_x after 30 frames of movement
    for i, sec in enumerate(secrets):
        p_idx = mem[labels["SECRETS_PLAT_IDX"] + i]
        rel_x = mem[labels["SECRETS_REL_X"] + i]
        assert mem[labels["SECRETS_X"] + i] == mem[ptr_x + p_idx] + rel_x

    # Now simulate Hero death completion (@respawn -> jsr player_init)
    mpu.a = target_scene_id
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # After respawn, platforms reset to init_x AND every secret on a moving platform must match plat_x[p] + rel_x!
    for i, sec in enumerate(secrets):
        p_idx = mem[labels["SECRETS_PLAT_IDX"] + i]
        rel_x = mem[labels["SECRETS_REL_X"] + i]
        expected_x = plats[p_idx]["x"] + rel_x
        assert mem[ptr_x + p_idx] == plats[p_idx]["x"]
        assert mem[labels["SECRETS_X"] + i] == expected_x, (
            f"Secret {i} desynchronized from moving platform {p_idx} after Hero respawn: "
            f"got {mem[labels['SECRETS_X'] + i]}, expected {expected_x}"
        )
        if mem[labels["SECRETS_ACTIVE"] + i] and mem[labels["SECRETS_CHANNEL"] + i] == 3:
            zone = mem[labels["SECRETS_ZONE"] + i]
            for m in range(4):
                for slot in dli_secret_hpos_slots(labels, zone, m):
                    assert mem[slot] == 48 + expected_x + 2 * m
