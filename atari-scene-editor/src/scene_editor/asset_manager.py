"""Asset manager for loading, caching, validating, and cropping tileset graphics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap

from .json_serializer import find_project_root
from .scene_model import Rect


class AssetManager:
    """Manages graphics loading, caching, cropping, and path resolution."""

    SUPPORTED_EXTENSIONS = {".png", ".bmp", ".gif", ".jpg", ".jpeg"}

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir).resolve() if base_dir else find_project_root()
        self._image_cache: dict[str, QImage] = {}
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._thumbnail_cache: dict[tuple[str, int, int], QPixmap] = {}

    def set_base_dir(self, base_dir: Path | str) -> None:
        """Update base project directory."""
        self.base_dir = Path(base_dir).resolve()

    def scan_tiles(self, tiles_dir: Path | str | None = None) -> list[Path]:
        """Scan a directory for supported graphics files. Returns sorted list of paths."""
        if tiles_dir is None:
            scan_path = self.base_dir / "tiles"
        else:
            scan_path = Path(tiles_dir)
            if not scan_path.is_absolute():
                scan_path = self.base_dir / scan_path

        if not scan_path.is_dir():
            return []

        found: list[Path] = []
        for entry in sorted(scan_path.iterdir()):
            if entry.is_file() and entry.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                found.append(entry)
        return found

    def resolve_path(self, path: Path | str) -> Path:
        """Resolve a path against base_dir if it is relative."""
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (self.base_dir / p).resolve()

    def to_relative_path(self, path: Path | str) -> str:
        """Convert a path to relative POSIX string relative to base_dir if possible."""
        p = Path(path)
        if not p.is_absolute():
            p = (self.base_dir / p).resolve()
        else:
            p = p.resolve()
        try:
            return p.relative_to(self.base_dir).as_posix()
        except ValueError:
            return p.as_posix()

    def get_image(self, source_path: Path | str) -> Optional[QImage]:
        """Load and cache QImage from source path. Returns None if loading fails."""
        resolved = self.resolve_path(source_path)
        key = str(resolved)

        if key in self._image_cache:
            return self._image_cache[key]

        if not resolved.is_file():
            return None

        img = QImage()
        if not img.load(str(resolved)):
            return None

        # Convert to RGB32/ARGB32 for reliable manipulation and fast drawing
        if img.format() not in (QImage.Format.Format_ARGB32, QImage.Format.Format_RGB32):
            img = img.convertToFormat(QImage.Format.Format_ARGB32)

        self._image_cache[key] = img
        return img

    def get_pixmap(self, source_path: Path | str) -> Optional[QPixmap]:
        """Load and cache QPixmap from source path."""
        resolved = self.resolve_path(source_path)
        key = str(resolved)

        if key in self._pixmap_cache:
            return self._pixmap_cache[key]

        img = self.get_image(source_path)
        if img is None:
            return None

        pm = QPixmap.fromImage(img)
        self._pixmap_cache[key] = pm
        return pm

    def get_thumbnail(self, source_path: Path | str, size: QSize = QSize(64, 64)) -> Optional[QPixmap]:
        """Generate or retrieve a cached thumbnail for a graphic."""
        resolved = self.resolve_path(source_path)
        key = (str(resolved), size.width(), size.height())

        if key in self._thumbnail_cache:
            return self._thumbnail_cache[key]

        pm = self.get_pixmap(source_path)
        if pm is None:
            return None

        thumb = pm.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._thumbnail_cache[key] = thumb
        return thumb

    def validate_crop(self, source_path: Path | str, rect: Rect) -> tuple[bool, str]:
        """Check if crop rectangle is valid within source image dimensions."""
        img = self.get_image(source_path)
        if img is None:
            return False, f"Source image '{source_path}' could not be loaded."

        if rect.x < 0 or rect.y < 0:
            return False, f"Crop coordinates must be non-negative, got ({rect.x}, {rect.y})."

        if rect.width <= 0 or rect.height <= 0:
            return False, f"Crop dimensions must be positive, got {rect.width}x{rect.height}."

        img_w = img.width()
        img_h = img.height()

        if rect.x + rect.width > img_w or rect.y + rect.height > img_h:
            return (
                False,
                f"Crop rect [{rect.x}, {rect.y}, {rect.width}, {rect.height}] exceeds "
                f"image bounds ({img_w}x{img_h}).",
            )

        return True, "Valid crop."

    def get_cropped_image(
        self,
        source_path: Path | str,
        rect: Rect,
        flip_x: bool = False,
    ) -> Optional[QImage]:
        """Extract a sub-region from source image and optionally flip horizontally."""
        img = self.get_image(source_path)
        if img is None:
            return None

        # Clamp safely for extraction if needed, but copy rect exactly
        sub_img = img.copy(rect.x, rect.y, rect.width, rect.height)
        if flip_x:
            from PySide6.QtGui import QTransform
            sub_img = sub_img.transformed(QTransform().scale(-1, 1))
        return sub_img

    def get_cropped_pixmap(
        self,
        source_path: Path | str,
        rect: Rect,
        flip_x: bool = False,
    ) -> Optional[QPixmap]:
        """Extract cropped region as QPixmap."""
        sub_img = self.get_cropped_image(source_path, rect, flip_x=flip_x)
        if sub_img is None:
            return None
        return QPixmap.fromImage(sub_img)

    def clear_cache(self) -> None:
        """Clear all in-memory image and pixmap caches."""
        self._image_cache.clear()
        self._pixmap_cache.clear()
        self._thumbnail_cache.clear()
