"""Asset-agnostic expectations derived from the SSOT scene definitions.

Rule 05 (Test Design & Asset Agnosticism): tests must never hardcode counts,
coordinates, colours, speeds or strategies of resources that evolve during game
development (`scenes/*.json`, `scenes/definitions.json`). Everything in this
module is derived from those files (or from the compiled ROM tables) so scene and
catalogue edits cannot break the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.compile_scenes import OBJ_SPEED_MAP, OBJ_STRATEGY_MAP

SCENES_DIR = Path("scenes")
MANIFEST_PATH = SCENES_DIR / "scenes.json"
DEFINITIONS_PATH = SCENES_DIR / "definitions.json"

# Geometry constants mirroring scripts/compile_scenes.py
PMG_ROW_BASE = 32        # PMG scanline of the pas base for platform row y: 32 + y * 2
SPRITE_TAIL_MARGIN = 3   # sprites end 3 scanlines above the platform pas base
ZONE_HEIGHT = 16         # platform rows are 16 canvas lines apart


def load_definitions() -> dict[str, Any]:
    """Parsed scenes/definitions.json (enemies, secrets, platform profiles)."""
    return json.loads(DEFINITIONS_PATH.read_text(encoding="utf-8"))


def scene_files() -> list[str]:
    """Scene file names in game progression order (scenes/scenes.json)."""
    return list(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["scenes"])


def load_scene(scene_file: str) -> dict[str, Any]:
    return json.loads((SCENES_DIR / scene_file).read_text(encoding="utf-8"))


def scene_objects(scene_file: str, kind: str) -> list[dict[str, Any]]:
    """Objects of `kind` ("secret"/"enemy") in engine order (scene JSON order).

    Each entry carries the object fields plus resolved catalogue data
    (sprite_id, atari_color, blink, dependency) and derived geometry.
    """
    catalogue = {
        item["id"]: item
        for item in load_definitions().get("secrets" if kind == "secret" else "enemies", [])
    }
    scene = load_scene(scene_file)
    platforms = {p["id"]: p["position"] for p in scene["platforms"]}
    objects: list[dict[str, Any]] = []
    for obj in scene["objects"]:
        if obj.get("type") != kind:
            continue
        definition = catalogue.get(obj["definition_id"], {})
        platform_y = platforms[obj["platform_id"]]["y"]
        objects.append(
            {
                **obj,
                "platform_y": platform_y,
                "zone": zone_index(platform_y),
                "dependency": obj.get("dependency", definition.get("dependency")),
                "sprite_id": obj.get("sprite_id", definition.get("sprite_id")),
                "atari_color": definition.get("atari_color"),
                "blink": bool(definition.get("blink", False)),
            }
        )
    return objects


def zone_index(platform_y: int) -> int:
    """Zone table index used by the DLI (0 = zone above the first platform row)."""
    return (platform_y - 8) // ZONE_HEIGHT if platform_y >= 8 else 0


# Background palette: engine/dli.asm swaps COLPF0..2 once per zone. Per frame the zone order is
# upper, upper, lower, lower, lower, upper (the lower zone starts at playfield line 44 and the
# upper palette is restored at line 92).
BG_ZONE_ORDER = ("upper", "upper", "lower", "lower", "lower", "upper")


def scene_engine_index(scene_file: str) -> int:
    """Engine scene index of a scene file (its position in scenes/scenes.json)."""
    return scene_files().index(scene_file)


def scene_background_palette(scene_index: int) -> dict[str, list[int]]:
    """Background palette (upper/lower COLPF0..2) of the scene at that engine index.

    Derived from the scene JSON, which is the single source of truth for the DLI colours.
    """
    scene_file = scene_files()[scene_index]
    palette = load_scene(scene_file).get("background_palette")
    assert palette is not None, f"{scene_file} stores no background_palette"
    return {"upper": list(palette["upper"]), "lower": list(palette["lower"])}


def expected_pmg_y(platform_y: int, sprite_height: int) -> int:
    """PMG scanline of a sprite resting on the platform row at `platform_y`."""
    return max(0, PMG_ROW_BASE + platform_y * 2 - sprite_height - SPRITE_TAIL_MARGIN)


def sprite_height(mem, labels, sprite_id: int) -> int:
    """Sprite height from the compiled ROM table (1-based sprite ids)."""
    return mem[labels["SPRITE_HEIGHT"] + sprite_id]


def sprite_frame_label(sprite_id: int, frame: int) -> str:
    """ROM label of a compiled sprite frame (see scripts/compile_sprites.py)."""
    return f"SPRITE_{sprite_id}_FRAME_{frame}"


def expected_speed_code(obj: dict[str, Any]) -> int:
    """Engine speed code for a scene object (single source of truth: compiler map)."""
    return OBJ_SPEED_MAP.get(str(obj.get("speed", "slow")).lower(), 0)


def expected_strategy_code(obj: dict[str, Any]) -> int:
    """Engine strategy code for a scene object (compiler map, incl. aliases)."""
    return OBJ_STRATEGY_MAP.get(str(obj.get("movement_strategy", "stationary")).lower(), 0)


# ==============================================================================
# PMG / DLI runtime accessors (engine table layout)
# ==============================================================================


def secret_pmg_rows(mem, labels, index: int) -> list[int]:
    """PMG_MISSILES scanlines currently holding secret `index`."""
    top = labels["PMG_MISSILES"] + mem[labels["SECRETS_PMG_Y"] + index]
    height = mem[labels["SECRETS_HEIGHT"] + index]
    return [mem[top + i] for i in range(height)]


def secret_frame_bytes(mem, labels, index: int, frame: int = 0) -> list[int]:
    """Compiled sprite frame bytes of secret `index` (sprite id read at runtime)."""
    sprite_id = mem[labels["SECRETS_SPRITE_ID"] + index]
    top = labels[sprite_frame_label(sprite_id, frame)]
    height = mem[labels["SECRETS_HEIGHT"] + index]
    return [mem[top + i] for i in range(height)]


def dli_secret_hpos_slots(labels, zone: int, channel: int) -> list[int]:
    """Both double-buffer HPOSM<channel> addresses for zone-table slot `zone`.

    `zone` is the pas index (0..5) stored in the engine tables: engine/dli.asm reads
    `dli_zone_hpos_m*` with that same index, so slot 0 is the platform row at y = 8.
    """
    base = labels[f"DLI_ZONE_HPOS_M{channel}"] + zone
    return [base, base + 8]


def dli_secret_color_slots(labels, zone: int) -> list[int]:
    """Both double-buffer 5th-player colour addresses used for zone-table slot `zone`."""
    base = labels["DLI_ZONE_SECRET_COL"] + zone
    return [base, base + 8]


def dli_enemy_hpos_slots(labels, zone: int, channel: int) -> list[int]:
    """Both double-buffer HPOSP<channel+1> addresses for zone-table slot `zone` (pas index)."""
    base = labels[f"DLI_ZONE_HPOS_P{channel + 1}"] + zone
    return [base, base + 8]


def enemy_pmg_rows(mem, labels, index: int) -> list[int]:
    """PMG player scanlines currently holding enemy `index`."""
    channel = mem[labels["ENEMIES_CHANNEL"] + index]
    top = labels["PMG_PLAYER1"] + channel * 256 + mem[labels["ENEMIES_PMG_Y"] + index]
    height = mem[labels["ENEMIES_HEIGHT"] + index]
    return [mem[top + i] for i in range(height)]


def enemy_frame_bytes(mem, labels, index: int, frame: int = 0) -> list[int]:
    """Compiled sprite frame bytes of enemy `index` (sprite id read at runtime)."""
    sprite_id = mem[labels["ENEMIES_SPRITE_ID"] + index]
    top = labels[sprite_frame_label(sprite_id, frame)]
    height = mem[labels["ENEMIES_HEIGHT"] + index]
    return [mem[top + i] for i in range(height)]


# ==============================================================================
# Secret progression model (mirror of secret_collect in scenes/game.asm)
# ==============================================================================


class SecretProgressionModel:
    """Python mirror of the engine's stage-unlock rule.

    - a secret is initially active iff it has no dependency;
    - collecting a secret marks it collected=1 / active=0;
    - once no active secret remains, every uncollected secret whose dependency
      equals the collected secret's definition id is activated (one stage at a
      time);
    - if nothing was unlocked and every secret is collected, the scene advances.
    """

    def __init__(self, secrets: list[dict[str, Any]]) -> None:
        self.secrets = secrets
        self.active = [not secret.get("dependency") for secret in secrets]
        self.collected = [False] * len(secrets)
        self.scene_advanced = False

    @property
    def pending(self) -> list[int]:
        return [i for i in range(len(self.secrets)) if self.active[i] and not self.collected[i]]

    def collect(self, index: int) -> list[int]:
        """Collect `index`; return the indices unlocked by this step."""
        assert self.active[index] and not self.collected[index]
        self.collected[index] = True
        self.active[index] = False
        collected_def = self.secrets[index]["definition_id"]
        if any(self.active):
            return []
        unlocked = [
            i
            for i, secret in enumerate(self.secrets)
            if not self.collected[i] and (secret.get("dependency") or 0) == collected_def
        ]
        for i in unlocked:
            self.active[i] = True
        if not unlocked and all(self.collected):
            self.scene_advanced = True
        return unlocked


def engine_colliding_secrets(mem, labels, player_x: int, player_pmg_y: int) -> list[int]:
    """Active, uncollected secrets overlapping the hero, per the engine's own rule."""
    hits: list[int] = []
    for i in range(mem[labels["SECRETS_COUNT"]]):
        if not mem[labels["SECRETS_ACTIVE"] + i] or mem[labels["SECRETS_COLLECTED"] + i]:
            continue
        if abs(player_x - mem[labels["SECRETS_X"] + i]) >= 8:
            continue
        top = mem[labels["SECRETS_PMG_Y"] + i]
        height = mem[labels["SECRETS_HEIGHT"] + i]
        if top + height > player_pmg_y and player_pmg_y + 20 > top:
            hits.append(i)
    return hits


