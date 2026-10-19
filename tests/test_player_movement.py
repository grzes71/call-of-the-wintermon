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

    # Hero respawned at start coordinates of Scene 0 (x=96, y=68)
    assert mem[labels["PLAYER_X"]] == 96
    assert mem[labels["PLAYER_Y"]] == 68
    assert mem[labels["PLAYER_STATE"]] == 0  # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0


def test_player_fall_death_game_over_when_zero_lives():
    """Verify falling off bottom with 1 life remaining triggers Game Over with GAME_FAILED status."""
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

    # 1 frame: y reaches 94 -> Death!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Lives decremented to 0
    assert mem[labels["PLAYER_LIVES"]] == 0

    # All 3 hearts turned off
    status_vram = labels["STATUS_LINE_VRAM"]
    assert mem[status_vram + 0] == 0
    assert mem[status_vram + 1] == 0
    assert mem[status_vram + 2] == 0

    # Game over defeat status set
    assert mem[labels["GAME_RESULT"]] == 1      # GAME_FAILED
    assert mem[labels["GAME_STATE"]] == 3       # STATE_OVER
