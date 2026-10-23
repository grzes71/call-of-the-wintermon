"""Generate centered 40-character lines of Atari internal screen codes from a text file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Number of text lines on the intro screen. Must match the number of ANTIC Mode 2
# instructions in dlist_intro (main.asm): each text line is 8 scanlines + DL_BLANK8,
# and the display list fills the PAL screen (3 + 3 blank8 margins, 232 scanlines).
INTRO_TEXT_LINES = 12
INTRO_TEXT_COLS = 40
INTRO_TEXT_SIZE = INTRO_TEXT_LINES * INTRO_TEXT_COLS

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
    """Read lines from input_path, center each line, and encode to screen codes."""
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        return 1

    content = input_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if len(lines) != INTRO_TEXT_LINES:
        print(
            f"Error: Expected exactly {INTRO_TEXT_LINES} lines in '{input_path}', got {len(lines)}.",
            file=sys.stderr,
        )
        return 1

    buffer = bytearray()
    for idx, line in enumerate(lines, start=1):
        if len(line) > INTRO_TEXT_COLS:
            print(
                f"Error: Line {idx} exceeds {INTRO_TEXT_COLS} characters ({len(line)}): '{line}'",
                file=sys.stderr,
            )
            return 1

        left_pad = (INTRO_TEXT_COLS - len(line)) // 2
        right_pad = INTRO_TEXT_COLS - len(line) - left_pad
        centered = (" " * left_pad) + line + (" " * right_pad)
        assert len(centered) == INTRO_TEXT_COLS, (
            f"Line {idx} length is {len(centered)}, expected {INTRO_TEXT_COLS}"
        )

        encoded = [char_to_atari_screencode(c) for c in centered]
        buffer.extend(encoded)

    assert len(buffer) == INTRO_TEXT_SIZE, f"Expected {INTRO_TEXT_SIZE} bytes, got {len(buffer)}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buffer)
    print(
        f"Generated Intro text: '{input_path}' -> '{output_path}' "
        f"({len(buffer)} bytes, {INTRO_TEXT_LINES} lines x {INTRO_TEXT_COLS} cols)"
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
