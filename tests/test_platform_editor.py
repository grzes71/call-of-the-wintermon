"""Automated unit and integration tests for Atari 8-bit Hardware Platform Editor."""

import json
from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest
from scene_editor.commands import (
    AddPlatformCommand,
    ChangePlatformMovementCommand,
    ChangePlatformMovementSpeedCommand,
    ChangePlatformTypeCommand,
    MovePlatformCommand,
    RemovePlatformCommand,
    ResizePlatformCommand,
)
from scene_editor.json_serializer import CorruptedFileError, SceneSerializer
from scene_editor.scene_model import (
    HardwareResourceLimitError,
    InvalidPlatformDimensionError,
    InvalidPlatformPositionError,
    MAX_MISSILES_PER_ROW,
    MAX_SPRITES_PER_ROW,
    MISSILE_WIDTHS,
    ModelValidationError,
    PLATFORM_HEIGHT,
    PLATFORM_MOVEMENT_LABELS,
    PLATFORM_MOVEMENT_NONE,
    PLATFORM_MOVEMENTS,
    PLATFORM_SPEED_DEFAULT,
    PLATFORM_SPEED_FAST,
    PLATFORM_SPEED_LABELS,
    PLATFORM_SPEED_MEDIUM,
    PLATFORM_SPEED_SLOW,
    PLATFORM_SPEEDS,
    PLATFORM_TYPE_MISSILE,
    PLATFORM_TYPE_SPRITE,
    PlatformCollisionError,
    PlatformElement,
    Position,
    Scene,
    normalize_platform_movement,
    normalize_platform_speed,
    SPRITE_WIDTHS,
    can_add_platform_to_row,
    check_platform_collision,
    get_allowed_platform_rows,
    get_allowed_widths,
    get_required_platform_resources,
    get_row_index,
    get_row_resource_usage,
    is_valid_platform_y,
    platforms_overlap,
)


class TestPlatformDimensions:
    """Tests for platform width and height constraints."""

    def test_all_sprite_widths_allowed(self):
        expected_widths = (8, 16, 24, 32, 48, 64, 96)
        assert SPRITE_WIDTHS == expected_widths
        assert get_allowed_widths(PLATFORM_TYPE_SPRITE) == expected_widths

        for w in SPRITE_WIDTHS:
            plat = PlatformElement(
                id=f"spr-{w}",
                type=PLATFORM_TYPE_SPRITE,
                position=Position(10, 8),
                width=w,
                height=4,
            )
            plat.validate()
            assert plat.width == w
            assert plat.height == 4

    def test_all_missile_widths_allowed(self):
        expected_widths = (8, 32)
        assert MISSILE_WIDTHS == expected_widths
        assert get_allowed_widths(PLATFORM_TYPE_MISSILE) == expected_widths

        for w in MISSILE_WIDTHS:
            plat = PlatformElement(
                id=f"mis-{w}",
                type=PLATFORM_TYPE_MISSILE,
                position=Position(10, 8),
                width=w,
                height=4,
            )
            plat.validate()
            assert plat.width == w
            assert plat.height == 4

    def test_rejection_of_invalid_sprite_widths(self):
        invalid_widths = [-8, -4, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 15, 20, 28, 30, 31, 33, 36, 40, 50, 60, 97, 98, 100]
        for w in invalid_widths:
            plat = PlatformElement(
                id="bad-spr",
                type=PLATFORM_TYPE_SPRITE,
                position=Position(0, 8),
                width=w,
                height=4,
            )
            with pytest.raises(InvalidPlatformDimensionError):
                plat.validate()

    def test_rejection_of_invalid_missile_widths(self):
        invalid_widths = [-8, -4, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 15, 16, 20, 24, 28, 30, 31, 33, 36, 40]
        for w in invalid_widths:
            plat = PlatformElement(
                id="bad-mis",
                type=PLATFORM_TYPE_MISSILE,
                position=Position(0, 8),
                width=w,
                height=4,
            )
            with pytest.raises(InvalidPlatformDimensionError):
                plat.validate()

    def test_rejection_of_invalid_platform_height(self):
        for h in [1, 2, 3, 5, 8, 16]:
            plat = PlatformElement(
                id="bad-h",
                type=PLATFORM_TYPE_SPRITE,
                position=Position(0, 8),
                width=16,
                height=h,
            )
            with pytest.raises(InvalidPlatformDimensionError):
                plat.validate()


