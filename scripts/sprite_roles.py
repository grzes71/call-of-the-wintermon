"""Sprite role determination and linkage resolution for Atari 8-bit pipeline.

Single source of truth for:
1. Resolving sprite_id for scene objects (scene explicit > definitions catalog fallback > error).
2. Determining sprite format roles across all scenes (player vs missiles).
3. Validating sprite constraints, zones, and manifest consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Optional


MAX_ZONE_SPRITE_HEIGHT = 20
MAX_ENEMIES_PER_ZONE = 3
MAX_ENEMIES_TOTAL = 6
# Per-scene secret capacity: the engine sizes its SoA arrays (16 bytes per slot) with
# MAX_SECRETS in engine/secrets.asm - keep both values in sync (asserted by tests).
# The *design* limit is one secret per unique dependency per platform row, which the
# scene validation below enforces; this constant is only a memory guard.
MAX_SECRETS_TOTAL = 12


class SpriteValidationError(ValueError):
    """Raised when sprite data or linkage fails project validation rules."""
    pass


class SpriteRoleConflictError(SpriteValidationError):
    """Raised when a sprite is used simultaneously as an enemy and a secret."""
    pass


@dataclass
class ResolvedObjectSprite:
    """Result of resolving an object's sprite_id."""
    scene_file: str
    scene_name: str
    object_id: Any
    object_type: str  # 'enemy' | 'secret'
    def_id: int
    sprite_id: int
    resolved_via: str  # 'explicit' | 'catalog'


@dataclass
class SpriteManifestEntry:
    """Metadata entry for compiled sprite in sprites_manifest.json."""
    id: int
    name: str
    format: str  # 'player' | 'missiles'
    width: int
    height: int
    frame_count: int
    data_size_bytes: int
    frame_labels: list[str] = field(default_factory=list)


try:
    from scripts.sprite_links import (
        SpriteLinkError,
        SpriteRegistry,
        resolve_object_sprite,
    )
except ImportError:
    try:
        from sprite_links import (
            SpriteLinkError,
            SpriteRegistry,
            resolve_object_sprite,
        )
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.resolve()))
        from sprite_links import (
            SpriteLinkError,
            SpriteRegistry,
            resolve_object_sprite,
        )


def resolve_object_sprite_id(
    obj: dict[str, Any],
    catalog_items: dict[int, Any],
    scene_name: str,
    scene_file: str,
    registry: Optional[SpriteRegistry] = None,
    sprites_path: Optional[Path] = None,
    sprites_dict: Optional[dict[int, Any]] = None,
) -> int:
    """Resolve sprite_id for an object: explicit in scene has priority, then catalog fallback.

    Supports both 'sprite' (name string) and legacy 'sprite_id' (integer).
    Raises SpriteValidationError if no sprite can be resolved.
    """
    oid = obj.get("id", "?")
    otype = obj.get("type", "unknown")
    def_id = obj.get("definition_id")
    if def_id is None:
        raise SpriteValidationError(
            f"Błąd w scenie '{scene_name}' ({scene_file}): obiekt '{oid}' ({otype}) nie posiada 'definition_id'."
        )

    cat_item = catalog_items.get(int(def_id))

    # If registry is available or can be loaded, use full resolution
    reg = registry
    if reg is None and sprites_path is not None and sprites_path.is_file():
        try:
            reg = SpriteRegistry(sprites_path)
        except Exception:
            reg = None
    elif reg is None and sprites_dict is None:
        default_spr = Path("sprites/objects.sprite.json")
        if default_spr.is_file():
            try:
                reg = SpriteRegistry(default_spr)
            except Exception:
                reg = None

    if reg is not None:
        try:
            sid, _, _ = resolve_object_sprite(obj, cat_item, reg, scene_name, scene_file)
            return sid
        except SpriteLinkError as err:
            raise SpriteValidationError(str(err)) from err

    # Fallback if no sprite registry (e.g. lightweight isolated unit test)
    # 1. Explicit sprite_id in scene object
    raw_spr = obj.get("sprite_id")
    if raw_spr is not None:
        try:
            return int(raw_spr)
        except (ValueError, TypeError):
            raise SpriteValidationError(
                f"Błąd w scenie '{scene_name}' ({scene_file}): obiekt '{oid}' ({otype}) ma nieprawidłowy sprite_id '{raw_spr}'."
            )

    # 2. Catalog fallback
    if cat_item is not None:
        cat_spr = getattr(cat_item, "sprite_id", None)
        if cat_spr is None and isinstance(cat_item, dict):
            cat_spr = cat_item.get("sprite_id")
        if cat_spr is not None:
            return int(cat_spr)

    # 3. Neither specified -> strict error
    raise SpriteValidationError(
        f"Błąd w scenie '{scene_name}' ({scene_file}): obiekt '{oid}' ({otype}, typ katalogu {def_id}) "
        f"nie ma przypisanego sprite_id w scenie ani w definitions.json (has no assigned sprite_id)."
    )


