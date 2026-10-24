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
from scene_editor.scene_model import ANTIC_D_PLAYFIELD_HEIGHT, ANTIC_D_PLAYFIELD_WIDTH, Rect

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
        # A new scene starts as the ANTIC Mode D playfield the engine renders
        assert window.scene_model.width == ANTIC_D_PLAYFIELD_WIDTH
        assert window.scene_model.height == ANTIC_D_PLAYFIELD_HEIGHT
        assert window.tile_browser.list_widget.count() == 1
        assert window.tile_browser.list_widget.item(0).text() == "grass.png"

    def test_default_canvas_is_landscape_antic_d_playfield(self, test_app):
        """The default canvas is the ANTIC D playfield, so the scene is landscape."""
        window, _tmp_path, _tile_path = test_app
        canvas = window.scene_view.canvas
        assert canvas.canvas_width == ANTIC_D_PLAYFIELD_WIDTH
        assert canvas.canvas_height == ANTIC_D_PLAYFIELD_HEIGHT
        assert canvas.canvas_width > canvas.canvas_height, "the playfield is landscape"
        assert window.scene_group.title() == (
            f"Scene Settings ({ANTIC_D_PLAYFIELD_WIDTH} × {ANTIC_D_PLAYFIELD_HEIGHT})"
        )

    def test_fit_scene_in_view_uses_largest_integer_zoom_that_fits(self, test_app):
        """Fit Scene to View shows the whole canvas at the largest integer zoom level."""
        window, _tmp_path, _tile_path = test_app
        # Give the view a realistic (landscape) viewport through the window layout
        window.resize(1400, 900)
        window.show()
        QApplication.processEvents()

        view = window.scene_view
        view.fit_scene_in_view()

        rect = view.canvas.sceneRect()
        viewport = view.viewport().rect()
        assert viewport.width() > rect.width(), "the viewport must be wider than the playfield"
        visible = view.mapFromScene(rect).boundingRect()
        assert visible.width() <= viewport.width()
        assert visible.height() <= viewport.height()

        # The chosen level must be an integer zoom step and the largest one that still fits
        factor = view.ZOOM_LEVELS[view.zoom_index]
        margin = 8
        fit_scale = min(
            (viewport.width() - margin) / rect.width(),
            (viewport.height() - margin) / rect.height(),
        )
        assert factor <= fit_scale + 1e-6
        if view.zoom_index + 1 < len(view.ZOOM_LEVELS):
            assert view.ZOOM_LEVELS[view.zoom_index + 1] > fit_scale

    def test_scene_settings_title_flags_playfield_overflow(self, test_app):
        """Rows below the ANTIC D playfield are flagged in the Scene Settings title."""
        window, _tmp_path, _tile_path = test_app
        window.scene_model.height = 192
        window._sync_all()
        title = window.scene_group.title()
        assert "192" in title
        assert "below the visible ANTIC D playfield" in title

    def test_new_scene_dialog_defaults_to_antic_d_playfield(self, test_app):
        """The New Scene dialog offers the ANTIC D playfield as its default preset."""
        from scene_editor.main_window import NewSceneDialog

        dialog = NewSceneDialog()
        assert dialog.preset_combo.currentData() == (
            ANTIC_D_PLAYFIELD_WIDTH,
            ANTIC_D_PLAYFIELD_HEIGHT,
        )
        assert dialog.width_spin.value() == ANTIC_D_PLAYFIELD_WIDTH
        assert dialog.height_spin.value() == ANTIC_D_PLAYFIELD_HEIGHT


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

    def test_crop_snaps_to_byte_grid(self, test_app):
        """Crop x and width must snap to multiples of 4 (ANTIC Mode E packs 4 px per byte)."""
        from PySide6.QtCore import QRectF
        from scene_editor.crop_editor import SOURCE_X_ALIGN, align_crop_width, align_source_x

        window, _tmp_path, _tile_path = test_app

        assert SOURCE_X_ALIGN == 4
        assert align_source_x(0) == 0
        assert align_source_x(3) == 0
        assert align_source_x(4) == 4
        assert align_source_x(79) == 76   # the value that used to shift the crop in game
        assert align_source_x(-5) == 0

        # Widths round *up* to whole bytes so no selected pixel is dropped
        assert align_crop_width(0) == 4
        assert align_crop_width(1) == 4
        assert align_crop_width(4) == 4
        assert align_crop_width(5) == 8
        assert align_crop_width(77) == 80
        assert align_crop_width(81) == 84

        window.tile_browser.select_file("tiles/grass.png")
        editor = window.crop_editor
        assert editor.spin_x.singleStep() == SOURCE_X_ALIGN
        assert editor.spin_w.singleStep() == SOURCE_X_ALIGN

        # Spinbox input is snapped and reflected back to the user (tile is 64 px wide)
        editor.spin_x.setValue(47)
        assert editor.spin_x.value() == 44
        assert editor._current_crop.x == 44

        editor.spin_x.setValue(0)
        editor.spin_w.setValue(45)
        assert editor.spin_w.value() == 48
        assert editor._current_crop.width == 48

        # A mouse selection is snapped as well
        item = editor.canvas_view.selection_item
        item.set_crop_rect(QRectF(47, 5, 16, 10))
        assert item.rect().x() == 44
        assert item.to_rect().x == 44

        item.set_crop_rect(QRectF(4, 5, 45, 10))
        assert item.rect().width() == 48
        assert item.to_rect().width == 48

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

        # 5. Try resizing platform 2 from 32 to 48 -> needs 2 sprites (total would be 4)
        p2_id = window.scene_model.platforms[1].id
        window._on_platform_selected(p2_id)
        idx_prop_48 = window.plat_prop_width_combo.findData(48)
        assert idx_prop_48 >= 0
        window.plat_prop_width_combo.setCurrentIndex(idx_prop_48)
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

    def test_properties_dock_tabs_have_scroll_areas(self, test_app):
        """Verify that property dock tabs are enclosed in QScrollArea with resizable contents."""
        window, _, _ = test_app
        from PySide6.QtWidgets import QFrame, QScrollArea

        assert window.prop_tabs.count() == 5
        expected_titles = [
            "Tiles & Elements",
            "Hardware Platforms",
            "Objects",
            "Player Start",
            "Background Colors",
        ]

        for idx, title in enumerate(expected_titles):
            assert window.prop_tabs.tabText(idx) == title
            tab_widget = window.prop_tabs.widget(idx)
            assert isinstance(tab_widget, QScrollArea), f"Tab {idx} '{title}' must be a QScrollArea"
            assert tab_widget.widgetResizable() is True
            assert tab_widget.frameShape() == QFrame.Shape.NoFrame
            assert tab_widget.widget() is not None

        assert window.layers_list.minimumHeight() >= 100
        assert window.platforms_list.minimumHeight() >= 100
        assert window.objects_list.minimumHeight() >= 100

