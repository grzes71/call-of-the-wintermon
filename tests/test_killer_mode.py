"""Automated py65 integration tests for Killer mode in Atari Call of the Wintermoon.

Verifies:
1. Secret collection with killer flag sets player_killer_timer to 250 (5 seconds).
2. Normal secret collection leaves player_killer_timer unchanged.
3. Player update decrements player_killer_timer, modulates COLPM0/PCOLR0 luminance,
   and restores player_color when timer reaches 0.
4. Player collision with enemy while killer mode is inactive triggers player death.
5. Player collision with enemy while killer mode is active eliminates the enemy
   (clears PMG memory, DLI HPOS, deactivates enemy) and preserves player lives.
"""

from __future__ import annotations

from py65.devices.mpu6502 import MPU
import pytest

from tests.test_dli_system import load_xex_and_symbols, run_subroutine


def test_secret_collect_activates_killer_mode():
    """Collecting a secret with killer=1 sets player_killer_timer to 250."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)

    # Initialize stack and scene
    mpu.sp = 0xFD
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["GAME_INIT"])

    # Setup secret 0 as killer secret
    sec_killer_addr = labels["SECRETS_KILLER"]
    sec_active_addr = labels["SECRETS_ACTIVE"]
    mem[sec_killer_addr] = 1
    mem[sec_active_addr] = 1
    mem[labels["PLAYER_KILLER_TIMER"]] = 0

    # Collect secret 0
    mpu.x = 0
    run_subroutine(mpu, labels["SECRET_COLLECT"])

    # Timer must be activated to 250 (KILLER_MODE_DURATION)
    assert mem[labels["PLAYER_KILLER_TIMER"]] == 250

    # Now collect secret 1 with killer=0
    mem[sec_killer_addr + 1] = 0
    mem[sec_active_addr + 1] = 1
    mem[labels["PLAYER_KILLER_TIMER"]] = 0

    mpu.x = 1
    run_subroutine(mpu, labels["SECRET_COLLECT"])

    # Normal secret must not activate killer mode
    assert mem[labels["PLAYER_KILLER_TIMER"]] == 0


def test_killer_mode_timer_countdown_and_color_modulation():
    """player_update decrements timer, modulates COLPM0 luminance, and restores color on expiry."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD

    # Initialize player
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])

    base_color = mem[labels["PLAYER_COLOR"]]
    base_hue = base_color & 0xF0

    # Activate killer mode
    mem[labels["PLAYER_KILLER_TIMER"]] = 250
    # Make sure joystick STICK0 is neutral ($FF) and STRIG0 is not pressed ($01)
    mem[labels["STICK0"]] = 0xFF
    mem[labels["STRIG0"]] = 0x01

    # Step 1 frame
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_KILLER_TIMER"]] == 249
    expected_lum_1 = (249 >> 1) & 0x0E
    assert mem[labels["COLPM0"]] == (base_hue | expected_lum_1)
    assert mem[labels["PCOLR0"]] == (base_hue | expected_lum_1)

    # Step another frame (timer = 248 -> lum changes)
    run_subroutine(mpu, labels["PLAYER_UPDATE"])
    assert mem[labels["PLAYER_KILLER_TIMER"]] == 248
    expected_lum_2 = (248 >> 1) & 0x0E
    assert mem[labels["COLPM0"]] == (base_hue | expected_lum_2)

    # Now simulate countdown near expiration: set timer to 1
    mem[labels["PLAYER_KILLER_TIMER"]] = 1
    run_subroutine(mpu, labels["PLAYER_UPDATE"])

    # Timer should be 0 and color fully restored to base_color
    assert mem[labels["PLAYER_KILLER_TIMER"]] == 0
    assert mem[labels["COLPM0"]] == base_color
    assert mem[labels["PCOLR0"]] == base_color


