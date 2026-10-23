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
    text_to_screencodes_line_at,
    STATUS_LINE_WIDTH,
    STATUS_NAME_COL,
    status_name_max,
    status_special_total,
    PAS_Y_COORDS,
    PlatformData,
    SceneDliCompiledData,
    validate_scene_dli_platforms,
)
from tests.scene_expectations import special_secret_total


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


def test_text_to_screencodes_line_at_status_line_layout():
    """Status-line variant: left-aligned at STATUS_NAME_COL, truncated to `max_len`."""
    max_len = 8
    line = text_to_screencodes_line_at("Forest", start_col=STATUS_NAME_COL,
                                       width=STATUS_LINE_WIDTH, max_len=max_len)
    assert len(line) == STATUS_LINE_WIDTH
    # Columns 0..2 hold the lives and column 3 the spacer, so the name starts at column 4.
    assert line[:STATUS_NAME_COL] == [0] * STATUS_NAME_COL
    assert line[STATUS_NAME_COL] == char_to_atari_screencode("F")
    assert line[STATUS_NAME_COL:STATUS_NAME_COL + 6] == [
        char_to_atari_screencode(c) for c in "Forest"
    ]
    # Everything after the text is blank - including the icon row on the right.
    assert line[STATUS_NAME_COL + 6:] == [0] * (STATUS_LINE_WIDTH - STATUS_NAME_COL - 6)

    # A name longer than the reserved area is truncated at `max_len`.
    long_line = text_to_screencodes_line_at("X" * 60, start_col=STATUS_NAME_COL,
                                            width=STATUS_LINE_WIDTH, max_len=max_len)
    assert long_line[STATUS_NAME_COL:STATUS_NAME_COL + max_len] == (
        [char_to_atari_screencode("X")] * max_len
    )
    assert long_line[STATUS_NAME_COL + max_len:] == [0] * (
        STATUS_LINE_WIDTH - STATUS_NAME_COL - max_len
    )


