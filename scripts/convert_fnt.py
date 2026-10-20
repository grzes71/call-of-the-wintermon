#!/usr/bin/env python3
"""Convert between Atari 8-bit 1bpp font files (.fnt) and indexed PNG glyph sheets.

The .fnt layout matches ``fonts/font.fnt``:
  * 128 characters, 8x8 pixels each,
  * 8 bytes per character, one byte per pixel row,
  * most significant bit is the leftmost pixel,
  * 1 = foreground pixel, 0 = background pixel,
  * total size: 1024 bytes.

The PNG glyph sheet is 128x64 pixels (16 glyphs per row, 8 rows) and uses an
indexed palette with two entries: index 0 = background, index 1 = foreground.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image

GLYPH_WIDTH = 8
GLYPH_HEIGHT = 8
COLUMNS = 16
ROWS = 8
IMAGE_WIDTH = GLYPH_WIDTH * COLUMNS  # 128
IMAGE_HEIGHT = GLYPH_HEIGHT * ROWS  # 64
CHARACTER_COUNT = COLUMNS * ROWS  # 128
FONT_SIZE = CHARACTER_COUNT * GLYPH_HEIGHT  # 1024

BACKGROUND_COLOR = (0, 0, 0)
FOREGROUND_COLOR = (255, 255, 255)


class FntError(Exception):
    """Raised when validation, conversion, or file operations fail."""


def _read_png_pixels(path: Path, invert: bool) -> list[int]:
    """Load an indexed PNG and return 128*64 binary pixel values in row-major order."""
    if not path.exists():
        raise FntError(f"ERROR: Input file does not exist: {path}")
    if not path.is_file():
        raise FntError(f"ERROR: Input path is not a file: {path}")

    try:
        with Image.open(path) as img:
            if img.size != (IMAGE_WIDTH, IMAGE_HEIGHT):
                raise FntError(
                    f"ERROR: Input image must be {IMAGE_WIDTH}x{IMAGE_HEIGHT} pixels; "
                    f"got {img.size[0]}x{img.size[1]}."
                )

            raw_pixels = (
                list(img.get_flattened_data())
                if hasattr(img, "get_flattened_data")
                else list(img.getdata())
            )

            if img.mode == "1":
                # 1-bit images use 0 for black and 255 for white.
                pixels = [1 if value else 0 for value in raw_pixels]
            elif img.mode == "P":
                pixels = raw_pixels
                used = sorted(set(pixels))
                invalid = [index for index in used if index not in (0, 1)]
                if invalid:
                    raise FntError(
                        "ERROR: Input image must use only palette indices 0 (background) "
                        f"and 1 (foreground); found indices {invalid}."
                    )
            else:
                raise FntError(
                    f"ERROR: Input image must be an indexed PNG (mode P or 1); got mode '{img.mode}'."
                )
    except (OSError, Image.DecompressionBombError) as exc:
        raise FntError(f"ERROR: Failed to read image '{path}': {exc}") from exc

    if invert:
        pixels = [1 - value for value in pixels]
    return pixels


def png_to_fnt_data(pixels: Sequence[int]) -> bytes:
    """Encode 128*64 binary pixels into 1024 bytes of Atari font data."""
    if len(pixels) != IMAGE_WIDTH * IMAGE_HEIGHT:
        raise FntError(
            f"ERROR: Expected {IMAGE_WIDTH * IMAGE_HEIGHT} pixels; got {len(pixels)}."
        )

    font = bytearray(FONT_SIZE)
    offset = 0
    for glyph_row in range(ROWS):
        for glyph_col in range(COLUMNS):
            x_start = glyph_col * GLYPH_WIDTH
            y_start = glyph_row * GLYPH_HEIGHT
            for row in range(GLYPH_HEIGHT):
                row_offset = (y_start + row) * IMAGE_WIDTH + x_start
                value = 0
                for column in range(GLYPH_WIDTH):
                    if pixels[row_offset + column]:
                        value |= 0x80 >> column
                font[offset] = value
                offset += 1
    return bytes(font)


def fnt_to_png_image(font_data: bytes) -> Image.Image:
    """Decode 1024 bytes of Atari font data into a 128x64 indexed image."""
    if len(font_data) != FONT_SIZE:
        raise FntError(
            f"ERROR: Input .fnt file must be exactly {FONT_SIZE} bytes; got {len(font_data)}."
        )

    image = Image.new("P", (IMAGE_WIDTH, IMAGE_HEIGHT), 0)
    image.putpalette([*BACKGROUND_COLOR, *FOREGROUND_COLOR])

    pixels = image.load()
    offset = 0
    for glyph_row in range(ROWS):
        for glyph_col in range(COLUMNS):
            x_start = glyph_col * GLYPH_WIDTH
            y_start = glyph_row * GLYPH_HEIGHT
            for row in range(GLYPH_HEIGHT):
                value = font_data[offset]
                offset += 1
                for column in range(GLYPH_WIDTH):
                    if value & (0x80 >> column):
                        pixels[x_start + column, y_start + row] = 1
    return image


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FntError(f"ERROR: Cannot create output directory '{path.parent}': {exc}") from exc


def convert_png_to_fnt(input_path: Path, output_path: Path, invert: bool = False) -> int:
    """Convert an indexed 128x64 PNG glyph sheet into a 1024-byte .fnt file."""
    pixels = _read_png_pixels(input_path, invert)
    font_data = png_to_fnt_data(pixels)

    _ensure_parent(output_path)
    try:
        output_path.write_bytes(font_data)
    except OSError as exc:
        raise FntError(f"ERROR: Failed to write '{output_path}': {exc}") from exc

    return len(font_data)


def convert_fnt_to_png(input_path: Path, output_path: Path) -> tuple[int, int]:
    """Convert a 1024-byte .fnt file into an indexed 128x64 PNG glyph sheet."""
    if not input_path.exists():
        raise FntError(f"ERROR: Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise FntError(f"ERROR: Input path is not a file: {input_path}")

    try:
        font_data = input_path.read_bytes()
    except OSError as exc:
        raise FntError(f"ERROR: Failed to read '{input_path}': {exc}") from exc

    image = fnt_to_png_image(font_data)

    _ensure_parent(output_path)
    try:
        image.save(output_path, format="PNG")
    except OSError as exc:
        raise FntError(f"ERROR: Failed to write '{output_path}': {exc}") from exc

    return image.size


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert between Atari 8-bit 1bpp fonts (.fnt, 128 glyphs of 8x8) "
            "and indexed 128x64 PNG glyph sheets."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    png_to_fnt_parser = subparsers.add_parser(
        "png2fnt",
        help="Convert an indexed 128x64 PNG into a 1024-byte .fnt file.",
    )
    png_to_fnt_parser.add_argument("input", type=Path, help="Input PNG file (128x64, indexed).")
    png_to_fnt_parser.add_argument("output", type=Path, help="Output .fnt file.")
    png_to_fnt_parser.add_argument(
        "--invert",
        action="store_true",
        help="Treat palette index 0 as foreground and index 1 as background.",
    )

    fnt_to_png_parser = subparsers.add_parser(
        "fnt2png",
        help="Convert a 1024-byte .fnt file into an indexed 128x64 PNG.",
    )
    fnt_to_png_parser.add_argument("input", type=Path, help="Input .fnt file (1024 bytes).")
    fnt_to_png_parser.add_argument("output", type=Path, help="Output PNG file.")

    return parser


def _infer_command(argv: list[str]) -> list[str]:
    """Allow shorthand: infer the direction from the input file extension."""
    if not argv or argv[0] in {"png2fnt", "fnt2png", "-h", "--help"}:
        return argv

    suffix = Path(argv[0]).suffix.lower()
    command = {".png": "png2fnt", ".fnt": "fnt2png"}.get(suffix)
    if command is None:
        raise FntError(
            "ERROR: Cannot infer conversion direction. "
            "Use 'png2fnt <input.png> <output.fnt>' or 'fnt2png <input.fnt> <output.png>'."
        )
    return [command, *argv]


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_arg_parser()
    raw_args = list(argv) if argv is not None else sys.argv[1:]

    try:
        args = parser.parse_args(_infer_command(raw_args))

        if args.command == "png2fnt":
            size = convert_png_to_fnt(args.input, args.output, invert=args.invert)
            print(f"Input image: {args.input} ({IMAGE_WIDTH}x{IMAGE_HEIGHT})")
            print(f"Font file: {args.output} ({size} bytes, {CHARACTER_COUNT} glyphs)")
        else:
            width, height = convert_fnt_to_png(args.input, args.output)
            print(f"Font file: {args.input} ({FONT_SIZE} bytes, {CHARACTER_COUNT} glyphs)")
            print(f"Output image: {args.output} ({width}x{height}, indexed palette)")
    except FntError as err:
        sys.stderr.write(f"{err}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
