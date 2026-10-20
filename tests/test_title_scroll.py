"""Unit and py65 emulation tests for title screen smooth scrolling line (ANTIC Mode 2)."""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.compile_scroll_text import char_to_screencode, compile_scroll_text


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


def step_until_rts_or_rti(mpu: MPU, max_cycles: int = 50000, target_sp: int | None = None) -> int:
    """Step 6502 MPU until RTS ($60) or RTI ($40) instruction executes at the target stack depth."""
    cycles = 0
    while cycles < max_cycles:
        opcode = mpu.memory[mpu.pc]
        mpu.step()
        cycles += 1
        if opcode in (0x60, 0x40):  # RTS or RTI
            if target_sp is None or mpu.sp == target_sp:
                return cycles
    raise TimeoutError(f"Subroutine at PC=${mpu.pc:04X} timed out (SP=${mpu.sp:02X}, target_sp={target_sp})")


def run_dli_interrupt(mpu: MPU, addr: int) -> int:
    """Simulate hardware NMI pushing PC and P to stack before jumping to DLI handler."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x01      # PC high ($01)
    mpu.memory[0x0100 + sp - 1] = 0x00  # PC low ($00) -> return to $0100
    mpu.memory[0x0100 + sp - 2] = 0x30  # P status
    mpu.sp = sp - 3
    mpu.pc = addr
    return step_until_rts_or_rti(mpu, target_sp=sp)


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


# ==============================================================================
# Unit Tests for compile_scroll_text.py
# ==============================================================================


def test_char_to_screencode():
    assert char_to_screencode(" ") == 0
    assert char_to_screencode("A") == 33
    assert char_to_screencode("C") == 35
    assert char_to_screencode("!") == 1
    assert char_to_screencode("-") == 13
    assert char_to_screencode("0") == 16
    assert char_to_screencode("a") == 97


def test_compile_scroll_text_output(tmp_path: Path):
    in_file = tmp_path / "test_scroll.txt"
    in_file.write_text("HELLO WORLD!", encoding="utf-8")
    out_file = tmp_path / "test_scroll.asm"

    ret = compile_scroll_text(in_file, out_file, min_trailing_spaces=10)
    assert ret == 0
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "TITLE_SCROLL_TEXT_LEN = 22" in content  # 12 chars + 10 spaces
    assert "title_scroll_text" in content


# ==============================================================================
# Emulation Integration Tests
# ==============================================================================


def test_title_scroll_symbols_present(emu_env):
    _, labels = emu_env
    required = [
        "TITLE_INIT",
        "TITLE_RUN",
        "DLI_TITLE_SCROLL",
        "UPDATE_TITLE_SCROLL",
        "TITLE_SCROLL_FINE",
        "TITLE_SCROLL_DELAY",
        "TITLE_SCROLL_IDX",
        "TITLE_SCROLL_VRAM",
        "TITLE_SCROLL_TEXT",
        "TITLE_SCROLL_TEXT_LEN",
    ]
    for sym in required:
        assert sym in labels, f"Missing symbol {sym} in gen/main.lab"


def test_title_init_initializes_scroller(emu_env):
    mpu, labels = emu_env

    # Poison values
    mpu.memory[labels["TITLE_SCROLL_FINE"]] = 99
    mpu.memory[labels["TITLE_SCROLL_IDX"]] = 55
    vram_addr = labels["TITLE_SCROLL_VRAM"]
    for i in range(48):
        mpu.memory[vram_addr + i] = 0xFF

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Fine scroll must start at 3
    assert mpu.memory[labels["TITLE_SCROLL_FINE"]] == 3
    assert mpu.memory[labels["TITLE_SCROLL_IDX"]] == 0
    assert mpu.memory[labels["TITLE_SCROLL_DELAY"]] == labels["TITLE_SCROLL_SPEED"]

    # Entire 48-byte VRAM must be cleared to spaces ($00)
    for i in range(48):
        assert mpu.memory[vram_addr + i] == 0x00

    # DLI vector must point to dli_title_color_call (first in chain)
    dli_vec = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert dli_vec == labels["DLI_TITLE_COLOR_CALL"]

    # NMIEN must have DLI ($80) and VBI ($40) enabled ($C0)
    assert mpu.memory[labels["NMIEN"]] == 0xC0

    # CHBASE must point to intro_font page ($24)
    assert mpu.memory[labels["CHBASE"]] == labels["INTRO_FONT"] >> 8

    # Normal playfield DMA ($22)
    assert mpu.memory[labels["SDMCTL"]] == 0x22
    assert mpu.memory[labels["DMACTL"]] == 0x22


def test_update_title_scroll_progression_and_wrap(emu_env):
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    vram_addr = labels["TITLE_SCROLL_VRAM"]
    text_addr = labels["TITLE_SCROLL_TEXT"]
    first_char = mpu.memory[text_addr]  # 'C' = 0x23
    assert first_char == 0x23

    def step_fine_scroll():
        delay = mpu.memory[labels["TITLE_SCROLL_DELAY"]]
        for _ in range(delay):
            run_subroutine(mpu, labels["UPDATE_TITLE_SCROLL"])

    # Step 1: fine scroll 3 -> 2
    step_fine_scroll()
    assert mpu.memory[labels["TITLE_SCROLL_FINE"]] == 2
    assert mpu.memory[labels["TITLE_SCROLL_IDX"]] == 0

    # Step 2: fine scroll 2 -> 1
    step_fine_scroll()
    assert mpu.memory[labels["TITLE_SCROLL_FINE"]] == 1
    assert mpu.memory[labels["TITLE_SCROLL_IDX"]] == 0

    # Step 3: fine scroll 1 -> 0
    step_fine_scroll()
    assert mpu.memory[labels["TITLE_SCROLL_FINE"]] == 0
    assert mpu.memory[labels["TITLE_SCROLL_IDX"]] == 0

    # Step 4: fine scroll wraps to 3, VRAM shifts left, byte 47 gets first char!
    step_fine_scroll()
    assert mpu.memory[labels["TITLE_SCROLL_FINE"]] == 3
    assert mpu.memory[labels["TITLE_SCROLL_IDX"]] == 1
    assert mpu.memory[vram_addr + 47] == first_char


def test_dli_title_scroll_sets_registers(emu_env):
    mpu, labels = emu_env

    mpu.memory[labels["DMACTL"]] = 0x22
    mpu.memory[labels["TITLE_SCROLL_FINE"]] = 2

    colpf2_writes = []
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x01
    mpu.memory[0x0100 + sp - 1] = 0x00
    mpu.memory[0x0100 + sp - 2] = 0x30
    mpu.sp = sp - 3
    mpu.pc = labels["DLI_TITLE_SCROLL"]

    while mpu.sp != sp:
        pc = mpu.pc
        if mpu.memory[pc] == 0x8D and mpu.memory[pc + 1] == (labels["COLPF2"] & 0xFF) and mpu.memory[pc + 2] == (labels["COLPF2"] >> 8):
            colpf2_writes.append(mpu.a)
        mpu.step()

    # 8 rainbow scanlines on COLPF2 ($C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0) + restore ($EE)
    expected = [0xC0, 0xC2, 0xC4, 0xC6, 0xC6, 0xC4, 0xC2, 0xC0, labels["TITLE_COLOR_PF2"]]
    assert colpf2_writes == expected

    # Final restored state
    assert mpu.memory[labels["DMACTL"]] == 0x22
    assert mpu.memory[labels["HSCROL"]] == 0
    assert mpu.memory[labels["COLPF1"]] == labels["TITLE_COLOR_PF1"]
    assert mpu.memory[labels["COLPF2"]] == labels["TITLE_COLOR_PF2"]

    # VDSLST self-reset to dli_title_color_call
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_CALL"]