class TestPlatformResourceCalculation:
    """Tests for shared hardware resource usage calculation: ceil(width / 32) and ceil(width / 8)."""

    def test_sprite_resource_calculation_all_intervals(self):
        # 8, 16, 32 px -> 1 sprite
        for w in (8, 16, 32):
            assert get_required_platform_resources(PLATFORM_TYPE_SPRITE, w) == 1
            plat = PlatformElement(f"s-{w}", PLATFORM_TYPE_SPRITE, Position(0, 8), w)
            assert plat.required_resources == 1

        # 24 px requires 2 hardware sprites (16px double + 8px normal)
        assert get_required_platform_resources(PLATFORM_TYPE_SPRITE, 24) == 2
        plat_24 = PlatformElement("s-24", PLATFORM_TYPE_SPRITE, Position(0, 8), 24)
        assert plat_24.required_resources == 2

        # 48, 64 px -> 2 sprites
        for w in (48, 64):
            assert get_required_platform_resources(PLATFORM_TYPE_SPRITE, w) == 2
            plat = PlatformElement(f"s-{w}", PLATFORM_TYPE_SPRITE, Position(0, 8), w)
            assert plat.required_resources == 2

        # 96 px -> 3 sprites
        assert get_required_platform_resources(PLATFORM_TYPE_SPRITE, 96) == 3
        plat_96 = PlatformElement("s-96", PLATFORM_TYPE_SPRITE, Position(0, 8), 96)
        assert plat_96.required_resources == 3

    def test_sprite_platform_24px_resource_limit_rejection(self):
        """A 24px platform takes 2 sprites, so combining with two 32px platforms exceeds limit of 3."""
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(0, 24), 32))   # 1 sprite
        scene.add_platform(PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(40, 24), 24))  # 2 sprites
        assert scene.get_platform_row_usage(24) == (3, 0)

        # Adding another 32px sprite must fail (3 + 1 = 4 > 3)
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("p3", PLATFORM_TYPE_SPRITE, Position(80, 24), 32))

    def test_two_24px_sprite_platforms_in_same_row_rejected(self):
        """Two 24px sprite platforms take 2 + 2 = 4 sprites, exceeding the limit of 3."""
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(0, 56), 24))
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(40, 56), 24))

    def test_resize_to_24px_enforces_limit(self):
        """Resizing from 16px (1 sprite) to 24px (2 sprites) in a row with two 32px platforms is rejected."""
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(0, 24), 32))
        scene.add_platform(PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(40, 24), 16))
        scene.add_platform(PlatformElement("p3", PLATFORM_TYPE_SPRITE, Position(60, 24), 32))
        assert scene.get_platform_row_usage(24) == (3, 0)

        with pytest.raises(HardwareResourceLimitError):
            scene.resize_platform("p2", 24)
        assert scene.get_platform("p2").width == 16

    def test_missile_resource_calculation_all_intervals(self):
        # 8 px -> 1 missile
        assert get_required_platform_resources(PLATFORM_TYPE_MISSILE, 8) == 1
        plat = PlatformElement("m-8", PLATFORM_TYPE_MISSILE, Position(0, 8), 8)
        assert plat.required_resources == 1

        # 32 px -> 4 missiles
        assert get_required_platform_resources(PLATFORM_TYPE_MISSILE, 32) == 4
        plat = PlatformElement("m-32", PLATFORM_TYPE_MISSILE, Position(0, 8), 32)
        assert plat.required_resources == 4

    def test_resource_calculation_invalid_type_rejected(self):
        with pytest.raises(ModelValidationError):
            get_required_platform_resources("unknown", 16)

    def test_resource_calculation_invalid_widths_rejected(self):
        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_SPRITE, 30)

        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_SPRITE, 100)

        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_MISSILE, 16)

        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_MISSILE, 24)

        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_MISSILE, 36)

        with pytest.raises(InvalidPlatformDimensionError):
            get_required_platform_resources(PLATFORM_TYPE_MISSILE, 6)


class TestPlatformVerticalPositioning:
    """Tests for platform row rules: y % 16 == 8 and scene height boundary."""

    def test_valid_vertical_positions_accepted(self):
        valid_ys = [8, 24, 40, 56, 72, 88, 104, 120, 136, 152, 168, 184]
        for y in valid_ys:
            assert is_valid_platform_y(y, scene_height=192) is True
            plat = PlatformElement(
                id=f"p-{y}",
                type=PLATFORM_TYPE_SPRITE,
                position=Position(0, y),
                width=16,
                height=4,
            )
            plat.validate(scene_height=192)
            assert plat.row_index == (y - 8) // 16

    def test_invalid_vertical_positions_rejected(self):
        invalid_ys = [0, 4, 16, 20, 32, 48, 64, 80, 96, 112]
        for y in invalid_ys:
            assert is_valid_platform_y(y) is False
            plat = PlatformElement(
                id=f"bad-{y}",
                type=PLATFORM_TYPE_SPRITE,
                position=Position(0, y),
                width=16,
                height=4,
            )
            with pytest.raises(InvalidPlatformPositionError):
                plat.validate()

    def test_negative_y_rejected(self):
        assert is_valid_platform_y(-8) is False
        plat = PlatformElement(
            id="neg-y",
            type=PLATFORM_TYPE_SPRITE,
            position=Position(0, -8),
            width=16,
            height=4,
        )
        with pytest.raises(InvalidPlatformPositionError):
            plat.validate()

    def test_scene_height_boundary_enforced(self):
        # In a scene of height 96: valid rows are y=8, 24, 40, 56, 72, 88.
        # y=88 has height 4, so 88+4 = 92 <= 96 (valid).
        # y=104 has 104+4 = 108 > 96 (exceeds scene height).
        assert is_valid_platform_y(88, scene_height=96) is True
        assert is_valid_platform_y(104, scene_height=96) is False

        allowed_96 = get_allowed_platform_rows(96)
        assert allowed_96 == [8, 24, 40, 56, 72, 88]

        allowed_192 = get_allowed_platform_rows(192)
        assert len(allowed_192) == 12
        assert allowed_192[0] == 8
        assert allowed_192[-1] == 184

        plat_oob = PlatformElement(
            id="p-oob",
            type=PLATFORM_TYPE_SPRITE,
            position=Position(0, 104),
            width=16,
            height=4,
        )
        with pytest.raises(InvalidPlatformPositionError):
            plat_oob.validate(scene_height=96)


