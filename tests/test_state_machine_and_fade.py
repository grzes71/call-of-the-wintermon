"""Pytest harness using py65 6502 emulation to verify state machine and title screen fade-in logic."""

import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU


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


def run_subroutine(mpu: MPU, addr: int, max_steps: int = 100_000) -> None:
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
    assert mpu.pc == 0x0100, f"Subroutine at 0x{addr:04X} did not return within {max_steps} steps (PC=0x{mpu.pc:04X})"


def run_dli_interrupt(mpu: MPU, addr: int, max_cycles: int = 50_000) -> int:
    """Simulate hardware NMI pushing PC and P to stack before jumping to DLI handler."""
    sp = mpu.sp
    mpu.memory[0x0100 + sp] = 0x01      # PC high ($01)
    mpu.memory[0x0100 + sp - 1] = 0x00  # PC low ($00) -> return to $0100
    mpu.memory[0x0100 + sp - 2] = 0x30  # P status
    mpu.sp = sp - 3
    mpu.pc = addr
    cycles = 0
    while cycles < max_cycles:
        opcode = mpu.memory[mpu.pc]
        mpu.step()
        cycles += 1
        if opcode == 0x40 and mpu.sp == sp:  # RTI
            return cycles
    raise TimeoutError(f"DLI handler at PC=${mpu.pc:04X} timed out")


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


def test_title_init_immediate_full_brightness_and_normal_playfield(emu_env):
    """title_init must set colors to full brightness immediately and configure Normal playfield ($22)."""
    mpu, labels = emu_env

    mpu.memory[labels["COLOR0"]] = 0x00
    mpu.memory[labels["COLOR1"]] = 0x00
    mpu.memory[labels["COLOR2"]] = 0x00

    run_subroutine(mpu, labels["TITLE_INIT"])

    assert mpu.memory[labels["COLOR0"]] == 0xC4
    assert mpu.memory[labels["COLPF0"]] == 0xC4
    assert mpu.memory[labels["COLOR1"]] == 0xCA
    assert mpu.memory[labels["COLPF1"]] == 0xCA
    assert mpu.memory[labels["COLOR2"]] == 0xEE
    assert mpu.memory[labels["COLPF2"]] == 0xEE
    assert mpu.memory[labels["COLBK"]] == 0x00
    assert mpu.memory[labels["SDMCTL"]] == 0x22
    assert mpu.memory[labels["DMACTL"]] == 0x22


def test_title_scroll_rainbow_dli(emu_env):
    """Verify DLI renders 9-scanline rainbow ($C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0, $C0) on COLPF2 and restores state."""
    mpu, labels = emu_env

    mpu.memory[labels["DMACTL"]] = 0x22
    mpu.memory[labels["HSCROL"]] = 0

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

    # 9 rainbow scanlines on COLPF2 followed by below-window color TITLE_BELOW_PF2 ($00)
    expected = [0xC0, 0xC2, 0xC4, 0xC6, 0xC6, 0xC4, 0xC2, 0xC0, 0xC0, labels["TITLE_BELOW_PF2"]]
    assert colpf2_writes == expected

    # State below scroll window: black background, black playfield colors
    assert mpu.memory[labels["DMACTL"]] == 0x22
    assert mpu.memory[labels["HSCROL"]] == 0
    assert mpu.memory[labels["COLPF1"]] == labels["TITLE_BELOW_PF1"]
    assert mpu.memory[labels["COLPF2"]] == labels["TITLE_BELOW_PF2"]
    assert mpu.memory[labels["COLBK"]] == 0x00


