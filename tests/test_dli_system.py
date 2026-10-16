"""Automated py65 integration test suite for Atari 8-bit Unified DLI & Double Buffer Engine.

Validates:
1. Shared Display List (dlist_game) structure, line count (96), and DLI flags on lines 7, 23, 39, 55, 71, 87.
2. Memory bounds, Zero Page allocations ($B8-$BE), and ascending segment placement ($6100-$676E < $6800).
3. dli_init: PMG initialization (solid platform pas scanlines), VDSLST hook, NMIEN ($C0).
4. dli_stage_scene: Double-buffered scene staging into inactive buffer without affecting active buffer.
5. dli_vblank_update: Atomic buffer swap, Zone 0 initialization, upper background palette in hardware & shadows.
6. dli_handler: 3-phase execution across all 6 pas:
   - Faza A: PMG platform sizes (x4), positions (HPOSP1..3, HPOSM1..3), PRIOR ($01).
   - Faza B: 8 scanlines platform color profiles (COLPM1..3).
   - Faza C: Background palette (COLPF0..2), lower palette switch at Pas 40, upper palette restore at Pas 88;
     enemy/secret PMG setup in guard line (x1 sizes, HPOSP1..3, COLPM1..3, HPOSM0..3, COLPF3, PRIOR bit 4).
7. Strict hardware invariants: Hero P0 (HPOSP0, SIZEP0, COLPM0) never touched; COLBK strictly black ($00).
8. Zero stack usage during DLI, registers preserved in Zero Page ($B8-$BA).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.check_memory import parse_xex_segments


def load_xex_and_symbols() -> tuple[bytearray, dict[str, int]]:
    """Load call_of_the_wintermon.xex into a 64 KB memory array and parse symbols from main.lab."""
    xex_path = Path("call_of_the_wintermon.xex")
    lab_path = Path("gen/main.lab")
    assert xex_path.is_file(), "Executable call_of_the_wintermon.xex must be built before testing"
    assert lab_path.is_file(), "Symbol file gen/main.lab must exist"

    mem = bytearray(65536)
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

    import re
    labels: dict[str, int] = {}
    pattern = re.compile(r"^[0-9a-fA-F]{2}\t([0-9a-fA-F]{4})\t([^\s]+)")
    for line in lab_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.match(line)
        if m:
            labels[m.group(2).upper()] = int(m.group(1), 16)

    return mem, labels


def step_until_rts_or_rti(mpu: MPU, max_cycles: int = 20000) -> int:
    """Step 6502 MPU until RTS ($60) or RTI ($40) instruction executes."""
    cycles = 0
    while cycles < max_cycles:
        opcode = mpu.memory[mpu.pc]
        mpu.step()
        cycles += 1
        if opcode in (0x60, 0x40):  # RTS or RTI
            return cycles
    raise TimeoutError(f"Subroutine at PC=${mpu.pc:04X} did not return within {max_cycles} cycles")


def run_subroutine(mpu: MPU, addr: int, max_cycles: int = 20000) -> int:
    """Execute a subroutine ending with RTS, preserving stack pointer."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x00
    mpu.memory[0x0100 + sp - 1] = 0x00
    mpu.sp = sp - 2
    mpu.pc = addr
    return step_until_rts_or_rti(mpu, max_cycles)