class TestHardwareRowLimits:
    """Tests for sprite limit (3) and missile limit (4) per row."""

    def test_three_sprites_in_one_row_allowed(self):
        scene = Scene(width=160, height=192)
        for i in range(3):
            scene.add_platform(
                PlatformElement(
                    id=f"spr-{i}",
                    type=PLATFORM_TYPE_SPRITE,
                    position=Position(i * 32, 24),
                    width=16,
                )
            )
        assert len(scene.platforms) == 3
        s_count, m_count = scene.get_platform_row_usage(24)
        assert s_count == 3
        assert m_count == 0

    def test_fourth_sprite_in_same_row_rejected(self):
        scene = Scene(width=160, height=192)
        for i in range(3):
            scene.add_platform(
                PlatformElement(
                    id=f"spr-{i}",
                    type=PLATFORM_TYPE_SPRITE,
                    position=Position(i * 32, 24),
                    width=16,
                )
            )

        fourth = PlatformElement(
            id="spr-3",
            type=PLATFORM_TYPE_SPRITE,
            position=Position(100, 24),
            width=16,
        )
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(fourth)

        assert len(scene.platforms) == 3

    def test_four_missiles_in_one_row_allowed(self):
        scene = Scene(width=160, height=192)
        for i in range(4):
            scene.add_platform(
                PlatformElement(
                    id=f"mis-{i}",
                    type=PLATFORM_TYPE_MISSILE,
                    position=Position(i * 12, 40),
                    width=8,
                )
            )
        assert len(scene.platforms) == 4
        s_count, m_count = scene.get_platform_row_usage(40)
        assert s_count == 0
        assert m_count == 4

    def test_fifth_missile_in_same_row_rejected(self):
        scene = Scene(width=160, height=192)
        for i in range(4):
            scene.add_platform(
                PlatformElement(
                    id=f"mis-{i}",
                    type=PLATFORM_TYPE_MISSILE,
                    position=Position(i * 12, 40),
                    width=8,
                )
            )

        fifth = PlatformElement(
            id="mis-4",
            type=PLATFORM_TYPE_MISSILE,
            position=Position(60, 40),
            width=8,
        )
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(fifth)

        assert len(scene.platforms) == 4

    def test_mixing_sprites_and_missiles_in_same_row(self):
        scene = Scene(width=160, height=192)
        # Add 3 sprites
        for i in range(3):
            scene.add_platform(
                PlatformElement(
                    id=f"spr-{i}",
                    type=PLATFORM_TYPE_SPRITE,
                    position=Position(i * 32, 56),
                    width=16,
                )
            )
        # Add 4 missiles to the same row (placed in non-overlapping positions)
        for i in range(4):
            scene.add_platform(
                PlatformElement(
                    id=f"mis-{i}",
                    type=PLATFORM_TYPE_MISSILE,
                    position=Position(80 + i * 10, 56),
                    width=8,
                )
            )

        assert len(scene.platforms) == 7
        s, m = scene.get_platform_row_usage(56)
        assert s == 3
        assert m == 4

        # Cannot add 4th sprite (even at an empty position)
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("s-extra", PLATFORM_TYPE_SPRITE, Position(120, 56), 8))

        # Cannot add 5th missile (even at an empty position)
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("m-extra", PLATFORM_TYPE_MISSILE, Position(130, 56), 8))

    def test_resource_freed_on_deletion(self):
        scene = Scene(width=160, height=192)
        for i in range(3):
            scene.add_platform(
                PlatformElement(
                    id=f"spr-{i}",
                    type=PLATFORM_TYPE_SPRITE,
                    position=Position(i * 20, 8),
                    width=16,
                )
            )

        # Row 8 has 3 sprites
        assert scene.get_platform_row_usage(8)[0] == 3

        # Delete one
        removed = scene.remove_platform("spr-1")
        assert removed is not None
        assert scene.get_platform_row_usage(8)[0] == 2

        # Now adding another sprite to row 8 in the freed slot (x=20) succeeds
        new_spr = PlatformElement("spr-new", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        scene.add_platform(new_spr)
        assert scene.get_platform_row_usage(8)[0] == 3

    def test_moving_platform_between_rows_updates_usage(self):
        scene = Scene(width=160, height=192)
        # Row 8: 1 sprite
        scene.add_platform(PlatformElement("spr-a", PLATFORM_TYPE_SPRITE, Position(10, 8), 16))
        # Row 24: 3 sprites (full)
        for i in range(3):
            scene.add_platform(PlatformElement(f"spr-r24-{i}", PLATFORM_TYPE_SPRITE, Position(i * 30, 24), 16))

        # Attempting to move spr-a to row 24 must fail due to limit
        with pytest.raises(HardwareResourceLimitError):
            scene.move_platform("spr-a", 10, 24)

        # spr-a remains at row 8
        assert scene.get_platform("spr-a").position.y == 8
        assert scene.get_platform_row_usage(8)[0] == 1
        assert scene.get_platform_row_usage(24)[0] == 3

        # Moving spr-a to row 40 (empty) succeeds
        scene.move_platform("spr-a", 10, 40)
        assert scene.get_platform("spr-a").position.y == 40
        assert scene.get_platform_row_usage(8)[0] == 0
        assert scene.get_platform_row_usage(40)[0] == 1

    def test_sprite_platform_width_96_consumes_all_three_sprites(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("spr-wide", PLATFORM_TYPE_SPRITE, Position(0, 8), 96))
        assert scene.get_platform_row_usage(8) == (3, 0)

        # Adding another sprite is rejected
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("spr-extra", PLATFORM_TYPE_SPRITE, Position(100, 8), 8))

    def test_sprite_platforms_32_and_64_can_coexist(self):
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("spr-32", PLATFORM_TYPE_SPRITE, Position(0, 24), 32)
        p2 = PlatformElement("spr-64", PLATFORM_TYPE_SPRITE, Position(35, 24), 64)
        scene.add_platform(p1)
        scene.add_platform(p2)
        assert scene.get_platform_row_usage(24) == (3, 0)

        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("spr-extra", PLATFORM_TYPE_SPRITE, Position(105, 24), 8))

    def test_sprite_platforms_three_32s_can_coexist(self):
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("spr-1", PLATFORM_TYPE_SPRITE, Position(0, 40), 32)
        p2 = PlatformElement("spr-2", PLATFORM_TYPE_SPRITE, Position(35, 40), 32)
        p3 = PlatformElement("spr-3", PLATFORM_TYPE_SPRITE, Position(70, 40), 32)
        scene.add_platform(p1)
        scene.add_platform(p2)
        scene.add_platform(p3)
        assert scene.get_platform_row_usage(40) == (3, 0)

    def test_sprite_platforms_two_64s_rejected(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("spr-64-a", PLATFORM_TYPE_SPRITE, Position(0, 56), 64))
        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("spr-64-b", PLATFORM_TYPE_SPRITE, Position(70, 56), 64))

    def test_missile_platforms_two_8s_can_coexist(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("mis-8a", PLATFORM_TYPE_MISSILE, Position(0, 8), 8))
        scene.add_platform(PlatformElement("mis-8b", PLATFORM_TYPE_MISSILE, Position(20, 8), 8))
        assert scene.get_platform_row_usage(8) == (0, 2)

    def test_missile_platforms_four_8s_can_coexist(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("mis-8a", PLATFORM_TYPE_MISSILE, Position(0, 24), 8))
        scene.add_platform(PlatformElement("mis-8b", PLATFORM_TYPE_MISSILE, Position(20, 24), 8))
        scene.add_platform(PlatformElement("mis-8c", PLATFORM_TYPE_MISSILE, Position(40, 24), 8))
        scene.add_platform(PlatformElement("mis-8d", PLATFORM_TYPE_MISSILE, Position(60, 24), 8))
        assert scene.get_platform_row_usage(24) == (0, 4)

        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("mis-extra", PLATFORM_TYPE_MISSILE, Position(80, 24), 8))

    def test_missile_platforms_32_and_8_rejected(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("mis-32", PLATFORM_TYPE_MISSILE, Position(0, 40), 32))
        assert scene.get_platform_row_usage(40) == (0, 4)

        with pytest.raises(HardwareResourceLimitError):
            scene.add_platform(PlatformElement("mis-8", PLATFORM_TYPE_MISSILE, Position(40, 40), 8))

    def test_resizing_platform_enforces_hardware_limits(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(0, 8), 32))
        scene.add_platform(PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(50, 8), 64))

        with pytest.raises(HardwareResourceLimitError):
            scene.resize_platform("p1", 48)

        assert scene.get_platform("p1").width == 32

        scene.resize_platform("p2", 32)
        assert scene.get_platform_row_usage(8) == (2, 0)

        scene.resize_platform("p1", 48)
        assert scene.get_platform("p1").width == 48
        assert scene.get_platform_row_usage(8) == (3, 0)

    def test_change_platform_type_enforces_hardware_limits(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("mis-row", PLATFORM_TYPE_MISSILE, Position(0, 8), 8))
        scene.add_platform(PlatformElement("spr-cand", PLATFORM_TYPE_SPRITE, Position(30, 8), 32))

        with pytest.raises(HardwareResourceLimitError):
            scene.set_platform_type("spr-cand", PLATFORM_TYPE_MISSILE, new_width=32)

        assert scene.get_platform("spr-cand").type == PLATFORM_TYPE_SPRITE

    def test_move_platform_between_rows_wide_sprites(self):
        scene = Scene(width=160, height=192)
        scene.add_platform(PlatformElement("s1", PLATFORM_TYPE_SPRITE, Position(0, 8), 64))
        scene.add_platform(PlatformElement("s2", PLATFORM_TYPE_SPRITE, Position(0, 24), 64))

        with pytest.raises(HardwareResourceLimitError):
            scene.move_platform("s1", 70, 24)

        assert scene.get_platform("s1").position.y == 8