def drive_secret_progression(mpu, mem, labels, model: SecretProgressionModel, run_subroutine) -> int:
    """Walk the hero through every secret of the active scene.

    After each hardware-collision step the engine tables must match the model
    exactly (which secret got collected, and which ones were unlocked).
    Returns the number of collection steps performed.
    """
    steps = 0
    while model.pending:
        target = model.pending[0]
        hero_x = mem[labels["SECRETS_X"] + target]
        hero_y = mem[labels["SECRETS_PMG_Y"] + target]
        hits = engine_colliding_secrets(mem, labels, hero_x, hero_y)
        assert hits, f"hero placed on secret {target} must overlap it"
        expected = min(hits)  # engine scans from index 0 and collects the first match

        mem[labels["PLAYER_X"]] = hero_x
        mem[labels["PLAYER_PMG_Y"]] = hero_y
        mem[labels["M0PL"]] = 1
        run_subroutine(mpu, labels["SECRETS_CHECK_PLAYER_COLLISION"])

        collected_now = [
            i
            for i in range(len(model.secrets))
            if mem[labels["SECRETS_COLLECTED"] + i] and not model.collected[i]
        ]
        assert collected_now == [expected], (
            f"engine collected {collected_now}, model expected [{expected}]"
        )
        model.collect(expected)

        for i in range(len(model.secrets)):
            assert mem[labels["SECRETS_ACTIVE"] + i] == int(model.active[i]), (
                f"secret {i} active flag mismatch after step {steps}"
            )
            assert mem[labels["SECRETS_COLLECTED"] + i] == int(model.collected[i]), (
                f"secret {i} collected flag mismatch after step {steps}"
            )
        steps += 1
    return steps


