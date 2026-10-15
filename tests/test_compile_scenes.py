"""Tests for scene compiler (scripts/compile_scenes.py)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.compile_scenes import (
    compile_scenes,
    load_catalogues,
    parse_scene_json,
    generate_scenes_asm,
    sanitize_symbol,
    resolve_tileset_id,
    char_to_atari_screencode,
    text_to_screencodes_line,
)


def test_char_to_atari_screencode():
    assert char_to_atari_screencode(" ") == 0
    assert char_to_atari_screencode("A") == 65 - 32
    assert char_to_atari_screencode("a") == 97
    assert char_to_atari_screencode("Ą") == 65
    assert char_to_atari_screencode("ę") == 83


def test_text_to_screencodes_line():
    line = text_to_screencodes_line("Test", width=40)
    assert len(line) == 40
    # Centered: (40 - 4) // 2 = 18 spaces
    assert line[:18] == [0] * 18
    assert line[18:22] == [
        char_to_atari_screencode("T"),
        char_to_atari_screencode("e"),
        char_to_atari_screencode("s"),
        char_to_atari_screencode("t"),
    ]
    assert line[22:] == [0] * 18


def test_sanitize_symbol():
    assert sanitize_symbol("01-forest") == "sc_01_forest"
    assert sanitize_symbol("02-forest-castle") == "sc_02_forest_castle"
    assert sanitize_symbol("forest_level") == "forest_level"


def test_resolve_tileset_id():
    assert resolve_tileset_id("tiles/castles.png") == 0
    assert resolve_tileset_id("tiles/depths.png") == 1
    assert resolve_tileset_id("tiles/hell.png") == 2
    assert resolve_tileset_id("tiles/trees.png") == 3
    assert resolve_tileset_id(None) == 3


def test_load_catalogues():
    enemies, secrets = load_catalogues(Path("enemies.json"), Path("secrets.json"))
    assert 1 in enemies
    assert enemies[1].name == "Azathoth"
    assert enemies[1].atari_color == 66  # $42
    assert 1 in secrets
    assert secrets[1].name == "Gold Key"
    assert secrets[1].atari_color == 26  # $1A
    assert 2 in secrets
    assert secrets[2].blink is True


def test_parse_01_forest_scene():
    enemies, secrets = load_catalogues(Path("enemies.json"), Path("secrets.json"))
    scene = parse_scene_json(Path("scenes/01-forest.json"), enemies, secrets)

    assert scene.name == "The Forest Whispers My Name"
    assert scene.width == 160
    assert scene.height == 96
    assert scene.primary_tileset_id == 3  # trees
    assert len(scene.elements) == 5
    assert len(scene.platforms) == 11
    assert len(scene.objects) == 6

    # Verify enemy 1
    obj1 = scene.objects[0]
    assert obj1.type_code == 0  # enemy
    assert obj1.def_id == 1  # Azathoth
    assert obj1.speed_code == 0  # slow
    assert obj1.strategy_code == 1  # left_right
    assert obj1.atari_color == 66

    # Verify secret with blink
    exit_door = [o for o in scene.objects if o.def_id == 2 and o.type_code == 1][0]
    assert exit_door.blink is True
    assert exit_door.atari_color == 72


def test_parse_02_forest_castle_scene():
    enemies, secrets = load_catalogues(Path("enemies.json"), Path("secrets.json"))
    scene = parse_scene_json(Path("scenes/02-forest-castle.json"), enemies, secrets)

    assert scene.name == "Be Quick or Be Dead"
    assert len(scene.elements) == 4
    assert len(scene.platforms) == 14
    assert len(scene.objects) == 4


def test_compile_scenes_full_pipeline(tmp_path):
    out_asm = tmp_path / "scenes_data.asm"
    res = compile_scenes(
        manifest_path=Path("scenes/scenes.json"),
        output_path=out_asm,
        scenes_dir=Path("scenes"),
        enemies_path=Path("enemies.json"),
        secrets_path=Path("secrets.json"),
    )
    assert res == 0
    assert out_asm.is_file()

    content = out_asm.read_text(encoding="utf-8")
    assert "SCENE_COUNT = 2" in content
    assert "SCENE_SC_01_FOREST_ID = 0" in content
    assert "SCENE_SC_02_FOREST_CASTLE_ID = 1" in content
    assert "scene_sc_01_forest_name" in content
    assert "scene_sc_02_forest_castle_name" in content
    assert "scene_name_lo" in content
    assert "scene_name_hi" in content
    assert "scene_elem_count" in content
    assert "scene_plat_count" in content
    assert "scene_obj_count" in content


def test_compile_scenes_missing_manifest(tmp_path):
    res = compile_scenes(
        manifest_path=tmp_path / "non_existent.json",
        output_path=tmp_path / "out.asm",
    )
    assert res != 0


def test_compile_scenes_missing_referenced_file(tmp_path):
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps({"scenes": ["does_not_exist.json"]}), encoding="utf-8")
    res = compile_scenes(
        manifest_path=bad_manifest,
        output_path=tmp_path / "out.asm",
        scenes_dir=tmp_path,
    )
    assert res != 0


def test_mads_symbols_present_in_built_xex():
    lab_file = Path("gen/main.lab")
    if not lab_file.is_file():
        pytest.skip("main.lab not found, build XEX first")

    lab_text = lab_file.read_text(encoding="utf-8")
    expected_symbols = [
        "SCENE_COUNT",
        "SCENE_SC_01_FOREST_ID",
        "SCENE_SC_02_FOREST_CASTLE_ID",
        "scene_sc_01_forest_name",
        "scene_sc_02_forest_castle_name",
        "scene_sc_01_forest_name_line",
        "scene_sc_02_forest_castle_name_line",
        "scene_name_line_lo",
        "scene_name_line_hi",
        "dlist_scene_title",
        "scene_elem_count",
        "scene_plat_count",
        "scene_obj_count",
        "scene_plat_x_lo",
        "scene_plat_x_hi",
        "scene_obj_x_lo",
        "scene_obj_x_hi",
    ]
    for sym in expected_symbols:
        assert sym.lower() in lab_text.lower(), f"Symbol {sym} missing from MADS labels."