class TestPlatformSerialization:
    """Tests for JSON export and import with platforms."""

    def test_json_round_trip_with_platforms(self):
        scene = Scene(name="plat_scene", width=160, height=192)
        p1 = PlatformElement(
            id="platform-001",
            type="sprite",
            position=Position(24, 8),
            width=16,
            height=4,
        )
        p2 = PlatformElement(
            id="platform-002",
            type="missile",
            position=Position(60, 24),
            width=8,
            height=4,
        )
        scene.add_platform(p1)
        scene.add_platform(p2)

        d = SceneSerializer.to_dict(scene)
        assert "platforms" in d
        assert len(d["platforms"]) == 2
        assert d["platforms"][0]["id"] == "platform-001"
        assert d["platforms"][0]["type"] == "sprite"
        assert d["platforms"][0]["position"] == {"x": 24, "y": 8}
        assert d["platforms"][0]["width"] == 16
        assert d["platforms"][0]["height"] == 4

        json_str = SceneSerializer.to_json(scene)
        restored = SceneSerializer.from_json(json_str)

        assert len(restored.platforms) == 2
        assert restored.platforms[0].id == "platform-001"
        assert restored.platforms[0].type == "sprite"
        assert restored.platforms[0].position.x == 24
        assert restored.platforms[0].position.y == 8
        assert restored.platforms[0].width == 16
        assert restored.platforms[0].height == 4

        assert restored.platforms[1].id == "platform-002"
        assert restored.platforms[1].type == "missile"
        assert restored.platforms[1].position.x == 60
        assert restored.platforms[1].position.y == 24
        assert restored.platforms[1].width == 8
        assert restored.platforms[1].height == 4

    def test_backward_compatibility_older_project_without_platforms(self):
        legacy_data = {
            "schema_version": 1,
            "scene": {"name": "legacy", "width": 160, "height": 96},
            "elements": [],
            # No 'platforms' key
        }
        loaded = SceneSerializer.from_dict(legacy_data)
        assert hasattr(loaded, "platforms")
        assert loaded.platforms == []

    def test_backward_compatibility_platform_height_8_migrated_to_4(self):
        legacy_plat_data = {
            "schema_version": 1,
            "scene": {"name": "legacy_8", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "p-legacy",
                    "type": "sprite",
                    "position": {"x": 20, "y": 8},
                    "width": 16,
                    "height": 8,  # Old format height
                }
            ],
        }
        loaded = SceneSerializer.from_dict(legacy_plat_data)
        assert len(loaded.platforms) == 1
        assert loaded.platforms[0].height == 4
        assert loaded.platforms[0].id == "p-legacy"

    def test_corrupted_platform_data_rejected(self):
        bad_json = {
            "schema_version": 1,
            "scene": {"name": "bad", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "bad-p",
                    "type": "sprite",
                    "position": {"x": 0, "y": 16},  # Invalid row y % 16 == 0
                    "width": 16,
                    "height": 4,
                }
            ],
        }
        with pytest.raises(CorruptedFileError):
            SceneSerializer.from_dict(bad_json)

    def test_json_round_trip_with_wide_platforms(self):
        scene = Scene(name="wide_scene", width=160, height=192)
        scene.add_platform(PlatformElement("spr-wide", PLATFORM_TYPE_SPRITE, Position(0, 8), 96))
        scene.add_platform(PlatformElement("mis-wide", PLATFORM_TYPE_MISSILE, Position(0, 24), 32))

        json_str = SceneSerializer.to_json(scene)
        restored = SceneSerializer.from_json(json_str)

        assert len(restored.platforms) == 2
        p1 = restored.get_platform("spr-wide")
        assert p1.width == 96
        assert p1.required_resources == 3

        p2 = restored.get_platform("mis-wide")
        assert p2.width == 32
        assert p2.required_resources == 4

    def test_json_rejection_of_invalid_platform_width(self):
        bad_json = {
            "schema_version": 1,
            "scene": {"name": "bad_w", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "bad-w",
                    "type": "sprite",
                    "position": {"x": 0, "y": 8},
                    "width": 35,  # Invalid width (not in SPRITE_WIDTHS)
                    "height": 4,
                }
            ],
        }
        with pytest.raises(CorruptedFileError):
            SceneSerializer.from_dict(bad_json)

    def test_json_rejection_of_sprite_row_limit_exceeded(self):
        # Two 64px sprites on same row -> 2 + 2 = 4 > 3
        bad_json = {
            "schema_version": 1,
            "scene": {"name": "bad_spr_limit", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "spr-1",
                    "type": "sprite",
                    "position": {"x": 0, "y": 8},
                    "width": 64,
                    "height": 4,
                },
                {
                    "id": "spr-2",
                    "type": "sprite",
                    "position": {"x": 70, "y": 8},
                    "width": 64,
                    "height": 4,
                },
            ],
        }
        with pytest.raises(CorruptedFileError) as exc_info:
            SceneSerializer.from_dict(bad_json)
        assert "sprite limit" in str(exc_info.value).lower()

    def test_json_rejection_of_missile_row_limit_exceeded(self):
        # 32px missile (4) + 4px missile (1) on same row -> 5 > 4
        bad_json = {
            "schema_version": 1,
            "scene": {"name": "bad_mis_limit", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "mis-1",
                    "type": "missile",
                    "position": {"x": 0, "y": 8},
                    "width": 32,
                    "height": 4,
                },
                {
                    "id": "mis-2",
                    "type": "missile",
                    "position": {"x": 40, "y": 8},
                    "width": 8,
                    "height": 4,
                },
            ],
        }
        with pytest.raises(CorruptedFileError) as exc_info:
            SceneSerializer.from_dict(bad_json)
        assert "missile limit" in str(exc_info.value).lower()