def test_enemy_collision_kills_hero_when_killer_mode_inactive():
    """Colliding with an enemy while killer mode is inactive (timer=0) triggers hero death."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD

    # Setup alive player with 3 lives
    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    mem[labels["PLAYER_KILLER_TIMER"]] = 0
    mem[labels["PLAYER_X"]] = 50
    mem[labels["PLAYER_PMG_Y"]] = 100

    # Setup 1 active enemy overlapping player
    mem[labels["ENEMIES_COUNT"]] = 1
    mem[labels["ENEMIES_ACTIVE"]] = 1
    mem[labels["ENEMIES_X"]] = 50
    mem[labels["ENEMIES_PMG_Y"]] = 100
    mem[labels["ENEMIES_HEIGHT"]] = 8
    mem[labels["ENEMIES_CHANNEL"]] = 0
    mem[labels["ENEMIES_ZONE"]] = 1

    # Run collision check
    run_subroutine(mpu, labels["ENEMIES_CHECK_PLAYER_COLLISION"])

    # Lives should be decremented and death state initiated
    assert mem[labels["PLAYER_LIVES"]] == 2
    assert mem[labels["PLAYER_STATE"]] in (
        labels["PLAYER_STATE_DEATH"],
        labels["PLAYER_STATE_EMERGE"],
    )


def test_enemy_collision_eliminates_enemy_when_killer_mode_active():
    """Colliding with an enemy while killer mode is active eliminates the enemy and preserves hero lives."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD

    # Setup alive player with active killer mode
    mem[labels["PLAYER_LIVES"]] = 3
    mem[labels["PLAYER_STATE"]] = labels["PLAYER_STATE_IDLE"]
    mem[labels["PLAYER_KILLER_TIMER"]] = 100
    mem[labels["PLAYER_X"]] = 50
    mem[labels["PLAYER_PMG_Y"]] = 100

    # Setup 1 active enemy overlapping player
    mem[labels["ENEMIES_COUNT"]] = 1
    mem[labels["ENEMIES_ACTIVE"]] = 1
    mem[labels["ENEMIES_X"]] = 50
    mem[labels["ENEMIES_PMG_Y"]] = 100
    mem[labels["ENEMIES_HEIGHT"]] = 8
    mem[labels["ENEMIES_CHANNEL"]] = 0  # Player 1
    mem[labels["ENEMIES_ZONE"]] = 1

    # Fill some dummy enemy bitmap in PMG_PLAYER1
    pmg_p1_addr = labels["PMG_PLAYER1"] + 100
    for i in range(8):
        mem[pmg_p1_addr + i] = 0xAA

    # Run collision check
    run_subroutine(mpu, labels["ENEMIES_CHECK_PLAYER_COLLISION"])

    # 1. Hero lives must NOT be decremented!
    assert mem[labels["PLAYER_LIVES"]] == 3
    assert mem[labels["PLAYER_STATE"]] == labels["PLAYER_STATE_IDLE"]

    # 2. Enemy must be eliminated: inactive and PMG scanlines cleared
    assert mem[labels["ENEMIES_ACTIVE"]] == 0
    for i in range(8):
        assert mem[pmg_p1_addr + i] == 0, f"Enemy PMG scanline {i} not cleared"

    # 3. DLI HPOS for this enemy slot must be cleared (0)
    # Zone 1 channel 0 uses dli_zone_hpos_p1[0]
    zone_hpos_p1 = labels["DLI_ZONE_HPOS_P1"]
    assert mem[zone_hpos_p1] == 0
    assert mem[zone_hpos_p1 + 8] == 0


def test_secret_collect_awards_extra_life():
    """Collecting a secret with extra_life=1 increments player_lives and updates status line."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)

    mpu.sp = 0xFD
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    mpu.a = 0
    run_subroutine(mpu, labels["GAME_INIT"])

    # Simulate player having lost 1 life: lives = 2
    mem[labels["PLAYER_LIVES"]] = 2
    run_subroutine(mpu, labels["STATUS_LINE_REFRESH_LIVES"])

    vram = labels["STATUS_LINE_VRAM"]
    assert mem[vram] == 64      # Heart
    assert mem[vram + 1] == 64  # Heart
    assert mem[vram + 2] == 0   # Space (lost life)

    # Arm secret 0 as extra_life secret
    sec_xlf_addr = labels["SECRETS_EXTRA_LIFE"]
    sec_active_addr = labels["SECRETS_ACTIVE"]
    mem[sec_xlf_addr] = 1
    mem[sec_active_addr] = 1

    # Collect secret 0
    mpu.x = 0
    run_subroutine(mpu, labels["SECRET_COLLECT"])

    # Lives must be incremented to 3 and third heart rendered on status line
    assert mem[labels["PLAYER_LIVES"]] == 3
    assert mem[vram] == 64      # Heart
    assert mem[vram + 1] == 64  # Heart
    assert mem[vram + 2] == 64  # Heart restored!

    # Arm secret 1 without extra_life
    mem[sec_xlf_addr + 1] = 0
    mem[sec_active_addr + 1] = 1

    mpu.x = 1
    run_subroutine(mpu, labels["SECRET_COLLECT"])

    # Lives must remain 3
    assert mem[labels["PLAYER_LIVES"]] == 3


def test_scene_secret_extra_life_rom_tables_compiled_and_loaded():
    """Verify scene_secret_extra_life tables are compiled and loaded in secrets_init."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD

    assert "SCENE_SECRET_EXTRA_LIFE_LO" in labels
    assert "SCENE_SECRET_EXTRA_LIFE_HI" in labels
    assert "SECRETS_EXTRA_LIFE" in labels

    # Run secrets_init for scene 0
    mpu.a = 0
    run_subroutine(mpu, labels["SECRETS_INIT"])

    # Check that secrets_extra_life array exists in memory
    sec_count = mem[labels["SECRETS_COUNT"]]
    xlf_addr = labels["SECRETS_EXTRA_LIFE"]
    for i in range(sec_count):
        assert mem[xlf_addr + i] in (0, 1)