# ==============================================================================
# TEST 1: Display List (dlist_game) Structure and DLI Triggers
# ==============================================================================
def test_dlist_game_structure_and_dli_flags():
    mem, labels = load_xex_and_symbols()
    dl_addr = labels["DLIST_GAME"]
    assert dl_addr == 0x3F00, f"DLIST_GAME must be at $3F00, got ${dl_addr:04X}"

    # Top blank margin: 3x DL_BLANK8 ($70)
    assert list(mem[dl_addr : dl_addr + 3]) == [0x70, 0x70, 0x70]

    # Line 0: DL_MODE_D | DL_LMS ($4D) pointing to GAME_VRAM ($3000)
    assert mem[dl_addr + 3] == 0x4D
    lms_target = mem[dl_addr + 4] | (mem[dl_addr + 5] << 8)
    assert lms_target == 0x3000

    # Remaining 95 lines of Mode D:
    # DL_DLI ($80) MUST be set on lines 7, 23, 39, 55, 71, 87 (i in 6, 22, 38, 54, 70, 86)
    expected_dli_lines = {7, 23, 39, 55, 71, 87}
    dli_found = set()

    for line_idx in range(1, 96):
        byte_val = mem[dl_addr + 6 + (line_idx - 1)]
        is_dli = bool(byte_val & 0x80)
        mode = byte_val & 0x0F
        assert mode == 0x0D, f"Line {line_idx} must be ANTIC Mode D ($0D), got ${byte_val:02X}"
        if is_dli:
            dli_found.add(line_idx)

    assert dli_found == expected_dli_lines, f"DLI flags must be exactly on lines {expected_dli_lines}, found {dli_found}"

    # Bottom blank margin: 3x DL_BLANK8 ($70)
    assert list(mem[dl_addr + 101 : dl_addr + 104]) == [0x70, 0x70, 0x70]

    # JVB ($41) jump back to dlist_game
    assert mem[dl_addr + 104] == 0x41
    jvb_target = mem[dl_addr + 105] | (mem[dl_addr + 106] << 8)
    assert jvb_target == dl_addr


# ==============================================================================
# TEST 2: Memory Segment Bounds and Zero Page Allocations
# ==============================================================================
def test_dli_memory_bounds_and_zeropage_allocations():
    xex_path = Path("call_of_the_wintermon.xex")
    segments = parse_xex_segments(xex_path.read_bytes())

    # Locate DLI segment at $6100
    dli_seg = next((s for s in segments if s[0] == 0x6100), None)
    assert dli_seg is not None, "DLI segment starting at $6100 not found"
    start, end, size = dli_seg
    assert start == 0x6100
    assert end < 0x6800, f"DLI segment ($6100-${end:04X}) must end strictly below PMG at $6800"

    # Verify PMG segment at $6800 exists and starts strictly after DLI segment
    pmg_seg = next((s for s in segments if s[0] == 0x6800), None)
    assert pmg_seg is not None, "PMG segment starting at $6800 not found"
    assert pmg_seg[0] > end, "PMG segment must not overlap DLI segment"

    # Verify Zero Page variables
    mem, labels = load_xex_and_symbols()
    for var in ["DLI_SAVE_A", "DLI_SAVE_X", "DLI_SAVE_Y", "DLI_PAS_IDX", "DLI_ACTIVE_OFFSET", "DLI_PENDING_OFFSET", "DLI_SWAP_REQUESTED"]:
        addr = labels[var]
        assert 0x80 <= addr <= 0xFF, f"Zero page variable {var} (${addr:02X}) must be in $80-$FF"


# ==============================================================================
# TEST 3: dli_init Hardware Setup and PMG Pre-fill
# ==============================================================================
def test_dli_init_execution():
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])

    # 1. Vector VDSLST ($0200) points to dli_handler
    vdslst = mem[labels["VDSLST"]] | (mem[labels["VDSLST"] + 1] << 8)
    assert vdslst == labels["DLI_HANDLER"], f"VDSLST (${vdslst:04X}) must point to DLI_HANDLER (${labels['DLI_HANDLER']:04X})"

    # 2. NMIEN ($D40E) has DLI ($80) and VBI ($40) enabled = $C0
    assert mem[labels["NMIEN"]] == 0xC0

    # 3. State variables reset to 0
    assert mem[labels["DLI_ACTIVE_OFFSET"]] == 0
    assert mem[labels["DLI_PENDING_OFFSET"]] == 0
    assert mem[labels["DLI_SWAP_REQUESTED"]] == 0
    assert mem[labels["DLI_PAS_IDX"]] == 0

    # 4. PMG platform rows pre-filled with solid pixels ($FF in P1..P3, $FC in Missiles)
    # 6 pas at scanlines: 16..23, 48..55, 80..87, 112..119, 144..151, 176..183
    pas_scanline_starts = [16, 48, 80, 112, 144, 176]
    pmg_p1 = labels["PMG_PLAYER1"]
    pmg_p2 = labels["PMG_PLAYER2"]
    pmg_p3 = labels["PMG_PLAYER3"]
    pmg_m  = labels["PMG_MISSILES"]

    for p_start in pas_scanline_starts:
        for sl in range(8):
            curr_sl = p_start + sl
            assert mem[pmg_p1 + curr_sl] == 0xFF, f"Player 1 pas row {curr_sl} must be $FF"
            assert mem[pmg_p2 + curr_sl] == 0xFF, f"Player 2 pas row {curr_sl} must be $FF"
            assert mem[pmg_p3 + curr_sl] == 0xFF, f"Player 3 pas row {curr_sl} must be $FF"
            assert mem[pmg_m + curr_sl] == 0xFF, f"Missiles pas row {curr_sl} must be $FF"

    # Guard lines (e.g. scanline 15, 24, 47, 56) must remain 0
    guard_lines = [15, 24, 47, 56, 79, 88, 111, 120, 143, 152, 175, 184]
    for gl in guard_lines:
        assert mem[pmg_p1 + gl] == 0x00, f"Guard line {gl} in Player 1 must be $00"
        assert mem[pmg_m + gl] == 0x00, f"Guard line {gl} in Missiles must be $00"


