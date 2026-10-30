"""Unit tests for ANTIC Mode E tileset conversion and assembly data structures."""

from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from scripts.convert_tiles import (
    image_to_indexed_2bit,
    pack_antic_e_bytes,
    quantize_rgb_to_4colors,
    convert_tiles,
    DEFAULT_PALETTES,
)
from tests.tile_expectations import expected_tileset_metrics
from tests.scene_expectations import scene_files, scene_symbol


def test_pack_antic_e_bytes_exact_multiples() -> None:
    """Verify ANTIC Mode E bit packing for 4 pixels per byte."""
    # 1 scanline of 4 pixels: values 0, 1, 2, 3
    # pixel 0: bits 7..6 = 0
    # pixel 1: bits 5..4 = 1
    # pixel 2: bits 3..2 = 2
    # pixel 3: bits 1..0 = 3
    # Expected byte: (0 << 6) | (1 << 4) | (2 << 2) | 3 = 0x00 | 0x10 | 0x08 | 0x03 = 0x1B
    pixels = np.array([[0, 1, 2, 3]], dtype=np.uint8)
    packed = pack_antic_e_bytes(pixels)
    assert len(packed) == 1
    assert packed[0] == 0x1B


def test_pack_antic_e_bytes_all_colors() -> None:
    """Verify bit packing with solid color patterns."""
    # Color 0 solid (00 00 00 00) = 0x00
    p0 = np.zeros((1, 4), dtype=np.uint8)
    assert pack_antic_e_bytes(p0) == bytes([0x00])

    # Color 1 solid (01 01 01 01) = 0x55
    p1 = np.ones((1, 4), dtype=np.uint8)
    assert pack_antic_e_bytes(p1) == bytes([0x55])

    # Color 2 solid (10 10 10 10) = 0xAA
    p2 = np.full((1, 4), 2, dtype=np.uint8)
    assert pack_antic_e_bytes(p2) == bytes([0xAA])

    # Color 3 solid (11 11 11 11) = 0xFF
    p3 = np.full((1, 4), 3, dtype=np.uint8)
    assert pack_antic_e_bytes(p3) == bytes([0xFF])


def test_pack_antic_e_bytes_padding() -> None:
    """Verify padding when image width is not a multiple of 4."""
    # Width 5 -> 2 bytes per scanline: 4 pixels in byte 0, 1 pixel in byte 1 (padded with zeros)
    # [3, 2, 1, 0] -> (3<<6)|(2<<4)|(1<<2)|0 = 0xC0|0x20|0x04|0 = 0xE4
    # [2] -> (2<<6)|0|0|0 = 0x80
    pixels = np.array([[3, 2, 1, 0, 2]], dtype=np.uint8)
    packed = pack_antic_e_bytes(pixels)
    assert len(packed) == 2
    assert packed[0] == 0xE4
    assert packed[1] == 0x80


def test_quantize_rgb_to_4colors_black_and_shades() -> None:
    """Verify RGB clustering assigns 0 to background and sorts shades by luminance."""
    # Create synthetic RGB image with black background and 3 distinct brightness levels
    img_arr = np.zeros((10, 20, 3), dtype=np.uint8)
    img_arr[1:3, :] = [80, 10, 10]    # dark red
    img_arr[4:6, :] = [160, 20, 10]   # mid red
    img_arr[7:9, :] = [250, 120, 10]  # bright yellow-orange

    img = Image.fromarray(img_arr, mode="RGB")
    indexed = quantize_rgb_to_4colors(img)

    assert indexed.shape == (10, 20)
    # Background rows should be index 0
    assert np.all(indexed[0, :] == 0)
    assert np.all(indexed[9, :] == 0)
    # Dark red rows should be index 1
    assert np.all(indexed[1:3, :] == 1)
    # Mid red rows should be index 2
    assert np.all(indexed[4:6, :] == 2)
    # Bright rows should be index 3
    assert np.all(indexed[7:9, :] == 3)


