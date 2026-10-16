"""Convert images to ANTIC binary formats for Atari 8-bit.

Supported Modes:
- ANTIC Mode D (Graphics 7): 160x95..97 2 bits per pixel (4 pixels/byte, 40 bytes/line = 3,840 bytes normalized to 96 lines).
- ANTIC Mode F (Graphics 8): 320x192 1 bit per pixel (8 pixels/byte, 40 bytes/line = 7,696 bytes with 4 KB split).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from PIL import Image


def convert_image_to_antic_d(
    input_path: Path,
    output_path: Path,
) -> int:
    """Convert an image (160x95..97) into ANTIC Mode D binary (160x96, 3,840 bytes).

    Args:
        input_path: Path to source image (160x95..97).
        output_path: Destination binary file (3,840 bytes).

    Returns:
        0 on success, non-zero on failure.
    """
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        return 1

    img = Image.open(input_path)
    width, height = img.size

    if width != 160 or height not in (95, 96, 97):
        print(
            f"Error: Expected 160x95..97 image, got {width}x{height}.",
            file=sys.stderr,
        )
        return 1

    if img.mode != "P":
        img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=4)

    pixels = img.load()
    if pixels is None:
        print("Error: Could not load pixel data.", file=sys.stderr)
        return 1

    TARGET_LINES = 96
    raw_bytes = bytearray()
    for y in range(TARGET_LINES):
        if y < height:
            for byte_idx in range(width // 4):
                x = byte_idx * 4
                p0 = pixels[x + 0, y] & 3
                p1 = pixels[x + 1, y] & 3
                p2 = pixels[x + 2, y] & 3
                p3 = pixels[x + 3, y] & 3
                byte_val = (p0 << 6) | (p1 << 4) | (p2 << 2) | p3
                raw_bytes.append(byte_val)
        else:
            # Pad with zero bytes if source has 95 lines
            raw_bytes.extend(bytes(width // 4))

    assert len(raw_bytes) == 3840, f"Invalid binary size: {len(raw_bytes)}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw_bytes)

    print(
        f"Converted '{input_path}' ({width}x{height}) -> '{output_path}' ({len(raw_bytes)} bytes: "
        f"160x96 ANTIC Mode D)"
    )
    return 0


def convert_image_to_antic_f(
    input_path: Path,
    output_path: Path,
    invert: bool = False,
) -> int:
    """Convert a 320x192 image into ANTIC Mode F binary.

    Args:
        input_path: Path to source image.
        output_path: Destination binary file.
        invert: Invert pixel values (0->1, 1->0).

    Returns:
        0 on success, non-zero on failure.
    """
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        return 1

    img = Image.open(input_path)
    width, height = img.size

    if width != 320 or height != 192:
        print(
            f"Error: Expected 320x192 image, got {width}x{height}.",
            file=sys.stderr,
        )
        return 1

    gray = img.convert("L")
    mono = gray.point(lambda p: 255 if p > 128 else 0, mode="1")

    pixels = mono.load()
    if pixels is None:
        print("Error: Could not load pixel data.", file=sys.stderr)
        return 1

    raw_bytes = bytearray()

    for y in range(height):
        for byte_idx in range(width // 8):
            byte_val = 0
            for bit in range(8):
                x = byte_idx * 8 + bit
                is_on = 1 if pixels[x, y] != 0 else 0
                if invert:
                    is_on ^= 1
                if is_on:
                    byte_val |= 1 << (7 - bit)
            raw_bytes.append(byte_val)

    seg1_len = 102 * 40
    seg2_len = 90 * 40

    seg1 = raw_bytes[:seg1_len]
    padding = bytes(4096 - seg1_len)  # 16 bytes
    seg2 = raw_bytes[seg1_len : seg1_len + seg2_len]

    output_data = seg1 + padding + seg2
    assert len(output_data) == 7696, f"Invalid binary size: {len(output_data)}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_data)

    print(
        f"Converted '{input_path}' -> '{output_path}' ({len(output_data)} bytes: "
        f"{seg1_len}b + {len(padding)}b pad + {seg2_len}b)"
    )
    return 0


def main() -> int:
    """CLI entry point for image converter."""
    parser = argparse.ArgumentParser(
        description="Convert image to ANTIC Mode D (160x95..97) or Mode F (320x192) binary."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input PNG image",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("gen/title.bin"),
        help="Path to output binary (default: gen/title.bin)",
    )
    parser.add_argument(
        "--mode",
        choices=["D", "F"],
        default="D",
        help="ANTIC mode: D (160x95..97 2bpp normalized to 96 lines, default) or F (320x192 1bpp)",
    )
    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert pixel values (Mode F only)",
    )

    args = parser.parse_args()
    if args.mode == "D":
        return convert_image_to_antic_d(args.input, args.output)
    else:
        return convert_image_to_antic_f(args.input, args.output, args.invert)


if __name__ == "__main__":
    sys.exit(main())
