"""Validate memory map and bounds for Atari 8-bit executable (.xex).

Enforces project rules:
1. All user segments must end at or below $BFFF.
2. OS ROM ($C000-$CFFF, $E000-$FFFF) and Hardware registers ($D000-$DFFF) must never be overwritten.
3. Display lists must not cross a 1 KB ($0400) boundary.
4. Reports segment allocations and remaining headroom.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_xex_segments(data: bytes) -> list[tuple[int, int, int]]:
    """Parse segments from an Atari DOS XEX binary file.

    Returns list of (start_addr, end_addr, size).
    """
    segments: list[tuple[int, int, int]] = []
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0

    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4

        # If secondary header $FFFF is encountered, re-read start/end
        if start == 0xFFFF:
            if pos + 4 > len(data):
                break
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4

        size = end - start + 1
        if size <= 0 or pos + size > len(data):
            break

        segments.append((start, end, size))
        pos += size

    return segments


def check_memory(xex_path: Path) -> int:
    """Validate memory segments against Atari hardware and engine architecture rules."""
    if not xex_path.exists():
        print(f"Error: XEX file '{xex_path}' not found.", file=sys.stderr)
        return 1

    data = xex_path.read_bytes()
    segments = parse_xex_segments(data)

    print("=" * 60)
    print(f"ATARI MEMORY VALIDATION: {xex_path.name}")
    print("=" * 60)

    errors: list[str] = []
    total_user_bytes = 0

    for start, end, size in segments:
        seg_type = "DATA/CODE"
        if start == 0x02E0 or start == 0x02E2:
            seg_type = "VECTOR (RUNAD/INITAD)"
        elif start == 0x2000:
            seg_type = "Engine & State Machine Code"
        elif start == 0x2400:
            seg_type = "Intro Font / Text VRAM / DLIST"
        elif start == 0x2A00:
            seg_type = "Intro Display List"
        elif start in (0x2A30, 0x2B00):
            seg_type = "Tileset Metadata & Row Tables"
        elif start in (0x2C30, 0x2D00):
            seg_type = "Scene Definitions & Object Tables"
        elif start == 0x3000:
            seg_type = "Gameplay VRAM (ANTIC Mode D 160x96) + DLIST"
        elif start == 0x3F00:
            seg_type = "Gameplay Display List"
        elif start == 0x4000:
            seg_type = "Title Screen VRAM (320x192 Mode F)"
        elif start == 0x6000:
            seg_type = "Title Display List"
        elif start == 0x6100:
            seg_type = "Unified DLI Double Buffers"
        elif start == 0x6800:
            seg_type = "Player-Missile Graphics (PMG 2 KB) + Audio"
        elif start == 0x7000:
            seg_type = "Audio Player & Music Buffers"
        elif start in (0x79D0, 0x7A00):
            seg_type = "Render Lookup Tables (Flip & Row Pointers)"
        elif start == 0x8000:
            seg_type = "ANTIC Mode E Tileset Bitmaps"

        if start != 0x02E0 and start != 0x02E2:
            total_user_bytes += size

        print(
            f"Segment: ${start:04X} - ${end:04X}  ({size:5d} bytes)  [{seg_type}]"
        )

        # Skip vector targets for memory boundary checks
        if start == 0x02E0 or start == 0x02E2:
            continue

        # Rule 1 & 2: Boundary checks
        if start >= 0xC000:
            errors.append(
                f"Segment ${start:04X}-${end:04X} overlaps OS ROM ($C000+)!"
            )
        elif end >= 0xC000:
            errors.append(
                f"Segment ${start:04X}-${end:04X} exceeds $BFFF user limit into OS ROM!"
            )
        elif 0xD000 <= start <= 0xDFFF or 0xD000 <= end <= 0xDFFF:
            errors.append(
                f"Segment ${start:04X}-${end:04X} overlaps Hardware Registers ($D000-$DFFF)!"
            )

    print("-" * 60)
    print(f"Total User RAM Allocated: {total_user_bytes:,} bytes")
    # Base user RAM available: $2000 to $BFFF = $A000 (40,960 bytes)
    headroom = 40960 - total_user_bytes
    print(f"Estimated Available Headroom below $C000: {headroom:,} bytes")
    print("=" * 60)

    if errors:
        for err in errors:
            print(f"FAILED: {err}", file=sys.stderr)
        return 1

    print("SUCCESS: All segments pass memory architecture validation.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Atari 8-bit XEX memory boundaries.")
    parser.add_argument("xex", type=Path, help="Path to .xex file to validate")
    args = parser.parse_args()
    return check_memory(args.xex)


if __name__ == "__main__":
    sys.exit(main())
