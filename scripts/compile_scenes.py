"""Compile scene definitions (scenes/*.json) into Atari 8-bit 6502 MADS assembly data tables.

Target: Atari 800XL / 65XE (MOS 6502, 64 KB RAM)
Display: ANTIC Mode E (160x96 2bpp) + Player-Missile Graphics (PMG)

Reads scenes listed in scenes/scenes.json, validates them, and produces Structure-of-Arrays (SoA)
data tables in gen/scenes_data.asm for fast 6502 indexing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any


# Known tileset mappings matching gen/tiles_data.asm equates
TILESET_NAME_TO_ID: dict[str, int] = {
    "castles": 0,
    "depths": 1,
    "hell": 2,
    "trees": 3,
}

TILESET_ID_TO_EQUATE: dict[int, str] = {
    0: "TILESET_CASTLES",
    1: "TILESET_DEPTHS",
    2: "TILESET_HELL",
    3: "TILESET_TREES",
}

# Object speed mapping
OBJ_SPEED_MAP: dict[str, int] = {
    "slow": 0,
    "medium": 1,
    "fast": 2,
}

# Object movement strategy mapping
OBJ_STRATEGY_MAP: dict[str, int] = {
    "stationary": 0,
    "left_right": 1,
    "right_left": 2,
    "patrol": 3,
    "ambush": 4,
}

# Polish diacritics mapping for Atari 8-bit custom font
POLISH_CHARS: dict[str, int] = {
    "Ą": 65, "Ć": 66, "Ę": 67, "Ł": 68, "Ń": 69, "Ó": 70, "Ś": 71, "Ź": 72, "Ż": 73,
    "ą": 81, "ć": 82, "ę": 83, "ł": 84, "ń": 85, "ó": 86, "ś": 87, "ź": 88, "ż": 89,
}


def char_to_atari_screencode(c: str) -> int:
    """Convert Unicode character to Atari ANTIC 2 internal screen code."""
    if c in POLISH_CHARS:
        return POLISH_CHARS[c]
    val = ord(c)
    if 32 <= val <= 95:
        return val - 32
    if 96 <= val <= 127:
        return val
    if 0 <= val <= 31:
        return val + 64
    return 0  # Blank space


def text_to_screencodes_line(text: str, width: int = 40) -> list[int]:
    """Center text within width characters and convert to Atari screen codes."""
    stripped = text.strip()
    if len(stripped) > width:
        stripped = stripped[:width]
    pad_left = (width - len(stripped)) // 2
    pad_right = width - len(stripped) - pad_left
    padded = (" " * pad_left) + stripped + (" " * pad_right)
    return [char_to_atari_screencode(c) for c in padded]


@dataclass
class CatalogueItem:
    """Enemy or Secret definition from catalogues."""

    id: int
    name: str
    atari_color: int
    blink: bool = False
    dependency: Optional[int] = None


@dataclass
class SceneElementData:
    """Compiled background graphics element."""

    id: str
    tileset_id: int
    src_x_px: int
    src_x_byte: int
    src_y: int
    w_px: int
    w_bytes: int
    h_lines: int
    dst_x_px: int
    dst_x_byte: int
    dst_y: int
    flip_x: bool
    z_index: int


@dataclass
class PlatformData:
    """Compiled platform collider / PMG element."""

    id: str
    type_code: int  # 0 = sprite, 1 = missile
    x: int
    y: int
    width: int
    height: int
    color_profile_id: int | None = None
    colors: list[int] = field(default_factory=lambda: [0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80])


@dataclass
class SceneObjectData:
    """Compiled enemy or secret entity."""

    id: int
    type_code: int  # 0 = enemy, 1 = secret
    def_id: int
    platform_idx: int
    x: int
    y: int
    speed_code: int
    strategy_code: int
    dependency_id: int
    atari_color: int
    blink: bool


PAS_Y_COORDS = [8, 24, 40, 56, 72, 88]

TILESET_PALETTES: dict[int, tuple[int, int, int]] = {
    0: (0x94, 0xD6, 0xEA),  # castles
    1: (0xA2, 0xA6, 0xBA),  # depths
    2: (0x32, 0x26, 0x1C),  # hell
    3: (0xC4, 0xC8, 0xDC),  # trees
}


@dataclass
class SceneDliCompiledData:
    """Compiled DLI table data for a single scene (285 bytes)."""

    # 45 tables x 6 bytes = 270 bytes
    hpos_p1: list[int]          # 6 bytes (pasy 0..5)
    hpos_p2: list[int]          # 6 bytes
    hpos_p3: list[int]          # 6 bytes
    hpos_m1: list[int]          # 6 bytes
    hpos_m2: list[int]          # 6 bytes
    hpos_m3: list[int]          # 6 bytes
    bg_colpf0: list[int]        # 6 bytes
    bg_colpf1: list[int]        # 6 bytes
    bg_colpf2: list[int]        # 6 bytes
    pas_c1_sl: list[list[int]]  # 8 lists of 6 bytes
    pas_c2_sl: list[list[int]]  # 8 lists of 6 bytes
    pas_c3_sl: list[list[int]]  # 8 lists of 6 bytes
    zone_hpos_p1: list[int]     # 6 bytes (zones 1..6)
    zone_col_p1: list[int]      # 6 bytes
    zone_hpos_p2: list[int]     # 6 bytes
    zone_col_p2: list[int]      # 6 bytes
    zone_hpos_p3: list[int]     # 6 bytes
    zone_col_p3: list[int]      # 6 bytes
    zone_hpos_m0: list[int]     # 6 bytes
    zone_hpos_m1: list[int]     # 6 bytes
    zone_hpos_m2: list[int]     # 6 bytes
    zone_hpos_m3: list[int]     # 6 bytes
    zone_secret_col: list[int]  # 6 bytes
    zone_prior: list[int]       # 6 bytes
    # Zone 0 initial values (15 bytes)
    z0_hpos_p1: int
    z0_col_p1: int
    z0_hpos_p2: int
    z0_col_p2: int
    z0_hpos_p3: int
    z0_col_p3: int
    z0_hpos_m0: int
    z0_hpos_m1: int
    z0_hpos_m2: int
    z0_hpos_m3: int
    z0_secret_col: int
    z0_prior: int
    z0_colpf0: int
    z0_colpf1: int
    z0_colpf2: int


def compile_scene_dli_data(
    elements: list[SceneElementData],
    platforms: list[PlatformData],
    objects: list[SceneObjectData],
    primary_tileset_id: int,
) -> SceneDliCompiledData:
    """Compile platform channels, profiles, palettes, and zones for unified DLI."""
    # 1. Determine background palettes
    upper_elements = [e for e in elements if e.dst_y < 44]
    upper_ts = upper_elements[0].tileset_id if upper_elements else primary_tileset_id
    upper_palette = TILESET_PALETTES.get(upper_ts, (0xC4, 0xC8, 0xDC))

    lower_elements = [e for e in elements if e.dst_y >= 44]
    lower_ts = lower_elements[0].tileset_id if lower_elements else upper_ts
    lower_palette = TILESET_PALETTES.get(lower_ts, upper_palette)

    # Background palette per pas:
    # Pas 0 (line 8): upper
    # Pas 1 (line 24): upper
    # Pas 2 (line 40): lower (swapped in Faza C at line 44)
    # Pas 3 (line 56): lower
    # Pas 4 (line 72): lower
    # Pas 5 (line 88): upper (restored in Faza C at line 92)
    bg_colpf0 = [upper_palette[0], upper_palette[0], lower_palette[0], lower_palette[0], lower_palette[0], upper_palette[0]]
    bg_colpf1 = [upper_palette[1], upper_palette[1], lower_palette[1], lower_palette[1], lower_palette[1], upper_palette[1]]
    bg_colpf2 = [upper_palette[2], upper_palette[2], lower_palette[2], lower_palette[2], lower_palette[2], upper_palette[2]]

    # 2. Compile platforms for the 6 pas
    hpos_p1 = [0] * 6
    hpos_p2 = [0] * 6
    hpos_p3 = [0] * 6
    hpos_m1 = [0] * 6
    hpos_m2 = [0] * 6
    hpos_m3 = [0] * 6

    pas_c1_sl = [[0] * 6 for _ in range(8)]
    pas_c2_sl = [[0] * 6 for _ in range(8)]
    pas_c3_sl = [[0] * 6 for _ in range(8)]

    for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
        pas_platforms = [p for p in platforms if p.y == pas_y]
        channels: list[list[PlatformData]] = []
        profile_map: dict[Any, list[PlatformData]] = {}
        for p in pas_platforms:
            prof_key = p.color_profile_id if p.color_profile_id is not None else id(p)
            profile_map.setdefault(prof_key, []).append(p)
        for prof_plats in profile_map.values():
            if len(channels) < 3:
                channels.append(prof_plats)

        for ch_idx, ch_plats in enumerate(channels):
            ch_colors = ch_plats[0].colors if ch_plats else [0] * 8
            if ch_idx == 0:
                for sl in range(8):
                    pas_c1_sl[sl][pas_idx] = ch_colors[sl]
                for p in ch_plats:
                    if p.type_code == 1 or p.width <= 8:
                        hpos_m1[pas_idx] = min(255, max(0, 48 + p.x))
                    else:
                        hpos_p1[pas_idx] = min(255, max(0, 48 + p.x))
            elif ch_idx == 1:
                for sl in range(8):
                    pas_c2_sl[sl][pas_idx] = ch_colors[sl]
                for p in ch_plats:
                    if p.type_code == 1 or p.width <= 8:
                        hpos_m2[pas_idx] = min(255, max(0, 48 + p.x))
                    else:
                        hpos_p2[pas_idx] = min(255, max(0, 48 + p.x))
            elif ch_idx == 2:
                for sl in range(8):
                    pas_c3_sl[sl][pas_idx] = ch_colors[sl]
                for p in ch_plats:
                    if p.type_code == 1 or p.width <= 8:
                        hpos_m3[pas_idx] = min(255, max(0, 48 + p.x))
                    else:
                        hpos_p3[pas_idx] = min(255, max(0, 48 + p.x))

    # 3. Compile enemies and secrets for 7 zones
    def get_zone_idx(y: int) -> int:
        if y < 8:
            return 0
        elif y < 24:
            return 1
        elif y < 40:
            return 2
        elif y < 56:
            return 3
        elif y < 72:
            return 4
        elif y < 88:
            return 5
        else:
            return 6

    zone_objects: dict[int, list[SceneObjectData]] = {z: [] for z in range(7)}
    for obj in objects:
        zid = get_zone_idx(obj.y)
        zone_objects[zid].append(obj)

    # Zone 0 initial values (applied in VBLANK before Pas 0)
    z0_objs = zone_objects[0]
    z0_enemies = [o for o in z0_objs if o.type_code == 0][:3]
    z0_secrets = [o for o in z0_objs if o.type_code == 1][:1]

    z0_hpos_p1 = min(255, max(0, 48 + z0_enemies[0].x)) if len(z0_enemies) > 0 else 0
    z0_col_p1  = z0_enemies[0].atari_color if len(z0_enemies) > 0 else 0
    z0_hpos_p2 = min(255, max(0, 48 + z0_enemies[1].x)) if len(z0_enemies) > 1 else 0
    z0_col_p2  = z0_enemies[1].atari_color if len(z0_enemies) > 1 else 0
    z0_hpos_p3 = min(255, max(0, 48 + z0_enemies[2].x)) if len(z0_enemies) > 2 else 0
    z0_col_p3  = z0_enemies[2].atari_color if len(z0_enemies) > 2 else 0

    if z0_secrets:
        sec = z0_secrets[0]
        z0_hpos_m0 = min(255, max(0, 48 + sec.x))
        z0_hpos_m1 = min(255, max(0, 48 + sec.x + 2))
        z0_hpos_m2 = min(255, max(0, 48 + sec.x + 4))
        z0_hpos_m3 = min(255, max(0, 48 + sec.x + 6))
        z0_secret_col = sec.atari_color
        z0_prior = 0x11
    else:
        z0_hpos_m0 = 0
        z0_hpos_m1 = 0
        z0_hpos_m2 = 0
        z0_hpos_m3 = 0
        z0_secret_col = 0
        z0_prior = 0x01

    # Zones 1..6 (set up in Faza C of pas 0..5, 6 entries)
    zone_hpos_p1 = [0] * 6
    zone_col_p1  = [0] * 6
    zone_hpos_p2 = [0] * 6
    zone_col_p2  = [0] * 6
    zone_hpos_p3 = [0] * 6
    zone_col_p3  = [0] * 6

    zone_hpos_m0 = [0] * 6
    zone_hpos_m1 = [0] * 6
    zone_hpos_m2 = [0] * 6
    zone_hpos_m3 = [0] * 6
    zone_secret_col = [0] * 6
    zone_prior = [0x01] * 6

    for z_idx in range(6):
        target_zone = z_idx + 1  # Zones 1..6
        objs = zone_objects[target_zone]
        enemies = [o for o in objs if o.type_code == 0][:3]
        secrets = [o for o in objs if o.type_code == 1][:1]

        if len(enemies) > 0:
            zone_hpos_p1[z_idx] = min(255, max(0, 48 + enemies[0].x))
            zone_col_p1[z_idx]  = enemies[0].atari_color
        if len(enemies) > 1:
            zone_hpos_p2[z_idx] = min(255, max(0, 48 + enemies[1].x))
            zone_col_p2[z_idx]  = enemies[1].atari_color
        if len(enemies) > 2:
            zone_hpos_p3[z_idx] = min(255, max(0, 48 + enemies[2].x))
            zone_col_p3[z_idx]  = enemies[2].atari_color

        if secrets:
            s = secrets[0]
            zone_hpos_m0[z_idx] = min(255, max(0, 48 + s.x))
            zone_hpos_m1[z_idx] = min(255, max(0, 48 + s.x + 2))
            zone_hpos_m2[z_idx] = min(255, max(0, 48 + s.x + 4))
            zone_hpos_m3[z_idx] = min(255, max(0, 48 + s.x + 6))
            zone_secret_col[z_idx] = s.atari_color
            zone_prior[z_idx] = 0x11
        else:
            zone_prior[z_idx] = 0x01

    return SceneDliCompiledData(
        hpos_p1=hpos_p1,
        hpos_p2=hpos_p2,
        hpos_p3=hpos_p3,
        hpos_m1=hpos_m1,
        hpos_m2=hpos_m2,
        hpos_m3=hpos_m3,
        bg_colpf0=bg_colpf0,
        bg_colpf1=bg_colpf1,
        bg_colpf2=bg_colpf2,
        pas_c1_sl=pas_c1_sl,
        pas_c2_sl=pas_c2_sl,
        pas_c3_sl=pas_c3_sl,
        zone_hpos_p1=zone_hpos_p1,
        zone_col_p1=zone_col_p1,
        zone_hpos_p2=zone_hpos_p2,
        zone_col_p2=zone_col_p2,
        zone_hpos_p3=zone_hpos_p3,
        zone_col_p3=zone_col_p3,
        zone_hpos_m0=zone_hpos_m0,
        zone_hpos_m1=zone_hpos_m1,
        zone_hpos_m2=zone_hpos_m2,
        zone_hpos_m3=zone_hpos_m3,
        zone_secret_col=zone_secret_col,
        zone_prior=zone_prior,
        z0_hpos_p1=z0_hpos_p1,
        z0_col_p1=z0_col_p1,
        z0_hpos_p2=z0_hpos_p2,
        z0_col_p2=z0_col_p2,
        z0_hpos_p3=z0_hpos_p3,
        z0_col_p3=z0_col_p3,
        z0_hpos_m0=z0_hpos_m0,
        z0_hpos_m1=z0_hpos_m1,
        z0_hpos_m2=z0_hpos_m2,
        z0_hpos_m3=z0_hpos_m3,
        z0_secret_col=z0_secret_col,
        z0_prior=z0_prior,
        z0_colpf0=upper_palette[0],
        z0_colpf1=upper_palette[1],
        z0_colpf2=upper_palette[2],
    )


@dataclass
class SceneCompiledData:
    """Full compiled data for a single scene."""

    file_stem: str
    symbol_name: str
    name: str
    width: int
    height: int
    primary_tileset_id: int
    elements: list[SceneElementData] = field(default_factory=list)
    platforms: list[PlatformData] = field(default_factory=list)
    objects: list[SceneObjectData] = field(default_factory=list)
    dli_data: SceneDliCompiledData | None = None


def sanitize_symbol(name: str) -> str:
    """Convert an arbitrary string into a valid assembly label identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower()
    if cleaned and cleaned[0].isdigit():
        cleaned = "sc_" + cleaned
    return cleaned or "scene"


