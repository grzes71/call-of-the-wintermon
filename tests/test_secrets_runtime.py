"""Automated py65 integration test suite for Atari 8-bit Secrets display and animation.

Validates:
1. Secrets loaded for active scene (Scene 0 Forest, Scene 1 Forest Castle).
2. Root secrets (no dependency) are active initially; dependent secrets are inactive.
3. Secret placement in PMG_MISSILES has at least 1 line margin from platform.
4. Frame 0 missile graphics rendered into PMG_MISSILES at correct scanline ranges.
5. Inactive secret scanlines remain $00.
6. Animation loop: timer decrements, advances frame index at duration boundary,
   rewrites PMG_MISSILES with new frame bytes, and wraps around.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from py65.devices.mpu6502 import MPU

from tests.scene_expectations import (
    SPRITE_TAIL_MARGIN,
    SecretProgressionModel,
    complete_victory_hold,
    dli_secret_color_slots,
    dli_secret_hpos_slots,
    drive_secret_progression,
    engine_colliding_secrets,
    expected_pmg_y,
    scene_files,
    scene_index_with_secrets,
    scene_objects,
    scene_special_secret_count,
    secret_frame_bytes,
    special_secret_total,
    secret_pmg_rows,
    sprite_height,
)
from tests.test_dli_system import load_xex_and_symbols, run_subroutine


# The runtime tests run on the first scene that carries what their fixtures need; the checks
# below are per test (Rule 05: the fixture must not depend on which scene is first in
# scenes/scenes.json). SCENE has a dependency chain and a successor scene (stage progression
# plus the scene-transition assertions).
SCENE = scene_index_with_secrets(with_dependency=True, require_next=True)
# A scene with a non-blinking secret (blink-cadence reference) and one with a "special" secret.
SCENE_STATIC = scene_index_with_secrets(static=True)
SCENE_SPECIAL = scene_index_with_secrets(special=True)
# A second, different scene for the tests that compare two screens.
SCENE_NEXT = scene_index_with_secrets(exclude=(SCENE,))


def test_secrets_init_scene0():
    """Verify secrets_init sets up Scene 0 exactly as derived from the scene JSON.

    Count, order, coordinates, zones, colours, sprite ids, heights, PMG scanlines and
    the initially active stage are all derived from scenes/*.json + definitions.json
    (Rule 05) - editing the scene must not require touching this test.
    """
    scene_file = scene_files()[SCENE]
    secrets = scene_objects(scene_file, "secret")
    assert secrets, f"{scene_file} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize DLI and stage Scene 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])

    # Initialize Secrets
    mpu.a = SCENE
    run_subroutine(mpu, labels["SECRETS_INIT"])

    count = len(secrets)
    assert mem[labels["SECRETS_COUNT"]] == count

    act_addr = labels["SECRETS_ACTIVE"]
    x_addr = labels["SECRETS_X"]
    y_addr = labels["SECRETS_PMG_Y"]
    h_addr = labels["SECRETS_HEIGHT"]
    spr_addr = labels["SECRETS_SPRITE_ID"]
    zone_addr = labels["SECRETS_ZONE"]
    col_addr = labels["SECRETS_COLOR"]

    for i, secret in enumerate(secrets):
        # Only dependency-free secrets belong to the initial stage
        assert mem[act_addr + i] == int(not secret.get("dependency")), (
            f"secret {i} ({secret['id']}) active flag must follow its dependency"
        )
        assert mem[x_addr + i] == secret["x"], f"secret {i} x coordinate mismatch"
        assert mem[zone_addr + i] == secret["zone"], f"secret {i} zone mismatch"
        assert mem[spr_addr + i] == secret["sprite_id"], f"secret {i} sprite id mismatch"
        assert mem[col_addr + i] == secret["atari_color"], f"secret {i} colour mismatch"

        height = mem[h_addr + i]
        assert height == sprite_height(mem, labels, secret["sprite_id"])
        assert mem[y_addr + i] == expected_pmg_y(secret["platform_y"], height), (
            f"secret {i} pmg_y mismatch"
        )
        # The sprite must end exactly SPRITE_TAIL_MARGIN scanlines above the platform pas base
        pas_base = 32 + secret["platform_y"] * 2
        assert pas_base - (mem[y_addr + i] + height) == SPRITE_TAIL_MARGIN, (
            f"secret {i} must end {SPRITE_TAIL_MARGIN} scanline(s) above its platform pas"
        )

        if mem[act_addr + i]:
            assert secret_pmg_rows(mem, labels, i) == secret_frame_bytes(mem, labels, i), (
                f"active secret {i} must render sprite frame 0 into PMG_MISSILES"
            )

    # Inactive secrets whose PMG rows are not shared with an active secret stay cleared
    for i, secret in enumerate(secrets):
        if mem[act_addr + i]:
            continue
        top = mem[y_addr + i]
        height = mem[h_addr + i]
        shared = any(
            mem[act_addr + j]
            and top < mem[y_addr + j] + mem[h_addr + j]
            and mem[y_addr + j] < top + height
            for j in range(count)
        )
        if not shared:
            assert secret_pmg_rows(mem, labels, i) == [0] * height, (
                f"inactive secret {i} must not render into PMG_MISSILES"
            )


def test_secrets_animation_progression():
    """Verify secrets_update decrements timer, advances frames, and updates PMG_MISSILES."""
    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize Scene 0
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    mpu.a = SCENE
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["SECRETS_INIT"])

    timer_addr = labels["SECRETS_TIMER"]
    frame_addr = labels["SECRETS_FRAME_IDX"]
    dur_addr = labels["SECRETS_FRAME_DUR"]
    frame_cnt_addr = labels["SECRETS_FRAME_COUNT"]
    act_addr = labels["SECRETS_ACTIVE"]
    pmg_m = labels["PMG_MISSILES"]

    # Pick the first active secret that has multiple animation frames (frame_count > 1)
    count = mem[labels["SECRETS_COUNT"]]
    secret_idx = next(
        (i for i in range(count) if mem[act_addr + i] and mem[frame_cnt_addr + i] > 1),
        None,
    )
    assert secret_idx is not None, f"scene {SCENE} must have at least one active animated secret"

    # Secret duration and frame count from runtime tables
    key_dur = mem[dur_addr + secret_idx]
    key_frame_count = mem[frame_cnt_addr + secret_idx]

    assert key_dur > 0
    assert key_frame_count > 1
    assert mem[timer_addr + secret_idx] == key_dur
    assert mem[frame_addr + secret_idx] == 0

    # Ticks 1..key_dur-1: timer counts down; frame index stays 0
    for expected_timer in range(key_dur - 1, 0, -1):
        run_subroutine(mpu, labels["SECRETS_UPDATE"])
        assert mem[timer_addr + secret_idx] == expected_timer
        assert mem[frame_addr + secret_idx] == 0

    # Tick key_dur: timer resets to key_dur, frame index advances to 1
    run_subroutine(mpu, labels["SECRETS_UPDATE"])
    assert mem[timer_addr + secret_idx] == key_dur
    assert mem[frame_addr + secret_idx] == 1

    # PMG_MISSILES rows must now match the sprite's frame 1 (sprite id read at runtime)
    assert secret_pmg_rows(mem, labels, secret_idx) == secret_frame_bytes(mem, labels, secret_idx, frame=1), (
        f"PMG_MISSILES rows do not match Frame 1 after {key_dur} ticks"
    )

    # Step through remaining frames (frames 2 .. key_frame_count - 1)
    for f in range(2, key_frame_count):
        for _ in range(key_dur):
            run_subroutine(mpu, labels["SECRETS_UPDATE"])
        assert mem[frame_addr + secret_idx] == f

    # Next key_dur ticks should wrap back to frame 0 (loop=True)
    for _ in range(key_dur):
        run_subroutine(mpu, labels["SECRETS_UPDATE"])
    assert mem[frame_addr + secret_idx] == 0


def test_secrets_init_scene1():
    """Verify secrets_init sets up the second scene exactly as derived from its JSON."""
    scene_file = scene_files()[SCENE_NEXT]
    secrets = scene_objects(scene_file, "secret")
    assert secrets, f"{scene_file} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE_NEXT
    mpu.a = SCENE_NEXT
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE_NEXT
    run_subroutine(mpu, labels["SECRETS_INIT"])

    assert mem[labels["SECRETS_COUNT"]] == len(secrets)

    act_addr = labels["SECRETS_ACTIVE"]
    x_addr = labels["SECRETS_X"]
    spr_addr = labels["SECRETS_SPRITE_ID"]
    for i, secret in enumerate(secrets):
        assert mem[act_addr + i] == int(not secret.get("dependency")), (
            f"secret {i} ({secret['id']}) active flag must follow its dependency"
        )
        assert mem[x_addr + i] == secret["x"]
        assert mem[spr_addr + i] == secret["sprite_id"]


def test_secret_collection_and_stage_progression_scene0():
    """Drive the first scene through its full secret chain against a model of the engine.

    The scene layout, secret count and dependency graph are derived from the scene JSON
    and definitions.json (Rule 05); the expected progression comes from
    SecretProgressionModel, a mirror of `secret_collect` in scenes/game.asm.
    """
    scene_file = scene_files()[SCENE]
    secrets = scene_objects(scene_file, "secret")
    assert secrets, f"{scene_file} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize scene 0 and game
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = SCENE
    run_subroutine(mpu, labels["PLAYER_INIT"])
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])  # engine-defined starting HUD state

    count = len(secrets)
    act_addr = labels["SECRETS_ACTIVE"]
    coll_addr = labels["SECRETS_COLLECTED"]
    x_addr = labels["SECRETS_X"]
    y_addr = labels["SECRETS_PMG_Y"]
    h_addr = labels["SECRETS_HEIGHT"]
    zone_addr = labels["SECRETS_ZONE"]
    m0pl_addr = labels["M0PL"]
    initial_lives = mem[labels["PLAYER_LIVES"]]

    # 1. Hardware false-positive guard: a bare missile-platform touch must not collect.
    #    The hero is placed horizontally on a secret but vertically clear of every one.
    topmost = min(mem[y_addr + i] for i in range(count))
    mem[labels["PLAYER_X"]] = mem[x_addr + 0]
    mem[labels["PLAYER_PMG_Y"]] = max(0, topmost - 21)
    mem[m0pl_addr] = 1  # Hardware collision with a missile platform
    run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])
    assert all(mem[coll_addr + i] == 0 for i in range(count)), (
        "bounding-box check must reject a missile-platform-only hardware hit"
    )

    # 2. Walk the whole secret chain: after every collection the engine tables must
    #    match SecretProgressionModel (mirror of secret_collect in scenes/game.asm)
    model = SecretProgressionModel(secrets)
    steps = 0
    while model.pending:
        target = model.pending[0]
        hero_x = mem[x_addr + target]
        hero_y = mem[y_addr + target]
        hits = engine_colliding_secrets(mem, labels, hero_x, hero_y)
        assert hits, f"hero placed on secret {target} must overlap it"
        expected = min(hits)  # engine scans from index 0 and collects the first match

        mem[labels["PLAYER_X"]] = hero_x
        mem[labels["PLAYER_PMG_Y"]] = hero_y
        mem[m0pl_addr] = 1
        run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

        collected = [i for i in range(count) if mem[coll_addr + i] and not model.collected[i]]
        assert collected == [expected], (
            f"step {steps}: engine collected {collected}, model expected [{expected}]"
        )
        unlocked = model.collect(expected)

        # Collected secret: PMG rows erased (except rows taken over by newly unlocked
        # secrets, whose sprites may overlap the collected one), DLI positions cleared
        unlocked_rows: set[int] = set()
        for j in unlocked:
            top_j = mem[y_addr + j]
            unlocked_rows.update(range(top_j, top_j + mem[h_addr + j]))
        top = mem[y_addr + expected]
        for row in range(top, top + mem[h_addr + expected]):
            if row in unlocked_rows:
                continue
            assert mem[labels["PMG_MISSILES"] + row] == 0, (
                f"step {steps}: collected secret {expected} must leave PMG row {row} cleared"
            )
        zone = mem[zone_addr + expected]
        if not any(mem[act_addr + i] and mem[zone_addr + i] == zone for i in range(count)):
            for channel in range(4):
                for slot in dli_secret_hpos_slots(labels, zone, channel):
                    assert mem[slot] == 0xFF, (
                        f"step {steps}: HPOSM{channel} of collected secret {expected} must be $FF"
                    )

        # Newly unlocked secrets: activated, frame 0 rendered, DLI positions updated
        for j in unlocked:
            assert secret_pmg_rows(mem, labels, j) == secret_frame_bytes(mem, labels, j), (
                f"step {steps}: unlocked secret {j} must render sprite frame 0"
            )
            zone_j = mem[zone_addr + j]
            owners = [i for i in range(count) if mem[act_addr + i] and mem[zone_addr + i] == zone_j]
            if owners != [j]:
                continue  # shared zone: the last writer of that zone wins
            base = 48 + mem[x_addr + j]
            for channel in range(4):
                for slot in dli_secret_hpos_slots(labels, zone_j, channel):
                    assert mem[slot] == base + channel * 2, (
                        f"step {steps}: HPOSM{channel} of unlocked secret {j} must be {base + channel * 2}"
                    )
        steps += 1

    assert steps == count, "every secret must be collected exactly once"
    assert model.scene_advanced, "the model must detect scene completion"

    # 3. Level complete: the victory fanfare plays IN the finished scene and the engine
    #    advances only after it has finished (see complete_victory_hold)
    scene_index = SCENE
    assert mem[labels["ACTIVE_SCENE_ID"]] == scene_index, (
        "the scene must not change while the victory fanfare is playing"
    )
    complete_victory_hold(mpu, mem, labels, run_subroutine)

    if scene_index + 1 < labels["SCENE_COUNT"]:
        assert mem[labels["ACTIVE_SCENE_ID"]] == scene_index + 1
        assert mem[labels["GAME_PHASE"]] == labels["GAME_PHASE_TITLE_IN"]
        assert mem[labels["PLAYER_LIVES"]] == initial_lives, "lives must survive scene change"
        next_secrets = scene_objects(scene_files()[scene_index + 1], "secret")
        assert mem[labels["SECRETS_COUNT"]] == len(next_secrets)
        for i, secret in enumerate(next_secrets):
            assert mem[act_addr + i] == int(not secret.get("dependency")), (
                "next scene secrets must be initialized fresh from their own JSON"
            )
            assert mem[coll_addr + i] == 0
    else:
        assert mem[labels["GAME_RESULT"]] == labels["GAME_SUCCESS"]
        assert mem[labels["GAME_STATE"]] == labels["STATE_OVER"]


def test_game_success_on_final_scene_completion():
    """Collecting every secret of the final scene must set GAME_SUCCESS / STATE_OVER.

    The final scene, its secret count and the unlock chain are derived from
    scenes/scenes.json + the scene JSON (Rule 05).
    """
    scene_list = scene_files()
    final_index = len(scene_list) - 1
    secrets = scene_objects(scene_list[final_index], "secret")
    assert secrets, f"{scene_list[final_index]} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Start directly on the final scene
    mem[labels["ACTIVE_SCENE_ID"]] = final_index
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = final_index
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = final_index
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = final_index
    run_subroutine(mpu, labels["PLAYER_INIT"])

    model = SecretProgressionModel(secrets)
    drive_secret_progression(mpu, mem, labels, model, run_subroutine)

    assert model.scene_advanced, (
        "the last secret must complete the final scene; the chain stopped with these "
        f"secrets uncollected: {model.uncollected_description()}"
    )
    # The fanfare plays in the finished scene first; GAME_SUCCESS follows afterwards
    complete_victory_hold(mpu, mem, labels, run_subroutine)
    assert mem[labels["GAME_RESULT"]] == labels["GAME_SUCCESS"]
    assert mem[labels["GAME_STATE"]] == labels["STATE_OVER"]


def test_secrets_blink_cadence_and_static_colors():
    """Blinking secrets must pulse their luminance while static secrets keep one colour.

    Which secrets blink, their base colours and their zones are derived from the scene
    JSON + definitions.json and cross-checked against the engine tables (Rule 05).
    Cadence contract: each luminance step is held for SECRETS_BLINK_STEP_FRAMES frames.
    """
    scene_file = scene_files()[SCENE_STATIC]
    secrets = scene_objects(scene_file, "secret")
    blinking = [i for i, secret in enumerate(secrets) if secret["blink"]]
    static = [i for i, secret in enumerate(secrets) if not secret["blink"]]
    assert blinking, f"{scene_file} must contain at least one blinking secret"
    assert static, f"{scene_file} must contain at least one static secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    # Initialize DLI and Secrets for the fixture scene
    run_subroutine(mpu, labels["DLI_INIT"])
    mem[labels["ACTIVE_SCENE_ID"]] = SCENE_STATIC
    mpu.a = SCENE_STATIC
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE_STATIC
    run_subroutine(mpu, labels["SECRETS_INIT"])

    count = len(secrets)
    act_addr = labels["SECRETS_ACTIVE"]
    col_addr = labels["SECRETS_COLOR"]
    zone_addr = labels["SECRETS_ZONE"]
    blink_addr = labels["SECRETS_BLINK"]

    # 1. Engine blink flags and colours must match the catalogue definitions
    for i, secret in enumerate(secrets):
        assert mem[blink_addr + i] == int(secret["blink"]), f"secret {i} blink flag mismatch"
        assert mem[col_addr + i] == secret["atari_color"], f"secret {i} colour mismatch"

    # 2. Pick a blinking secret that is the last writer of its zone
    blink_idx = next(
        i for i in blinking if not any(j != i and mem[zone_addr + j] == mem[zone_addr + i] for j in blinking)
    )
    mem[act_addr + blink_idx] = 1  # ensure the pulse phase updates its DLI colour
    base_color = mem[col_addr + blink_idx]
    slots = dli_secret_color_slots(labels, mem[zone_addr + blink_idx])

    lum_addr = labels["SECRETS_BLINK_LUM"]
    timer_addr = labels["SECRETS_BLINK_TIMER"]
    step_frames = labels["SECRETS_BLINK_STEP_FRAMES"]
    assert step_frames == 2, "blink pulse must stay 2x slower than per-frame stepping"
    assert mem[timer_addr] == step_frames, "frame divider must be armed by secrets_init"
    assert mem[lum_addr] == 0x00

    lum_steps = 8                             # $00, $02, ... $0E
    cycle_frames = lum_steps * step_frames    # full pulse cycle (16 frames at step = 2)

    # 3. Each luminance step is held for `step_frames` frames in both DLI buffers
    for frame in range(1, 2 * cycle_frames + 1):
        run_subroutine(mpu, labels["SECRETS_UPDATE"])

        expected_color = (base_color & 0xF0) | ((2 * ((frame - 1) // step_frames)) & 0x0E)
        for slot in slots:
            assert mem[slot] == expected_color, (
                f"frame {frame}: expected colour ${expected_color:02X}, got ${mem[slot]:02X}"
            )

        # Luminance counter advances only once per SECRETS_BLINK_STEP_FRAMES frames
        expected_lum = (2 * (frame // step_frames)) & 0x0E
        assert mem[lum_addr] == expected_lum, (
            f"frame {frame}: expected SECRETS_BLINK_LUM ${expected_lum:02X}, got ${mem[lum_addr]:02X}"
        )

    # 4. Static secrets that exclusively own their zone must keep a constant colour
    checked = 0
    for i in static:
        if not mem[act_addr + i]:
            continue
        zone = mem[zone_addr + i]
        owners = [j for j in range(count) if mem[act_addr + j] and mem[zone_addr + j] == zone]
        if owners != [i]:
            continue  # shared zone: the last writer of that zone wins
        for slot in dli_secret_color_slots(labels, zone):
            assert mem[slot] == mem[col_addr + i], f"static secret {i} colour must not change"
        checked += 1
    assert checked, "at least one static secret must be verifiable in this scene"


def test_secret_collect_blip_variant_and_final_secret_silence():
    """Collecting a secret arms the collect blip; the scene-finishing one stays silent.

    Derived from the scene JSON + definitions.json (Rule 05). Contract
    (scenes/game.asm, `secret_collect`):
      - `secrets_special` mirrors the catalogue "special" flag;
      - every collected secret triggers the blip with that flag (different sound),
        except the one that completes the scene - that path plays the victory fanfare
        instead and must not start the blip at all;
      - special secrets also add one disc glyph (code 61) to the status line, filled
        from the right end (engine/status_line.asm).
    """
    scene_file = scene_files()[SCENE_SPECIAL]
    secrets = scene_objects(scene_file, "secret")
    assert secrets, f"{scene_file} must define at least one secret"

    mem, labels = load_xex_and_symbols()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x01FE] = 0x1F
    mem[0x01FF] = 0x00

    mem[labels["ACTIVE_SCENE_ID"]] = SCENE_SPECIAL
    run_subroutine(mpu, labels["DLI_INIT"])
    mpu.a = SCENE_SPECIAL
    run_subroutine(mpu, labels["DLI_STAGE_SCENE"])
    mpu.a = SCENE_SPECIAL
    run_subroutine(mpu, labels["SECRETS_INIT"])
    mpu.a = SCENE_SPECIAL
    run_subroutine(mpu, labels["PLAYER_INIT"])
    run_subroutine(mpu, labels["STATUS_LINE_RESET"])
    mpu.a = 0
    run_subroutine(mpu, labels["STATUS_LINE_INIT"])

    count = len(secrets)
    coll_addr = labels["SECRETS_COLLECTED"]
    x_addr = labels["SECRETS_X"]
    y_addr = labels["SECRETS_PMG_Y"]
    spec_addr = labels["SECRETS_SPECIAL"]
    blip_timer = labels["SFX_SECRET_TIMER"]
    fanfare_timer = labels["SFX_VICTORY_TIMER"]
    hud = labels["STATUS_LINE_VRAM"]
    icon_capacity = special_secret_total()
    icon_start = 40 - icon_capacity

    # 1. Engine flag table mirrors the catalogue (compiler -> ROM -> secrets_init)
    for i, secret in enumerate(secrets):
        assert mem[spec_addr + i] == int(secret["special"]), f"secret {i} special flag mismatch"

    # 2. Walk the whole chain and check the blip contract at every collection
    model = SecretProgressionModel(secrets)
    played = 0
    silent = 0
    specials_collected = 0
    while model.pending:
        target = model.pending[0]
        hits = engine_colliding_secrets(mem, labels, mem[x_addr + target], mem[y_addr + target])
        assert hits, f"hero placed on secret {target} must overlap it"
        expected = min(hits)  # the engine collects the first matching secret

        mem[labels["PLAYER_X"]] = mem[x_addr + target]
        mem[labels["PLAYER_PMG_Y"]] = mem[y_addr + target]
        mem[labels["M0PL"]] = 1
        mem[blip_timer] = 0         # cleared so arming the blip is observable
        mem[fanfare_timer] = 0
        run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

        assert mem[coll_addr + expected] == 1, "the collided secret must be collected"
        assert mem[labels["SECRET_COLL_SPECIAL"]] == int(secrets[expected]["special"]), (
            f"secret {expected}: blip variant must follow the catalogue 'special' flag"
        )

        # HUD: one disc glyph (code 61) per collected special secret, filled right to left.
        if secrets[expected]["special"]:
            specials_collected += 1
        assert mem[labels["PLAYER_SPECIALS"]] == specials_collected, (
            f"secret {expected}: the HUD counter must follow the collected special secrets"
        )
        icon_area = [mem[hud + icon_start + k] for k in range(icon_capacity)]
        assert icon_area == [0] * (icon_capacity - specials_collected) + [61] * specials_collected, (
            f"secret {expected}: collected special secrets must be drawn at the right end"
        )

        model.collect(expected)
        if model.pending:
            # Scene continues: the blip plays, with the variant of the collected secret
            expected_duration = (
                labels["SFX_SECRET_SPECIAL_DURATION"]
                if secrets[expected]["special"]
                else labels["SFX_SECRET_DURATION"]
            )
            assert mem[labels["SECRET_COLL_SFX"]] == 1
            assert mem[blip_timer] == expected_duration, (
                f"secret {expected}: the collect blip must be armed for {expected_duration} frames"
            )
            played += 1
        else:
            # Last secret of the scene: the fanfare plays, so no collect blip
            assert mem[labels["SECRET_COLL_SFX"]] == 0
            assert mem[blip_timer] == 0, "the scene-finishing secret must not play the collect blip"
            assert mem[fanfare_timer] != 0, "the victory fanfare must be armed instead"
            assert mem[labels["GAME_PHASE"]] == labels["GAME_PHASE_VICTORY"]
            silent += 1

    assert played == count - 1, f"every secret but the last must play a blip (count={count})"
    assert silent == 1, "exactly one secret finishes the scene"
    assert specials_collected == scene_special_secret_count(0), (
        "the HUD must show exactly the special secrets placed in the scene"
    )
