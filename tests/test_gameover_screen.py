"""Tests for the Game Over / Victory screens (FAILURE and SUCCESS).

Covers the text converter (scripts/convert_gameover_texts.py), the run-time screen
builder (scenes/gameover.asm), both display lists and the DLI colour chain, using
py65 for the 6502 side - conventions as in the title screen tests.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.convert_gameover_texts import (
    GAMEOVER_LINE_WIDTH,
    GAMEOVER_MAX_LINES,
    GameOverTextError,
    compile_gameover_texts,
    parse_text_file,
    render_include,
)
from scripts.compile_scroll_text import char_to_screencode
from tests.test_dli_system import load_xex_and_symbols, run_subroutine
from tests.test_title_text import run_dli_handler

# --- Screen geometry mirrors (scenes/gameover.asm) ---
GAMEOVER_TOP_BLANKS = 3
GAMEOVER_HEADER_LINES = 16
GAMEOVER_TEXT_LINES = 18
HEADER_BUF_OFFSET = 0x0000          # GAME_VRAM + $0000
TEXT_BUF_OFFSET = 0x0140            # GAME_VRAM + $0140
CLEAR_BYTES = 320 + 720             # 1040

HEADER_CODES = {
    "failure": [0x27, 0x21, 0x2D, 0x25, 0x00, 0x2F, 0x36, 0x25, 0x32],
    "success": [0x36, 0x29, 0x23, 0x34, 0x2F, 0x32, 0x39, 0x01],
}
HEADER_OFFSETS = {"failure": 11, "success": 12}


def variant_from_game_result(game_result: int, success: int = 2) -> str:
    """Mirror of the variant selection in gameover_init (GAME_SUCCESS -> SUCCESS)."""
    return "success" if game_result == success else "failure"


# ==============================================================================
# Text converter
# ==============================================================================

def write_text(tmp_path: Path, name: str, content: str) -> Path:
    """Write a text file with exact bytes (no newline translation by the platform)."""
    path = tmp_path / name
    path.write_bytes(content.encode("utf-8"))
    return path


def test_parse_text_file_keeps_blank_lines_and_trailing_newline(tmp_path: Path):
    """0, 1 and 18 lines; blank lines keep their position; a final newline adds none."""
    empty = write_text(tmp_path, "empty.txt", "")
    assert parse_text_file(empty) == []

    one = write_text(tmp_path, "one.txt", "HELLO\n")
    assert parse_text_file(one) == [[char_to_screencode(c) for c in "HELLO"]]

    # Blank lines at the start, in the middle and at the end must all survive.
    spaced = write_text(tmp_path, "spaced.txt", "\nAB\n\nCD\n\n")
    encoded = parse_text_file(spaced)
    assert [len(line) for line in encoded] == [0, 2, 0, 2, 0]

    full = write_text(tmp_path, "full.txt", "\n".join(f"LINE {i}" for i in range(1, 19)) + "\n")
    assert len(parse_text_file(full)) == GAMEOVER_MAX_LINES

    # CRLF endings behave exactly like LF
    crlf = write_text(tmp_path, "crlf.txt", "AB\r\n\r\nCD\r\n")
    assert [len(line) for line in parse_text_file(crlf)] == [2, 0, 2]


def test_parse_text_file_rejects_invalid_input(tmp_path: Path):
    too_many = write_text(tmp_path, "many.txt", "\n".join("X" for _ in range(19)))
    with pytest.raises(GameOverTextError, match="exceed the 18-line screen area"):
        parse_text_file(too_many)

    too_long = write_text(tmp_path, "long.txt", "Y" * (GAMEOVER_LINE_WIDTH + 1))
    with pytest.raises(GameOverTextError, match=f"line 1 is {GAMEOVER_LINE_WIDTH + 1} characters"):
        parse_text_file(too_long)

    unknown = write_text(tmp_path, "unknown.txt", "OK\nAB\u2603CD")
    with pytest.raises(GameOverTextError, match="column 3"):
        parse_text_file(unknown)

    with pytest.raises(GameOverTextError, match="Missing text file"):
        parse_text_file(tmp_path / "does-not-exist.txt")


def test_typographic_punctuation_is_normalised(tmp_path: Path):
    """Dashes and typographic quotes map to their ASCII equivalents, not to blanks."""
    path = write_text(tmp_path, "dash.txt", "A \u2014 B \u2013 C \u2019D\u2019")
    line = parse_text_file(path)[0]
    assert line == [char_to_screencode(c) for c in "A - B - C 'D'"]


def test_generated_include_matches_independent_reference(tmp_path: Path):
    """The emitted MADS data must equal an independent conversion of the same text."""
    failure = write_text(tmp_path, "f.txt", "ONE\n\nTWO \u2014 THREE")
    success = write_text(tmp_path, "s.txt", "GRATULACJE!\n\nBYE")
    out = tmp_path / "gameover_texts.inc"
    assert compile_gameover_texts(out, failure, success) == 0

    lines = out.read_text(encoding="utf-8").splitlines()
    expected_failure = [[char_to_screencode(c) for c in "ONE"], [], [char_to_screencode(c) for c in "TWO - THREE"]]
    expected_success = [[char_to_screencode(c) for c in "GRATULACJE!"], [], [char_to_screencode(c) for c in "BYE"]]

    for name, expected in (("failure", expected_failure), ("success", expected_success)):
        start = lines.index(f"gameover_{name}_text:")
        assert lines[start + 1] == f"    .byte {len(expected)}"
        body = lines[start + 2:start + 2 + len(expected)]
        for emitted, codes in zip(body, expected):
            if not codes:
                assert emitted == "    .byte 0"
            else:
                assert emitted == "    .byte %d, %s" % (
                    len(codes), ", ".join(f"${c:02X}" for c in codes)
                )


def test_real_project_texts_compile(tmp_path: Path):
    """texts/failure.txt and texts/success.txt must pass validation (build contract)."""
    out = tmp_path / "gameover_texts.inc"
    assert compile_gameover_texts(out) == 0
    failure = parse_text_file(Path("texts/failure.txt"))
    success = parse_text_file(Path("texts/success.txt"))
    assert failure and success
    assert len(failure) <= GAMEOVER_MAX_LINES and len(success) <= GAMEOVER_MAX_LINES
    for line in failure + success:
        assert len(line) <= GAMEOVER_LINE_WIDTH



# ==============================================================================
# Header and text buffers (py65)
# ==============================================================================

def reference_glyph_row(byte: int) -> tuple[int, int]:
    """Left/right 2bpp bytes for one 8-pixel glyph row, per the three column bands.

    Every *set pixel* of the source row is emitted with the band value of its source
    bit range: bits 7-6 -> %10 (COLPF1), bits 5-2 -> %11 (COLPF2), bits 1-0 -> %01
    (COLPF0). Pixels 0..3 land in the left byte, pixels 4..7 in the right one.
    """
    left = 0
    right = 0
    for i in range(8):
        if not ((byte >> (7 - i)) & 1):
            continue
        band = 0b10 if i < 2 else (0b11 if i < 6 else 0b01)
        if i < 4:
            left |= band << (6 - 2 * i)
        else:
            right |= band << (6 - 2 * (i - 4))
    return left, right


def reference_header_buffer(variant: str) -> list[int]:
    """Independent 320-byte reference of the generated header buffer."""
    codes = HEADER_CODES[variant]
    offset = HEADER_OFFSETS[variant]
    font = Path("fonts/font.fnt").read_bytes()
    buffer = [0] * 320
    for index, code in enumerate(codes):
        glyph = font[code * 8:(code * 8) + 8]
        for row in range(8):
            left, right = reference_glyph_row(glyph[row])
            base = row * 40 + offset + index * 2
            buffer[base] = left
            buffer[base + 1] = right
    return buffer


def reference_text_buffer(variant: str) -> list[int]:
    """Independent 720-byte reference: every line centred with floor((40 - len) / 2)."""
    lines = parse_text_file(Path("texts") / f"{variant}.txt")
    buffer = [0] * 720
    for row, codes in enumerate(lines[:GAMEOVER_TEXT_LINES]):
        left = (GAMEOVER_LINE_WIDTH - len(codes)) // 2
        for i, code in enumerate(codes):
            buffer[row * GAMEOVER_LINE_WIDTH + left + i] = code
    return buffer


def init_gameover(mpu, mem, labels, game_result: int) -> None:
    """Enter the Game Over state the way the state machine does (main.asm)."""
    mem[labels["GAME_RESULT"]] = game_result
    run_subroutine(mpu, labels["GAMEOVER_INIT"])


@pytest.mark.parametrize("variant,game_result", [("failure", 1), ("success", 2)])
def test_header_buffer_matches_reference(variant: str, game_result: int):
    """Both variants must render their header with the title screen's 2bpp bands."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    init_gameover(mpu, mem, labels, game_result)
    assert mem[labels["GAMEOVER_RESULT"]] == (1 if variant == "success" else 0)

    header = labels["GAMEOVER_HEADER_BUF"]
    actual = list(mem[header:header + 320])
    expected = reference_header_buffer(variant)
    assert actual == expected, f"{variant}: header buffer differs from the reference"

    # Margins around the header text must stay blank (cleared) bytes.
    offset = HEADER_OFFSETS[variant]
    codes = HEADER_CODES[variant]
    for row in range(8):
        base = row * 40
        assert actual[base:base + offset] == [0] * offset
        assert actual[base + offset + 2 * len(codes):base + 40] == [0] * (
            40 - offset - 2 * len(codes)
        )


