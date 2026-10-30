"""Element clipping tests: elements starting above/left of the playfield must still be drawn.

Rule 05 (Test Design & Asset Agnosticism): every expectation is derived from `scenes/*.json`,
the reference geometry model in `tests/tile_expectations.py` and the compiled ROM tables.
"""

from __future__ import annotations

import json
from pathlib import Path

from py65.devices.mpu6502 import MPU
import pytest

from scripts.compile_scenes import load_catalogues, parse_scene_json
from tests.scene_expectations import scene_files
from tests.tile_expectations import (
    GAME_VRAM_LINES,
    GAME_VRAM_PITCH,
    element_dst_rect,
    element_geometry,
    element_is_rendered,
    element_reference_bytes,
    load_scene,
)
from tests.test_dli_system import load_xex_and_symbols, run_subroutine

SCENES_DIR = Path("scenes")
DEFINITIONS = SCENES_DIR / "definitions.json"


def compiled_is_rendered(elem) -> bool:
    """The renderer's own skip rules applied to compiled element values."""
    if elem.w_bytes <= 0 or elem.h_lines <= 0:
        return False
    return 0 <= elem.dst_x_byte < GAME_VRAM_PITCH and 0 <= elem.dst_y < 92


def _compile(tmp_path: Path, scene_data: dict):
    scene_file = tmp_path / "clipping.json"
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")
    enemies, secrets = load_catalogues(DEFINITIONS, DEFINITIONS)
    return parse_scene_json(scene_file, enemies, secrets)


def _element(**overrides) -> dict:
    element = {
        "id": "element-001",
        "source": "tiles/trees.png",
        "source_rect": {"x": 0, "y": 4, "width": 40, "height": 30},
        "position": {"x": 0, "y": 0},
    }
    element.update(overrides)
    return element


def _scene(*elements) -> dict:
    return {
        "schema_version": 1,
        "scene": {"name": "Clipping Scene", "width": 160, "height": 96},
        "elements": list(elements),
    }


def test_element_starting_above_the_playfield_is_clipped_not_dropped(tmp_path: Path):
    """A negative y must advance the source pointer and shrink the extent (not skip the element)."""
    compiled = _compile(tmp_path, _scene(_element(position={"x": 0, "y": -6})))
    elem = compiled.elements[0]

    assert elem.dst_y == 0
    assert elem.src_y == 4 + 6      # skip the 6 source lines that would land off-screen
    assert elem.h_lines == 30 - 6
    assert compiled_is_rendered(elem)


def test_element_starting_left_of_the_playfield_drops_whole_byte_columns(tmp_path: Path):
    """A negative x must drop the byte-aligned columns that fall off the left edge."""
    compiled = _compile(tmp_path, _scene(_element(position={"x": -10, "y": 0})))
    elem = compiled.elements[0]

    assert elem.dst_x_byte == 0
    assert elem.src_x_byte == 0 + 10 // 4     # 2 whole 4-pixel columns dropped
    assert elem.w_bytes == (40 + 3) // 4 - 10 // 4
    assert compiled_is_rendered(elem)


def test_flipped_element_clipped_left_keeps_the_source_range_start(tmp_path: Path):
    """A flipped element is drawn from the high end, so clipping its left only shrinks the range."""
    compiled = _compile(
        tmp_path, _scene(_element(position={"x": -10, "y": 0}, flip_x=True))
    )
    elem = compiled.elements[0]

    assert elem.dst_x_byte == 0
    assert elem.src_x_byte == 0               # not advanced: the high source bytes are dropped
    assert elem.w_bytes == (40 + 3) // 4 - 10 // 4
    assert elem.flip_x is True
    assert compiled_is_rendered(elem)


def test_element_entirely_above_or_left_compiles_to_zero_extent(tmp_path: Path):
    """An element fully off the playfield must compile to a zero extent so the renderer skips it."""
    above = _compile(tmp_path, _scene(_element(position={"x": 0, "y": -30}))).elements[0]
    assert above.h_lines == 0
    assert above.dst_y == 0

    left = _compile(tmp_path, _scene(_element(position={"x": -60, "y": 0}))).elements[0]
    assert left.w_bytes == 0
    assert left.dst_x_byte == 0

    # Zero extent is exactly what render.asm tests with `beq @do_skip`
    assert not compiled_is_rendered(above)
    assert not compiled_is_rendered(left)


def test_compiled_geometry_matches_the_reference_model_for_game_scenes():
    """Every game scene element must compile to exactly the reference geometry (incl. clipping)."""
    enemies, secrets = load_catalogues(DEFINITIONS, DEFINITIONS)

    for scene_file in scene_files():
        scene = load_scene(scene_file)
        compiled = parse_scene_json(SCENES_DIR / scene_file, enemies, secrets)
        by_id = {elem.id: elem for elem in compiled.elements}
        assert set(by_id) == {elem["id"] for elem in scene["elements"]}

        for element in scene["elements"]:
            geometry = element_geometry(element)
            elem = by_id[element["id"]]
            assert (elem.dst_x_byte, elem.dst_y, elem.w_bytes, elem.h_lines) == element_dst_rect(element), (
                f"{scene_file}: {element['id']} compiled geometry differs from the reference model"
            )
            assert (elem.src_x_byte, elem.src_y) == (
                geometry["src_x_byte"],
                geometry["src_y"],
            ), f"{scene_file}: {element['id']} source pointer differs from the reference model"


def test_no_game_scene_element_is_silently_dropped():
    """Regression: elements placed above the playfield used to be skipped by the renderer."""
    for scene_file in scene_files():
        scene = load_scene(scene_file)
        for element in scene["elements"]:
            assert element_is_rendered(element), (
                f"{scene_file}: {element['id']} would not be drawn "
                f"(position {element['position']}, crop {element['source_rect']})"
            )


@pytest.mark.parametrize("scene_index", range(len(scene_files())))
def test_every_element_reaches_the_playfield_in_the_compiled_rom(scene_index: int):
    """End-to-end: rendering a scene must produce exactly the reference playfield image."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mpu.a = scene_index
    run_subroutine(mpu, labels["RENDER_SCENE_BACKGROUND"])

    scene_file = scene_files()[scene_index]
    scene = load_scene(scene_file)

    scene_lines = labels.get("SCENE_PLAYFIELD_LINES", 92)
    # Reference playfield: draw every element in z order, clipped exactly like render.asm
    expected = bytearray(GAME_VRAM_PITCH * scene_lines)
    for element in sorted(scene["elements"], key=lambda e: e.get("z_index", 0)):
        if not element_is_rendered(element):
            continue
        dst_x, dst_y, w_bytes, h_lines = element_dst_rect(element)
        if dst_y >= scene_lines:
            continue
        w_bytes = min(w_bytes, GAME_VRAM_PITCH - dst_x)
        h_lines = min(h_lines, scene_lines - dst_y)
        reference = element_reference_bytes(mem, labels, element)
        for row in range(h_lines):
            start = (dst_y + row) * GAME_VRAM_PITCH + dst_x
            # The renderer copies exactly w_bytes (clipped) bytes, so slice the reference row
            expected[start : start + w_bytes] = bytes(reference[row][:w_bytes])

    actual = bytes(mem[labels["GAME_VRAM"] : labels["GAME_VRAM"] + GAME_VRAM_PITCH * scene_lines])
    assert actual == bytes(expected), f"{scene_file}: rendered playfield differs from the reference"

    # Regression for elements placed above the playfield: the upper zone must not stay empty
    assert any(expected[:44 * GAME_VRAM_PITCH]), (
        f"{scene_file}: the upper zone is blank - its tileset is not being drawn"
    )
