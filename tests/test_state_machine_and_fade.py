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


def test_title_init_first_run_starts_at_black(emu_env):
    """When title_first_run == 1, title_init must set colors to $00 and fade_frame to 0."""
    mpu, labels = emu_env

    # Setup first run state
    mpu.memory[labels["TITLE_FIRST_RUN"]] = 1
    mpu.memory[labels["FADE_FRAME"]] = 99
    mpu.memory[labels["COLOR0"]] = 0xC4
    mpu.memory[labels["COLOR1"]] = 0xCA
    mpu.memory[labels["COLOR2"]] = 0xEE

    run_subroutine(mpu, labels["TITLE_INIT"])

    assert mpu.memory[labels["FADE_FRAME"]] == 0
    assert mpu.memory[labels["COLOR0"]] == 0x00
    assert mpu.memory[labels["COLPF0"]] == 0x00
    assert mpu.memory[labels["COLOR1"]] == 0x00
    assert mpu.memory[labels["COLPF1"]] == 0x00
    assert mpu.memory[labels["COLOR2"]] == 0x00
    assert mpu.memory[labels["COLPF2"]] == 0x00
    assert mpu.memory[labels["COLBK"]] == 0x00


def test_title_init_subsequent_run_skips_fade(emu_env):
    """When title_first_run == 0 (e.g. returning from game over), colors must be full brightness immediately."""
    mpu, labels = emu_env

    # Setup return from game over (title_first_run == 0)
    mpu.memory[labels["TITLE_FIRST_RUN"]] = 0
    mpu.memory[labels["FADE_FRAME"]] = 0
    mpu.memory[labels["COLOR0"]] = 0x00
    mpu.memory[labels["COLOR1"]] = 0x00
    mpu.memory[labels["COLOR2"]] = 0x00

    run_subroutine(mpu, labels["TITLE_INIT"])

    # Must be set directly to full brightness ($C4, $CA, $EE), fade_frame to 28
    assert mpu.memory[labels["FADE_FRAME"]] == 28
    assert mpu.memory[labels["COLOR0"]] == 0xC4
    assert mpu.memory[labels["COLPF0"]] == 0xC4
    assert mpu.memory[labels["COLOR1"]] == 0xCA
    assert mpu.memory[labels["COLPF1"]] == 0xCA
    assert mpu.memory[labels["COLOR2"]] == 0xEE
    assert mpu.memory[labels["COLPF2"]] == 0xEE


def test_fade_frame_progression_over_28_frames():
    """Verify the 8-step fade progression for 28-frame title screen fade-in."""
    title_fade_c0 = [0x00, 0xC0, 0xC0, 0xC2, 0xC2, 0xC4, 0xC4, 0xC4]
    title_fade_c1 = [0x00, 0xC2, 0xC4, 0xC6, 0xC8, 0xCA, 0xCA, 0xCA]
    title_fade_c2 = [0x00, 0xE2, 0xE4, 0xE6, 0xE8, 0xEA, 0xEC, 0xEE]

    for frame in range(1, 29):
        step = frame >> 2
        c0 = title_fade_c0[step]
        c1 = title_fade_c1[step]
        c2 = title_fade_c2[step]
        if frame < 4:
            assert (c0, c1, c2) == (0x00, 0x00, 0x00)
        if frame >= 28:
            assert (c0, c1, c2) == (0xC4, 0xCA, 0xEE)


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

