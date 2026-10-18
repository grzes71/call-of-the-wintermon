"""Automated py65 integration test suite for Atari 8-bit Player 0 (Hero) spawn and movement.

Validates:
1. player_init initializes Player 0 position, PMG memory, hardware registers and standing frame.
2. player_update polls STICK0 and moves right when pushed right, advancing walk animation.
3. player_update moves left when pushed left, advancing walk animation with left frames.
4. player_update returns to standing frame (frame 0) when joystick is idle, preserving direction.
5. Boundaries: player_x clamps at PLAYER_MIN_X (0) and PLAYER_MAX_X (152).
"""

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def test_player_init_scene0():
    """Verify player_init correctly initializes Player 0 state and PMG for Scene 0."""
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

    # 3. Hardware registers
    assert mem[labels["HPOSP0"]] == 48 + 96  # 144 ($90)
    assert mem[labels["SIZEP0"]] == 0        # 1x normal width
    assert mem[labels["COLPM0"]] == 0x98     # Cyan / blue hero color
    assert mem[labels["PCOLR0"]] == 0x98

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


def test_player_walk_right():
    """Verify player moves right at half speed (1 px every 2 frames)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    initial_x = mem[labels["PLAYER_X"]]
    assert initial_x == 96

    # STICK0 bit 3 is 0 (right pressed): %00000111 = 0x07
    mem[labels["STICK0"]] = 0x07

    # Frame 1: move right 1 pixel (sub_x=1), frame_timer decrements from 4 to 3
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 97
    assert mem[labels["HPOSP0"]] == 48 + 97
    assert mem[labels["PLAYER_DIR"]] == 0       # Right
    assert mem[labels["PLAYER_STATE"]] == 1     # Walk
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 3

    # Frame 2: sub_x=2 (even) -> no movement step (player_x stays 97)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 97
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 2

    # Frame 3: sub_x=3 (odd) -> move right 1 pixel (player_x=98)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 98
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 1

    # Frame 4: sub_x=4 (even) -> timer reaches 0, resets to 4, frame advances to 1!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 98
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 4
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1

    # PMG memory should now contain frame 1 of right animation
    pmg_p0 = labels["PMG_PLAYER0"]
    right_f1_addr = labels["PLAYER_ANIM_RIGHT_FRAME_1"]
    for i in range(20):
        assert mem[pmg_p0 + 188 + i] == mem[right_f1_addr + i]


def test_player_walk_left():
    """Verify player moves left when STICK0 has left bit active (bit 2 = 0)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # STICK0 bit 2 is 0 (left pressed): %00001011 = 0x0B
    mem[labels["STICK0"]] = 0x0B

    # Frame 1: move left 1 pixel (sub_x=1)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 95
    assert mem[labels["HPOSP0"]] == 48 + 95
    assert mem[labels["PLAYER_DIR"]] == 1       # Left
    assert mem[labels["PLAYER_STATE"]] == 1     # Walk

    # Frame 2: sub_x=2 (even) -> stays at 95
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_X"]] == 95

    # PMG memory should render using left animation frame
    pmg_p0 = labels["PMG_PLAYER0"]
    left_f0_addr = labels["PLAYER_ANIM_LEFT_FRAME_0"]
    for i in range(20):
        assert mem[pmg_p0 + 188 + i] == mem[left_f0_addr + i]


def test_player_idle_stops_animation_and_keeps_direction():
    """Verify releasing joystick stops walking animation and resets to standing frame."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Walk left for 4 frames so frame_idx = 1
    mem[labels["STICK0"]] = 0x0B
    for _ in range(4):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_DIR"]] == 1
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1

    # Release joystick (idle STICK0 = $0F)
    mem[labels["STICK0"]] = 0x0F
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Idle state: standing frame 0, but still facing left (dir = 1)!
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    assert mem[labels["PLAYER_DIR"]] == 1
    assert mem[labels["PLAYER_FRAME_TIMER"]] == 4
    assert mem[labels["PLAYER_SUB_X"]] == 0

    # PMG memory should render standing frame facing left
    pmg_p0 = labels["PMG_PLAYER0"]
    left_f0_addr = labels["PLAYER_ANIM_LEFT_FRAME_0"]
    for i in range(20):
        assert mem[pmg_p0 + 188 + i] == mem[left_f0_addr + i]


def test_player_bounds_clamping():
    """Verify player cannot move past horizontal screen bounds (0..152)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Set player_x = 1 and move left 3 times
    mem[labels["PLAYER_X"]] = 1
    mem[labels["STICK0"]] = 0x0B  # Left
    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 1: sub_x=1 -> x=0
    assert mem[labels["PLAYER_X"]] == 0
    assert mem[labels["HPOSP0"]] == 48

    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 2: sub_x=2 -> x=0
    assert mem[labels["PLAYER_X"]] == 0

    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 3: sub_x=3 -> clamped at 0
    assert mem[labels["PLAYER_X"]] == 0
    assert mem[labels["HPOSP0"]] == 48

    # Reset to idle then test right clamping
    mem[labels["STICK0"]] = 0x0F
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Set player_x = 151 and move right 3 times
    mem[labels["PLAYER_X"]] = 151
    mem[labels["STICK0"]] = 0x07  # Right
    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 1: sub_x=1 -> x=152
    assert mem[labels["PLAYER_X"]] == 152
    assert mem[labels["HPOSP0"]] == 48 + 152  # 200 ($C8)

    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 2: sub_x=2 -> x=152
    assert mem[labels["PLAYER_X"]] == 152

    run_subroutine(mpu, labels["PLAYER_UPDATE"])  # frame 3: sub_x=3 -> clamped at 152
    assert mem[labels["PLAYER_X"]] == 152
    assert mem[labels["HPOSP0"]] == 200