def resolve_tileset_id(source_str: str | None) -> int:
    """Map a source path (e.g. 'tiles/trees.png') to its integer tileset ID."""
    if not source_str:
        return 3  # Default to trees (Forest theme)
    stem = Path(source_str).stem.lower()
    for name, tid in TILESET_NAME_TO_ID.items():
        if name in stem:
            return tid
    return 3


def load_catalogues(
    enemies_file: Path, secrets_file: Path
) -> tuple[dict[int, CatalogueItem], dict[int, CatalogueItem]]:
    """Load enemies and secrets definitions for attribute and color resolution."""
    enemies: dict[int, CatalogueItem] = {}
    if enemies_file.is_file():
        try:
            data = json.loads(enemies_file.read_text(encoding="utf-8"))
            for item in data.get("enemies", []):
                enemies[item["id"]] = CatalogueItem(
                    id=item["id"],
                    name=item.get("name", f"Enemy {item['id']}"),
                    atari_color=item.get("atari_color", 0x42),
                    blink=bool(item.get("blink", False)),
                )
        except Exception as exc:
            print(f"Warning: Failed loading enemies catalog ({exc})", file=sys.stderr)

    secrets: dict[int, CatalogueItem] = {}
    if secrets_file.is_file():
        try:
            data = json.loads(secrets_file.read_text(encoding="utf-8"))
            for item in data.get("secrets", []):
                raw_dep = item.get("dependency")
                dep = int(raw_dep) if (raw_dep is not None and str(raw_dep).strip() != "") else None
                secrets[item["id"]] = CatalogueItem(
                    id=item["id"],
                    name=item.get("name", f"Secret {item['id']}"),
                    atari_color=item.get("atari_color", 0x1A),
                    blink=bool(item.get("blink", False)),
                    dependency=dep,
                )
        except Exception as exc:
            print(f"Warning: Failed loading secrets catalog ({exc})", file=sys.stderr)

    return enemies, secrets


