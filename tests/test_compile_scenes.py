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
    PAS_Y_COORDS,
    PlatformData,
    SceneDliCompiledData,
    validate_scene_dli_platforms,
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
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    assert 1 in enemies
    assert enemies[1].name == "Azathoth"
    assert enemies[1].atari_color == 66  # $42
    assert 1 in secrets
    assert secrets[1].name == "Gold Key"
    assert secrets[1].atari_color == 26  # $1A
    assert 2 in secrets
    assert secrets[2].blink is True


def test_parse_01_forest_scene():
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
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
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
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
        definitions_path=Path("scenes/definitions.json"),
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


def test_scene_dli_data_matches_json():
    manifest_path = Path("scenes/scenes.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    for scene_file_name in manifest["scenes"]:
        scene_path = Path("scenes") / scene_file_name
        scene_data = parse_scene_json(scene_path, enemies, secrets)
        dli = scene_data.dli_data
        assert dli is not None, f"DLI data missing for {scene_path}"

        for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
            pas_plats = [p for p in scene_data.platforms if p.y == pas_y]
            all_hpos = [
                dli.hpos_p1[pas_idx],
                dli.hpos_p2[pas_idx],
                dli.hpos_p3[pas_idx],
                dli.hpos_m0[pas_idx],
                dli.hpos_m1[pas_idx],
                dli.hpos_m2[pas_idx],
                dli.hpos_m3[pas_idx],
            ]

            # 1. & 2. Every platform from JSON has a corresponding HPOS (48 + p.x)
            for p in pas_plats:
                expected_hpos = 48 + p.x
                assert expected_hpos in all_hpos, (
                    f"Platform {p.id} in {scene_file_name} at y={pas_y}, x={p.x} "
                    f"(expected HPOS {expected_hpos}) missing from DLI tables: {all_hpos}"
                )

            # 3. For platforms with width > 32, verify they occupy consecutive channels
            for p in pas_plats:
                if p.type_code == 0 and p.width > 32:
                    segs_32 = p.width // 32
                    exp_hpos_list = [48 + p.x + s * 32 for s in range(segs_32)]
                    hpos_p_vals = [dli.hpos_p1[pas_idx], dli.hpos_p2[pas_idx], dli.hpos_p3[pas_idx]]
                    assert exp_hpos_list[0] in hpos_p_vals
                    start_ch = hpos_p_vals.index(exp_hpos_list[0])
                    for s_idx, exp_hpos in enumerate(exp_hpos_list):
                        ch = start_ch + s_idx
                        assert ch < len(hpos_p_vals)
                        assert hpos_p_vals[ch] == exp_hpos, (
                            f"Platform {p.id} segment {s_idx} expected at channel {ch} "
                            f"with HPOS {exp_hpos}, got {hpos_p_vals[ch]}"
                        )

            # 4. Verify no platform was overwritten by another
            # In 01-forest pas 1 (y=24): exactly 3 distinct platforms (x=15, 56, 96) -> P1, P2, P3
            if scene_file_name == "01-forest.json" and pas_y == 24:
                assert dli.hpos_p1[1] == 48 + 15  # $3F (platform-013)
                assert dli.hpos_p2[1] == 48 + 56  # $68 (platform-011)
                assert dli.hpos_p3[1] == 48 + 96  # $90 (platform-010)

            # In 01-forest pas 5 (y=88): 96px sprite (P1..P3) + 32px missile (M0..M3)
            if scene_file_name == "01-forest.json" and pas_y == 88:
                assert dli.hpos_p1[5] == 48 + 48        # $60
                assert dli.hpos_p2[5] == 48 + 48 + 32   # $80
                assert dli.hpos_p3[5] == 48 + 48 + 64   # $A0
                assert dli.hpos_m0[5] == 48 + 16        # $40
                assert dli.hpos_m1[5] == 48 + 16 + 8    # $48
                assert dli.hpos_m2[5] == 48 + 16 + 16   # $50
                assert dli.hpos_m3[5] == 48 + 16 + 24   # $58


def test_validate_scene_dli_platforms_rejects_invalid():
    # Helper to construct dummy SceneDliCompiledData
    def make_dummy_dli():
        return SceneDliCompiledData(
            hpos_p1=[0]*6, hpos_p2=[0]*6, hpos_p3=[0]*6,
            hpos_m0=[0]*6, hpos_m1=[0]*6, hpos_m2=[0]*6, hpos_m3=[0]*6,
            sizep1=[0]*6, sizep2=[0]*6, sizep3=[0]*6, sizem=[0]*6,
            bg_colpf0=[0]*6, bg_colpf1=[0]*6, bg_colpf2=[0]*6,
            pas_c1_sl=[[0]*6 for _ in range(8)],
            pas_c2_sl=[[0]*6 for _ in range(8)],
            pas_c3_sl=[[0]*6 for _ in range(8)],
            zone_hpos_p1=[0]*6, zone_col_p1=[0]*6,
            zone_hpos_p2=[0]*6, zone_col_p2=[0]*6,
            zone_hpos_p3=[0]*6, zone_col_p3=[0]*6,
            zone_hpos_m0=[0]*6, zone_hpos_m1=[0]*6,
            zone_hpos_m2=[0]*6, zone_hpos_m3=[0]*6,
            zone_secret_col=[0]*6, zone_prior=[0]*6,
            z0_hpos_p1=0, z0_col_p1=0, z0_hpos_p2=0, z0_col_p2=0,
            z0_hpos_p3=0, z0_col_p3=0, z0_hpos_m0=0, z0_hpos_m1=0,
            z0_hpos_m2=0, z0_hpos_m3=0, z0_secret_col=0, z0_prior=0,
            z0_colpf0=0, z0_colpf1=0, z0_colpf2=0,
        )

    # 1. Total width > 128 px
    plats_wide = [
        PlatformData(id="p1", type_code=0, x=0, y=8, width=96, height=4),
        PlatformData(id="p2", type_code=0, x=96, y=8, width=48, height=4),
    ]
    with pytest.raises(ValueError, match="exceeds maximum limit of 128 px"):
        validate_scene_dli_platforms(plats_wide, make_dummy_dli(), "test")

    # 2. Unsupported platform width
    plats_bad_width = [PlatformData(id="p1", type_code=0, x=10, y=8, width=50, height=4)]
    with pytest.raises(ValueError, match="unsupported width 50 px"):
        validate_scene_dli_platforms(plats_bad_width, make_dummy_dli(), "test")

    # 3. Missing HPOS for platform
    plats_missing = [PlatformData(id="p1", type_code=0, x=10, y=8, width=32, height=4)]
    dummy_dli = make_dummy_dli()  # all hpos are 0
    dummy_dli.sizep1[0] = 3
    with pytest.raises(ValueError, match="has no corresponding HPOS"):
        validate_scene_dli_platforms(plats_missing, dummy_dli, "test")

    # 4. Non-consecutive channels for platform > 32 px
    plats_skip = [PlatformData(id="p1", type_code=0, x=0, y=8, width=64, height=4)]
    dummy_skip = make_dummy_dli()
    dummy_skip.hpos_p1[0] = 48 + 0   # segment 0 in P1
    dummy_skip.hpos_p2[0] = 0        # skip!
    dummy_skip.hpos_p3[0] = 48 + 32  # segment 1 in P3
    with pytest.raises(ValueError, match="do not occupy consecutive channels without skips"):
        validate_scene_dli_platforms(plats_skip, dummy_skip, "test")

    # 5. SIZEP mismatch for platform
    plats_bad_sizep = [PlatformData(id="p1", type_code=0, x=0, y=8, width=32, height=4)]
    dummy_bad_sizep = make_dummy_dli()
    dummy_bad_sizep.hpos_p1[0] = 48 + 0
    dummy_bad_sizep.sizep1[0] = 1  # Expected 3, given 1!
    with pytest.raises(ValueError, match="requires SIZEP=3, got 1"):
        validate_scene_dli_platforms(plats_bad_sizep, dummy_bad_sizep, "test")

    # 6. SIZEM mismatch for missile platform
    plats_bad_sizem = [PlatformData(id="p_m", type_code=1, x=16, y=88, width=32, height=4)]
    dummy_bad_sizem = make_dummy_dli()
    dummy_bad_sizem.hpos_m0[5] = 48 + 16
    dummy_bad_sizem.hpos_m1[5] = 48 + 16 + 8
    dummy_bad_sizem.hpos_m2[5] = 48 + 16 + 16
    dummy_bad_sizem.hpos_m3[5] = 48 + 16 + 24
    dummy_bad_sizem.sizem[5] = 0x00  # Expected 0xFF!
    with pytest.raises(ValueError, match="requires SIZEM=\\$FF"):
        validate_scene_dli_platforms(plats_bad_sizem, dummy_bad_sizem, "test")


def test_sizep_matches_platform_width():
    manifest_path = Path("scenes/scenes.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    for scene_file_name in manifest["scenes"]:
        scene_path = Path("scenes") / scene_file_name
        scene_data = parse_scene_json(scene_path, enemies, secrets)
        dli = scene_data.dli_data
        assert dli is not None

        for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
            pas_plats = [p for p in scene_data.platforms if p.y == pas_y]
            sprite_plats = sorted([p for p in pas_plats if p.type_code == 0], key=lambda p: p.x)
            ch_p = 0
            sizep_vals = [dli.sizep1[pas_idx], dli.sizep2[pas_idx], dli.sizep3[pas_idx]]
            for p in sprite_plats:
                if p.width == 32:
                    expected_segs = [(32, 3)]
                elif p.width == 16:
                    expected_segs = [(16, 1)]
                elif p.width == 8:
                    expected_segs = [(8, 0)]
                elif p.width == 48:
                    expected_segs = [(32, 3), (16, 1)]
                elif p.width == 64:
                    expected_segs = [(32, 3), (32, 3)]
                elif p.width == 96:
                    expected_segs = [(32, 3), (32, 3), (32, 3)]
                elif p.width == 24:
                    expected_segs = [(16, 1), (8, 0)]
                else:
                    pytest.fail(f"Unexpected width {p.width} in {scene_file_name}")

                for seg_w, exp_sz in expected_segs:
                    assert ch_p < 3, f"Too many platform segments in {scene_file_name} pas {pas_idx}"
                    assert sizep_vals[ch_p] == exp_sz, (
                        f"Platform {p.id} ({p.width}px, seg {seg_w}px) at pas {pas_idx} "
                        f"expected SIZEP={exp_sz} at ch {ch_p}, got {sizep_vals[ch_p]}"
                    )
                    ch_p += 1


def test_sizem_for_missile_platforms():
    manifest_path = Path("scenes/scenes.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    for scene_file_name in manifest["scenes"]:
        scene_path = Path("scenes") / scene_file_name
        scene_data = parse_scene_json(scene_path, enemies, secrets)
        dli = scene_data.dli_data
        assert dli is not None

        for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
            pas_plats = [p for p in scene_data.platforms if p.y == pas_y]
            missile_plats = [p for p in pas_plats if p.type_code == 1]
            if missile_plats:
                # In 01-forest, pas 5 has platform-014 (32 px missile)
                has_32 = any(p.width == 32 for p in missile_plats)
                if has_32:
                    assert dli.sizem[pas_idx] == 0xFF, (
                        f"Scene {scene_file_name} pas {pas_idx} has 32px missile platform, "
                        f"expected SIZEM=$FF, got ${dli.sizem[pas_idx]:02X}"
                    )
            else:
                assert dli.sizem[pas_idx] == 0x00, (
                    f"Scene {scene_file_name} pas {pas_idx} has no missile platform, "
                    f"expected SIZEM=$00, got ${dli.sizem[pas_idx]:02X}"
                )




