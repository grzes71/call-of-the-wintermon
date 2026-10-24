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

from scripts.compile_scenes import OBJ_SPEED_MAP, OBJ_STRATEGY_MAP, SPRITE_TAIL_MARGIN, sanitize_symbol
from scripts.sprite_roles import MAX_CHANNELS_PER_ROW, SECRET_CHANNEL_PLAYER

SCENES_DIR = Path("scenes")
MANIFEST_PATH = SCENES_DIR / "scenes.json"
DEFINITIONS_PATH = SCENES_DIR / "definitions.json"

# Geometry constants mirroring scripts/compile_scenes.py
PMG_ROW_BASE = 32        # PMG scanline of the pas base for platform row y: 32 + y * 2
ZONE_HEIGHT = 16         # platform rows are 16 canvas lines apart


def load_definitions() -> dict[str, Any]:
    """Parsed scenes/definitions.json (enemies, secrets, platform profiles)."""
    return json.loads(DEFINITIONS_PATH.read_text(encoding="utf-8"))


def scene_files() -> list[str]:
    """Scene file names in game progression order (scenes/scenes.json)."""
    return list(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["scenes"])


def load_scene(scene_file: str) -> dict[str, Any]:
    return json.loads((SCENES_DIR / scene_file).read_text(encoding="utf-8"))


def scene_symbol(scene_file: str) -> str:
    """Compiler symbol of a scene file (mirrors scripts/compile_scenes.py sanitize_symbol)."""
    return sanitize_symbol(Path(scene_file).stem)


def scene_secret_channels(scene_file: str) -> list[int]:
    """Sprite channel index per secret of a scene (0..2 = Players 1..3, 3 = 5th player).

    Derived from scenes/definitions.json ("channel", default "missiles") with the same rule
    the compiler applies, so the expectation follows the catalogue instead of a constant.
    """
    catalogue = {item["id"]: item for item in load_definitions().get("secrets", [])}
    channels: list[int] = []
    for secret in scene_objects(scene_file, "secret"):
        raw = str(catalogue.get(secret["definition_id"], {}).get("channel", "missiles")).lower()
        channels.append(0 if raw == SECRET_CHANNEL_PLAYER else MAX_CHANNELS_PER_ROW - 1)
    return channels


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
                "special": bool(definition.get("special", False)),
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


def scene_index_with_enemies(min_count: int = 1) -> int:
    """Engine index of the first scene with at least `min_count` enemies.

    Engine tests are about the engine, not about which level happens to be first in
    scenes/scenes.json, so they pick a scene that actually carries the content they need.
    """
    for index, name in enumerate(scene_files()):
        if len(scene_objects(name, "enemy")) >= min_count:
            return index
    raise AssertionError(
        f"no scene in scenes/scenes.json defines {min_count} enemy(ies) - the enemy runtime "
        f"tests need one"
    )


def scene_index_with_secrets(
    min_count: int = 1,
    *,
    special: bool = False,
    static: bool = False,
    with_dependency: bool = False,
    require_next: bool = False,
    exclude: tuple[int, ...] = (),
) -> int:
    """Engine index of the first scene with at least `min_count` secrets.

    `special=True` additionally requires a secret with the catalogue `special` flag,
    `static=True` a non-blinking one (the blink-cadence test needs a static reference),
    `with_dependency=True` a secret that depends on another one (stage progression),
    `require_next=True` a scene that has a successor (scene-transition assertions) and
    `exclude` skips already used scene indices (tests that need two different scenes).
    """
    for index, name in enumerate(scene_files()):
        if index in exclude:
            continue
        if require_next and index + 1 >= len(scene_files()):
            continue
        secrets = scene_objects(name, "secret")
        selected = [
            s
            for s in secrets
            if (not special or s.get("special"))
            and (not static or not s.get("blink"))
            and (not with_dependency or s.get("dependency"))
        ]
        if len(selected) >= min_count:
            return index
    qualifiers = "".join(
        [
            ", special" if special else "",
            ", static (non-blinking)" if static else "",
            ", with a dependency" if with_dependency else "",
            ", with a successor scene" if require_next else "",
            f", excluding {exclude}" if exclude else "",
        ]
    )
    raise AssertionError(
        f"no scene in scenes/scenes.json defines {min_count} secret(s){qualifiers} - the secret "
        f"runtime tests need one"
    )