def test_status_line_reserves_columns_for_special_icons():
    """The HUD scene name must stop before the special-secret icon row (Rule 05).

    The icon row is as wide as the number of special secrets placed in all scenes, and
    the compiled HUD line must leave those columns blank - otherwise a collected icon
    would overwrite the scene name.
    """
    manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    scenes = [
        parse_scene_json(Path("scenes") / name, enemies, secrets) for name in manifest["scenes"]
    ]

    total = status_special_total(scenes)
    assert total == special_secret_total(), "compiler total must match the raw scene JSON"
    name_max = status_name_max(total)
    assert name_max == STATUS_LINE_WIDTH - STATUS_NAME_COL - total
    assert name_max >= 1, "the status line must still have room for the scene name"

    icon_start = STATUS_LINE_WIDTH - total
    for scene in scenes:
        hud = text_to_screencodes_line_at(
            scene.name, start_col=STATUS_NAME_COL, width=STATUS_LINE_WIDTH, max_len=name_max
        )
        assert hud[icon_start:] == [0] * total, (
            f"{scene.file_stem}: the HUD line must leave the icon row blank"
        )
        assert hud[STATUS_NAME_COL] != 0, f"{scene.file_stem}: the scene name must be present"


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
    """Catalogues must mirror scenes/definitions.json (Rule 05: no hardcoded values)."""
    raw = json.loads(Path("scenes/definitions.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    raw_enemies = {item["id"]: item for item in raw.get("enemies", [])}
    raw_secrets = {item["id"]: item for item in raw.get("secrets", [])}
    assert raw_enemies, "definitions.json must define enemies"
    assert raw_secrets, "definitions.json must define secrets"

    for defn_id, item in raw_enemies.items():
        assert defn_id in enemies, f"enemy {defn_id} missing from the loaded catalogue"
        assert enemies[defn_id].name == item["name"]
        assert enemies[defn_id].blink is bool(item.get("blink", False))
        assert enemies[defn_id].sprite_id == item.get("sprite_id")
        if "atari_color" in item:
            assert enemies[defn_id].atari_color == item["atari_color"]

    for defn_id, item in raw_secrets.items():
        assert defn_id in secrets, f"secret {defn_id} missing from the loaded catalogue"
        assert secrets[defn_id].name == item["name"]
        assert secrets[defn_id].blink is bool(item.get("blink", False))
        assert secrets[defn_id].sprite_id == item.get("sprite_id")
        assert secrets[defn_id].dependency == item.get("dependency")
        assert secrets[defn_id].special is bool(item.get("special", False))
        if "atari_color" in item:
            assert secrets[defn_id].atari_color == item["atari_color"]


def test_parse_01_forest_scene():
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    scene = parse_scene_json(Path("scenes/01-forest.json"), enemies, secrets)

    with open("scenes/01-forest.json", "r", encoding="utf-8") as f:
        raw_json = json.load(f)

    assert scene.name == raw_json["scene"]["name"]
    assert scene.width == raw_json["scene"]["width"]
    assert scene.height == raw_json["scene"]["height"]
    assert len(scene.elements) == len(raw_json["elements"])
    assert len(scene.platforms) == len(raw_json["platforms"])
    assert len(scene.objects) == len(raw_json["objects"])

    # Verify first enemy dynamically from raw JSON per Rule 05
    speed_map = {"slow": 0, "medium": 1, "fast": 2}
    strat_map = {"stationary": 0, "left_right": 1, "right_left": 2}
    obj1 = scene.objects[0]
    raw_obj1 = raw_json["objects"][0]
    assert obj1.type_code == (0 if raw_obj1["type"] == "enemy" else 1)
    assert obj1.def_id == raw_obj1["definition_id"]
    assert obj1.speed_code == speed_map.get(raw_obj1.get("speed", "slow"), 0)
    assert obj1.strategy_code == strat_map.get(raw_obj1.get("movement_strategy", "stationary"), 0)
    assert obj1.atari_color == enemies[obj1.def_id].atari_color

    # Secrets inherit blink and colour from their catalogue definitions - whatever the
    # current values are (no hardcoded definition ids or colours, Rule 05).
    for obj in scene.objects:
        if obj.type_code != 1:
            continue
        catalogue_secret = secrets[obj.def_id]
        assert obj.blink is catalogue_secret.blink, (
            f"secret def {obj.def_id}: compiled blink flag must match the catalogue"
        )
        assert obj.atari_color == catalogue_secret.atari_color, (
            f"secret def {obj.def_id}: compiled colour must match the catalogue"
        )


def test_parse_02_forest_castle_scene():
    """Scene 2 must compile every element/platform/object of its JSON (counts from the JSON)."""
    scene_path = Path("scenes/02-forest-castle.json")
    raw = json.loads(scene_path.read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    scene = parse_scene_json(scene_path, enemies, secrets)

    assert scene.name == raw["scene"]["name"]
    assert scene.width == raw["scene"]["width"]
    assert scene.height == raw["scene"]["height"]
    assert len(scene.elements) == len(raw["elements"])
    assert len(scene.platforms) == len(raw["platforms"])
    assert len(scene.objects) == len(raw["objects"])


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
    assert "scene_sc_01_forest_name_line" in content
    assert "scene_sc_02_forest_castle_name_line" in content
    assert "scene_name_line_lo" in content
    assert "scene_name_line_hi" in content
    assert "scene_sc_01_forest_hud_line" in content
    assert "scene_sc_02_forest_castle_hud_line" in content
    assert "scene_hud_line_lo" in content
    assert "scene_hud_line_hi" in content
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
        "scene_sc_01_forest_name_line",
        "scene_sc_02_forest_castle_name_line",
        "scene_name_line_lo",
        "scene_name_line_hi",
        "scene_sc_01_forest_hud_line",
        "scene_sc_02_forest_castle_hud_line",
        "scene_hud_line_lo",
        "scene_hud_line_hi",
        "dlist_scene_title",
        "scene_elem_count",
        "scene_plat_count",
        "scene_obj_count",
        "scene_plat_x_lo",
        "scene_plat_x_hi",
        "scene_secret_x_lo",
        "scene_secret_x_hi",
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
                assert dli.hpos_p2[1] == 48 + 63  # $6F (platform-011)
                assert dli.hpos_p3[1] == 48 + 96  # $90 (platform-010)

            # In 01-forest pas 5 (y=88): 96px sprite (P1..P3) + 32px missile (M0..M3)
            if scene_file_name == "01-forest.json" and pas_y == 88:
                assert dli.hpos_p1[5] == 48 + 48        # $60
                assert dli.hpos_p2[5] == 48 + 48 + 32   # $80
                assert dli.hpos_p3[5] == 48 + 48 + 64   # $A0
                p14 = next(p for p in pas_plats if p.id == "platform-014")
                assert dli.hpos_m0[5] == 48 + p14.x
                assert dli.hpos_m1[5] == 48 + p14.x + 8
                assert dli.hpos_m2[5] == 48 + p14.x + 16
                assert dli.hpos_m3[5] == 48 + p14.x + 24


def test_validate_scene_dli_platforms_rejects_invalid():
    # Helper to construct dummy SceneDliCompiledData
    def make_dummy_dli():
        return SceneDliCompiledData(
            hpos_p1=[0]*6, hpos_p2=[0]*6, hpos_p3=[0]*6,
            hpos_m0=[0]*6, hpos_m1=[0]*6, hpos_m2=[0]*6, hpos_m3=[0]*6,
            sizep1=[0]*6, sizep2=[0]*6, sizep3=[0]*6, sizem=[0]*6,
            bg_colpf0=[0]*6, bg_colpf1=[0]*6, bg_colpf2=[0]*6,
            pas_color_sl=[[0]*6 for _ in range(8)],
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


def test_pmg_patterns_match_platform_widths():
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    scene_data = parse_scene_json(Path("scenes/01-forest.json"), enemies, secrets)
    dli = scene_data.dli_data
    assert dli is not None
    assert dli.pmg_patterns is not None

    # Expected patterns for 01-forest:
    # pas 0: P1=32px ($FF), P2=32px ($FF), P3=32px ($FF)
    # pas 1: P1=32px ($FF), P2=32px ($FF), P3=32px ($FF)
    # pas 2: platform-008 is 16px -> P1 has $F0; P2=$FF, P3=$FF
    # pas 3: platform-006 (32px, $FF) + platform-012 (24px -> seg 16px $F0 + seg 8px $C0) -> P1=$FF, P2=$F0, P3=$C0
    # pas 4: platform-004 is 48px -> P1=32px ($FF), P2=16px ($F0); P3=$FF
    # pas 5: platform-002 is 96px -> P1=32px ($FF), P2=32px ($FF), P3=32px ($FF)
    expected_patterns = [
        0xFF, 0xFF, 0xFF,  # pas 0
        0xFF, 0xF0, 0xFF,  # pas 1 (platform-011 16px on P2)
        0xF0, 0xFF, 0xFF,  # pas 2 (platform-008 16px on P1)
        0xFF, 0xFF, 0xFF,  # pas 3 (platform-006 32px on P1, platform-012 32px on P2)
        0xFF, 0xF0, 0xFF,  # pas 4 (platform-004 48px -> P2 has $F0)
        0xFF, 0xFF, 0xFF,  # pas 5 (platform-002 96px)
    ]
    assert dli.pmg_patterns.patterns == expected_patterns

    # Also verify generated ASM contains correct pattern tables
    asm_text = Path("gen/scenes_dli_data.asm").read_text(encoding="utf-8")
    assert "scene_sc_01_forest_pmg_patterns" in asm_text
    assert ".byte $F0, $FF, $FF" in asm_text
    assert ".byte $FF, $F0, $FF" in asm_text
    assert "scene_pmg_patterns_lo" in asm_text
    assert "scene_pmg_patterns_hi" in asm_text


# ==============================================================================
# Game Scenes Invariants: Secret Presence & Row Color Profile Consistency
# ==============================================================================

def test_game_scenes_contain_at_least_one_secret():
    """All scenes included in the game manifest must contain at least one secret."""
    manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    for fname in manifest["scenes"]:
        sc_path = Path("scenes") / fname
        sc_data = parse_scene_json(sc_path, enemies, secrets, require_secret=True)
        assert len(sc_data.secrets) >= 1, f"Scene '{sc_data.name}' ({fname}) must contain at least one secret."


def test_compile_scenes_rejects_game_scene_without_secrets(tmp_path: Path):
    """Game scenes missing secrets must fail compilation with a descriptive error."""
    scene_file = tmp_path / "no_secrets.json"
    scene_data = {
        "scene": {"name": "Empty of Secrets", "width": 160, "height": 96},
        "platforms": [
            {"id": "p1", "type": "sprite", "position": {"x": 20, "y": 24}, "width": 32, "height": 4, "color_profile_id": 1}
        ],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 24, "sprite_id": 1}
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    with pytest.raises(ValueError, match="powinien być ustawiony co najmniej jeden sekret"):
        parse_scene_json(scene_file, enemies, secrets, require_secret=True)


def test_game_scenes_have_consistent_row_color_profiles():
    """All platforms in any given row in game scenes must share the same color profile."""
    manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    for fname in manifest["scenes"]:
        sc_path = Path("scenes") / fname
        sc_data = parse_scene_json(sc_path, enemies, secrets)
        # Check platform row color consistency
        row_profiles: dict[int, int | None] = {}
        for p in sc_data.platforms:
            if p.y in row_profiles:
                assert p.color_profile_id == row_profiles[p.y], (
                    f"Scene '{sc_data.name}' ({fname}) row y={p.y} has conflicting platform color profiles."
                )
            else:
                row_profiles[p.y] = p.color_profile_id


def test_compile_scenes_rejects_row_color_profile_mismatch(tmp_path: Path):
    """Platforms in the same row with conflicting color profiles must be rejected."""
    scene_file = tmp_path / "cprof_mismatch.json"
    scene_data = {
        "scene": {"name": "Profile Mismatch", "width": 160, "height": 96},
        "platforms": [
            {"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4, "color_profile_id": 1},
            {"id": "p2", "type": "sprite", "position": {"x": 60, "y": 24}, "width": 32, "height": 4, "color_profile_id": 2},
        ],
        "objects": [
            {"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 12, "sprite_id": 8}
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    with pytest.raises(ValueError, match="Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów"):
        parse_scene_json(scene_file, enemies, secrets)


def test_compile_scenes_rejects_platform_conflicting_with_scene_row_color_profiles(tmp_path: Path):
    """Platform color profile conflicting with scene-level row_color_profiles must be rejected."""
    scene_file = tmp_path / "row_cprof_conflict.json"
    scene_data = {
        "scene": {"name": "Row Profile Conflict", "width": 160, "height": 96},
        "row_color_profiles": [None, 1, None, None, None, None],  # row index 1 = y 24 has profile 1
        "platforms": [
            {"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4, "color_profile_id": 3},
        ],
        "objects": [
            {"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 12, "sprite_id": 8}
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    with pytest.raises(ValueError, match="profil zdefiniowany dla tego wiersza to 1"):
        parse_scene_json(scene_file, enemies, secrets)






def test_compiled_secret_special_flag_matches_catalogue():
    """SceneSecretData.special mirrors the catalogue flag (Rule 05: derived from JSON).

    The flag drives the secret-collect sound in the engine (scenes/game.asm ->
    engine/sfx_secret.asm), so a wrong value would be audible in game.
    """
    manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))

    checked = 0
    for scene_file_name in manifest["scenes"]:
        scene_data = parse_scene_json(Path("scenes") / scene_file_name, enemies, secrets)
        for secret in scene_data.secrets:
            catalogue_item = secrets.get(secret.def_id)
            expected = bool(getattr(catalogue_item, "special", False)) if catalogue_item else False
            assert secret.special is expected, (
                f"{scene_file_name}: secret {secret.id} (def {secret.def_id}) 'special' mismatch"
            )
            checked += 1
    assert checked, "at least one compiled secret must be checked"


def test_generated_asm_contains_secret_special_tables():
    """Every scene emits the secret_special SoA table plus the shared pointer pair."""
    asm_path = Path("gen/scenes_data.asm")
    if not asm_path.is_file():
        pytest.skip("gen/scenes_data.asm not found, run 'make data' first")

    manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
    enemies, secrets = load_catalogues(Path("scenes/definitions.json"), Path("scenes/definitions.json"))
    asm_text = asm_path.read_text(encoding="utf-8")

    assert "scene_secret_special_lo" in asm_text
    assert "scene_secret_special_hi" in asm_text
    assert "scene_hud_line_lo" in asm_text
    assert "scene_hud_line_hi" in asm_text
    assert f"SCENE_SPECIAL_TOTAL = {special_secret_total()}" in asm_text, (
        "the compiled status-line layout must match the scene data"
    )
    assert f"STATUS_NAME_MAX = {status_name_max(special_secret_total())}" in asm_text
    for scene_file_name in manifest["scenes"]:
        scene_data = parse_scene_json(Path("scenes") / scene_file_name, enemies, secrets)
        assert f"scene_{scene_data.symbol_name}_secret_special" in asm_text, (
            f"{scene_file_name}: compiled secret_special table missing from the generated ASM"
        )
        assert f"scene_{scene_data.symbol_name}_hud_line" in asm_text, (
            f"{scene_file_name}: compiled status-line (HUD) table missing from the generated ASM"
        )