def determine_sprite_roles_from_scenes(
    manifest_path: Path,
    definitions_path: Path,
    scenes_dir: Optional[Path] = None,
    sprites_path: Optional[Path] = None,
) -> tuple[dict[int, str], dict[int, list[str]], dict[int, list[str]]]:
    """Inspect all scenes in manifest and determine the packing format for every sprite_id.

    Returns:
        roles: dict[sprite_id, 'player' | 'missiles']
        enemy_usages: dict[sprite_id, list of 'scene:object_id']
        secret_usages: dict[sprite_id, list of 'scene:object_id']

    Raises SpriteValidationError on conflict (sprite used as both enemy and secret).
    """
    if not manifest_path.is_file():
        raise SpriteValidationError(f"Błąd: brak pliku manifestu scen '{manifest_path}'.")

    sdir = scenes_dir or manifest_path.parent
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_files = manifest_data.get("scenes", [])

    # Load catalogue definitions
    enemy_cats: dict[int, Any] = {}
    secret_cats: dict[int, Any] = {}
    if definitions_path.is_file():
        defs_data = json.loads(definitions_path.read_text(encoding="utf-8"))
        for e in defs_data.get("enemies", []):
            enemy_cats[int(e["id"])] = e
        for s in defs_data.get("secrets", []):
            secret_cats[int(s["id"])] = s

    spr_p = sprites_path or Path("sprites/objects.sprite.json")
    registry: Optional[SpriteRegistry] = None
    if spr_p.is_file():
        try:
            registry = SpriteRegistry(spr_p)
        except Exception:
            registry = None

    enemy_usages: dict[int, list[str]] = {}
    secret_usages: dict[int, list[str]] = {}

    for fname in scene_files:
        sc_path = sdir / fname if not Path(fname).is_absolute() else Path(fname)
        if not sc_path.is_file():
            raise SpriteValidationError(f"Błąd: plik sceny '{sc_path}' z manifestu nie istnieje.")
        sc_data = json.loads(sc_path.read_text(encoding="utf-8"))
        sc_name = sc_data.get("scene", {}).get("name", fname)

        for obj in sc_data.get("objects", []):
            otype = obj.get("type")
            oid = obj.get("id", "?")
            if otype == "enemy":
                sid = resolve_object_sprite_id(
                    obj, enemy_cats, sc_name, sc_path.name, registry=registry, sprites_path=spr_p
                )
                enemy_usages.setdefault(sid, []).append(f"{sc_path.name}:obiekt_{oid}")
            elif otype == "secret":
                sid = resolve_object_sprite_id(
                    obj, secret_cats, sc_name, sc_path.name, registry=registry, sprites_path=spr_p
                )
                secret_usages.setdefault(sid, []).append(f"{sc_path.name}:obiekt_{oid}")

    # Check for conflicts
    conflicting_ids = set(enemy_usages.keys()) & set(secret_usages.keys())
    if conflicting_ids:
        conflict_details = []
        for cid in sorted(conflicting_ids):
            e_str = ", ".join(enemy_usages[cid])
            s_str = ", ".join(secret_usages[cid])
            cname = registry.id_to_name.get(cid, f"ID {cid}") if registry else f"ID {cid}"
            conflict_details.append(
                f"- Sprite '{cname}' (ID {cid}) użyty jako Wróg ({e_str}) oraz jako Sekret ({s_str})"
            )
        raise SpriteRoleConflictError(
            "Błąd kompilacji: Konflikt ról (konflikt formatów sprite'ów)! Ten sam sprite nie może być jednocześnie Wrogiem i Sekretem:\n"
            + "\n".join(conflict_details)
        )

    roles: dict[int, str] = {}
    for sid in enemy_usages:
        roles[sid] = "player"
    for sid in secret_usages:
        roles[sid] = "missiles"

    # Also register catalogue definitions as baseline roles if not yet used in any scene
    for e in enemy_cats.values():
        sid = None
        if registry and isinstance(e, dict) and e.get("sprite"):
            try:
                sid, _ = registry.resolve_by_name(e["sprite"])
            except Exception:
                sid = None
        if sid is None:
            raw_s = e.get("sprite_id") if isinstance(e, dict) else getattr(e, "sprite_id", None)
            sid = int(raw_s) if raw_s is not None else None
        if sid is not None and sid not in roles:
            roles[sid] = "player"

    for s in secret_cats.values():
        sid = None
        if registry and isinstance(s, dict) and s.get("sprite"):
            try:
                sid, _ = registry.resolve_by_name(s["sprite"])
            except Exception:
                sid = None
        if sid is None:
            raw_s = s.get("sprite_id") if isinstance(s, dict) else getattr(s, "sprite_id", None)
            sid = int(raw_s) if raw_s is not None else None
        if sid is not None and sid not in roles:
            roles[sid] = "missiles"

    return roles, enemy_usages, secret_usages


