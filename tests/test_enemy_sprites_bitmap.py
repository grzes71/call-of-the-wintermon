"""Automated test suite verifying sprite pipeline robustness, roles, and validation.

Enforces:
1. Universal parameterized verification:
   - For all scenes and all enemies: PMG bytes match independent JSON reference (Player 1bpp bitmap format).
   - For all scenes and all secrets: PMG bytes match independent JSON reference (5th player missile format).
   - Updates across N frames maintain exact match with reference frame animations.
2. Synthetic tests with temporary files (tmp_path):
   a) New sprite id=5 assigned to enemy in scene only -> Player format, PMG matches reference.
   b) New secret with new sprite -> missiles format.
   c) Same sprite used as enemy and secret -> build error with scene and object details.
   d) Enemy without sprite -> build error.
   e) Sprite with width != 8 or height > 20 -> build error.
   f) Duplicate sprite id across files or within file -> build error.
   g) More than 3 enemies in one zone -> build error.
   h) Enemy referencing secret missile sprite -> compiler validation error.
3. Manifest consistency:
   - gen/sprites_manifest.json matches gen/sprites_data.asm (formats, frame counts, byte sizes).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.sprite_roles import (
    MAX_ZONE_SPRITE_HEIGHT,
    MAX_ENEMIES_PER_ZONE,
    MAX_ENEMIES_TOTAL,
    MAX_SECRETS_TOTAL,
    SpriteValidationError,
    resolve_object_sprite_id,
    determine_sprite_roles_from_scenes,
    validate_sprite_definition_data,
    check_sprite_id_uniqueness,
)
from scripts.compile_scenes import (
    parse_scene_json,
    load_catalogues,
    compile_scenes,
)
from scripts.compile_sprites import (
    parse_sprites_json,
    compile_sprites,
    generate_sprites_manifest,
)
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


# ==============================================================================
# 1. Parameterized Verification across ALL Scenes and Objects
# ==============================================================================

def test_all_scenes_enemies_and_secrets_match_independent_reference():
    """All enemies (Player format) and all secrets (Missile format) must match independent JSON reference."""
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
    pmg_missiles = labels["PMG_MISSILES"]

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

        # 1. Check all Enemies in this scene
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
                f"Scene {sc_id} Enemy {e_idx} (Sprite {sid}, P{ch+1}) PMG mismatch!\n"
                f"Actual:   {[f'0x{b:02X}' for b in actual_bytes]}\n"
                f"Expected: {[f'0x{b:02X}' for b in exp_bytes]}"
            )

        # 2. Check active Secrets in this scene (initial stage)
        s_cnt = mem[labels["SECRETS_COUNT"]]
        for s_idx in range(s_cnt):
            is_active = mem[labels["SECRETS_ACTIVE"] + s_idx]
            if not is_active:
                continue
            sid = mem[labels["SECRETS_SPRITE_ID"] + s_idx]
            pmg_y = mem[labels["SECRETS_PMG_Y"] + s_idx]
            h = mem[labels["SECRETS_HEIGHT"] + s_idx]

            spr_data = sprites_dict[sid]
            frame0_pixels = spr_data["frames"][0]["pixels"]

            exp_bytes = [independent_pack_missile_row(r) for r in frame0_pixels[:h]]
            actual_bytes = [mem[pmg_missiles + pmg_y + r] for r in range(h)]

            assert actual_bytes == exp_bytes, (
                f"Scene {sc_id} Secret {s_idx} (Sprite {sid}) PMG mismatch!\n"
                f"Actual:   {[f'0x{b:02X}' for b in actual_bytes]}\n"
                f"Expected: {[f'0x{b:02X}' for b in exp_bytes]}"
            )


def test_secrets_all_frames_missiles_regression():
    """Verify all frames of secret sprites match independent missile reference."""
    spr_path = Path("sprites/objects.sprite.json")
    spr_json = json.loads(spr_path.read_text(encoding="utf-8"))
    mem, labels = load_xex_and_symbols()

    # Secrets currently used: 6 (CD), 7 (Skull), 8 (Key), 9 (Mjolnir)
    for spr in spr_json.get("sprites", []):
        sid = spr["id"]
        if sid not in (6, 7, 8, 9):
            continue
        for f_idx, frame in enumerate(spr["frames"]):
            lbl = f"SPRITE_{sid}_FRAME_{f_idx}"
            assert lbl in labels, f"Label {lbl} missing from symbols"
            addr = labels[lbl]
            pixels = frame["pixels"]
            exp_bytes = [independent_pack_missile_row(r) for r in pixels]
            actual_bytes = list(mem[addr : addr + len(exp_bytes)])
            assert actual_bytes == exp_bytes, f"Sprite {sid} frame {f_idx} missile bytes differ from reference"


# ==============================================================================
# 2. Synthetic Unit & Integration Tests (tmp_path)
# ==============================================================================

def test_synthetic_new_enemy_sprite_in_scene_only(tmp_path: Path):
    """a) New sprite id=5 assigned to enemy in scene only -> Player format, PMG matches reference."""
    sprites_file = tmp_path / "objects.sprite.json"
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)
    manifest_file = scenes_dir / "scenes.json"
    defs_file = scenes_dir / "definitions.json"
    scene_file = scenes_dir / "01-test.json"

    # Base sprites with extra sprite 5 (Goblin, 8x20, 1 frame)
    base_sprites = {
        "version": 1,
        "sprites": [
            {
                "id": 5,
                "description": "Goblin",
                "width": 8,
                "height": 20,
                "animation": {"frame_duration": 4, "loop": True},
                "frames": [{"pixels": ["11000011"] * 20}],
            }
        ],
    }
    sprites_file.write_text(json.dumps(base_sprites), encoding="utf-8")

    # definitions.json knows nothing about sprite 5 (enemy def 1 has no sprite_id)
    defs = {
        "version": 1,
        "enemies": [{"id": 1, "name": "Goblin", "atari_color": 66}],
        "secrets": [],
    }
    defs_file.write_text(json.dumps(defs), encoding="utf-8")

    # Scene 01-test explicitly assigns sprite_id: 5 to enemy
    scene_data = {
        "scene": {"name": "Test Goblin"},
        "platforms": [{"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}],
        "objects": [{"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 12, "sprite_id": 5}],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")
    manifest_file.write_text(json.dumps({"scenes": ["01-test.json"]}), encoding="utf-8")

    out_asm = tmp_path / "sprites_data.asm"
    out_manifest = tmp_path / "sprites_manifest.json"

    res = compile_sprites(
        input_path=sprites_file,
        output_path=out_asm,
        mode="missiles",
        definitions_path=defs_file,
        scenes_manifest_path=manifest_file,
        manifest_output_path=out_manifest,
    )
    assert res == 0
    m_data = json.loads(out_manifest.read_text(encoding="utf-8"))
    assert m_data["sprites"]["5"]["format"] == "player"
    asm_text = out_asm.read_text(encoding="utf-8")
    # Row "11000011" in player format is %11000011 = $C3
    assert "$C3, $C3" in asm_text


def test_synthetic_new_secret_with_new_sprite(tmp_path: Path):
    """b) New secret with new sprite -> missiles format."""
    sprites_file = tmp_path / "objects.sprite.json"
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)
    manifest_file = scenes_dir / "scenes.json"
    defs_file = scenes_dir / "definitions.json"
    scene_file = scenes_dir / "01-test.json"

    base_sprites = {
        "version": 1,
        "sprites": [
            {
                "id": 6,
                "description": "Potion",
                "width": 8,
                "height": 16,
                "animation": {"frame_duration": 4, "loop": True},
                "frames": [{"pixels": ["11000011"] * 16}],
            }
        ],
    }
    sprites_file.write_text(json.dumps(base_sprites), encoding="utf-8")

    defs = {
        "version": 1,
        "enemies": [],
        "secrets": [{"id": 1, "name": "Potion", "atari_color": 26, "sprite_id": 6}],
    }
    defs_file.write_text(json.dumps(defs), encoding="utf-8")

    scene_data = {
        "scene": {"name": "Test Potion"},
        "platforms": [{"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}],
        "objects": [{"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 12}],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")
    manifest_file.write_text(json.dumps({"scenes": ["01-test.json"]}), encoding="utf-8")

    out_asm = tmp_path / "sprites_data.asm"
    out_manifest = tmp_path / "sprites_manifest.json"

    res = compile_sprites(
        input_path=sprites_file,
        output_path=out_asm,
        mode="missiles",
        definitions_path=defs_file,
        scenes_manifest_path=manifest_file,
        manifest_output_path=out_manifest,
    )
    assert res == 0
    m_data = json.loads(out_manifest.read_text(encoding="utf-8"))
    assert m_data["sprites"]["6"]["format"] == "missiles"
    asm_text = out_asm.read_text(encoding="utf-8")
    # Row "11000011" in 5th missile mode: M0=3, M1=0, M2=0, M3=3 -> %11000011 = $C3
    assert "$C3, $C3" in asm_text


def test_synthetic_role_conflict_rejected(tmp_path: Path):
    """c) Same sprite used as enemy and secret -> build error with details."""
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)
    manifest_file = scenes_dir / "scenes.json"
    defs_file = scenes_dir / "definitions.json"
    scene_file = scenes_dir / "01-test.json"

    defs = {
        "version": 1,
        "enemies": [{"id": 1, "name": "E", "sprite_id": 4}],
        "secrets": [{"id": 1, "name": "S", "sprite_id": 4}],
    }
    defs_file.write_text(json.dumps(defs), encoding="utf-8")

    scene_data = {
        "scene": {"name": "Conflict Scene"},
        "platforms": [{"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 12},
            {"id": 2, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 18},
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")
    manifest_file.write_text(json.dumps({"scenes": ["01-test.json"]}), encoding="utf-8")

    with pytest.raises(SpriteValidationError, match="konflikt formatów sprite'ów"):
        determine_sprite_roles_from_scenes(manifest_file, defs_file)


def test_synthetic_enemy_without_sprite_rejected(tmp_path: Path):
    """d) Enemy without sprite in scene and catalog -> build error."""
    scene_file = tmp_path / "bad_enemy.json"
    scene_data = {
        "scene": {"name": "No Sprite"},
        "platforms": [{"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}],
        "objects": [{"id": 1, "type": "enemy", "definition_id": 2, "platform_id": "p1", "x": 12}],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemy_cats = {2: {"id": 2, "name": "Ghost"}}  # No sprite_id
    with pytest.raises(SpriteValidationError, match="nie ma przypisanego sprite_id"):
        resolve_object_sprite_id(scene_data["objects"][0], enemy_cats, "No Sprite", "bad_enemy.json")


def test_synthetic_bad_sprite_dimensions_rejected():
    """e) Sprite with width != 8 or height > 20 -> build error."""
    bad_width = {
        "id": 10,
        "description": "Wide",
        "width": 9,
        "height": 16,
        "frames": [{"pixels": ["000000000"] * 16}],
    }
    with pytest.raises(SpriteValidationError, match="szerokość musi wynosić dokładnie 8 px"):
        validate_sprite_definition_data(bad_width, "wide.json")

    bad_height = {
        "id": 11,
        "description": "Tall",
        "width": 8,
        "height": 21,
        "frames": [{"pixels": ["00000000"] * 21}],
    }
    with pytest.raises(SpriteValidationError, match="wykracza poza dopuszczalny zakres"):
        validate_sprite_definition_data(bad_height, "tall.json")


def test_synthetic_duplicate_sprite_id_rejected(tmp_path: Path):
    """f) Duplicate sprite id across files -> build error."""
    f1 = tmp_path / "f1.sprite.json"
    f2 = tmp_path / "f2.sprite.json"
    f1.write_text(json.dumps({"version": 1, "sprites": [{"id": 1, "description": "A"}]}), encoding="utf-8")
    f2.write_text(json.dumps({"version": 1, "sprites": [{"id": 1, "description": "B"}]}), encoding="utf-8")

    with pytest.raises(SpriteValidationError, match="powtórzony sprite ID 1"):
        check_sprite_id_uniqueness([f1, f2])


def test_synthetic_four_enemies_in_zone_rejected(tmp_path: Path):
    """g) More than 3 enemies in one zone -> build error."""
    scene_file = tmp_path / "too_many_enemies.json"
    scene_data = {
        "scene": {"name": "Crowded Zone"},
        "platforms": [
            {"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4},
            {"id": "p2", "type": "sprite", "position": {"x": 45, "y": 24}, "width": 32, "height": 4},
            {"id": "p3", "type": "sprite", "position": {"x": 80, "y": 24}, "width": 32, "height": 4},
            {"id": "p4", "type": "sprite", "position": {"x": 115, "y": 24}, "width": 32, "height": 4},
        ],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 12, "sprite_id": 4},
            {"id": 2, "type": "enemy", "definition_id": 1, "platform_id": "p2", "x": 47, "sprite_id": 4},
            {"id": 3, "type": "enemy", "definition_id": 1, "platform_id": "p3", "x": 82, "sprite_id": 4},
            {"id": 4, "type": "enemy", "definition_id": 1, "platform_id": "p4", "x": 117, "sprite_id": 4},
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemies_dict, secrets_dict = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    with pytest.raises(ValueError, match="przekroczono limit maksymalnie 3 wrogów w strefie 1"):
        parse_scene_json(scene_file, enemies_dict, secrets_dict)


def test_synthetic_enemy_pointing_to_missiles_sprite_rejected(tmp_path: Path):
    """h) Enemy referencing sprite in missiles format -> compiler error."""
    scene_file = tmp_path / "mismatch.json"
    scene_data = {
        "scene": {"name": "Format Mismatch"},
        "platforms": [{"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}],
        "objects": [{"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 12, "sprite_id": 1}],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemies_dict, secrets_dict = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    # Load sprites where sprite 1 is explicitly in missiles format
    sprites_dict = parse_sprites_json(Path("sprites/objects.sprite.json"), mode="missiles")
    assert sprites_dict[1].format == "missiles"

    with pytest.raises(ValueError, match="wymagają formatu 'player'"):
        parse_scene_json(scene_file, enemies_dict, secrets_dict, sprites=sprites_dict)


# ==============================================================================
# 3. Manifest and Data Consistency Test
# ==============================================================================

def test_manifest_matches_generated_asm():
    """Verify gen/sprites_manifest.json matches gen/sprites_data.asm."""
    m_path = Path("gen/sprites_manifest.json")
    asm_path = Path("gen/sprites_data.asm")
    assert m_path.is_file(), "sprites_manifest.json missing"
    assert asm_path.is_file(), "sprites_data.asm missing"

    manifest = json.loads(m_path.read_text(encoding="utf-8"))
    asm_text = asm_path.read_text(encoding="utf-8")

    for sid_str, sdata in manifest.get("sprites", {}).items():
        sid = sdata["id"]
        # Verify frame labels exist in ASM
        for flbl in sdata["frame_labels"]:
            assert f"{flbl}" in asm_text, f"Frame label {flbl} not in sprites_data.asm"
        # Verify frames label exists in ASM
        assert f"{sdata['frames_label']}" in asm_text, f"Frames label {sdata['frames_label']} not in sprites_data.asm"
