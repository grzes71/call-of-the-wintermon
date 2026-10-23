"""Unit and integration tests for JSON serialization, deserialization, and atomic storage."""

import json
from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest
from scene_editor.json_serializer import (
    CorruptedFileError,
    MissingSourceFileError,
    SceneSerializer,
    UnsupportedSchemaVersionError,
)
from scene_editor.scene_model import (
    ModelValidationError,
    Position,
    Rect,
    Scene,
    SceneElement,
    SingleSourceViolationError,
)


class TestJsonSerializer:
    @pytest.fixture
    def sample_scene(self) -> Scene:
        scene = Scene(name="level_sample", width=160, height=96)
        elem1 = SceneElement(
            id="element-001",
            source="tiles/castles.png",
            source_rect=Rect(x=0, y=0, width=32, height=16),
            position=Position(x=10, y=20),
            flip_x=False,
            z_index=0,
        )
        elem2 = SceneElement(
            id="element-002",
            source="tiles/castles.png",
            source_rect=Rect(x=32, y=0, width=16, height=16),
            position=Position(x=50, y=20),
            flip_x=True,
            z_index=1,
        )
        scene.add_element(elem1)
        scene.add_element(elem2)
        return scene

    def test_serialize_to_dict_and_json(self, sample_scene: Scene):
        d = SceneSerializer.to_dict(sample_scene)
        assert d["schema_version"] == 1
        assert d["scene"]["name"] == "level_sample"
        assert d["scene"]["width"] == 160
        assert d["scene"]["height"] == 96
        assert len(d["elements"]) == 2

        # Check element fields
        elem0 = d["elements"][0]
        assert elem0["id"] == "element-001"
        assert elem0["source"] == "tiles/castles.png"
        assert elem0["source_rect"] == {"x": 0, "y": 0, "width": 32, "height": 16}
        assert elem0["position"] == {"x": 10, "y": 20}
        assert elem0["flip_x"] is False
        assert elem0["z_index"] == 0

        elem1 = d["elements"][1]
        assert elem1["flip_x"] is True
        assert elem1["z_index"] == 1

        json_str = SceneSerializer.to_json(sample_scene)
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == 1

    def test_deserialize_from_dict_and_json(self, sample_scene: Scene):
        json_str = SceneSerializer.to_json(sample_scene)
        loaded_scene = SceneSerializer.from_json(json_str)

        assert loaded_scene.name == sample_scene.name
        assert loaded_scene.width == sample_scene.width
        assert loaded_scene.height == sample_scene.height
        assert len(loaded_scene.elements) == 2

        assert loaded_scene.elements[0].id == "element-001"
        assert loaded_scene.elements[0].position.x == 10
        assert loaded_scene.elements[0].source_rect.width == 32
        assert loaded_scene.elements[0].flip_x is False

        assert loaded_scene.elements[1].id == "element-002"
        assert loaded_scene.elements[1].flip_x is True
        assert loaded_scene.elements[1].z_index == 1

    def test_round_trip_atomic_file_save_and_load(self, sample_scene: Scene, tmp_path: Path):
        file_path = tmp_path / "saved_scene.json"
        SceneSerializer.save_to_file(sample_scene, file_path, base_dir=tmp_path)
        assert file_path.is_file()

        loaded_scene = SceneSerializer.load_from_file(file_path, base_dir=tmp_path)
        assert loaded_scene.name == sample_scene.name
        assert len(loaded_scene.elements) == len(sample_scene.elements)
        for original, restored in zip(sample_scene.elements, loaded_scene.elements):
            assert original.id == restored.id
            assert original.source == restored.source
            assert original.source_rect == restored.source_rect
            assert original.position == restored.position
            assert original.flip_x == restored.flip_x
            assert original.z_index == restored.z_index

    def test_off_grid_crop_is_realigned_on_load_and_save(self):
        """Crop x and width must snap to the ANTIC Mode E byte grid (4 pixels per byte)."""
        from scene_editor.scene_model import SOURCE_X_ALIGN

        assert SOURCE_X_ALIGN == 4
        scene_dict = {
            "schema_version": 1,
            "scene": {"name": "Crop Grid", "width": 160, "height": 96},
            "elements": [
                {
                    "id": "element-001",
                    "source": "tiles/castles.png",
                    "source_rect": {"x": 79, "y": 0, "width": 81, "height": 42},
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "element-002",
                    "source": "tiles/castles.png",
                    "source_rect": {"x": 4, "y": 0, "width": 16, "height": 16},
                    "position": {"x": 0, "y": 0},
                },
            ],
        }

        scene = SceneSerializer.from_dict(scene_dict)
        assert scene.elements[0].source_rect.x == 76        # 79 -> 76 (byte aligned)
        assert scene.elements[0].source_rect.width == 84    # 81 -> 84 (whole bytes)
        assert scene.elements[1].source_rect.x == 4         # already on the grid
        assert scene.elements[1].source_rect.width == 16    # already on the grid

        saved = SceneSerializer.to_dict(scene)
        assert saved["elements"][0]["source_rect"]["x"] == 76
        assert saved["elements"][0]["source_rect"]["width"] == 84
        assert saved["elements"][0]["source_rect"]["height"] == 42  # other fields untouched
        assert saved["elements"][1]["source_rect"]["x"] == 4
        assert saved["elements"][1]["source_rect"]["width"] == 16

    def test_unsupported_schema_version(self):
        data = {
            "schema_version": 999,
            "scene": {"name": "test", "width": 160, "height": 96},
            "elements": [],
        }
        with pytest.raises(UnsupportedSchemaVersionError):
            SceneSerializer.from_dict(data)

    def test_corrupted_json_syntax(self):
        bad_json = '{"schema_version": 1, "scene": {'
        with pytest.raises(CorruptedFileError):
            SceneSerializer.from_json(bad_json)

    def test_missing_required_fields(self):
        bad_dict = {"schema_version": 1}  # Missing 'scene'
        with pytest.raises(CorruptedFileError):
            SceneSerializer.from_dict(bad_dict)

    def test_invalid_scene_dimensions_rejected(self):
        bad_dict = {
            "schema_version": 1,
            "scene": {"name": "test", "width": -5, "height": 200},
            "elements": [],
        }
        with pytest.raises(ModelValidationError):
            SceneSerializer.from_dict(bad_dict)

    def test_missing_source_file_validation(self, tmp_path: Path):
        data = {
            "schema_version": 1,
            "scene": {"name": "test", "width": 160, "height": 96},
            "elements": [
                {
                    "id": "e1",
                    "source": "tiles/nonexistent_file.png",
                    "source_rect": {"x": 0, "y": 0, "width": 16, "height": 16},
                    "position": {"x": 0, "y": 0},
                    "flip_x": False,
                }
            ],
        }
        # Without validation, loads fine:
        scene = SceneSerializer.from_dict(data, base_dir=tmp_path, validate_source_exists=False)
        assert len(scene.elements) == 1

        # With validation, raises MissingSourceFileError:
        with pytest.raises(MissingSourceFileError):
            SceneSerializer.from_dict(data, base_dir=tmp_path, validate_source_exists=True)
