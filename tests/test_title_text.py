"""Unit and py65 emulation tests for procedural 2bpp title text generator and Display List."""

from __future__ import annotations

import json
import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

# ANTIC Constants
DL_BLANK1 = 0x00
DL_BLANK2 = 0x10
DL_BLANK3 = 0x20
DL_BLANK4 = 0x30
DL_BLANK5 = 0x40
DL_BLANK6 = 0x50
DL_BLANK7 = 0x60
DL_BLANK8 = 0x70

DL_MODE_2 = 0x02
DL_MODE_D = 0x0D
DL_MODE_E = 0x0E

DL_HSCROL = 0x10
DL_VSCROL = 0x20
DL_LMS = 0x40
DL_DLI = 0x80
DL_JVB = 0x41


def parse_labels(lab_path: Path) -> dict[str, int]:
    """Parse MADS symbol table (.lab) into dictionary of UPPERCASE label -> address."""
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
    """Parse Atari DOS XEX segments and load payload into memory."""
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


def run_subroutine(mpu: MPU, addr: int, max_steps: int = 100_000) -> None:
    """Execute a 6502 subroutine via JSR simulation until RTS."""
    mpu.sp = 0xFD
    mpu.stPushWord(0x0100 - 1)
    mpu.memory[0x0100] = 0x00
    mpu.pc = addr
    steps = 0
    while mpu.pc != 0x0100 and steps < max_steps:
        mpu.step()
        steps += 1
    assert mpu.pc == 0x0100, f"Subroutine at 0x{addr:04X} timed out (PC=0x{mpu.pc:04X})"


@pytest.fixture
def emu_env():
    xex_file = Path("call_of_the_wintermon.xex")
    lab_file = Path("gen/main.lab")
    assert xex_file.exists(), "Binary not found. Run 'make all' first."
    assert lab_file.exists(), "Symbol file not found. Run 'make all' first."

    mem = bytearray(65536)
    load_xex_into_memory(xex_file, mem)
    labels = parse_labels(lab_file)
    mpu = MPU(memory=mem)
    return mpu, labels


# --- Python Independent Reference Implementations ---


def conv(b: int) -> tuple[int, int]:
    """Convert 1 byte of 1bpp font data to two 2bpp bytes (2+4+2 mapping: 10, 11, 01)."""
    px = []
    for i in range(8):                  # i = 0 -> bit 7
        if not (b >> (7 - i)) & 1:
            px.append(0b00)
        elif i < 2:
            px.append(0b10)
        elif i < 6:
            px.append(0b11)
        else:
            px.append(0b01)
    left = (px[0] << 6) | (px[1] << 4) | (px[2] << 2) | px[3]
    right = (px[4] << 6) | (px[5] << 4) | (px[6] << 2) | px[7]
    return left, right


def convert_byte_to_2bpp(b: int) -> tuple[int, int]:
    return conv(b)


def render_text_reference(font_bytes: bytes, codes: list[int], x_offset: int, pitch: int = 40) -> bytearray:
    """Render text into 8x40 byte buffer using independent reference algorithm."""
    buf = bytearray(8 * pitch)
    for i, code in enumerate(codes):
        glyph_base = code * 8
        col = x_offset + i * 2
        for row in range(8):
            src_byte = font_bytes[glyph_base + row]
            left, right = convert_byte_to_2bpp(src_byte)
            buf[row * pitch + col] = left
            buf[row * pitch + col + 1] = right
    return buf


# ==============================================================================
# 1. Generator and Font Tests
# ==============================================================================


def test_font_matches_font_file(emu_env):
    """Verify that fonts/font.fnt and memory at $2400 (INTRO_FONT) are byte-for-byte identical."""
    mpu, labels = emu_env
    font_file = Path("fonts/font.fnt")
    assert font_file.is_file()
    font_bytes = font_file.read_bytes()
    assert len(font_bytes) == 1024

    font_addr = labels["INTRO_FONT"]
    mem_font = bytes(mpu.memory[font_addr : font_addr + 1024])
    assert mem_font == font_bytes, "Memory font at $2400 does not match fonts/font.fnt"