@pytest.mark.parametrize("variant,game_result", [("failure", 1), ("success", 2)])
def test_text_buffer_centering_and_blanks(variant: str, game_result: int):
    """Text lines are centred, blank lines keep their position and the rest stays blank."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    init_gameover(mpu, mem, labels, game_result)

    text = labels["GAMEOVER_TEXT_BUF"]
    actual = list(mem[text:text + 720])
    assert actual == reference_text_buffer(variant), f"{variant}: text buffer differs"

    # The text buffer must sit right after the header buffer ($3140).
    header = labels["GAMEOVER_HEADER_BUF"]
    assert text == header + 320

    # Nothing past the 1040 cleared bytes may be touched.
    sentinel = 0x3410
    mem[sentinel] = 0xAA
    mem[0x3000 - 1] = 0x55
    init_gameover(mpu, mem, labels, game_result)
    assert mem[sentinel] == 0xAA, "the first byte after the buffers must stay untouched"
    assert mem[0x3000 - 1] == 0x55, "the byte before the buffers must stay untouched"


def test_reentry_from_the_other_variant_clears_the_previous_screen():
    """Switching variants must not leave anything from the previous screen behind."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    header = labels["GAMEOVER_HEADER_BUF"]
    text = labels["GAMEOVER_TEXT_BUF"]

    init_gameover(mpu, mem, labels, 2)          # SUCCESS
    success_header = list(mem[header:header + 320])
    success_text = list(mem[text:text + 720])

    init_gameover(mpu, mem, labels, 1)          # FAILURE
    assert list(mem[header:header + 320]) == reference_header_buffer("failure")
    assert list(mem[text:text + 720]) == reference_text_buffer("failure")
    assert list(mem[header:header + 320]) != success_header

    init_gameover(mpu, mem, labels, 2)          # back to SUCCESS
    assert list(mem[header:header + 320]) == success_header
    assert list(mem[text:text + 720]) == success_text



