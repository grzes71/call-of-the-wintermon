"""py65 integration tests for per-definition secret sprite channels.

Covers the channel-aware paths added in engine/secrets_channel.asm plus the GTIA
collision gate in scenes/game.asm:

1. secrets_init mirrors the compiled `scene_*_secret_channel` table into secrets_channel.
2. A "player" channel secret writes HPOSP<ch> + COLPM<ch> (zone and zone 0 tables) instead
   of HPOSM0..M3 + COLPF3, and renders its bitmap into PMG_PLAYER<ch> instead of PMG_MISSILES.
3. clear_secret_hpos moves a player-channel secret off screen ($FF) in the player table.
4. A P0-vs-P<ch> hardware collision (P1PL..P3PL) also gates the collect overlap test.

Expectations come from scenes/*.json + definitions.json (Rule 05); the channel pattern used
to exercise the player paths is injected into engine state at runtime.
"""

from __future__ import annotations

from py65.devices.mpu6502 import MPU

from tests.scene_expectations import (
    scene_files,
    scene_objects,
    scene_secret_channels,
    scene_symbol,
)
from tests.test_dli_system import load_xex_and_symbols, run_subroutine

MISSILES_CHANNEL = 3  # 0..2 = Players 1..3, 3 = 5th player (missiles)


def _stage_scene0(mem, labels, mpu: MPU) -> None:
    """DLI init + stage scene 0 + secrets_init (engine state ready for one-frame calls)."""
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00
    mem[labels["ACTIVE_SCENE_ID"]] = 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = 0
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = 0
    run_subroutine(mpu, labels["SECRETS_INIT"])


def test_secrets_init_copies_channels_from_scene_table():
    """secrets_init mirrors the compiled per-scene channel table into secrets_channel."""
    scene_file = scene_files()[0]
    secrets = scene_objects(scene_file, "secret")
    assert secrets, f"{scene_file} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)

    # The compiled table must match definitions.json ("channel", default "missiles")
    scene_table = labels[f"SCENE_{scene_symbol(scene_file).upper()}_SECRET_CHANNEL"]
    for i, channel in enumerate(scene_secret_channels(scene_file)):
        assert mem[scene_table + i] == channel, (
            f"secret {i}: compiled channel {mem[scene_table + i]} != definitions.json {channel}"
        )

    # Inject a synthetic pattern (Player 1/2/3 round robin) and re-run secrets_init: py65
    # memory is plain RAM, so the scene table can be rewritten before the copy.
    pattern = [i % 3 for i in range(len(secrets))]
    for i, value in enumerate(pattern):
        mem[scene_table + i] = value

    _stage_scene0(mem, labels, mpu)

    assert mem[labels["SECRETS_COUNT"]] == len(secrets)
    for i, value in enumerate(pattern):
        assert mem[labels["SECRETS_CHANNEL"] + i] == value, (
            f"secret {i}: secrets_channel must mirror the scene table ({value})"
        )


def test_player_channel_secret_writes_player_tables():
    """A player-channel secret writes HPOSP<ch>/COLPM<ch> instead of HPOSM0..3/COLPF3."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    _stage_scene0(mem, labels, mpu)

    index = 0
    mem[labels["SECRETS_CHANNEL"] + index] = 1  # Player 2
    mem[labels["SECRETS_ZONE"] + index] = 2     # zone 2 -> DLI slot 1
    mem[labels["SECRETS_X"] + index] = 40

    # Wipe both channels' tables so the assertions below are unambiguous
    for base in (
        labels["DLI_ZONE_HPOS_P2"],
        labels["DLI_ZONE_COL_P2"],
        labels["DLI_ZONE_HPOS_M0"],
        labels["DLI_ZONE_SECRET_COL"],
    ):
        mem[base : base + 8] = bytes(8)

    mpu.x = index
    run_subroutine(mpu, labels["UPDATE_SECRET_HPOS"])

    slot = mem[labels["SECRETS_ZONE"] + index] - 1
    assert mem[labels["DLI_ZONE_HPOS_P2"] + slot] == 48 + 40, "buffer 0 HPOSP2"
    assert mem[labels["DLI_ZONE_HPOS_P2"] + 8 + slot] == 48 + 40, "buffer 1 HPOSP2"
    assert mem[labels["DLI_ZONE_COL_P2"] + slot] == mem[labels["SECRETS_COLOR"] + index]
    assert mem[labels["DLI_ZONE_COL_P2"] + 8 + slot] == mem[labels["SECRETS_COLOR"] + index]

    assert all(mem[labels["DLI_ZONE_HPOS_M0"] + i] == 0 for i in range(8)), (
        "a player-channel secret must not write the missile positions"
    )
    assert all(mem[labels["DLI_ZONE_SECRET_COL"] + i] == 0 for i in range(8)), (
        "a player-channel secret must not write COLPF3"
    )


def test_player_channel_secret_zone0_writes_z0_tables():
    """Zone 0 player-channel secrets use the dli_z0_hpos_p*/col_p* pair (both buffers)."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    _stage_scene0(mem, labels, mpu)

    index = 1
    mem[labels["SECRETS_CHANNEL"] + index] = 2  # Player 3
    mem[labels["SECRETS_ZONE"] + index] = 0
    mem[labels["SECRETS_X"] + index] = 24

    for base in (labels["DLI_Z0_HPOS_P3"], labels["DLI_Z0_COL_P3"]):
        mem[base : base + 2] = bytes(2)

    mpu.x = index
    run_subroutine(mpu, labels["UPDATE_SECRET_HPOS"])

    colour = mem[labels["SECRETS_COLOR"] + index]
    assert mem[labels["DLI_Z0_HPOS_P3"]] == 48 + 24
    assert mem[labels["DLI_Z0_HPOS_P3"] + 1] == 48 + 24
    assert mem[labels["DLI_Z0_COL_P3"]] == colour
    assert mem[labels["DLI_Z0_COL_P3"] + 1] == colour