DEFAULT_PLATFORM_COLORS: list[int] = [0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80]


def load_platform_profiles(profiles_file: Path) -> dict[int, list[int]]:
    """Load platform color profiles (8 scanline GTIA color bytes each)."""
    profiles: dict[int, list[int]] = {}
    if profiles_file.is_file():
        try:
            data = json.loads(profiles_file.read_text(encoding="utf-8"))
            items = []
            if isinstance(data, dict):
                items = data.get("profiles") or data.get("platform_profiles", [])
            elif isinstance(data, list):
                items = data
            for item in items:
                raw_id = item.get("id")
                try:
                    pid = int(raw_id)
                except (ValueError, TypeError):
                    continue
                colors = item.get("colors", [])
                if len(colors) == 8:
                    parsed_colors: list[int] = []
                    for c in colors:
                        if isinstance(c, str):
                            val = int(c, 16) if c.startswith(("0x", "0X", "$")) else int(c)
                        else:
                            val = int(c)
                        parsed_colors.append(val & 0xFE)
                    profiles[pid] = parsed_colors
        except Exception as exc:
            print(f"Warning: Failed loading platform profiles ({exc})", file=sys.stderr)
    return profiles


def parse_scene_json(
    scene_file: Path,
    enemies: dict[int, CatalogueItem],
    secrets: dict[int, CatalogueItem],
    profiles: dict[str, list[int]] | None = None,
) -> SceneCompiledData:
    """Parse and validate a scene JSON file into structured compiler models."""
    if not scene_file.is_file():
        raise FileNotFoundError(f"Scene file not found: {scene_file}")

    data = json.loads(scene_file.read_text(encoding="utf-8"))
    scene_meta = data.get("scene", {})
    name = str(scene_meta.get("name", scene_file.stem))
    width = int(scene_meta.get("width", 160))
    height = int(scene_meta.get("height", 96))
    raw_elements = data.get("elements", [])
    primary_tile_src = scene_meta.get("tile_source")
    if not primary_tile_src and raw_elements:
        primary_tile_src = raw_elements[0].get("source")
    primary_tileset_id = resolve_tileset_id(primary_tile_src)

    stem = scene_file.stem
    symbol = sanitize_symbol(stem)

    # 1. Elements
    # Sort elements by z_index ascending
    sorted_elements = sorted(raw_elements, key=lambda e: int(e.get("z_index", 0)))
    elements: list[SceneElementData] = []

    for elem in sorted_elements:
        elem_id = str(elem.get("id", ""))
        ts_id = resolve_tileset_id(elem.get("source"))
        srect = elem.get("source_rect", {})
        pos = elem.get("position", {})

        src_x = int(srect.get("x", 0))
        src_y = int(srect.get("y", 0))
        w_px = int(srect.get("width", 0))
        h_lines = int(srect.get("height", 0))

        dst_x = int(pos.get("x", 0))
        dst_y = int(pos.get("y", 0))
        flip_x = bool(elem.get("flip_x", False))
        z_idx = int(elem.get("z_index", 0))

        src_x_byte = src_x // 4
        w_bytes = (w_px + 3) // 4
        dst_x_byte = max(0, dst_x) // 4

        elements.append(
            SceneElementData(
                id=elem_id,
                tileset_id=ts_id,
                src_x_px=src_x,
                src_x_byte=src_x_byte,
                src_y=src_y,
                w_px=w_px,
                w_bytes=w_bytes,
                h_lines=h_lines,
                dst_x_px=dst_x,
                dst_x_byte=dst_x_byte,
                dst_y=dst_y,
                flip_x=flip_x,
                z_index=z_idx,
            )
        )

    # 2. Platforms
    raw_platforms = data.get("platforms", [])
    platforms: list[PlatformData] = []
    plat_id_to_idx: dict[str, int] = {}
    plat_id_to_y: dict[str, int] = {}

    for idx, p in enumerate(raw_platforms):
        pid = str(p.get("id", f"platform-{idx}"))
        ptype_str = str(p.get("type", "sprite")).lower()
        ptype = 1 if ptype_str == "missile" else 0
        ppos = p.get("position", {})
        px = int(ppos.get("x", 0))
        py = int(ppos.get("y", 0))
        pw = int(p.get("width", 16))
        ph = int(p.get("height", 4))

        plat_id_to_idx[pid] = idx
        plat_id_to_y[pid] = py
        raw_cprof_id = p.get("color_profile_id")
        cprof_id: Optional[int] = None
        if raw_cprof_id is not None and str(raw_cprof_id).strip() != "":
            try:
                cprof_id = int(raw_cprof_id)
            except (ValueError, TypeError):
                cprof_id = None

        if cprof_id is not None and profiles and cprof_id in profiles:
            colors = list(profiles[cprof_id])
        else:
            colors = list(DEFAULT_PLATFORM_COLORS)

        platforms.append(
            PlatformData(
                id=pid,
                type_code=ptype,
                x=px,
                y=py,
                width=pw,
                height=ph,
                color_profile_id=cprof_id,
                colors=colors,
            )
        )

    # 3. Objects
    raw_objects = data.get("objects", [])
    objects: list[SceneObjectData] = []
    row_secret_deps: dict[int, dict[Optional[int], int]] = {}

    for obj in raw_objects:
        oid = int(obj.get("id", 0))
        otype_str = str(obj.get("type", "enemy")).lower()
        is_secret = otype_str in ("secret", "treasure")
        type_code = 1 if is_secret else 0
        def_id = int(obj.get("definition_id", 1))
        plat_id = str(obj.get("platform_id", ""))
        plat_idx = plat_id_to_idx.get(plat_id, 0)
        ox = int(obj.get("x", 0))

        # Y position sits on the assigned platform surface (object height 8)
        plat_y = plat_id_to_y.get(plat_id, 0)
        oy = max(0, plat_y - 8)

        # Speed and movement strategy
        speed_str = str(obj.get("speed", "slow")).lower()
        speed_code = OBJ_SPEED_MAP.get(speed_str, 0) if not is_secret else 0

        strat_str = str(obj.get("movement_strategy", "stationary")).lower()
        strat_code = OBJ_STRATEGY_MAP.get(strat_str, 0) if not is_secret else 0

        # Catalogue lookup for Atari GTIA color, blink, and dependency
        if is_secret:
            cat_item = secrets.get(def_id)
            color = cat_item.atari_color if cat_item else 0x1A
            blink = cat_item.blink if cat_item else False
            dep_val = cat_item.dependency if cat_item else None
            dep_id = int(dep_val) if dep_val is not None else 0

            # Validate unique secret dependency per platform row
            deps_on_row = row_secret_deps.setdefault(plat_y, {})
            if dep_val in deps_on_row:
                first_oid = deps_on_row[dep_val]
                dep_desc = (
                    f"'{secrets[dep_val].name}' (ID {dep_val})"
                    if (dep_val is not None and dep_val in secrets)
                    else "None"
                )
                raise ValueError(
                    f"Scene '{name}' ({scene_file.name}) violates secret row constraint at platform row y={plat_y}: "
                    f"conflict between secret '{first_oid}' and secret '{oid}' (both have dependency {dep_desc}). "
                    f"Only one secret per unique dependency is allowed per row."
                )
            deps_on_row[dep_val] = oid
        else:
            cat_item = enemies.get(def_id)
            color = cat_item.atari_color if cat_item else 0x42
            blink = cat_item.blink if cat_item else False
            dep_id = 0

        objects.append(
            SceneObjectData(
                id=oid,
                type_code=type_code,
                def_id=def_id,
                platform_idx=plat_idx,
                x=ox,
                y=oy,
                speed_code=speed_code,
                strategy_code=strat_code,
                dependency_id=dep_id,
                atari_color=color,
                blink=blink,
            )
        )

    dli_data = compile_scene_dli_data(elements, platforms, objects, primary_tileset_id)

    return SceneCompiledData(
        file_stem=stem,
        symbol_name=symbol,
        name=name,
        width=width,
        height=height,
        primary_tileset_id=primary_tileset_id,
        elements=elements,
        platforms=platforms,
        objects=objects,
        dli_data=dli_data,
    )


