"""JSON serialization, deserialization, and atomic storage for scene models."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Optional

from .scene_model import (
    MAX_SCENE_HEIGHT,
    MAX_SCENE_WIDTH,
    MIN_SCENE_HEIGHT,
    MIN_SCENE_WIDTH,
    ModelValidationError,
    PlatformElement,
    PlayerSpawn,
    Position,
    Rect,
    Scene,
    SceneElement,
    SceneObjectElement,
    SingleSourceViolationError,
)


class SerializationError(Exception):
    """Base exception for serialization errors."""
    pass


class UnsupportedSchemaVersionError(SerializationError):
    """Raised when the JSON file has an unsupported schema version."""
    pass


class CorruptedFileError(SerializationError):
    """Raised when the JSON file syntax or structure is malformed."""
    pass


class MissingSourceFileError(SerializationError):
    """Raised when an element's source graphic cannot be found."""
    pass


def find_project_root(start_path: Path | str | None = None) -> Path:
    """Locate the project root containing tiles/ starting from start_path upwards or cwd."""
    start = Path(start_path).resolve() if start_path else Path.cwd().resolve()
    curr = start if start.is_dir() else start.parent
    for _ in range(5):
        if (curr / "tiles").is_dir():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    if (Path.cwd() / "tiles").is_dir():
        return Path.cwd().resolve()
    return start if start.is_dir() else start.parent


