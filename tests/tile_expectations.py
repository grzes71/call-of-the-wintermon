"""Asset-agnostic tileset expectations derived from the source PNGs.

Rule 05 (Test Design & Asset Agnosticism): tests must never hardcode tileset
dimensions, binary sizes, palettes or element crops - those evolve with the
graphics. Everything here is derived from `tiles/*.png`, the scene JSONs and the
compiled ROM tables, so replacing the background artwork cannot break the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.convert_tiles import image_to_indexed_2bit, pack_antic_e_bytes

TILES_DIR = Path("tiles")
SCENES_DIR = Path("scenes")

GAME_VRAM_PITCH = 40   # bytes per Mode E/D playfield line
GAME_VRAM_LINES = 96


def tileset_files() -> list[tuple[str, Path]]:
    """(tileset name, source PNG) pairs in the converter's emission order.

    scripts/convert_tiles.py converts the PNGs in sorted order, so the engine's
    tileset indices follow the same alphabetical order (castles, depths, hell, trees).
    """
    return [(path.stem, path) for path in sorted(TILES_DIR.glob("*.png"))]


def expected_tileset_metrics() -> list[dict[str, Any]]:
    """Derived ANTIC Mode E metrics for every tileset, in engine index order."""
    metrics: list[dict[str, Any]] = []
    for name, path in tileset_files():
        width_px, height_lines = Image.open(path).size
        width_bytes = (width_px + 3) // 4   # 4 pixels per byte
        metrics.append(
            {
                "name": name,
                "path": path,
                "w_px": width_px,
                "h_lines": height_lines,
                "w_bytes": width_bytes,
                "size": width_bytes * height_lines,
            }
        )
    return metrics


def tileset_index(name: str) -> int:
    """Engine index of a tileset (its position in the converter's emission order)."""
    return [metric["name"] for metric in expected_tileset_metrics()].index(name)


def load_scene(scene_file: str) -> dict[str, Any]:
    return json.loads((SCENES_DIR / scene_file).read_text(encoding="utf-8"))


def element_dst_rect(element: dict[str, Any]) -> tuple[int, int, int, int]:
    """(dst_x_byte, dst_y, w_bytes, h_lines) of a scene element, as compiled.

    scripts/compile_scenes.py emits `dst_x_byte = max(0, x) // 4` and keeps the raw
    y, while the width is packed in bytes (4 pixels each).
    """
    rect = element["source_rect"]
    width_bytes = (rect["width"] + 3) // 4
    return (
        max(0, int(element["position"]["x"])) // 4,
        int(element["position"]["y"]),
        width_bytes,
        rect["height"],
    )


def element_is_rendered(element: dict[str, Any]) -> bool:
    """Whether render_scene_background draws this element at all.

    The renderer skips an element whose destination byte column is >= 40 or whose
    destination line is >= 96 (so negative y values are skipped, not clipped).
    """
    dst_x, dst_y, _, _ = element_dst_rect(element)
    return 0 <= dst_x < GAME_VRAM_PITCH and 0 <= dst_y < GAME_VRAM_LINES


def element_reference_bytes(mem, labels, element: dict[str, Any]) -> list[list[int]]:
    """Reference ANTIC Mode E bytes for a scene element, scanline by scanline.

    Mirrors the compiler/renderer contract exactly: the bitmap is read at byte column
    `src_x // 4` for `w_bytes` bytes per scanline (byte-aligned source reads, so a
    source x that is not a multiple of 4 shifts the crop), and flip_x reverses the
    byte order of each scanline while swapping the pixels inside every byte through
    the ROM flip table.
    """
    rect = element["source_rect"]
    width_bytes = (rect["width"] + 3) // 4
    src_x_byte = int(rect["x"]) // 4
    src_y = int(rect["y"])

    image = Image.open(element["source"])
    stride = (image.size[0] + 3) // 4
    packed = pack_antic_e_bytes(image_to_indexed_2bit(image))

    rows: list[list[int]] = []
    for line in range(rect["height"]):
        start = (src_y + line) * stride + src_x_byte
        row = list(packed[start : start + width_bytes])
        if len(row) < width_bytes:  # read past the bitmap: the renderer sees zeroes
            row += [0] * (width_bytes - len(row))

        if element.get("flip_x"):
            flip = labels["FLIP_BYTE_2BPP"]
            row = [mem[flip + byte] for byte in reversed(row)]
        rows.append(row)
    return rows


def topmost_visible_element(scene: dict[str, Any]) -> dict[str, Any] | None:
    """Topmost element the renderer draws fully inside the playfield.

    The element is the last one drawn for its z_index, so no later element can
    overwrite its bytes and they can be compared against VRAM exactly.
    """
    for element in sorted(scene["elements"], key=lambda e: e.get("z_index", 0), reverse=True):
        if not element_is_rendered(element):
            continue
        dst_x, dst_y, w_bytes, h_lines = element_dst_rect(element)
        if dst_x + w_bytes > GAME_VRAM_PITCH or dst_y + h_lines > GAME_VRAM_LINES:
            continue
        return element
    return None
