"""Generate 10 centered 40-character lines of Atari internal screen codes from a text file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Polish diacritics mapping for Atari 8-bit custom font
# Ą, Ć, Ę, Ł, Ń, Ó, Ś, Ź, Ż -> 65, 66, 67, 68, 69, 70, 71, 72, 73
# ą, ć, ę, ł, ń, ó, ś, ź, ż -> 81, 82, 83, 84, 85, 86, 87, 88, 89
POLISH_CHARS: dict[str, int] = {
    # Uppercase
    "Ą": 65,
    "Ć": 66,
    "Ę": 67,
    "Ł": 68,
    "Ń": 69,
    "Ó": 70,
    "Ś": 71,
    "Ź": 72,
    "Ż": 73,
    # Lowercase
    "ą": 81,
    "ć": 82,
    "ę": 83,
    "ł": 84,
    "ń": 85,
    "ó": 86,
    "ś": 87,
    "ź": 88,
    "ż": 89,
}


def char_to_atari_screencode(c: str) -> int:
    """Convert Unicode character to Atari ANTIC 2 internal screen code."""
    if c in POLISH_CHARS:
        return POLISH_CHARS[c]
    val = ord(c)
    if 32 <= val <= 95:
        return val - 32
    if 96 <= val <= 127:
        return val
    if 0 <= val <= 31:
        return val + 64
    return 0  # Default to blank space


def generate_intro_text_binary(input_path: Path, output_path: Path) -> int:
    """Read lines from input_path, center each of 10 lines, and encode to screen codes."""
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        return 1

    content = input_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if len(lines) != 10:
        print(
            f"Error: Expected exactly 10 lines in '{input_path}', got {len(lines)}.",
            file=sys.stderr,
        )
        return 1

    buffer = bytearray()
    for idx, line in enumerate(lines, start=1):
        if len(line) > 40:
            print(
                f"Error: Line {idx} exceeds 40 characters ({len(line)}): '{line}'",
                file=sys.stderr,
            )
            return 1

        left_pad = (40 - len(line)) // 2
        right_pad = 40 - len(line) - left_pad
        centered = (" " * left_pad) + line + (" " * right_pad)
        assert len(centered) == 40, f"Line {idx} length is {len(centered)}, expected 40"

        encoded = [char_to_atari_screencode(c) for c in centered]
        buffer.extend(encoded)

    assert len(buffer) == 400, f"Expected 400 bytes, got {len(buffer)}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buffer)
    print(
        f"Generated Intro text: '{input_path}' -> '{output_path}' ({len(buffer)} bytes, 10 lines x 40 cols)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert input text file to Atari Intro screen text binary."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("texts/intro.txt"),
        help="Path to input text file (default: texts/intro.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("gen/intro_text.bin"),
        help="Path to output binary file (default: gen/intro_text.bin)",
    )
    args = parser.parse_args()
    return generate_intro_text_binary(args.input, args.output)


if __name__ == "__main__":
    sys.exit(main())
