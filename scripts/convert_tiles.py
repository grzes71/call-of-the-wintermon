"""Convert tileset PNG images to Atari 8-bit ANTIC Mode E (2bpp) binary assets.

ANTIC Mode E (Graphics 7 / 15):
- Resolution: 160 pixels wide, 2 bits per pixel (4 pixels per byte).
- Pixel mapping:
  - bits 7..6: leftmost pixel (x=0)
  - bits 5..4: second pixel   (x=1)
  - bits 3..2: third pixel    (x=2)
  - bits 1..0: fourth pixel   (x=3)
- Palette: 4 colors (0: COLBK, 1: COLPF0, 2: COLPF1, 3: COLPF2).

This script processes PNG files in the specified directory (excluding subdirectories)
and generates:
1. Raw ANTIC Mode E binary files: gen/tiles_<name>.bin
2. An assembly descriptor file: gen/tiles_data.asm containing:
   - Equates for tileset IDs and dimensions
   - Structure-of-Arrays (SoA) metadata tables (width_px, width_bytes, height, size, data ptrs)
   - Recommended Atari GTIA color palette registers
   - Per-tileset precomputed row offset lookup tables for fast 6502 indexing
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
import numpy as np


# Recommended Atari GTIA color registers (COLBK, COLPF0, COLPF1, COLPF2) for known tilesets
DEFAULT_PALETTES: dict[str, tuple[int, int, int, int]] = {
    # name: (COLBK, COLPF0, COLPF1, COLPF2)
    # castles: black, slate blue/grey ($94), olive grey ($D6), light stone ($EA)
    "castles": (0x00, 0x94, 0xD6, 0xEA),
    # depths: black, dark cyan ($A2), medium cyan ($A6), bright teal ($BA)
    "depths": (0x00, 0xA2, 0xA6, 0xBA),
    # hell: black, dark red ($32), orange-red ($26), flame yellow/orange ($1C)
    "hell": (0x00, 0x32, 0x26, 0x1C),
    # trees: black, dark green ($C4), medium emerald ($C8), bright lime ($DC)
    "trees": (0x00, 0xC4, 0xC8, 0xDC),
}


@dataclass
class TilesetInfo:
    """Metadata describing a converted tileset."""

    name: str
    width_px: int
    height_lines: int
    width_bytes: int
    size_bytes: int
    bin_filename: str
    colbk: int
    colpf0: int
    colpf1: int
    colpf2: int


def quantize_rgb_to_4colors(img: Image.Image) -> np.ndarray:
    """Convert an RGB image to a 2D array of 2-bit color indices (0..3).

    Black / background (luminance <= 10) maps to index 0.
    Non-black pixels are clustered into 3 luminance levels:
    - 1: dark shade
    - 2: medium shade
    - 3: highlight / light shade
    """
    arr = np.array(img.convert("RGB"), dtype=np.float64)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    # Non-black luminance
    non_black = lum[lum > 10.0]
    if len(non_black) == 0:
        return np.zeros(arr.shape[:2], dtype=np.uint8)

    # 1D K-means clustering on non-black pixels into 3 centers
    p25, p50, p75 = np.percentile(non_black, [25, 50, 75])
    centers = np.array([float(p25), float(p50), float(p75)], dtype=np.float64)

    for _ in range(25):
        dists = np.abs(non_black[:, None] - centers[None, :])
        labels = np.argmin(dists, axis=1)
        for k in range(3):
            mask = labels == k
            if np.any(mask):
                centers[k] = non_black[mask].mean()
    centers.sort()

    th2 = (centers[0] + centers[1]) / 2.0
    th3 = (centers[1] + centers[2]) / 2.0

    indexed = np.zeros(arr.shape[:2], dtype=np.uint8)
    indexed[lum > 10.0] = 1
    indexed[lum > th2] = 2
    indexed[lum > th3] = 3

    return indexed


def image_to_indexed_2bit(img: Image.Image) -> np.ndarray:
    """Convert a PIL Image to a 2D numpy array of 2-bit indices (0..3)."""
    if img.mode == "P":
        # Palette mode: ensure indices are sorted by luminance if not already
        pal = img.getpalette() or []
        rgbs = [
            (pal[i], pal[i + 1], pal[i + 2])
            for i in range(0, min(12, len(pal)), 3)
        ]
        # Check if index 0 is black / darkest
        lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in rgbs]
        sorted_order = np.argsort(lums)

        raw = np.array(img, dtype=np.uint8)
        if list(sorted_order) == list(range(len(rgbs))):
            # Already sorted by luminance: clip to 0..3
            return np.clip(raw, 0, 3)

        # Remap palette indices to ascending luminance order
        lut = np.zeros(256, dtype=np.uint8)
        for new_idx, old_idx in enumerate(sorted_order):
            lut[old_idx] = min(new_idx, 3)
        return lut[raw]

    # RGB or RGBA mode
    return quantize_rgb_to_4colors(img)


def pack_antic_e_bytes(indexed: np.ndarray) -> bytes:
    """Pack a 2D array of 2-bit pixels (0..3) into ANTIC Mode E byte stream.

    4 pixels per byte:
    - pixel 0 (x % 4 == 0): bits 7..6
    - pixel 1 (x % 4 == 1): bits 5..4
    - pixel 2 (x % 4 == 2): bits 3..2
    - pixel 3 (x % 4 == 3): bits 1..0
    """
    height, width = indexed.shape
    width_bytes = (width + 3) // 4
    out = bytearray(height * width_bytes)

    out_idx = 0
    for y in range(height):
        row = indexed[y]
        for b in range(width_bytes):
            x_base = b * 4
            p0 = int(row[x_base]) if x_base < width else 0
            p1 = int(row[x_base + 1]) if x_base + 1 < width else 0
            p2 = int(row[x_base + 2]) if x_base + 2 < width else 0
            p3 = int(row[x_base + 3]) if x_base + 3 < width else 0

            val = ((p0 & 3) << 6) | ((p1 & 3) << 4) | ((p2 & 3) << 2) | (p3 & 3)
            out[out_idx] = val
            out_idx += 1

    return bytes(out)


def generate_asm_descriptors(tilesets: list[TilesetInfo], output_asm_path: Path) -> None:
    """Generate MADS assembly header and Structure-of-Arrays tables."""
    lines: list[str] = [
        "; ==============================================================================",
        "; TILESET METADATA & ROW OFFSET TABLES (Auto-generated by convert_tiles.py)",
        "; Target: Atari 800XL / 65XE (ANTIC Mode E, 160x96 2bpp)",
        "; Format: Structure-of-Arrays (SoA) for fast indexed 6502 access",
        "; ==============================================================================",
        "",
        "; --- Tileset Identifiers ---",
    ]

    for idx, t in enumerate(tilesets):
        lines.append(f"TILESET_{t.name.upper():<10} = {idx}")
    lines.append(f"TILESET_COUNT      = {len(tilesets)}")
    lines.append("")

    lines.append("; --- Tileset Dimension Equates ---")
    for t in tilesets:
        u = t.name.upper()
        lines.append(f"TILESET_{u}_W_PX    = {t.width_px}")
        lines.append(f"TILESET_{u}_W_BYTES = {t.width_bytes}")
        lines.append(f"TILESET_{u}_H_LINES = {t.height_lines}")
        lines.append(f"TILESET_{u}_SIZE    = {t.size_bytes}")
    lines.append("")

    lines.append("; --- Structure-of-Arrays (SoA) Metadata Tables ---")
    lines.append("tileset_w_px_lo")
    lines.append("    .byte " + ", ".join(f"<TILESET_{t.name.upper()}_W_PX" for t in tilesets))
    lines.append("tileset_w_px_hi")
    lines.append("    .byte " + ", ".join(f">TILESET_{t.name.upper()}_W_PX" for t in tilesets))
    lines.append("tileset_w_bytes")
    lines.append("    .byte " + ", ".join(f"TILESET_{t.name.upper()}_W_BYTES" for t in tilesets))
    lines.append("tileset_h_lines")
    lines.append("    .byte " + ", ".join(f"TILESET_{t.name.upper()}_H_LINES" for t in tilesets))
    lines.append("tileset_size_lo")
    lines.append("    .byte " + ", ".join(f"<TILESET_{t.name.upper()}_SIZE" for t in tilesets))
    lines.append("tileset_size_hi")
    lines.append("    .byte " + ", ".join(f">TILESET_{t.name.upper()}_SIZE" for t in tilesets))
    lines.append("tileset_data_lo")
    lines.append("    .byte " + ", ".join(f"<tiles_{t.name}_data" for t in tilesets))
    lines.append("tileset_data_hi")
    lines.append("    .byte " + ", ".join(f">tiles_{t.name}_data" for t in tilesets))
    lines.append("")

    lines.append("; --- Recommended Atari GTIA Palette Color Registers ---")
    lines.append("tileset_colbk")
    lines.append("    .byte " + ", ".join(f"${t.colbk:02X}" for t in tilesets))
    lines.append("tileset_colpf0")
    lines.append("    .byte " + ", ".join(f"${t.colpf0:02X}" for t in tilesets))
    lines.append("tileset_colpf1")
    lines.append("    .byte " + ", ".join(f"${t.colpf1:02X}" for t in tilesets))
    lines.append("tileset_colpf2")
    lines.append("    .byte " + ", ".join(f"${t.colpf2:02X}" for t in tilesets))
    lines.append("")

    lines.append("; --- Precomputed Row Offset Tables (stride * y) ---")
    for t in tilesets:
        lines.append(f"; {t.name}: {t.height_lines} lines, stride {t.width_bytes} bytes")
        lines.append(f"tiles_{t.name}_row_lo")
        row_los = [f"<({y}*{t.width_bytes})" for y in range(t.height_lines)]
        for chunk_start in range(0, len(row_los), 16):
            chunk = row_los[chunk_start : chunk_start + 16]
            lines.append("    .byte " + ", ".join(chunk))

        lines.append(f"tiles_{t.name}_row_hi")
        row_his = [f">({y}*{t.width_bytes})" for y in range(t.height_lines)]
        for chunk_start in range(0, len(row_his), 16):
            chunk = row_his[chunk_start : chunk_start + 16]
            lines.append("    .byte " + ", ".join(chunk))
        lines.append("")

    lines.append("; --- Pointers to Row Offset Tables ---")
    lines.append("tileset_row_table_lo")
    lines.append("    .byte " + ", ".join(f"<tiles_{t.name}_row_lo" for t in tilesets))
    lines.append("tileset_row_table_hi")
    lines.append("    .byte " + ", ".join(f">tiles_{t.name}_row_lo" for t in tilesets))
    lines.append("")

    output_asm_path.parent.mkdir(parents=True, exist_ok=True)
    output_asm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_tiles(tiles_dir: Path, gen_dir: Path) -> int:
    """Scan tiles_dir for PNG files, convert to ANTIC Mode E, and generate ASM descriptors."""
    if not tiles_dir.is_dir():
        print(f"Error: Tiles directory '{tiles_dir}' not found.", file=sys.stderr)
        return 1

    gen_dir.mkdir(parents=True, exist_ok=True)

    # Find PNG files directly in tiles_dir (ignore subdirectories like tiles/org)
    png_files = sorted(
        [
            p
            for p in tiles_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".png"
        ]
    )

    if not png_files:
        print(f"Warning: No PNG files found directly in '{tiles_dir}'.", file=sys.stderr)
        return 0

    print("=" * 60)
    print("CONVERTING TILESETS TO ANTIC MODE E (160x96 2bpp)")
    print("=" * 60)

    tilesets: list[TilesetInfo] = []
    total_bytes = 0

    for png_path in png_files:
        name = png_path.stem
        img = Image.open(png_path)
        w, h = img.size

        indexed = image_to_indexed_2bit(img)
        bin_data = pack_antic_e_bytes(indexed)

        bin_filename = f"tiles_{name}.bin"
        bin_path = gen_dir / bin_filename
        bin_path.write_bytes(bin_data)

        w_bytes = (w + 3) // 4
        size_bytes = len(bin_data)
        total_bytes += size_bytes

        pal = DEFAULT_PALETTES.get(name, (0x00, 0x94, 0x26, 0xDC))

        info = TilesetInfo(
            name=name,
            width_px=w,
            height_lines=h,
            width_bytes=w_bytes,
            size_bytes=size_bytes,
            bin_filename=bin_filename,
            colbk=pal[0],
            colpf0=pal[1],
            colpf1=pal[2],
            colpf2=pal[3],
        )
        tilesets.append(info)

        print(
            f"  {name:<10}: {w:3d}x{h:2d} px -> {w_bytes:2d} B/line x {h:2d} lines "
            f"= {size_bytes:5d} bytes -> {bin_filename}"
        )

    asm_path = gen_dir / "tiles_data.asm"
    generate_asm_descriptors(tilesets, asm_path)
    print(f"Generated ASM descriptor: {asm_path.name}")
    print("-" * 60)
    print(f"Total Converted Tiles Data: {total_bytes:,} bytes across {len(tilesets)} tilesets")
    print("=" * 60)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert tileset PNG images to ANTIC Mode E binary assets and ASM structures."
    )
    parser.add_argument(
        "--tiles-dir",
        type=Path,
        default=Path("tiles"),
        help="Source directory containing tileset PNGs (default: tiles)",
    )
    parser.add_argument(
        "--gen-dir",
        type=Path,
        default=Path("gen"),
        help="Destination directory for binaries and asm (default: gen)",
    )

    args = parser.parse_args()
    return convert_tiles(args.tiles_dir, args.gen_dir)


if __name__ == "__main__":
    sys.exit(main())