def test_conversion_lut_and_test_vectors(emu_env):
    """Verify test vectors, 256-value reference match, and 16-byte LUT tables in memory."""
    mpu, labels = emu_env

    # 1. Test vectors
    assert convert_byte_to_2bpp(0x00) == (0x00, 0x00)
    assert convert_byte_to_2bpp(0xFF) == (0xAF, 0xF5)
    assert convert_byte_to_2bpp(0xC0) == (0xA0, 0x00)
    assert convert_byte_to_2bpp(0x30) == (0x0F, 0x00)
    assert convert_byte_to_2bpp(0x0C) == (0x00, 0xF0)
    assert convert_byte_to_2bpp(0x03) == (0x00, 0x05)
    assert convert_byte_to_2bpp(0x3C) == (0x0F, 0xF0)
    assert convert_byte_to_2bpp(0x81) == (0x80, 0x01)
    assert convert_byte_to_2bpp(0x9A) == (0x83, 0xC4)

    # 2. Check reference generation of LUT tables
    expected_hi = [
        0x00, 0x03, 0x0C, 0x0F, 0x20, 0x23, 0x2C, 0x2F,
        0x80, 0x83, 0x8C, 0x8F, 0xA0, 0xA3, 0xAC, 0xAF,
    ]
    expected_lo = [
        0x00, 0x01, 0x04, 0x05, 0x30, 0x31, 0x34, 0x35,
        0xC0, 0xC1, 0xC4, 0xC5, 0xF0, 0xF1, 0xF4, 0xF5,
    ]

    for b in range(256):
        assert (expected_hi[b >> 4], expected_lo[b & 0x0F]) == conv(b)

    # 3. Compare tables in 6502 memory
    lut_hi_addr = labels.get("TITLE_TEXT_LUT_HI", labels["TITLE_TEXT_LUT"])
    lut_lo_addr = labels["TITLE_TEXT_LUT_LO"]

    mem_lut_hi = [mpu.memory[lut_hi_addr + i] for i in range(16)]
    mem_lut_lo = [mpu.memory[lut_lo_addr + i] for i in range(16)]

    assert mem_lut_hi == expected_hi
    assert mem_lut_lo == expected_lo

    # 4. Compare all 256 combinations in memory against conv(b)
    for b in range(256):
        assert (mem_lut_hi[b >> 4], mem_lut_lo[b & 0x0F]) == conv(b)


# Polish diacritics mapping for Atari 8-bit custom font
POLISH_CHARS: dict[str, int] = {
    "Ą": 65, "Ć": 66, "Ę": 67, "Ł": 68, "Ń": 69, "Ó": 70, "Ś": 71, "Ź": 72, "Ż": 73,
    "ą": 81, "ć": 82, "ę": 83, "ł": 84, "ń": 85, "ó": 86, "ś": 87, "ź": 88, "ż": 89,
}


def char_to_screencode(c: str) -> int:
    """Convert Unicode character to Atari ANTIC internal screen code (0..127)."""
    if c in POLISH_CHARS:
        return POLISH_CHARS[c]
    val = ord(c)
    if 32 <= val <= 95:
        return val - 32
    if 96 <= val <= 127:
        return val
    if 0 <= val <= 31:
        return val + 64
    return 0


