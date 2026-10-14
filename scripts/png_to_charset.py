#!/usr/bin/env python3
"""Convert indexed 4-color PNG images into Atari 8-bit charset binaries and JSON tile maps."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image


class CharsetError(Exception):
    """Raised when validation, conversion, or file operations fail."""


def encode_row_to_byte(pixels: Sequence[int]) -> int:
    """Encode a sequence of 4 2-bit color index pixels into a single byte.

    Pixel 0 occupies bits 7-6, pixel 1 bits 5-4, pixel 2 bits 3-2, pixel 3 bits 1-0.
    """
    if len(pixels) != 4:
        raise ValueError(f"Expected exactly 4 pixels per row; got {len(pixels)}.")
    p0, p1, p2, p3 = pixels
    return (
        ((p0 & 0x03) << 6)
        | ((p1 & 0x03) << 4)
        | ((p2 & 0x03) << 2)
        | (p3 & 0x03)
    )


def encode_tile_to_bytes(tile_rows: Sequence[Sequence[int]]) -> bytes:
    """Encode an 8-row by 4-pixel tile into 8 bytes."""
    if len(tile_rows) != 8:
        raise ValueError(f"Expected exactly 8 rows in tile; got {len(tile_rows)}.")
    return bytes(encode_row_to_byte(row) for row in tile_rows)


def validate_image(img: Image.Image) -> None:
    """Validate that the image satisfies all Atari 4-color charset requirements."""
    if img.mode != "P":
        raise CharsetError("ERROR: Input image must be an indexed PNG (palette mode P).")

    width, height = img.size
    if width % 4 != 0:
        raise CharsetError(f"ERROR: Image width must be divisible by 4; got {width}.")
    if height % 8 != 0:
        raise CharsetError(f"ERROR: Image height must be divisible by 8; got {height}.")

    if hasattr(img, "get_flattened_data"):
        used_colors = set(img.get_flattened_data())
    else:
        used_colors = set(img.getdata())
    if len(used_colors) != 4:
        raise CharsetError(f"ERROR: Expected exactly 4 used colors; found {len(used_colors)}.")
    if used_colors != {0, 1, 2, 3}:
        raise CharsetError("ERROR: Used palette indices must be 0, 1, 2, and 3.")


def extract_and_build_charset(
    img: Image.Image, source_name: str
) -> tuple[bytes, dict]:
    """Extract tiles from the image, deduplicate them, and construct font data and JSON mapping."""
    validate_image(img)

    width, height = img.size
    cols = width // 4
    rows = height // 8
    total_tiles = cols * rows

    if hasattr(img, "get_flattened_data"):
        pixel_data = list(img.get_flattened_data())
    else:
        pixel_data = list(img.getdata())

    unique_patterns: dict[bytes, int] = {}
    tiles_mapping: list[dict[str, int]] = []
    capacity_exceeded = False

    for row_idx in range(rows):
        y_start = row_idx * 8
        for col_idx in range(cols):
            x_start = col_idx * 4

            tile_rows: list[list[int]] = []
            for r in range(8):
                y = y_start + r
                row_offset = y * width + x_start
                tile_rows.append(pixel_data[row_offset : row_offset + 4])

            tile_bytes = encode_tile_to_bytes(tile_rows)

            if tile_bytes not in unique_patterns:
                if len(unique_patterns) >= 128:
                    capacity_exceeded = True
                unique_patterns[tile_bytes] = len(unique_patterns)

            char_index = unique_patterns[tile_bytes]
            tiles_mapping.append(
                {
                    "x": x_start,
                    "y": y_start,
                    "column": col_idx,
                    "row": row_idx,
                    "character_index": char_index,
                }
            )

    if capacity_exceeded or len(unique_patterns) > 128:
        total_unique = len(unique_patterns)
        raise CharsetError(
            "ERROR: Charset capacity exceeded.\n"
            f"Found {total_unique} unique characters; maximum allowed is 128.\n"
            "No output files were generated."
        )

    # Build 1024-byte font binary
    font_data = bytearray(1024)
    for pattern, idx in unique_patterns.items():
        font_data[idx * 8 : (idx + 1) * 8] = pattern

    if len(font_data) != 1024:
        raise CharsetError(
            f"ERROR: Charset font size is {len(font_data)} bytes; expected 1024."
        )

    unique_count = len(unique_patterns)
    json_data = {
        "image": {
            "source": source_name,
            "width": width,
            "height": height,
            "tile_width": 4,
            "tile_height": 8,
            "columns": cols,
            "rows": rows,
            "tile_count": total_tiles,
        },
        "charset": {
            "capacity": 128,
            "unique_characters": unique_count,
            "file_size": 1024,
            "unused_characters": 128 - unique_count,
        },
        "tiles": tiles_mapping,
    }

    return bytes(font_data), json_data


def save_outputs(
    font_data: bytes,
    json_data: dict,
    font_path: Path,
    json_path: Path,
    input_path: Path,
) -> None:
    """Safely write charset and JSON files, guaranteeing no partial or corrupted outputs."""
    try:
        font_resolved = font_path.resolve()
        json_resolved = json_path.resolve()
        input_resolved = input_path.resolve()
    except Exception as exc:
        raise CharsetError(f"ERROR: Cannot resolve file paths: {exc}") from exc

    if font_resolved == json_resolved:
        raise CharsetError(
            "ERROR: Font output and JSON output cannot point to the same file."
        )

    if font_resolved == input_resolved or json_resolved == input_resolved:
        raise CharsetError("ERROR: Output file cannot overwrite the input image.")

    try:
        font_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CharsetError(f"ERROR: Cannot create output directories: {exc}") from exc

    tmp_font = font_path.with_name(f"{font_path.name}.tmp_{os.getpid()}")
    tmp_json = json_path.with_name(f"{json_path.name}.tmp_{os.getpid()}")

    font_replaced = False
    try:
        tmp_font.write_bytes(font_data)
        if tmp_font.stat().st_size != 1024:
            raise CharsetError(
                f"ERROR: Generated font size is {tmp_font.stat().st_size} bytes; expected 1024."
            )

        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        tmp_font.replace(font_path)
        font_replaced = True
        tmp_json.replace(json_path)
    except Exception as exc:
        for tmp_file in (tmp_font, tmp_json):
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
        if font_replaced and font_path.exists():
            try:
                font_path.unlink()
            except OSError:
                pass
        raise CharsetError(f"ERROR: Failed to write output files: {exc}") from exc


def process_image_to_charset(
    input_path: Path,
    font_path: Path,
    json_path: Path,
) -> tuple[int, int, int, int]:
    """Execute complete workflow from loading image to saving outputs."""
    if not input_path.exists():
        raise CharsetError(f"ERROR: Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise CharsetError(f"ERROR: Input path is not a file: {input_path}")

    try:
        with Image.open(input_path) as img:
            font_data, json_data = extract_and_build_charset(img, input_path.name)
            width, height = img.size
    except (OSError, Image.DecompressionBombError) as exc:
        raise CharsetError(f"ERROR: Failed to read image '{input_path}': {exc}") from exc

    save_outputs(font_data, json_data, font_path, json_path, input_path)

    total_tiles = json_data["image"]["tile_count"]
    unique_chars = json_data["charset"]["unique_characters"]
    return width, height, total_tiles, unique_chars


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert an indexed 4-color PNG into an Atari 8-bit charset (.fnt) and JSON tile map."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input indexed 4-color PNG image.",
    )
    parser.add_argument(
        "--font-output",
        type=Path,
        default=Path("charset.fnt"),
        help="Path to the output .fnt file (default: charset.fnt).",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("charset.json"),
        help="Path to the output JSON file (default: charset.json).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        width, height, total_tiles, unique_chars = process_image_to_charset(
            args.input, args.font_output, args.json_output
        )
    except CharsetError as err:
        sys.stderr.write(f"{err}\n")
        return 1

    summary = (
        f"Input image: {args.input.name}\n"
        f"Image size: {width}x{height}\n"
        f"Tiles processed: {total_tiles}\n"
        f"Unique characters: {unique_chars} / 128\n"
        f"Charset file: {args.font_output} (1024 bytes)\n"
        f"JSON mapping: {args.json_output}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
