"""Unit tests for ANTIC Mode F image converter (scripts/convert_image.py)."""

from pathlib import Path
from PIL import Image
import pytest

from scripts.convert_image import convert_image_to_antic_f


def test_convert_image_valid_output(tmp_path: Path):
    # Create test 320x192 monochrome image
    img = Image.new("1", (320, 192), color=0)
    # Draw some pixels in both segments
    img.putpixel((0, 0), 1)  # Segment 1
    img.putpixel((10, 150), 1)  # Segment 2

    test_png = tmp_path / "test_input.png"
    test_bin = tmp_path / "test_output.bin"
    img.save(test_png)

    ret = convert_image_to_antic_f(test_png, test_bin)
    assert ret == 0
    assert test_bin.exists()

    data = test_bin.read_bytes()
    assert len(data) == 7696

    # Verify first byte has MSB set (pixel 0,0 is 1)
    assert data[0] == 0x80

    # Verify padding between segment 1 and 2 is 16 zero bytes
    # Segment 1 is 102 lines * 40 bytes = 4080 bytes
    padding = data[4080:4096]
    assert len(padding) == 16
    assert padding == bytes(16)


def test_convert_image_invalid_dimensions(tmp_path: Path):
    img = Image.new("1", (300, 192), color=0)
    test_png = tmp_path / "invalid_size.png"
    test_bin = tmp_path / "output.bin"
    img.save(test_png)

    ret = convert_image_to_antic_f(test_png, test_bin)
    assert ret != 0
    assert not test_bin.exists()


def test_convert_image_missing_file(tmp_path: Path):
    missing_png = tmp_path / "does_not_exist.png"
    test_bin = tmp_path / "output.bin"
    ret = convert_image_to_antic_f(missing_png, test_bin)
    assert ret != 0