def test_image_to_indexed_2bit_paletted() -> None:
    """Verify indexed mode P images are correctly processed into 0..3 range."""
    # Palette image with 4 colors
    img = Image.new("P", (8, 4))
    # Palette: 0:black, 1:dark green, 2:mid green, 3:light green
    palette = [0, 0, 0, 10, 80, 20, 20, 140, 40, 150, 220, 50] + [0] * (768 - 12)
    img.putpalette(palette)

    # Set some pixels
    data = [
        0, 1, 2, 3, 0, 1, 2, 3,
        1, 1, 2, 2, 3, 3, 0, 0,
        2, 2, 3, 3, 0, 0, 1, 1,
        3, 3, 0, 0, 1, 1, 2, 2,
    ]
    img.putdata(data)

    indexed = image_to_indexed_2bit(img)
    assert indexed.shape == (4, 8)
    assert list(indexed[0]) == [0, 1, 2, 3, 0, 1, 2, 3]


def test_convert_tiles_integration(tmp_path: Path) -> None:
    """Verify full convert_tiles run against the real tiles/ directory."""
    tiles_dir = Path("tiles")
    gen_dir = tmp_path / "gen"

    result = convert_tiles(tiles_dir, gen_dir)
    assert result == 0

    # Check generated files
    expected_files = [
        "tiles_castles.bin",
        "tiles_depths.bin",
        "tiles_hell.bin",
        "tiles_trees.bin",
        "tiles_data.asm",
    ]
    for ef in expected_files:
        p = gen_dir / ef
        assert p.is_file(), f"Expected {ef} to exist"
        assert p.stat().st_size > 0, f"Expected {ef} to be non-empty"

    # Verify binary sizes are exactly the packed source dimensions (derived, Rule 05)
    for metrics in expected_tileset_metrics():
        bin_path = gen_dir / f"tiles_{metrics['name']}.bin"
        assert bin_path.stat().st_size == metrics["size"], (
            f"{bin_path.name}: expected {metrics['size']} bytes "
            f"({metrics['w_bytes']} bytes/line x {metrics['h_lines']} lines) from {metrics['path']}"
        )

    # Verify ASM contents
    asm_content = (gen_dir / "tiles_data.asm").read_text(encoding="utf-8")
    assert "TILESET_CASTLES" in asm_content
    assert "TILESET_DEPTHS" in asm_content
    assert "TILESET_HELL" in asm_content
    assert "TILESET_TREES" in asm_content
    assert "tileset_w_px_lo" in asm_content
    assert "tileset_w_bytes" in asm_content
    assert "tiles_castles_row_lo" in asm_content
    assert "tiles_depths_row_lo" in asm_content
    assert "tiles_hell_row_lo" in asm_content
    assert "tiles_trees_row_lo" in asm_content


def test_compiled_xex_tiles_layout() -> None:
    """Verify compiled call_of_the_wintermon.xex contains the tileset segment below $C000."""
    xex_path = Path("call_of_the_wintermon.xex")
    assert xex_path.is_file()

    from scripts.check_memory import parse_xex_segments

    segments = parse_xex_segments(xex_path.read_bytes())
    # Locate the $8000 segment
    tiles_seg = next((s for s in segments if s[0] == 0x8000), None)
    assert tiles_seg is not None, "Segment starting at $8000 not found"

    start, end, size = tiles_seg
    expected_total = sum(metrics["size"] for metrics in expected_tileset_metrics())
    assert start == 0x8000
    assert size == expected_total, (
        f"tiles payload is {size} bytes, expected {expected_total} from the source PNGs"
    )
    assert end == 0x8000 + expected_total - 1
    assert end <= 0xBFFF, f"Tiles segment exceeds $BFFF limit: ${end:04X}"


