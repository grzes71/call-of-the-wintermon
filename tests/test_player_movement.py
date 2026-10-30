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
from tests.scene_expectations import (
    free_x_on_row,
    jump_apex_dy,
    jump_dx_total,
    jump_dy_total,
    physics_fixture_scene,
    platform_supporting,
    player_spawn,
    player_spawn_pmg_y,
    scene_platform,
    scene_platform_count,
    scene_platform_index,
    scene_files,
    load_scene,
)

# ---------------------------------------------------------------------------
# Scene-derived fixtures (Rule 05): the physics scenarios run on the first scene in
# scenes/scenes.json that provides the platform roles they need (floor under the spawn, a row
# above it, a ceiling two rows above, both screen edges, the top row, a missile platform with a
# sprite platform to its left and a spare slot). Reordering scenes - or adding a new level as
# the first entry - therefore cannot break these tests. Engine constants (PLAYER_MAX_X,
# PLAYER_HPOS_OFFSET, JUMP_*_LEN, PLAYER_SPRITE_HEIGHT, ...) are read from the compiled labels.
# ---------------------------------------------------------------------------
SCENE0, PLAT_ROLES = physics_fixture_scene()
SPAWN0_X = player_spawn(SCENE0)["x"]
SPAWN0_Y = player_spawn(SCENE0)["y"]
SPAWN0_PMG_Y = player_spawn_pmg_y(SCENE0)

# The engine clips PMG writes at the status-line area (player.asm compares against 224).
PMG_STATUS_LINE_TOP = 216


def _role_index(role: str) -> int:
    """Engine platform index of a role resolved by physics_fixture_scene()."""
    return scene_platform_index(SCENE0, PLAT_ROLES[role]["id"])


# The platform the hero spawns on, plus the platforms the physics scenarios use.
PLAT_FLOOR = PLAT_ROLES["floor"]
PLAT_FLOOR_IDX = _role_index("floor")
PLAT_UPPER = PLAT_ROLES["upper"]                             # one platform row above the floor
PLAT_UPPER_IDX = _role_index("upper")
PLAT_LEFT_EDGE = PLAT_ROLES["left_edge"]                     # platform touching x = 0
PLAT_LEFT_EDGE_IDX = _role_index("left_edge")
PLAT_RIGHT_EDGE = PLAT_ROLES["right_edge"]                   # platform touching the right edge
PLAT_RIGHT_EDGE_IDX = _role_index("right_edge")
PLAT_CEILING = PLAT_ROLES["ceiling"]                         # ceiling row above the floor
PLAT_TOP_ROW = PLAT_ROLES["top"]                             # top platform row
PLAT_TOP_ROW_IDX = _role_index("top")
PLAT_JUMP_FROM = PLAT_ROLES["jump_from"]                     # missile platform on its row
PLAT_JUMP_FROM_IDX = _role_index("jump_from")
PLAT_JUMP_TO = PLAT_ROLES["jump_to"]                         # sprite platform left of it
# A platform slot on a row the roles above do not use, reused to build synthetic geometry in RAM
# (scenarios that need a specific ceiling must not depend on the scene layout).
PLAT_SCRATCH_IDX = _role_index("spare")


