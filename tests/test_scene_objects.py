"""Automated unit and integration tests for Scene Objects (Enemies & Treasures) in Atari 8-bit Scene Editor."""

import json
import os
from pathlib import Path
import sys

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PIL import Image
from PySide6.QtWidgets import QApplication
import pytest

from scene_editor.commands import (
    AddPlatformCommand,
    AddSceneObjectCommand,
    MovePlatformCommand,
    MoveSceneObjectCommand,
    RemovePlatformCommand,
    RemoveSceneObjectCommand,
    UpdateSceneObjectPropsCommand,
)
from scene_editor.json_serializer import CorruptedFileError, SceneSerializer
from scene_editor.main_window import MainWindow
from scene_editor.scene_items import SceneObjectGraphicsItem
from scene_editor.scene_model import (
    ENEMY_SPEED_FAST,
    ENEMY_SPEED_MEDIUM,
    ENEMY_SPEED_SLOW,
    ENEMY_SPEEDS,
    InvalidObjectPropertyError,
    InvalidPlatformAssignmentError,
    MAX_OBJECTS_PER_ROW,
    ModelValidationError,
    MOVEMENT_STRATEGIES,
    OBJECT_TYPE_ENEMY,
    OBJECT_TYPE_TREASURE,
    OBJECT_TYPES,
    ObjectLimitExceededError,
    PLATFORM_TYPE_SPRITE,
    PlatformElement,
    Position,
    Rect,
    Scene,
    SceneObjectElement,
    STRATEGY_LEFT_PAUSE_RIGHT,
    STRATEGY_LEFT_RIGHT,
    STRATEGY_RIGHT_LEFT,
    STRATEGY_RIGHT_PAUSE_LEFT,
    STRATEGY_STATIONARY,
)

_qapp = QApplication.instance() or QApplication([])


@pytest.fixture
def empty_scene() -> Scene:
    scene = Scene(name="test_scene", width=160, height=192)
    # Add two platforms on row y=24
    plat1 = PlatformElement(
        id="plat-01",
        type=PLATFORM_TYPE_SPRITE,
        width=16,
        position=Position(10, 24),
    )
    plat2 = PlatformElement(
        id="plat-02",
        type=PLATFORM_TYPE_SPRITE,
        width=16,
        position=Position(40, 24),
    )
    # Add a platform on row y=40
    plat3 = PlatformElement(
        id="plat-03",
        type=PLATFORM_TYPE_SPRITE,
        width=16,
        position=Position(10, 40),
    )
    scene.add_platform(plat1)
    scene.add_platform(plat2)
    scene.add_platform(plat3)
    return scene