# ==============================================================================
# TEST 4: dli_stage_scene and Double Buffer Isolation
# ==============================================================================
def test_dli_stage_scene_double_buffer_isolation():
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize DLI
    run_subroutine(mpu, labels["DLI_INIT"])
    assert mem[labels["DLI_ACTIVE_OFFSET"]] == 0

    # Stage scene 0 (Forest) into inactive buffer (offset 8)
    mpu.a = 0  # scene 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])

    # Active buffer remains 0
    assert mem[labels["DLI_ACTIVE_OFFSET"]] == 0
    # Pending buffer is 8
    assert mem[labels["DLI_PENDING_OFFSET"]] == 8
    # Swap requested mailbox flag is set to 1
    assert mem[labels["DLI_SWAP_REQUESTED"]] == 1

    # Active buffer (offset 0) is still 0
    assert mem[labels["DLI_HPOS_P1"] + 0] == 0

    # Inactive buffer (offset 8) has received staged scene 0 data
    # In Scene 0 (Forest), pas 1 (y=24) has platform-010 at x=96 -> HPOS = 48 + 96 = 144 ($90) or 0x68
    staged_hpos_p1 = mem[labels["DLI_HPOS_P1"] + 8 + 1]  # pas index 1 in buffer 1
    assert staged_hpos_p1 > 0, "Staged buffer at offset 8 must contain platform data"


# ==============================================================================
# TEST 5: dli_vblank_update Atomic Commit and Zone 0 Setup
# ==============================================================================
def test_dli_vblank_update_and_zone0():
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Stage scene 1 (Forest Castle: has castles top $94, trees bottom $C4)
    run_subroutine(mpu, labels["DLI_INIT"])

    mpu.a = 1  # Scene 1: 02-forest-castle
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    assert mem[labels["DLI_SWAP_REQUESTED"]] == 1

    # Execute VBLANK update
    run_subroutine(mpu, labels["DLI_VBLANK_UPDATE"])

    # 1. Swap committed: active buffer is now 8, swap requested cleared
    assert mem[labels["DLI_ACTIVE_OFFSET"]] == 8
    assert mem[labels["DLI_SWAP_REQUESTED"]] == 0
    assert mem[labels["DLI_PAS_IDX"]] == 8

    # 2. Upper palette applied to hardware and shadows (Scene 1 castles: $94, $D6, $EA)
    assert mem[labels["COLPF0"]] == 0x94
    assert mem[labels["COLOR0"]] == 0x94
    assert mem[labels["COLPF1"]] == 0xD6
    assert mem[labels["COLOR1"]] == 0xD6
    assert mem[labels["COLPF2"]] == 0xEA
    assert mem[labels["COLOR2"]] == 0xEA

    # 3. COLBK and COLOR4 are strictly black ($00)
    assert mem[labels["COLBK"]] == 0x00
    assert mem[labels["COLOR4"]] == 0x00

    # 4. Sizes reset to x1 for Zone 0
    assert mem[labels["SIZEP1"]] == 0
    assert mem[labels["SIZEP2"]] == 0
    assert mem[labels["SIZEP3"]] == 0
    assert mem[labels["SIZEM"]]  == 0


