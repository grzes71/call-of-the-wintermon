"""Unit tests for ANTIC Mode D and Mode F image converter (scripts/convert_image.py)."""

from pathlib import Path
from PIL import Image
import pytest

from scripts.convert_image import convert_image_to_antic_d, convert_image_to_antic_f


def test_convert_image_antic_d_valid_output(tmp_path: Path):
    # Create test 160x95 palette image
    img = Image.new("P", (160, 95), color=0)
    # Set palette: 0, 1, 2, 3
    img.putpalette([0, 0, 0, 13, 91, 37, 58, 168, 56, 207, 243, 75] + [0] * (768 - 12))

    # Set first 4 pixels of line 0: 1, 2, 3, 0 -> (1<<6) | (2<<4) | (3<<2) | 0 = 0x6C
    img.putpixel((0, 0), 1)
    img.putpixel((1, 0), 2)
    img.putpixel((2, 0), 3)
    img.putpixel((3, 0), 0)

    # Set last line pixel
    img.putpixel((159, 94), 3)

    test_png = tmp_path / "test_input_d.png"
    test_bin = tmp_path / "test_output_d.bin"
    img.save(test_png)

    ret = convert_image_to_antic_d(test_png, test_bin)
    assert ret == 0
    assert test_bin.exists()

    data = test_bin.read_bytes()
    assert len(data) == 3840  # 160 / 4 * 96 = 40 * 96 = 3840 bytes
    assert data[0] == 0x6C


def test_convert_image_antic_d_invalid_dimensions(tmp_path: Path):
    img = Image.new("P", (160, 100), color=0)
    test_png = tmp_path / "invalid_size_d.png"
    test_bin = tmp_path / "output_d.bin"
    img.save(test_png)

    ret = convert_image_to_antic_d(test_png, test_bin)
    assert ret != 0
    assert not test_bin.exists()


def test_convert_image_antic_d_missing_file(tmp_path: Path):
    missing_png = tmp_path / "does_not_exist_d.png"
    test_bin = tmp_path / "output_d.bin"
    ret = convert_image_to_antic_d(missing_png, test_bin)
    assert ret != 0


def test_convert_image_valid_output(tmp_path: Path):
    # Create test 320x192 monochrome image
    img = Image.new("1", (320, 192), color=0)
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
    assert data[0] == 0x80

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
