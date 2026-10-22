"""Automated py65 integration test suite for Atari 8-bit Player 0 (Hero) spawn and movement with inertia.

Validates:
1. player_init initializes Player 0 position, PMG memory, hardware registers and standing frame.
2. player_update accelerates gradually when starting movement (speed increases by $10 up to $80).
3. player_update decelerates gradually when releasing joystick (coasting down to $00 before full stop).
4. player_update performs active braking when reversing direction.
5. Boundaries: player_x clamps at PLAYER_MIN_X (0) and PLAYER_MAX_X (152), zeroing speed.
"""

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def test_player_init_scene0():
    """Verify player_init correctly initializes Player 0 state, inertia vars and PMG for Scene 0."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize Player 0 on Scene 0 (Forest: start_x=96, start_y=68)
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # 1. Canvas position and PMG scanline
    assert mem[labels["PLAYER_X"]] == 96
    # pmg_y = 68 * 2 + 52 = 188
    assert mem[labels["PLAYER_PMG_Y"]] == 188

    # 2. State & Direction: facing right (0), idle (0), frame 0
    assert mem[labels["PLAYER_DIR"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 4
    assert mem[labels["PLAYER_X_SUB"]] == 0
    assert mem[labels["PLAYER_SPEED"]] == 0

    # 3. Hardware registers
    expected_color_0 = mem[labels["SCENE_PLAYER_COLOR"]]
    assert mem[labels["HPOSP0"]] == 48 + 96  # 144 ($90)
    assert mem[labels["SIZEP0"]] == 0        # 1x normal width
    assert mem[labels["COLPM0"]] == expected_color_0
    assert mem[labels["PCOLR0"]] == expected_color_0
    assert mem[labels["PLAYER_COLOR"]] == expected_color_0


    # 4. PMG memory verification
    # Scanlines before 188 must be $00
    pmg_p0 = labels["PMG_PLAYER0"]
    for y in range(0, 188):
        assert mem[pmg_p0 + y] == 0x00, f"Scanline {y} before player must be 0"

    # Scanlines 188..207 must match player_anim_right_frame_0
    right_f0_addr = labels["PLAYER_ANIM_RIGHT_FRAME_0"]
    for i in range(20):
        expected_byte = mem[right_f0_addr + i]
        actual_byte = mem[pmg_p0 + 188 + i]
        assert actual_byte == expected_byte, f"Byte {i} at scanline {188+i} mismatch: {actual_byte:#04x} vs {expected_byte:#04x}"

    # Scanlines after 207 must be $00
    for y in range(208, 256):
        assert mem[pmg_p0 + y] == 0x00, f"Scanline {y} after player must be 0"


def test_player_init_scene1_custom_color():
    """Verify player_init initializes Player 0 on Scene 1 with scene-specific player color."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    scene0_color = mem[labels["SCENE_PLAYER_COLOR"]]
    scene1_color = mem[labels["SCENE_PLAYER_COLOR"] + 1]

    # Verify that Scene 1 has a distinct color configured compared to Scene 0
    assert scene1_color != scene0_color

    # Initialize Player 0 on Scene 1 (Forest Castle: start_x=90, start_y=68)
    mem[labels["ACTIVE_SCENE_ID"]] = 1
    mpu.a = 1
    run_subroutine(mpu, labels["PLAYER_INIT"])

    assert mem[labels["PLAYER_X"]] == 90
    assert mem[labels["COLPM0"]] == scene1_color
    assert mem[labels["PCOLR0"]] == scene1_color
    assert mem[labels["PLAYER_COLOR"]] == scene1_color

    # Verify platform tables for Scene 1 (14 platforms vs 11 on Scene 0)
    expected_plat_count = mem[labels["SCENE_PLAT_COUNT"] + 1]
    expected_ptr_x = mem[labels["SCENE_PLAT_X_LO"] + 1] | (mem[labels["SCENE_PLAT_X_HI"] + 1] << 8)
    expected_ptr_y = mem[labels["SCENE_PLAT_Y_LO"] + 1] | (mem[labels["SCENE_PLAT_Y_HI"] + 1] << 8)
    expected_ptr_w = mem[labels["SCENE_PLAT_W_LO"] + 1] | (mem[labels["SCENE_PLAT_W_HI"] + 1] << 8)

    actual_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    actual_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    actual_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    assert mem[labels["ZP_PLAT_COUNT"]] == expected_plat_count
    assert expected_plat_count == 14
    assert actual_ptr_x == expected_ptr_x
    assert actual_ptr_y == expected_ptr_y
    assert actual_ptr_w == expected_ptr_w