def complete_victory_hold(mpu, mem, labels, run_subroutine) -> None:
    """Drive the level-complete victory hold until the engine leaves the phase.

    Collecting the last secret of a scene switches to GAME_PHASE_VICTORY and starts
    the victory fanfare; game_next_scene is called only after the whole fanfare has
    been played (SFX_VICTORY_DURATION frames), so the scene must not change before.
    """
    duration = labels["SFX_VICTORY_DURATION"]
    assert mem[labels["GAME_PHASE"]] == labels["GAME_PHASE_VICTORY"], (
        "collecting the last secret must enter the victory hold"
    )
    assert mem[labels["SFX_VICTORY_TIMER"]] == duration, "victory fanfare must be armed"

    for _ in range(duration - 1):
        run_subroutine(mpu, labels["GAME_VICTORY_UPDATE"])
    assert mem[labels["GAME_PHASE"]] == labels["GAME_PHASE_VICTORY"], (
        "the scene must not change before the fanfare has finished"
    )

    run_subroutine(mpu, labels["GAME_VICTORY_UPDATE"])
    assert (
        mem[labels["GAME_PHASE"]] != labels["GAME_PHASE_VICTORY"]
        or mem[labels["GAME_RESULT"]] == labels["GAME_SUCCESS"]
    ), "the victory hold must end after SFX_VICTORY_DURATION frames"

