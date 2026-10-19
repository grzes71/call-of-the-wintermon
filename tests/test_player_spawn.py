"""Unit and integration tests for Player Spawn feature in Atari Scene Editor and build pipeline."""

import json
import os
from pathlib import Path
import sys

# Ensure offscreen Qt for headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure editor src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
import pytest

from scene_editor.commands import (
    ChangePlayerSpawnColorCommand,
    MovePlayerSpawnCommand,
    SetPlayerSpawnCommand,
)
from scene_editor.json_serializer import SceneSerializer
from scene_editor.main_window import MainWindow
from scene_editor.scene_items import PlayerSpawnGraphicsItem
from scene_editor.scene_model import (
    ModelValidationError,
    PlatformElement,
    PLATFORM_TYPE_SPRITE,
    PlayerSpawn,
    PLAYER_HEIGHT,
    PLAYER_WIDTH,
    Position,
    Rect,
    Scene,
)
from scripts.compile_scenes import (
    CatalogueItem,
    generate_scenes_asm,
    parse_scene_json,
    SceneCompiledData,
)

# Headless QApplication instance
_qapp = QApplication.instance() or QApplication([])


class TestPlayerSpawnModel:
    """Tests for PlayerSpawn dataclass and Scene model integration."""

    def test_valid_player_spawn_creation(self):
        spawn = PlayerSpawn(x=24, y=60)
        assert spawn.x == 24
        assert spawn.y == 60
        assert spawn.width == PLAYER_WIDTH
        assert spawn.height == PLAYER_HEIGHT
        assert spawn.bottom == 80
        assert spawn.right == 32

    def test_validation_within_scene_bounds(self):
        spawn = PlayerSpawn(x=0, y=0)
        spawn.validate(scene_width=160, scene_height=96)

        spawn_max = PlayerSpawn(x=160 - PLAYER_WIDTH, y=96 - PLAYER_HEIGHT)
        spawn_max.validate(scene_width=160, scene_height=96)

    def test_validation_out_of_bounds_raises(self):
        # Negative X
        with pytest.raises(ModelValidationError, match="out of scene bounds"):
            PlayerSpawn(x=-1, y=20).validate(160, 96)

        # Negative Y
        with pytest.raises(ModelValidationError, match="out of scene bounds"):
            PlayerSpawn(x=20, y=-5).validate(160, 96)

        # Exceeds width
        with pytest.raises(ModelValidationError, match="out of scene bounds"):
            PlayerSpawn(x=160 - PLAYER_WIDTH + 1, y=20).validate(160, 96)

        # Exceeds height
        with pytest.raises(ModelValidationError, match="out of scene bounds"):
            PlayerSpawn(x=20, y=96 - PLAYER_HEIGHT + 1).validate(160, 96)

    def test_clone_and_to_dict_from_dict(self):
        spawn = PlayerSpawn(x=32, y=50, color=0x38)
        clone = spawn.clone()
        assert clone == spawn
        assert clone is not spawn

        d = spawn.to_dict()
        assert d == {"x": 32, "y": 50, "color": 0x38}

        spawn_from_d = PlayerSpawn.from_dict(d)
        assert spawn_from_d == spawn
        assert spawn_from_d.color == 0x38

    def test_color_validation(self):
        # Valid even colors
        PlayerSpawn(x=10, y=10, color=0x00).validate(160, 96)
        PlayerSpawn(x=10, y=10, color=0xFE).validate(160, 96)

        # Invalid: odd luminance
        with pytest.raises(ModelValidationError, match="lowest bit must be 0"):
            PlayerSpawn(x=10, y=10, color=0x99).validate(160, 96)

        # Invalid: out of range
        with pytest.raises(ModelValidationError, match="between 0 and 255"):
            PlayerSpawn(x=10, y=10, color=-2).validate(160, 96)
        with pytest.raises(ModelValidationError, match="between 0 and 255"):
            PlayerSpawn(x=10, y=10, color=256).validate(160, 96)

    def test_scene_model_player_spawn_helpers(self):
        scene = Scene(name="Test", width=160, height=96)
        assert scene.player_spawn is None

        scene.set_player_spawn(30, 40, color=0x28)
        assert scene.player_spawn is not None
        assert scene.player_spawn.x == 30
        assert scene.player_spawn.y == 40
        assert scene.player_spawn.color == 0x28

        scene.validate()

        scene.remove_player_spawn()
        assert scene.player_spawn is None
        scene.validate()

    def test_scene_validation_fails_on_invalid_player_spawn(self):
        scene = Scene(name="Test", width=160, height=96)
        scene.player_spawn = PlayerSpawn(x=158, y=10)  # 158 + 8 = 166 > 160
        with pytest.raises(ModelValidationError):
            scene.validate()