def test_player_init_scene0():
    """Verify player_init correctly initializes Player 0 state, inertia vars and PMG for Scene 0."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize Player 0 on the fixture scene (spawn derived from the scene JSON, Rule 05).
    # The DLI buffers are pre-filled from scene 0's compiled tables, so the scene must be
    # staged before player_init reads SCENE_PLAYER_COLOR.
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE0
    mpu.a = SCENE0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # 1. Canvas position and PMG scanline
    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    # pmg_y = scene_y * 2 + 52 (sprite offset)
    assert mem[labels["PLAYER_PMG_Y"]] == SPAWN0_Y * 2 + 52

    # 2. State & Direction: facing right (0), idle (0), frame 0
    assert mem[labels["PLAYER_DIR"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0
    assert mem[labels["PLAYER_FRAME_TIMER"]] == labels["PLAYER_FRAME_DUR"]
    assert mem[labels["PLAYER_X_SUB"]] == 0
    assert mem[labels["PLAYER_SPEED"]] == 0

    # 3. Hardware registers (SCENE_PLAYER_COLOR is the per-scene SoA table)
    expected_color_0 = mem[labels["SCENE_PLAYER_COLOR"] + SCENE0]
    assert mem[labels["HPOSP0"]] == labels["PLAYER_HPOS_OFFSET"] + SPAWN0_X
    assert mem[labels["SIZEP0"]] == 0        # 1x normal width
    assert mem[labels["COLPM0"]] == expected_color_0
    assert mem[labels["PCOLR0"]] == expected_color_0
    assert mem[labels["PLAYER_COLOR"]] == expected_color_0


    # 4. PMG memory verification (scanlines derived from the scene spawn)
    pmg_p0 = labels["PMG_PLAYER0"]
    pmg_y = SPAWN0_PMG_Y
    height = labels["PLAYER_SPRITE_HEIGHT"]

    for y in range(0, pmg_y):
        assert mem[pmg_p0 + y] == 0x00, f"Scanline {y} before player must be 0"

    # Scanlines pmg_y..pmg_y+height-1 must match player_anim_right_frame_0
    right_f0_addr = labels["PLAYER_ANIM_RIGHT_FRAME_0"]
    for i in range(height):
        expected_byte = mem[right_f0_addr + i]
        actual_byte = mem[pmg_p0 + pmg_y + i]
        assert actual_byte == expected_byte, f"Byte {i} at scanline {pmg_y+i} mismatch: {actual_byte:#04x} vs {expected_byte:#04x}"

    # Scanlines after the sprite must be $00
    for y in range(pmg_y + height, 256):
        assert mem[pmg_p0 + y] == 0x00, f"Scanline {y} after player must be 0"


def test_player_init_uses_the_scene_player_color():
    """Verify player_init takes the player colour from the scene it stages.

    Two scenes with *different* player colours are picked from the manifest (Rule 05: no
    hardcoded scene indices, so reordering scenes or adding a level cannot break this).
    """
    scene_a = SCENE0
    colour_a = player_spawn(scene_a)["color"]
    scene_b = next(
        (
            index
            for index in range(len(scene_files()))
            if index != scene_a and player_spawn(index)["color"] != colour_a
        ),
        None,
    )
    assert scene_b is not None, "no other scene defines a different player colour"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    scene_a_color = mem[labels["SCENE_PLAYER_COLOR"] + scene_a]
    scene_b_color = mem[labels["SCENE_PLAYER_COLOR"] + scene_b]
    assert scene_b_color != scene_a_color, (
        f"scene {scene_b} ({scene_files()[scene_b]}) must have its own player colour"
    )

    # Initialize Player 0 on the second scene (spawn read from the scene JSON, Rule 05)
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = scene_b
    mpu.a = scene_b
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = scene_b
    run_subroutine(mpu, labels["PLAYER_INIT"])

    assert mem[labels["PLAYER_X"]] == player_spawn(scene_b)["x"]
    assert mem[labels["COLPM0"]] == scene_b_color
    assert mem[labels["PCOLR0"]] == scene_b_color
    assert mem[labels["PLAYER_COLOR"]] == scene_b_color

    # Verify platform tables for that scene (count comes from its scene JSON, Rule 05)
    expected_plat_count = scene_platform_count(scene_b)
    expected_ptr_x = mem[labels["SCENE_PLAT_X_LO"] + scene_b] | (mem[labels["SCENE_PLAT_X_HI"] + scene_b] << 8)
    expected_ptr_y = mem[labels["SCENE_PLAT_Y_LO"] + scene_b] | (mem[labels["SCENE_PLAT_Y_HI"] + scene_b] << 8)
    expected_ptr_w = mem[labels["SCENE_PLAT_W_LO"] + scene_b] | (mem[labels["SCENE_PLAT_W_HI"] + scene_b] << 8)

    actual_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    actual_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    actual_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    assert mem[labels["SCENE_PLAT_COUNT"] + scene_b] == expected_plat_count, (
        "the compiled platform count must match the scene JSON"
    )
    assert mem[labels["ZP_PLAT_COUNT"]] == expected_plat_count
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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    assert mem[labels["PLAYER_SPEED"]] == 0

    # STICK0 bit 3 is 0 (right pressed): %00000111 = 0x07
    mem[labels["STICK0"]] = 0x07

    # Frame 1: speed increases by $10 to $10, x_sub = $10 (no step yet)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x10
    assert mem[labels["PLAYER_X_SUB"]] == 0x10
    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    assert mem[labels["PLAYER_STATE"]] == 1     # Walk
    assert mem[labels["PLAYER_DIR"]] == 0       # Right

    # Frame 2: speed = $20, x_sub = $30
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x20
    assert mem[labels["PLAYER_X_SUB"]] == 0x30
    assert mem[labels["PLAYER_X"]] == SPAWN0_X

    # Frame 3: speed = $30, x_sub = $60
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x30
    assert mem[labels["PLAYER_X_SUB"]] == 0x60
    assert mem[labels["PLAYER_X"]] == SPAWN0_X

    # Frame 4: speed = $40, x_sub = $A0, animation frame advances to 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x40
    assert mem[labels["PLAYER_X_SUB"]] == 0xA0
    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    assert mem[labels["PLAYER_FRAME_IDX"]] == 1

    # Frame 5: speed = $50, x_sub = $F0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x50
    assert mem[labels["PLAYER_X_SUB"]] == 0xF0
    assert mem[labels["PLAYER_X"]] == SPAWN0_X

    # Frame 6: speed = $60, x_sub = $F0 + $60 = $50 (carry!), steps one pixel right
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x60
    assert mem[labels["PLAYER_X_SUB"]] == 0x50
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 1
    assert mem[labels["HPOSP0"]] == labels["PLAYER_HPOS_OFFSET"] + SPAWN0_X + 1

    # Frame 7: speed = $70, x_sub = $C0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x70
    assert mem[labels["PLAYER_X_SUB"]] == 0xC0
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 1

    # Frame 8: speed reaches max $80, x_sub = $C0 + $80 = $40 (carry!), two pixels right
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0x40
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 2

    # Frame 9: speed stays at $80, x_sub = $40 + $80 = $C0
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0xC0
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 2

    # Frame 10: speed stays at $80, x_sub = $C0 + $80 = $40 (carry!), three pixels right
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X_SUB"]] == 0x40
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 3


def test_player_deceleration_and_inertia_stop():
    """Verify player gradually decelerates before stopping completely when joystick is released."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Accelerate to max speed (8 frames right)
    mem[labels["STICK0"]] = 0x07
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_SPEED"]] == 0x80
    assert mem[labels["PLAYER_X"]] == SPAWN0_X + 2

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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Accelerate left (STICK0 = 0x0B) for 8 frames
    mem[labels["STICK0"]] = 0x0B
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_DIR"]] == 1       # Left
    assert mem[labels["PLAYER_SPEED"]] == 0x80  # Max speed left
    assert mem[labels["PLAYER_X"]] == SPAWN0_X - 2  # Two sub-pixel carries to the left

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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Left boundary: stand on the platform that touches x = 0
    mem[labels["PLAYER_X"]] = labels["PLAYER_MIN_X"]
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_LEFT_EDGE_IDX
    mem[labels["PLAYER_X_SUB"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0

    # Try moving left (STICK0 = 0x0B)
    mem[labels["STICK0"]] = 0x0B
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == labels["PLAYER_MIN_X"]
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["HPOSP0"]] == labels["PLAYER_HPOS_OFFSET"] + labels["PLAYER_MIN_X"]

    # Right boundary: stand on the platform that touches the right screen edge
    mem[labels["PLAYER_X"]] = labels["PLAYER_MAX_X"]
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_RIGHT_EDGE_IDX
    mem[labels["PLAYER_X_SUB"]] = 0
    mem[labels["PLAYER_SPEED"]] = 0

    # Try moving right (STICK0 = 0x07)
    mem[labels["STICK0"]] = 0x07
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == labels["PLAYER_MAX_X"]
    assert mem[labels["PLAYER_SPEED"]] == 0
    assert mem[labels["PLAYER_STATE"]] == 0
    assert mem[labels["HPOSP0"]] == labels["PLAYER_HPOS_OFFSET"] + labels["PLAYER_MAX_X"]


def test_player_fall_off_platform_right_edge():
    """Verify player falls when moving > 50% past the right edge of a platform."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # The engine tests the hero's midpoint (player_x + 4) against the platform edges, so
    # standing needs midpoint < right edge and the next pixel step pushes it past.
    floor_right = PLAT_FLOOR["x"] + PLAT_FLOOR["width"]
    mem[labels["PLAYER_X"]] = floor_right - 5      # midpoint = right - 1 (still standing)
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed right
    mem[labels["PLAYER_DIR"]] = 0       # Right
    mem[labels["STICK0"]] = 0x07        # Pressing right

    # Subpixel accumulator set so the next frame steps one pixel right
    mem[labels["PLAYER_X_SUB"]] = 0x80
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # midpoint = right edge -> more than 50% past the edge, hero falls
    assert mem[labels["PLAYER_X"]] == floor_right - 4
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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Mirror of the right-edge scenario: standing needs midpoint >= left edge, the next
    # pixel step to the left pushes it past.
    floor_left = PLAT_FLOOR["x"]
    mem[labels["PLAYER_X"]] = floor_left - 4       # midpoint = left edge (still standing)
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed left
    mem[labels["PLAYER_DIR"]] = 1       # Left
    mem[labels["STICK0"]] = 0x0B        # Pressing left

    # Subpixel accumulator set so the next frame steps one pixel left
    mem[labels["PLAYER_X_SUB"]] = 0x80
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # midpoint = left edge - 1 -> more than 50% past the edge, hero falls
    assert mem[labels["PLAYER_X"]] == floor_left - 5
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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Put player in fall state at the spawn line (coordinates from the scene JSON)
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    run_subroutine(mpu, labels["PLAYER_RENDER_FRAME"])

    pmg_p0 = labels["PMG_PLAYER0"]
    fall_f0 = labels["PLAYER_ANIM_FALL_FRAME_0"]

    # Scanlines SPAWN0_PMG_Y.. must match player_anim_fall_frame_0
    for i in range(labels["PLAYER_SPRITE_HEIGHT"]):
        expected_byte = mem[fall_f0 + i]
        actual_byte = mem[pmg_p0 + SPAWN0_PMG_Y + i]
        assert actual_byte == expected_byte, f"Fall frame scanline {SPAWN0_PMG_Y+i} mismatch"


def test_player_fall_and_land_on_lower_platform():
    """Verify player falling downwards lands on a lower platform in its vertical path."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Fall onto PLAT_UPPER: start two canvas lines above its surface, horizontally centred.
    start_y = PLAT_UPPER["y"] - 22                       # feet two lines above the surface
    start_x = PLAT_UPPER["x"] + PLAT_UPPER["width"] // 2 - 4
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = start_y
    mem[labels["PLAYER_PMG_Y"]] = start_y * 2 + 52
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Frame 1: one line down, feet still above the platform surface
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == start_y + 1
    assert mem[labels["PLAYER_STATE"]] == 2

    # Frame 2: feet reach the platform surface (mid_x inside the platform) -> lands on it
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == start_y + 2
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_UPPER_IDX


def test_player_fall_death_and_respawn_with_lives_decrement():
    """Verify falling off bottom of scene clips at status line, decrements lives, and respawns."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Position the hero falling past the floor row, in a column with no platform there.
    fall_x = free_x_on_row(SCENE0, PLAT_FLOOR["y"], PLAT_FLOOR["x"] + PLAT_FLOOR["width"])
    fall_y = PLAT_FLOOR["y"] - 8            # feet already below the floor surface
    mem[labels["PLAYER_X"]] = fall_x
    mem[labels["PLAYER_Y"]] = fall_y
    mem[labels["PLAYER_PMG_Y"]] = fall_y * 2 + 52
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # Advance fall frames up to the death threshold
    # During this time, PMG scanlines >= PMG_STATUS_LINE_TOP MUST be 0 (clipped from status line)
    death_y = labels["PLAYER_DEATH_Y"]
    pmg_p0 = labels["PMG_PLAYER0"]
    for y_cur in range(fall_y + 1, death_y):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        assert mem[labels["PLAYER_Y"]] == y_cur
        assert mem[labels["PLAYER_STATE"]] == 2  # Still falling
        # Verify clipping invariant: status-line scanlines must be strictly 0
        for sl in range(PMG_STATUS_LINE_TOP, 256):
            assert mem[pmg_p0 + sl] == 0, f"PMG scanline {sl} on status line must be 0!"

    # Frame at the death threshold: triggers PLAYER_HANDLE_DEATH
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Lives decremented from 3 to 2
    assert mem[labels["PLAYER_LIVES"]] == 2
    # Status line updated: 3rd heart glyph turned off
    status_chars = labels["STATUS_LINE_CHARS"]
    assert mem[status_chars + 0] == 64  # Heart 1
    assert mem[status_chars + 1] == 64  # Heart 2
    assert mem[status_chars + 2] == 0   # Space (lost life)

    # Hero enters EMERGE state starting below the status line edge
    assert mem[labels["PLAYER_STATE"]] == 5  # PLAYER_STATE_EMERGE
    assert mem[labels["PLAYER_PMG_Y"]] == PMG_STATUS_LINE_TOP

    # Advance the emergence: one scanline up per frame until the spawn scanline
    emerge_frames = PMG_STATUS_LINE_TOP - SPAWN0_PMG_Y
    fall_f0 = labels["PLAYER_ANIM_FALL_FRAME_0"]
    for i in range(1, emerge_frames + 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        expected_pmg_y = PMG_STATUS_LINE_TOP - i
        assert mem[labels["PLAYER_PMG_Y"]] == expected_pmg_y
        if i < emerge_frames:
            assert mem[labels["PLAYER_STATE"]] == 5  # Still emerging
            # Verify fall frame top line is at expected_pmg_y
            assert mem[pmg_p0 + expected_pmg_y] == mem[fall_f0]
        else:
            # Final emergence frame: reached the spawn scanline, transitioned to DEATH
            assert mem[labels["PLAYER_STATE"]] == 4  # PLAYER_STATE_DEATH
            assert mem[labels["PLAYER_Y"]] == SPAWN0_Y
            assert mem[labels["PLAYER_PMG_Y"]] == SPAWN0_PMG_Y
            death_f0 = labels["PLAYER_ANIM_DEATH_FRAME_0"]
            assert mem[pmg_p0 + SPAWN0_PMG_Y] == mem[death_f0]

    # Advance through death sequence: 10 + 10 + 60 = 80 frames
    for _ in range(80):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Hero respawned at the scene spawn coordinates
    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y
    assert mem[labels["PLAYER_STATE"]] == 0  # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_FLOOR_IDX


def test_player_fall_death_game_over_when_zero_lives():
    """Verify falling off bottom with 1 life remaining triggers Game Over with GAME_FAILED status after emergence and death animation."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Start with 1 life
    mem[labels["PLAYER_LIVES"]] = 1
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Put the hero one canvas line above the death threshold, in a column with no platform
    fall_x = free_x_on_row(SCENE0, PLAT_FLOOR["y"], PLAT_FLOOR["x"] + PLAT_FLOOR["width"])
    death_y = labels["PLAYER_DEATH_Y"]
    mem[labels["PLAYER_X"]] = fall_x
    mem[labels["PLAYER_Y"]] = death_y - 1
    mem[labels["PLAYER_PMG_Y"]] = ((death_y - 1) * 2 + 52) & 0xFF
    mem[labels["PLAYER_STATE"]] = 2  # FALL
    mem[labels["PLAYER_PLAT_IDX"]] = 0xFF

    # 1 frame: y reaches the death threshold -> Emergence triggered!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Lives decremented to 0
    assert mem[labels["PLAYER_LIVES"]] == 0

    # All 3 hearts turned off
    status_chars = labels["STATUS_LINE_CHARS"]
    assert mem[status_chars + 0] == 0
    assert mem[status_chars + 1] == 0
    assert mem[status_chars + 2] == 0

    # Player is in EMERGE state (5)
    assert mem[labels["PLAYER_STATE"]] == 5

    # Emergence (one scanline per frame) ends in DEATH state at the spawn scanline
    emerge_frames = PMG_STATUS_LINE_TOP - SPAWN0_PMG_Y
    for _ in range(emerge_frames):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 4
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y
    assert mem[labels["PLAYER_PMG_Y"]] == SPAWN0_PMG_Y


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
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE0
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    mpu.a = SCENE0
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
    assert mem[labels["PLAYER_X"]] == SPAWN0_X
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y
    assert mem[labels["PLAYER_LIVES"]] == 1     # Still 1 life



def test_player_jump_up_vertical():
    """Verify neutral joystick + Fire triggers vertical jump, peaks, and lands back on same platform."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero starts on the scene spawn platform (Rule 05)
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_FLOOR_IDX

    # Jump profile straight from the compiled tables the engine uses
    jump_len = labels["JUMP_UP_LEN"]
    apex_dy = jump_apex_dy(mem, labels, "JUMP_UP_DY", jump_len)    # negative (upward)
    apex_y = SPAWN0_Y + apex_dy
    assert jump_dy_total(mem, labels, "JUMP_UP_DY", jump_len) == 0, (
        "a vertical jump profile must return to its starting line"
    )
    first_dy = mem[labels["JUMP_UP_DY"]]
    first_dy = first_dy - 256 if first_dy >= 128 else first_dy

    # Release fire first, then press Fire with neutral joystick (STICK0 = 0x0F)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x0F                # Neutral joystick

    # Frame 1: Jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 0 # JUMP_TYPE_UP
    assert mem[labels["PLAYER_JUMP_LEN"]] == jump_len
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0 # Phase 0 (Frame 0: fast ascent)
    assert mem[labels["PLAYER_X"]] == SPAWN0_X  # No horizontal motion
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y + first_dy

    # Step through the rest of the ascent (JUMP_UP_DY entries 1..10)
    mem[labels["STRIG0"]] = 1
    for _ in range(10):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        assert mem[labels["PLAYER_STATE"]] == 3 # Still in jump
        assert mem[labels["PLAYER_X"]] == SPAWN0_X    # Strictly vertical

    # Apex: cumulative dy of the ascent table applied to the spawn line
    assert mem[labels["PLAYER_Y"]] == apex_y

    # Apex hold step (dy = 0 -> y unchanged)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3
    assert mem[labels["PLAYER_Y"]] == apex_y

    # Descent at 1 px/frame, rendering the fall animation frame
    pmg_p0 = labels["PMG_PLAYER0"]
    fall_frame_addr = labels["PLAYER_ANIM_FALL_FRAME_0"]
    expected_y = apex_y
    for _ in range(SPAWN0_Y - apex_y - 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        expected_y += 1
        assert mem[labels["PLAYER_STATE"]] == 3
        assert mem[labels["PLAYER_X"]] == SPAWN0_X
        assert mem[labels["PLAYER_Y"]] == expected_y
        pmg_y = mem[labels["PLAYER_PMG_Y"]]
        assert mem[pmg_p0 + pmg_y] == mem[fall_frame_addr]

    # Final descent step lands back on the spawn platform
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_FLOOR_IDX
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y   # Exact return to starting Y
    assert mem[labels["PLAYER_X"]] == SPAWN0_X


def test_player_jump_short_crosses_gap():
    """Verify Fire + Left/Right triggers short jump (~18px) to clear a 16px gap between platforms."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Configure a 16px gap in RAM using PLAT_SCRATCH_IDX and PLAT_FLOOR on PLAT_FLOOR["y"]
    # (built in RAM per Rule 05 so scene edits or reordering cannot remove the test premise).
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    plat_y = PLAT_FLOOR["y"]
    scratch_x = 16
    scratch_w = 16
    floor_x = 48  # 16px gap between scratch (16..32) and floor (48..144)
    floor_w = 96

    mem[plat_ptr_x + PLAT_SCRATCH_IDX] = scratch_x
    mem[plat_ptr_w + PLAT_SCRATCH_IDX] = scratch_w
    mem[plat_ptr_y + PLAT_SCRATCH_IDX] = plat_y

    mem[plat_ptr_x + PLAT_FLOOR_IDX] = floor_x
    mem[plat_ptr_w + PLAT_FLOOR_IDX] = floor_w
    mem[plat_ptr_y + PLAT_FLOOR_IDX] = plat_y

    jump_len = labels["JUMP_SHORT_LEN"]
    start_x = scratch_x + scratch_w - 6  # 26
    landing_x = start_x + jump_dx_total(mem, labels, "JUMP_SHORT_DX", jump_len)  # 26 + 18 = 44
    target_idx = PLAT_FLOOR_IDX

    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = SPAWN0_Y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_SCRATCH_IDX

    # Ensure open sky above the gap: clear the platform row above the starting platform
    mem[plat_ptr_y + PLAT_UPPER_IDX] = 0

    # Release fire, then press Fire + Right (STICK0 bit 3=0 -> 0x07)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x07                # Right active

    # Frame 1: Jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 1 # JUMP_TYPE_SHORT
    assert mem[labels["PLAYER_JUMP_LEN"]] == jump_len
    assert mem[labels["PLAYER_DIR"]] == 0       # Facing Right
    assert mem[labels["PLAYER_X"]] == start_x + 1   # first dx step

    # Advance through the remaining steps of the jump
    mem[labels["STRIG0"]] = 1
    for _ in range(jump_len - 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Total horizontal travel comes from JUMP_SHORT_DX: the hero lands across the gap
    assert mem[labels["PLAYER_X"]] == landing_x
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed on platform across gap!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == target_idx


def test_player_jump_long_reaches_higher_platform():
    """Verify Fire + Up+Left triggers high jump (apex 20 lines) to land on platform 16 lines above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero stands on the floor platform at the right end of PLAT_UPPER and jumps up-left
    # onto it (all coordinates from the scene JSON).
    start_x = PLAT_UPPER["x"] + PLAT_UPPER["width"] - 4
    jump_len = labels["JUMP_LONG_LEN"]
    dx_total = jump_dx_total(mem, labels, "JUMP_LONG_DX", jump_len)
    assert PLAT_UPPER["x"] <= start_x - dx_total, (
        f"landing x must stay inside {PLAT_UPPER['id']} ({PLAT_UPPER['x']}..{PLAT_UPPER['x'] + PLAT_UPPER['width']})"
    )

    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = SPAWN0_Y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX

    # Release fire, then press Fire + Up+Left (STICK0 bit 0=0 up, bit 2=0 left -> 0x0A)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0                   # Fire pressed
    mem[labels["STICK0"]] = 0x0A                # Up+Left active

    # Frame 1: Long jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 2 # JUMP_TYPE_LONG
    assert mem[labels["PLAYER_JUMP_LEN"]] == jump_len
    assert mem[labels["PLAYER_DIR"]] == 1       # Facing Left

    # Step through the jump until landing on the higher platform
    mem[labels["STRIG0"]] = 1
    landed = False
    for _ in range(2, jump_len + 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        if mem[labels["PLAYER_STATE"]] == 0:    # IDLE -> Landed!
            landed = True
            break

    assert landed, f"Hero must land on {PLAT_UPPER['id']}"
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_UPPER_IDX
    assert mem[labels["PLAYER_Y"]] == PLAT_UPPER["y"] - labels["PLAYER_SPRITE_HEIGHT"]
    # Horizontal displacement must stay within the JUMP_LONG_DX budget:
    dx_traveled = start_x - mem[labels["PLAYER_X"]]
    assert 0 < dx_traveled <= dx_total, f"Horizontal displacement ({dx_traveled}) must be <= {dx_total}px"


def test_player_jump_long_does_not_hit_ceiling_two_tiers_above():
    """Verify long jump to a platform 16 lines above does not trigger ceiling bounce when a ceiling is 2 tiers above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on the floor at the right end of PLAT_UPPER, jumping up-left onto it, while a
    # ceiling two platform rows above the floor spans the jump path (built in RAM so a scene
    # edit cannot silently remove the premise of this test).
    start_x = PLAT_UPPER["x"] + PLAT_UPPER["width"] - 4
    jump_len = labels["JUMP_LONG_LEN"]
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = SPAWN0_Y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX

    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    ceiling_y = PLAT_FLOOR["y"] - 2 * 16          # two platform rows above the floor
    mem[plat_ptr_x + PLAT_SCRATCH_IDX] = start_x - 16
    mem[plat_ptr_w + PLAT_SCRATCH_IDX] = 32
    mem[plat_ptr_y + PLAT_SCRATCH_IDX] = ceiling_y

    # Trigger long jump Up+Left
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0A

    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3  # PLAYER_STATE_JUMP

    mem[labels["STRIG0"]] = 1
    landed = False
    for _ in range(jump_len - 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        # Must NEVER bounce into fall state during this jump
        assert mem[labels["PLAYER_STATE"]] != 2, f"Must not bounce off the ceiling at y={ceiling_y}!"
        if mem[labels["PLAYER_STATE"]] == 0:
            landed = True
            break

    assert landed, "Hero must land on target platform"
    assert mem[labels["PLAYER_Y"]] == PLAT_UPPER["y"] - labels["PLAYER_SPRITE_HEIGHT"]


def test_player_jump_blocked_when_platform_directly_overhead():
    """Verify Hero standing on a platform with another platform directly overhead (16px above) cannot jump."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on the floor directly under PLAT_UPPER: a platform 16 canvas lines above leaves no
    # headroom, so the jump must be refused (geometry from the scene JSON).
    start_x = PLAT_UPPER["x"] + PLAT_UPPER["width"] // 2 - 4
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = SPAWN0_Y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX

    # Fire + neutral (JUMP_UP)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F

    # Jump must be blocked! Hero remains standing in IDLE on the floor platform
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0      # PLAYER_STATE_IDLE (not JUMP, not FALL!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_FLOOR_IDX
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y    # Never moved down or penetrated platform

    # Re-release fire and try Fire + Right (short jump attempt under ceiling)
    mem[labels["STRIG0"]] = 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x07                 # Right

    # Jump must still be blocked!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] != 3      # Not jumping
    assert mem[labels["PLAYER_STATE"]] != 2      # Not falling through platform!
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_FLOOR_IDX
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y



def test_player_jump_ceiling_collision_bounces_to_fall():
    """Verify Hero jumping into a platform ceiling from below bounces off and falls straight down."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero under PLAT_CEILING: the head starts just below the ceiling bottom, so the first
    # jump step bumps it and bounces straight into FALL (geometry from the scene JSON).
    first_dy = mem[labels["JUMP_SHORT_DY"]]
    first_dy = first_dy - 256 if first_dy >= 128 else first_dy
    start_x = PLAT_CEILING["x"] + PLAT_CEILING["width"] // 2
    start_y = PLAT_CEILING["y"] + PLAT_CEILING["height"] - first_dy
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = start_y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX   # standing on a platform below

    # Release fire, then press Fire + Right (JUMP_SHORT)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x07                # Right active -> JUMP_TYPE_SHORT

    # Frame 1: Jump triggers, the first dy step lifts the head into the ceiling bottom
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Hero bumps ceiling: bounces immediately into PLAYER_STATE_FALL!
    assert mem[labels["PLAYER_STATE"]] == 2     # PLAYER_STATE_FALL
    assert mem[labels["PLAYER_PLAT_IDX"]] == 0xFF
    assert mem[labels["PLAYER_FRAME_IDX"]] == 0 # Fall animation frame
    assert mem[labels["PLAYER_SPEED"]] == 0     # Speed 0 (falls vertically)

    # Next frame: regular fall update drops by 1 line
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 2     # Still falling
    assert mem[labels["PLAYER_Y"]] == start_y - 1


def test_player_jump_up_does_not_hit_ceiling_two_tiers_above():
    """Verify vertical jump (JUMP_UP) reaches full apex and is not clipped by a platform two tiers above."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on the floor, with a ceiling two platform rows above built in RAM (a scene edit
    # must not silently remove the premise of this test).
    start_x = PLAT_UPPER["x"] + PLAT_UPPER["width"] - 4
    jump_len = labels["JUMP_UP_LEN"]
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = SPAWN0_Y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_FLOOR_IDX

    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)
    ceiling_y = PLAT_FLOOR["y"] - 2 * 16          # two platform rows above the floor
    mem[plat_ptr_x + PLAT_SCRATCH_IDX] = start_x - 16
    mem[plat_ptr_w + PLAT_SCRATCH_IDX] = 32
    mem[plat_ptr_y + PLAT_SCRATCH_IDX] = ceiling_y

    # Trigger vertical jump (Fire + neutral)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F                # Neutral -> JUMP_TYPE_UP

    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3     # PLAYER_STATE_JUMP

    mem[labels["STRIG0"]] = 1
    landed = False
    for _ in range(jump_len - 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        # Must NEVER bounce into fall state: a ceiling two tiers above is not a head bump
        assert mem[labels["PLAYER_STATE"]] != 2, (
            f"Must not bounce off the ceiling at y={ceiling_y} during a vertical jump!"
        )
        if mem[labels["PLAYER_STATE"]] == 0:
            landed = True
            break

    assert landed, "Hero must land back on starting platform"
    assert mem[labels["PLAYER_Y"]] == SPAWN0_Y


def test_player_jump_animation_frames_in_pmg():
    """Verify jump animation frames 0, 1, 2 are rendered into PMG memory during jump phases."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Start a jump from the scene spawn platform (Rule 05)
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

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero standing on the top platform row, head at the platform surface minus sprite height
    start_y = PLAT_TOP_ROW["y"] - labels["PLAYER_SPRITE_HEIGHT"]
    jump_len = labels["JUMP_UP_LEN"]
    first_dy = mem[labels["JUMP_UP_DY"]]
    first_dy = first_dy - 256 if first_dy >= 128 else first_dy
    apex_dy = jump_apex_dy(mem, labels, "JUMP_UP_DY", jump_len)

    mem[labels["PLAYER_X"]] = PLAT_TOP_ROW["x"] + 4
    mem[labels["PLAYER_Y"]] = start_y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_TOP_ROW_IDX

    # Trigger vertical jump
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0F

    # Step 1: first dy step
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3
    assert mem[labels["PLAYER_Y"]] == start_y + first_dy

    # Step 2: second dy step
    mem[labels["STRIG0"]] = 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == start_y + 2 * first_dy

    # Step 3: y crosses into negative (two's complement) - must NOT be clamped to 0!
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == (start_y + 3 * first_dy) & 0xFF

    # Step through the remaining steps to the apex (cumulative dy from JUMP_UP_DY)
    for _ in range(8):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_Y"]] == (start_y + apex_dy) & 0xFF

    # PMG scanline at apex: signed y * 2 + 52 (still a valid PMG scanline)
    assert mem[labels["PLAYER_PMG_Y"]] == ((start_y + apex_dy) * 2 + 52) & 0xFF

    # Complete the jump (1 apex step + the descent steps) and verify a clean landing
    for _ in range(19):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 0     # IDLE (landed!)
    assert mem[labels["PLAYER_PLAT_IDX"]] == PLAT_TOP_ROW_IDX
    assert mem[labels["PLAYER_Y"]] == start_y    # Exactly returned to starting Y


def test_player_jump_short_from_platform_016_to_012_under_platform_010():
    """Verify Hero jumping left from platform-016 (y=56) to platform-012 (y=56)
    does not hit ceiling of platform-010 (y=24, 32px above) and lands cleanly."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero on PLAT_JUMP_FROM (a missile platform) jumping left onto PLAT_JUMP_TO on the same
    # row, under the top-row platform two tiers above (geometry from the scene JSON).
    # Dynamically place Hero at the leftmost standing position on PLAT_JUMP_FROM (Rule 05)
    # so the short jump (dx=18) reaches PLAT_JUMP_TO cleanly across the gap.
    start_x = max(PLAT_JUMP_FROM["x"] - 4, PLAT_JUMP_TO["x"] - 4 + 18)
    start_y = PLAT_JUMP_FROM["y"] - labels["PLAYER_SPRITE_HEIGHT"]
    jump_len = labels["JUMP_SHORT_LEN"]
    mem[labels["PLAYER_X"]] = start_x
    mem[labels["PLAYER_Y"]] = start_y
    mem[labels["PLAYER_PLAT_IDX"]] = PLAT_JUMP_FROM_IDX

    # Trigger jump left (STICK0 bit 2=0 left -> 0x0B)
    mem[labels["PLAYER_FIRE_RELEASED"]] = 1
    mem[labels["STRIG0"]] = 0
    mem[labels["STICK0"]] = 0x0B  # Left active -> JUMP_TYPE_SHORT

    # Frame 1: Jump triggers
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_STATE"]] == 3  # JUMP
    assert mem[labels["PLAYER_JUMP_TYPE"]] == 1  # JUMP_TYPE_SHORT
    assert mem[labels["PLAYER_DIR"]] == 1  # Left

    # Release fire and step through the jump
    mem[labels["STRIG0"]] = 1
    for step in range(2, jump_len + 1):
        run_subroutine(mpu, labels["PLAYER_UPDATE"])
        # Crucial invariant: Hero must NEVER transition to FALL state during ascent!
        assert mem[labels["PLAYER_STATE"]] != 2, f"Bounced off false ceiling on step {step}!"
        if mem[labels["PLAYER_STATE"]] == 0:
            break

    # Jump must complete and land on the target platform (same row, feet on its surface)
    assert mem[labels["PLAYER_STATE"]] == 0, "Hero must land in IDLE state"
    assert mem[labels["PLAYER_Y"]] == start_y, "Hero must land at the platform surface"
    assert PLAT_JUMP_TO["x"] <= mem[labels["PLAYER_X"]] <= PLAT_JUMP_TO["x"] + PLAT_JUMP_TO["width"], (
        f"Hero must be within {PLAT_JUMP_TO['id']} x bounds"
    )


def test_player_walks_across_adjacent_platforms():
    """Verify Hero seamlessly walks across two touching platforms at the same Y level without falling."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLATFORMS_INIT"])
    mpu.a = SCENE0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Configure two touching platforms in RAM on SCENE0 using PLAT_FLOOR and PLAT_SCRATCH_IDX
    # (built in RAM per Rule 05 so scene edits or reordering cannot remove the test premise).
    plat_ptr_x = mem[labels["ZP_PLAT_PTR_X"]] | (mem[labels["ZP_PLAT_PTR_X"] + 1] << 8)
    plat_ptr_y = mem[labels["ZP_PLAT_PTR_Y"]] | (mem[labels["ZP_PLAT_PTR_Y"] + 1] << 8)
    plat_ptr_w = mem[labels["ZP_PLAT_PTR_W"]] | (mem[labels["ZP_PLAT_PTR_W"] + 1] << 8)

    plat_y = PLAT_FLOOR["y"]
    left_x = 40
    left_w = 32
    right_x = left_x + left_w  # 72, exactly touching
    right_w = 32
    boundary_x = right_x

    left_idx = PLAT_FLOOR_IDX
    right_idx = PLAT_SCRATCH_IDX

    mem[plat_ptr_x + left_idx] = left_x
    mem[plat_ptr_w + left_idx] = left_w
    mem[plat_ptr_y + left_idx] = plat_y

    mem[plat_ptr_x + right_idx] = right_x
    mem[plat_ptr_w + right_idx] = right_w
    mem[plat_ptr_y + right_idx] = plat_y

    hero_y = (plat_y - labels["PLAYER_SPRITE_HEIGHT"]) & 0xFF

    # 1. Test walking right across boundary: left_plat -> right_plat
    # Midpoint = player_x + 4. Boundary = boundary_x.
    mem[labels["PLAYER_X"]] = boundary_x - 5  # mid_x = boundary_x - 1 (still on left_plat)
    mem[labels["PLAYER_Y"]] = hero_y
    mem[labels["PLAYER_PLAT_IDX"]] = left_idx
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed right
    mem[labels["PLAYER_DIR"]] = 0       # Right
    mem[labels["STICK0"]] = 0x07        # Pressing right
    mem[labels["PLAYER_X_SUB"]] = 0x80  # Step 1px right on next frame

    # Advance 1 frame: player_x becomes boundary_x - 4, mid_x becomes boundary_x
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == boundary_x - 4
    assert mem[labels["PLAYER_STATE"]] != 2, "Hero must not fall when stepping onto adjacent platform"
    assert mem[labels["PLAYER_PLAT_IDX"]] == right_idx, f"Platform index must switch to scratch platform ({right_idx})"

    # 2. Test walking left across boundary: right_plat -> left_plat
    mem[labels["PLAYER_X"]] = boundary_x - 4  # mid_x = boundary_x (on right_plat)
    mem[labels["PLAYER_PLAT_IDX"]] = right_idx
    mem[labels["PLAYER_SPEED"]] = 0x80  # Max speed left
    mem[labels["PLAYER_DIR"]] = 1       # Left
    mem[labels["STICK0"]] = 0x0B        # Pressing left
    mem[labels["PLAYER_X_SUB"]] = 0x80  # Step 1px left on next frame

    # Advance 1 frame: player_x becomes boundary_x - 5, mid_x becomes boundary_x - 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    assert mem[labels["PLAYER_X"]] == boundary_x - 5
    assert mem[labels["PLAYER_STATE"]] != 2, "Hero must not fall when stepping back onto left platform"
    assert mem[labels["PLAYER_PLAT_IDX"]] == left_idx, f"Platform index must switch back to floor platform ({left_idx})"