def test_player_walk_right_acceleration():
    """Verify player accelerates gradually when moving right up to max speed ($80)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_SPEED"]] == 0

    # STICK0 bit 3 is 0 (right pressed): %00000111 = 0x07
    mem[labels["STICK0"]] = 0x07

    # Frame 1: speed increases by $10 to $10, x_sub = $10 (no step yet)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x10
    assert mem[labels["PLAYER_X_SUB"]] == 0x10
    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_STATE"]] == 1     # Walk
    assert mem[labels["PLAYER_DIR"]] == 0       # Right

    # Frame 2: speed = $20, x_sub = $30
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x20
    assert mem[labels["PLAYER_X_SUB"]] == 0x30
    assert mem[labels["PLAYER_X"]] == 96

    # Frame 3: speed = $30, x_sub = $60
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x30
    assert mem[labels["PLAYER_X_SUB"]] == 0x60
    assert mem[labels["PLAYER_X"]] == 96

    # Frame 4: speed = $40, x_sub = $A0, animation frame advances to 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x40
    assert mem[labels["PLAYER_X_SUB"]] == 0xA0
    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1

    # Frame 5: speed = $50, x_sub = $F0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x50
    assert mem[labels["PLAYER_X_SUB"]] == 0xF0
    assert mem[labels["PLAYER_X"]] == 96

    # Frame 6: speed = $60, x_sub = $F0 + $60 = $50 (carry!), steps to x=97!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x60
    assert mem[labels["PLAYER_X_SUB"]] == 0x50
    assert mem[labels["PLAYER_X"]] == 97
    assert mem[labels["HPOSP0"]] == 48 + 97

    # Frame 7: speed = $70, x_sub = $C0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x70
    assert mem[labels["PLAYER_X_SUB"]] == 0xC0
    assert mem[labels["PLAYER_X"]] == 97

    # Frame 8: speed reaches max $80, x_sub = $C0 + $80 = $40 (carry!), steps to x=98!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0x40
    assert mem[labels["PLAYER_X"]] == 98

    # Frame 9: speed stays at $80, x_sub = $40 + $80 = $C0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0xC0
    assert mem[labels["PLAYER_X"]] == 98

    # Frame 10: speed stays at $80, x_sub = $C0 + $80 = $40 (carry!), steps to x=99!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0x40
    assert mem[labels["PLAYER_X"]] == 99


def test_player_deceleration_and_inertia_stop():
    """Verify player gradually decelerates before stopping completely when joystick is released."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Accelerate to max speed (8 frames right)
    mem[labels["STICK0"]] = 0x07
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X"]] == 98

    # Release joystick (STICK0 = 0x0F)
    mem[labels["STICK0"]] = 0x0F

    # Deceleration sequence: speed decreases by $10 each frame: $70, $60, $50, $40, $30, $20, $10, $00
    expected_speeds = [0x70, 0x60, 0x50, 0x40, 0x30, 0x20, 0x10, 0x00]
    for i, exp_speed in enumerate(expected_speeds):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        assert mem[labels["PLAYER_SPEED"]] == exp_speed, f"Frame {i+1} expected speed {exp_speed:#04x}, got {mem[labels['PLAYER_SPEED']]:#04x}"
        if exp_speed > 0:
            assert mem[labels["PLAYER_STATE"]] == 1, "Player should remain in WALK state while decelerating"

    # Once speed is 0: player transitions to IDLE state with standing frame 0
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    assert mem[labels["PLAYER_X_SUB"]] == 0
    assert mem[labels["PLAYER_DIR"]] == 0  # Still facing right


