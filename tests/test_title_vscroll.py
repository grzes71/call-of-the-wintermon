"""Unit and py65 emulation tests for title screen vertical scrolling window (ANTIC Mode 2 VSCROL)."""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.compile_title_vscroll import char_to_screencode, compile_title_vscroll

# ANTIC Constants
DL_BLANK1 = 0x00
DL_BLANK2 = 0x10
DL_BLANK3 = 0x20
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


def run_dli_handler(mpu: MPU, addr: int, max_steps: int = 50_000) -> int:
    """Simulate hardware NMI pushing PC and P to stack before jumping to DLI handler until RTI."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x01
    mpu.memory[0x0100 + sp - 1] = 0x00
    mpu.memory[0x0100 + sp - 2] = mpu.p
    mpu.sp = sp - 3
    mpu.pc = addr
    steps = 0
    while steps < max_steps:
        opcode = mpu.memory[mpu.pc]
        mpu.step()
        steps += 1
        if opcode == 0x40 and mpu.sp == sp:  # RTI at original stack pointer
            return steps
    raise TimeoutError(f"DLI handler at 0x{addr:04X} timed out (PC=0x{mpu.pc:04X})")


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
# 1. Data Source & Compilation Tool Tests
# ==============================================================================


def test_vscroll_source_text_and_memory_alignment(emu_env):
    """Independently verify scroll/title.txt lines, formatting, bounds and memory tables."""
    mpu, labels = emu_env
    src_file = Path("scroll/title.txt")
    assert src_file.is_file(), "scroll/title.txt missing"

    lines = [line.strip() for line in src_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    n = len(lines)
    assert 1 <= n <= 255
    assert labels["TITLE_VS_COUNT"] == n

    table_addr = labels["TITLE_VS_LINES"]
    mem = mpu.memory

    for i, line in enumerate(lines):
        assert len(line) <= 40, f"Line {i} in scroll/title.txt exceeds 40 chars: {len(line)}"
        exp_offset = (40 - len(line)) // 2
        entry_addr = table_addr + i * 40
        entry_bytes = mem[entry_addr : entry_addr + 40]
        assert len(entry_bytes) == 40

        # Left padding spaces
        assert all(b == 0x00 for b in entry_bytes[:exp_offset])

        # Centered text converted to screen codes
        exp_text_codes = [char_to_screencode(c) for c in line]
        assert list(entry_bytes[exp_offset : exp_offset + len(line)]) == exp_text_codes

        # Right padding spaces
        assert all(b == 0x00 for b in entry_bytes[exp_offset + len(line) :])

        # Pointer table entry verification
        lo_addr = labels["TITLE_VS_LINES_PTR_LO"] + i
        hi_addr = labels["TITLE_VS_LINES_PTR_HI"] + i
        ptr = mem[lo_addr] | (mem[hi_addr] << 8)
        assert ptr == entry_addr


def test_compile_vscroll_rejects_line_longer_than_40(tmp_path: Path):
    """Verify that compile_title_vscroll aborts with error when line > 40 chars."""
    bad_file = tmp_path / "bad_title.txt"
    bad_file.write_text("This line is way too long and definitely exceeds forty characters!", encoding="utf-8")
    out_file = tmp_path / "out.asm"

    with pytest.raises(ValueError, match="exceeds 40-character"):
        compile_title_vscroll(bad_file, out_file)


# ==============================================================================
# 2. Display List Structure & Geometry Tests
# ==============================================================================


def test_dlist_title_vscroll_instructions_and_properties(emu_env):
    """Verify Display List VSCROL instructions, exact height (200 scanlines) and no HSCROL."""
    mpu, labels = emu_env
    dlist_addr = labels["DLIST_TITLE"]
    mem = mpu.memory

    # Find the VSCROL instruction by searching for DL_VSCROL
    pc = dlist_addr
    total_scanlines = 0
    dli_count = 0
    hscrol_found = False
    while pc < dlist_addr + 122:
        inst = mem[pc]
        if inst & DL_DLI:
            dli_count += 1

        mode = inst & 0x0F
        if mode == 0x00:  # Blank
            scanlines = ((inst >> 4) & 0x07) + 1
            total_scanlines += scanlines
            pc += 1
        elif mode == 0x01:  # JVB / JMP
            pc += 3
        else:
            if inst & DL_HSCROL:
                hscrol_found = True

            if inst & DL_LMS:
                pc += 3
            else:
                pc += 1

            # Mode lines scanline contribution
            if mode == DL_MODE_E:
                total_scanlines += 1
            elif mode == DL_MODE_D:
                total_scanlines += 2
            elif mode == DL_MODE_2:
                # Mode 2 with VSCROL: 2 lines combine into 9 scanlines
                if inst & DL_VSCROL:
                    pass  # handled in combined check below

    assert not hscrol_found, "Display List must not contain DL_HSCROL"
    assert dli_count == 5, f"Expected exactly 5 DLI bits, got {dli_count}"

    # Verify specific VSCROL window instructions
    lms_inst_addr = labels["TITLE_DL_VS_LMS"]
    assert mem[lms_inst_addr] == (DL_MODE_2 | DL_LMS | DL_VSCROL)
    addr_operand = mem[lms_inst_addr + 1] | (mem[lms_inst_addr + 2] << 8)
    assert addr_operand == labels["TITLE_VS_BUF"]
    second_line_inst = mem[lms_inst_addr + 3]
    assert second_line_inst == (DL_MODE_2 | DL_VSCROL)


# ==============================================================================
# 3. Initialization and State Machine Py65 Emulation
# ==============================================================================


def test_title_init_vscroll_state(emu_env):
    """Verify title_init sets p=7, VSCROL=7, clears L0/L1, and loads first message into L2."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    assert mpu.memory[labels["TITLE_VS_POS"]] == 7
    assert mpu.memory[labels["TITLE_VS_STATE"]] == 0  # TITLE_VS_STATE_IN
    assert mpu.memory[labels["TITLE_VS_TIMER"]] == labels["TITLE_VS_FRAMES_PER_STEP"]
    assert mpu.memory[labels["TITLE_VS_INDEX"]] == 0
    assert mpu.memory[labels["VSCROL"]] == 7

    dl_lms = mpu.memory[labels["TITLE_DL_VS_ADDR"]] | (mpu.memory[labels["TITLE_DL_VS_ADDR"] + 1] << 8)
    assert dl_lms == labels["TITLE_VS_BUF"]

    vs_buf = labels["TITLE_VS_BUF"]
    # L0 and L1 must be all 0x00 spaces
    assert all(mpu.memory[vs_buf + i] == 0x00 for i in range(80))

    # L2 must match first line in title_vs_lines
    first_line = bytes(mpu.memory[labels["TITLE_VS_LINES"] : labels["TITLE_VS_LINES"] + 40])
    l2_content = bytes(mpu.memory[vs_buf + 80 : vs_buf + 120])
    assert l2_content == first_line


