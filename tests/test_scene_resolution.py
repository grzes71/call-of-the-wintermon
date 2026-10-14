"""Automated unit and integration tests for individual and configurable scene resolution."""

import json
from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest
from scene_editor.commands import ResizeSceneCommand
from scene_editor.json_serializer import SceneSerializer
from scene_editor.scene_model import (
    DEFAULT_SCENE_HEIGHT,
    DEFAULT_SCENE_WIDTH,
    MAX_SCENE_HEIGHT,
    MAX_SCENE_WIDTH,
    MIN_SCENE_HEIGHT,
    MIN_SCENE_WIDTH,
    ModelValidationError,
    Position,
    Rect,
    Scene,
    SceneElement,
)


class TestSceneResolution:
    def test_default_resolution_160x192(self):
        scene = Scene()
        assert scene.width == 160
        assert scene.height == 192
        assert scene.width == DEFAULT_SCENE_WIDTH
        assert scene.height == DEFAULT_SCENE_HEIGHT
        scene.validate()

    def test_custom_dimensions_valid(self):
        scene = Scene(name="wide_level", width=256, height=128)
        assert scene.width == 256
        assert scene.height == 128
        scene.validate()

        scene2 = Scene(name="tower_level", width=160, height=384)
        scene2.validate()
        assert scene2.height == 384

    def test_rejection_of_zero_and_negative_dimensions(self):
        with pytest.raises(ModelValidationError):
            Scene(width=0, height=192).validate()

        with pytest.raises(ModelValidationError):
            Scene(width=160, height=0).validate()

        with pytest.raises(ModelValidationError):
            Scene(width=-160, height=192).validate()

        with pytest.raises(ModelValidationError):
            Scene(width=160, height=-10).validate()

    def test_rejection_of_invalid_types(self):
        with pytest.raises(ModelValidationError):
            Scene(width="160", height=192).validate()  # type: ignore

        with pytest.raises(ModelValidationError):
            Scene(width=160, height=192.5).validate()  # type: ignore

        with pytest.raises(ModelValidationError):
            Scene(width=None, height=192).validate()  # type: ignore

    def test_rejection_of_dimensions_exceeding_max(self):
        with pytest.raises(ModelValidationError):
            Scene(width=MAX_SCENE_WIDTH + 1, height=192).validate()

        with pytest.raises(ModelValidationError):
            Scene(width=160, height=MAX_SCENE_HEIGHT + 1).validate()

    def test_resize_scene_method(self):
        scene = Scene(width=160, height=192)
        elem = SceneElement(
            id="e1",
            source="tiles/grass.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(100, 100),
        )
        scene.add_element(elem)

        scene.resize(320, 240)
        assert scene.width == 320
        assert scene.height == 240
        # Elements should NOT be moved or scaled
        assert elem.position.x == 100
        assert elem.position.y == 100
        assert elem.width == 16
        assert elem.height == 16

    def test_out_of_bounds_detection(self):
        scene = Scene(width=160, height=192)
        # Inside
        e_inside = SceneElement("in", "t.png", Rect(0, 0, 16, 16), Position(10, 10))
        # Exceeds width
        e_oob_x = SceneElement("oob_x", "t.png", Rect(0, 0, 16, 16), Position(150, 10))
        # Negative y
        e_neg_y = SceneElement("neg_y", "t.png", Rect(0, 0, 16, 16), Position(10, -5))
        # Exceeds height
        e_oob_y = SceneElement("oob_y", "t.png", Rect(0, 0, 16, 16), Position(10, 185))

        scene.add_element(e_inside)
        scene.add_element(e_oob_x)
        scene.add_element(e_neg_y)
        scene.add_element(e_oob_y)

        oob = scene.get_out_of_bounds_elements()
        assert "in" not in oob
        assert "oob_x" in oob
        assert "neg_y" in oob
        assert "oob_y" in oob

    def test_json_round_trip_preserves_resolution(self):
        scene = Scene(name="custom_res", width=256, height=128)
        elem = SceneElement("e1", "tiles/a.png", Rect(0, 0, 32, 16), Position(10, 20))
        scene.add_element(elem)

        d = SceneSerializer.to_dict(scene)
        assert d["scene"]["width"] == 256
        assert d["scene"]["height"] == 128

        json_str = SceneSerializer.to_json(scene)
        loaded = SceneSerializer.from_json(json_str)
        assert loaded.width == 256
        assert loaded.height == 128
        assert len(loaded.elements) == 1
        assert loaded.elements[0].position.x == 10
        assert loaded.elements[0].position.y == 20

    def test_migration_of_older_project_without_dimensions(self):
        legacy_data = {
            "schema_version": 1,
            "scene": {
                "name": "legacy_screen"
                # Missing width and height
            },
            "elements": [
                {
                    "id": "e1",
                    "source": "tiles/stone.png",
                    "source_rect": {"x": 0, "y": 0, "width": 16, "height": 16},
                    "position": {"x": 20, "y": 30},
                }
            ],
        }

        loaded = SceneSerializer.from_dict(legacy_data)
        # Should migrate to legacy 160x96 as documented
        assert loaded.width == 160
        assert loaded.height == 96
        assert len(loaded.elements) == 1

    def test_resize_scene_undo_redo(self):
        scene = Scene(width=160, height=192)
        callback_called = []
        cmd = ResizeSceneCommand(
            scene,
            320,
            240,
            callback=lambda: callback_called.append(True),
        )

        cmd.redo()
        assert scene.width == 320
        assert scene.height == 240
        assert len(callback_called) == 1

        cmd.undo()
        assert scene.width == 160
        assert scene.height == 192
        assert len(callback_called) == 2