def test_player_walk_left_and_reversal_braking():
    """Verify player accelerates left, and brakes before reversing when pushing right."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Accelerate left (STICK0 = 0x0B) for 8 frames
    mem[labels["STICK0"]] = 0x0B
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_DIR"]] == 1       # Left
    assert mem[labels["PLAYER_SPEED"]] == 0x80  # Max speed left
    assert mem[labels["PLAYER_X"]] == 94        # Moved left (96 -> 95 -> 94)

    # Now press RIGHT while moving full speed left -> Active turnaround braking!
    mem[labels["STICK0"]] = 0x07

    # Should brake down: $70, $60, $50, $40, $30, $20, $10, $00
    for frame in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        expected_speed = 0x70 - (frame * 0x10)
        assert mem[labels["PLAYER_SPEED"]] == expected_speed

    # After speed reached 0, direction reversed to RIGHT
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_DIR"]] == 0

    # Next frame with RIGHT still held: accelerates right!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_DIR"]] == 0
    assert mem[labels["PLAYER_SPEED"]] == 0x10


def test_player_bounds_clamping_with_inertia():
    """Verify player clamps at boundaries without speed overflow."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Set player at left boundary (x = 0) on platform 3 (plat_x=0, plat_w=32)
    mem[labels["PLAYER_X"]] = 0
    mem[labels["PLAYER_PLAT_IDX"]] = 3
    mem[labels["PLAYER_X_SUB"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0

    # Try moving left (STICK0 = 0x0B)
    mem[labels["STICK0"]] = 0x0B
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == 0
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["HPOSP0"]] == 48

    # Set player at right boundary (x = 152) on platform 2 (plat_x=128, plat_w=32)
    mem[labels["PLAYER_X"]] = 152
    mem[labels["PLAYER_PLAT_IDX"]] = 2
    mem[labels["PLAYER_X_SUB"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0

    # Try moving right (STICK0 = 0x07)
    mem[labels["STICK0"]] = 0x07
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == 152
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["HPOSP0"]] == 48 + 152


def test_player_fall_off_platform_right_edge():
    """Verify player falls when moving > 50% past the right edge of a platform."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Platform 0 in Scene 0: plat_x = 48, plat_w = 96 -> right edge = 144
    # Player width = 8, midpoint = player_x + 4.
    # At player_x = 139: mid_x = 143 < 144 (still on platform)
    mem[labels["PLAYER_X"]] = 139
    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed right
    mem[labels["PLAYER_DIR"]] = 0       # Right
    mem[labels["STICK0"]] = 0x07        # Pressing right

    # Subpixel accumulator set so next frame steps to x = 140
    mem[labels["PLAYER_X_SUB"]] = 0x80
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # At player_x = 140: mid_x = 144 >= 144 (>= 50% past right edge!)
    assert mem[labels["PLAYER_X"]] == 140
    assert mem[labels["PLAYER_STATE"]] == 2     # PLAYER_STATE_FALL
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0xFF
    assert mem[labels["PLAYER_SPEED"]] == 0


def test_player_fall_off_platform_left_edge():
    """Verify player falls when moving > 50% past the left edge of a platform."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Platform 0 in Scene 0: plat_x = 48.
    # At player_x = 44: mid_x = 48 >= 48 (50% on, still standing)
    mem[labels["PLAYER_X"]] = 44
    mem[labels["PLAYER_PLAT_IDX"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed left
    mem[labels["PLAYER_DIR"]] = 1       # Left
    mem[labels["STICK0"]] = 0x0B        # Pressing left

    # Subpixel accumulator set so next frame steps left to x = 43
    mem[labels["PLAYER_X_SUB"]] = 0x80
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # At player_x = 43: mid_x = 47 < 48 (> 50% past left edge!)
    assert mem[labels["PLAYER_X"]] == 43
    assert mem[labels["PLAYER_STATE"]] == 2     # PLAYER_STATE_FALL
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0xFF
    assert mem[labels["PLAYER_SPEED"]] == 0


def test_player_fall_animation_frame_in_pmg():
    """Verify PMG buffer renders player_anim_fall_frame_0 while falling."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Put player in fall state at y = 68
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    run_subroutine(mpu, labels["PLAYER_RENDER_FRAME"])

    pmg_p0 = labels["PMG_PLAYER0"]
    fall_f0 = labels["PLAYER_ANIM_FALL_FRAME_0"]

    # Scanlines 188..207 must match player_anim_fall_frame_0
    for i in range(20):
        expected_byte = mem[fall_f0 + i]
        actual_byte = mem[pmg_p0 + 188 + i]
        assert actual_byte == expected_byte, f"Fall frame scanline {188+i} mismatch"


def test_player_fall_and_land_on_lower_platform():
    """Verify player falling downwards lands on a lower platform in its vertical path."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # In Scene 0: Platform 1 is at plat_x = 32, plat_y = 72, plat_w = 48 [32..80).
    # Starting at x = 60, y = 50 (above platform 1 at plat_y = 72).
    # feet_y will go 70 -> 71 -> 72.
    mem[labels["PLAYER_X"]] = 60
    mem[labels["PLAYER_Y"]] = 50
    mem[labels["PLAYER_PMG_Y"]] = 50 * 2 + 52
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Frame 1: y increases to 51, feet = 71 (not landed)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == 51
    assert mem[labels["PLAYER_STATE"]] == 2

    # Frame 2: y increases to 52, feet = 72. Platform 1 has plat_y = 72, plat_x = 32, plat_w = 48.
    # mid_x = 64 is within [32..80)! Lands on platform 1!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == 52
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == 1  # Platform 1


def test_player_fall_death_and_respawn_with_lives_decrement():
    """Verify falling off bottom of scene clips at status line, decrements lives, and respawns."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Position player falling below all platforms (x = 150 has no platform at y=88 in Scene 0)
    # Set y = 80 (pmg_y = 212, feet = 231 > 224 -> sinking behind status line)
    mem[labels["PLAYER_X"]] = 150
    mem[labels["PLAYER_Y"]] = 80
    mem[labels["PLAYER_PMG_Y"]] = 80 * 2 + 52  # 212
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Advance fall frames: y = 81..93
    # During this time, PMG scanlines >= 224 MUST be 0 (clipped from status line)
    pmg_p0 = labels["PMG_PLAYER0"]
    for y_cur in range(81, 94):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        assert mem[labels["PLAYER_Y"]] == y_cur
        assert mem[labels["PLAYER_STATE"]] == 2  # Still falling
        # Verify clipping invariant: scanlines 224..255 must be strictly 0
        for sl in range(224, 256):
            assert mem[pmg_p0 + sl] == 0, f"PMG scanline {sl} on status line must be 0!"

    # Frame at y = 94: triggers PLAYER_HANDLE_DEATH
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Lives decremented from 3 to 2
    assert mem[labels["PLAYER_LIVES"]] == 2
    # Status line updated: 3rd heart glyph turned off
    status_vram = labels["STATUS_LINE_VRAM"]
    assert mem[status_vram + 0] == 64  # Heart 1
    assert mem[status_vram + 1] == 64  # Heart 2
    assert mem[status_vram + 2] == 0   # Space (lost life)

    # Hero enters EMERGE state starting below status line edge (pmg_y = 224)
    assert mem[labels["PLAYER_STATE"]] == 5  # PLAYER_STATE_EMERGE
    assert mem[labels["PLAYER_PMG_Y"]] == 224

    # Advance 36 frames of emergence: moves up 1 scanline per frame to lowest platform height (pmg_y = 188)
    fall_f0 = labels["PLAYER_ANIM_FALL_FRAME_0"]
    for i in range(1, 37):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        expected_pmg_y = 224 - i
        assert mem[labels["PLAYER_PMG_Y"]] == expected_pmg_y
        if i < 36:
            assert mem[labels["PLAYER_STATE"]] == 5  # Still emerging
            # Verify fall frame top line is at expected_pmg_y
            assert mem[pmg_p0 + expected_pmg_y] == mem[fall_f0]
        else:
            # On 36th frame: reached target (188), transitioned to PLAYER_STATE_DEATH
            assert mem[labels["PLAYER_STATE"]] == 4  # PLAYER_STATE_DEATH
            assert mem[labels["PLAYER_Y"]] == 68
            assert mem[labels["PLAYER_PMG_Y"]] == 188
            death_f0 = labels["PLAYER_ANIM_DEATH_FRAME_0"]
            assert mem[pmg_p0 + 188] == mem[death_f0]

    # Advance through death sequence: 10 + 10 + 60 = 80 frames
    for _ in range(80):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Hero respawned at start coordinates of Scene 0 (x=96, y=68)
    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_Y"]] == 68
    assert mem[labels["PLAYER_STATE"]] == 0  # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0


def test_player_fall_death_game_over_when_zero_lives():
    """Verify falling off bottom with 1 life remaining triggers Game Over with GAME_FAILED status after emergence and death animation."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Start with 1 life
    mem[labels["PLAYER_LIVES"]] = 1
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Put player right at death threshold
    mem[labels["PLAYER_X"]] = 150
    mem[labels["PLAYER_Y"]] = 93
    mem[labels["PLAYER_PMG_Y"]] = (93 * 2 + 52) & 0xFF
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # 1 frame: y reaches 94 -> Emergence triggered!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Lives decremented to 0
    assert mem[labels["PLAYER_LIVES"]] == 0

    # All 3 hearts turned off
    status_vram = labels["STATUS_LINE_VRAM"]
    assert mem[status_vram + 0] == 0
    assert mem[status_vram + 1] == 0
    assert mem[status_vram + 2] == 0

    # Player is in EMERGE state (5)
    assert mem[labels["PLAYER_STATE"]] == 5

    # 36 frames of emergence -> transitions to DEATH state (4) at lowest platform height
    for _ in range(36):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 4
    assert mem[labels["PLAYER_Y"]] == 68
    assert mem[labels["PLAYER_PMG_Y"]] == 188


    # Advance death sequence (80 frames)
    for _ in range(80):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Game over defeat status set
    assert mem[labels["GAME_RESULT"]] == 1      # GAME_FAILED
    assert mem[labels["GAME_STATE"]] == 3       # STATE_OVER


def test_player_death_animation_sequence():
    """Verify full 3-frame death animation (frames 0, 1) and 1-second hold on frame 2 before respawn."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["PLAYER_LIVES"]] = 2
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Trigger death explicitly
    run_subroutine(mpu, labels["PLAYER_HANDLE_DEATH"])

    # Lives decremented to 1
    assert mem[labels["PLAYER_LIVES"]] == 1
    assert mem[labels["PLAYER_STATE"]] == 4     # PLAYER_STATE_DEATH
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0 # Frame 0
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 10

    # Verify frame 0 bitmap matches player_anim_death_frame_0 in PMG
    pmg_p0 = labels["PMG_PLAYER0"]
    pmg_y = mem[labels["PLAYER_PMG_Y"]]
    death_f0 = labels["PLAYER_ANIM_DEATH_FRAME_0"]
    assert mem[pmg_p0 + pmg_y] == mem[death_f0]

    # Advance 10 frames: should transition to frame 1 with timer 10
    for _ in range(10):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_STATE"]] == 4
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 10

    # Verify frame 1 bitmap matches in PMG
    death_f1 = labels["PLAYER_ANIM_DEATH_FRAME_1"]
    assert mem[pmg_p0 + pmg_y] == mem[death_f1]

    # Advance 10 frames: should transition to frame 2 with timer 60 (10 dur + 50 hold = 60)
    for _ in range(10):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_STATE"]] == 4
    assert mem[labels["PLAYER_FRAME_IDX"]] == 2
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 60

    # Verify frame 2 bitmap matches in PMG
    death_f2 = labels["PLAYER_ANIM_DEATH_FRAME_2"]
    assert mem[pmg_p0 + pmg_y] == mem[death_f2]

    # Advance 59 frames of hold: should still be in death state holding frame 2!
    for _ in range(59):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_STATE"]] == 4
    assert mem[labels["PLAYER_FRAME_IDX"]] == 2
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 1

    # 60th frame (80th frame overall): hold expires, hero respawns!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_STATE"]] == 0     # PLAYER_STATE_IDLE
    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_Y"]] == 68
    assert mem[labels["PLAYER_LIVES"]] == 1     # Still 1 life



def test_player_jump_up_vertical():
    """Verify neutral joystick + Fire triggers vertical jump, peaks, and lands back on same platform."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero starts at x=96, y=68 on Platform 0 (plat_y=88)
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0

    # Release fire first, then press Fire with neutral joystick (STICK0 = 0x0F)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x0F                # Neutral joystick

    # Frame 1: Jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 0 # JUMP_TYPE_UP
    assert mem[labels["PLAYER_JUMP_LEN"]] == 30
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0 # Phase 0 (Frame 0: fast ascent)
    assert mem[labels["PLAYER_X"]] == 96        # No horizontal motion
    assert mem[labels["PLAYER_Y"]] == 66        # First step: dy = -2

    # Step through remaining frames of the ascent (steps 1..10)
    # Fire can now be released or held:
    mem[labels["STRIG0"]] = 1
    for _ in range(10):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        assert mem[labels["PLAYER_STATE"]] == 3 # Still in jump
        assert mem[labels["PLAYER_X"]] == 96    # Strictly vertical

    # At step 10 (11 steps total, 0..10): apex reached (total dy = -18 -> y = 68 - 18 = 50)
    assert mem[labels["PLAYER_Y"]] == 50

    # Step 11: apex frame (dy = 0 -> y remains 50)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3
    assert mem[labels["PLAYER_Y"]] == 50

    # Steps 12..28: descent at 1 px/frame (17 steps: y goes 51 to 67)
    # Verify vertical motion is exactly 1 px per frame and renders fall animation frame
    pmg_p0 = labels["PMG_PLAYER0"]
    fall_frame_addr = labels["PLAYER_ANIM_FALL_FRAME_0"]
    expected_y = 50
    for _ in range(17):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        expected_y += 1
        assert mem[labels["PLAYER_STATE"]] == 3
        assert mem[labels["PLAYER_X"]] == 96
        assert mem[labels["PLAYER_Y"]] == expected_y
        pmg_y = mem[labels["PLAYER_PMG_Y"]]
        assert mem[pmg_p0 + pmg_y] == mem[fall_frame_addr]

    # Step 29: Final descent step lands back on Platform 0!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0  # Landed on Platform 0
    assert mem[labels["PLAYER_Y"]] == 68        # Exact return to starting Y
    assert mem[labels["PLAYER_X"]] == 96


def test_player_jump_short_crosses_gap():
    """Verify Fire + Left/Right triggers short jump (~18px) to clear a 16px gap between platforms."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Position player at x=33, y=68 (standing on Platform 10 at y=88: plat_x=7..39)
    # Right of Platform 10 is a gap (x=39..48), then Platform 0 begins at x=48..144
    mem[labels["PLAYER_X"]] = 33
    mem[labels["PLAYER_Y"]] = 68
    mem[labels["PLAYER_PLAT_IDX"]] = 10         # On platform 10

    # Ensure open sky above gap by moving Platform 1 out of the way
    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    mem[plat_ptr_y + 1] = 0

    # Release fire, then press Fire + Right (STICK0 bit 3=0 -> 0x07)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x07                # Right active

    # Frame 1: Jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 1 # JUMP_TYPE_SHORT
    assert mem[labels["PLAYER_JUMP_LEN"]] == 18
    assert mem[labels["PLAYER_DIR"]] == 0       # Facing Right
    assert mem[labels["PLAYER_X"]] == 34        # dx = 1

    # Advance through remaining steps (17 more steps)
    mem[labels["STRIG0"]] = 1
    for _ in range(17):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # At the end of 18 steps: total dx = 18 px (x = 33 + 18 = 51)
    # At x=51, Hero is on Platform 0 (x=48..144, y=88) across the gap!
    assert mem[labels["PLAYER_X"]] == 51
    assert mem[labels["PLAYER_Y"]] == 68
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed on platform across gap!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0  # Platform 0


def test_player_jump_long_reaches_higher_platform():
    """Verify Fire + Up+Left triggers high jump (apex 20 lines) to land on platform 16 lines above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on lower platform 0 (plat_y=88) at x=76, y=68
    # Higher platform is Platform 1 at plat_x=32..80, plat_y=72 (16 lines higher)
    mem[labels["PLAYER_X"]] = 76
    mem[labels["PLAYER_Y"]] = 68
    mem[labels["PLAYER_PLAT_IDX"]] = 0

    # Release fire, then press Fire + Up+Left (STICK0 bit 0=0 up, bit 2=0 left -> 0x0A)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x0A                # Up+Left active

    # Frame 1: Long jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 2 # JUMP_TYPE_LONG
    assert mem[labels["PLAYER_JUMP_LEN"]] == 22
    assert mem[labels["PLAYER_DIR"]] == 1       # Facing Left

    # Step through frames until landing on the higher platform at plat_y=72 (y=52)
    mem[labels["STRIG0"]] = 1
    landed = False
    for step in range(2, 23):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        if mem[labels["PLAYER_STATE"]] == 0:    # IDLE -> Landed!
            landed = True
            break

    assert landed, "Hero must land on higher platform 1"
    assert mem[labels["PLAYER_PLAT_IDX"]] == 1  # Landed on Platform 1!
    assert mem[labels["PLAYER_Y"]] == 52        # 72 - 20 = 52 (exact platform surface!)
    # Horizontal displacement must be <= 8px:
    dx_traveled = 76 - mem[labels["PLAYER_X"]]
    assert 0 < dx_traveled <= 8, f"Horizontal displacement ({dx_traveled}) must be <= 8px"


def test_player_jump_long_does_not_hit_ceiling_two_tiers_above():
    """Verify long jump to a platform 16 lines above does not trigger ceiling bounce when a ceiling is 2 tiers above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on lower platform 0 (plat_y=88) at x=76, y=68
    # Target platform: Platform 1 at plat_x=32..80, plat_y=72 (surface at y=52)
    # Put a ceiling platform at plat_y=56 (thickness 4: lines 56..59, bottom=60, 32px above lower platform)
    mem[labels["PLAYER_X"]] = 76
    mem[labels["PLAYER_Y"]] = 68
    mem[labels["PLAYER_PLAT_IDX"]] = 0

    # Overwrite Platform 7 in scene data to be a ceiling directly above the jump path at y=56 (bottom=60)
    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[plat_ptr_x + 7] = 60
    mem[plat_ptr_w + 7] = 30
    mem[plat_ptr_y + 7] = 56  # Bottom is at 56 + 4 = 60

    # Trigger long jump Up+Left
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0A

    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3  # PLAYER_STATE_JUMP

    mem[labels["STRIG0"]] = 1
    landed = False
    for _ in range(21):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        # Must NEVER bounce into fall state during this jump
        assert mem[labels["PLAYER_STATE"]] != 2, "Must not bounce off ceiling at y=56!"
        if mem[labels["PLAYER_STATE"]] == 0:
            landed = True
            break

    assert landed, "Hero must land on target platform"
    assert mem[labels["PLAYER_Y"]] == 52


def test_player_jump_blocked_when_platform_directly_overhead():
    """Verify Hero standing on a platform with another platform directly overhead (16px above) cannot jump."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on lower Platform 0 (plat_y=88) at x=60 (standing under Platform 1 at plat_x=32..80, plat_y=72)
    mem[labels["PLAYER_X"]] = 60
    mem[labels["PLAYER_Y"]] = 68
    mem[labels["PLAYER_PLAT_IDX"]] = 0

    # Fire + neutral (JUMP_UP)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F

    # Jump must be blocked! Hero remains standing in IDLE on Platform 0 at y=68
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0      # PLAYER_STATE_IDLE (not JUMP, not FALL!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0   # Still securely on Platform 0
    assert mem[labels["PLAYER_Y"]] == 68         # Never moved down or penetrated platform

    # Re-release fire and try Fire + Right (short jump attempt under ceiling)
    mem[labels["STRIG0"]] = 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x07                 # Right

    # Jump must still be blocked!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] != 3      # Not jumping
    assert mem[labels["PLAYER_STATE"]] != 2      # Not falling through platform!
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0   # Still on Platform 0
    assert mem[labels["PLAYER_Y"]] == 68



def test_player_jump_ceiling_collision_bounces_to_fall():
    """Verify Hero jumping into a platform ceiling from below bounces off and falls straight down."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # In Scene 0: Platform 4 is at plat_x=1..17, plat_y=40 (thickness 4: lines 40..43, bottom=44).
    # Position Hero directly under Platform 4 at x=8, y=46 (head at 46, below bottom 44).
    mem[labels["PLAYER_X"]] = 8
    mem[labels["PLAYER_Y"]] = 46
    mem[labels["PLAYER_PLAT_IDX"]] = 0          # On some platform below

    # Release fire, then press Fire + Right (JUMP_SHORT)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x07                # Right active -> JUMP_TYPE_SHORT

    # Frame 1: Jump triggers, dy = -2, dx = 1, player_y goes 46 -> 44 (hits bottom at 44!)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Hero bumps ceiling: bounces immediately into PLAYER_STATE_FALL!
    assert mem[labels["PLAYER_STATE"]] == 2     # PLAYER_STATE_FALL
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0xFF
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0 # Fall animation frame
    assert mem[labels["PLAYER_SPEED"]] == 0     # Speed 0 (falls vertically)

    # Next frame: regular fall update drops by 1 line
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 2     # Still falling
    assert mem[labels["PLAYER_Y"]] == 45        # Dropping down


def test_player_jump_up_does_not_hit_ceiling_two_tiers_above():
    """Verify vertical jump (JUMP_UP) reaches full apex and is not clipped by a platform two tiers above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on lower Platform 0 (plat_y=88) at x=76, y=68
    mem[labels["PLAYER_X"]] = 76
    mem[labels["PLAYER_Y"]] = 68
    mem[labels["PLAYER_PLAT_IDX"]] = 0

    # Overwrite Platform 7 in scene data to be directly above Hero at y=56 (bottom=60, 32px above floor)
    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    mem[plat_ptr_x + 7] = 60
    mem[plat_ptr_w + 7] = 30
    mem[plat_ptr_y + 7] = 56

    # Trigger vertical jump (Fire + neutral)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F                # Neutral -> JUMP_TYPE_UP

    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP

    mem[labels["STRIG0"]] = 1
    landed = False
    for _ in range(29):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        # Must NEVER bounce into fall state during vertical jump under platform at y=56
        assert mem[labels["PLAYER_STATE"]] != 2, "Must not bounce off ceiling at y=56 during vertical jump!"
        if mem[labels["PLAYER_STATE"]] == 0:
            landed = True
            break

    assert landed, "Hero must land back on starting platform"
    assert mem[labels["PLAYER_Y"]] == 68


def test_player_jump_animation_frames_in_pmg():
    """Verify jump animation frames 0, 1, 2 are rendered into PMG memory during jump phases."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Start jump-right from x=96, y=68
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F                # Neutral -> JUMP_UP (facing Right)

    # Frame 1: Phase 0 (Frame 0)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    pmg_p0 = labels["PMG_PLAYER0"]
    frame0_addr = labels["PLAYER_ANIM_JUMP_RIGHT_FRAME_0"]
    pmg_y = mem[labels["PLAYER_PMG_Y"]]
    # Compare first scanline
    assert mem[pmg_p0 + pmg_y] == mem[frame0_addr]

    # Advance to Phase 1 (Frame 1) at step 8 (steps 8..11: apex)
    mem[labels["STRIG0"]] = 1
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1
    frame1_addr = labels["PLAYER_ANIM_JUMP_RIGHT_FRAME_1"]
    pmg_y = mem[labels["PLAYER_PMG_Y"]]
    assert mem[pmg_p0 + pmg_y + 2] == mem[frame1_addr + 2]

    # Advance to descent at step 13 (post-incremented step >= 13):
    # In vertical jump, descent uses fall animation frame 0!
    for _ in range(5):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    fall_frame_addr = labels["PLAYER_ANIM_FALL_FRAME_0"]
    pmg_y = mem[labels["PLAYER_PMG_Y"]]
    assert mem[pmg_p0 + pmg_y] == mem[fall_frame_addr]


def test_player_jump_on_row_1_full_height():
    """Verify Hero jumping from Row 1 (y=24) reaches full apex without being clamped at y=0."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Platform 6 ("platform-010") in Scene 0 is at x=96, y=24, w=32. Standing head is at player_y = 4
    mem[labels["PLAYER_X"]] = 100
    mem[labels["PLAYER_Y"]] = 4
    mem[labels["PLAYER_PLAT_IDX"]] = 6

    # Trigger vertical jump (apex 18 lines)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F

    # Step 1: y = 2
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3
    assert mem[labels["PLAYER_Y"]] == 2

    # Step 2: y = 0
    mem[labels["STRIG0"]] = 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == 0

    # Step 3: y crosses into negative (-2 = 254 / 0xFE) - must NOT be clamped to 0!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == 254  # -2 in two's complement

    # Step through remaining steps to apex (step 11: total dy = -18, y = 4 - 18 = -14 = 242 / 0xF2)
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == 242  # -14 in two's complement (apex 18 lines reached!)

    # PMG scanline at apex: (-14 * 2) + 52 = 24 (valid PMG scanline)
    assert mem[labels["PLAYER_PMG_Y"]] == 24

    # Complete jump (1 apex step + 18 descent steps = 19 steps) and verify clean landing back on Platform 6 at y=4
    for _ in range(19):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == 6  # Platform 6
    assert mem[labels["PLAYER_Y"]] == 4         # Exactly returned to starting Y