def generate_scenes_asm(scenes: list[SceneCompiledData]) -> str:
    """Generate MADS 6502 assembly defining Structure-of-Arrays (SoA) scene structures."""
    lines: list[str] = [
        "; ==============================================================================",
        "; SCENES DATA — CALL OF THE WINTERMON (Auto-generated by compile_scenes.py)",
        "; Target: Atari 800XL / 65XE (MOS 6502, ANTIC Mode E 160x96 2bpp)",
        "; Format: Structure-of-Arrays (SoA) for fast 6502 indexed addressing",
        "; ==============================================================================",
        "",
        "; --- Global Scene Equates ---",
        f"SCENE_COUNT = {len(scenes)}",
        "",
        "; Object Type Equates",
        "OBJ_TYPE_ENEMY          = 0",
        "OBJ_TYPE_SECRET         = 1",
        "",
        "; Enemy Speed Equates",
        "OBJ_SPEED_SLOW          = 0",
        "OBJ_SPEED_MED           = 1",
        "OBJ_SPEED_FAST          = 2",
        "",
        "; Enemy Movement Strategy Equates",
        "OBJ_STRAT_STATIONARY    = 0",
        "OBJ_STRAT_LEFT_RIGHT    = 1",
        "OBJ_STRAT_RIGHT_LEFT    = 2",
        "OBJ_STRAT_PATROL        = 3",
        "OBJ_STRAT_AMBUSH        = 4",
        "",
        "; Platform Type Equates",
        "PLATFORM_TYPE_SPRITE    = 0",
        "PLATFORM_TYPE_MISSILE   = 1",
        "",
    ]

    # Per-scene equates
    lines.append("; --- Per-Scene Constants ---")
    for idx, sc in enumerate(scenes):
        prefix = f"SCENE_{sc.symbol_name.upper()}"
        lines.append(f"{prefix}_ID = {idx}")
        lines.append(f"{prefix}_ELEM_COUNT = {len(sc.elements)}")
        lines.append(f"{prefix}_PLAT_COUNT = {len(sc.platforms)}")
        lines.append(f"{prefix}_OBJ_COUNT  = {len(sc.objects)}")
    lines.append("")

    # Per-scene data blocks
    for idx, sc in enumerate(scenes):
        sym = sc.symbol_name
        screencodes = text_to_screencodes_line(sc.name, width=40)
        sc_bytes = ", ".join(f"${b:02X}" for b in screencodes)
        lines.extend([
            "; " + "=" * 78,
            f"; SCENE {idx}: {sc.name} ({sc.file_stem}.json)",
            "; " + "=" * 78,
            f"scene_{sym}_name",
            f"    dta c'{sc.name}', 0",
            f"scene_{sym}_name_line",
            f"    .byte {sc_bytes}",
            "",
        ])

        # Scene elements
        lines.append(f"; --- Elements ({len(sc.elements)}) ---")
        if sc.elements:
            lines.append(f"scene_{sym}_elem_tileset")
            lines.append("    .byte " + ", ".join(TILESET_ID_TO_EQUATE[e.tileset_id] for e in sc.elements))
            lines.append(f"scene_{sym}_elem_src_x_px")
            lines.append("    .byte " + ", ".join(str(e.src_x_px) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_src_x_byte")
            lines.append("    .byte " + ", ".join(str(e.src_x_byte) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_src_y")
            lines.append("    .byte " + ", ".join(str(e.src_y) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_w_px")
            lines.append("    .byte " + ", ".join(str(e.w_px) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_w_byte")
            lines.append("    .byte " + ", ".join(str(e.w_bytes) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_h_lines")
            lines.append("    .byte " + ", ".join(str(e.h_lines) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_dst_x_px")
            lines.append("    .byte " + ", ".join(f"${(e.dst_x_px & 0xFF):02X}" for e in sc.elements))
            lines.append(f"scene_{sym}_elem_dst_x_byte")
            lines.append("    .byte " + ", ".join(str(e.dst_x_byte) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_dst_y")
            lines.append("    .byte " + ", ".join(str(e.dst_y) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_flags")
            lines.append("    .byte " + ", ".join(str(1 if e.flip_x else 0) for e in sc.elements))
        else:
            lines.extend([
                f"scene_{sym}_elem_tileset    .byte 0",
                f"scene_{sym}_elem_src_x_px   .byte 0",
                f"scene_{sym}_elem_src_x_byte .byte 0",
                f"scene_{sym}_elem_src_y      .byte 0",
                f"scene_{sym}_elem_w_px       .byte 0",
                f"scene_{sym}_elem_w_byte     .byte 0",
                f"scene_{sym}_elem_h_lines    .byte 0",
                f"scene_{sym}_elem_dst_x_px   .byte 0",
                f"scene_{sym}_elem_dst_x_byte .byte 0",
                f"scene_{sym}_elem_dst_y      .byte 0",
                f"scene_{sym}_elem_flags      .byte 0",
            ])
        lines.append("")

        # Scene platforms
        lines.append(f"; --- Platforms ({len(sc.platforms)}) ---")
        if sc.platforms:
            lines.append(f"scene_{sym}_plat_type")
            lines.append("    .byte " + ", ".join(str(p.type_code) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_x")
            lines.append("    .byte " + ", ".join(str(p.x) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_y")
            lines.append("    .byte " + ", ".join(str(p.y) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_w")
            lines.append("    .byte " + ", ".join(str(p.width) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_h")
            lines.append("    .byte " + ", ".join(str(p.height) for p in sc.platforms))
            for sl in range(8):
                lines.append(f"scene_{sym}_plat_color_sl{sl + 1}")
                lines.append("    .byte " + ", ".join(f"${p.colors[sl]:02X}" for p in sc.platforms))
        else:
            lines.extend([
                f"scene_{sym}_plat_type      .byte 0",
                f"scene_{sym}_plat_x         .byte 0",
                f"scene_{sym}_plat_y         .byte 0",
                f"scene_{sym}_plat_w         .byte 0",
                f"scene_{sym}_plat_h         .byte 0",
            ])
            for sl in range(8):
                lines.append(f"scene_{sym}_plat_color_sl{sl + 1} .byte 0")
        lines.append("")

        # Scene objects
        lines.append(f"; --- Objects ({len(sc.objects)}) ---")
        if sc.objects:
            lines.append(f"scene_{sym}_obj_type")
            lines.append("    .byte " + ", ".join(str(o.type_code) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_def_id")
            lines.append("    .byte " + ", ".join(str(o.def_id) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_plat_idx")
            lines.append("    .byte " + ", ".join(str(o.platform_idx) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_x")
            lines.append("    .byte " + ", ".join(str(o.x) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_y")
            lines.append("    .byte " + ", ".join(str(o.y) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_speed")
            lines.append("    .byte " + ", ".join(str(o.speed_code) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_strat")
            lines.append("    .byte " + ", ".join(str(o.strategy_code) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_dep")
            lines.append("    .byte " + ", ".join(str(o.dependency_id) for o in sc.objects))
            lines.append(f"scene_{sym}_obj_color")
            lines.append("    .byte " + ", ".join(f"${o.atari_color:02X}" for o in sc.objects))
            lines.append(f"scene_{sym}_obj_flags")
            lines.append("    .byte " + ", ".join(str(1 if o.blink else 0) for o in sc.objects))
        else:
            lines.extend([
                f"scene_{sym}_obj_type     .byte 0",
                f"scene_{sym}_obj_def_id   .byte 0",
                f"scene_{sym}_obj_plat_idx .byte 0",
                f"scene_{sym}_obj_x        .byte 0",
                f"scene_{sym}_obj_y        .byte 0",
                f"scene_{sym}_obj_speed    .byte 0",
                f"scene_{sym}_obj_strat    .byte 0",
                f"scene_{sym}_obj_dep      .byte 0",
                f"scene_{sym}_obj_color    .byte 0",
                f"scene_{sym}_obj_flags    .byte 0",
            ])
        lines.append("")

    # Master Table (Structure-of-Arrays across all scenes)
    lines.extend([
        "; " + "=" * 78,
        "; MASTER SCENE INDEX TABLES (Structure-of-Arrays)",
        "; " + "=" * 78,
        "scene_name_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_name" for sc in scenes),
        "scene_name_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_name" for sc in scenes),
        "scene_name_line_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_name_line" for sc in scenes),
        "scene_name_line_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_name_line" for sc in scenes),
        "",
        "scene_width_px",
        "    .byte " + ", ".join(str(sc.width) for sc in scenes),
        "scene_height_lines",
        "    .byte " + ", ".join(str(sc.height) for sc in scenes),
        "scene_primary_tileset",
        "    .byte " + ", ".join(TILESET_ID_TO_EQUATE[sc.primary_tileset_id] for sc in scenes),
        "",
        "scene_elem_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_ELEM_COUNT" for sc in scenes),
        "scene_plat_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_PLAT_COUNT" for sc in scenes),
        "scene_obj_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_OBJ_COUNT" for sc in scenes),
        "",
        "; --- Element Pointer Tables ---",
        "scene_elem_tileset_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_tileset" for sc in scenes),
        "scene_elem_tileset_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_tileset" for sc in scenes),
        "scene_elem_src_x_byte_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_src_x_byte" for sc in scenes),
        "scene_elem_src_x_byte_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_src_x_byte" for sc in scenes),
        "scene_elem_src_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_src_y" for sc in scenes),
        "scene_elem_src_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_src_y" for sc in scenes),
        "scene_elem_w_byte_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_w_byte" for sc in scenes),
        "scene_elem_w_byte_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_w_byte" for sc in scenes),
        "scene_elem_h_lines_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_h_lines" for sc in scenes),
        "scene_elem_h_lines_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_h_lines" for sc in scenes),
        "scene_elem_dst_x_byte_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_dst_x_byte" for sc in scenes),
        "scene_elem_dst_x_byte_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_dst_x_byte" for sc in scenes),
        "scene_elem_dst_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_dst_y" for sc in scenes),
        "scene_elem_dst_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_dst_y" for sc in scenes),
        "scene_elem_flags_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_elem_flags" for sc in scenes),
        "scene_elem_flags_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_elem_flags" for sc in scenes),
        "",
        "; --- Platform Pointer Tables ---",
        "scene_plat_type_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_type" for sc in scenes),
        "scene_plat_type_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_type" for sc in scenes),
        "scene_plat_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_x" for sc in scenes),
        "scene_plat_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_x" for sc in scenes),
        "scene_plat_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_y" for sc in scenes),
        "scene_plat_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_y" for sc in scenes),
        "scene_plat_w_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_w" for sc in scenes),
        "scene_plat_w_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_w" for sc in scenes),
        "scene_plat_h_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_h" for sc in scenes),
        "scene_plat_h_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_h" for sc in scenes),
        *[
            line
            for sl in range(1, 9)
            for line in [
                f"scene_plat_color_sl{sl}_lo",
                "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_color_sl{sl}" for sc in scenes),
                f"scene_plat_color_sl{sl}_hi",
                "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_color_sl{sl}" for sc in scenes),
            ]
        ],
        "",
        "; --- Object Pointer Tables ---",
        "scene_obj_type_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_type" for sc in scenes),
        "scene_obj_type_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_type" for sc in scenes),
        "scene_obj_def_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_def_id" for sc in scenes),
        "scene_obj_def_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_def_id" for sc in scenes),
        "scene_obj_plat_idx_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_plat_idx" for sc in scenes),
        "scene_obj_plat_idx_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_plat_idx" for sc in scenes),
        "scene_obj_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_x" for sc in scenes),
        "scene_obj_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_x" for sc in scenes),
        "scene_obj_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_y" for sc in scenes),
        "scene_obj_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_y" for sc in scenes),
        "scene_obj_speed_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_speed" for sc in scenes),
        "scene_obj_speed_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_speed" for sc in scenes),
        "scene_obj_strat_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_strat" for sc in scenes),
        "scene_obj_strat_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_strat" for sc in scenes),
        "scene_obj_dep_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_dep" for sc in scenes),
        "scene_obj_dep_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_dep" for sc in scenes),
        "scene_obj_color_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_color" for sc in scenes),
        "scene_obj_color_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_color" for sc in scenes),
        "scene_obj_flags_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_obj_flags" for sc in scenes),
        "scene_obj_flags_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_obj_flags" for sc in scenes),
        "",
    ])

    return "\n".join(lines)


