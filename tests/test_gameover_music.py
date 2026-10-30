"""Unit and py65 emulation tests for Game Over background music (failure and victory)."""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from scripts.compile_music import compile_music


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


def test_gameover_music_symbols_present(emu_env):
    """Verify that all gameover and victory audio routines and song tables are present."""
    _, labels = emu_env
    required = [
        "AUDIO_PLAY_GAMEOVER",
        "AUDIO_PLAY_VICTORY",
        "AUDIO_UPDATE",
        "AUDIO_STOP",
        "MUSIC_GAMEOVER_DATA",
        "MUSIC_VICTORY_DATA",
        "GAMEOVER_INIT",
        "GAMEOVER_RUN",
    ]
    for sym in required:
        assert sym in labels, f"Missing symbol {sym} in gen/main.lab"


def test_audio_play_gameover_initialization(emu_env):
    """Verify that audio_play_gameover initializes the POKEY player with music_gameover_data."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["AUDIO_PLAY_GAMEOVER"])

    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_GAMEOVER_DATA"]
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1


def test_audio_play_victory_initialization(emu_env):
    """Verify that audio_play_victory initializes the POKEY player with music_victory_data."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["AUDIO_PLAY_VICTORY"])

    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_VICTORY_DATA"]
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1


def test_gameover_init_failure_plays_gameover_music(emu_env):
    """Verify that gameover_init plays game_over music when game_result is FAILURE."""
    mpu, labels = emu_env

    # Setup game_result = GAMEOVER_FAILURE (0)
    mpu.memory[labels["GAME_RESULT"]] = 0
    run_subroutine(mpu, labels["AUDIO_STOP"])
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 0

    run_subroutine(mpu, labels["GAMEOVER_INIT"])

    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1
    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_GAMEOVER_DATA"]


def test_gameover_init_success_plays_victory_music(emu_env):
    """Verify that gameover_init plays victory music when game_result is SUCCESS."""
    mpu, labels = emu_env

    # Setup game_result = GAME_SUCCESS (2)
    mpu.memory[labels["GAME_RESULT"]] = labels["GAME_SUCCESS"]
    run_subroutine(mpu, labels["AUDIO_STOP"])
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 0

    run_subroutine(mpu, labels["GAMEOVER_INIT"])

    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1
    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_VICTORY_DATA"]
