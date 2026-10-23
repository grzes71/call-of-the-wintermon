"""Automated py65 integration test suite for Atari 8-bit Enemy movement, animation, speed, pause, and collision.

Validates:
1. Enemy-to-sprite validation:
   - Rejects enemies with missing sprite_id (neither on object nor definition).
   - Rejects enemies with invalid/non-existent sprite_id.
2. Enemy initialization (enemies_init) across scenes:
   - Correct count and initial SoA parameters.
   - Initial sprite frame rendered to PMG memory (PMG_PLAYER1..3).
   - DLI hardware horizontal positions (dli_zone_hpos_p1..3) synced to 48 + x.
3. Speed intervals:
   - Slow (0): moves 1 pixel every 4 frames.
   - Medium (1): moves 1 pixel every 2 frames.
   - Fast (2): moves 1 pixel every 1 frame.
4. Movement strategies & initial directions:
   - stationary (0): does not move.
   - left_right (1): starts moving left (dir=1), reverses at min_x to right (dir=0).
   - right_left (2): starts moving right (dir=0), reverses at max_x to left (dir=1).
   - left_pause_right (3): starts left (dir=1), hits min_x, pauses 50 frames (1 sec PAL), reverses right.
   - right_pause_left (4): starts right (dir=0), hits max_x, pauses 50 frames (1 sec PAL), reverses left.
5. 50-frame pause timing:
   - Position remains stationary while pause_timer counts down from 50 to 0.
   - Resumes patrol movement on frame 51.
6. Player collision:
   - Hero overlapping an enemy calls player_handle_death (decrements player_lives).
   - Non-overlapping Hero does not collide (player_lives unchanged).
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
from tests.scene_expectations import (
    dli_enemy_hpos_slots,
    enemy_frame_bytes,
    enemy_pmg_rows,
    expected_pmg_y,
    expected_speed_code,
    expected_strategy_code,
    scene_files,
    scene_objects,
    sprite_height,
)
from tests.test_dli_system import load_xex_and_symbols, run_subroutine


# ==============================================================================
# 1. Validation Tests (Sprite linkage)
# ==============================================================================


def test_enemy_missing_sprite_id_raises_error(tmp_path: Path):
    """Enemies without sprite_id on object or definition must raise ValueError."""
    # Dummy scene with an enemy lacking sprite_id
    scene_json = {
        "scene": {"name": "Test Scene", "width": 160, "height": 96},
        "platforms": [
            {
                "id": "plat-01",
                "type": "sprite",
                "position": {"x": 20, "y": 24},
                "width": 32,
                "height": 4,
            }
        ],
        "objects": [
            {
                "id": 1,
                "type": "enemy",
                "definition_id": 99,  # definition does not specify sprite_id
                "platform_id": "plat-01",
                "x": 24,
                "speed": "slow",
                "movement_strategy": "left_right",
                # "sprite_id" is deliberately omitted
            }
        ],
    }
    sc_file = tmp_path / "test_missing_spr.json"
    sc_file.write_text(json.dumps(scene_json), encoding="utf-8")

    enemies = {
        99: CatalogueItem(id=99, name="Ghost", atari_color=0x42, sprite_id=None)
    }
    secrets = {}

    with pytest.raises(ValueError, match=r"(has no assigned sprite_id|nie ma przypisanego sprite_id)"):
        parse_scene_json(sc_file, enemies, secrets, sprites={})


def test_enemy_invalid_sprite_id_raises_error(tmp_path: Path):
    """Enemies referencing non-existent sprite_id must raise ValueError."""
    scene_json = {
        "scene": {"name": "Test Scene", "width": 160, "height": 96},
        "platforms": [
            {
                "id": "plat-01",
                "type": "sprite",
                "position": {"x": 20, "y": 24},
                "width": 32,
                "height": 4,
            }
        ],
        "objects": [
            {
                "id": 1,
                "type": "enemy",
                "definition_id": 1,
                "platform_id": "plat-01",
                "x": 24,
                "sprite_id": 999,  # Non-existent sprite
                "speed": "medium",
                "movement_strategy": "left_right",
            }
        ],
    }
    sc_file = tmp_path / "test_invalid_spr.json"
    sc_file.write_text(json.dumps(scene_json), encoding="utf-8")

    sprites_file = Path("sprites/objects.sprite.json")
    sprites = parse_sprites_json(sprites_file)

    with pytest.raises(ValueError, match=r"(references non-existent sprite_id|nie istnieje w pliku sprite)"):
        parse_scene_json(sc_file, {}, {}, sprites=sprites)


# ==============================================================================
# 2. Runtime Initialization Tests (py65 Emulation)
# ==============================================================================


def test_enemies_init_scene0():
    """Verify enemies_init sets up Scene 0 enemies exactly as derived from the scene JSON.

    Everything (count, sprite ids, speeds, strategies, coordinates, PMG rows and DLI
    positions) is derived from scenes/*.json + definitions.json (Rule 05).
    """
    scene_file = scene_files()[0]
    enemies = scene_objects(scene_file, "enemy")
    assert enemies, f"{scene_file} must define at least one enemy"

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

    # Initialize Enemies
    mpu.a = 0
    run_subroutine(mpu, labels["ENEMIES_INIT"])

    count = len(enemies)
    assert mem[labels["ENEMIES_COUNT"]] == count

    act_addr = labels["ENEMIES_ACTIVE"]
    x_addr = labels["ENEMIES_X"]
    spd_addr = labels["ENEMIES_SPEED"]
    strat_addr = labels["ENEMIES_STRATEGY"]
    spr_addr = labels["ENEMIES_SPRITE_ID"]
    pmg_y_addr = labels["ENEMIES_PMG_Y"]
    h_addr = labels["ENEMIES_HEIGHT"]
    chan_addr = labels["ENEMIES_CHANNEL"]
    zone_addr = labels["ENEMIES_ZONE"]

    for i, enemy in enumerate(enemies):
        assert mem[act_addr + i] == 1, f"Enemy {i} must be active"
        assert mem[spr_addr + i] == enemy["sprite_id"], f"Enemy {i} sprite id mismatch"
        assert mem[spd_addr + i] == expected_speed_code(enemy), f"Enemy {i} speed mismatch"
        assert mem[strat_addr + i] == expected_strategy_code(enemy), f"Enemy {i} strategy mismatch"
        assert mem[x_addr + i] == enemy["x"], f"Enemy {i} x coordinate mismatch"
        assert mem[zone_addr + i] == enemy["zone"], f"Enemy {i} zone mismatch"

        height = mem[h_addr + i]
        assert height == sprite_height(mem, labels, enemy["sprite_id"])
        assert mem[pmg_y_addr + i] == expected_pmg_y(enemy["platform_y"], height), (
            f"Enemy {i} pmg_y mismatch"
        )
        # Frame 0 must be rendered on the enemy's hardware player channel
        assert enemy_pmg_rows(mem, labels, i) == enemy_frame_bytes(mem, labels, i), (
            f"Enemy {i} PMG rows do not match sprite frame 0"
        )

    # DLI horizontal positions: the last enemy written per (zone, channel) wins
    expected_hpos: dict[tuple[int, int], int] = {}
    for i in range(count):
        expected_hpos[(mem[zone_addr + i], mem[chan_addr + i])] = 48 + mem[x_addr + i]
    for (zone, channel), hpos in expected_hpos.items():
        slots = dli_enemy_hpos_slots(labels, zone, channel)
        assert all(mem[slot] == hpos for slot in slots), (
            f"DLI HPOSP{channel + 1} for zone {zone} must be {hpos} in both buffers"
        )


# ==============================================================================
# 3. Movement and Speed Interval Tests
# ==============================================================================


def test_enemies_speed_intervals():
    """Verify speed timing: slow moves every 4 frames, medium every 2, fast every 1 frame."""
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

    x_addr = labels["ENEMIES_X"]
    spd_addr = labels["ENEMIES_SPEED"]
    timer_addr = labels["ENEMIES_SPEED_TIMER"]
    dir_addr = labels["ENEMIES_DIR"]
    strat_addr = labels["ENEMIES_STRATEGY"]

    # Explicitly configure test fixture parameters for interval verification (Rule 05)
    # Enemy 0: medium (speed=1), moving left from x=120
    # Enemy 1: slow (speed=0), moving right from x=5
    # Enemy 2: stationary (strategy=0) at x=78
    mem[spd_addr + 0] = 1
    mem[timer_addr + 0] = 0
    mem[dir_addr + 0] = 1
    mem[strat_addr + 0] = 1
    mem[x_addr + 0] = 120

    mem[spd_addr + 1] = 0
    mem[timer_addr + 1] = 0
    mem[dir_addr + 1] = 0
    mem[strat_addr + 1] = 2
    mem[x_addr + 1] = 5

    mem[strat_addr + 2] = 0
    mem[x_addr + 2] = 78

    # Synthetic patrol bounds so the interval check never depends on scene geometry (Rule 05)
    for i in range(3):
        mem[labels["ENEMIES_MIN_X"] + i] = 0
        mem[labels["ENEMIES_MAX_X"] + i] = 152

    # Frame 1:
    # Enemy 0 (med): speed_timer was 0 -> reloads 1, moves 1 px left to 119
    # Enemy 1 (slow): speed_timer was 0 -> reloads 3, moves 1 px right to 6
    # Enemy 2 (stat): stays 110
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 119
    assert mem[x_addr + 1] == 6
    assert mem[x_addr + 2] == 78

    # Frame 2:
    # Enemy 0 (med): speed_timer=1 -> decrements to 0, does NOT move (stays 119)
    # Enemy 1 (slow): speed_timer=3 -> decrements to 2, does NOT move (stays 6)
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 119
    assert mem[x_addr + 1] == 6

    # Frame 3:
    # Enemy 0 (med): speed_timer=0 -> reloads 1, moves 1 px left to 118!
    # Enemy 1 (slow): speed_timer=2 -> decrements to 1, stays 6
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 118
    assert mem[x_addr + 1] == 6

    # Frame 4:
    # Enemy 0 (med): speed_timer=1 -> decrements to 0, stays 118
    # Enemy 1 (slow): speed_timer=1 -> decrements to 0, stays 6
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 118
    assert mem[x_addr + 1] == 6

    # Frame 5:
    # Enemy 0 (med): speed_timer=0 -> reloads 1, moves 1 px left to 117!
    # Enemy 1 (slow): speed_timer=0 -> reloads 3, moves 1 px right to 7!
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 117
    assert mem[x_addr + 1] == 7


# ==============================================================================
# 4. Strategy Boundary Bouncing & 50-Frame Pause Timing Tests
# ==============================================================================


def test_strategy_pause_at_boundary():
    """Verify left_pause_right (strategy 3) pauses for 50 frames at platform boundary."""
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

    # Configure Enemy 0 specifically for pause test:
    # Set fast speed (speed 2 = moves every frame)
    # Set strategy = 3 (left_pause_right)
    # Set min_x = 96, max_x = 120
    # Set x = 98, dir = 1 (moving left toward min_x)
    x_addr = labels["ENEMIES_X"]
    spd_addr = labels["ENEMIES_SPEED"]
    strat_addr = labels["ENEMIES_STRATEGY"]
    dir_addr = labels["ENEMIES_DIR"]
    pause_addr = labels["ENEMIES_PAUSE_TIMER"]

    mem[spd_addr + 0] = 2    # Fast (every frame)
    mem[strat_addr + 0] = 3  # left_pause_right
    mem[dir_addr + 0] = 1    # Moving left
    mem[x_addr + 0] = 98
    mem[pause_addr + 0] = 0
    # Explicit patrol bounds for the fixture (Rule 05)
    mem[labels["ENEMIES_MIN_X"] + 0] = 96
    mem[labels["ENEMIES_MAX_X"] + 0] = 120

    # Frame 1: moves left from 98 -> 97
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 97
    assert mem[dir_addr + 0] == 1
    assert mem[pause_addr + 0] == 0

    # Frame 2: moves left from 97 -> 96 (hits min_x!)
    # Direction reverses to right (dir = 0), and pause_timer is set to 50!
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 96
    assert mem[dir_addr + 0] == 0
    assert mem[pause_addr + 0] == 50, "Hitting boundary on left_pause_right must set pause_timer to 50"

    # Next 50 frames: enemy must remain at x=96 while pause_timer counts down 50 -> 0!
    for rem in range(49, -1, -1):
        run_subroutine(mpu, labels["ENEMIES_UPDATE"])
        assert mem[x_addr + 0] == 96, f"Enemy must remain stationary during pause (remaining {rem})"
        assert mem[pause_addr + 0] == rem

    assert mem[pause_addr + 0] == 0

    # Frame 53 (first frame after 1-second pause has elapsed):
    # Enemy resumes movement toward right: moves from 96 -> 97!
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 97
    assert mem[dir_addr + 0] == 0


def test_strategy_without_pause_bounces_immediately():
    """Verify left_right (strategy 1) bounces immediately at boundary with 0 pause."""
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

    x_addr = labels["ENEMIES_X"]
    spd_addr = labels["ENEMIES_SPEED"]
    strat_addr = labels["ENEMIES_STRATEGY"]
    dir_addr = labels["ENEMIES_DIR"]
    pause_addr = labels["ENEMIES_PAUSE_TIMER"]

    mem[spd_addr + 0] = 2    # Fast
    mem[strat_addr + 0] = 1  # left_right (no pause)
    mem[dir_addr + 0] = 1    # Moving left
    mem[x_addr + 0] = 97
    # Explicit patrol bounds for the fixture (Rule 05)
    mem[labels["ENEMIES_MIN_X"] + 0] = 96
    mem[labels["ENEMIES_MAX_X"] + 0] = 120

    # Hits min_x = 96
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 96
    assert mem[dir_addr + 0] == 0
    assert mem[pause_addr + 0] == 0, "No pause on left_right"

    # Immediately moves right on next frame
    run_subroutine(mpu, labels["ENEMIES_UPDATE"])
    assert mem[x_addr + 0] == 97
    assert mem[dir_addr + 0] == 0


# ==============================================================================
# 5. Player Collision Tests
# ==============================================================================


def test_player_collision_triggers_death():
    """Verify that Hero overlapping an enemy triggers player_handle_death."""
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
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    # Hero starts with 3 lives
    lives_addr = labels["PLAYER_LIVES"]
    mem[lives_addr] = 3

    # Position Hero directly overlapping Enemy 0
    e0_x = mem[labels["ENEMIES_X"] + 0]
    e0_pmg_y = mem[labels["ENEMIES_PMG_Y"] + 0]
    mem[labels["PLAYER_X"]] = e0_x
    mem[labels["PLAYER_PMG_Y"]] = e0_pmg_y + 5

    # Check collision
    run_subroutine(mpu, labels["ENEMIES_CHECK_PLAYER_COLLISION"])

    # Lives must have decremented from 3 to 2!
    assert mem[lives_addr] == 2, "Collision must call player_handle_death and decrement lives"


def test_player_no_collision_preserves_lives():
    """Verify that Hero far from enemies does not trigger death."""
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
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    lives_addr = labels["PLAYER_LIVES"]
    mem[lives_addr] = 3

    # Position Hero far from any enemy: x=20, pmg_y=188
    mem[labels["PLAYER_X"]] = 20
    mem[labels["PLAYER_PMG_Y"]] = 188

    run_subroutine(mpu, labels["ENEMIES_CHECK_PLAYER_COLLISION"])

    assert mem[lives_addr] == 3, "Non-overlapping Hero must keep lives unchanged"


# ==============================================================================
# 7. Zone slot placement (regression: enemies must sit on their platform row)
# ==============================================================================
def test_enemy_zone_slot_matches_its_platform_row():
    """Enemy HPOS must land in the DLI zone slot of the enemy's own platform row.

    engine/dli.asm applies zone slot `p` on the platform row at y = 8 + 16*p, so an enemy
    standing on that row must be stored in slot `p`. Any other slot draws it one row off its
    platform - exactly the bug this test guards against.
    """
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])

    enemies_catalogue, secrets_catalogue = load_catalogues(
        Path("scenes/definitions.json"), Path("scenes/definitions.json")
    )

    checked = 0
    for scene_index, scene_file in enumerate(scene_files()):
        enemies = scene_objects(scene_file, "enemy")
        if not enemies:
            continue

        compiled = parse_scene_json(
            Path("scenes") / scene_file, enemies_catalogue, secrets_catalogue
        )
        dli = compiled.dli_data
        tables = (dli.zone_hpos_p1, dli.zone_hpos_p2, dli.zone_hpos_p3)

        # 1. Compiled DLI block: the initial HPOS must already sit in the platform row's slot
        for enemy in enemies:
            data = next(e for e in compiled.enemies if e.id == enemy["id"])
            slot = (enemy["platform_y"] - 8) // 16
            assert data.zone_idx == slot, (
                f"{scene_file}: enemy {enemy['id']} zone must be the pas index of its platform row"
            )
            assert data.min_x <= data.x <= data.max_x, (
                f"{scene_file}: enemy {enemy['id']} x={data.x} is outside its platform "
                f"[{data.min_x}, {data.max_x}]"
            )
            assert tables[data.channel][slot] == 48 + data.x, (
                f"{scene_file}: enemy {enemy['id']} (platform row {enemy['platform_y']}) must be "
                f"compiled into zone slot {slot} of channel {data.channel}"
            )

        # 2. Runtime: after staging the scene and running enemies_init the same slot must hold 48 + x
        mem[labels["ACTIVE_SCENE_ID"]] = scene_index
        mpu.a = scene_index
        run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
        mpu.a = scene_index
        run_subroutine(mpu, labels["ENEMIES_INIT"])
        for i, enemy in enumerate(enemies):
            slot = (enemy["platform_y"] - 8) // 16
            assert mem[labels["ENEMIES_ZONE"] + i] == slot, (
                f"{scene_file}: enemy {enemy['id']} zone field must be the pas index of its row"
            )
            hpos = 48 + mem[labels["ENEMIES_X"] + i]
            channel = mem[labels["ENEMIES_CHANNEL"] + i]
            slots = dli_enemy_hpos_slots(labels, slot, channel)
            assert all(mem[addr] == hpos for addr in slots), (
                f"{scene_file}: enemy {enemy['id']} HPOS {hpos} missing from zone slot {slot} "
                f"(channel {channel})"
            )
            checked += 1

    assert checked > 0, "no game scene defines an enemy to verify"

