"""Pytest test harness using py65 6502 emulation to verify playfield background rendering."""

from __future__ import annotations

from pathlib import Path
import re
import pytest
from py65.devices.mpu6502 import MPU

from tests.scene_expectations import scene_files
from tests.tile_expectations import (
    element_dst_rect,
    element_reference_bytes,
    load_scene,
    topmost_visible_element,
)


def parse_labels(lab_path: Path) -> dict[str, int]:
    """Parse MADS symbol table into dictionary of uppercase label -> address."""
    labels: dict[str, int] = {}
    pattern = re.compile(r"^[0-9a-fA-F]{2}\t([0-9a-fA-F]{4})\t([^\s]+)")
    for line in lab_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.match(line)
        if m:
            addr = int(m.group(1), 16)
            name = m.group(2).upper()
            labels[name] = addr
    return labels


def load_xex_into_memory(xex_path: Path, mem: bytearray) -> None:
    """Parse Atari DOS XEX segments and load payload directly into memory."""
    data = xex_path.read_bytes()
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0

    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4

        if start == 0xFFFF:
            if pos + 4 > len(data):
                break
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4

        size = end - start + 1
        if size <= 0 or pos + size > len(data):
            break

        mem[start : start + size] = data[pos : pos + size]
        pos += size


def run_subroutine(mpu: MPU, addr: int, max_steps: int = 500_000) -> None:
    """Execute a 6502 subroutine via JSR simulation until RTS."""
    mpu.sp = 0xFD
    # Push return address (RTS pulls address and increments by 1)
    mpu.stPushWord(0x0100 - 1)
    mpu.memory[0x0100] = 0x00  # Sentinel
    mpu.pc = addr
    steps = 0
    while mpu.pc != 0x0100 and steps < max_steps:
        mpu.step()
        steps += 1
    assert mpu.pc == 0x0100, (
        f"Subroutine at 0x{addr:04X} did not return within {max_steps} steps (PC=0x{mpu.pc:04X})"
    )


@pytest.fixture(scope="module")
def emu_state():
    xex_path = Path("call_of_the_wintermon.xex")
    lab_path = Path("gen/main.lab")
    if not xex_path.exists() or not lab_path.exists():
        pytest.skip("call_of_the_wintermon.xex or gen/main.lab not found. Run make all first.")

    mem = bytearray(65536)
    load_xex_into_memory(xex_path, mem)
    labels = parse_labels(lab_path)
    return mem, labels


def test_clear_game_vram(emu_state):
    base_mem, labels = emu_state
    mem = bytearray(base_mem)
    mpu = MPU(memory=mem)

    clear_proc = labels["CLEAR_GAME_VRAM"]
    game_vram = labels.get("GAME_VRAM", 0x3000)

    # Fill VRAM with 0xAA dirty pattern
    for i in range(3840):
        mem[game_vram + i] = 0xAA

    # Assert dirty
    assert mem[game_vram] == 0xAA
    assert mem[game_vram + 3839] == 0xAA

    run_subroutine(mpu, clear_proc)

    # Assert completely cleared
    for i in range(3840):
        assert mem[game_vram + i] == 0x00, f"Byte at offset {i} not cleared"


def test_flip_byte_2bpp_table(emu_state):
    mem, labels = emu_state
    flip_table = labels["FLIP_BYTE_2BPP"]

    # In ANTIC Mode E: 4 pixels of 2 bits each
    # Pixel 0 is bits 7..6, pixel 1 is bits 5..4, pixel 2 is bits 3..2, pixel 3 is bits 1..0
    # %11000000 (0xC0, pixel 0=3) should become %00000011 (0x03, pixel 3=3)
    assert mem[flip_table + 0xC0] == 0x03
    assert mem[flip_table + 0x03] == 0xC0
    # %00110000 (0x30, pixel 1=3) should become %00001100 (0x0C, pixel 2=3)
    assert mem[flip_table + 0x30] == 0x0C
    assert mem[flip_table + 0x0C] == 0x30
    # Identity for symmetric patterns: %00000000 -> %00000000, %11111111 -> %11111111
    assert mem[flip_table + 0x00] == 0x00
    assert mem[flip_table + 0xFF] == 0xFF


