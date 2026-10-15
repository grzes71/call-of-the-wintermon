"""Convert a 320x192 1-bit image to ANTIC Mode F binary format for Atari 8-bit.

ANTIC Mode F (Graphics 8) uses 1 bit per pixel (40 bytes per scanline, 320 pixels wide).
Because ANTIC's 12-bit address counter wraps at 4 KB ($1000) boundaries:
- Segment 1: scanlines 0..101 (102 lines * 40 = 4080 bytes).
- 16 bytes of padding to align Segment 2 at the next 4 KB boundary ($1000).
- Segment 2: scanlines 102..191 (90 lines * 40 = 3600 bytes).
Total binary size: 4096 + 3600 = 7696 bytes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from PIL import Image


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

    # Convert to 1-bit monochrome image (mode '1')
    # Threshold at 128 luminance if RGB/RGBA/P
    gray = img.convert("L")
    mono = gray.point(lambda p: 255 if p > 128 else 0, mode="1")

    # If original image is indexed with palette, verify if index 1 corresponds to foreground
    # In images/title.png, index 0 is black (0,0,0) and 1 is white (255,255,255).
    # mono image has 0 for black (<128) and 255 for white (>128).
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
                # 255 in mode '1' means foreground (white) -> bit 1
                is_on = 1 if pixels[x, y] != 0 else 0
                if invert:
                    is_on ^= 1
                if is_on:
                    byte_val |= 1 << (7 - bit)
            raw_bytes.append(byte_val)

    # ANTIC 4KB boundary split:
    # Segment 1: Lines 0..101 -> 102 * 40 = 4080 bytes
    # Padding: 16 zero bytes -> 4096 bytes total
    # Segment 2: Lines 102..191 -> 90 * 40 = 3600 bytes
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
        description="Convert 320x192 image to ANTIC Mode F (Graphics 8) binary."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input PNG image (320x192)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("gen/title.bin"),
        help="Path to output binary (default: gen/title.bin)",
    )
    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert pixel values (0->1, 1->0)",
    )

    args = parser.parse_args()
    return convert_image_to_antic_f(args.input, args.output, args.invert)


if __name__ == "__main__":
    sys.exit(main())
