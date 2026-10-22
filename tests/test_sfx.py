"""Unit and py65 emulation tests for POKEY sound effects engine (engine/sfx.asm)."""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU


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


# ==============================================================================
# SFX Tests
# ==============================================================================


def test_sfx_symbols_present(emu_env):
    """Verify that all required SFX routines and variables exist in the symbol table."""
    _, labels = emu_env
    required = [
        "SFX_INIT",
        "SFX_STOP_ALL",
        "SFX_PLAY_STEP",
        "SFX_PLAY_JUMP",
        "SFX_PLAY_FALL",
        "SFX_STOP_FALL",
        "SFX_PLAY_DEATH",
        "SFX_UPDATE",
        "SFX_WALK_TIMER",
        "SFX_JUMP_TIMER",
        "SFX_FALL_ACTIVE",
        "SFX_DEATH_TIMER",
    ]
    for sym in required:
        assert sym in labels, f"Missing required SFX symbol '{sym}'"


def test_sfx_init_and_silence(emu_env):
    """Verify that sfx_init zeroes all timers and silences POKEY."""
    mpu, labels = emu_env

    # Corrupt timers and audio registers
    mpu.memory[labels["SFX_WALK_TIMER"]] = 5
    mpu.memory[labels["SFX_JUMP_TIMER"]] = 10
    mpu.memory[labels["SFX_FALL_ACTIVE"]] = 1
    mpu.memory[labels["SFX_DEATH_TIMER"]] = 50
    mpu.memory[labels["AUDC1"]] = 0xA8
    mpu.memory[labels["AUDC2"]] = 0x88

    run_subroutine(mpu, labels["SFX_INIT"])

    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 0
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 0
    assert mpu.memory[labels["SFX_DEATH_TIMER"]] == 0
    assert mpu.memory[labels["AUDC1"]] == 0
    assert mpu.memory[labels["AUDC2"]] == 0
    assert mpu.memory[labels["SKCTL"]] == 3
    assert mpu.memory[labels["AUDCTL"]] == 0


def test_sfx_footstep_lifecycle(emu_env):
    """Verify triggering footstep SFX and frame-by-frame envelope advancement."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["SFX_INIT"])
    run_subroutine(mpu, labels["SFX_PLAY_STEP"])

    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 3
    assert mpu.memory[labels["AUDF1"]] == 0x28
    assert mpu.memory[labels["AUDC1"]] == 0xC5

    # Advance 1 frame
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 2
    assert mpu.memory[labels["AUDF1"]] == 0x34
    assert mpu.memory[labels["AUDC1"]] == 0xC3

    # Advance 2nd frame
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 1
    assert mpu.memory[labels["AUDF1"]] == 0x40
    assert mpu.memory[labels["AUDC1"]] == 0xC1

    # Advance 3rd frame (finishes and silences Ch 1)
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0
    assert mpu.memory[labels["AUDC1"]] == 0
    assert mpu.memory[labels["AUDF1"]] == 0


def test_sfx_jump_overrides_walk(emu_env):
    """Verify that jumping preempts footstep and produces upward pitch sweep."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["SFX_INIT"])
    run_subroutine(mpu, labels["SFX_PLAY_STEP"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 3

    # Play jump while step is active
    run_subroutine(mpu, labels["SFX_PLAY_JUMP"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0  # Walk preempted
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 14
    assert mpu.memory[labels["AUDF1"]] == 0x84
    assert mpu.memory[labels["AUDC1"]] == 0xA7

    # Walk cannot interrupt jump
    run_subroutine(mpu, labels["SFX_PLAY_STEP"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 14

    # Advance 13 more frames to complete jump
    for _ in range(13):
        run_subroutine(mpu, labels["SFX_UPDATE"])
        assert (mpu.memory[labels["AUDC1"]] & 0xF0) == 0xA0  # Pure tone

    # Final frame silences Ch 1
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 0
    assert mpu.memory[labels["AUDC1"]] == 0


def test_sfx_fall_auto_tracking(emu_env):
    """Verify that sfx_update plays wind whoosh on Ch 2 when player is falling, and stops when landing."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["SFX_INIT"])

    # Idle player -> no fall sound
    mpu.memory[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 0
    assert mpu.memory[labels["AUDC2"]] == 0

    # Fall state -> fall sound activates on Ch 2
    mpu.memory[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_FALL"]
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 1
    assert (mpu.memory[labels["AUDC2"]] & 0xF0) == 0x80  # Poly17 noise

    # Update again while falling -> continues playing
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 1
    assert (mpu.memory[labels["AUDC2"]] & 0xF0) == 0x80

    # Hero lands -> stops fall sound immediately
    mpu.memory[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 0
    assert mpu.memory[labels["AUDC2"]] == 0
    assert mpu.memory[labels["AUDF2"]] == 0


def test_sfx_death_full_sequence_and_priority(emu_env):
    """Verify death SFX sequence: crash impact on Ch 1+2, followed by mournful arpeggio."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["SFX_INIT"])

    # Activate jump and fall sounds
    run_subroutine(mpu, labels["SFX_PLAY_JUMP"])
    mpu.memory[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_FALL"]
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 1

    # Trigger death
    run_subroutine(mpu, labels["SFX_PLAY_DEATH"])
    assert mpu.memory[labels["SFX_DEATH_TIMER"]] == 72
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 0
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 0

    # Frame 0 of death: Crash impact
    assert mpu.memory[labels["AUDC1"]] == 0x8C
    assert mpu.memory[labels["AUDC2"]] == 0xC8

    # Other sounds cannot interrupt death
    run_subroutine(mpu, labels["SFX_PLAY_STEP"])
    run_subroutine(mpu, labels["SFX_PLAY_JUMP"])
    run_subroutine(mpu, labels["SFX_PLAY_FALL"])
    assert mpu.memory[labels["SFX_WALK_TIMER"]] == 0
    assert mpu.memory[labels["SFX_JUMP_TIMER"]] == 0
    assert mpu.memory[labels["SFX_FALL_ACTIVE"]] == 0

    # Step through 8 crash decay frames (frames 71..64)
    for _ in range(8):
        run_subroutine(mpu, labels["SFX_UPDATE"])

    assert mpu.memory[labels["SFX_DEATH_TIMER"]] == 64
    # Next frame starts arpeggio on Ch 1, and silences Ch 2
    run_subroutine(mpu, labels["SFX_UPDATE"])
    assert mpu.memory[labels["AUDC2"]] == 0
    assert (mpu.memory[labels["AUDC1"]] & 0xF0) == 0xA0  # Pure tone note

    # Step through remaining frames until timer reaches 0
    remaining = mpu.memory[labels["SFX_DEATH_TIMER"]]
    for _ in range(remaining):
        run_subroutine(mpu, labels["SFX_UPDATE"])

    assert mpu.memory[labels["SFX_DEATH_TIMER"]] == 0
    assert mpu.memory[labels["AUDC1"]] == 0
    assert mpu.memory[labels["AUDC2"]] == 0