def generate_scenes_dli_asm(scenes: list[SceneCompiledData]) -> str:
    """Generate MADS 6502 assembly defining DLI SoA data tables for all scenes."""
    lines: list[str] = [
        "; ==============================================================================",
        "; SCENES DLI DATA — CALL OF THE WINTERMON (Auto-generated by compile_scenes.py)",
        "; Target: Atari 800XL / 65XE (MOS 6502, ANTIC Mode D 160x96 2bpp)",
        "; Format: 285 bytes per scene (45 tables x 6 bytes + 15 bytes Zone 0)",
        "; Segment: Loaded under RENDER_TABLES segment ($7A00)",
        "; ==============================================================================",
        "",
    ]

    for sc in scenes:
        sym = sc.symbol_name
        dli = sc.dli_data
        lines.append(f"; --- DLI Data for {sc.name} (285 bytes) ---")
        lines.append(f"scene_{sym}_dli_data")
        if dli:
            lines.append("    ; 1..6: Platform HPOSP1..3 and HPOSM1..3 (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m3))

            lines.append("    ; 7..9: Background Palettes COLPF0..2 (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf0))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf2))

            lines.append("    ; 10..17: Platform Channel 1 Scanlines 0..7 (6 bytes each)")
            for sl in range(8):
                lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.pas_c1_sl[sl]))

            lines.append("    ; 18..25: Platform Channel 2 Scanlines 0..7 (6 bytes each)")
            for sl in range(8):
                lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.pas_c2_sl[sl]))

            lines.append("    ; 26..33: Platform Channel 3 Scanlines 0..7 (6 bytes each)")
            for sl in range(8):
                lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.pas_c3_sl[sl]))

            lines.append("    ; 34..39: Zone Enemies HPOS and Color (P1..P3, 6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p3))

            lines.append("    ; 40..45: Zone Secrets HPOS (M0..M3), Color, and PRIOR (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_m0))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_m1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_m2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_m3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_secret_col))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_prior))

            lines.append("    ; Zone 0 Initial Values (15 bytes)")
            z0_vals = [
                dli.z0_hpos_p1, dli.z0_col_p1, dli.z0_hpos_p2, dli.z0_col_p2, dli.z0_hpos_p3, dli.z0_col_p3,
                dli.z0_hpos_m0, dli.z0_hpos_m1, dli.z0_hpos_m2, dli.z0_hpos_m3, dli.z0_secret_col, dli.z0_prior,
                dli.z0_colpf0, dli.z0_colpf1, dli.z0_colpf2,
            ]
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in z0_vals))
        else:
            lines.append("    :285 .byte 0")
        lines.append("")

    lines.extend([
        "; " + "=" * 78,
        "; MASTER SCENE DLI DATA POINTER TABLES",
        "; " + "=" * 78,
        "scene_dli_data_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_dli_data" for sc in scenes),
        "scene_dli_data_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_dli_data" for sc in scenes),
        "",
    ])

    return "\n".join(lines)