class TestPlayerSpawnSerialization:
    """Tests for JSON serialization and backward compatibility."""

    def test_round_trip_with_player_spawn(self):
        scene = Scene(name="Forest Spawn", width=160, height=96)
        scene.set_player_spawn(44, 52, color=0x78)

        data = SceneSerializer.to_dict(scene)
        assert "player_spawn" in data
        assert data["player_spawn"] == {"x": 44, "y": 52, "color": 0x78}

        restored = SceneSerializer.from_dict(data)
        assert restored.player_spawn is not None
        assert restored.player_spawn.x == 44
        assert restored.player_spawn.y == 52
        assert restored.player_spawn.color == 0x78


    def test_backward_compatibility_when_omitted(self):
        raw_json = {
            "schema_version": 1,
            "scene": {"name": "Old Scene", "width": 160, "height": 96},
            "elements": [],
            "platforms": [],
            "objects": [],
        }
        scene = SceneSerializer.from_dict(raw_json)
        assert scene.player_spawn is None

    def test_deserialization_with_null_player_spawn(self):
        raw_json = {
            "schema_version": 1,
            "scene": {"name": "Old Scene", "width": 160, "height": 96},
            "player_spawn": None,
            "elements": [],
            "platforms": [],
            "objects": [],
        }
        scene = SceneSerializer.from_dict(raw_json)
        assert scene.player_spawn is None


class TestPlayerSpawnCommands:
    """Tests for Undo/Redo commands controlling player spawn."""

    def test_set_player_spawn_command(self):
        scene = Scene(name="CmdTest", width=160, height=96)
        callback_count = 0

        def cb():
            nonlocal callback_count
            callback_count += 1

        cmd = SetPlayerSpawnCommand(scene, PlayerSpawn(x=16, y=60), callback=cb)
        cmd.redo()
        assert scene.player_spawn == PlayerSpawn(x=16, y=60)
        assert callback_count == 1

        cmd.undo()
        assert scene.player_spawn is None
        assert callback_count == 2

    def test_move_player_spawn_command(self):
        scene = Scene(name="MoveTest", width=160, height=96)
        scene.set_player_spawn(10, 20)

        cmd = MovePlayerSpawnCommand(scene, (10, 20), (30, 45))
        cmd.redo()
        assert scene.player_spawn.x == 30
        assert scene.player_spawn.y == 45

        cmd.undo()
        assert scene.player_spawn.x == 10
        assert scene.player_spawn.y == 20

    def test_change_player_spawn_color_command(self):
        scene = Scene(name="ColorTest", width=160, height=96)
        scene.set_player_spawn(10, 20, color=0x98)

        cmd = ChangePlayerSpawnColorCommand(scene, 0x98, 0x38)
        cmd.redo()
        assert scene.player_spawn.color == 0x38

        cmd.undo()
        assert scene.player_spawn.color == 0x98



class TestSceneCompilerPlayerSpawn:
    """Tests for compiler parsing and assembly generation of player start tables."""

    def test_compiler_extracts_player_spawn(self, tmp_path: Path):
        scene_file = tmp_path / "03-test-spawn.json"
        scene_content = {
            "scene": {"name": "Test Scene", "width": 160, "height": 96},
            "player_spawn": {"x": 48, "y": 72},
            "elements": [],
            "platforms": [],
            "objects": [],
        }
        scene_file.write_text(json.dumps(scene_content), encoding="utf-8")

        compiled = parse_scene_json(
            scene_file=scene_file,
            enemies={},
            secrets={},
        )
        assert compiled.player_start_x == 48
        assert compiled.player_start_y == 72

    def test_compiler_defaults_when_spawn_missing(self, tmp_path: Path):
        scene_file = tmp_path / "04-no-spawn.json"
        scene_content = {
            "scene": {"name": "No Spawn", "width": 160, "height": 96},
            "elements": [],
            "platforms": [],
            "objects": [],
        }
        scene_file.write_text(json.dumps(scene_content), encoding="utf-8")

        compiled = parse_scene_json(
            scene_file=scene_file,
            enemies={},
            secrets={},
        )
        assert compiled.player_start_x == 20
        assert compiled.player_start_y == 68

    def test_assembly_generation_includes_player_start_tables(self):
        sc1 = SceneCompiledData(
            file_stem="01-forest",
            symbol_name="forest",
            name="Dark Forest",
            width=160,
            height=96,
            primary_tileset_id=3,
            player_start_x=24,
            player_start_y=68,
            player_color=0x98,
        )
        sc2 = SceneCompiledData(
            file_stem="02-castle",
            symbol_name="castle",
            name="Castle Hall",
            width=160,
            height=96,
            primary_tileset_id=0,
            player_start_x=40,
            player_start_y=52,
            player_color=0x28,
        )

        asm = generate_scenes_asm([sc1, sc2])
        assert "SCENE_FOREST_PLAYER_START_X = 24" in asm
        assert "SCENE_FOREST_PLAYER_START_Y = 68" in asm
        assert "SCENE_FOREST_PLAYER_COLOR   = $98" in asm
        assert "SCENE_CASTLE_PLAYER_START_X = 40" in asm
        assert "SCENE_CASTLE_PLAYER_START_Y = 52" in asm
        assert "SCENE_CASTLE_PLAYER_COLOR   = $28" in asm

        assert "scene_player_start_x\n    .byte 24, 40" in asm
        assert "scene_player_start_y\n    .byte 68, 52" in asm
        assert "scene_player_color\n    .byte $98, $28" in asm


