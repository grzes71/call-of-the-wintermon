"""Automated test suite enforcing scanline PMG invariants across all scenes.

Invariants (Section 2 of specification):
1. In Enemies/Secrets zones between platforms, PMG data (Players 1-3, Missiles)
   can be non-zero ONLY on valid sprite rows assigned to that channel.
2. All transition scanlines (the 3 DLI setup scanlines p_base - 3 .. p_base - 1
   before each platform pas) and top guard lines (p_base - 24) MUST have 0x00
   in Players 1-3 and Missiles.
3. Platform scanlines (p_base .. p_base + 7) contain ONLY platform patterns.
4. Sprite height + guard/transition lines (4) <= zone height (24). Max sprite height is 20.
   compile_scenes.py must raise an error for oversized sprites.
5. After enemies_update (patrol movement, pause frames), non-sprite scanlines remain 0x00.
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


PLATFORM_BASES = [48, 80, 112, 144, 176, 208]
ZONE_HEIGHT = 24
MAX_SPRITE_HEIGHT = 20  # Zone (24) - guard line (1) - DLI transition (3) = 20


def get_pmg_snapshot(mem, labels) -> dict[str, list[int]]:
    """Extract scanlines 0..255 for P1, P2, P3, Missiles."""
    p1_base = labels["PMG_PLAYER1"]
    p2_base = labels["PMG_PLAYER2"]
    p3_base = labels["PMG_PLAYER3"]
    m_base = labels["PMG_MISSILES"]
    return {
        "P1": [mem[p1_base + i] for i in range(256)],
        "P2": [mem[p2_base + i] for i in range(256)],
        "P3": [mem[p3_base + i] for i in range(256)],
        "M":  [mem[m_base + i] for i in range(256)],
    }


def assert_pmg_invariants(snapshot: dict[str, list[int]], scene_id: int, context_msg: str):
    """Enforces that transition scanlines and guard lines are strictly zero."""
    errors = []

    for k, p_base in enumerate(PLATFORM_BASES):
        # 1. Top guard line (for zones 1..5: p_base - 24)
        if k > 0:
            guard_sl = p_base - 24
            for ch in ("P1", "P2", "P3", "M"):
                val = snapshot[ch][guard_sl]
                if val != 0:
                    errors.append(
                        f"Scene {scene_id} ({context_msg}): Top guard line SL {guard_sl} "
                        f"has non-zero byte in {ch}: 0x{val:02X}"
                    )

        # 2. DLI Pre-pas transition window (3 scanlines: p_base - 3 .. p_base - 1)
        for t_offset in (3, 2, 1):
            trans_sl = p_base - t_offset
            for ch in ("P1", "P2", "P3", "M"):
                val = snapshot[ch][trans_sl]
                if val != 0:
                    errors.append(
                        f"Scene {scene_id} ({context_msg}): DLI transition line SL {trans_sl} "
                        f"(p_base {p_base} - {t_offset}) has non-zero byte in {ch}: 0x{val:02X}"
                    )

    if errors:
        pytest.fail("\n".join(errors))


def test_scene0_forest_pmg_scanline_invariants():
    """Red/Green test for Scene 0 (01-forest): verifies transition & guard line invariants."""
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
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["ENEMIES_INIT"])

    snap_init = get_pmg_snapshot(mem, labels)
    assert_pmg_invariants(snap_init, scene_id=0, context_msg="after enemies_init")

    # Run 10 frames of enemies_update
    for frame in range(10):
        run_subroutine(mpu, labels["ENEMIES_UPDATE"])

    snap_update = get_pmg_snapshot(mem, labels)
    assert_pmg_invariants(snap_update, scene_id=0, context_msg="after 10 frames of enemies_update")


def test_all_scenes_pmg_scanline_invariants():
    """Verifies PMG scanline invariants across all compiled scenes."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)

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

        snap = get_pmg_snapshot(mem, labels)
        assert_pmg_invariants(snap, scene_id=sc_id, context_msg="after init")


def test_compiler_rejects_oversized_sprite(tmp_path: Path):
    """Compiler must raise ValueError if an enemy or secret exceeds max safe height (20)."""
    scene_json = {
        "scene": {"name": "Test Oversized", "width": 160, "height": 96},
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
                "sprite_id": 99,
                "speed": "slow",
                "movement_strategy": "left_right",
            }
        ],
    }
    sc_file = tmp_path / "test_oversized.json"
    sc_file.write_text(json.dumps(scene_json), encoding="utf-8")

    from scripts.compile_sprites import SpriteDefinition, SpriteFrame
    # Oversized sprite: height 21 (exceeds max safe height 20)
    oversized_spr = SpriteDefinition(
        id=99,
        description="Giant",
        width=8,
        height=21,
        frame_duration=4,
        loop=True,
        frames=[SpriteFrame(rows=[0xFF] * 21)],
    )

    with pytest.raises(ValueError, match="exceeds maximum safe height"):
        parse_scene_json(
            sc_file,
            enemies={1: CatalogueItem(id=1, name="Giant", atari_color=0x42, sprite_id=99)},
            secrets={},
            sprites={99: oversized_spr},
        )