class TestPlatformUndoRedo:
    """Tests for QUndoStack command integration."""

    def test_add_and_remove_platform_command(self):
        scene = Scene(width=160, height=192)
        plat = PlatformElement("p-1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        called = []

        add_cmd = AddPlatformCommand(scene, plat, callback=lambda: called.append("add"))
        add_cmd.redo()
        assert len(scene.platforms) == 1
        assert scene.get_platform("p-1") is not None
        assert len(called) == 1

        add_cmd.undo()
        assert len(scene.platforms) == 0
        assert len(called) == 2

        # Re-add and remove command
        add_cmd.redo()
        rem_cmd = RemovePlatformCommand(scene, "p-1", callback=lambda: called.append("rem"))
        rem_cmd.redo()
        assert len(scene.platforms) == 0

        rem_cmd.undo()
        assert len(scene.platforms) == 1
        assert scene.get_platform("p-1") is not None

    def test_move_platform_command(self):
        scene = Scene(width=160, height=192)
        plat = PlatformElement("p-1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        scene.add_platform(plat)

        cmd = MovePlatformCommand(scene, "p-1", (10, 8), (45, 24))
        cmd.redo()
        assert plat.position.x == 45
        assert plat.position.y == 24
        assert scene.get_platform_row_usage(8)[0] == 0
        assert scene.get_platform_row_usage(24)[0] == 1

        cmd.undo()
        assert plat.position.x == 10
        assert plat.position.y == 8
        assert scene.get_platform_row_usage(8)[0] == 1
        assert scene.get_platform_row_usage(24)[0] == 0

    def test_resize_platform_command(self):
        scene = Scene(width=160, height=192)
        plat = PlatformElement("p-1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        scene.add_platform(plat)

        cmd = ResizePlatformCommand(scene, "p-1", 16, 32)
        cmd.redo()
        assert plat.width == 32

        cmd.undo()
        assert plat.width == 16

    def test_change_platform_type_command(self):
        scene = Scene(width=160, height=192)
        plat = PlatformElement("p-1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        scene.add_platform(plat)

        assert scene.get_platform_row_usage(8) == (1, 0)

        cmd = ChangePlatformTypeCommand(scene, "p-1", PLATFORM_TYPE_SPRITE, 16, PLATFORM_TYPE_MISSILE, 8)
        cmd.redo()
        assert plat.type == PLATFORM_TYPE_MISSILE
        assert plat.width == 8
        assert scene.get_platform_row_usage(8) == (0, 1)

        cmd.undo()
        assert plat.type == PLATFORM_TYPE_SPRITE
        assert plat.width == 16
        assert scene.get_platform_row_usage(8) == (1, 0)


class TestPlatformCollisions:
    """Tests enforcing the strict prohibition of overlapping platforms."""

    def test_identical_position_collision(self):
        """Two platforms with identical coordinates must collide and be rejected."""
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        p2 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        scene.add_platform(p1)

        with pytest.raises(PlatformCollisionError) as exc_info:
            scene.add_platform(p2)
        assert "p2" in str(exc_info.value)
        assert "p1" in str(exc_info.value)

    def test_partial_overlap_collision(self):
        """Partially overlapping platforms on the same row must be rejected."""
        scene = Scene(width=160, height=192)
        # p1 spans x: [20..36)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        scene.add_platform(p1)

        # p2 spans x: [30..46) -> overlaps p1 by 6px [30..36)
        p2 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(30, 8), 16)
        with pytest.raises(PlatformCollisionError):
            scene.add_platform(p2)

        # p3 spans x: [10..26) -> overlaps p1 by 6px [20..26)
        p3 = PlatformElement("p3", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        with pytest.raises(PlatformCollisionError):
            scene.add_platform(p3)

    def test_platforms_of_different_widths_collision(self):
        """Platforms of different widths colliding (or one containing another) must be rejected."""
        scene = Scene(width=160, height=192)
        # p_wide spans x: [10..42)
        p_wide = PlatformElement("p-wide", PLATFORM_TYPE_SPRITE, Position(10, 24), 32)
        scene.add_platform(p_wide)

        # p_narrow spans x: [18..26) inside p_wide
        p_narrow = PlatformElement("p-narrow", PLATFORM_TYPE_SPRITE, Position(18, 24), 8)
        with pytest.raises(PlatformCollisionError):
            scene.add_platform(p_narrow)

    def test_sprite_and_missile_collision(self):
        """Sprites and missiles in the same row must not overlap."""
        scene = Scene(width=160, height=192)
        # Sprite at x: [40..56)
        sprite = PlatformElement("spr", PLATFORM_TYPE_SPRITE, Position(40, 40), 16)
        scene.add_platform(sprite)

        # Missile at x: [48..56) -> overlaps right half of sprite
        missile = PlatformElement("mis", PLATFORM_TYPE_MISSILE, Position(48, 40), 8)
        with pytest.raises(PlatformCollisionError):
            scene.add_platform(missile)

    def test_touching_edges_do_not_collide(self):
        """Platforms touching edges without sharing any pixels are permitted."""
        scene = Scene(width=160, height=192)
        # p1 spans x: [20..36)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        # p2 starts exactly at p1's right edge x=36, spans [36..44)
        p2 = PlatformElement("p2", PLATFORM_TYPE_MISSILE, Position(36, 8), 8)
        # p3 ends exactly at p1's left edge x=20, spans [12..20)
        p3 = PlatformElement("p3", PLATFORM_TYPE_MISSILE, Position(12, 8), 8)

        scene.add_platform(p1)
        scene.add_platform(p2)
        scene.add_platform(p3)
        assert len(scene.platforms) == 3

    def test_different_rows_do_not_collide(self):
        """Platforms at the exact same X coordinate on different rows do not collide."""
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(20, 8), 16)
        p2 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(20, 24), 16)
        p3 = PlatformElement("p3", PLATFORM_TYPE_SPRITE, Position(20, 40), 16)

        scene.add_platform(p1)
        scene.add_platform(p2)
        scene.add_platform(p3)
        assert len(scene.platforms) == 3

    def test_reject_move_causing_collision(self):
        """Moving a platform to an overlapping position is rejected and preserves old position."""
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        p2 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(60, 8), 16)
        scene.add_platform(p1)
        scene.add_platform(p2)

        # Move p2 to overlap p1
        with pytest.raises(PlatformCollisionError):
            scene.move_platform("p2", new_x=15, new_y=8)

        # p2 remains untouched
        assert p2.position.x == 60
        assert p2.position.y == 8

        # Move p2 to different row works
        scene.move_platform("p2", new_x=15, new_y=24)
        assert p2.position.x == 15
        assert p2.position.y == 24

    def test_reject_resize_causing_collision(self):
        """Resizing a platform into an existing platform is rejected and preserves original width."""
        scene = Scene(width=160, height=192)
        # p1: [10..26)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        # p2: [30..38)
        p2 = PlatformElement("p2", PLATFORM_TYPE_MISSILE, Position(30, 8), 8)
        scene.add_platform(p1)
        scene.add_platform(p2)

        # Attempt to expand p1 width from 16 to 24 (new right edge = 34 > 30) -> collision with p2
        with pytest.raises(PlatformCollisionError):
            scene.resize_platform("p1", 24)

        # p1 width must remain 16
        assert p1.width == 16

    def test_reject_type_change_causing_collision(self):
        """Changing platform type that results in collision is rejected and keeps previous state."""
        scene = Scene(width=160, height=192)
        # mis: [20..28)
        mis = PlatformElement("mis", PLATFORM_TYPE_MISSILE, Position(20, 8), 8)
        # other: [30..46)
        other = PlatformElement("other", PLATFORM_TYPE_SPRITE, Position(30, 8), 16)
        scene.add_platform(mis)
        scene.add_platform(other)

        # Changing mis to sprite with width 16 would span [20..36), overlapping other at [30..36)
        with pytest.raises(PlatformCollisionError):
            scene.set_platform_type("mis", PLATFORM_TYPE_SPRITE, new_width=16)

        assert mis.type == PLATFORM_TYPE_MISSILE
        assert mis.width == 8

    def test_json_collision_detection(self):
        """Loading a JSON scene with overlapping platforms must raise CorruptedFileError with details."""
        colliding_json = json.dumps({
            "schema_version": 1,
            "scene": {"name": "test_collision", "width": 160, "height": 192},
            "elements": [],
            "platforms": [
                {
                    "id": "p-1",
                    "type": "sprite",
                    "position": {"x": 20, "y": 8},
                    "width": 16,
                    "height": 4,
                },
                {
                    "id": "p-2",
                    "type": "sprite",
                    "position": {"x": 25, "y": 8},
                    "width": 16,
                    "height": 4,
                },
            ],
        })

        with pytest.raises(CorruptedFileError) as exc_info:
            SceneSerializer.from_json(colliding_json)

        assert "collides" in str(exc_info.value).lower()
        assert "p-1" in str(exc_info.value)
        assert "p-2" in str(exc_info.value)

    def test_undo_redo_collision_safety(self):
        """Undo and redo operations preserve collision-free invariants."""
        scene = Scene(width=160, height=192)
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        p2 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(50, 8), 16)
        scene.add_platform(p1)
        scene.add_platform(p2)

        # Move p2 to non-colliding (80, 8)
        cmd = MovePlatformCommand(scene, "p2", (50, 8), (80, 8))
        cmd.redo()
        assert p2.position.x == 80
        scene.validate()

        # Undo returns to (50, 8)
        cmd.undo()
        assert p2.position.x == 50
        scene.validate()

    def test_platform_collision_with_4px_height(self):
        """Validate that collision uses exactly 4 pixels height."""
        p1 = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, 4)
        assert p1.height == 4
        # Same row (y=8), overlapping in X
        p2_overlap = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(20, 8), 16, 4)
        assert check_platform_collision([p1], (p2_overlap.position.x, p2_overlap.position.y, p2_overlap.width, p2_overlap.height)) is p1

        # Same row (y=8), touching at x=26 (p1 is [10..26), p2 is [26..42))
        p2_touch_x = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(26, 8), 16, 4)
        assert check_platform_collision([p1], (p2_touch_x.position.x, p2_touch_x.position.y, p2_touch_x.width, p2_touch_x.height)) is None

        # Different valid row (y=24), same X: no overlap because y1=[8..12) and y2=[24..28)
        p2_row24 = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(10, 24), 16, 4)
        assert check_platform_collision([p1], (p2_row24.position.x, p2_row24.position.y, p2_row24.width, p2_row24.height)) is None

        # Direct platforms_overlap helper calls
        assert platforms_overlap(10, 8, 16, 4, 20, 8, 16, 4) is True
        assert platforms_overlap(10, 8, 16, 4, 26, 8, 16, 4) is False

    def test_vertical_edge_touching_no_collision(self):
        """Simulate vertical edge touching (y=[8..12) and y=[12..16)) without overlapping."""
        # Top box: (10, 8, 16, 4) -> y in [8, 12)
        # Touching bottom box at y=12: (10, 12, 16, 4) -> y in [12, 16)
        assert platforms_overlap(10, 8, 16, 4, 10, 12, 16, 4) is False

        # Partially overlapping vertically (y=11..15, overlapping by 1px at y=11)
        assert platforms_overlap(10, 8, 16, 4, 10, 11, 16, 4) is True