class TestMainWindowPlayerSpawnUI:
    """Integration tests for MainWindow Player Start tab, controls, and canvas item."""

    @pytest.fixture
    def test_app(self, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        return window

    def test_initial_state_without_spawn(self, test_app: MainWindow):
        window = test_app
        assert window.scene_model.player_spawn is None
        assert window.btn_set_player_spawn.isEnabled()
        assert not window.player_x_spin.isEnabled()
        assert not window.player_y_spin.isEnabled()
        assert not window.player_color_spin.isEnabled()
        assert not window.btn_remove_player_spawn.isEnabled()
        assert window.scene_view.player_spawn_item is None

    def test_set_and_remove_player_spawn_via_buttons(self, test_app: MainWindow):
        window = test_app
        # Click set spawn button
        window.btn_set_player_spawn.click()

        assert window.scene_model.player_spawn is not None
        assert window.scene_model.player_spawn.x == 20
        assert window.scene_model.player_spawn.y == 68
        assert window.scene_model.player_spawn.color == 0x98
        assert not window.btn_set_player_spawn.isEnabled()
        assert window.player_x_spin.isEnabled()
        assert window.player_y_spin.isEnabled()
        assert window.player_color_spin.isEnabled()
        assert window.player_x_spin.value() == 20
        assert window.player_y_spin.value() == 68
        assert window.player_color_spin.value() == 0x98
        assert window.scene_view.player_spawn_item is not None

        # Click remove spawn button
        window.btn_remove_player_spawn.click()
        assert window.scene_model.player_spawn is None
        assert window.btn_set_player_spawn.isEnabled()
        assert window.scene_view.player_spawn_item is None

        # Undo removal
        window.undo_stack.undo()
        assert window.scene_model.player_spawn is not None
        assert window.scene_view.player_spawn_item is not None

    def test_spinbox_adjustments_update_model(self, test_app: MainWindow):
        window = test_app
        window.btn_set_player_spawn.click()

        window.player_x_spin.setValue(45)
        assert window.scene_model.player_spawn.x == 45

        window.player_y_spin.setValue(55)
        assert window.scene_model.player_spawn.y == 55

        # Undo position changes
        window.undo_stack.undo()
        assert window.scene_model.player_spawn.y == 68
        window.undo_stack.undo()
        assert window.scene_model.player_spawn.x == 20

    def test_player_color_controls_in_ui(self, test_app: MainWindow):
        window = test_app
        window.btn_set_player_spawn.click()
        assert window.player_color_spin.value() == 0x98
        assert window.player_color_hex_lbl.text() == "$98"

        # Change color via spinbox to $28 (40)
        window.player_color_spin.setValue(0x28)
        assert window.scene_model.player_spawn.color == 0x28
        assert window.player_color_hex_lbl.text() == "$28"
        assert "$28" in window.scene_view.player_spawn_item.toolTip()

        # Odd value is clamped to even
        window.player_color_spin.setValue(0x29)
        assert window.scene_model.player_spawn.color == 0x28
        assert window.player_color_spin.value() == 0x28

        # Undo changes color back to $98
        window.undo_stack.undo()
        assert window.scene_model.player_spawn.color == 0x98
        assert window.player_color_spin.value() == 0x98

    def test_snap_to_platform(self, test_app: MainWindow):
        window = test_app
        # Add a platform at x=60, y=72, w=32, h=4
        plat = PlatformElement(
            id="plat-test",
            type=PLATFORM_TYPE_SPRITE,
            position=Position(x=60, y=72),
            width=32,
            height=4,
        )
        window.scene_model.add_platform(plat)
        window._sync_all()

        # Set player spawn at (20, 20)
        window.scene_model.set_player_spawn(20, 20)
        window._sync_all()

        assert window.player_snap_plat_combo.count() >= 1
        window.player_snap_plat_combo.setCurrentIndex(0)
        window.btn_snap_player.click()

        # Snapped feet at platform top (y=72 - 20 = 52) and clamped x (>= 60)
        assert window.scene_model.player_spawn.y == 52
        assert window.scene_model.player_spawn.x == 60

    def test_delete_key_removes_player_spawn(self, test_app: MainWindow):
        window = test_app
        window.btn_set_player_spawn.click()
        assert window.scene_model.player_spawn is not None

        # Select tab 3 (Player Start) and invoke delete
        window.prop_tabs.setCurrentIndex(3)
        window.delete_selected_element()
        assert window.scene_model.player_spawn is None

    def test_canvas_item_drag_movement(self, test_app: MainWindow):
        window = test_app
        window.btn_set_player_spawn.click()
        item = window.scene_view.player_spawn_item
        assert item is not None

        # Simulate movement signal from view
        window.scene_view.player_spawn_moved.emit((20, 68), (50, 40))
        assert window.scene_model.player_spawn.x == 50
        assert window.scene_model.player_spawn.y == 40
        assert window.player_x_spin.value() == 50
        assert window.player_y_spin.value() == 40