def test_py65_tiles_metadata_and_tables() -> None:
    """Verify in py65 memory that the generated tiles metadata and row tables are accurate."""
    import re
    from py65.devices.mpu6502 import MPU

    lab_path = Path("gen/main.lab")
    assert lab_path.is_file(), "Symbol file gen/main.lab not found"

    labels: dict[str, int] = {}
    pattern = re.compile(r"^[0-9a-fA-F]{2}\t([0-9a-fA-F]{4})\t([^\s]+)")
    for line in lab_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.match(line)
        if m:
            labels[m.group(2).upper()] = int(m.group(1), 16)

    # Required symbols
    required = [
        "TILESET_W_BYTES",
        "TILESET_H_LINES",
        "TILESET_DATA_LO",
        "TILESET_DATA_HI",
        "TILES_CASTLES_DATA",
        "TILES_DEPTHS_DATA",
        "TILES_HELL_DATA",
        "TILES_TREES_DATA",
        "TILES_TREES_ROW_LO",
        "TILES_TREES_ROW_HI",
        "TILES_DEPTHS_ROW_LO",
        "TILES_DEPTHS_ROW_HI",
    ]
    for sym in required:
        assert sym in labels, f"Symbol {sym} missing from main.lab"

    # Load XEX into py65 memory
    mem = bytearray(0x10000)
    data = Path("call_of_the_wintermon.xex").read_bytes()
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0
    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4
        if start == 0xFFFF:
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4
        size = end - start + 1
        mem[start : start + size] = data[pos : pos + size]
        pos += size

    metrics = expected_tileset_metrics()

    # Width in bytes and height in lines must match the source PNGs (Rule 05)
    wb_addr = labels["TILESET_W_BYTES"]
    assert list(mem[wb_addr : wb_addr + len(metrics)]) == [m["w_bytes"] for m in metrics]

    h_addr = labels["TILESET_H_LINES"]
    assert list(mem[h_addr : h_addr + len(metrics)]) == [m["h_lines"] for m in metrics]

    # Verify data pointers in SoA table: emission order with cumulative sizes
    dlo_addr = labels["TILESET_DATA_LO"]
    dhi_addr = labels["TILESET_DATA_HI"]
    ptrs = [mem[dlo_addr + i] | (mem[dhi_addr + i] << 8) for i in range(len(metrics))]

    expected_ptrs: list[int] = []
    running = 0x8000
    for metrics_entry in metrics:
        expected_ptrs.append(running)
        running += metrics_entry["size"]
    assert ptrs == expected_ptrs

    for metrics_entry, ptr in zip(metrics, ptrs):
        assert ptr == labels[f"TILES_{metrics_entry['name'].upper()}_DATA"]

    # Row offset tables: line y must map to y * stride for every tileset
    for metrics_entry in metrics:
        row_lo = labels[f"TILES_{metrics_entry['name'].upper()}_ROW_LO"]
        row_hi = labels[f"TILES_{metrics_entry['name'].upper()}_ROW_HI"]
        for line in (0, 1, metrics_entry["h_lines"] // 2, metrics_entry["h_lines"] - 1):
            offset = mem[row_lo + line] | (mem[row_hi + line] << 8)
            assert offset == line * metrics_entry["w_bytes"], (
                f"{metrics_entry['name']} row {line}: expected "
                f"{line * metrics_entry['w_bytes']}, got {offset}"
            )


def test_gameplay_vram_and_pmg_reservation() -> None:
    """Verify memory reservation and alignment for Mode E playfield and PMG."""
    import re
    from py65.devices.mpu6502 import MPU

    lab_path = Path("gen/main.lab")
    assert lab_path.is_file()

    labels: dict[str, int] = {}
    pattern = re.compile(r"^[0-9a-fA-F]{2}\t([0-9a-fA-F]{4})\t([^\s]+)")
    for line in lab_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.match(line)
        if m:
            labels[m.group(2).upper()] = int(m.group(1), 16)

    # 1. Verify addresses and hardware alignment
    assert labels["GAME_VRAM"] == 0x3000
    assert labels["GAME_VRAM"] % 0x1000 == 0, "GAME_VRAM must be 4 KB aligned"
    assert labels["GAME_VRAM_BUF"] == 0x3000

    assert labels["GAME_DLIST"] == 0x3F60
    assert labels["DLIST_GAME"] == 0x3F60
    assert labels["GAME_DLIST"] % 0x0400 == 0 or labels["GAME_DLIST"] >= 0x3C00, "GAME_DLIST must not cross 1 KB"

    assert labels["PMG_ADDR"] == 0x6800
    assert labels["PMG_ADDR"] % 0x0800 == 0, "PMG_ADDR must be 2 KB aligned for single-line resolution"
    assert labels["PMBASE_PAGE"] == 0x68

    # 2. Load binary and verify display list structure
    mem = bytearray(0x10000)
    data = Path("call_of_the_wintermon.xex").read_bytes()
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0
    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4
        if start == 0xFFFF:
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4
        size = end - start + 1
        mem[start : start + size] = data[pos : pos + size]
        pos += size

    # Inspect dlist_game:
    # Bytes 0..2: 3x DL_BLANK8 ($70)
    dl_addr = labels["DLIST_GAME"]
    assert list(mem[dl_addr : dl_addr + 3]) == [0x70, 0x70, 0x70]

    # Byte 3: DL_MODE_D | DL_LMS ($0D | $40 = $4D)
    assert mem[dl_addr + 3] == 0x4D

    # Bytes 4..5: LMS target address ($3000)
    lms_target = mem[dl_addr + 4] | (mem[dl_addr + 5] << 8)
    assert lms_target == 0x3000

    # Remaining 91 scene lines of mode D ($0D), with DL_DLI ($8D) on lines 6, 22, 38, 54, 70, 86
    dli_indices = {5, 21, 37, 53, 69, 85}
    for i in range(91):
        expected = 0x8D if i in dli_indices else 0x0D
        assert mem[dl_addr + 6 + i] == expected, f"Mode D line {i+1} mismatch: expected {expected:#x}, got {mem[dl_addr + 6 + i]:#x}"

    # Margin before HUD (8 blank scanlines + DLI):
    assert mem[dl_addr + 97] == 0xF0  # DL_BLANK8 | DL_DLI
    # HUD Line 0: Mode D with LMS to HUD_VRAM
    assert mem[dl_addr + 98] == 0x4D  # DL_MODE_D | DL_LMS
    hud_target = mem[dl_addr + 99] | (mem[dl_addr + 100] << 8)
    assert hud_target == labels["HUD_VRAM"]
    # Remaining 7 lines of HUD Mode D
    for i in range(7):
        assert mem[dl_addr + 101 + i] == 0x0D
    # Margin after HUD (8 blank scanlines + DLI to restore normal width):
    assert mem[dl_addr + 108] == 0xF0  # DL_BLANK8 | DL_DLI

    # JVB instruction ($41) pointing to dlist_game
    assert mem[dl_addr + 109] == 0x41
    jvb_target = mem[dl_addr + 110] | (mem[dl_addr + 111] << 8)
    assert jvb_target == dl_addr

    # 3. Simulate game_init with py65
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    # Push dummy return address
    mem[0x01FE] = 0x1F
    mem[0x01FD] = 0xFF

    mpu.pc = labels["GAME_INIT"]
    steps = 0
    while mpu.pc != 0x2000 and steps < 50_000:
        mpu.step()
        steps += 1

    # Verify game_init sets PMBASE to $68
    assert mem[labels["PMBASE"]] == 0x68
    # Verify SDLSTL points to dlist_scene_title for initial scene title card
    sdlst = mem[labels["SDLSTL"]] | (mem[labels["SDLSTH"]] << 8)
    assert sdlst == labels["DLIST_SCENE_TITLE"]
    # Verify title card LMS points to the first scene's name line (centered screencodes)
    title_lms = mem[labels["DLIST_SCENE_TITLE_ADDR"]] | (mem[labels["DLIST_SCENE_TITLE_ADDR"] + 1] << 8)
    first_scene_symbol = scene_symbol(scene_files()[0]).upper()
    assert title_lms == labels[f"SCENE_{first_scene_symbol}_NAME_LINE"]



