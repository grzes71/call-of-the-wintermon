"""Headless integration tests for MainWindow and GUI interaction flows."""

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
from scene_editor.main_window import MainWindow
from scene_editor.scene_model import Rect

# Initialize headless QApplication once
_qapp = QApplication.instance() or QApplication([])


class TestMainWindowIntegration:
    @pytest.fixture
    def test_app(self, tmp_path: Path):
        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()

        # Create test tile
        img = Image.new("RGBA", (64, 32), color=(100, 150, 200, 255))
        img.save(tiles_dir / "grass.png")

        window = MainWindow(base_dir=tmp_path)
        return window, tmp_path, tiles_dir / "grass.png"

    def test_window_init_and_tiles_browser(self, test_app):
        window, tmp_path, tile_path = test_app
        assert window.scene_model.width == 160
        assert window.scene_model.height == 192
        assert window.tile_browser.list_widget.count() == 1
        assert window.tile_browser.list_widget.item(0).text() == "grass.png"

    def test_add_element_flow(self, test_app):
        window, tmp_path, tile_path = test_app
        # Select tile
        window.tile_browser.select_file("tiles/grass.png")
        assert window.crop_editor.current_source is not None

        # Add element
        crop_rect = Rect(x=0, y=0, width=16, height=16)
        window._on_add_element_requested("tiles/grass.png", crop_rect)

        assert len(window.scene_model.elements) == 1
        elem = window.scene_model.elements[0]
        assert elem.id == "element-001"
        assert elem.width == 16
        assert elem.height == 16
        assert elem.source == "tiles/grass.png"
        assert "tiles/grass.png" in window.scene_model.get_sources()

        # Add second element from another graphic
        # Create stone tile
        stone_img = Image.new("RGBA", (32, 32), color=(180, 180, 180, 255))
        stone_img.save(tmp_path / "tiles" / "stone.png")
        window.tile_browser.reload_tiles()
        window.tile_browser.select_file("tiles/stone.png")

        window._on_add_element_requested("tiles/stone.png", Rect(0, 0, 16, 16))
        assert len(window.scene_model.elements) == 2
        assert window.scene_model.elements[1].source == "tiles/stone.png"
        assert len(window.scene_model.get_sources()) == 2

        # Check UI synchronizations
        assert window.layers_list.count() == 2
        assert window.scene_view.get_selected_element_id() == "element-002"

    def test_flip_and_delete_flow(self, test_app):
        window, tmp_path, tile_path = test_app
        window._on_add_element_requested("tiles/grass.png", Rect(0, 0, 16, 16))
        elem_id = window.scene_model.elements[0].id

        # Toggle flip
        window.scene_view.select_element(elem_id)
        window.toggle_flip_selected()
        assert window.scene_model.elements[0].flip_x is True

        # Undo flip
        window.undo_stack.undo()
        assert window.scene_model.elements[0].flip_x is False

        # Redo flip
        window.undo_stack.redo()
        assert window.scene_model.elements[0].flip_x is True

        # Delete element
        window.delete_selected_element()
        assert len(window.scene_model.elements) == 0

        # Undo delete
        window.undo_stack.undo()
        assert len(window.scene_model.elements) == 1

    def test_save_and_reopen_project(self, test_app):
        window, tmp_path, tile_path = test_app
        window._on_add_element_requested("tiles/grass.png", Rect(0, 0, 24, 16))

        save_target = tmp_path / "test_scene.json"
        window.current_file_path = save_target
        assert window.save_scene() is True
        assert save_target.is_file()

        # Create new scene (clears model)
        window.new_scene(prompt_dialog=False)
        assert len(window.scene_model.elements) == 0

        # Load back the saved scene directly
        from scene_editor.json_serializer import SceneSerializer

        loaded = SceneSerializer.load_from_file(save_target, base_dir=tmp_path)
        assert len(loaded.elements) == 1
        assert loaded.elements[0].source_rect.width == 24

    def test_platform_gui_collision_rejection(self, test_app, monkeypatch):
        window, tmp_path, tile_path = test_app
        from PySide6.QtWidgets import QMessageBox

        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append((title, text)))

        # Switch to platforms tab
        window.prop_tabs.setCurrentIndex(1)

        # 1. Add first platform at (20, 8), width=16
        window.new_plat_x_spin.setValue(20)
        idx = window.new_plat_width_combo.findData(16)
        if idx >= 0:
            window.new_plat_width_combo.setCurrentIndex(idx)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 1
        p1 = window.scene_model.platforms[0]
        assert p1.position.x == 20
        assert p1.position.y == 8

        # 2. Try adding colliding platform at (28, 8) overlapping [20..36)
        window.new_plat_x_spin.setValue(28)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 1
        assert len(warnings) == 1
        assert warnings[-1][0] == "Platform Collision"

        # 3. Add second platform in non-overlapping spot (60, 8)
        window.new_plat_x_spin.setValue(60)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 2
        p2 = window.scene_model.platforms[1]
        assert p2.position.x == 60

        # 4. Try dragging/moving p2 to overlap p1 via _on_platform_moved_by_view
        window._on_platform_moved_by_view(p2.id, (60, 8), (25, 8))
        assert p2.position.x == 60  # unchanged
        assert len(warnings) == 2
        assert warnings[-1][0] == "Platform Collision"

        # 5. Try moving via property spinbox
        window._on_platform_selected(p2.id)
        window.plat_prop_x_spin.setValue(25)  # Triggers _on_plat_prop_x_changed
        assert p2.position.x == 60  # unchanged
        assert len(warnings) == 3
        assert warnings[-1][0] == "Platform Collision"

    def test_platform_gui_resource_limit_rejection(self, test_app, monkeypatch):
        window, tmp_path, tile_path = test_app
        from PySide6.QtWidgets import QMessageBox

        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append((title, text)))

        # Switch to platforms tab
        window.prop_tabs.setCurrentIndex(1)

        # 1. Add sprite platform width 64 at (0, 8) -> 2 sprites
        window.new_plat_x_spin.setValue(0)
        idx_64 = window.new_plat_width_combo.findData(64)
        assert idx_64 >= 0
        window.new_plat_width_combo.setCurrentIndex(idx_64)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 1

        # 2. Add sprite platform width 32 at (70, 8) -> 1 sprite -> total 3 sprites (row 8 full)
        window.new_plat_x_spin.setValue(70)
        idx_32 = window.new_plat_width_combo.findData(32)
        assert idx_32 >= 0
        window.new_plat_width_combo.setCurrentIndex(idx_32)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 2

        # 3. Check property panel status label for row 8
        window._on_platform_selected(window.scene_model.platforms[1].id)
        assert "Sprite: 3/3" in window.plat_prop_row_status_lbl.text()
        assert "Missile: 0/4" in window.plat_prop_row_status_lbl.text()

        # 4. Try adding a 3rd sprite platform at (110, 8) width 16 -> exceeds limit (3+1=4)
        window.new_plat_x_spin.setValue(110)
        idx_16 = window.new_plat_width_combo.findData(16)
        window.new_plat_width_combo.setCurrentIndex(idx_16)
        window.btn_add_plat.click()
        assert len(window.scene_model.platforms) == 2  # rejected
        assert len(warnings) == 1
        assert "Invalid Platform Position" in warnings[-1][0]

        # 5. Try resizing platform 2 from 32 to 36 -> needs 2 sprites (total would be 4)
        p2_id = window.scene_model.platforms[1].id
        window._on_platform_selected(p2_id)
        idx_prop_36 = window.plat_prop_width_combo.findData(36)
        assert idx_prop_36 >= 0
        window.plat_prop_width_combo.setCurrentIndex(idx_prop_36)
        assert window.scene_model.get_platform(p2_id).width == 32  # preserved
        assert len(warnings) == 2
        assert "Hardware Resource Limit" in warnings[-1][0]

    def test_open_scene_with_file_dialog(self, test_app, monkeypatch):
        window, tmp_path, tile_path = test_app
        import json
        from PySide6.QtWidgets import QFileDialog

        scene_file = tmp_path / "test_open.json"
        scene_data = {
            "schema_version": 1,
            "scene": {"name": "Test Open Dialog", "width": 160, "height": 96},
            "elements": [],
            "platforms": [],
            "objects": [],
        }
        scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

        # Simulate QFileDialog.getOpenFileName returning the file path when open_scene() called without args
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(scene_file), "Scene JSON (*.json)"),
        )

        window.open_scene(None)
        assert window.current_file_path == scene_file.resolve()
        assert window.scene_model.name == "Test Open Dialog"

