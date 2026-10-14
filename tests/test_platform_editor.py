"""Automated unit and integration tests for Atari 8-bit Hardware Platform Editor."""

import json
from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest
from scene_editor.commands import (
    AddPlatformCommand,
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
    PLATFORM_TYPE_MISSILE,
    PLATFORM_TYPE_SPRITE,
    PlatformCollisionError,
    PlatformElement,
    Position,
    Scene,
    SPRITE_WIDTHS,
    can_add_platform_to_row,
    check_platform_collision,
    get_allowed_platform_rows,
    get_allowed_widths,
    get_row_index,
    get_row_resource_usage,
    is_valid_platform_y,
    platforms_overlap,
)


class TestPlatformDimensions:
    """Tests for platform width and height constraints."""

    def test_all_sprite_widths_allowed(self):
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
        invalid_widths = [0, 1, 2, 3, 5, 6, 7, 10, 15, 30, 36, 64]
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
        invalid_widths = [0, 2, 6, 12, 16, 20, 32]
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
                    width=4,
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
            scene.add_platform(PlatformElement("m-extra", PLATFORM_TYPE_MISSILE, Position(130, 56), 4))

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