def test_player_channel_secret_renders_into_player_pmg_page():
    """render_secret_frame writes a player-channel secret into PMG_PLAYER<ch>, not missiles."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    _stage_scene0(mem, labels, mpu)

    index = 0
    mem[labels["SECRETS_CHANNEL"] + index] = 0  # Player 1

    height = mem[labels["SECRETS_HEIGHT"] + index]
    pmg_y = mem[labels["SECRETS_PMG_Y"] + index]
    sprite_id = mem[labels["SECRETS_SPRITE_ID"] + index]
    frame = [mem[labels[f"SPRITE_{sprite_id}_FRAME_0"] + i] for i in range(height)]

    player = labels["PMG_PLAYER1"] + pmg_y
    missiles = labels["PMG_MISSILES"] + pmg_y
    mem[player : player + height] = bytes(height)
    mem[missiles : missiles + height] = bytes(height)

    mpu.x = index
    run_subroutine(mpu, labels["RENDER_SECRET_FRAME"])

    assert list(mem[player : player + height]) == frame, (
        "the sprite frame must land in the PMG page of the secret's channel"
    )
    assert all(mem[missiles + i] == 0 for i in range(height)), (
        "PMG_MISSILES must stay untouched for a player-channel secret"
    )


def test_clear_secret_hpos_moves_player_channel_secret_off_screen():
    """clear_secret_hpos moves a player-channel secret to $FF in the player table."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    _stage_scene0(mem, labels, mpu)

    index = 0
    mem[labels["SECRETS_CHANNEL"] + index] = 2  # Player 3
    mem[labels["SECRETS_ZONE"] + index] = 3

    mpu.x = index
    run_subroutine(mpu, labels["UPDATE_SECRET_HPOS"])
    mpu.x = index
    run_subroutine(mpu, labels["CLEAR_SECRET_HPOS"])

    slot = mem[labels["SECRETS_ZONE"] + index] - 1
    assert mem[labels["DLI_ZONE_HPOS_P3"] + slot] == 0xFF
    assert mem[labels["DLI_ZONE_HPOS_P3"] + 8 + slot] == 0xFF


def test_player_collision_registers_collect_secret():
    """A P0-vs-Player collision (P1PL..P3PL) is a valid gate for collecting a secret."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    _stage_scene0(mem, labels, mpu)
    mpu.a = 0
    run_subroutine(mpu, labels["PLAYER_INIT"])
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])

    count = mem[labels["SECRETS_COUNT"]]
    active = next(i for i in range(count) if mem[labels["SECRETS_ACTIVE"] + i])

    # Missile registers silent: only a player collision is reported
    for name in ("M0PL", "M1PL", "M2PL", "M3PL"):
        mem[labels[name]] = 0
    mem[labels["PLAYER_X"]] = mem[labels["SECRETS_X"] + active]
    mem[labels["PLAYER_PMG_Y"]] = mem[labels["SECRETS_PMG_Y"] + active]
    mem[labels["P1PL"]] = 1  # P0 collided with Player 1

    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

    assert mem[labels["SECRETS_COLLECTED"] + active] == 1, (
        "a P0-vs-P1 hardware collision must let the overlap test collect the secret"
    )

    # Same hardware bit, but the hero vertically clear of every secret: nothing is collected
    mem[labels["SECRETS_COLLECTED"] + active] = 0
    mem[labels["SECRETS_ACTIVE"] + active] = 1
    topmost = min(mem[labels["SECRETS_PMG_Y"] + i] for i in range(count))
    mem[labels["PLAYER_PMG_Y"]] = max(0, topmost - 21)
    mem[labels["P1PL"]] = 1
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])
    assert all(mem[labels["SECRETS_COLLECTED"] + i] == 0 for i in range(count)), (
        "the bounding-box check must still reject a player-collision-only hit"
    )

