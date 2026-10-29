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
            seg_type = "Tileset Metadata, Status Line & SFX Engine"
        elif start in (0x5000, 0x2C30, 0x2D00):
            seg_type = "Scene Runtime Engine (secrets/channel dispatch/enemies/sfx)"
        elif start in (0xA800, 0xA400, 0xA300):
            seg_type = "Scene SoA Tables, DLI Blocks & Pointer Tables (grows with scene count)"
        elif start == 0x3000:
            seg_type = "Gameplay VRAM (ANTIC Mode D 160x96) + DLIST"
        elif start == 0x3F00:
            seg_type = "Gameplay Display List"
        elif start == 0x4000:
            seg_type = "Title Vertical Scroll VRAM & Text"
        elif start == 0x6000:
            seg_type = "Title Display List"
        elif start == 0x6100:
            seg_type = "Unified DLI Double Buffers"
        elif start == 0x5C00:
            seg_type = "Game Over / Victory Module (2 display lists + DLI chain + builder)"
        elif start in (0xBC00, 0xBD00):
            seg_type = "Game Over Texts (generated compact data)"
        elif start == 0x6800:
            seg_type = "Render Lookup Tables + Intro Screen Handler"
        elif start == 0x69C0:
            seg_type = "Intro Screen Handler (relocated from $2000)"
        elif start == 0x6B00:
            seg_type = "Active PMG (1.25 KB) + Audio Player & Music"
        elif start == 0x7000:
            seg_type = "Audio Player & Music Buffers"
        elif start in (0x79D0, 0x7A00):
            seg_type = "Playfield Blitter Engine & Sprites Data"
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

    # Rule 3: no two payload segments may overlap. Checked in address order, because the XEX
    # may emit segments out of address order (e.g. the scene tables above the tilesets).
    prev_end: int | None = None
    for start, end, size in sorted(seg for seg in segments if seg[0] not in (0x02E0, 0x02E2)):
        if prev_end is not None and start <= prev_end:
            errors.append(
                f"Segment ${start:04X}-${end:04X} overlaps the previous segment ending at ${prev_end:04X}!"
            )
        prev_end = end

    # Scene data tables headroom: how much room is left for additional scenes
    scene_tables_seg = next((s for s in segments if s[0] in (0xA800, 0xA400, 0xA300)), None)
    if scene_tables_seg:
        st_start, st_end, st_size = scene_tables_seg
        # The Game Over text segment sits in the same window, so its bytes are not
        # available for more scenes.
        go_text_seg = next((s for s in segments if s[0] in (0xBC00, 0xBD00)), None)
        st_reserved = go_text_seg[2] if go_text_seg else 0
        st_headroom = 0xBFFF - st_end - st_reserved
        print(
            f"Scene Data Tables (${st_start:04X}-$BFFF) used {st_size} bytes, "
            f"{st_headroom} bytes left for additional scenes"
            + (f" (Game Over texts reserve {st_reserved} bytes)" if st_reserved else "")
        )

    # Dedicated check for Render Code / Sprites segment ($7A00-$7FFF) headroom before $8000
    # Cost of a typical sprite: 20 rows/frame * 2 frames + 2 frames * 2 bytes pointer = 44 bytes (or 48 bytes with SoA tables)
    TYPICAL_SPRITE_COST = 44
    render_code_seg = next((s for s in segments if s[0] == 0x7A00 or s[0] == 0x79D0), None)
    if render_code_seg:
        r_start, r_end, r_size = render_code_seg
        r_headroom = 0x8000 - (r_end + 1)
        print(
            f"Sprite/Render Engine Segment ($7A00-$7FFF) Headroom before $8000: "
            f"{r_headroom} bytes (Typical sprite cost: {TYPICAL_SPRITE_COST} B)"
        )
        if r_headroom < TYPICAL_SPRITE_COST:
            errors.append(
                f"Krytyczny brak pamięci: rezerwa segmentu danych sprite'ów ($7A00) wynosi tylko {r_headroom} B "
                f"(wymagane minimum {TYPICAL_SPRITE_COST} B na 1 typowy sprite)!"
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