# ==============================================================================
# Display lists
# ==============================================================================

DL_BLANK8 = 0x70
DL_MODE_2 = 0x02
DL_MODE_D = 0x0D
DL_LMS = 0x40
DL_DLI = 0x80
DL_JVB = 0x41


def walk_display_list(mem, start: int) -> list[tuple[int, int | None]]:
    """Return (instruction, operand) pairs until JVB; mode instructions may carry LMS."""
    out: list[tuple[int, int | None]] = []
    pc = start
    while True:
        ins = mem[pc]
        if (ins & 0x0F) != 0 and (ins & 0x40):
            operand = mem[pc + 1] | (mem[pc + 2] << 8)
            pc += 3
        else:
            operand = None
            pc += 1
        out.append((ins, operand))
        if ins == DL_JVB:
            return out
        assert len(out) < 200, "display list is not terminated by JVB"


@pytest.mark.parametrize("variant", ["failure", "success"])
def test_display_list_structure(variant: str):
    """Exact byte sequence, DLI count, total height and the 1 KB page rule."""
    mem, labels = load_xex_and_symbols()
    start = labels[f"DLIST_GAMEOVER_{variant.upper()}"]
    instructions = walk_display_list(mem, start)
    header_buf = labels["GAMEOVER_HEADER_BUF"]
    text_buf = labels["GAMEOVER_TEXT_BUF"]

    # 1. Top margin: (GAMEOVER_TOP_BLANKS - 1) blank lines, then the DLI blank line.
    assert instructions[0][0] == DL_BLANK8 and instructions[1][0] == DL_BLANK8
    assert instructions[2][0] == (DL_BLANK8 | DL_DLI)

    # 2. Header: 16 ANTIC D lines with their own LMS, every glyph row twice.
    header = instructions[3:19]
    assert len(header) == GAMEOVER_HEADER_LINES
    for index, (ins, operand) in enumerate(header):
        assert ins == (DL_MODE_D | DL_LMS)
        assert operand == header_buf + 40 * (index // 2)

    # 3. Margin with the text DLI bit, then 18 ANTIC 2 lines (first one with LMS).
    assert instructions[19][0] == (DL_BLANK8 | DL_DLI)
    assert instructions[20][0] == (DL_MODE_2 | DL_LMS)
    assert instructions[20][1] == text_buf
    assert [ins for ins, _ in instructions[21:38]] == [DL_MODE_2] * 17

    # 4. Jump back to the start of this display list.
    assert instructions[38][0] == DL_JVB
    assert instructions[38][1] == start
    assert len(instructions) == 39      # 3 blanks + 16 header + 1 blank + 18 text + JVB

    # Exactly two DLI bits, height 208 scanlines: ANTIC D = 2 scanlines per line,
    # ANTIC 2 and DL_BLANK8 = 8 scanlines each.
    assert sum(1 for ins, _ in instructions if ins & DL_DLI) == 2
    height = 0
    for ins, _ in instructions:
        if ins == DL_JVB:
            continue
        height += 2 if (ins & 0x0F) == DL_MODE_D else 8
    assert height == 208
    end = start + (3 + 16 * 3 + 1 + 3 + 17 + 3)
    assert start // 1024 == (end - 1) // 1024, "the display list must not cross a 1 KB boundary"


# ==============================================================================
# DLI chain and integration
# ==============================================================================

def test_dli_handlers_write_colors_and_preserve_registers():
    """Both handlers write exactly the colour registers and the VDSLST chain."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Unique test values so a wrong index cannot pass by accident. The background
    # value is non-zero here (production uses $00) so the write is observable.
    colors = [0x12, 0x34, 0x56, 0x78, 0x9A, 0x2E]
    for i, value in enumerate(colors):
        mem[labels["GAMEOVER_COLORS"] + i] = value

    header_handler = labels["DLI_GAMEOVER_HEADER"]
    text_handler = labels["DLI_GAMEOVER_TEXT"]

    for handler, vdslst_target in ((header_handler, text_handler), (text_handler, header_handler)):
        # The header handler also writes COLPF0, the text handler does not.
        expected_addresses = [
            labels["COLPF1"], labels["COLPF2"], labels["COLBK"],
            labels["VDSLST"], labels["VDSLST"] + 1,
        ]
        if handler == header_handler:
            expected_addresses.append(labels["COLPF0"])

        # Distinct sentinels so every write the handler performs is observable, even
        # when it rewrites a register with the value it already had.
        for addr in (labels["COLPF0"], labels["COLPF1"], labels["COLPF2"], labels["COLBK"]):
            mem[addr] = 0xFE
        mem[labels["VDSLST"]] = 0x00
        mem[labels["VDSLST"] + 1] = 0x00

        before = bytearray(mem)
        mpu.a = 0x5A
        mpu.x = 0x3C
        mpu.y = 0xC3
        cycles = run_dli_handler(mpu, handler)

        assert cycles <= 57, f"handler must fit in one scanline, took {cycles} cycles"
        assert mpu.a == 0x5A, "A must be preserved"
        assert mpu.x == 0x3C, "X must be preserved"
        assert mpu.y == 0xC3, "Y must be preserved"
        assert (mem[labels["VDSLST"]] | (mem[labels["VDSLST"] + 1] << 8)) == vdslst_target

        changed = [
            addr for addr in range(0x10000)
            if mem[addr] != before[addr] and not (0x0100 <= addr <= 0x01FF)
        ]
        assert sorted(changed) == sorted(expected_addresses), (
            f"handler must only write {[hex(a) for a in expected_addresses]}, "
            f"wrote {[hex(a) for a in changed]}"
        )

        # Register mapping: header = PF0..PF2 + COLBK, text = PF1/PF2 + COLBK.
        if handler == header_handler:
            assert mem[labels["COLPF0"]] == colors[0]
            assert mem[labels["COLPF1"]] == colors[1]
            assert mem[labels["COLPF2"]] == colors[2]
        else:
            assert mem[labels["COLPF1"]] == colors[3]
            assert mem[labels["COLPF2"]] == colors[4]
        assert mem[labels["COLBK"]] == colors[5]



@pytest.mark.parametrize("variant,game_result", [("failure", 1), ("success", 2)])
def test_gameover_init_sets_up_the_screen(variant: str, game_result: int):
    """Full contract of gameover_init for both variants."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    init_gameover(mpu, mem, labels, game_result)

    # Variant id and the display list of that variant
    assert mem[labels["GAMEOVER_RESULT"]] == (1 if variant == "success" else 0)
    dlist = labels[f"DLIST_GAMEOVER_{variant.upper()}"]
    assert mem[labels["SDLSTL"]] == (dlist & 0xFF)
    assert mem[labels["SDLSTH"]] == (dlist >> 8)
    assert mem[labels["DLISTL"]] == (dlist & 0xFF)
    assert mem[labels["DLISTH"]] == (dlist >> 8)

    # Colours: the variant table copied into the runtime gameover_colors table
    variant_colors = labels[f"GAMEOVER_COLORS_{variant.upper()}"]
    for i in range(6):
        assert mem[labels["GAMEOVER_COLORS"] + i] == mem[variant_colors + i]

    # Normal-width playfield DMA, shared font, PMG graphics off, DLI + VBLANK enabled
    assert mem[labels["SDMCTL"]] == 0x22 and mem[labels["DMACTL"]] == 0x22
    assert mem[labels["CHBAS"]] == 0x24 and mem[labels["CHBASE"]] == 0x24
    assert mem[labels["GRACTL"]] == 0
    for reg in (
        "HPOSP0", "HPOSP1", "HPOSP2", "HPOSP3",
        "HPOSM0", "HPOSM1", "HPOSM2", "HPOSM3",
        "SIZEP0", "SIZEP1", "SIZEP2", "SIZEP3", "SIZEM",
    ):
        assert mem[labels[reg]] == 0, f"{reg} must be cleared"
    assert mem[labels["NMIEN"]] == 0xC0
    assert (mem[labels["VDSLST"]] | (mem[labels["VDSLST"] + 1] << 8)) == labels["DLI_GAMEOVER_HEADER"]

    # Header and text of this variant
    header = labels["GAMEOVER_HEADER_BUF"]
    assert list(mem[header:header + 320]) == reference_header_buffer(variant)
    text = labels["GAMEOVER_TEXT_BUF"]
    assert list(mem[text:text + 720]) == reference_text_buffer(variant)


def run_gameover_frame(mpu, mem, labels, steps: int = 400_000, tick: int = 40) -> None:
    """Run gameover_run once, emulating the VBLANK counter it synchronises with."""
    mpu.sp = 0xFD
    mpu.stPushWord(0x0100 - 1)
    mem[0x0100] = 0x00
    mpu.pc = labels["GAMEOVER_RUN"]
    executed = 0
    while mpu.pc != 0x0100 and executed < steps:
        mpu.step()
        executed += 1
        if executed % tick == 0:
            rtc = labels["RTCLOK"] + 2
            mem[rtc] = (mem[rtc] + 1) & 0xFF
    assert mpu.pc == 0x0100, "gameover_run did not return"


def test_gameover_run_returns_to_the_title_screen():
    """Fire (after being released once) leaves to the title screen and disables the DLI."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    init_gameover(mpu, mem, labels, 1)      # FAILURE screen
    mem[labels["GAME_STATE"]] = labels["STATE_OVER"]

    # Fire still held from the gameplay: the handler only arms the release flag
    mem[labels["FIRE_RELEASED"]] = 0
    mem[labels["STRIG0"]] = 0
    run_gameover_frame(mpu, mem, labels)
    assert mem[labels["FIRE_RELEASED"]] == 1
    assert mem[labels["GAME_STATE"]] != labels["STATE_TITLE"]

    # Fire pressed again: leave to the title screen with the DLI disabled
    run_gameover_frame(mpu, mem, labels)
    assert mem[labels["GAME_STATE"]] == labels["STATE_TITLE"]
    assert mem[labels["NMIEN"]] == 0x40
    assert mem[labels["VSCROL"]] == 0 and mem[labels["HSCROL"]] == 0