def test_render_forest_scene_background(emu_state):
    base_mem, labels = emu_state
    mem = bytearray(base_mem)
    mpu = MPU(memory=mem)

    render_proc = labels["RENDER_SCENE_BACKGROUND"]
    game_vram = labels.get("GAME_VRAM", 0x3000)
    forest_id = labels["SCENE_SC_01_FOREST_ID"]

    # Call render_scene_background with A = 0 (Forest)
    mpu.a = forest_id
    run_subroutine(mpu, render_proc)

    # 1. Palette must match the scene's primary tileset ROM entry (derived, Rule 05)
    primary_tileset = mem[labels["SCENE_PRIMARY_TILESET"] + forest_id]
    assert mem[labels["COLOR0"]] == mem[labels["TILESET_COLPF0"] + primary_tileset]
    assert mem[labels["COLOR1"]] == mem[labels["TILESET_COLPF1"] + primary_tileset]
    assert mem[labels["COLOR2"]] == mem[labels["TILESET_COLPF2"] + primary_tileset]
    assert mem[labels["COLOR4"]] == mem[labels["TILESET_COLBK"] + primary_tileset]

    # 2. Check active scene ID
    active_scene_id = labels["ACTIVE_SCENE_ID"]
    assert mem[active_scene_id] == forest_id

    # 3. Check VRAM contains rendered background graphics (not blank)
    vram_slice = mem[game_vram : game_vram + 3840]
    non_zero_count = sum(1 for b in vram_slice if b != 0)
    assert non_zero_count > 0, "scene background must not be blank"

    # 4. Byte-exact verification of the topmost scene element that fits on screen:
    #    read the source bitmap, pack it and compare against the rendered playfield
    scene = load_scene(scene_files()[forest_id])
    element = topmost_visible_element(scene)
    assert element is not None, "scene must contain a fully visible background element"
    dst_x, dst_y, w_bytes, h_lines = element_dst_rect(element)
    reference = element_reference_bytes(mem, labels, element)
    for row in range(h_lines):
        base = game_vram + (dst_y + row) * 40 + dst_x
        actual = list(mem[base : base + w_bytes])
        assert actual == reference[row], (
            f"element {element['id']} scanline {row} mismatch: "
            f"{actual} != {reference[row]}"
        )


def test_render_castle_scene_background(emu_state):
    base_mem, labels = emu_state
    mem = bytearray(base_mem)
    mpu = MPU(memory=mem)

    render_proc = labels["RENDER_SCENE_BACKGROUND"]
    game_vram = labels.get("GAME_VRAM", 0x3000)
    castle_id = labels["SCENE_SC_02_FOREST_CASTLE_ID"]

    # Call render_scene_background with A = 1 (Forest Castle)
    mpu.a = castle_id
    run_subroutine(mpu, render_proc)

    # 1. Palette must match the scene's primary tileset ROM entry (derived, Rule 05)
    primary_tileset = mem[labels["SCENE_PRIMARY_TILESET"] + castle_id]
    assert mem[labels["COLOR0"]] == mem[labels["TILESET_COLPF0"] + primary_tileset]
    assert mem[labels["COLOR1"]] == mem[labels["TILESET_COLPF1"] + primary_tileset]
    assert mem[labels["COLOR2"]] == mem[labels["TILESET_COLPF2"] + primary_tileset]
    assert mem[labels["COLOR4"]] == mem[labels["TILESET_COLBK"] + primary_tileset]

    # 2. Check active scene ID
    active_scene_id = labels["ACTIVE_SCENE_ID"]
    assert mem[active_scene_id] == castle_id

    # 3. Byte-exact verification of the topmost scene element that fits on screen
    #    (elements whose y is negative are skipped by the renderer entirely)
    scene = load_scene(scene_files()[castle_id])
    element = topmost_visible_element(scene)
    assert element is not None, "scene must contain a fully visible background element"
    dst_x, dst_y, w_bytes, h_lines = element_dst_rect(element)
    reference = element_reference_bytes(mem, labels, element)
    for row in range(h_lines):
        base = game_vram + (dst_y + row) * 40 + dst_x
        actual = list(mem[base : base + w_bytes])
        assert actual == reference[row], (
            f"element {element['id']} scanline {row} mismatch: "
            f"{actual} != {reference[row]}"
        )