def load_title_lines() -> list[dict[str, object]]:
    """Load texts/title.txt and return parsed lines with lengths, offsets, and screen codes."""
    title_path = Path("texts/title.txt")
    lines = [line.rstrip("\r\n") for line in title_path.read_text(encoding="utf-8").splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    assert len(lines) == 3, f"Expected 3 title lines in texts/title.txt, got {len(lines)}"

    result = []
    for line in lines:
        length = len(line)
        offset = (40 - length * 2) // 2
        codes = [char_to_screencode(c) for c in line]
        result.append({"text": line, "len": length, "offset": offset, "codes": codes})
    return result


def test_screen_codes_and_lengths(emu_env):
    """Verify title screen code tables and character counts in memory match texts/title.txt."""
    mpu, labels = emu_env
    title_data = load_title_lines()

    addrs = [
        labels["TITLE_TEXT_CALL_CODES"],
        labels["TITLE_TEXT_OF_THE_CODES"],
        labels["TITLE_TEXT_WINTERMOON_CODES"],
    ]

    for item, addr in zip(title_data, addrs):
        codes = item["codes"]
        assert [mpu.memory[addr + i] for i in range(len(codes))] == codes


def test_title_generated_text_matches_reference_model(emu_env):
    """Execute title_init and verify generated VRAM buffers match the Python reference model."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    font_file = Path("fonts/font.fnt")
    font_bytes = font_file.read_bytes()

    title_data = load_title_lines()
    buffer_addrs = [
        labels["TITLE_TEXT_CALL"],
        labels["TITLE_TEXT_OF_THE"],
        labels["TITLE_TEXT_WINTERMOON"],
    ]

    for item, buf_addr in zip(title_data, buffer_addrs):
        ref = render_text_reference(font_bytes, item["codes"], x_offset=item["offset"])
        actual = bytes(mpu.memory[buf_addr : buf_addr + 320])
        assert actual == bytes(ref), f"Buffer for '{item['text']}' does not match reference model"


def test_pixel_patterns_and_structural_bands(emu_env):
    """Verify byte pairs have valid structural pixel bands:
    Left byte: px 0-1 in {00, 10}, px 2-3 in {00, 11}.
    Right byte: px 4-5 in {00, 11}, px 6-7 in {00, 01}.
    """
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    title_data = load_title_lines()
    buffers = [
        (labels["TITLE_TEXT_CALL"], title_data[0]["offset"], title_data[0]["len"]),
        (labels["TITLE_TEXT_OF_THE"], title_data[1]["offset"], title_data[1]["len"]),
        (labels["TITLE_TEXT_WINTERMOON"], title_data[2]["offset"], title_data[2]["len"]),
    ]

    for base, x_offset, char_count in buffers:
        # Check glyph area byte pairs
        for row in range(8):
            row_base = base + row * 40
            for i in range(char_count):
                b_left = mpu.memory[row_base + x_offset + i * 2]
                b_right = mpu.memory[row_base + x_offset + i * 2 + 1]

                px0 = (b_left >> 6) & 0x03
                px1 = (b_left >> 4) & 0x03
                px2 = (b_left >> 2) & 0x03
                px3 = b_left & 0x03

                assert px0 in (0, 2), f"px0 ({px0:02b}) invalid in left byte 0x{b_left:02X}"
                assert px1 in (0, 2), f"px1 ({px1:02b}) invalid in left byte 0x{b_left:02X}"
                assert px2 in (0, 3), f"px2 ({px2:02b}) invalid in left byte 0x{b_left:02X}"
                assert px3 in (0, 3), f"px3 ({px3:02b}) invalid in left byte 0x{b_left:02X}"

                px4 = (b_right >> 6) & 0x03
                px5 = (b_right >> 4) & 0x03
                px6 = (b_right >> 2) & 0x03
                px7 = b_right & 0x03

                assert px4 in (0, 3), f"px4 ({px4:02b}) invalid in right byte 0x{b_right:02X}"
                assert px5 in (0, 3), f"px5 ({px5:02b}) invalid in right byte 0x{b_right:02X}"
                assert px6 in (0, 1), f"px6 ({px6:02b}) invalid in right byte 0x{b_right:02X}"
                assert px7 in (0, 1), f"px7 ({px7:02b}) invalid in right byte 0x{b_right:02X}"


# ==============================================================================
# 2. Centering, Boundaries and Sentinel Tests
# ==============================================================================


def test_text_centering_and_row_margins(emu_env):
    """Verify absolute placement, character width, and clean zero margins on every row."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])
    mem = mpu.memory
    font_bytes = Path("fonts/font.fnt").read_bytes()

    title_data = load_title_lines()
    checks = [
        (labels["TITLE_TEXT_CALL"], title_data[0]["offset"], title_data[0]["len"] * 2, title_data[0]["codes"]),
        (labels["TITLE_TEXT_OF_THE"], title_data[1]["offset"], title_data[1]["len"] * 2, title_data[1]["codes"]),
        (labels["TITLE_TEXT_WINTERMOON"], title_data[2]["offset"], title_data[2]["len"] * 2, title_data[2]["codes"]),
    ]

    for base, x_offset, width, codes in checks:
        expected_buf = render_text_reference(font_bytes, codes, x_offset=x_offset)
        for row in range(8):
            row_base = base + row * 40
            expected_row = expected_buf[row * 40 + x_offset : row * 40 + x_offset + width]

            # Text content placement
            assert bytes(mem[row_base + x_offset : row_base + x_offset + width]) == bytes(expected_row)

            # Left margin zero check
            if x_offset > 0:
                assert mem[row_base + x_offset - 1] == 0x00
                assert all(mem[row_base + col] == 0x00 for col in range(x_offset))

            # Right margin zero check
            if x_offset + width < 40:
                assert mem[row_base + x_offset + width] == 0x00
                assert all(mem[row_base + col] == 0x00 for col in range(x_offset + width, 40))


def test_clearing_bounds_and_sentinels(emu_env):
    """Verify that title_init clears exactly 2,240 bytes ($3000-$38BF) and does not touch $38C0+."""
    mpu, labels = emu_env

    # Fill sentinels
    mpu.memory[0x2FFE] = 0xAA
    mpu.memory[0x2FFF] = 0x55
    for addr in range(0x38C0, 0x3900):
        mpu.memory[addr] = 0xEE

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Sentinels before $3000
    assert mpu.memory[0x2FFE] == 0xAA
    assert mpu.memory[0x2FFF] == 0x55

    # Sentinels at $38C0 and beyond must remain completely untouched
    for addr in range(0x38C0, 0x3900):
        assert mpu.memory[addr] == 0xEE, f"Memory corrupted at 0x{addr:04X}"


def test_logo_codes_and_generation(emu_env):
    """Verify Atari logo codes table, reference rendering of 1280B buffer, centering, and margins."""
    mpu, labels = emu_env

    # Load logo codes dynamically from title/title.json
    json_path = Path("title/title.json")
    with open(json_path, "r", encoding="utf-8") as f:
        logo_data = json.load(f)
    logo_lines = logo_data["logo"]["codes"]

    # 1. Verify title_logo_codes table in memory
    codes_addr = labels["TITLE_LOGO_CODES"]
    expected_flat = [c for line in logo_lines for c in line]
    mem_codes = [mpu.memory[codes_addr + i] for i in range(20)]
    assert mem_codes == expected_flat, "title_logo_codes memory table does not match specification"

    # 2. Run title_init to populate buffers
    run_subroutine(mpu, labels["TITLE_INIT"])

    font_file = Path("fonts/font.fnt")
    font_bytes = font_file.read_bytes()

    logo_base = labels["TITLE_TEXT_LOGO"]
    assert logo_base == labels["GAME_VRAM"] + 0x03C0

    # 3. Verify byte-by-byte match with independent Python reference
    for k, line_codes in enumerate(logo_lines):
        line_ref = render_text_reference(font_bytes, line_codes, x_offset=15)
        actual_line = bytes(mpu.memory[logo_base + k * 320 : logo_base + (k + 1) * 320])
        assert actual_line == bytes(line_ref), f"Logo line {k} does not match reference model"

    # 4. Centering & margin check for all 32 display rows
    for r in range(32):
        row_base = logo_base + r * 40
        # Left margin (15 bytes)
        assert all(mpu.memory[row_base + i] == 0x00 for i in range(15)), f"Row {r} left margin non-zero"
        # Right margin (15 bytes: cols 25..39)
        assert all(mpu.memory[row_base + i] == 0x00 for i in range(25, 40)), f"Row {r} right margin non-zero"

    # 5. Space character (code 0) zero verification
    for k, line_codes in enumerate(logo_lines):
        for c, code in enumerate(line_codes):
            if code == 0:
                col_start = 15 + c * 2
                for r in range(k * 8, (k + 1) * 8):
                    row_base = logo_base + r * 40
                    assert mpu.memory[row_base + col_start] == 0x00 and mpu.memory[row_base + col_start + 1] == 0x00


def test_generator_validation_rejects_invalid_parameters(emu_env):
    """Verify that title_text_generate sets Carry flag and makes zero memory writes on invalid input."""
    mpu, labels = emu_env

    dst_addr = labels["TITLE_TEXT_CALL"]
    # Poison destination buffer
    for i in range(320):
        mpu.memory[dst_addr + i] = 0x77

    def setup_gen_call(len_val: int, x_val: int):
        mpu.memory[labels["TITLE_GEN_CHARSET"]] = labels["INTRO_FONT"] & 0xFF
        mpu.memory[labels["TITLE_GEN_CHARSET"] + 1] = labels["INTRO_FONT"] >> 8
        mpu.memory[labels["TITLE_GEN_TEXT"]] = labels["TITLE_TEXT_CALL_CODES"] & 0xFF
        mpu.memory[labels["TITLE_GEN_TEXT"] + 1] = labels["TITLE_TEXT_CALL_CODES"] >> 8
        mpu.memory[labels["TITLE_GEN_DST"]] = dst_addr & 0xFF
        mpu.memory[labels["TITLE_GEN_DST"] + 1] = dst_addr >> 8
        mpu.memory[labels["TITLE_GEN_LEN"]] = len_val
        mpu.memory[labels["TITLE_GEN_X"]] = x_val

    invalid_cases = [
        (2, 39),   # x_offset = 39, length = 2 (exceeds row boundary: 39 + 4 = 43)
        (0, 10),   # length = 0
        (4, 40),   # x_offset = 40 (>= 40)
        (21, 0),   # length = 21 (> 20)
        (130, 0),  # length = 130 (checks 8-bit overflow prevention: 2 * 130 = 260)
    ]

    for len_val, x_val in invalid_cases:
        setup_gen_call(len_val, x_val)
        run_subroutine(mpu, labels["TITLE_TEXT_GENERATE"])
        assert (mpu.p & 0x01) == 0x01, f"Carry not set for len={len_val}, x={x_val}"
        # Buffer must remain untouched
        assert all(mpu.memory[dst_addr + i] == 0x77 for i in range(320))


def test_generator_validation_accepts_valid_boundary_parameters(emu_env):
    """Verify that title_text_generate clears Carry flag and succeeds on exact boundary cases."""
    mpu, labels = emu_env
    dst_addr = labels["TITLE_TEXT_CALL"]

    def call_generator(len_val: int, x_val: int):
        # Clear buffer
        for i in range(320):
            mpu.memory[dst_addr + i] = 0x00
        mpu.memory[labels["TITLE_GEN_CHARSET"]] = labels["INTRO_FONT"] & 0xFF
        mpu.memory[labels["TITLE_GEN_CHARSET"] + 1] = labels["INTRO_FONT"] >> 8
        mpu.memory[labels["TITLE_GEN_TEXT"]] = labels["TITLE_TEXT_WINTERMOON_CODES"] & 0xFF
        mpu.memory[labels["TITLE_GEN_TEXT"] + 1] = labels["TITLE_TEXT_WINTERMOON_CODES"] >> 8
        mpu.memory[labels["TITLE_GEN_DST"]] = dst_addr & 0xFF
        mpu.memory[labels["TITLE_GEN_DST"] + 1] = dst_addr >> 8
        mpu.memory[labels["TITLE_GEN_LEN"]] = len_val
        mpu.memory[labels["TITLE_GEN_X"]] = x_val
        run_subroutine(mpu, labels["TITLE_TEXT_GENERATE"])

    # Boundary 1: max length 20 at offset 0 (20 * 2 = 40)
    call_generator(20, 0)
    assert (mpu.p & 0x01) == 0x00, "Carry was unexpectedly set for len=20, x=0"

    # Boundary 2: min length 1 at offset 38 (38 + 2 = 40)
    call_generator(1, 38)
    assert (mpu.p & 0x01) == 0x00, "Carry was unexpectedly set for len=1, x=38"


# ==============================================================================
# 3. Display List Structure & LMS Tests
# ==============================================================================


def test_dlist_title_exact_instruction_sequence_and_height(emu_env):
    """Verify exact sequence of instructions, LMS addresses, scanline height (199) and size (122B)."""
    mpu, labels = emu_env

    dlist_addr = labels["DLIST_TITLE"]
    mem = mpu.memory

    pc = dlist_addr
    total_scanlines = 0

    # 1. 2x DL_BLANK8 + 1x (DL_BLANK8 | DL_DLI) = 24 scanlines
    assert mem[pc] == DL_BLANK8
    pc += 1
    total_scanlines += 8

    assert mem[pc] == DL_BLANK8
    pc += 1
    total_scanlines += 8

    assert mem[pc] == (DL_BLANK8 | DL_DLI)
    pc += 1
    total_scanlines += 8

    # 2. CALL: Mode E with LMS, then 7x Mode E = 8 scanlines
    assert mem[pc] == (DL_MODE_E | DL_LMS)
    pc += 1
    call_addr = mem[pc] | (mem[pc + 1] << 8)
    pc += 2
    assert call_addr == labels["TITLE_TEXT_CALL"]
    total_scanlines += 1  # ANTIC E = 1 scanline/line

    for _ in range(7):
        assert mem[pc] == DL_MODE_E
        pc += 1
        total_scanlines += 1

    # 3. Spacing: 1x (DL_BLANK8 | DL_DLI) = 8 scanlines
    assert mem[pc] == (DL_BLANK8 | DL_DLI)
    pc += 1
    total_scanlines += 8

    # 4. OF THE: Mode D with LMS, then 7x Mode D = 16 scanlines
    assert mem[pc] == (DL_MODE_D | DL_LMS)
    pc += 1
    of_the_addr = mem[pc] | (mem[pc + 1] << 8)
    pc += 2
    assert of_the_addr == labels["TITLE_TEXT_OF_THE"]
    total_scanlines += 2  # ANTIC D = 2 scanlines/line

    for _ in range(7):
        assert mem[pc] == DL_MODE_D
        pc += 1
        total_scanlines += 2

    # 5. Spacing: 1x (DL_BLANK8 | DL_DLI) = 8 scanlines
    assert mem[pc] == (DL_BLANK8 | DL_DLI)
    pc += 1
    total_scanlines += 8

    # 6. WINTERMOON: 16x (Mode D | LMS) = 32 scanlines
    winter_base = labels["TITLE_TEXT_WINTERMOON"]
    expected_offsets = [0, 0, 40, 40, 80, 80, 120, 120, 160, 160, 200, 200, 240, 240, 280, 280]

    for idx, exp_off in enumerate(expected_offsets):
        assert mem[pc] == (DL_MODE_D | DL_LMS), f"WINTERMOON line {idx} missing LMS"
        pc += 1
        line_addr = mem[pc] | (mem[pc + 1] << 8)
        pc += 2
        assert line_addr == winter_base + exp_off, f"WINTERMOON line {idx} wrong LMS address"
        total_scanlines += 2

    assert total_scanlines == 96, f"Text block total scanlines must be 96, got {total_scanlines}"

    # 7. Spacing before Logo: 1x (DL_BLANK8 | DL_DLI) = 8 scanlines
    assert mem[pc] == (DL_BLANK8 | DL_DLI)
    pc += 1
    total_scanlines += 8

    # 8. Logo: Mode D with LMS (title_text_logo), then 31x Mode D = 64 scanlines
    assert mem[pc] == (DL_MODE_D | DL_LMS)
    pc += 1
    logo_addr = mem[pc] | (mem[pc + 1] << 8)
    pc += 2
    assert logo_addr == labels["TITLE_TEXT_LOGO"]
    total_scanlines += 2

    for _ in range(31):
        assert mem[pc] == DL_MODE_D
        pc += 1
        total_scanlines += 2

    # 9. Spacing margin between logo and scroll: 1x DL_BLANK8 = 8 scanlines
    assert mem[pc] == DL_BLANK8
    pc += 1
    total_scanlines += 8

    assert total_scanlines == 176, f"Scanlines before scroll prolog must be 176, got {total_scanlines}"

    # 10. DLI Prolog: 3 blank scanlines
    assert mem[pc] == DL_BLANK1
    pc += 1
    total_scanlines += 1

    assert mem[pc] == (DL_BLANK1 | DL_DLI)
    pc += 1
    total_scanlines += 1

    assert mem[pc] == DL_BLANK1
    pc += 1
    total_scanlines += 1

    assert total_scanlines == 179, f"Mode 2 must start at scanline 179, got {total_scanlines}"

    # 11. Vertical scroll window: 1 line with DL_VSCROL + 1 buffer line without DL_VSCROL = 9 scanlines
    assert mem[pc] == (DL_MODE_2 | DL_LMS | DL_VSCROL)
    pc += 1
    vs_addr = mem[pc] | (mem[pc + 1] << 8)
    pc += 2
    assert vs_addr == labels["TITLE_VS_BUF"]
    assert mem[pc] == DL_MODE_2
    pc += 1
    total_scanlines += 9

    # 12. Tail (12 scanlines) copied directly from original DL
    assert mem[pc] == DL_BLANK1
    pc += 1
    total_scanlines += 1

    assert mem[pc] == DL_BLANK8
    pc += 1
    total_scanlines += 8

    assert mem[pc] == DL_BLANK3
    pc += 1
    total_scanlines += 3

    # 13. End of display list: JVB to dlist_title
    assert mem[pc] == DL_JVB
    pc += 1
    jvb_target = mem[pc] | (mem[pc + 1] << 8)
    pc += 2
    assert jvb_target == dlist_addr

    # Verifications
    assert total_scanlines == 200, f"Total Display List scanlines must be 200, got {total_scanlines}"
    dl_size = pc - dlist_addr
    assert dl_size == 122, f"Display list size must be exactly 122 bytes, got {dl_size}"
    assert pc <= labels["DLI_BUFFERS"], "Display list exceeds into DLI_BUFFERS segment"


def test_dlist_title_exactly_five_dli_bits(emu_env):
    """Verify that exactly 5 instructions in dlist_title have DL_DLI ($80) bit set."""
    mpu, labels = emu_env
    dlist_addr = labels["DLIST_TITLE"]
    mem = mpu.memory

    dli_offsets = []
    pc = dlist_addr
    # Parse instructions in display list
    while pc < dlist_addr + 121:
        inst = mem[pc]
        offset = pc - dlist_addr
        if inst & DL_DLI:
            dli_offsets.append((offset, inst))
        # Advance pc according to instruction
        mode = inst & 0x0F
        if mode == 0x00:       # Blank lines (DL_BLANK1..8): 1 byte
            pc += 1
        elif mode == 0x01:     # JMP / JVB: 3 bytes
            pc += 3
        else:                  # Playfield modes (2..F): 3 bytes if LMS, else 1 byte
            if inst & DL_LMS:
                pc += 3
            else:
                pc += 1

    assert len(dli_offsets) == 5, f"Expected exactly 5 DLI instructions in dlist_title, got {len(dli_offsets)}: {dli_offsets}"
    expected_dli = [
        (2, DL_BLANK8 | DL_DLI),    # Blank line 3 before CALL
        (13, DL_BLANK8 | DL_DLI),   # Spacing blank line before OF THE
        (24, DL_BLANK8 | DL_DLI),   # Spacing blank line before WINTERMOON
        (73, DL_BLANK8 | DL_DLI),   # Spacing blank line before LOGO
        (110, DL_BLANK1 | DL_DLI),  # Scroll prolog blank line
    ]
    assert dli_offsets == expected_dli


# ==============================================================================
# 4. DMA, System Registers and Title Init State
# ==============================================================================


def test_title_init_hardware_and_shadow_registers(emu_env):
    """Verify hardware registers, shadow registers and pointers initialized by title_init."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Normal playfield DMA ($22)
    assert mpu.memory[labels["SDMCTL"]] == 0x22
    assert mpu.memory[labels["DMACTL"]] == 0x22

    # Display List pointers
    dlist_target = mpu.memory[labels["SDLSTL"]] | (mpu.memory[labels["SDLSTH"]] << 8)
    assert dlist_target == labels["DLIST_TITLE"]
    hw_dlist = mpu.memory[labels["DLISTL"]] | (mpu.memory[labels["DLISTH"]] << 8)
    assert hw_dlist == labels["DLIST_TITLE"]

    # Font page ($24)
    assert mpu.memory[labels["CHBAS"]] == labels["INTRO_FONT"] >> 8
    assert mpu.memory[labels["CHBASE"]] == labels["INTRO_FONT"] >> 8

    # DLI vector must point to first handler in chain (dli_title_color_call)
    dli_vec = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert dli_vec == labels["DLI_TITLE_COLOR_CALL"]

    # NMIEN (VBI + DLI enabled = $C0)
    assert mpu.memory[labels["NMIEN"]] == 0xC0

    # Colors
    assert mpu.memory[labels["COLBK"]] == 0x00
    assert mpu.memory[labels["COLPF0"]] != 0x00, "COLPF0 must not be black ($00)"
    assert mpu.memory[labels["COLPF0"]] != labels["COLBK"], "COLPF0 must differ from COLBK"
    assert mpu.memory[labels["COLPF0"]] != labels["TITLE_COLOR_PF1"], "COLPF0 must differ from COLPF1"
    assert mpu.memory[labels["COLPF0"]] == labels["TITLE_COLOR_PF0"]
    assert mpu.memory[labels["COLPF1"]] == labels["TITLE_COLOR_PF1"]
    assert mpu.memory[labels["COLPF2"]] == labels["TITLE_COLOR_PF2"]

    # Title row colors table (12 bytes in RAM, default values)
    table_addr = labels["TITLE_ROW_COLORS"]
    table_colors = [mpu.memory[table_addr + i] for i in range(12)]
    expected_table = [
        labels["TITLE_CALL_PF0"], labels["TITLE_CALL_PF1"], labels["TITLE_CALL_PF2"],
        labels["TITLE_OFTHE_PF0"], labels["TITLE_OFTHE_PF1"], labels["TITLE_OFTHE_PF2"],
        labels["TITLE_WINTER_PF0"], labels["TITLE_WINTER_PF1"], labels["TITLE_WINTER_PF2"],
        labels["TITLE_LOGO_PF0"], labels["TITLE_LOGO_PF1"], labels["TITLE_LOGO_PF2"],
    ]
    assert table_colors == expected_table
    for i, c in enumerate(table_colors):
        assert c != 0x00, f"Color at index {i} in title_row_colors must not be black ($00)"


# ==============================================================================
# 5. Title Line Color DLI Handlers & Self-Resetting Chain Tests
# ==============================================================================


def run_dli_handler(mpu: MPU, addr: int) -> int:
    """Simulate hardware NMI pushing PC and P to stack before jumping to DLI handler until RTI."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x01
    mpu.memory[0x0100 + sp - 1] = 0x00
    mpu.memory[0x0100 + sp - 2] = mpu.p
    mpu.sp = sp - 3
    mpu.pc = addr

    cycles_start = mpu.processorCycles
    while mpu.sp != sp:
        mpu.step()
    return mpu.processorCycles - cycles_start


@pytest.mark.parametrize(
    "test_colors",
    [
        [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB, 0xCC],
        [0x84, 0x9A, 0x32, 0x62, 0x48, 0x56, 0x36, 0x1E, 0x2A, 0x46, 0x58, 0x6A],
    ],
)
def test_title_color_handlers_and_chain(emu_env, test_colors):
    """Verify each color handler reads from title_row_colors, sets COLPF0/COLPF1/COLPF2, and chains VDSLST."""
    mpu, labels = emu_env

    table_addr = labels["TITLE_ROW_COLORS"]
    for i, c in enumerate(test_colors):
        mpu.memory[table_addr + i] = c

    # 1. dli_title_color_call
    cycles_call = run_dli_handler(mpu, labels["DLI_TITLE_COLOR_CALL"])
    assert cycles_call == 49, f"Expected 49 cycles for dli_title_color_call, got {cycles_call}"
    assert mpu.memory[labels["COLPF0"]] == test_colors[0]
    assert mpu.memory[labels["COLPF1"]] == test_colors[1]
    assert mpu.memory[labels["COLPF2"]] == test_colors[2]
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_OF_THE"]

    # 2. dli_title_color_of_the
    cycles_of_the = run_dli_handler(mpu, labels["DLI_TITLE_COLOR_OF_THE"])
    assert cycles_of_the == 49, f"Expected 49 cycles for dli_title_color_of_the, got {cycles_of_the}"
    assert mpu.memory[labels["COLPF0"]] == test_colors[3]
    assert mpu.memory[labels["COLPF1"]] == test_colors[4]
    assert mpu.memory[labels["COLPF2"]] == test_colors[5]
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_WINTER"]

    # 3. dli_title_color_winter
    cycles_winter = run_dli_handler(mpu, labels["DLI_TITLE_COLOR_WINTER"])
    assert cycles_winter == 49, f"Expected 49 cycles for dli_title_color_winter, got {cycles_winter}"
    assert mpu.memory[labels["COLPF0"]] == test_colors[6]
    assert mpu.memory[labels["COLPF1"]] == test_colors[7]
    assert mpu.memory[labels["COLPF2"]] == test_colors[8]
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_LOGO"]

    # 4. dli_title_color_logo
    cycles_logo = run_dli_handler(mpu, labels["DLI_TITLE_COLOR_LOGO"])
    assert cycles_logo == 49, f"Expected 49 cycles for dli_title_color_logo, got {cycles_logo}"
    assert mpu.memory[labels["COLPF0"]] == test_colors[9]
    assert mpu.memory[labels["COLPF1"]] == test_colors[10]
    assert mpu.memory[labels["COLPF2"]] == test_colors[11]
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_SCROLL"]


def test_title_color_handlers_isolation_and_registers(emu_env):
    """Verify color handlers preserve A, X, Y and write ONLY to COLPF0, COLPF1, COLPF2, VDSLST, VDSLST+1."""
    mpu, labels = emu_env

    handlers = [
        labels["DLI_TITLE_COLOR_CALL"],
        labels["DLI_TITLE_COLOR_OF_THE"],
        labels["DLI_TITLE_COLOR_WINTER"],
        labels["DLI_TITLE_COLOR_LOGO"],
    ]

    allowed_writes = {
        labels["COLPF0"],
        labels["COLPF1"],
        labels["COLPF2"],
        labels["VDSLST"],
        labels["VDSLST"] + 1,
    }

    for handler_addr in handlers:
        # Preload registers with sentinel values
        mpu.a = 0xAA
        mpu.x = 0x55
        mpu.y = 0x33
        mpu.p = 0x20

        # Capture memory snapshot (excluding stack which is used by interrupt)
        mem_snapshot = bytearray(mpu.memory)

        sp = mpu.sp
        run_dli_handler(mpu, handler_addr)

        # Register preservation checks
        assert mpu.a == 0xAA, "Accumulator not preserved by DLI handler"
        assert mpu.x == 0x55, "Register X clobbered by DLI handler"
        assert mpu.y == 0x33, "Register Y clobbered by DLI handler"

        # Check that no unauthorized memory was modified
        stack_range = set(range(0x0100 + sp - 3, 0x0100 + sp + 1))
        for addr in range(65536):
            if addr in allowed_writes or addr in stack_range:
                continue
            assert mpu.memory[addr] == mem_snapshot[addr], (
                f"Unauthorized memory modification at 0x{addr:04X} by handler at 0x{handler_addr:04X}: "
                f"was 0x{mem_snapshot[addr]:02X}, became 0x{mpu.memory[addr]:02X}"
            )


def test_title_full_frame_dli_chain_simulation(emu_env):
    """Simulate a complete frame through all 5 DLIs and verify self-resetting loop."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Initial vector after title_init
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_CALL"]

    # 1st DLI: CALL
    run_dli_handler(mpu, vdslst)
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_OF_THE"]

    # 2nd DLI: OF THE
    run_dli_handler(mpu, vdslst)
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_WINTER"]

    # 3rd DLI: WINTERMOON
    run_dli_handler(mpu, vdslst)
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_LOGO"]

    # 4th DLI: LOGO
    run_dli_handler(mpu, vdslst)
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_SCROLL"]

    # 5th DLI: SCROLL
    run_dli_handler(mpu, vdslst)
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_CALL"], "DLI chain must self-reset to dli_title_color_call"


def test_title_run_resets_vdslst(emu_env):
    """Verify that title_run resets VDSLST to dli_title_color_call at start of frame."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Corrupt VDSLST
    mpu.memory[labels["VDSLST"]] = 0x55
    mpu.memory[labels["VDSLST"] + 1] = 0xAA

    # Allow title_run to pass RTCLOK synchronization
    rtclok_lo = labels["RTCLOK"] + 2
    mpu.memory[rtclok_lo] = 10

    # Advance RTCLOK in a small step or mock RTCLOK loop
    # In title_run:
    #   lda RTCLOK+2
    # @sync_vblank: cmp RTCLOK+2; beq @sync_vblank
    # To bypass, we simulate PC past sync loop
    title_run_addr = labels["TITLE_RUN"]
    mpu.sp = 0xFD
    mpu.stPushWord(0x0100 - 1)
    mpu.pc = title_run_addr
    # Step past DMACTL, ATRACT, up to RTCLOK sync
    steps = 0
    while steps < 15:
        # If waiting at beq @sync_vblank, change RTCLOK+2
        if mpu.memory[mpu.pc] == 0xF0:  # BEQ
            mpu.memory[rtclok_lo] += 1
        mpu.step()
        steps += 1
        if mpu.pc == labels.get("AUDIO_UPDATE", 0):
            break

    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_CALL"], f"title_run must reset VDSLST to DLI_TITLE_COLOR_CALL, got 0x{vdslst:04X}"

