"""Tests for Platform Color Profiles system in Atari Scene Editor & Game Exporter.

Covers all 11 acceptance criteria + integer ID (1-255 range) constraints:
1. Creation of profile with exactly eight values and integer ID (1-255).
2. Validation of Atari GTIA register hex format and range (even byte, 0x00-0xFE).
3. Correctness of Atari GTIA to RGB conversion.
4. Editing and duplicating/cloning profiles.
5. Assigning one profile to multiple platforms.
6. Independent assignment of different profiles to different platforms.
7. Updating profile updates platforms using that profile.
8. Safe deletion of profile in use (detection, warning, unassignment).
9. Saving and reopening project preserving profiles and assignments.
10. Export of all eight scanline values in exact order.
11. Backwards compatibility for legacy scenes without profile information.
12. Validation of Platform profile ID as integer in 1-255 range.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scene_editor.atari_palette import (
    ATARI_GTIA_PALETTE,
    atari_color_to_rgb,
    atari_color_to_hex_rgb,
    format_atari_color_hex,
    is_valid_atari_color_string,
    parse_atari_color_hex,
)
from scene_editor.catalogue_model import (
    PlatformColorProfile,
    ProjectCatalogues,
    ProfileInUseError,
    InvalidDefinitionError,
    DEFAULT_PLATFORM_PROFILES,
)
from scene_editor.scene_model import ModelValidationError, PlatformElement, Position, Scene
from scene_editor.json_serializer import SceneSerializer
from scene_editor.commands import ChangePlatformColorProfileCommand

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from compile_scenes import compile_scenes, parse_scene_json, load_platform_profiles


# ------------------------------------------------------------------------------
# Criterion 1: Creation of a profile with exactly eight values
# ------------------------------------------------------------------------------
def test_create_platform_color_profile():
    colors = [0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80]
    prof = PlatformColorProfile(
        id=1,
        name="Custom Ice",
        colors=colors,
        description="Blue ice platform gradient",
    )
    assert prof.id == 1
    assert prof.name == "Custom Ice"
    assert len(prof.colors) == 8
    assert prof.colors == colors
    prof.validate()


# ------------------------------------------------------------------------------
# Criterion 2: Validation of format and range of HEX values
# ------------------------------------------------------------------------------
def test_atari_color_hex_validation():
    # Valid even hex codes
    assert parse_atari_color_hex("0x8E") == 0x8E
    assert parse_atari_color_hex("8E") == 0x8E
    assert parse_atari_color_hex("$8E") == 0x8E
    assert parse_atari_color_hex("0x00") == 0x00
    assert parse_atari_color_hex("0xFE") == 0xFE
    assert is_valid_atari_color_string("0x8E") is True
    assert is_valid_atari_color_string("0x00") is True

    # Reject odd values (bit 0 is unused/must be 0 on Atari GTIA)
    assert is_valid_atari_color_string("0xC7") is False
    with pytest.raises(ValueError, match="lowest bit must be 0"):
        parse_atari_color_hex("0xC7")

    with pytest.raises(ValueError, match="lowest bit must be 0"):
        parse_atari_color_hex("0x81")

    # Reject out of range (> 0xFE)
    assert is_valid_atari_color_string("0x100") is False
    with pytest.raises(ValueError, match="out of range"):
        parse_atari_color_hex("0x100")

    # Reject negative or invalid hex strings
    assert is_valid_atari_color_string("-0x02") is False
    assert is_valid_atari_color_string("XYZ") is False
    with pytest.raises(ValueError):
        parse_atari_color_hex("XYZ")

    # Profile validation rejects wrong number of colors or invalid entries
    with pytest.raises(InvalidDefinitionError, match="must define exactly 8"):
        PlatformColorProfile(id=1, name="Bad", colors=[0x80, 0x82]).validate()

    with pytest.raises(InvalidDefinitionError, match="bit 0"):
        PlatformColorProfile(id=2, name="Bad", colors=[0x81] * 8).validate()


# ------------------------------------------------------------------------------
# Profile ID range (integer 1-255) validation
# ------------------------------------------------------------------------------
def test_platform_profile_id_integer_range_validation():
    # Valid IDs
    p_min = PlatformColorProfile(id=1, name="Min", colors=[0x80] * 8)
    p_min.validate()
    assert p_min.id == 1

    p_max = PlatformColorProfile(id=255, name="Max", colors=[0x80] * 8)
    p_max.validate()
    assert p_max.id == 255

    # String numeric converts to int
    p_str = PlatformColorProfile(id="42", name="Str", colors=[0x80] * 8)
    p_str.validate()
    assert p_str.id == 42

    # Reject 0
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile(id=0, name="Zero", colors=[0x80] * 8).validate()

    # Reject negative
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile(id=-5, name="Negative", colors=[0x80] * 8).validate()

    # Reject > 255
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile(id=256, name="TooBig", colors=[0x80] * 8).validate()

    # Reject non-numeric string
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile(id="profile_ice", name="NonNum", colors=[0x80] * 8).validate()

    # Reject bool
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile(id=True, name="Bool", colors=[0x80] * 8).validate()

    # from_dict validation
    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile.from_dict({
            "id": "invalid_id",
            "name": "Bad",
            "colors": ["0x80"] * 8,
        })

    with pytest.raises(InvalidDefinitionError, match="between 1 and 255"):
        PlatformColorProfile.from_dict({
            "id": 0,
            "name": "Bad",
            "colors": ["0x80"] * 8,
        })

    # PlatformElement color_profile_id validation
    plat_ok = PlatformElement(id="p1", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id=1)
    plat_ok.validate()

    plat_str_ok = PlatformElement(id="p2", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id="99")
    plat_str_ok.validate()
    assert plat_str_ok.color_profile_id == 99

    with pytest.raises(ModelValidationError, match="between 1 and 255"):
        PlatformElement(id="p3", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id=0).validate()

    with pytest.raises(ModelValidationError, match="between 1 and 255"):
        PlatformElement(id="p4", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id=300).validate()

    with pytest.raises(ModelValidationError, match="between 1 and 255"):
        PlatformElement(id="p5", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id="text").validate()


# ------------------------------------------------------------------------------
# Criterion 3: Correctness of Atari to RGB conversion
# ------------------------------------------------------------------------------
def test_atari_color_to_rgb_conversion():
    # 0x00 is pure black in standard Atari palette
    r, g, b = atari_color_to_rgb(0x00)
    assert (r, g, b) == (0, 0, 0)
    assert atari_color_to_hex_rgb(0x00) == "#000000"

    # Test an even color register, e.g. 0x8E (medium/light blue)
    rgb = atari_color_to_rgb(0x8E)
    assert isinstance(rgb, tuple) and len(rgb) == 3
    for channel in rgb:
        assert 0 <= channel <= 255
    hex_rgb = atari_color_to_hex_rgb(0x8E)
    assert hex_rgb.startswith("#") and len(hex_rgb) == 7

    # Consistency with palette table
    assert rgb == ATARI_GTIA_PALETTE[0x8E]
    assert format_atari_color_hex(0x8E) == "0x8E"


# ------------------------------------------------------------------------------
# Criterion 4: Editing and duplicating/cloning a profile
# ------------------------------------------------------------------------------
def test_edit_and_duplicate_profile():
    catalogues = ProjectCatalogues()
    p_orig = PlatformColorProfile(
        id=2,
        name="Gold",
        colors=[0x2E, 0x2C, 0x2A, 0x28, 0x26, 0x24, 0x22, 0x20],
    )
    catalogues.add_platform_profile(p_orig)

    # Duplicate
    p_copy = catalogues.duplicate_platform_profile(2, new_id=3)
    assert p_copy.id == 3
    assert "Copy" in p_copy.name
    assert p_copy.colors == p_orig.colors
    assert 3 in catalogues.platform_profiles

    # Edit duplicate
    updated_colors = [0x2A, 0x28, 0x26, 0x24, 0x22, 0x20, 0x1E, 0x1C]
    p_copy.colors = updated_colors
    catalogues.update_platform_profile(p_copy)

    retrieved = catalogues.get_platform_profile(3)
    assert retrieved is not None
    assert retrieved.colors == updated_colors
    # Original remains untouched
    assert catalogues.get_platform_profile(2).colors[0] == 0x2E


# ------------------------------------------------------------------------------
# Criterion 5: Assigning one profile to multiple platforms
# ------------------------------------------------------------------------------
def test_assign_profile_to_multiple_platforms():
    scene = Scene(name="Test Scene", width=160, height=96)
    p1 = PlatformElement(id="plat-1", type="sprite", position=Position(10, 24), width=16, height=4, color_profile_id=1)
    p2 = PlatformElement(id="plat-2", type="sprite", position=Position(50, 40), width=16, height=4, color_profile_id=1)
    scene.add_platform(p1)
    scene.add_platform(p2)

    catalogues = ProjectCatalogues()
    usage = catalogues.get_profile_platform_usage(1, scene)
    assert [p.id for p in usage] == ["plat-1", "plat-2"]


# ------------------------------------------------------------------------------
# Criterion 6: Independent assignment of different profiles to platforms
# ------------------------------------------------------------------------------
def test_independent_profile_assignment():
    scene = Scene(name="Test Scene", width=160, height=96)
    p1 = PlatformElement(id="plat-1", type="sprite", position=Position(10, 24), width=16, height=4, color_profile_id=1)
    p2 = PlatformElement(id="plat-2", type="sprite", position=Position(50, 40), width=16, height=4, color_profile_id=3)
    scene.add_platform(p1)
    scene.add_platform(p2)

    # Change profile of p1 via Command pattern
    cmd = ChangePlatformColorProfileCommand(scene, "plat-1", 1, 4)
    cmd.redo()
    assert scene.get_platform("plat-1").color_profile_id == 4
    # p2 remains untouched
    assert scene.get_platform("plat-2").color_profile_id == 3

    cmd.undo()
    assert scene.get_platform("plat-1").color_profile_id == 1


# ------------------------------------------------------------------------------
# Criterion 7: Updating profile data updates platforms using that profile
# ------------------------------------------------------------------------------
def test_profile_update_reflects_in_consumers():
    catalogues = ProjectCatalogues()
    prof = PlatformColorProfile(id=10, name="Shared", colors=[0x8E] * 8)
    catalogues.add_platform_profile(prof)

    scene = Scene(name="Test Scene", width=160, height=96)
    scene.add_platform(PlatformElement(id="p1", type="sprite", position=Position(0, 8), width=16, height=4, color_profile_id=10))
    scene.add_platform(PlatformElement(id="p2", type="sprite", position=Position(30, 24), width=16, height=4, color_profile_id=10))

    # When catalogue updates the profile colors
    new_colors = [0x36] * 8
    prof.colors = new_colors
    catalogues.update_platform_profile(prof)

    # Both platforms resolve to the new colors
    p1_elem = scene.get_platform("p1")
    p2_elem = scene.get_platform("p2")
    assert catalogues.get_platform_profile(p1_elem.color_profile_id).colors == new_colors
    assert catalogues.get_platform_profile(p2_elem.color_profile_id).colors == new_colors


# ------------------------------------------------------------------------------
# Criterion 8: Safe deletion of profile in use
# ------------------------------------------------------------------------------
def test_safe_deletion_of_profile():
    catalogues = ProjectCatalogues()
    prof = PlatformColorProfile(id=20, name="Active", colors=[0x80] * 8)
    catalogues.add_platform_profile(prof)

    scene = Scene(name="Test Scene", width=160, height=96)
    scene.add_platform(PlatformElement(id="plat-x", type="sprite", position=Position(10, 24), width=16, height=4, color_profile_id=20))

    # Attempting to delete without force must raise ProfileInUseError
    with pytest.raises(ProfileInUseError) as exc_info:
        catalogues.remove_platform_profile(20, scene=scene, force=False)
    assert "plat-x" in str(exc_info.value)
    assert 20 in catalogues.platform_profiles

    # With force=True, profile is deleted and platform reference is safely cleared
    catalogues.remove_platform_profile(20, scene=scene, force=True)
    assert 20 not in catalogues.platform_profiles
    assert scene.get_platform("plat-x").color_profile_id is None


# ------------------------------------------------------------------------------
# Criterion 9: Save and reload project preserving profiles and assignments
# ------------------------------------------------------------------------------
def test_save_and_reload_scene_and_profiles(tmp_path: Path):
    profiles_path = tmp_path / "platform_profiles.json"
    scene_path = tmp_path / "scene.json"

    # 1. Setup catalogues and profiles
    catalogues = ProjectCatalogues(platform_profiles_path=profiles_path)
    prof = PlatformColorProfile(
        id=77,
        name="Mystic Violet",
        colors=[0x6E, 0x6C, 0x6A, 0x68, 0x66, 0x64, 0x62, 0x60],
        description="Violet crystal platform",
    )
    catalogues.add_platform_profile(prof)
    catalogues.save_to_paths(platform_profiles_path=profiles_path)

    # 2. Setup scene with platform referencing the profile
    scene = Scene(name="Mystic Cavern", width=160, height=96)
    scene.add_platform(PlatformElement(id="plat-crystal", type="sprite", position=Position(20, 24), width=16, height=4, color_profile_id=77))
    SceneSerializer.save_to_file(scene, scene_path)

    # 3. Reload catalogues from file
    loaded_cats = ProjectCatalogues.load_from_paths(platform_profiles_path=profiles_path)
    assert 77 in loaded_cats.platform_profiles
    assert loaded_cats.platform_profiles[77].colors[0] == 0x6E

    # 4. Reload scene from file
    loaded_scene = SceneSerializer.load_from_file(scene_path)
    assert len(loaded_scene.platforms) == 1
    assert loaded_scene.platforms[0].color_profile_id == 77


# ------------------------------------------------------------------------------
# Criterion 10: Export of all eight scanline values in exact order
# ------------------------------------------------------------------------------
def test_export_eight_scanline_values_in_order(tmp_path: Path):
    manifest_path = tmp_path / "scenes.json"
    scene_file = tmp_path / "test_scene.json"
    profiles_file = tmp_path / "platform_profiles.json"
    out_asm = tmp_path / "scenes_data.asm"

    # Profile with 8 distinct, strictly ordered scanline colors
    ordered_colors = [0x1E, 0x2C, 0x3A, 0x48, 0x56, 0x64, 0x72, 0x80]
    profiles_data = {
        "platform_profiles": [
            {
                "id": 99,
                "name": "Rainbow",
                "colors": ordered_colors,
            }
        ]
    }
    profiles_file.write_text(json.dumps(profiles_data), encoding="utf-8")

    scene_data = {
        "schema_version": 1,
        "scene": {"name": "Test Scanlines", "width": 160, "height": 96},
        "elements": [],
        "platforms": [
            {
                "id": "p0",
                "type": "sprite",
                "position": {"x": 10, "y": 24},
                "width": 16,
                "height": 4,
                "color_profile_id": 99,
            }
        ],
        "objects": [],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    manifest_data = {"scenes": [scene_file.name]}
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    ret = compile_scenes(
        manifest_path=manifest_path,
        output_path=out_asm,
        scenes_dir=tmp_path,
        profiles_path=profiles_file,
    )
    assert ret == 0
    asm = out_asm.read_text(encoding="utf-8")

    # Verify that each scanline table exists and has the exact color byte in order
    for idx, expected_color in enumerate(ordered_colors):
        sl_label = f"scene_test_scene_plat_color_sl{idx + 1}"
        assert sl_label in asm
        expected_hex = f"${expected_color:02X}"
        label_pos = asm.find(sl_label)
        snippet = asm[label_pos:label_pos + 60]
        assert expected_hex in snippet, f"Scanline {idx + 1} did not contain {expected_hex} in snippet: {snippet}"

    # Also check master table pointers
    for sl in range(1, 9):
        assert f"scene_plat_color_sl{sl}_lo" in asm
        assert f"scene_plat_color_sl{sl}_hi" in asm


# ------------------------------------------------------------------------------
# Criterion 11: Backwards compatibility for legacy scenes without profile info
# ------------------------------------------------------------------------------
def test_backwards_compatibility_legacy_scenes(tmp_path: Path):
    # Legacy platform dict without color_profile_id
    legacy_plat_dict = {
        "id": "plat-old",
        "type": "sprite",
        "position": {"x": 10, "y": 24},
        "width": 16,
        "height": 4,
    }
    plat = PlatformElement.from_dict(legacy_plat_dict)
    assert plat.id == "plat-old"
    assert plat.color_profile_id is None

    # Legacy scene dict without color_profile_id on platforms
    legacy_scene_dict = {
        "schema_version": 1,
        "scene": {"name": "Old Scene", "width": 160, "height": 96},
        "elements": [],
        "platforms": [legacy_plat_dict],
        "objects": [],
    }
    legacy_file = tmp_path / "legacy_scene.json"
    legacy_file.write_text(json.dumps(legacy_scene_dict), encoding="utf-8")

    scene = SceneSerializer.load_from_file(legacy_file)
    assert len(scene.platforms) == 1
    assert scene.platforms[0].color_profile_id is None

    # Serialization does not crash, to_dict gracefully handles None
    d = SceneSerializer.to_dict(scene)
    assert "color_profile_id" not in d["platforms"][0]