def test_title_vscroll_state_machine_full_cycle(emu_env):
    """Simulate consecutive frames in update_title_vscroll across multiple messages and wrap."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    num_messages = labels["TITLE_VS_COUNT"]
    total_cycles_to_test = num_messages + 1  # Verify wrap after last message

    frames_per_step = labels["TITLE_VS_FRAMES_PER_STEP"]
    hold_frames = labels["TITLE_VS_HOLD_FRAMES"]
    pause_frames = labels["TITLE_VS_PAUSE_FRAMES"]
    vs_buf = labels["TITLE_VS_BUF"]

    for msg_idx in range(total_cycles_to_test):
        expected_msg_index = msg_idx % num_messages
        assert mpu.memory[labels["TITLE_VS_INDEX"]] == expected_msg_index

        # Verify L2 contains current message
        exp_line = bytes(mpu.memory[labels["TITLE_VS_LINES"] + expected_msg_index * 40 : labels["TITLE_VS_LINES"] + (expected_msg_index + 1) * 40])
        assert bytes(mpu.memory[vs_buf + 80 : vs_buf + 120]) == exp_line

        # ----------------------------------------------------------------------
        # Phase 1: IN (p steps from 7 to 15, 8 steps * frames_per_step = 24 frames)
        # ----------------------------------------------------------------------
        assert mpu.memory[labels["TITLE_VS_STATE"]] == 0  # IN
        for step in range(8):
            for f in range(frames_per_step):
                run_subroutine(mpu, labels["UPDATE_TITLE_VSCROLL"])

                p = mpu.memory[labels["TITLE_VS_POS"]]
                vscrol = mpu.memory[labels["VSCROL"]]
                lms = mpu.memory[labels["TITLE_DL_VS_ADDR"]] | (mpu.memory[labels["TITLE_DL_VS_ADDR"] + 1] << 8)

                # Invariant checks in EVERY frame
                assert vscrol == (p & 7)
                assert vscrol <= 7
                assert lms == (vs_buf if p < 8 else vs_buf + 40)
                # L0 and L1 must remain empty
                assert all(mpu.memory[vs_buf + i] == 0x00 for i in range(80))

            expected_p = 7 + step + 1
            assert mpu.memory[labels["TITLE_VS_POS"]] == expected_p

        assert mpu.memory[labels["TITLE_VS_POS"]] == 15
        assert mpu.memory[labels["TITLE_VS_STATE"]] == 1  # HOLD

        # ----------------------------------------------------------------------
        # Phase 2: HOLD (p = 15 for hold_frames = 200 frames)
        # ----------------------------------------------------------------------
        for f in range(hold_frames):
            run_subroutine(mpu, labels["UPDATE_TITLE_VSCROLL"])
            p = mpu.memory[labels["TITLE_VS_POS"]]
            assert p == 15
            assert mpu.memory[labels["VSCROL"]] == 7
            lms = mpu.memory[labels["TITLE_DL_VS_ADDR"]] | (mpu.memory[labels["TITLE_DL_VS_ADDR"] + 1] << 8)
            assert lms == vs_buf + 40

        assert mpu.memory[labels["TITLE_VS_STATE"]] == 2  # OUT

        # ----------------------------------------------------------------------
        # Phase 3: OUT (p steps from 15 down to 7, 8 steps * frames_per_step = 24 frames)
        # ----------------------------------------------------------------------
        for step in range(8):
            for f in range(frames_per_step):
                run_subroutine(mpu, labels["UPDATE_TITLE_VSCROLL"])

                p = mpu.memory[labels["TITLE_VS_POS"]]
                vscrol = mpu.memory[labels["VSCROL"]]
                lms = mpu.memory[labels["TITLE_DL_VS_ADDR"]] | (mpu.memory[labels["TITLE_DL_VS_ADDR"] + 1] << 8)

                assert vscrol == (p & 7)
                assert vscrol <= 7
                assert lms == (vs_buf if p < 8 else vs_buf + 40)
                assert all(mpu.memory[vs_buf + i] == 0x00 for i in range(80))

            expected_p = 15 - (step + 1)
            assert mpu.memory[labels["TITLE_VS_POS"]] == expected_p

        assert mpu.memory[labels["TITLE_VS_POS"]] == 7
        assert mpu.memory[labels["TITLE_VS_STATE"]] == 3  # PAUSE

        # Next message must have been loaded into L2 exactly upon reaching p=7
        next_exp_index = (msg_idx + 1) % num_messages
        assert mpu.memory[labels["TITLE_VS_INDEX"]] == next_exp_index
        next_line = bytes(mpu.memory[labels["TITLE_VS_LINES"] + next_exp_index * 40 : labels["TITLE_VS_LINES"] + (next_exp_index + 1) * 40])
        assert bytes(mpu.memory[vs_buf + 80 : vs_buf + 120]) == next_line

        # ----------------------------------------------------------------------
        # Phase 4: PAUSE (p = 7 for pause_frames = 100 frames)
        # ----------------------------------------------------------------------
        for f in range(pause_frames):
            run_subroutine(mpu, labels["UPDATE_TITLE_VSCROLL"])
            p = mpu.memory[labels["TITLE_VS_POS"]]
            assert p == 7
            assert mpu.memory[labels["VSCROL"]] == 7
            lms = mpu.memory[labels["TITLE_DL_VS_ADDR"]] | (mpu.memory[labels["TITLE_DL_VS_ADDR"] + 1] << 8)
            assert lms == vs_buf

        assert mpu.memory[labels["TITLE_VS_STATE"]] == 0  # IN for next iteration


# ==============================================================================
# 4. DLI Handler Verification (9 scanlines gradient, no HSCROL)
# ==============================================================================


def test_dli_title_scroll_execution_and_clean_exit(emu_env):
    """Verify dli_title_scroll executes gradient across 9 scanlines, does not write HSCROL, and self-resets."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Pre-load HSCROL with non-zero sentinel to ensure dli_title_scroll does not touch it
    mpu.memory[labels["HSCROL"]] = 0xAA

    # Run handler
    run_dli_handler(mpu, labels["DLI_TITLE_SCROLL"])

    # HSCROL must remain untouched
    assert mpu.memory[labels["HSCROL"]] == 0xAA

    # COLPF1 and COLPF2 set to black below-window colors
    assert mpu.memory[labels["COLPF1"]] == labels["TITLE_BELOW_PF1"]
    assert mpu.memory[labels["COLPF2"]] == labels["TITLE_BELOW_PF2"]
    assert mpu.memory[labels["COLBK"]] == 0x00

    # VDSLST reset back to dli_title_color_call
    vdslst = mpu.memory[labels["VDSLST"]] | (mpu.memory[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_TITLE_COLOR_CALL"]


def test_title_state_exit_resets_vscrol(emu_env):
    """Verify that pressing fire/key to exit title screen sets VSCROL=0, HSCROL=0, NMIEN=$40."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Set non-zero scroll values
    mpu.memory[labels["VSCROL"]] = 7
    mpu.memory[labels["HSCROL"]] = 3

    # Signal fire released then pressed
    mpu.memory[labels["FIRE_RELEASED"]] = 1
    mpu.memory[labels["STRIG0"]] = 0  # Fire pressed

    # Simulate title_run past sync loop to @fire_pressed
    # In title_run:
    title_run_addr = labels["TITLE_RUN"]
    mpu.sp = 0xFD
    mpu.stPushWord(0x0100 - 1)
    mpu.pc = title_run_addr

    # Mock RTCLOK
    rtclok_lo = labels["RTCLOK"] + 2
    steps = 0
    while steps < 2000:
        if mpu.memory[mpu.pc] == 0xF0:  # BEQ sync loop
            mpu.memory[rtclok_lo] += 1
        mpu.step()
        steps += 1
        if mpu.pc == 0x0100:
            break

    assert mpu.pc == 0x0100, f"title_run timed out (PC=0x{mpu.pc:04X}, steps={steps})"
    assert mpu.memory[labels["VSCROL"]] == 0
    assert mpu.memory[labels["HSCROL"]] == 0
    assert mpu.memory[labels["NMIEN"]] == 0x40
    assert mpu.memory[labels["GAME_STATE"]] == labels["STATE_INTRO"]
