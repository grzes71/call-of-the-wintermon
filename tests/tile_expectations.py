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
SCENE_PLAYFIELD_LINES = 92


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


def element_geometry(element: dict[str, Any]) -> dict[str, int]:
    """Element geometry exactly as scripts/compile_scenes.py emits it.

    The compiler packs the width into bytes (4 pixels each), clamps the destination column to
    `max(0, x) // 4`, and clips elements that start above or left of the playfield: the source
    pointer advances and the extent shrinks so the visible part keeps its editor position
    (engine/render.asm skips - rather than clips - negative destinations on its own).
    """
    rect = element["source_rect"]
    pos = element["position"]

    src_x_byte = int(rect["x"]) // 4
    src_y = int(rect["y"])
    w_bytes = (int(rect["width"]) + 3) // 4
    h_lines = int(rect["height"])
    dst_x_byte = max(0, int(pos["x"])) // 4
    dst_y = int(pos["y"])

    if dst_y < 0:
        clipped_lines = min(h_lines, -dst_y)
        src_y += clipped_lines
        h_lines -= clipped_lines
        dst_y = 0

    if int(pos["x"]) < 0:
        clipped_bytes = min(w_bytes, (-int(pos["x"])) // 4)
        w_bytes -= clipped_bytes
        if not element.get("flip_x"):
            src_x_byte += clipped_bytes
        dst_x_byte = 0

    # Right edge: the compiler emits the clipped extent and, for a flipped element, advances the
    # source pointer so the emitted range starts at the byte that appears leftmost (the engine
    # reads a flipped range right-to-left from its start - see scripts/compile_scenes.py).
    if dst_x_byte + w_bytes > GAME_VRAM_PITCH:
        clipped_bytes = (dst_x_byte + w_bytes) - GAME_VRAM_PITCH
        w_bytes -= clipped_bytes
        if element.get("flip_x"):
            src_x_byte += clipped_bytes

    return {
        "src_x_byte": src_x_byte,
        "src_y": src_y,
        "w_bytes": w_bytes,
        "h_lines": h_lines,
        "dst_x_byte": dst_x_byte,
        "dst_y": dst_y,
    }


def element_dst_rect(element: dict[str, Any]) -> tuple[int, int, int, int]:
    """(dst_x_byte, dst_y, w_bytes, h_lines) of a scene element, as compiled and clipped."""
    geometry = element_geometry(element)
    return (
        geometry["dst_x_byte"],
        geometry["dst_y"],
        geometry["w_bytes"],
        geometry["h_lines"],
    )


def element_is_rendered(element: dict[str, Any]) -> bool:
    """Whether render_scene_background draws this element at all.

    The renderer skips an element with a zero width/height (which is what an element clipped
    completely off the playfield compiles to), a destination byte column >= 40 or a destination
    line >= 96.
    """
    geometry = element_geometry(element)
    if geometry["w_bytes"] <= 0 or geometry["h_lines"] <= 0:
        return False
    return (
        0 <= geometry["dst_x_byte"] < GAME_VRAM_PITCH
        and 0 <= geometry["dst_y"] < SCENE_PLAYFIELD_LINES
    )


def element_reference_bytes(mem, labels, element: dict[str, Any]) -> list[list[int]]:
    """Reference ANTIC Mode E bytes for a scene element, scanline by scanline.

    Mirrors the compiler/renderer contract exactly: the bitmap is read at byte column
    `src_x // 4` for `w_bytes` bytes per scanline (byte-aligned source reads, so a
    source x that is not a multiple of 4 shifts the crop), and flip_x reverses the
    byte order of each scanline while swapping the pixels inside every byte through
    the ROM flip table.
    """
    geometry = element_geometry(element)
    src_x_byte = geometry["src_x_byte"]
    src_y = geometry["src_y"]
    width_bytes = geometry["w_bytes"]

    image = Image.open(element["source"])
    stride = (image.size[0] + 3) // 4
    packed = pack_antic_e_bytes(image_to_indexed_2bit(image))

    rows: list[list[int]] = []
    for line in range(geometry["h_lines"]):
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
