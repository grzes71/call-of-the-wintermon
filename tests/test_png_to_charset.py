"""Unit and integration tests for png_to_charset."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from png_to_charset import (
    CharsetError,
    encode_row_to_byte,
    encode_tile_to_bytes,
    extract_and_build_charset,
    main,
    process_image_to_charset,
    validate_image,
)

DEFAULT_PALETTE = [
    0, 0, 0,        # 0: black
    80, 80, 80,     # 1: dark gray
    160, 160, 160,  # 2: light gray
    255, 255, 255,  # 3: white
] + [0] * (256 * 3 - 12)


def make_indexed_png(
    path: Path,
    width: int,
    height: int,
    pixels: list[int],
    palette: list[int] | None = None,
) -> Path:
    """Create a mode 'P' PNG with specified pixel values and palette."""
    img = Image.new("P", (width, height))
    img.putpalette(palette or DEFAULT_PALETTE)
    img.putdata(pixels)
    img.save(path, format="PNG")
    return path


def test_encode_row_to_byte_standard_pattern():
    """Requirement 5: Test encoding pixels to byte, specifically [0, 1, 2, 3] -> 0x1B."""
    # 0 -> 00, 1 -> 01, 2 -> 10, 3 -> 11 => 00011011 = 0x1B (27)
    assert encode_row_to_byte([0, 1, 2, 3]) == 0x1B

    # Other patterns
    assert encode_row_to_byte([0, 0, 0, 0]) == 0x00
    assert encode_row_to_byte([3, 3, 3, 3]) == 0xFF
    assert encode_row_to_byte([1, 0, 0, 0]) == 0x40
    assert encode_row_to_byte([0, 0, 0, 1]) == 0x01

    with pytest.raises(ValueError):
        encode_row_to_byte([0, 1, 2])
    with pytest.raises(ValueError):
        encode_row_to_byte([0, 1, 2, 3, 0])


def test_encode_tile_to_bytes():
    """Test 8-row tile encoding into 8 bytes."""
    tile_rows = [[0, 1, 2, 3]] * 8
    encoded = encode_tile_to_bytes(tile_rows)
    assert encoded == bytes([0x1B] * 8)
    assert len(encoded) == 8

    with pytest.raises(ValueError):
        encode_tile_to_bytes([[0, 1, 2, 3]] * 7)


def test_single_unique_tile_image(tmp_path: Path):
    """Requirement 1: Valid image with a single unique tile containing all 4 colors."""
    img_path = tmp_path / "single_tile.png"
    # Tile 4x8: ensure all 4 colors {0, 1, 2, 3} are used
    row0 = [0, 1, 2, 3]
    row_other = [0, 0, 0, 0]
    pixels = row0 + row_other * 7
    make_indexed_png(img_path, 4, 8, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    width, height, total_tiles, unique_chars = process_image_to_charset(
        img_path, font_path, json_path
    )

    assert (width, height) == (4, 8)
    assert total_tiles == 1
    assert unique_chars == 1

    # Verify font file size and content
    fnt_bytes = font_path.read_bytes()
    assert len(fnt_bytes) == 1024
    assert fnt_bytes[:8] == bytes([0x1B] + [0x00] * 7)
    # Remaining 127 characters filled with 0x00
    assert fnt_bytes[8:] == bytes([0x00] * (127 * 8))

    # Verify JSON content
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["image"]["tile_count"] == 1
    assert data["charset"]["unique_characters"] == 1
    assert data["charset"]["unused_characters"] == 127
    assert data["tiles"][0] == {
        "x": 0,
        "y": 0,
        "column": 0,
        "row": 0,
        "character_index": 0,
    }


def test_multiple_distinct_tiles(tmp_path: Path):
    """Requirement 2: Image containing multiple distinct tiles."""
    img_path = tmp_path / "multi_tiles.png"
    # 2 columns x 1 row = 8x8 pixels
    # Tile 0: [0, 1, 2, 3] row + 7x [0, 0, 0, 0]
    # Tile 1: [3, 2, 1, 0] row + 7x [0, 0, 0, 0]
    pixels = []
    for r in range(8):
        if r == 0:
            pixels.extend([0, 1, 2, 3] + [3, 2, 1, 0])
        else:
            pixels.extend([0, 0, 0, 0] + [0, 0, 0, 0])

    make_indexed_png(img_path, 8, 8, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    width, height, total_tiles, unique_chars = process_image_to_charset(
        img_path, font_path, json_path
    )

    assert (width, height) == (8, 8)
    assert total_tiles == 2
    assert unique_chars == 2

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["tiles"]) == 2
    assert data["tiles"][0]["character_index"] == 0
    assert data["tiles"][1]["character_index"] == 1


def test_duplicate_tiles_same_character_index(tmp_path: Path):
    """Requirement 3: Identical tiles in different positions get the same character index."""
    img_path = tmp_path / "dup_tiles.png"
    # 3 columns x 1 row = 12x8 pixels
    # Tile 0: A, Tile 1: B, Tile 2: A
    t_a = [0, 1, 2, 3]
    t_b = [3, 2, 1, 0]
    pixels = []
    for r in range(8):
        if r == 0:
            pixels.extend(t_a + t_b + t_a)
        else:
            pixels.extend([0, 0, 0, 0] * 3)

    make_indexed_png(img_path, 12, 8, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    width, height, total_tiles, unique_chars = process_image_to_charset(
        img_path, font_path, json_path
    )

    assert total_tiles == 3
    assert unique_chars == 2

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["tiles"][0]["character_index"] == 0
    assert data["tiles"][1]["character_index"] == 1
    assert data["tiles"][2]["character_index"] == 0


def test_tiles_differing_by_one_pixel(tmp_path: Path):
    """Requirement 4: Tiles differing by even a single pixel produce distinct character indices."""
    img_path = tmp_path / "diff_one_pixel.png"
    # 2 tiles: 8x8 pixels
    # Tile 0 has pixel (0, 0) = 1
    # Tile 1 has pixel (4, 0) = 2
    # Ensure all 4 colors exist across image
    pixels = []
    for r in range(8):
        if r == 0:
            pixels.extend([1, 0, 0, 0] + [2, 0, 0, 0])
        elif r == 1:
            pixels.extend([3, 0, 0, 0] + [0, 0, 0, 0])
        else:
            pixels.extend([0, 0, 0, 0] * 2)

    make_indexed_png(img_path, 8, 8, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    process_image_to_charset(img_path, font_path, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["charset"]["unique_characters"] == 2
    assert data["tiles"][0]["character_index"] != data["tiles"][1]["character_index"]


def test_image_dimensions_360_by_72(tmp_path: Path):
    """Requirement 6: Image with 360x72 pixels (90 cols x 9 rows = 810 tiles)."""
    img_path = tmp_path / "full_size.png"
    width, height = 360, 72
    # Fill image with color 0, put 1, 2, 3 in first 3 pixels
    pixels = [0] * (width * height)
    pixels[0] = 1
    pixels[1] = 2
    pixels[2] = 3

    make_indexed_png(img_path, width, height, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    w, h, total_tiles, unique_chars = process_image_to_charset(
        img_path, font_path, json_path
    )

    assert (w, h) == (360, 72)
    assert total_tiles == 810
    assert font_path.stat().st_size == 1024

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["image"]["columns"] == 90
    assert data["image"]["rows"] == 9
    assert data["image"]["tile_count"] == 810
    assert len(data["tiles"]) == 810


def test_invalid_width_not_divisible_by_4(tmp_path: Path):
    """Requirement 7: Width not divisible by 4 raises specific error."""
    img_path = tmp_path / "bad_width.png"
    pixels = [0] * (362 * 72)
    pixels[0] = 1
    pixels[1] = 2
    pixels[2] = 3
    make_indexed_png(img_path, 362, 72, pixels)

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, tmp_path / "c.fnt", tmp_path / "c.json")
    assert "ERROR: Image width must be divisible by 4; got 362." in str(exc_info.value)


def test_invalid_height_not_divisible_by_8(tmp_path: Path):
    """Requirement 8: Height not divisible by 8 raises specific error."""
    img_path = tmp_path / "bad_height.png"
    pixels = [0] * (360 * 74)
    pixels[0] = 1
    pixels[1] = 2
    pixels[2] = 3
    make_indexed_png(img_path, 360, 74, pixels)

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, tmp_path / "c.fnt", tmp_path / "c.json")
    assert "ERROR: Image height must be divisible by 8; got 74." in str(exc_info.value)


def test_rgb_image_rejected(tmp_path: Path):
    """Requirement 9: Non-indexed RGB image is rejected with specific error."""
    img_path = tmp_path / "rgb_image.png"
    img = Image.new("RGB", (360, 72), color=(0, 0, 0))
    img.save(img_path, format="PNG")

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, tmp_path / "c.fnt", tmp_path / "c.json")
    assert "ERROR: Input image must be an indexed PNG (palette mode P)." in str(exc_info.value)


def test_fewer_than_4_colors_rejected(tmp_path: Path):
    """Requirement 10: Image with fewer than 4 used colors is rejected."""
    img_path = tmp_path / "three_colors.png"
    pixels = [0] * 32
    pixels[0] = 1
    pixels[1] = 2
    # Only colors 0, 1, 2 used
    make_indexed_png(img_path, 4, 8, pixels)

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, tmp_path / "c.fnt", tmp_path / "c.json")
    assert "ERROR: Expected exactly 4 used colors; found 3." in str(exc_info.value)


def test_invalid_palette_indices_rejected(tmp_path: Path):
    """Requirement 11: Image with colors not matching {0, 1, 2, 3} is rejected."""
    # 4 colors, but indices are 0, 1, 2, 4
    img_path = tmp_path / "bad_indices.png"
    pixels = [0] * 32
    pixels[0] = 1
    pixels[1] = 2
    pixels[2] = 4
    make_indexed_png(img_path, 4, 8, pixels)

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, tmp_path / "c.fnt", tmp_path / "c.json")
    assert "ERROR: Used palette indices must be 0, 1, 2, and 3." in str(exc_info.value)


def test_exactly_128_unique_characters_success(tmp_path: Path):
    """Requirement 12: Image with exactly 128 unique characters succeeds."""
    img_path = tmp_path / "exactly_128.png"
    # 16 cols x 8 rows = 128 tiles. Each tile 4x8 -> image size 64x64.
    width, height = 64, 64
    cols, rows = 16, 8
    # We will make 128 distinct tiles.
    # Tile index 0 to 127: each tile gets a unique pattern.
    # We must ensure all 4 colors {0, 1, 2, 3} are used somewhere in the image.
    tiles_data: list[list[int]] = []
    for i in range(128):
        tile = [0] * 32
        # Encode i into the first few pixels of each tile
        tile[0] = i % 4
        tile[1] = (i // 4) % 4
        tile[2] = (i // 16) % 4
        tile[3] = (i // 64) % 4
        # Add salt in row 1 so that tiles remain distinct
        tile[4] = (i * 3) % 4
        tiles_data.append(tile)

    # Place tiles into pixel array
    pixels = [0] * (width * height)
    for row in range(rows):
        for col in range(cols):
            tile_idx = row * cols + col
            tile = tiles_data[tile_idx]
            for r in range(8):
                y = row * 8 + r
                for c in range(4):
                    x = col * 4 + c
                    pixels[y * width + x] = tile[r * 4 + c]

    make_indexed_png(img_path, width, height, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    process_image_to_charset(img_path, font_path, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["charset"]["unique_characters"] == 128
    assert data["charset"]["unused_characters"] == 0
    assert font_path.stat().st_size == 1024


def test_exceeding_128_characters_raises_error(tmp_path: Path):
    """Requirement 13: 129 unique characters triggers capacity exceeded error and total count."""
    img_path = tmp_path / "exceed_128.png"
    # 129 tiles: 129 columns x 1 row -> width 129*4 = 516, height 8
    width, height = 129 * 4, 8
    pixels = [0] * (width * height)

    for i in range(129):
        tile = [0] * 32
        tile[0] = i % 4
        tile[1] = (i // 4) % 4
        tile[2] = (i // 16) % 4
        tile[3] = (i // 64) % 4
        tile[4] = (i * 7) % 4
        for r in range(8):
            for c in range(4):
                pixels[r * width + (i * 4 + c)] = tile[r * 4 + c]

    make_indexed_png(img_path, width, height, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(img_path, font_path, json_path)

    err_msg = str(exc_info.value)
    assert "ERROR: Charset capacity exceeded." in err_msg
    assert "Found 129 unique characters; maximum allowed is 128." in err_msg
    assert "No output files were generated." in err_msg
    assert not font_path.exists()
    assert not json_path.exists()


def test_fnt_file_always_1024_bytes_and_padded_with_zeros(tmp_path: Path):
    """Requirements 14 and 15: .fnt is exactly 1024 bytes and unused entries are 0x00."""
    img_path = tmp_path / "padding_test.png"
    # 2 unique tiles: 8x8 pixels
    row0 = [0, 1, 2, 3] + [3, 2, 1, 0]
    row_zeros = [0] * 8
    pixels = row0 + row_zeros * 7
    make_indexed_png(img_path, 8, 8, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    process_image_to_charset(img_path, font_path, json_path)

    fnt_bytes = font_path.read_bytes()
    assert len(fnt_bytes) == 1024

    # 2 unique characters take 2 * 8 = 16 bytes
    assert fnt_bytes[16:] == bytes([0x00] * (126 * 8))


def test_json_structure_and_completeness(tmp_path: Path):
    """Requirement 16: Structure of JSON and complete tile mapping."""
    img_path = tmp_path / "grid.png"
    # 2x2 tiles = 8x16 pixels
    # Tile (0,0): 0,1,2,3
    # Tile (1,0): 3,2,1,0
    # Tile (0,1): 3,2,1,0 (duplicate of (1,0))
    # Tile (1,1): 0,1,2,3 (duplicate of (0,0))
    pixels = []
    # Row 0:
    pixels.extend([0, 1, 2, 3, 3, 2, 1, 0])
    # Rows 1-7:
    for _ in range(7):
        pixels.extend([0] * 8)
    # Row 8:
    pixels.extend([3, 2, 1, 0, 0, 1, 2, 3])
    # Rows 9-15:
    for _ in range(7):
        pixels.extend([0] * 8)

    make_indexed_png(img_path, 8, 16, pixels)

    font_path = tmp_path / "charset.fnt"
    json_path = tmp_path / "charset.json"

    process_image_to_charset(img_path, font_path, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))

    # Validate structure
    assert data["image"]["source"] == "grid.png"
    assert data["image"]["width"] == 8
    assert data["image"]["height"] == 16
    assert data["image"]["tile_width"] == 4
    assert data["image"]["tile_height"] == 8
    assert data["image"]["columns"] == 2
    assert data["image"]["rows"] == 2
    assert data["image"]["tile_count"] == 4

    assert data["charset"]["capacity"] == 128
    assert data["charset"]["unique_characters"] == 2
    assert data["charset"]["file_size"] == 1024
    assert data["charset"]["unused_characters"] == 126

    assert len(data["tiles"]) == 4

    # Coordinates and indices
    t0 = data["tiles"][0]
    t1 = data["tiles"][1]
    t2 = data["tiles"][2]
    t3 = data["tiles"][3]

    assert (t0["x"], t0["y"], t0["column"], t0["row"]) == (0, 0, 0, 0)
    assert (t1["x"], t1["y"], t1["column"], t1["row"]) == (4, 0, 1, 0)
    assert (t2["x"], t2["y"], t2["column"], t2["row"]) == (0, 8, 0, 1)
    assert (t3["x"], t3["y"], t3["column"], t3["row"]) == (4, 8, 1, 1)

    assert t0["character_index"] == 0
    assert t1["character_index"] == 1
    assert t2["character_index"] == 1
    assert t3["character_index"] == 0


def test_file_io_errors_and_path_validation(tmp_path: Path):
    """Requirement 17: Read and write errors, collision detection."""
    # 1. Non-existent input file
    non_existent = tmp_path / "does_not_exist.png"
    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(non_existent, tmp_path / "out.fnt", tmp_path / "out.json")
    assert "Input file does not exist" in str(exc_info.value)

    # 2. Corrupt PNG
    corrupt_png = tmp_path / "corrupt.png"
    corrupt_png.write_text("not a real image")
    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(corrupt_png, tmp_path / "out.fnt", tmp_path / "out.json")
    assert "Failed to read image" in str(exc_info.value)

    # 3. Valid image for output tests
    valid_png = tmp_path / "valid.png"
    pixels = [0, 1, 2, 3] + [0] * 28
    make_indexed_png(valid_png, 4, 8, pixels)

    # 4. Same output file for font and json
    same_out = tmp_path / "same.bin"
    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(valid_png, same_out, same_out)
    assert "cannot point to the same file" in str(exc_info.value)

    # 5. Overwriting input file
    with pytest.raises(CharsetError) as exc_info:
        process_image_to_charset(valid_png, valid_png, tmp_path / "out.json")
    assert "cannot overwrite the input image" in str(exc_info.value)


def test_no_partial_files_after_errors(tmp_path: Path):
    """Requirement 18: No partial output files remain when errors occur."""
    out_font = tmp_path / "partial.fnt"
    out_json = tmp_path / "partial.json"

    # Validation error test
    bad_img = tmp_path / "bad.png"
    make_indexed_png(bad_img, 4, 8, [0] * 32)  # only 1 color

    with pytest.raises(CharsetError):
        process_image_to_charset(bad_img, out_font, out_json)

    assert not out_font.exists()
    assert not out_json.exists()

    # Capacity error test
    # (Already tested in test_exceeding_128_characters_raises_error)

    # Write error test: simulate error during json save
    valid_png = tmp_path / "valid.png"
    make_indexed_png(valid_png, 4, 8, [0, 1, 2, 3] + [0] * 28)

    with patch("png_to_charset.json.dump", side_effect=OSError("Disk full")):
        with pytest.raises(CharsetError):
            process_image_to_charset(valid_png, out_font, out_json)

    assert not out_font.exists()
    assert not out_json.exists()


def test_cli_execution_success(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test CLI exit code 0 and stdout summary."""
    img_path = tmp_path / "cli_valid.png"
    make_indexed_png(img_path, 4, 8, [0, 1, 2, 3] + [0] * 28)
    font_path = tmp_path / "custom.fnt"
    json_path = tmp_path / "custom.json"

    code = main([
        str(img_path),
        "--font-output", str(font_path),
        "--json-output", str(json_path),
    ])

    assert code == 0
    captured = capsys.readouterr()
    assert "Input image: cli_valid.png" in captured.out
    assert "Image size: 4x8" in captured.out
    assert "Tiles processed: 1" in captured.out
    assert "Unique characters: 1 / 128" in captured.out
    assert "Charset file:" in captured.out
    assert "JSON mapping:" in captured.out
    assert font_path.exists()
    assert json_path.exists()


def test_cli_execution_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test CLI exit code 1 and stderr message on failure."""
    code = main([str(tmp_path / "non_existent.png")])
    assert code == 1
    captured = capsys.readouterr()
    assert "ERROR: Input file does not exist" in captured.err


def test_validate_image_direct():
    """Direct test of validate_image function."""
    img = Image.new("P", (4, 8))
    img.putpalette(DEFAULT_PALETTE)
    img.putdata([0, 1, 2, 3] + [0] * 28)
    # Valid image does not raise
    validate_image(img)

    # Invalid mode
    img_l = Image.new("L", (4, 8))
    with pytest.raises(CharsetError):
        validate_image(img_l)


def test_extract_and_build_charset_direct():
    """Direct test of extract_and_build_charset function."""
    img = Image.new("P", (4, 8))
    img.putpalette(DEFAULT_PALETTE)
    img.putdata([0, 1, 2, 3] + [0] * 28)

    font_data, json_data = extract_and_build_charset(img, "test.png")
    assert len(font_data) == 1024
    assert json_data["charset"]["unique_characters"] == 1
    assert json_data["image"]["source"] == "test.png"