class SceneSerializer:
    """Handles serialization and deserialization of Scene models to/from JSON."""

    SUPPORTED_SCHEMA_VERSIONS = {1}

    @staticmethod
    def to_dict(
        scene: Scene,
        base_dir: Path | str | None = None,
        catalogues: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Convert a Scene object to a serializable dictionary with relative paths."""
        scene.validate()
        base_path = Path(base_dir).resolve() if base_dir else None

        elements_data = []
        for elem in scene.elements:
            elem_data = elem.to_dict()
            if base_path:
                source_path = Path(elem.source)
                if source_path.is_absolute():
                    try:
                        elem_data["source"] = source_path.relative_to(base_path).as_posix()
                    except ValueError:
                        elem_data["source"] = source_path.as_posix()
            elements_data.append(elem_data)

        scene_info: dict[str, Any] = {
            "name": scene.name,
            "width": scene.width,
            "height": scene.height,
        }
        if scene.tile_source and len(scene.get_sources()) <= 1:
            tile_src = Path(scene.tile_source)
            if base_path and tile_src.is_absolute():
                try:
                    scene_info["tile_source"] = tile_src.relative_to(base_path).as_posix()
                except ValueError:
                    scene_info["tile_source"] = tile_src.as_posix()
            else:
                scene_info["tile_source"] = scene.tile_source.replace("\\", "/")

        objects_data = []
        for obj in scene.objects:
            obj_data = obj.to_dict(catalogues=catalogues)
            if base_path and obj.source:
                source_path = Path(obj.source)
                if source_path.is_absolute():
                    try:
                        obj_data["source"] = source_path.relative_to(base_path).as_posix()
                    except ValueError:
                        obj_data["source"] = source_path.as_posix()
            objects_data.append(obj_data)

        res: dict[str, Any] = {
            "schema_version": scene.schema_version,
            "scene": scene_info,
            "elements": elements_data,
            "platforms": [p.to_dict() for p in scene.platforms],
            "objects": objects_data,
        }
        if scene.player_spawn is not None:
            res["player_spawn"] = scene.player_spawn.to_dict()
        if scene.row_color_profiles and any(x is not None for x in scene.row_color_profiles):
            res["row_color_profiles"] = list(scene.row_color_profiles)
        return res

    @classmethod
    def to_json(
        cls,
        scene: Scene,
        indent: int = 2,
        base_dir: Path | str | None = None,
        catalogues: Optional[Any] = None,
    ) -> str:
        """Serialize scene to a formatted JSON string."""
        data = cls.to_dict(scene, base_dir=base_dir, catalogues=catalogues)
        return json.dumps(data, indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        base_dir: Path | str | None = None,
        validate_source_exists: bool = False,
        catalogues: Optional[Any] = None,
    ) -> Scene:
        """Construct and validate a Scene object from a dictionary."""
        if not isinstance(data, dict):
            raise CorruptedFileError("Invalid JSON structure: top-level item must be an object.")

        if "schema_version" not in data:
            raise CorruptedFileError("Missing 'schema_version' field.")

        version = data["schema_version"]
        if not isinstance(version, int) or version not in cls.SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaVersionError(
                f"Unsupported schema version: {version}. Supported: {sorted(cls.SUPPORTED_SCHEMA_VERSIONS)}"
            )

        if "scene" not in data or not isinstance(data["scene"], dict):
            raise CorruptedFileError("Missing or invalid 'scene' section.")

        scene_meta = data["scene"]
        name = str(scene_meta.get("name", "untitled"))
        # Migrate older projects without explicit width or height to 160x96
        width = scene_meta.get("width", 160)
        height = scene_meta.get("height", 96)
        tile_source = scene_meta.get("tile_source")

        if not isinstance(width, int) or not isinstance(height, int):
            raise ModelValidationError("Scene width and height must be integers.")
        if width < MIN_SCENE_WIDTH or height < MIN_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions must be strictly positive (min {MIN_SCENE_WIDTH}x{MIN_SCENE_HEIGHT}), got {width}x{height}."
            )
        if width > MAX_SCENE_WIDTH or height > MAX_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions exceed maximum allowable limit ({MAX_SCENE_WIDTH}x{MAX_SCENE_HEIGHT}), got {width}x{height}."
            )

        raw_elements = data.get("elements", [])
        if not isinstance(raw_elements, list):
            raise CorruptedFileError("'elements' must be a list.")

        elements: list[SceneElement] = []
        base_path = Path(base_dir).resolve() if base_dir else None

        for idx, item in enumerate(raw_elements):
            try:
                elem = SceneElement.from_dict(item)
            except Exception as exc:
                raise CorruptedFileError(f"Error parsing element at index {idx}: {exc}") from exc

            # Validate source file existence if requested
            if validate_source_exists:
                source_p = Path(elem.source)
                if not source_p.is_absolute() and base_path:
                    resolved_p = base_path / source_p
                else:
                    resolved_p = source_p

                if not resolved_p.is_file():
                    raise MissingSourceFileError(
                        f"Source graphic for element '{elem.id}' does not exist: {elem.source}"
                    )

            elements.append(elem)

        raw_platforms = data.get("platforms", [])
        if not isinstance(raw_platforms, list):
            raise CorruptedFileError("'platforms' must be a list if present.")

        platforms: list[PlatformElement] = []
        for idx, p_item in enumerate(raw_platforms):
            try:
                p = PlatformElement.from_dict(p_item)
            except Exception as exc:
                raise CorruptedFileError(f"Error parsing platform at index {idx}: {exc}") from exc
            platforms.append(p)

        raw_objects = data.get("objects", [])
        if not isinstance(raw_objects, list):
            raise CorruptedFileError("'objects' must be a list if present.")

        objects: list[SceneObjectElement] = []
        for idx, o_item in enumerate(raw_objects):
            try:
                obj = SceneObjectElement.from_dict(o_item)
            except Exception as exc:
                raise CorruptedFileError(f"Error parsing object at index {idx}: {exc}") from exc
            objects.append(obj)

        if catalogues is None:
            eff_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
            try:
                from .catalogue_model import ProjectCatalogues
                catalogues = ProjectCatalogues.load_from_dir(eff_dir)
            except Exception:
                catalogues = None

        raw_row_profiles = data.get("row_color_profiles")
        if raw_row_profiles is None and isinstance(data.get("scene"), dict):
            raw_row_profiles = data["scene"].get("row_color_profiles")

        row_color_profiles: list[Optional[int]] = []
        if isinstance(raw_row_profiles, list):
            for item in raw_row_profiles:
                if item is not None and str(item).strip() != "":
                    try:
                        row_color_profiles.append(int(item))
                    except (ValueError, TypeError):
                        row_color_profiles.append(None)
                else:
                    row_color_profiles.append(None)

        raw_player_spawn = data.get("player_spawn")
        if raw_player_spawn is None and isinstance(data.get("scene"), dict):
            raw_player_spawn = data["scene"].get("player_spawn")

        player_spawn: Optional[PlayerSpawn] = None
        if raw_player_spawn is not None and isinstance(raw_player_spawn, dict):
            try:
                player_spawn = PlayerSpawn.from_dict(raw_player_spawn)
            except Exception as exc:
                raise CorruptedFileError(f"Error parsing player_spawn: {exc}") from exc

        scene = Scene(
            name=name,
            schema_version=version,
            width=width,
            height=height,
            tile_source=tile_source,
            elements=elements,
            platforms=platforms,
            objects=objects,
            row_color_profiles=row_color_profiles if row_color_profiles else [None] * 6,
            catalogues=catalogues,
            player_spawn=player_spawn,
        )
        try:
            scene.validate()
        except ModelValidationError as exc:
            raise CorruptedFileError(f"Validation error in scene: {exc}") from exc
        return scene

    @classmethod
    def from_json(
        cls,
        json_str: str,
        base_dir: Path | str | None = None,
        validate_source_exists: bool = False,
        catalogues: Optional[Any] = None,
    ) -> Scene:
        """Parse JSON string into a Scene object."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise CorruptedFileError(f"Malformed JSON: {exc}") from exc

        return cls.from_dict(
            data,
            base_dir=base_dir,
            validate_source_exists=validate_source_exists,
            catalogues=catalogues,
        )

    @classmethod
    def save_to_file(
        cls,
        scene: Scene,
        file_path: Path | str,
        base_dir: Path | str | None = None,
        indent: int = 2,
        catalogues: Optional[Any] = None,
    ) -> None:
        """Save a scene to a JSON file atomically using a temporary file and rename."""
        target_path = Path(file_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if base_dir is None:
            base_dir = find_project_root(target_path)

        json_text = cls.to_json(scene, indent=indent, base_dir=base_dir, catalogues=catalogues)

        # Atomic write in the same directory to guarantee atomic replace across filesystems
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            dir=target_path.parent,
            prefix=f"{target_path.stem}_",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        )
        temp_name = temp_file.name
        try:
            temp_file.write(json_text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            os.replace(temp_name, target_path)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    @classmethod
    def load_from_file(
        cls,
        file_path: Path | str,
        base_dir: Path | str | None = None,
        validate_source_exists: bool = False,
        catalogues: Optional[Any] = None,
    ) -> Scene:
        """Load a scene from a JSON file."""
        target_path = Path(file_path).resolve()
        if not target_path.is_file():
            raise FileNotFoundError(f"Scene file not found: {target_path}")

        if base_dir is None:
            base_dir = find_project_root(target_path)

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            raise CorruptedFileError(f"Cannot read file '{target_path}': {exc}") from exc

        return cls.from_json(
            content,
            base_dir=base_dir,
            validate_source_exists=validate_source_exists,
            catalogues=catalogues,
        )
