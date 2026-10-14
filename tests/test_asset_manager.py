"""Unit tests for AssetManager graphics loading, caching, cropping, and validation."""

import os
from pathlib import Path
import sys

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
import pytest
from scene_editor.asset_manager import AssetManager
from scene_editor.scene_model import Rect

# Initialize headless QApplication once for tests
_qapp = QApplication.instance() or QApplication([])


class TestAssetManager:
    @pytest.fixture
    def test_env(self, tmp_path: Path):
        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()

        # Create a sample test image (32x24) with distinctive left vs right colors
        img = Image.new("RGBA", (32, 24), color=(255, 0, 0, 255))
        # Left half red, right half blue
        for x in range(16, 32):
            for y in range(24):
                img.putpixel((x, y), (0, 0, 255, 255))
        img_path = tiles_dir / "test_tile.png"
        img.save(img_path)

        # Also create a bmp image
        bmp_path = tiles_dir / "test_bmp.bmp"
        Image.new("RGB", (16, 16), color=(0, 255, 0)).save(bmp_path)

        # Non-image file to test extension filtering
        (tiles_dir / "notes.txt").write_text("not an image")

        mgr = AssetManager(base_dir=tmp_path)
        return mgr, tmp_path, img_path

    def test_scan_tiles(self, test_env):
        mgr, tmp_path, _ = test_env
        tiles = mgr.scan_tiles()
        names = [p.name for p in tiles]
        assert "test_tile.png" in names
        assert "test_bmp.bmp" in names
        assert "notes.txt" not in names

    def test_scan_nonexistent_dir(self, tmp_path: Path):
        mgr = AssetManager(base_dir=tmp_path)
        assert mgr.scan_tiles(tmp_path / "nonexistent") == []

    def test_path_resolution_and_relative_path(self, test_env):
        mgr, tmp_path, img_path = test_env
        rel = mgr.to_relative_path(img_path)
        assert rel.replace("\\", "/") == "tiles/test_tile.png"

        resolved = mgr.resolve_path(rel)
        assert resolved == img_path

    def test_image_loading_and_caching(self, test_env):
        mgr, _, img_path = test_env
        img1 = mgr.get_image(img_path)
        assert img1 is not None
        assert img1.width() == 32
        assert img1.height() == 24

        # Verify caching returns same instance
        img2 = mgr.get_image(img_path)
        assert img1 is img2

    def test_validate_crop_boundaries(self, test_env):
        mgr, _, img_path = test_env

        # Valid crop
        valid, _ = mgr.validate_crop(img_path, Rect(x=0, y=0, width=16, height=16))
        assert valid is True

        # Exceeds width
        valid, msg = mgr.validate_crop(img_path, Rect(x=20, y=0, width=20, height=16))
        assert valid is False
        assert "exceeds" in msg.lower()

        # Negative coords
        valid, _ = mgr.validate_crop(img_path, Rect(x=-1, y=0, width=16, height=16))
        assert valid is False

        # Zero or negative dimensions
        valid, _ = mgr.validate_crop(img_path, Rect(x=0, y=0, width=0, height=16))
        assert valid is False

    def test_crop_extraction_and_flip(self, test_env):
        mgr, _, img_path = test_env

        # Extract 16x16 crop: left half is red, right half is blue
        crop_rect = Rect(x=8, y=0, width=16, height=16)

        sub_original = mgr.get_cropped_image(img_path, crop_rect, flip_x=False)
        assert sub_original is not None
        assert sub_original.width() == 16
        assert sub_original.height() == 16

        # In original crop: (x=0 to 7) is red, (x=8 to 15) is blue
        pixel_left = sub_original.pixelColor(0, 0)
        pixel_right = sub_original.pixelColor(15, 0)
        assert pixel_left.red() == 255 and pixel_left.blue() == 0
        assert pixel_right.red() == 0 and pixel_right.blue() == 255

        # With flip_x=True, colors must be mirrored
        sub_flipped = mgr.get_cropped_image(img_path, crop_rect, flip_x=True)
        assert sub_flipped is not None
        flipped_left = sub_flipped.pixelColor(0, 0)
        flipped_right = sub_flipped.pixelColor(15, 0)
        assert flipped_left.red() == 0 and flipped_left.blue() == 255
        assert flipped_right.red() == 255 and flipped_right.blue() == 0

        # Verify source image was NOT mutated
        source_again = mgr.get_image(img_path)
        assert source_again.pixelColor(0, 0).red() == 255

    def test_thumbnail_generation(self, test_env):
        mgr, _, img_path = test_env
        thumb = mgr.get_thumbnail(img_path, QSize(16, 16))
        assert thumb is not None
        assert not thumb.isNull()
        assert thumb.width() <= 16
        assert thumb.height() <= 16