class TestObjectRowLimits:
    """Tests checking hardware constraint: max 3 objects total per platform row."""

    def test_three_objects_allowed_on_same_row(self, empty_scene: Scene):
        # 2 enemies on plat-01, 1 treasure on plat-02 (all on row y=24)
        obj1 = SceneObjectElement(
            id="enemy-1",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        obj2 = SceneObjectElement(
            id="enemy-2",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=14,
            speed=ENEMY_SPEED_MEDIUM,
            movement_strategy=STRATEGY_LEFT_RIGHT,
        )
        obj3 = SceneObjectElement(
            id="treasure-1",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/items.png",
            source_rect=Rect(8, 0, 8, 8),
            platform_id="plat-02",
            x=42,
        )

        assert empty_scene.can_add_object_to_platform("plat-01")[0] is True
        empty_scene.add_object(obj1)
        assert empty_scene.can_add_object_to_platform("plat-01")[0] is True
        empty_scene.add_object(obj2)
        assert empty_scene.can_add_object_to_platform("plat-02")[0] is True
        empty_scene.add_object(obj3)

        assert len(empty_scene.get_row_objects(24)) == 3
        empty_scene.validate()

    def test_fourth_object_on_same_row_rejected(self, empty_scene: Scene):
        for i in range(3):
            obj = SceneObjectElement(
                id=f"enemy-{i}",
                type=OBJECT_TYPE_ENEMY,
                source="tiles/chars.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-01",
                x=10 + i * 2,
                speed=ENEMY_SPEED_FAST,
                movement_strategy=STRATEGY_STATIONARY,
            )
            empty_scene.add_object(obj)

        can_add, reason = empty_scene.can_add_object_to_platform("plat-01")
        assert can_add is False
        assert "Row already has 3 objects" in reason or "3" in reason

        # Trying to add 4th object must raise ObjectLimitExceededError
        obj4 = SceneObjectElement(
            id="treasure-4",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/items.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-02",  # also row 24!
            x=44,
        )
        with pytest.raises(ObjectLimitExceededError):
            empty_scene.add_object(obj4)

    def test_removing_object_frees_capacity(self, empty_scene: Scene):
        for i in range(3):
            empty_scene.add_object(
                SceneObjectElement(
                    id=f"obj-{i}",
                    type=OBJECT_TYPE_ENEMY,
                    source="tiles/chars.png",
                    source_rect=Rect(0, 0, 8, 8),
                    platform_id="plat-01",
                    x=10 + i * 2,
                    speed=ENEMY_SPEED_SLOW,
                    movement_strategy=STRATEGY_STATIONARY,
                )
            )

        assert empty_scene.can_add_object_to_platform("plat-01")[0] is False

        # Remove obj-1
        empty_scene.remove_object("obj-1")
        assert len(empty_scene.get_row_objects(24)) == 2
        assert empty_scene.can_add_object_to_platform("plat-01")[0] is True

        # Now can add a new treasure
        empty_scene.add_object(
            SceneObjectElement(
                id="new-treasure",
                type=OBJECT_TYPE_TREASURE,
                source="tiles/items.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-02",
                x=40,
            )
        )
        assert len(empty_scene.get_row_objects(24)) == 3

    def test_moving_object_to_full_row_rejected(self, empty_scene: Scene):
        # 3 objects on row y=24
        for i in range(3):
            empty_scene.add_object(
                SceneObjectElement(
                    id=f"obj-{i}",
                    type=OBJECT_TYPE_ENEMY,
                    source="tiles/chars.png",
                    source_rect=Rect(0, 0, 8, 8),
                    platform_id="plat-01",
                    x=10 + i,
                    speed=ENEMY_SPEED_SLOW,
                    movement_strategy=STRATEGY_STATIONARY,
                )
            )

        # 1 object on row y=40 (plat-03)
        obj_row40 = SceneObjectElement(
            id="obj-row40",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/items.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-03",
            x=12,
        )
        empty_scene.add_object(obj_row40)

        # Attempting to move obj-row40 to plat-01 (row 24) must be rejected
        can_move, reason = empty_scene.can_add_object_to_platform("plat-01", exclude_id="obj-row40")
        assert can_move is False

        with pytest.raises(ObjectLimitExceededError):
            empty_scene.update_object_props("obj-row40", new_platform_id="plat-01")


class TestPlatformBindingAndCascades:
    """Tests checking platform association and cascade behavior."""

    def test_object_without_platform_rejected(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="orphan-obj",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="non-existent-plat",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        with pytest.raises(InvalidPlatformAssignmentError):
            empty_scene.add_object(obj)

    def test_vertical_position_convention(self, empty_scene: Scene):
        # Object height 12, platform at y=24
        obj = SceneObjectElement(
            id="enemy-pos",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 12),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        empty_scene.add_object(obj)

        plat = empty_scene.get_platform("plat-01")
        # Visual top of object is platform.y - obj.height
        expected_top_y = plat.position.y - obj.height
        assert expected_top_y == 24 - 12 == 12

    def test_deleting_platform_removes_attached_objects(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="enemy-cascade",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=12,
            speed=ENEMY_SPEED_MEDIUM,
            movement_strategy=STRATEGY_STATIONARY,
        )
        empty_scene.add_object(obj)
        assert empty_scene.get_object("enemy-cascade") is not None

        # Remove plat-01
        empty_scene.remove_platform("plat-01")
        assert empty_scene.get_platform("plat-01") is None
        assert empty_scene.get_object("enemy-cascade") is None
        # Scene validation should pass with no orphaned objects
        empty_scene.validate()

    def test_moving_platform_shifts_attached_objects(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="enemy-shift",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=15,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        empty_scene.add_object(obj)

        # Move plat-01 from (10, 24) to (20, 24) -> dx = +10 (plat-02 is at 40)
        empty_scene.move_platform("plat-01", 20, 24)
        updated_obj = empty_scene.get_object("enemy-shift")
        assert updated_obj.x == 15 + 10 == 25

    def test_moving_platform_to_full_row_rejected(self, empty_scene: Scene):
        # Put 3 objects on row 24
        for i in range(3):
            empty_scene.add_object(
                SceneObjectElement(
                    id=f"obj-r24-{i}",
                    type=OBJECT_TYPE_TREASURE,
                    source="tiles/items.png",
                    source_rect=Rect(0, 0, 8, 8),
                    platform_id="plat-01",
                    x=10 + i,
                )
            )

        # Put 1 object on plat-03 (row 40)
        empty_scene.add_object(
            SceneObjectElement(
                id="obj-r40",
                type=OBJECT_TYPE_ENEMY,
                source="tiles/chars.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-03",
                x=10,
                speed=ENEMY_SPEED_SLOW,
                movement_strategy=STRATEGY_STATIONARY,
            )
        )

        # Attempting to move plat-03 from row 40 to row 24 must fail due to object limit
        with pytest.raises(ObjectLimitExceededError):
            empty_scene.move_platform("plat-03", 80, 24)


class TestEnemyProperties:
    """Tests for enemy speed and movement strategy validation."""

    def test_all_three_speeds_valid(self, empty_scene: Scene):
        for spd in [ENEMY_SPEED_SLOW, ENEMY_SPEED_MEDIUM, ENEMY_SPEED_FAST]:
            obj = SceneObjectElement(
                id=f"enemy-{spd}",
                type=OBJECT_TYPE_ENEMY,
                source="tiles/chars.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-01",
                x=10,
                speed=spd,
                movement_strategy=STRATEGY_STATIONARY,
            )
            empty_scene.add_object(obj)
            empty_scene.remove_object(obj.id)

    def test_invalid_speed_rejected(self):
        obj = SceneObjectElement(
            id="bad-speed",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed="supersonic",
            movement_strategy=STRATEGY_STATIONARY,
        )
        with pytest.raises(InvalidObjectPropertyError):
            obj.validate()

    def test_all_five_strategies_valid(self, empty_scene: Scene):
        strategies = [
            STRATEGY_STATIONARY,
            STRATEGY_LEFT_RIGHT,
            STRATEGY_RIGHT_LEFT,
            STRATEGY_LEFT_PAUSE_RIGHT,
            STRATEGY_RIGHT_PAUSE_LEFT,
        ]
        for st in strategies:
            obj = SceneObjectElement(
                id=f"enemy-{st}",
                type=OBJECT_TYPE_ENEMY,
                source="tiles/chars.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-01",
                x=10,
                speed=ENEMY_SPEED_MEDIUM,
                movement_strategy=st,
            )
            empty_scene.add_object(obj)
            empty_scene.remove_object(obj.id)

    def test_invalid_strategy_rejected(self):
        obj = SceneObjectElement(
            id="bad-strat",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_MEDIUM,
            movement_strategy="jump_and_fly",
        )
        with pytest.raises(InvalidObjectPropertyError):
            obj.validate()


class TestTreasureProperties:
    """Tests for treasure object constraints."""

    def test_treasure_has_no_movement_parameters(self, empty_scene: Scene):
        treasure = SceneObjectElement(
            id="treasure-clean",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/items.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=12,
        )
        assert treasure.speed is None
        assert treasure.movement_strategy is None
        empty_scene.add_object(treasure)
        empty_scene.validate()

    def test_treasure_with_speed_or_strategy_rejected(self):
        with pytest.raises(InvalidObjectPropertyError):
            SceneObjectElement(
                id="bad-treasure-1",
                type=OBJECT_TYPE_TREASURE,
                source="tiles/items.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-01",
                x=12,
                speed=ENEMY_SPEED_SLOW,
            ).validate()

        with pytest.raises(InvalidObjectPropertyError):
            SceneObjectElement(
                id="bad-treasure-2",
                type=OBJECT_TYPE_TREASURE,
                source="tiles/items.png",
                source_rect=Rect(0, 0, 8, 8),
                platform_id="plat-01",
                x=12,
                movement_strategy=STRATEGY_LEFT_RIGHT,
            ).validate()


class TestSerializationAndBackwardsCompatibility:
    """Tests for JSON serialization, schema compatibility, and missing graphics."""

    def test_json_roundtrip_with_objects(self, empty_scene: Scene, tmp_path: Path):
        enemy = SceneObjectElement(
            id="enemy-001",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/enemies.png",
            source_rect=Rect(0, 0, 16, 16),
            platform_id="plat-01",
            x=14,
            speed=ENEMY_SPEED_FAST,
            movement_strategy=STRATEGY_LEFT_PAUSE_RIGHT,
        )
        treasure = SceneObjectElement(
            id="treasure-001",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/treasures.png",
            source_rect=Rect(16, 0, 8, 8),
            platform_id="plat-02",
            x=45,
        )
        empty_scene.add_object(enemy)
        empty_scene.add_object(treasure)

        file_path = tmp_path / "scene_with_objs.json"
        SceneSerializer.save_to_file(empty_scene, file_path, base_dir=tmp_path)

        # Check raw JSON structure
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "objects" in data
        assert len(data["objects"]) == 2
        assert data["objects"][0]["id"] == "enemy-001"
        assert data["objects"][0]["speed"] == "fast"
        assert data["objects"][0]["movement_strategy"] == "left_pause_right"
        assert "speed" not in data["objects"][1] or data["objects"][1]["speed"] is None

        # Load back
        loaded = SceneSerializer.load_from_file(file_path, base_dir=tmp_path, validate_source_exists=False)
        assert len(loaded.objects) == 2
        l_enemy = loaded.get_object("enemy-001")
        assert l_enemy is not None
        assert l_enemy.type == OBJECT_TYPE_ENEMY
        assert l_enemy.speed == ENEMY_SPEED_FAST
        assert l_enemy.movement_strategy == STRATEGY_LEFT_PAUSE_RIGHT

        l_treasure = loaded.get_object("treasure-001")
        assert l_treasure is not None
        assert l_treasure.type == OBJECT_TYPE_TREASURE
        assert l_treasure.speed is None
        assert l_treasure.movement_strategy is None

    def test_backwards_compatibility_without_objects_key(self, tmp_path: Path):
        legacy_data = {
            "schema_version": 1,
            "scene": {
                "name": "legacy_screen",
                "width": 160,
                "height": 96,
            },
            "elements": [],
            "platforms": [
                {
                    "id": "platform-01",
                    "type": "sprite",
                    "width": 16,
                    "position": {"x": 20, "y": 24},
                }
            ],
        }
        file_path = tmp_path / "legacy.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        loaded = SceneSerializer.load_from_file(file_path, base_dir=tmp_path)
        assert hasattr(loaded, "objects")
        assert loaded.objects == []


class TestUndoRedoCommands:
    """Tests verifying Undo/Redo commands for objects."""

    def test_add_and_remove_object_undo_redo(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="enemy-undo",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )

        add_cmd = AddSceneObjectCommand(empty_scene, obj)
        add_cmd.redo()
        assert empty_scene.get_object("enemy-undo") is not None

        add_cmd.undo()
        assert empty_scene.get_object("enemy-undo") is None

        add_cmd.redo()
        assert empty_scene.get_object("enemy-undo") is not None

        rem_cmd = RemoveSceneObjectCommand(empty_scene, "enemy-undo")
        rem_cmd.redo()
        assert empty_scene.get_object("enemy-undo") is None

        rem_cmd.undo()
        assert empty_scene.get_object("enemy-undo") is not None

    def test_move_object_undo_redo(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="enemy-move",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        empty_scene.add_object(obj)

        cmd = MoveSceneObjectCommand(empty_scene, "enemy-move", 10, 22)
        cmd.redo()
        assert empty_scene.get_object("enemy-move").x == 22

        cmd.undo()
        assert empty_scene.get_object("enemy-move").x == 10

    def test_update_object_props_undo_redo(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="enemy-prop",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/chars.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        empty_scene.add_object(obj)

        cmd = UpdateSceneObjectPropsCommand(
            empty_scene,
            "enemy-prop",
            new_speed=ENEMY_SPEED_FAST,
            new_strategy=STRATEGY_RIGHT_LEFT,
        )
        cmd.redo()
        cur = empty_scene.get_object("enemy-prop")
        assert cur.speed == ENEMY_SPEED_FAST
        assert cur.movement_strategy == STRATEGY_RIGHT_LEFT

        cmd.undo()
        cur = empty_scene.get_object("enemy-prop")
        assert cur.speed == ENEMY_SPEED_SLOW
        assert cur.movement_strategy == STRATEGY_STATIONARY

    def test_remove_platform_restores_attached_objects_on_undo(self, empty_scene: Scene):
        obj = SceneObjectElement(
            id="obj-attached",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/items.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="plat-01",
            x=14,
        )
        empty_scene.add_object(obj)

        cmd = RemovePlatformCommand(empty_scene, "plat-01")
        cmd.redo()
        assert empty_scene.get_platform("plat-01") is None
        assert empty_scene.get_object("obj-attached") is None

        cmd.undo()
        assert empty_scene.get_platform("plat-01") is not None
        assert empty_scene.get_object("obj-attached") is not None


class TestGUIIntegrationObjects:
    """Headless GUI interaction tests for the Objects tab."""

    @pytest.fixture
    def test_app(self, tmp_path: Path, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()

        # Create dummy tileset
        img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img.save(tiles_dir / "sprites.png")

        window = MainWindow(base_dir=tmp_path)
        return window, tmp_path

    def test_add_enemy_through_gui_flow(self, test_app):
        window, tmp_path = test_app

        # 1. Add platform first
        window._on_add_platform_clicked()
        assert len(window.scene_model.platforms) == 1
        plat_id = window.scene_model.platforms[0].id

        # 2. Select tile & crop
        window.tile_browser.select_file("tiles/sprites.png")
        window.crop_editor._current_crop = Rect(0, 0, 16, 16)
        window._on_capture_crop_for_new_obj_clicked()

        # 3. Add enemy
        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_x_spin.setValue(25)
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        obj = window.scene_model.objects[0]
        assert obj.type == OBJECT_TYPE_ENEMY
        assert obj.platform_id == plat_id
        assert obj.x == 25
        assert obj.width == 16
        assert obj.height == 16

        # 4. Check status bar update
        assert "Objects: 1" in window.status_elem_count_lbl.text()

    def test_gui_rejects_fourth_object_on_same_row(self, test_app):
        window, tmp_path = test_app

        # Add platform on row y=24
        window._on_add_platform_clicked()
        plat_id = window.scene_model.platforms[0].id

        window.tile_browser.select_file("tiles/sprites.png")
        window.crop_editor._current_crop = Rect(0, 0, 8, 8)
        window._on_capture_crop_for_new_obj_clicked()
        window.new_obj_platform_combo.setCurrentIndex(0)

        # Add 3 objects on the platform (x=20..36)
        for i in range(3):
            window.new_obj_x_spin.setValue(20 + i * 4)
            window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 3

        # Attempt 4th object on same row
        window.new_obj_x_spin.setValue(25)
        window._on_add_object_clicked()

        # Count remains 3
        assert len(window.scene_model.objects) == 3

    def test_gui_property_change_and_undo(self, test_app):
        window, tmp_path = test_app
        window._on_add_platform_clicked()
        window.tile_browser.select_file("tiles/sprites.png")
        window.crop_editor._current_crop = Rect(0, 0, 8, 8)
        window._on_capture_crop_for_new_obj_clicked()
        window.new_obj_platform_combo.setCurrentIndex(0)
        window._on_add_object_clicked()

        obj_id = window.scene_model.objects[0].id
        window._on_object_selected(obj_id)

        # Change speed to fast
        idx = window.obj_prop_speed_combo.findData(ENEMY_SPEED_FAST)
        window.obj_prop_speed_combo.setCurrentIndex(idx)
        assert window.scene_model.get_object(obj_id).speed == ENEMY_SPEED_FAST

        # Undo
        window.undo_stack.undo()
        assert window.scene_model.get_object(obj_id).speed == ENEMY_SPEED_MEDIUM

        # Redo
        window.undo_stack.redo()
        assert window.scene_model.get_object(obj_id).speed == ENEMY_SPEED_FAST

    def test_delete_selected_object_gui(self, test_app):
        window, tmp_path = test_app
        window._on_add_platform_clicked()
        window.tile_browser.select_file("tiles/sprites.png")
        window.crop_editor._current_crop = Rect(0, 0, 8, 8)
        window._on_capture_crop_for_new_obj_clicked()
        window.new_obj_platform_combo.setCurrentIndex(0)
        window._on_add_object_clicked()

        obj_id = window.scene_model.objects[0].id
        window._on_object_selected(obj_id)

        # Delete
        window.delete_selected_element()
        assert len(window.scene_model.objects) == 0

        # Undo
        window.undo_stack.undo()
        assert len(window.scene_model.objects) == 1
        assert window.scene_model.objects[0].id == obj_id


class TestObjectRenderingAndGraphics:
    """Tests for graphics items, multiple sources, and missing assets."""

    def test_multiple_graphics_sources_in_objects(self, tmp_path: Path):
        scene = Scene(name="multi_source_scene", width=160, height=192)
        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=16, position=Position(10, 24))
        scene.add_platform(plat)

        obj1 = SceneObjectElement(
            id="enemy-1",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/monsters.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="p1",
            x=10,
            speed=ENEMY_SPEED_SLOW,
            movement_strategy=STRATEGY_STATIONARY,
        )
        obj2 = SceneObjectElement(
            id="treasure-1",
            type=OBJECT_TYPE_TREASURE,
            source="tiles/gems.png",
            source_rect=Rect(0, 0, 8, 8),
            platform_id="p1",
            x=18,
        )
        scene.add_object(obj1)
        scene.add_object(obj2)

        sources = scene.get_sources()
        assert "tiles/monsters.png" in sources
        assert "tiles/gems.png" in sources
        assert len(sources) == 2

    def test_graphics_item_renders_with_and_without_missing_image(self, tmp_path: Path):
        from scene_editor.asset_manager import AssetManager

        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()
        img = Image.new("RGBA", (16, 16), color=(0, 255, 0, 255))
        img.save(tiles_dir / "valid.png")

        mgr = AssetManager(base_dir=tmp_path)
        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=16, position=Position(10, 24))

        # 1. Valid graphic
        valid_obj = SceneObjectElement(
            id="enemy-valid",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/valid.png",
            source_rect=Rect(0, 0, 16, 16),
            platform_id="p1",
            x=10,
            speed=ENEMY_SPEED_FAST,
            movement_strategy=STRATEGY_LEFT_RIGHT,
        )
        item_valid = SceneObjectGraphicsItem(valid_obj, plat, mgr)
        assert item_valid.pos().x() == 10
        assert item_valid.pos().y() == 24 - 16 == 8  # Top edge is platform.y - obj.height

        # 2. Missing graphic
        missing_obj = SceneObjectElement(
            id="enemy-missing",
            type=OBJECT_TYPE_ENEMY,
            source="tiles/ghost.png",
            source_rect=Rect(0, 0, 16, 16),
            platform_id="p1",
            x=10,
            speed=ENEMY_SPEED_FAST,
            movement_strategy=STRATEGY_LEFT_RIGHT,
        )
        item_missing = SceneObjectGraphicsItem(missing_obj, plat, mgr)
        assert item_missing is not None
        assert item_missing.pos().x() == 10
        assert item_missing.pos().y() == 8

    def test_get_sources_handles_none_source(self):
        scene = Scene(name="test_sources")
        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=16, position=Position(10, 24))
        scene.add_platform(plat)

        obj = SceneObjectElement(
            id="obj1",
            type=OBJECT_TYPE_ENEMY,
            definition_id=1,
            platform_id="p1",
            x=10,
            source=None,
            source_rect=None,
        )
        scene.add_object(obj)
        # Must not raise AttributeError: 'NoneType' object has no attribute 'replace'
        sources = scene.get_sources()
        assert sources == []

    def test_add_catalogue_object_without_source_in_main_window(self, tmp_path: Path):
        from scene_editor.catalogue_model import EnemyDefinition

        window = MainWindow(base_dir=tmp_path)
        # Add a platform first
        plat = PlatformElement(id="plat-001", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        window.scene_model.add_platform(plat)
        window._sync_all()

        # Add enemy definition
        window.catalogues.add_enemy(EnemyDefinition(id=5, name="Goblin", rgb_color=(200, 50, 50)))
        window._refresh_object_creator_definitions()
        window._refresh_object_creator_platforms()

        # Select platform and definition in creator UI
        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_definition_combo.setCurrentIndex(0)
        assert window._new_obj_source is None

        # Add object to scene
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        added_obj = window.scene_model.objects[0]
        assert added_obj.definition_id == 5
        assert added_obj.platform_id == "plat-001"
        assert added_obj.source is None

        # Verify graphics item was created in scene_view
        obj_items = [it for it in window.scene_view.scene().items() if isinstance(it, SceneObjectGraphicsItem)]
        assert len(obj_items) == 1
        assert obj_items[0].scene_object.id == added_obj.id

        # Verify undo and redo work cleanly without exception
        window.undo_stack.undo()
        assert len(window.scene_model.objects) == 0
        window.undo_stack.redo()
        assert len(window.scene_model.objects) == 1

    def test_objects_tab_ui_specifications(self, tmp_path: Path):
        from scene_editor.catalogue_model import EnemyDefinition

        window = MainWindow(base_dir=tmp_path)
        # 1. No "Manage Catalogues" button on objects tab
        assert not hasattr(window, "btn_manage_catalogues")

        # Add platform and enemy definition
        plat = PlatformElement(id="plat-001", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        window.scene_model.add_platform(plat)
        window.catalogues.add_enemy(EnemyDefinition(id=1, name="Bat"))
        window._sync_all()

        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_definition_combo.setCurrentIndex(0)
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        obj = window.scene_model.objects[0]
        # 2. Numeric ID in range 1-255
        assert isinstance(obj.id, int)
        assert 1 <= obj.id <= 255

        # Select the object and verify property panel
        window.objects_list.setCurrentRow(0)
        assert window.obj_prop_id_spin.value() == obj.id

        # 3. Platform dropdown is read-only / disabled
        assert not window.obj_prop_platform_combo.isEnabled()

        # Test changing object ID via spinbox
        window.obj_prop_id_spin.setValue(42)
        assert obj.id == 42

        # Test undo / redo for ID change
        window.undo_stack.undo()
        assert obj.id == 1
        window.undo_stack.redo()
        assert obj.id == 42

    def test_click_object_on_canvas_selects_and_populates_properties(self, tmp_path: Path):
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem
        from scene_editor.catalogue_model import EnemyDefinition

        window = MainWindow(base_dir=tmp_path)
        plat = PlatformElement(id="plat-001", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        window.scene_model.add_platform(plat)
        window.catalogues.add_enemy(EnemyDefinition(id=7, name="Spider"))
        window._sync_all()

        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_definition_combo.setCurrentIndex(0)
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        created_obj = window.scene_model.objects[0]

        # Deselect everything first
        window.scene_view.select_object(None)
        window.prop_tabs.setCurrentIndex(0)

        # Find the graphics item on canvas
        obj_items = [it for it in window.scene_view.scene().items() if isinstance(it, SceneObjectGraphicsItem)]
        assert len(obj_items) == 1
        obj_item = obj_items[0]

        # Verify paint runs cleanly without NameError or exceptions
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        opt = QStyleOptionGraphicsItem()
        obj_item.paint(p, opt)
        p.end()

        # Simulate clicking the object on the canvas
        obj_item.setSelected(True)

        # Verify object selection signal correctly populated Selected Object panel
        assert window.scene_view.get_selected_object_id() == created_obj.id
        assert window.obj_elem_group.isEnabled()
        assert window.obj_prop_id_spin.value() == created_obj.id
        # Verify tab switched to Objects tab (index 2)
        assert window.prop_tabs.currentIndex() == 2

        # Verify can_add_object_to_platform works with exclude_obj_id alias
        ok, msg = window.scene_model.can_add_object_to_platform("plat-001", exclude_obj_id=created_obj.id)
        assert ok

    def test_selected_object_components_enabled_and_only_platform_readonly(self, tmp_path: Path):
        from scene_editor.catalogue_model import EnemyDefinition, SecretDefinition

        window = MainWindow(base_dir=tmp_path)
        plat = PlatformElement(id="plat-001", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        window.scene_model.add_platform(plat)
        window.catalogues.add_enemy(EnemyDefinition(id=1, name="Bat"))
        window.catalogues.add_secret(SecretDefinition(id=2, name="Gold"))
        window._sync_all()

        # Switch to Objects tab
        window.prop_tabs.setCurrentIndex(2)

        # Before any object added, components in Selected Object are enabled and only platform is disabled
        assert window.obj_elem_group.isEnabled()
        assert window.obj_prop_id_spin.isEnabled()
        assert window.obj_prop_type_combo.isEnabled()
        assert window.obj_prop_definition_combo.isEnabled()
        assert not window.obj_prop_platform_combo.isEnabled()  # Read-only!
        assert window.obj_prop_x_spin.isEnabled()
        assert window.obj_prop_speed_combo.isEnabled()
        assert window.obj_prop_strategy_combo.isEnabled()
        assert window.btn_delete_obj.isEnabled()

        # Add enemy object
        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_definition_combo.setCurrentIndex(0)
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        obj = window.scene_model.objects[0]

        # Selected Object panel is enabled with only platform disabled
        assert window.obj_elem_group.isEnabled()
        assert window.obj_prop_id_spin.isEnabled()
        assert window.obj_prop_type_combo.isEnabled()
        assert window.obj_prop_definition_combo.isEnabled()
        assert not window.obj_prop_platform_combo.isEnabled()  # Read-only!
        assert window.obj_prop_x_spin.isEnabled()
        assert window.obj_prop_speed_combo.isEnabled()
        assert window.obj_prop_strategy_combo.isEnabled()
        assert window.btn_delete_obj.isEnabled()

        # Changing components under Selected Object works as expected
        # 1. Change position X via spinbox
        window.obj_prop_x_spin.setValue(18)
        assert obj.x == 18

        # 2. Change speed via combo
        s_idx = window.obj_prop_speed_combo.findData(ENEMY_SPEED_FAST)
        window.obj_prop_speed_combo.setCurrentIndex(s_idx)
        assert obj.speed == ENEMY_SPEED_FAST

        # 3. Change strategy via combo
        st_idx = window.obj_prop_strategy_combo.findData(STRATEGY_LEFT_RIGHT)
        window.obj_prop_strategy_combo.setCurrentIndex(st_idx)
        assert obj.movement_strategy == STRATEGY_LEFT_RIGHT

    def test_load_01_forest_scene_with_numeric_objects(self):
        window = MainWindow(base_dir=Path("."))
        forest_file = Path("scenes/01-forest.json")
        if forest_file.is_file():
            window.open_scene(str(forest_file))
            assert len(window.scene_model.objects) == 4
            for o in window.scene_model.objects:
                assert isinstance(o.id, int)
                assert 1 <= o.id <= 255
            # Test moving object 1
            old_x = window.scene_model.get_object(1).x
            window._on_object_moved_by_view(1, (old_x, "platform-010"), (old_x + 4, "platform-010"))
            assert window.scene_model.get_object(1).x == old_x + 4
            window.undo_stack.undo()
            assert window.scene_model.get_object(1).x == old_x