def scene_index_with_platforms(
    min_count: int = 1, *, exclude: tuple[int, ...] = ()
) -> int:
    """Engine index of the first scene with at least `min_count` platforms."""
    for index, name in enumerate(scene_files()):
        if index in exclude:
            continue
        if len(scene_platforms(index)) >= min_count:
            return index
    raise AssertionError(
        f"no scene in scenes/scenes.json defines {min_count} platform(s) "
        f"(excluding {exclude})"
    )


def scene_index_with_missile_platform(exclude: tuple[int, ...] = ()) -> int:
    """Engine index of the first scene with a missile-type platform."""
    for index, name in enumerate(scene_files()):
        if index in exclude:
            continue
        if any(p["type_code"] == 1 for p in scene_platforms(index)):
            return index
    raise AssertionError(
        f"no scene in scenes/scenes.json defines a missile platform (excluding {exclude})"
    )


def scene_platform_roles(scene_index: int) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Platforms of a scene grouped by the roles the player/enemy physics scenarios need.

    Returns (roles, missing) - `missing` lists the role names this scene cannot provide, so a
    caller can pick another scene or fail with a precise message instead of asserting against
    the wrong layout (Rule 05: reordering scenes in scenes/scenes.json must not silently change
    the physics fixture).
    """
    platforms = scene_platforms(scene_index)
    scene = load_scene(scene_files()[scene_index])
    spawn = scene.get("player_spawn") or {}
    scene_width = int(scene["scene"]["width"])
    roles: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    def add(role: str, platform: Optional[dict[str, Any]]) -> None:
        if platform is None:
            missing.append(role)
        else:
            roles[role] = platform

    if "x" not in spawn or "y" not in spawn:
        missing.append("player_spawn")
        return roles, missing

    floor = next(
        (
            p
            for p in platforms
            if p["y"] == spawn["y"] + 20 and p["x"] <= spawn["x"] + 4 < p["x"] + p["width"]
        ),
        None,
    )
    add("floor", floor)

    if floor is not None:
        add("upper", next((p for p in platforms if p["y"] == floor["y"] - 16), None))
        # A ceiling row for the head-bump scenarios: prefer the row three tiers above the floor
        # (the forest layout), then two tiers, then anything above the floor.
        ceiling = next((p for p in platforms if p["y"] == floor["y"] - 48), None)
        if ceiling is None:
            ceiling = next((p for p in platforms if p["y"] == floor["y"] - 32), None)
        if ceiling is None:
            ceiling = next((p for p in platforms if p["y"] < floor["y"]), None)
        add("ceiling", ceiling)
        add(
            "missile_left",
            next(
                (
                    p
                    for p in platforms
                    if p["type_code"] == 1
                    and p["y"] == floor["y"]
                    and p["x"] + p["width"] <= floor["x"]
                ),
                None,
            ),
        )

    add("left_edge", next((p for p in platforms if p["x"] == 0), None))
    add("right_edge", next((p for p in platforms if p["x"] + p["width"] == scene_width), None))
    top_row_y = min((p["y"] for p in platforms), default=None)
    add("top", next((p for p in platforms if p["y"] == top_row_y), None))

    # The sprite platform directly to the left of a missile platform on the same row, closest
    # first (the jump scenarios must actually reach it with JUMP_SHORT_LEN).
    jump_from = jump_to = None
    best_gap = None
    for platform in platforms:
        if platform["type_code"] != 1:
            continue
        left = None
        for q in platforms:
            if q["y"] != platform["y"] or q["type_code"] != 0:
                continue
            gap = platform["x"] - (q["x"] + q["width"])
            if gap < 0:
                continue
            if left is None or gap < best_gap:
                left, best_gap = q, gap
        if left is not None:
            jump_from, jump_to = platform, left
            break
    add("jump_from", jump_from)
    add("jump_to", jump_to)

    used_ids = {p["id"] for p in roles.values()}
    add("spare", next((p for p in platforms if p["id"] not in used_ids), None))
    return roles, missing


def physics_fixture_scene() -> tuple[int, dict[str, dict[str, Any]]]:
    """(engine index, platform roles) of the first scene the physics scenarios can run on."""
    report: list[str] = []
    for index, name in enumerate(scene_files()):
        roles, missing = scene_platform_roles(index)
        if not missing:
            return index, roles
        report.append(f"    {name}: missing {', '.join(missing)}")
    raise AssertionError(
        "no scene in scenes/scenes.json provides the platform roles the player/enemy physics "
        "tests need (floor under the spawn, one row above, a ceiling two rows above, both screen "
        "edges, the top row, a missile platform with a sprite platform to its left and a spare "
        "slot):\n" + "\n".join(report)
    )


def scene_engine_index(scene_file: str) -> int:
    """Engine scene index of a scene file (its position in scenes/scenes.json)."""
    return scene_files().index(scene_file)

def player_spawn(scene_index: int) -> dict[str, Any]:
    """`player_spawn` block (x/y/color) of the scene at that engine index."""
    return load_scene(scene_files()[scene_index])["player_spawn"]


def scene_platform_count(scene_index: int) -> int:
    """Number of platforms defined by the scene at that engine index."""
    return len(load_scene(scene_files()[scene_index])["platforms"])


def scene_platforms(scene_index: int) -> list[dict[str, Any]]:
    """Platforms of the scene at that engine index, in the compiler's order (JSON order).

    Each entry carries the JSON fields plus the geometry the engine sees (`x`, `y`, `width`,
    `height`) and the compiler's `type_code` (0 = sprite/player, 1 = missile).
    """
    scene = load_scene(scene_files()[scene_index])
    return [
        {
            **platform,
            "type_code": 0 if platform["type"] == "sprite" else 1,
            "x": platform["position"]["x"],
            "y": platform["position"]["y"],
            "width": platform["width"],
            "height": platform["height"],
        }
        for platform in scene["platforms"]
    ]


def scene_platform(scene_index: int, platform_id: str) -> dict[str, Any]:
    """Platform by scene id (fails loudly when the scene no longer defines it)."""
    for platform in scene_platforms(scene_index):
        if platform["id"] == platform_id:
            return platform
    raise AssertionError(
        f"scene {scene_index} ({scene_files()[scene_index]}) has no platform '{platform_id}'"
    )


def scene_platform_index(scene_index: int, platform_id: str) -> int:
    """Engine index of a platform id (its position in the `scene_plat_*` tables)."""
    for index, platform in enumerate(scene_platforms(scene_index)):
        if platform["id"] == platform_id:
            return index
    raise AssertionError(
        f"scene {scene_index} ({scene_files()[scene_index]}) has no platform '{platform_id}'"
    )


def platform_supporting(scene_index: int, x: int, y: int) -> dict[str, Any]:
    """Platform of row `y` whose x-range contains `x` - i.e. what holds a sprite there."""
    row = [p for p in scene_platforms(scene_index) if p["y"] == y]
    for platform in row:
        if platform["x"] <= x < platform["x"] + platform["width"]:
            return platform
    raise AssertionError(
        f"scene {scene_index}: no platform at row y={y} covers x={x} "
        f"(platforms on that row: {[(p['id'], p['x'], p['width']) for p in row]})"
    )


def free_x_on_row(scene_index: int, y: int, start_x: int) -> int:
    """First x >= start_x on platform row `y` that no platform covers (a fall-through spot)."""
    row = [p for p in scene_platforms(scene_index) if p["y"] == y]
    x = start_x
    while x < 160 and any(p["x"] <= x < p["x"] + p["width"] for p in row):
        x += 1
    return x


def player_spawn_pmg_y(scene_index: int) -> int:
    """PMG scanline the engine derives from the scene spawn (`player_init`: y * 2 + 52)."""
    return player_spawn(scene_index)["y"] * 2 + 52


def jump_dy_total(mem, labels, table: str, length: int) -> int:
    """Signed sum of a compiled jump vertical table (the net vertical displacement).

    A well-formed jump profile returns to its starting line, so this is 0.
    """
    total = 0
    for i in range(length):
        value = mem[labels[table] + i]
        total += value - 256 if value >= 128 else value
    return total


def jump_apex_dy(mem, labels, table: str, length: int) -> int:
    """Lowest (most negative) running sum of a jump vertical table = the apex offset.

    Lets tests derive the jump height from the ROM table the engine actually uses instead
    of pinning the apex as a literal.
    """
    total = 0
    apex = 0
    for i in range(length):
        value = mem[labels[table] + i]
        total += value - 256 if value >= 128 else value
        apex = min(apex, total)
    return apex


def jump_dx_total(mem, labels, table: str, length: int) -> int:
    """Sum of a compiled jump horizontal table (`JUMP_SHORT_DX`, `JUMP_LONG_DX`, ...)."""
    return sum(mem[labels[table] + i] for i in range(length))


def scene_special_secret_count(scene_index: int) -> int:
    """Number of secrets with "special": true placed in the scene at that index."""
    return sum(1 for secret in scene_objects(scene_files()[scene_index], "secret") if secret["special"])


def special_secret_total() -> int:
    """Total number of "special" secrets across all scenes (the HUD icon capacity)."""
    return sum(scene_special_secret_count(i) for i in range(len(scene_files())))




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
    """Both double-buffer HPOSM<channel> addresses used for `zone`."""
    if zone == 0:
        base = labels[f"DLI_Z0_HPOS_M{channel}"]
        return [base, base + 1]
    base = labels[f"DLI_ZONE_HPOS_M{channel}"] + (zone - 1)
    return [base, base + 8]


def dli_secret_color_slots(labels, zone: int) -> list[int]:
    """Both double-buffer 5th-player colour addresses used for `zone`."""
    if zone == 0:
        base = labels["DLI_Z0_SECRET_COL"]
        return [base, base + 1]
    base = labels["DLI_ZONE_SECRET_COL"] + (zone - 1)
    return [base, base + 8]


def dli_enemy_hpos_slots(labels, zone: int, channel: int) -> list[int]:
    """Both double-buffer HPOSP<channel+1> addresses used for `zone`.

    The DLI applies slot `s` on the guard line of pas `s`, i.e. one platform row before the row
    whose sprites stand on it; zone 0 is the pre-frame set applied in VBLANK.
    """
    if zone == 0:
        base = labels[f"DLI_Z0_HPOS_P{channel + 1}"]
        return [base, base + 1]
    base = labels[f"DLI_ZONE_HPOS_P{channel + 1}"] + (zone - 1)
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
    - once no active secret remains, every uncollected secret whose dependency matches
      the definition id of *any* secret collected so far is activated (one stage at a
      time) - a stage may mix definitions, e.g. keys + skulls;
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
        if any(self.active):
            return []
        # Mirror of the nested scan in secret_collect (scenes/game.asm): unlock by the
        # definition of any collected secret, not only by the one collected last.
        collected_defs = {
            self.secrets[i]["definition_id"]
            for i in range(len(self.secrets))
            if self.collected[i]
        }
        unlocked = [
            i
            for i, secret in enumerate(self.secrets)
            if not self.collected[i] and (secret.get("dependency") or 0) in collected_defs
        ]
        for i in unlocked:
            self.active[i] = True
        if not unlocked and all(self.collected):
            self.scene_advanced = True
        return unlocked

    def uncollected_description(self) -> str:
        """Human-readable list of the secrets this model could not collect."""
        return ", ".join(
            f"id={self.secrets[i]['id']} def={self.secrets[i]['definition_id']} "
            f"dep={self.secrets[i].get('dependency')}"
            for i in range(len(self.secrets))
            if not self.collected[i]
        )


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