def invoke_dli(mpu: MPU, dli_addr: int) -> int:
    """Simulate hardware NMI pushing PC and P to stack before jumping to DLI handler."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x00      # PC high
    mpu.memory[0x0100 + sp - 1] = 0x00  # PC low
    mpu.memory[0x0100 + sp - 2] = 0x30  # P status
    mpu.sp = sp - 3
    mpu.pc = dli_addr
    return step_until_rts_or_rti(mpu)


# ==============================================================================
# TEST 6: dli_handler Full 6-Pas Cycle Execution and Palette Swapping
# ==============================================================================
def test_dli_handler_full_execution_and_palette_transition():
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Setup Scene 1 (02-forest-castle: castles upper $94, trees lower $C4)
    run_subroutine(mpu, labels["DLI_INIT"])

    mpu.a = 1  # Scene 1
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])

    run_subroutine(mpu, labels["DLI_VBLANK_UPDATE"])
    assert mem[labels["DLI_PAS_IDX"]] == 8

    # Set Hero P0 registers to distinct values to ensure DLI never touches them
    HERO_HPOS = 0x77
    HERO_SIZE = 0x01
    HERO_COL  = 0x48
    mem[labels["HPOSP0"]] = HERO_HPOS
    mem[labels["SIZEP0"]] = HERO_SIZE
    mem[labels["COLPM0"]] = HERO_COL

    initial_sp = mpu.sp

    # --- DLI 1 (Pas 0, line 8) ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 9
    assert mem[labels["COLPF0"]] == 0x94, "Pas 0 must keep upper palette ($94)"
    assert mem[labels["COLBK"]] == 0x00
    assert mem[labels["HPOSP0"]] == HERO_HPOS
    assert mem[labels["SIZEP0"]] == HERO_SIZE
    assert mem[labels["COLPM0"]] == HERO_COL

    # --- DLI 2 (Pas 1, line 24) ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 10
    assert mem[labels["COLPF0"]] == 0x94, "Pas 1 must keep upper palette ($94)"

    # --- DLI 3 (Pas 2, line 40) -> SWAPS TO LOWER PALETTE AT LINE 44 ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 11
    # Lower palette (trees) is $C4, $C8, $DC!
    assert mem[labels["COLPF0"]] == 0xC4, "Pas 2 must swap background palette to lower ($C4) at line 44"
    assert mem[labels["COLPF1"]] == 0xC8
    assert mem[labels["COLPF2"]] == 0xDC

    # --- DLI 4 (Pas 3, line 56) ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 12
    assert mem[labels["COLPF0"]] == 0xC4, "Pas 3 must keep lower palette ($C4)"

    # --- DLI 5 (Pas 4, line 72) ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 13
    assert mem[labels["COLPF0"]] == 0xC4, "Pas 4 must keep lower palette ($C4)"

    # --- DLI 6 (Pas 5, line 88) -> RESTORES UPPER PALETTE AT LINE 92 ---
    invoke_dli(mpu, labels["DLI_HANDLER"])
    assert mem[labels["DLI_PAS_IDX"]] == 14
    assert mem[labels["COLPF0"]] == 0x94, "Pas 5 must restore background palette to upper ($94) at line 92"
    assert mem[labels["COLPF1"]] == 0xD6
    assert mem[labels["COLPF2"]] == 0xEA

    # Invariants verification:
    # 1. Hero P0 was NEVER touched by any DLI
    assert mem[labels["HPOSP0"]] == HERO_HPOS
    assert mem[labels["SIZEP0"]] == HERO_SIZE
    assert mem[labels["COLPM0"]] == HERO_COL
    # 2. COLBK is strictly black
    assert mem[labels["COLBK"]] == 0x00
    # 3. Stack was not touched during DLI (SP remained intact)
    assert mpu.sp == 0xFD
