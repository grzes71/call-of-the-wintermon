"""Comprehensive automated tests for multi-source graphics support in scene editor."""

import os
from pathlib import Path
import sys

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PIL import Image
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication
import pytest
from scene_editor.asset_manager import AssetManager
from scene_editor.commands import (
    AddElementCommand,
    FlipElementCommand,
    MoveElementCommand,
    RemoveElementCommand,
)
from scene_editor.json_serializer import SceneSerializer
from scene_editor.main_window import MainWindow
from scene_editor.scene_items import SceneGraphicsItem
from scene_editor.scene_model import Position, Rect, Scene, SceneElement
from scene_editor.scene_view import SceneView

# Initialize headless QApplication once
_qapp = QApplication.instance() or QApplication([])


class TestMultiSourceSupport:
    @pytest.fixture
    def test_environment(self, tmp_path: Path):
        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()

        # Graphic A: Red image (32x32)
        img_a = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img_a.save(tiles_dir / "bricks.png")

        # Graphic B: Green image (40x24)
        img_b = Image.new("RGBA", (40, 24), color=(0, 255, 0, 255))
        img_b.save(tiles_dir / "foliage.png")

        # Graphic C: Blue image (48x16)
        img_c = Image.new("RGBA", (48, 16), color=(0, 0, 255, 255))
        img_c.save(tiles_dir / "water.png")

        mgr = AssetManager(base_dir=tmp_path)
        return mgr, tmp_path

    # 1. Dodanie do jednej sceny dwóch elementów z różnych plików
    def test_1_add_two_elements_from_different_files(self):
        scene = Scene(name="multi_test")
        e1 = SceneElement(
            id="elem-1",
            source="tiles/bricks.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(10, 10),
        )
        e2 = SceneElement(
            id="elem-2",
            source="tiles/foliage.png",
            source_rect=Rect(0, 0, 20, 12),
            position=Position(50, 10),
        )
        scene.add_element(e1)
        scene.add_element(e2)

        assert len(scene.elements) == 2
        assert scene.elements[0].source == "tiles/bricks.png"
        assert scene.elements[1].source == "tiles/foliage.png"
        scene.validate()

    # 2. Dodanie kilku elementów z różnych źródeł bez utraty wcześniej dodanych elementów
    def test_2_add_multiple_sources_without_losing_elements(self):
        scene = Scene(name="multi_progressive")
        sources = ["tiles/bricks.png", "tiles/foliage.png", "tiles/water.png"]

        for idx, src in enumerate(sources):
            elem = SceneElement(
                id=f"elem-{idx}",
                source=src,
                source_rect=Rect(0, 0, 8, 8),
                position=Position(idx * 20, idx * 10),
            )
            scene.add_element(elem)

        assert len(scene.elements) == 3
        assert [e.id for e in scene.elements] == ["elem-0", "elem-1", "elem-2"]
        assert [e.source for e in scene.elements] == sources
        assert scene.get_sources() == sources

    # 3. Poprawne renderowanie elementów z różnych grafik
    def test_3_rendering_elements_from_different_graphics(self, test_environment):
        mgr, tmp_path = test_environment
        scene = Scene(name="render_test")
        e1 = SceneElement(
            id="e-brick",
            source="tiles/bricks.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        e2 = SceneElement(
            id="e-foliage",
            source="tiles/foliage.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(30, 0),
        )
        scene.add_element(e1)
        scene.add_element(e2)

        view = SceneView()
        view.populate_scene(scene, mgr)

        item1 = view._items_by_id["e-brick"]
        item2 = view._items_by_id["e-foliage"]

        assert item1._cached_pixmap is not None
        assert item2._cached_pixmap is not None
        # Verify brick is red and foliage is green
        img1 = item1._cached_pixmap.toImage()
        img2 = item2._cached_pixmap.toImage()
        assert img1.pixelColor(0, 0).red() == 255
        assert img1.pixelColor(0, 0).green() == 0
        assert img2.pixelColor(0, 0).green() == 255
        assert img2.pixelColor(0, 0).red() == 0

    # 4. Nakładanie się elementów pochodzących z różnych źródeł
    def test_4_overlapping_elements_from_different_sources(self):
        scene = Scene(name="overlap_test")
        e1 = SceneElement(
            id="background-brick",
            source="tiles/bricks.png",
            source_rect=Rect(0, 0, 32, 32),
            position=Position(20, 20),
            z_index=0,
        )
        e2 = SceneElement(
            id="overlay-foliage",
            source="tiles/foliage.png",
            source_rect=Rect(0, 0, 20, 20),
            position=Position(25, 25),  # Overlaps e1 completely
            z_index=1,
        )
        scene.add_element(e1)
        scene.add_element(e2)
        scene.validate()
        assert len(scene.elements) == 2

    # 5. Niezależne odbicie poziome elementów z różnych grafik
    def test_5_independent_horizontal_flip(self, test_environment):
        mgr, tmp_path = test_environment
        e1 = SceneElement(
            id="e1",
            source="tiles/bricks.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
            flip_x=False,
        )
        e2 = SceneElement(
            id="e2",
            source="tiles/foliage.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(20, 0),
            flip_x=True,
        )
        scene = Scene(elements=[e1, e2])
        scene.validate()

        assert scene.elements[0].flip_x is False
        assert scene.elements[1].flip_x is True

        # Toggling e1 must not affect e2
        scene.set_element_flip("e1", True)
        assert scene.elements[0].flip_x is True
        assert scene.elements[1].flip_x is True

        scene.set_element_flip("e2", False)
        assert scene.elements[0].flip_x is True
        assert scene.elements[1].flip_x is False

    # 6. Zachowanie kolejności rysowania
    def test_6_draw_order_preservation(self):
        scene = Scene()
        e_brick = SceneElement(
            id="brick",
            source="tiles/bricks.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        e_foliage = SceneElement(
            id="foliage",
            source="tiles/foliage.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        e_water = SceneElement(
            id="water",
            source="tiles/water.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        scene.add_element(e_brick)
        scene.add_element(e_foliage)
        scene.add_element(e_water)

        assert [e.id for e in scene.elements] == ["brick", "foliage", "water"]
        # Bring brick to front
        scene.bring_to_front("brick")
        assert [e.id for e in scene.elements] == ["foliage", "water", "brick"]
        assert [e.z_index for e in scene.elements] == [0, 1, 2]

    # 7. Zapis i odczyt JSON sceny zawierającej wiele źródeł
    def test_7_json_multisource_roundtrip(self, test_environment):
        mgr, tmp_path = test_environment
        scene = Scene(name="multi_roundtrip")
        scene.add_element(
            SceneElement(
                id="e1",
                source="tiles/bricks.png",
                source_rect=Rect(0, 0, 16, 16),
                position=Position(10, 20),
                flip_x=False,
            )
        )
        scene.add_element(
            SceneElement(
                id="e2",
                source="tiles/foliage.png",
                source_rect=Rect(4, 2, 20, 10),
                position=Position(40, 50),
                flip_x=True,
            )
        )

        target = tmp_path / "multi_scene.json"
        SceneSerializer.save_to_file(scene, target, base_dir=tmp_path)

        loaded = SceneSerializer.load_from_file(target, base_dir=tmp_path, validate_source_exists=True)
        assert len(loaded.elements) == 2
        assert loaded.elements[0].source == "tiles/bricks.png"
        assert loaded.elements[1].source == "tiles/foliage.png"
        assert loaded.elements[0].flip_x is False
        assert loaded.elements[1].flip_x is True
        assert loaded.elements[1].source_rect.width == 20

    # 8. Poprawne działanie Undo/Redo dla wielu źródeł
    def test_8_undo_redo_multisource(self):
        scene = Scene()
        stack = QUndoStack()

        e1 = SceneElement("e1", "tiles/bricks.png", Rect(0, 0, 8, 8), Position(0, 0))
        e2 = SceneElement("e2", "tiles/foliage.png", Rect(0, 0, 8, 8), Position(10, 10))

        # Push additions
        stack.push(AddElementCommand(scene, e1))
        stack.push(AddElementCommand(scene, e2))
        assert len(scene.elements) == 2

        # Move e1
        stack.push(MoveElementCommand(scene, "e1", (0, 0), (25, 30)))
        assert scene.get_element("e1").position.x == 25

        # Flip e2
        stack.push(FlipElementCommand(scene, "e2", True))
        assert scene.get_element("e2").flip_x is True

        # Remove e1
        stack.push(RemoveElementCommand(scene, "e1"))
        assert len(scene.elements) == 1
        assert scene.elements[0].id == "e2"

        # Undo remove
        stack.undo()
        assert len(scene.elements) == 2
        assert scene.get_element("e1") is not None

        # Undo flip
        stack.undo()
        assert scene.get_element("e2").flip_x is False

        # Undo move
        stack.undo()
        assert scene.get_element("e1").position.x == 0

    # 9. Obsługa brakującego pliku źródłowego przy zachowaniu pozostałych elementów
    def test_9_missing_source_fallback_preserves_elements(self, test_environment):
        mgr, tmp_path = test_environment
        scene = Scene()
        e_valid = SceneElement("valid", "tiles/bricks.png", Rect(0, 0, 16, 16), Position(0, 0))
        e_missing = SceneElement("missing", "tiles/ghost.png", Rect(0, 0, 16, 16), Position(30, 0))
        scene.add_element(e_valid)
        scene.add_element(e_missing)

        view = SceneView()
        view.populate_scene(scene, mgr)

        item_valid = view._items_by_id["valid"]
        item_missing = view._items_by_id["missing"]

        assert item_valid._missing_source is False
        assert item_valid._cached_pixmap is not None

        assert item_missing._missing_source is True
        assert item_missing._cached_pixmap is None

        # Both items are present on canvas and can be selected/manipulated
        assert len(view.canvas.items()) >= 2
        item_missing.setSelected(True)
        assert item_missing.isSelected() is True

    # 10. Poprawne działanie dotychczasowych projektów (wsteczna kompatybilność)
    def test_10_backward_compatibility_with_existing_scenes(self):
        castle_path = Path("examples/sample_castle_scene.json")
        forest_path = Path("examples/sample_forest_scene.json")

        if castle_path.is_file():
            castle = SceneSerializer.load_from_file(castle_path, validate_source_exists=True)
            assert len(castle.elements) > 0
            # Can add a new element from trees.png to the castle scene!
            castle.add_element(
                SceneElement(
                    id="new-tree",
                    source="tiles/trees.png",
                    source_rect=Rect(0, 0, 16, 16),
                    position=Position(50, 50),
                )
            )
            castle.validate()
            assert "tiles/trees.png" in castle.get_sources()

        if forest_path.is_file():
            forest = SceneSerializer.load_from_file(forest_path, validate_source_exists=True)
            assert len(forest.elements) > 0
            forest.validate()
