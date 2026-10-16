"""Unit and py65 emulation tests for Intro screen background music (music/intro.dsl)."""

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


# ==============================================================================
# Unit Tests for compile_music DSL support
# ==============================================================================


def test_compile_music_dsl_support(tmp_path: Path):
    """Verify that compile_music compiles .dsl files into valid MADS assembly."""
    dsl_src = Path("music/intro.dsl")
    assert dsl_src.is_file(), "music/intro.dsl must exist"

    out_asm = tmp_path / "test_intro.asm"
    ret = compile_music(dsl_src, out_asm, song_label="music_intro_data")
    assert ret == 0
    assert out_asm.is_file()

    content = out_asm.read_text(encoding="utf-8")
    assert "music_intro_data:" in content
    assert "music_intro_data_instruments:" in content
    assert "music_intro_data_sequence:" in content


# ==============================================================================
# Emulation Integration Tests
# ==============================================================================


def test_intro_music_symbols_present(emu_env):
    """Verify that all intro audio routines and song tables are present in symbol table."""
    _, labels = emu_env
    required = [
        "AUDIO_PLAY_INTRO",
        "AUDIO_PLAY_TITLE",
        "AUDIO_UPDATE",
        "AUDIO_STOP",
        "MUSIC_INTRO_DATA",
        "MUSIC_INTRO_DATA_INSTRUMENTS",
        "MUSIC_INTRO_DATA_SEQUENCE",
        "INTRO_INIT",
        "INTRO_RUN",
    ]
    for sym in required:
        assert sym in labels, f"Missing symbol {sym} in gen/main.lab"


def test_audio_play_intro_initialization(emu_env):
    """Verify that audio_play_intro initializes the POKEY player with music_intro_data."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["AUDIO_PLAY_INTRO"])

    # Check song_ptr points to music_intro_data
    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_INTRO_DATA"]

    # Tempo divider from compiled music header (frames_per_tick)
    expected_tempo = mpu.memory[labels["MUSIC_INTRO_DATA"]]
    assert mpu.memory[labels["TEMPO_DIVIDER"]] == expected_tempo

    # 16-bit bass mode: audctl_mode is $10
    assert mpu.memory[labels["AUDCTL_MODE"]] == 0x10

    # Player state must be playing (1)
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1


def test_audio_update_advances_frame(emu_env):
    """Verify that audio_update advances frame ticks and runs without crash."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["AUDIO_PLAY_INTRO"])
    assert mpu.memory[labels["TICK_COUNTER"]] == 1  # music_play sets 1 for immediate row update

    expected_tempo = mpu.memory[labels["MUSIC_INTRO_DATA"]]
    # Run 1 frame update (triggers row update and resets tick_counter to tempo_divider)
    run_subroutine(mpu, labels["AUDIO_UPDATE"])
    assert mpu.memory[labels["TICK_COUNTER"]] == expected_tempo

    # Run next frame update (decrements tick_counter to expected_tempo - 1)
    run_subroutine(mpu, labels["AUDIO_UPDATE"])
    assert mpu.memory[labels["TICK_COUNTER"]] == expected_tempo - 1


def test_audio_stop_silences_channels(emu_env):
    """Verify that audio_stop stops playback and zeroes all POKEY volume registers."""
    mpu, labels = emu_env

    run_subroutine(mpu, labels["AUDIO_PLAY_INTRO"])
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1

    run_subroutine(mpu, labels["AUDIO_STOP"])
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 0
    assert mpu.memory[labels["AUDC1_REG"]] == 0
    assert mpu.memory[labels["AUDC2_REG"]] == 0
    assert mpu.memory[labels["AUDC3_REG"]] == 0
    assert mpu.memory[labels["AUDC4_REG"]] == 0


def test_intro_init_triggers_intro_music(emu_env):
    """Verify that intro_init triggers intro music playback."""
    mpu, labels = emu_env

    # Silence/poison player state
    run_subroutine(mpu, labels["AUDIO_STOP"])
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 0

    # Call intro_init
    run_subroutine(mpu, labels["INTRO_INIT"])

    # Must now be playing intro music
    assert mpu.memory[labels["MUSIC_PLAYING"]] == 1
    song_ptr = mpu.memory[labels["SONG_PTR_LO"]] | (mpu.memory[labels["SONG_PTR_HI"]] << 8)
    assert song_ptr == labels["MUSIC_INTRO_DATA"]