class TestPlatformMovement:
    """Tests for platform movement property, normalization, and commands."""

    def test_default_movement_is_none(self):
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        assert plat.movement == PLATFORM_MOVEMENT_NONE
        assert plat.movement == "none"

    @pytest.mark.parametrize(
        "movement_value",
        [
            "none",
            "left-right",
            "right-left",
            "left-pause-right",
            "right-pause-left",
        ],
    )
    def test_all_valid_movements_accepted(self, movement_value: str):
        plat = PlatformElement(
            "p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement=movement_value
        )
        plat.validate()
        assert plat.movement == movement_value

    def test_movement_typo_and_alias_normalization(self):
        # User typo 'left-rigth' is seamlessly normalized to 'left-right'
        assert normalize_platform_movement("Left-rigth") == "left-right"
        assert normalize_platform_movement("left-rigth") == "left-right"
        assert normalize_platform_movement("left_right") == "left-right"
        assert normalize_platform_movement("Left-Right") == "left-right"

        # None variants
        assert normalize_platform_movement(None) == "none"
        assert normalize_platform_movement("None (default)") == "none"
        assert normalize_platform_movement("default") == "none"
        assert normalize_platform_movement("none") == "none"

        # Snake_case variants
        assert normalize_platform_movement("right_left") == "right-left"
        assert normalize_platform_movement("left_pause_right") == "left-pause-right"
        assert normalize_platform_movement("right_pause_left") == "right-pause-left"

    def test_invalid_movement_rejected(self):
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement="circular")
        with pytest.raises(ModelValidationError, match="Platform 'movement' must be one of"):
            plat.validate()

    def test_movement_serialization_roundtrip(self):
        # When movement is default 'none', to_dict omits it
        p_default = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        d_default = p_default.to_dict()
        assert "movement" not in d_default
        p_loaded = PlatformElement.from_dict(d_default)
        assert p_loaded.movement == "none"

        # When movement is non-default, to_dict includes it
        p_moving = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement="left-right")
        d_moving = p_moving.to_dict()
        assert d_moving["movement"] == "left-right"
        p_loaded2 = PlatformElement.from_dict(d_moving)
        assert p_loaded2.movement == "left-right"

        # from_dict with alias/typo 'left-rigth'
        d_typo = {"id": "p3", "type": "sprite", "position": {"x": 10, "y": 8}, "width": 16, "movement": "Left-rigth"}
        p_loaded3 = PlatformElement.from_dict(d_typo)
        assert p_loaded3.movement == "left-right"

    def test_change_platform_movement_command(self):
        scene = Scene(width=160, height=96)
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        scene.add_platform(plat)

        cmd = ChangePlatformMovementCommand(scene, "p1", "none", "right-left")
        cmd.redo()
        assert plat.movement == "right-left"

        cmd.undo()
        assert plat.movement == "none"


