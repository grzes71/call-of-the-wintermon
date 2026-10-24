"""Unit tests for Scene, SceneElement, Rect, and Position models."""

from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest
from scene_editor.scene_model import (
    ANTIC_D_PLAYFIELD_HEIGHT,
    ANTIC_D_PLAYFIELD_WIDTH,
    DuplicateElementIdError,
    ModelValidationError,
    Position,
    Rect,
    Scene,
    SceneElement,
    SingleSourceViolationError,
)


class TestRectAndPosition:
    def test_valid_rect(self):
        r = Rect(x=10, y=20, width=16, height=8)
        r.validate()
        assert r.x == 10
        assert r.y == 20
        assert r.width == 16
        assert r.height == 8
        assert r.to_dict() == {"x": 10, "y": 20, "width": 16, "height": 8}

    def test_rect_from_dict(self):
        data = {"x": 5, "y": 0, "width": 32, "height": 16}
        r = Rect.from_dict(data)
        assert r.x == 5
        assert r.width == 32

    def test_rect_invalid_dimensions(self):
        with pytest.raises(ModelValidationError):
            Rect(x=0, y=0, width=0, height=8).validate()

        with pytest.raises(ModelValidationError):
            Rect(x=0, y=0, width=16, height=-5).validate()

    def test_rect_negative_coords(self):
        with pytest.raises(ModelValidationError):
            Rect(x=-1, y=0, width=8, height=8).validate()

        with pytest.raises(ModelValidationError):
            Rect(x=0, y=-2, width=8, height=8).validate()

    def test_position_valid_and_out_of_bounds(self):
        # Positions can be negative or beyond 160x96 as elements can be moved outside bounds
        p = Position(x=-20, y=150)
        p.validate()
        assert p.to_dict() == {"x": -20, "y": 150}

    def test_position_invalid_types(self):
        with pytest.raises(ModelValidationError):
            Position(x="invalid", y=10).validate()  # type: ignore


class TestSceneModel:
    def test_scene_creation_defaults(self):
        scene = Scene(name="level_test")
        assert scene.name == "level_test"
        # Defaults = the ANTIC Mode D playfield the engine renders (160 x 96)
        assert scene.width == ANTIC_D_PLAYFIELD_WIDTH
        assert scene.height == ANTIC_D_PLAYFIELD_HEIGHT
        assert scene.schema_version == 1
        assert len(scene.elements) == 0
        scene.validate()

    def test_scene_invalid_dimensions(self):
        with pytest.raises(ModelValidationError):
            Scene(name="bad", width=0, height=192).validate()
        with pytest.raises(ModelValidationError):
            Scene(name="bad", width=160, height=-10).validate()
        with pytest.raises(ModelValidationError):
            Scene(name="bad", width=5000, height=192).validate()

    def test_add_and_remove_element(self):
        scene = Scene()
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(10, 10),
            flip_x=False,
        )
        scene.add_element(elem)
        assert len(scene.elements) == 1
        assert "tiles/castles.png" in scene.get_sources()
        assert scene.get_element("elem-1") is not None
        assert elem.width == 16
        assert elem.height == 16

        removed = scene.remove_element("elem-1")
        assert removed is not None
        assert removed.id == "elem-1"
        assert len(scene.elements) == 0

    def test_duplicate_element_id_rejected(self):
        scene = Scene()
        elem1 = SceneElement(
            id="unique-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        elem2 = SceneElement(
            id="unique-1",
            source="tiles/castles.png",
            source_rect=Rect(16, 0, 16, 16),
            position=Position(20, 20),
        )
        scene.add_element(elem1)
        with pytest.raises(DuplicateElementIdError):
            scene.add_element(elem2)

    def test_multiple_graphics_allowed(self):
        """A scene can contain elements from multiple distinct graphics files."""
        scene = Scene()
        elem1 = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
        )
        elem2 = SceneElement(
            id="elem-2",
            source="tiles/trees.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(20, 20),
        )
        elem3 = SceneElement(
            id="elem-3",
            source="tiles/hell.png",
            source_rect=Rect(0, 0, 32, 24),
            position=Position(40, 20),
        )
        scene.add_element(elem1)
        scene.add_element(elem2)
        scene.add_element(elem3)

        assert len(scene.elements) == 3
        assert scene.get_sources() == ["tiles/castles.png", "tiles/trees.png", "tiles/hell.png"]
        scene.validate()

    def test_element_draw_order_and_reordering(self):
        scene = Scene()
        for i in range(4):
            scene.add_element(
                SceneElement(
                    id=f"elem-{i}",
                    source="tiles/castles.png",
                    source_rect=Rect(0, 0, 8, 8),
                    position=Position(i * 10, 0),
                )
            )

        assert [e.id for e in scene.elements] == ["elem-0", "elem-1", "elem-2", "elem-3"]
        assert [e.z_index for e in scene.elements] == [0, 1, 2, 3]

        # Bring elem-0 to front (should become last)
        scene.bring_to_front("elem-0")
        assert [e.id for e in scene.elements] == ["elem-1", "elem-2", "elem-3", "elem-0"]
        assert [e.z_index for e in scene.elements] == [0, 1, 2, 3]

        # Send elem-0 to back (should become first)
        scene.send_to_back("elem-0")
        assert [e.id for e in scene.elements] == ["elem-0", "elem-1", "elem-2", "elem-3"]

        # Raise elem-1
        scene.raise_element("elem-1")
        assert [e.id for e in scene.elements] == ["elem-0", "elem-2", "elem-1", "elem-3"]

        # Lower elem-1
        scene.lower_element("elem-1")
        assert [e.id for e in scene.elements] == ["elem-0", "elem-1", "elem-2", "elem-3"]

    def test_elements_can_overlap_and_exceed_bounds(self):
        scene = Scene()
        elem1 = SceneElement(
            id="e1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 32, 32),
            position=Position(x=-10, y=-5),  # partially outside top-left
        )
        elem2 = SceneElement(
            id="e2",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 32, 32),
            position=Position(x=10, y=10),  # overlaps e1
        )
        elem3 = SceneElement(
            id="e3",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 32, 32),
            position=Position(x=150, y=85),  # partially outside bottom-right
        )
        scene.add_element(elem1)
        scene.add_element(elem2)
        scene.add_element(elem3)

        # Scene validation must succeed even with overlapping and out-of-bounds positions
        scene.validate()
        assert len(scene.elements) == 3

    def test_horizontal_flip_property(self):
        scene = Scene()
        elem = SceneElement(
            id="flip-test",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
            flip_x=False,
        )
        scene.add_element(elem)
        assert elem.flip_x is False

        scene.set_element_flip("flip-test", True)
        assert elem.flip_x is True