def compile_scenes(
    manifest_path: Path,
    output_path: Path,
    scenes_dir: Path | None = None,
    enemies_path: Path | None = None,
    secrets_path: Path | None = None,
    profiles_path: Path | None = None,
) -> int:
    """Main compilation pipeline: parse manifest, compile scene JSONs, emit ASM."""
    if not manifest_path.is_file():
        print(f"Error: Manifest file '{manifest_path}' not found.", file=sys.stderr)
        return 1

    sdir = scenes_dir or manifest_path.parent
    efile = enemies_path or (manifest_path.parent.parent / "enemies.json")
    sfile = secrets_path or (manifest_path.parent.parent / "secrets.json")
    pfile = profiles_path or (manifest_path.parent.parent / "platform_profiles.json")
    if not pfile.is_file():
        pfile = Path("platform_profiles.json")

    enemies, secrets = load_catalogues(efile, sfile)
    profiles = load_platform_profiles(pfile)

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading manifest '{manifest_path}': {exc}", file=sys.stderr)
        return 1

    scene_filenames = manifest_data.get("scenes", [])
    if not isinstance(scene_filenames, list) or not scene_filenames:
        print(f"Error: Manifest '{manifest_path}' contains no scenes list.", file=sys.stderr)
        return 1

    compiled_scenes: list[SceneCompiledData] = []
    for fname in scene_filenames:
        scene_file = sdir / fname if not Path(fname).is_absolute() else Path(fname)
        if not scene_file.is_file():
            print(f"Error: Scene file '{scene_file}' referenced in manifest not found.", file=sys.stderr)
            return 1

        try:
            sc_data = parse_scene_json(scene_file, enemies, secrets, profiles)
            compiled_scenes.append(sc_data)
            print(
                f"Compiled scene: {sc_data.name} ({fname}) — "
                f"{len(sc_data.elements)} elems, {len(sc_data.platforms)} plats, {len(sc_data.objects)} objs"
            )
        except Exception as exc:
            print(f"Error compiling scene '{scene_file}': {exc}", file=sys.stderr)
            return 1

    asm_content = generate_scenes_asm(compiled_scenes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(asm_content, encoding="utf-8")
    print(f"Generated ASM scene structures: {output_path} ({len(asm_content)} chars)")

    dli_asm = generate_scenes_dli_asm(compiled_scenes)
    dli_output_path = output_path.parent / "scenes_dli_data.asm"
    dli_output_path.write_text(dli_asm, encoding="utf-8")
    print(f"Generated ASM scene DLI data: {dli_output_path} ({len(dli_asm)} chars)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile scenes into Atari 6502 MADS assembly.")
    parser.add_argument(
        "--manifest",
        "-m",
        type=Path,
        default=Path("scenes/scenes.json"),
        help="Path to scenes manifest JSON",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("gen/scenes_data.asm"),
        help="Path to output ASM file",
    )
    parser.add_argument(
        "--scenes-dir",
        type=Path,
        default=None,
        help="Directory containing scene JSON files (defaults to manifest parent)",
    )
    parser.add_argument(
        "--enemies",
        type=Path,
        default=Path("enemies.json"),
        help="Path to enemies.json catalogue",
    )
    parser.add_argument(
        "--secrets",
        type=Path,
        default=Path("secrets.json"),
        help="Path to secrets.json catalogue",
    )
    parser.add_argument(
        "--profiles",
        "-p",
        type=Path,
        default=Path("platform_profiles.json"),
        help="Path to platform_profiles.json catalogue",
    )

    args = parser.parse_args()
    return compile_scenes(
        manifest_path=args.manifest,
        output_path=args.output,
        scenes_dir=args.scenes_dir,
        enemies_path=args.enemies,
        secrets_path=args.secrets,
        profiles_path=args.profiles,
    )


if __name__ == "__main__":
    sys.exit(main())