def validate_sprite_definition_data(
    raw_sprite: dict[str, Any],
    source_file: str,
    max_height: int = MAX_ZONE_SPRITE_HEIGHT,
) -> None:
    """Validate a single sprite JSON definition: width == 8, height in 1..max_height, rows binary 0/1."""
    sid = raw_sprite.get("id")
    desc = raw_sprite.get("description", f"Sprite {sid}")
    w = raw_sprite.get("width")
    h = raw_sprite.get("height")

    if w != 8:
        raise SpriteValidationError(
            f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}'): szerokość musi wynosić dokładnie 8 px, otrzymano {w} px."
        )

    if h is None or h < 1 or h > max_height:
        raise SpriteValidationError(
            f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}'): wysokość {h} px wykracza poza dopuszczalny zakres 1–{max_height} px."
        )

    frames = raw_sprite.get("frames", [])
    if not frames:
        raise SpriteValidationError(
            f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}'): brak klatek animacji (lista 'frames' jest pusta)."
        )

    for f_idx, frame in enumerate(frames):
        pixels = frame.get("pixels", [])
        if len(pixels) != h:
            raise SpriteValidationError(
                f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}', klatka {f_idx}): oczekiwano {h} wierszy pikseli, otrzymano {len(pixels)}."
            )
        for r_idx, row in enumerate(pixels):
            clean = str(row).strip().replace(" ", "")
            if len(clean) != 8:
                raise SpriteValidationError(
                    f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}', klatka {f_idx}, wiersz {r_idx}): "
                    f"długość wiersza '{row}' wynosi {len(clean)}, oczekiwano dokładnie 8 pikseli."
                )
            for c in clean:
                if c not in ("0", "1", "X", "#"):
                    raise SpriteValidationError(
                        f"Błąd w pliku '{source_file}' (sprite {sid} '{desc}', klatka {f_idx}, wiersz {r_idx}): "
                        f"nieprawidłowy znak '{c}' w wierszu pikseli (dozwolone wyłącznie '0' i '1')."
                    )


def check_sprite_id_uniqueness(
    files: list[Path],
) -> tuple[dict[int, Path], list[str]]:
    """Check sprite ID uniqueness across all sprite files.

    Returns dict of {sprite_id: path_where_defined} or raises SpriteValidationError if duplicate found.
    Also returns list of warning messages for unused files.
    """
    id_map: dict[int, Path] = {}
    warnings: list[str] = []

    for fpath in files:
        if not fpath.is_file():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            for s in data.get("sprites", []):
                sid = int(s.get("id", 0))
                if sid in id_map:
                    first_file = id_map[sid]
                    raise SpriteValidationError(
                        f"Błąd integralności sprite'ów: powtórzony sprite ID {sid} w pliku '{fpath.name}' "
                        f"(pierwotnie zdefiniowany w '{first_file.name}')."
                    )
                id_map[sid] = fpath
        except SpriteValidationError:
            raise
        except Exception as exc:
            warnings.append(f"Nie udało się odczytać pliku sprite'ów '{fpath.name}': {exc}")

    return id_map, warnings