class TestPlatformMovementSpeed:
    """Tests for platform movement speed property, normalization, and commands."""

    def test_default_speed_is_medium(self):
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        assert plat.movement_speed == PLATFORM_SPEED_DEFAULT
        assert plat.movement_speed == "medium"

    @pytest.mark.parametrize(
        "speed_value",
        [
            "slow",
            "medium",
            "fast",
        ],
    )
    def test_all_valid_speeds_accepted(self, speed_value: str):
        plat = PlatformElement(
            "p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement_speed=speed_value
        )
        plat.validate()
        assert plat.movement_speed == speed_value

    def test_speed_normalization_and_aliases(self):
        assert normalize_platform_speed(None) == "medium"
        assert normalize_platform_speed("") == "medium"
        assert normalize_platform_speed("medium") == "medium"
        assert normalize_platform_speed("Medium") == "medium"
        assert normalize_platform_speed("Medium (obecna prędkość)") == "medium"
        assert normalize_platform_speed("default") == "medium"
        assert normalize_platform_speed("normal") == "medium"

        assert normalize_platform_speed("slow") == "slow"
        assert normalize_platform_speed("Slow") == "slow"
        assert normalize_platform_speed("wolny") == "slow"

        assert normalize_platform_speed("fast") == "fast"
        assert normalize_platform_speed("Fast") == "fast"
        assert normalize_platform_speed("szybki") == "fast"

    def test_invalid_speed_rejected(self):
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement_speed="turbo")
        with pytest.raises(ModelValidationError, match="Platform 'movement_speed' must be one of"):
            plat.validate()

    def test_speed_serialization_roundtrip(self):
        # When speed is default 'medium', to_dict omits it
        p_default = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        d_default = p_default.to_dict()
        assert "movement_speed" not in d_default
        p_loaded = PlatformElement.from_dict(d_default)
        assert p_loaded.movement_speed == "medium"

        # When speed is non-default, to_dict includes it
        p_fast = PlatformElement("p2", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement_speed="fast")
        d_fast = p_fast.to_dict()
        assert d_fast["movement_speed"] == "fast"
        p_loaded2 = PlatformElement.from_dict(d_fast)
        assert p_loaded2.movement_speed == "fast"

        p_slow = PlatformElement("p3", PLATFORM_TYPE_SPRITE, Position(10, 8), 16, movement_speed="slow")
        d_slow = p_slow.to_dict()
        assert d_slow["movement_speed"] == "slow"
        p_loaded3 = PlatformElement.from_dict(d_slow)
        assert p_loaded3.movement_speed == "slow"

    def test_change_platform_movement_speed_command(self):
        scene = Scene(width=160, height=96)
        plat = PlatformElement("p1", PLATFORM_TYPE_SPRITE, Position(10, 8), 16)
        scene.add_platform(plat)

        cmd = ChangePlatformMovementSpeedCommand(scene, "p1", "medium", "fast")
        cmd.redo()
        assert plat.movement_speed == "fast"

        cmd.undo()
        assert plat.movement_speed == "medium"