def test_scene_title_card_frame_progression(emu_env):
    """Verify that game_run advances scene title card: fade in -> hold 2s -> fade out -> playing."""
    mpu, labels = emu_env

    # 1. Initialize game state for scene 0
    mpu.memory[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["GAME_INIT"])

    # Verify initial setup
    assert mpu.memory[labels["GAME_PHASE"]] == 0  # GAME_PHASE_TITLE_IN
    assert mpu.memory[labels["COLOR1"]] == 0x00
    sdlst = mpu.memory[labels["SDLSTL"]] | (mpu.memory[labels["SDLSTH"]] << 8)
    assert sdlst == labels["DLIST_SCENE_TITLE"]

    # Patch VBLANK loop in game_run so it doesn't wait on real hardware VBLANK
    # In game_run, find the BEQ instruction and replace with NOPs ($EA, $EA)
    for offset in range(25):
        if mpu.memory[labels["GAME_RUN"] + offset] == 0xF0:
            mpu.memory[labels["GAME_RUN"] + offset] = 0xEA
            mpu.memory[labels["GAME_RUN"] + offset + 1] = 0xEA
            break

    # Prevent STRIG0 / CH from skipping
    mpu.memory[labels["STRIG0"]] = 1
    mpu.memory[labels["CH"]] = 0xFF

    # Phase 0: 24 frames of fade in (8 steps of 3 frames)
    for _ in range(24):
        assert mpu.memory[labels["GAME_PHASE"]] == 0
        run_subroutine(mpu, labels["GAME_RUN"])

    # At frame 24, transitioned to Phase 1 (TITLE_HOLD)
    assert mpu.memory[labels["GAME_PHASE"]] == 1
    assert mpu.memory[labels["COLOR1"]] == 0xCE

    # Phase 1: 100 frames of hold (~2.0s)
    for _ in range(100):
        assert mpu.memory[labels["GAME_PHASE"]] == 1
        assert mpu.memory[labels["COLOR1"]] == 0xCE
        run_subroutine(mpu, labels["GAME_RUN"])

    # At frame 124, transitioned to Phase 2 (TITLE_OUT)
    assert mpu.memory[labels["GAME_PHASE"]] == 2

    # Phase 2: 24 frames of fade out (8 steps of 3 frames)
    for _ in range(24):
        assert mpu.memory[labels["GAME_PHASE"]] == 2
        run_subroutine(mpu, labels["GAME_RUN"])

    # After fade out complete: transitioned to Phase 3 (GAME_PHASE_PLAYING)
    assert mpu.memory[labels["GAME_PHASE"]] == 3
    # Display list switched to dlist_game ($3F00)
    sdlst = mpu.memory[labels["SDLSTL"]] | (mpu.memory[labels["SDLSTH"]] << 8)
    assert sdlst == labels["DLIST_GAME"]
    assert sdlst == 0x3F00


def test_title_init_resets_game_state_and_active_scene_id(emu_env):
    """Verify that title_init resets active_scene_id to 0, lives to 3, cds to 0, and game_result to 0."""
    mpu, labels = emu_env

    # Simulate game won state after completing all scenes
    mpu.memory[labels["ACTIVE_SCENE_ID"]] = labels["SCENE_COUNT"]
    mpu.memory[labels["GAME_RESULT"]] = labels["GAME_SUCCESS"]
    mpu.memory[labels["PLAYER_LIVES"]] = 1
    mpu.memory[labels["PLAYER_CDS"]] = 42

    # Call title_init
    run_subroutine(mpu, labels["TITLE_INIT"])

    assert mpu.memory[labels["ACTIVE_SCENE_ID"]] == 0
    assert mpu.memory[labels["PLAYER_LIVES"]] == 3
    assert mpu.memory[labels["PLAYER_CDS"]] == 0
    assert mpu.memory[labels["GAME_RESULT"]] == labels["GAME_RESULT_NONE"]


def test_subroutines_reject_out_of_bounds_scene_id(emu_env):
    """Verify player_init, secrets_init, and status_line_init safely reject scene_id >= SCENE_COUNT."""
    mpu, labels = emu_env

    # 1. secrets_init with A = SCENE_COUNT
    mpu.memory[labels["SECRETS_COUNT"]] = 0x55
    mpu.a = labels["SCENE_COUNT"]
    run_subroutine(mpu, labels["SECRETS_INIT"])
    assert mpu.memory[labels["SECRETS_COUNT"]] == 0x55

    # 2. player_init with A = SCENE_COUNT
    mpu.memory[labels["PLAYER_X"]] = 0x77
    mpu.a = labels["SCENE_COUNT"]
    run_subroutine(mpu, labels["PLAYER_INIT"])
    assert mpu.memory[labels["PLAYER_X"]] == 0x77

    # 3. status_line_init with A = SCENE_COUNT
    mpu.memory[labels["STATUS_LINE_VRAM"]] = 0xAA
    mpu.a = labels["SCENE_COUNT"]
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])
    assert mpu.memory[labels["STATUS_LINE_VRAM"]] == 0xAA


