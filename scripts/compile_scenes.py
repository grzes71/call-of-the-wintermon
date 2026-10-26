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

try:
    from scripts.sprite_roles import (
        MAX_CHANNELS_PER_ROW,
        MAX_ZONE_SPRITE_HEIGHT,
        MAX_ENEMIES_PER_ZONE,
        MAX_ENEMIES_TOTAL,
        MAX_SECRETS_TOTAL,
        SECRET_CHANNEL_MISSILES,
        SECRET_CHANNEL_PLAYER,
        SpriteValidationError,
        resolve_object_sprite_id,
        secret_channel_of,
    )
except ImportError:
    try:
        from sprite_roles import (
            MAX_CHANNELS_PER_ROW,
            MAX_ZONE_SPRITE_HEIGHT,
            MAX_ENEMIES_PER_ZONE,
            MAX_ENEMIES_TOTAL,
            MAX_SECRETS_TOTAL,
            SECRET_CHANNEL_MISSILES,
            SECRET_CHANNEL_PLAYER,
            SpriteValidationError,
            resolve_object_sprite_id,
            secret_channel_of,
        )
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.resolve()))
        from sprite_roles import (
            MAX_CHANNELS_PER_ROW,
            MAX_ZONE_SPRITE_HEIGHT,
            MAX_ENEMIES_PER_ZONE,
            MAX_ENEMIES_TOTAL,
            MAX_SECRETS_TOTAL,
            SECRET_CHANNEL_MISSILES,
            SECRET_CHANNEL_PLAYER,
            SpriteValidationError,
            resolve_object_sprite_id,
            secret_channel_of,
        )

try:
    from compile_sprites import parse_sprites_json, SpriteDefinition
except ImportError:
    try:
        from scripts.compile_sprites import parse_sprites_json, SpriteDefinition
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.resolve()))
        from compile_sprites import parse_sprites_json, SpriteDefinition


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
    "left_pause_right": 3,
    "right_pause_left": 4,
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
    """Center text within width characters and convert to Atari screen codes.

    Used for the scene title card (dlist_scene_title LMS operand).
    """
    stripped = text.strip()
    if len(stripped) > width:
        stripped = stripped[:width]
    pad_left = (width - len(stripped)) // 2
    pad_right = width - len(stripped) - pad_left
    padded = (" " * pad_left) + stripped + (" " * pad_right)
    return [char_to_atari_screencode(c) for c in padded]


# Bottom status line (ANTIC Mode 2, 40 columns) layout:
#   columns 0..2    - remaining lives (heart glyphs)
#   column  3       - spacer
#   columns 4..N    - scene name, always starting at STATUS_NAME_COL
#   columns N+1..39 - one glyph per collected "special" secret (filled right to left)
# The icon area width follows the data, so the name limit is computed per project with
# status_name_max(status_special_total(scenes)) instead of being a fixed constant.
STATUS_LINE_WIDTH = 40

# Playfield geometry (engine/render.asm + main.asm GAME_VRAM): 40 bytes per line (160 px at
# 2 bpp), 96 lines. Used to clip elements against the visible screen when compiling scenes.
GAME_VRAM_PITCH = 40
GAME_VRAM_LINES = 96
STATUS_NAME_COL = 4


def status_special_total(scenes: list[Any]) -> int:
    """Number of "special" secrets placed across all scenes (the HUD icon capacity)."""
    return sum(1 for scene in scenes for secret in scene.secrets if secret.special)


def status_name_max(special_total: int) -> int:
    """Columns the scene name may use before the special-secret icon area starts."""
    return STATUS_LINE_WIDTH - STATUS_NAME_COL - special_total


def text_to_screencodes_line_at(
    text: str,
    start_col: int,
    width: int = 40,
    max_len: Optional[int] = None,
) -> list[int]:
    """Convert text to Atari screen codes, left-aligned at `start_col` (rest blank).

    The bottom status line keeps the lives and a spacer to the left of the name, so
    the name is left-aligned at `STATUS_NAME_COL` instead of being centred. `max_len`
    caps the text so a long name can never run into the CD counter on the right.
    """
    stripped = text.strip()
    limit = width - start_col if max_len is None else min(max_len, width - start_col)
    if len(stripped) > limit:
        stripped = stripped[:limit]
    padded = (" " * start_col) + stripped + (" " * (width - start_col - len(stripped)))
    return [char_to_atari_screencode(c) for c in padded]


@dataclass
class CatalogueItem:
    """Enemy or Secret definition from catalogues."""

    id: int
    name: str
    atari_color: int
    blink: bool = False
    dependency: Optional[int] = None
    special: bool = False
    sprite_id: Optional[int] = None
    sprite: Optional[str] = None
    # Secrets only: rendering channel, "player" (P1..P3) or "missiles" (5th player).
    channel: str = SECRET_CHANNEL_MISSILES


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
    # Colour scroll of this row's platform colours: 0 = none, 1 = slow (10 frames/step),
    # 2 = medium (5), 3 = fast (2). Row-wide, like the colour profile itself.
    scroll: int = 0
    # Horizontal movement pattern: "none" (default), "left-right", "right-left",
    # "left-pause-right", "right-pause-left".
    movement: str = "none"
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
    # Sprite channel in its platform row: 0..2 = Players 1..3, 3 = 5th player (missiles).
    # Enemies always use 0..2; secrets use the channel their definition asks for.
    channel: int = 3


@dataclass
class SceneSecretData:
    """Compiled secret instance on a scene."""

    id: int
    def_id: int
    sprite_id: int
    x: int
    y: int
    pmg_y: int
    height: int
    frame_dur: int
    frame_count: int
    atari_color: int
    active: bool
    dep_id: int = 0
    zone_idx: int = 0
    blink: bool = False
    special: bool = False
    # Sprite channel in its platform row: 0..2 = Players 1..3, 3 = 5th player (missiles).
    channel: int = 3
    # Channel kind requested by the definition ("player" or "missiles"); assigned in the
    # channel-budget pass that runs after all objects are parsed.
    channel_kind: str = SECRET_CHANNEL_MISSILES


@dataclass
class SceneEnemyData:
    """Compiled enemy instance on a scene."""

    id: int
    def_id: int
    sprite_id: int
    platform_idx: int
    zone_idx: int
    channel: int  # 0=P1, 1=P2, 2=P3
    min_x: int
    max_x: int
    x: int
    y: int
    pmg_y: int
    height: int
    frame_dur: int
    frame_count: int
    speed: int  # 0=slow, 1=medium, 2=fast
    strategy: int  # 0=stationary, 1=left_right, 2=right_left, 3=left_pause_right, 4=right_pause_left
    direction: int  # 0=right, 1=left
    atari_color: int


PAS_Y_COORDS = [8, 24, 40, 56, 72, 88]

# Vertical PMG geometry: a platform's pas base scanline is 32 + platform_y * 2 and its first
# visible scanline is that base. engine/dli.asm commits the platform's HPOSP/SIZEP/SIZEM on the
# two scanlines *just before* that base (Faza A2/A3), so they become active exactly on it - a
# sprite standing on the platform keeps its own values on the rows above, and one scanline of
# clearance (SPRITE_TAIL_MARGIN = 1) is enough.
SPRITE_TAIL_MARGIN = 1

TILESET_PALETTES: dict[int, tuple[int, int, int]] = {
    0: (0x94, 0xD6, 0xEA),  # castles
    1: (0xA2, 0xA6, 0xBA),  # depths
    2: (0x32, 0x26, 0x1C),  # hell
    3: (0xC4, 0xC8, 0xDC),  # trees
}

# Background palette used when a scene stores no explicit 'background_palette' and no
# tileset can be resolved. Mirrors scene_editor.scene_model.DEFAULT_BACKGROUND_PALETTE_COLORS
# (tests/test_scene_background_palette.py asserts both stay in sync).
DEFAULT_BACKGROUND_PALETTE: tuple[int, int, int] = (0xC4, 0xC8, 0xDC)
BG_PALETTE_ZONES = ("upper", "lower")

# Platform colour-profile scroll: code emitted per platform row (0 = none, 1 = slow, 2 = medium,
# 3 = fast). Mirrors SCROLL_PERIODS_FRAMES in the scene editor's catalogue_model (10/5/2 frames).
SCROLL_CODES: dict[str, int] = {"none": 0, "slow": 1, "medium": 2, "fast": 3}
BG_PALETTE_COLORS_PER_ZONE = 3


def parse_atari_color_value(raw: object, context: str) -> int:
    """Parse an Atari colour register byte from an int or a hex string ('$C4', '0xC4', 'C4')."""
    if isinstance(raw, bool):
        raise ValueError(f"{context}: colour must be an integer or hex string, got bool.")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            raise ValueError(f"{context}: colour cannot be empty.")
        try:
            if cleaned.startswith("$"):
                value = int(cleaned[1:], 16)
            elif cleaned.lower().startswith("0x"):
                value = int(cleaned[2:], 16)
            else:
                value = int(cleaned, 16)
        except ValueError as exc:
            raise ValueError(f"{context}: '{raw}' is not a valid Atari colour value.") from exc
    else:
        raise ValueError(
            f"{context}: colour must be an integer or hex string, got {type(raw).__name__}."
        )

    if not (0 <= value <= 255):
        raise ValueError(f"{context}: colour 0x{value:02X} is outside the 0x00-0xFF range.")
    if value & 1:
        raise ValueError(
            f"{context}: colour 0x{value:02X} has bit 0 set; GTIA ignores the lowest bit "
            f"(use 0x{value & 0xFE:02X})."
        )
    return value


def parse_scene_background_palette(
    data: dict[str, Any], scene_name: str
) -> Optional[dict[str, tuple[int, int, int]]]:
    """Parse the optional per-scene background palette (upper/lower zone COLPF0..2 triples).

    Returns None when the scene stores no explicit palette, in which case the DLI colours are
    derived from the tilesets (legacy behaviour).
    """
    raw = data.get("background_palette")
    if raw is None and isinstance(data.get("scene"), dict):
        raw = data["scene"].get("background_palette")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            f"Scene '{scene_name}': 'background_palette' must be an object with 'upper' and 'lower' zones."
        )

    parsed: dict[str, tuple[int, int, int]] = {}
    for zone in BG_PALETTE_ZONES:
        if zone not in raw:
            raise ValueError(f"Scene '{scene_name}': background_palette is missing the '{zone}' zone.")
        colors = raw[zone]
        if not isinstance(colors, (list, tuple)) or len(colors) != BG_PALETTE_COLORS_PER_ZONE:
            raise ValueError(
                f"Scene '{scene_name}': background_palette['{zone}'] must list exactly "
                f"{BG_PALETTE_COLORS_PER_ZONE} Atari colours (COLPF0..COLPF2), got {colors!r}."
            )
        values = tuple(
            parse_atari_color_value(item, f"Scene '{scene_name}': background_palette['{zone}'][{idx}]")
            for idx, item in enumerate(colors)
        )
        parsed[zone] = values  # type: ignore[assignment]
    return parsed


SUPPORTED_SPRITE_WIDTHS: dict[int, list[tuple[int, int]]] = {
    8: [(8, 0)],
    16: [(16, 1)],
    24: [(16, 1), (8, 0)],
    32: [(32, 3)],
    48: [(32, 3), (16, 1)],
    64: [(32, 3), (32, 3)],
    96: [(32, 3), (32, 3), (32, 3)],
}


WIDTH_TO_PMG_PATTERN: dict[int, int] = {
    32: 0xFF,
    16: 0xF0,
    8: 0xC0,
    24: 0xFC,
}


@dataclass
class ScenePmgPatterns:
    """PMG pattern bytes for platform channels (6 pas x 3 channels = 18 bytes)."""

    patterns: list[int]


@dataclass
class SceneDliCompiledData:
    """Compiled DLI table data for a single scene (219 bytes + 18 bytes PMG patterns)."""

    # 34 tables x 6 bytes = 204 bytes
    hpos_p1: list[int]          # 6 bytes (pasy 0..5)
    hpos_p2: list[int]          # 6 bytes
    hpos_p3: list[int]          # 6 bytes
    hpos_m0: list[int]          # 6 bytes
    hpos_m1: list[int]          # 6 bytes
    hpos_m2: list[int]          # 6 bytes
    hpos_m3: list[int]          # 6 bytes
    sizep1: list[int]           # 6 bytes
    sizep2: list[int]           # 6 bytes
    sizep3: list[int]           # 6 bytes
    sizem: list[int]            # 6 bytes
    bg_colpf0: list[int]        # 6 bytes
    bg_colpf1: list[int]        # 6 bytes
    bg_colpf2: list[int]        # 6 bytes
    pas_color_sl: list[list[int]]  # 8 lists of 6 bytes
    plat_scroll: list[int]         # 6 bytes: scroll code per pas (0 = none, 1 = slow, 2 = medium, 3 = fast)
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
    pmg_patterns: ScenePmgPatterns | None = None


def validate_scene_dli_platforms(
    platforms: list[PlatformData],
    dli_data: SceneDliCompiledData,
    scene_name: str = "",
) -> None:
    """Validate that compiled platform positions, widths, and sizes satisfy hardware constraints."""
    for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
        pas_plats = [p for p in platforms if p.y == pas_y]
        if not pas_plats:
            continue

        # 1. Total width in pas does not exceed 128 px
        total_width = sum(p.width for p in pas_plats)
        if total_width > 128:
            raise ValueError(
                f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                f"total platform width ({total_width} px) exceeds maximum limit of 128 px."
            )

        # 2. Number of active channels in pas does not exceed 4 (P1, P2, P3, 5P)
        p1_active = 1 if dli_data.hpos_p1[pas_idx] > 0 else 0
        p2_active = 1 if dli_data.hpos_p2[pas_idx] > 0 else 0
        p3_active = 1 if dli_data.hpos_p3[pas_idx] > 0 else 0
        m_active = 1 if any(
            h[pas_idx] > 0 for h in (dli_data.hpos_m0, dli_data.hpos_m1, dli_data.hpos_m2, dli_data.hpos_m3)
        ) else 0
        active_channels = p1_active + p2_active + p3_active + m_active
        if active_channels > 4:
            raise ValueError(
                f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                f"active channels count ({active_channels}) exceeds maximum limit of 4."
            )

        # 3. Platform width validation
        for p in pas_plats:
            if p.type_code == 0:
                if p.width not in SUPPORTED_SPRITE_WIDTHS:
                    raise ValueError(
                        f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                        f"platform '{p.id}' has unsupported width {p.width} px (supported: 8, 16, 24, 32, 48, 64, 96)."
                    )
            elif p.type_code == 1:
                if p.width not in (8, 32):
                    raise ValueError(
                        f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                        f"missile platform '{p.id}' has unsupported width {p.width} px (supported: 8, 32)."
                    )

        # 4. Multi-segment platforms: verify consecutive channels without skips
        hpos_p_vals = [dli_data.hpos_p1[pas_idx], dli_data.hpos_p2[pas_idx], dli_data.hpos_p3[pas_idx]]
        sizep_vals = [dli_data.sizep1[pas_idx], dli_data.sizep2[pas_idx], dli_data.sizep3[pas_idx]]
        sprite_plats = sorted([p for p in pas_plats if p.type_code == 0], key=lambda p: p.x)
        missile_plats = sorted([p for p in pas_plats if p.type_code == 1], key=lambda p: p.x)

        for p in sprite_plats:
            if len(SUPPORTED_SPRITE_WIDTHS[p.width]) > 1:
                seg_offset = 0
                exp_hpos_list = []
                for seg_w, exp_sz in SUPPORTED_SPRITE_WIDTHS[p.width]:
                    exp_hpos_list.append((48 + p.x + seg_offset, exp_sz))
                    seg_offset += seg_w

                first_hpos = exp_hpos_list[0][0]
                if first_hpos not in hpos_p_vals:
                    raise ValueError(
                        f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                        f"platform '{p.id}' (x={p.x}, width={p.width}) start segment not found in player channels."
                    )
                start_ch = hpos_p_vals.index(first_hpos)
                for s_idx, (exp_h, exp_sz) in enumerate(exp_hpos_list):
                    target_ch = start_ch + s_idx
                    if target_ch >= len(hpos_p_vals) or hpos_p_vals[target_ch] != exp_h:
                        raise ValueError(
                            f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                            f"platform '{p.id}' (width={p.width}) segments do not occupy consecutive channels without skips: "
                            f"expected HPOS {exp_h} at channel {target_ch}, found {hpos_p_vals[target_ch] if target_ch < len(hpos_p_vals) else 'out of range'}."
                        )

        # 5. SIZEP matches platform widths
        ch_p_check = 0
        for p in sprite_plats:
            for seg_w, exp_sz in SUPPORTED_SPRITE_WIDTHS[p.width]:
                if ch_p_check < 3:
                    if sizep_vals[ch_p_check] != exp_sz:
                        raise ValueError(
                            f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                            f"platform '{p.id}' segment width {seg_w} requires SIZEP={exp_sz}, got {sizep_vals[ch_p_check]}."
                        )
                    ch_p_check += 1

        # 6. SIZEM matches missile platforms
        if missile_plats:
            has_32 = any(p.width == 32 for p in missile_plats)
            if has_32 and dli_data.sizem[pas_idx] != 0xFF:
                raise ValueError(
                    f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                    f"missile platform width 32 px requires SIZEM=$FF, got ${dli_data.sizem[pas_idx]:02X}."
                )
        else:
            if dli_data.sizem[pas_idx] != 0:
                raise ValueError(
                    f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                    f"no missile platforms in pas, expected SIZEM=$00, got ${dli_data.sizem[pas_idx]:02X}."
                )

        # 7. Every platform from JSON has matching start HPOS
        all_hpos = [
            dli_data.hpos_p1[pas_idx],
            dli_data.hpos_p2[pas_idx],
            dli_data.hpos_p3[pas_idx],
            dli_data.hpos_m0[pas_idx],
            dli_data.hpos_m1[pas_idx],
            dli_data.hpos_m2[pas_idx],
            dli_data.hpos_m3[pas_idx],
        ]
        for p in pas_plats:
            expected_hpos = 48 + p.x
            if expected_hpos not in all_hpos:
                raise ValueError(
                    f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                    f"platform '{p.id}' (x={p.x}, expected HPOS={expected_hpos}) has no corresponding HPOS in generated data: {all_hpos}."
                )


def zone_channel_occupants(objs: list[SceneObjectData]) -> list[Optional[SceneObjectData]]:
    """Occupant of each sprite channel (0..2 = Players 1..3, 3 = 5th player) in one platform row.

    Enemies are on screen in every dependency stage, so they own their channel; a secret only
    appears when its stage unlocks, so the compiled DLI tables carry the *initially active*
    secrets (dependency 0) and the runtime patches the channel for every later stage.
    """
    occupants: list[Optional[SceneObjectData]] = [None] * MAX_CHANNELS_PER_ROW
    for obj in objs:
        if obj.type_code == 0 and obj.channel < MAX_CHANNELS_PER_ROW - 1:
            occupants[obj.channel] = obj
    for obj in objs:
        if obj.type_code != 1 or obj.dependency_id != 0:
            continue
        if 0 <= obj.channel < MAX_CHANNELS_PER_ROW and occupants[obj.channel] is None:
            occupants[obj.channel] = obj
    return occupants


def compile_scene_dli_data(
    elements: list[SceneElementData],
    platforms: list[PlatformData],
    objects: list[SceneObjectData],
    primary_tileset_id: int,
    scene_name: str = "",
    background_palette: Optional[dict[str, tuple[int, int, int]]] = None,
) -> SceneDliCompiledData:
    """Compile platform channels, profiles, palettes, and zones for unified DLI."""
    # 1. Determine background palettes
    upper_elements = [e for e in elements if e.dst_y < 44]
    upper_ts = upper_elements[0].tileset_id if upper_elements else primary_tileset_id
    upper_palette = TILESET_PALETTES.get(upper_ts, DEFAULT_BACKGROUND_PALETTE)

    lower_elements = [e for e in elements if e.dst_y >= 44]
    lower_ts = lower_elements[0].tileset_id if lower_elements else upper_ts
    lower_palette = TILESET_PALETTES.get(lower_ts, upper_palette)

    # An explicit scene palette (edited in the Scene Editor) always wins over the
    # tileset-derived colours above.
    if background_palette is not None:
        upper_palette = background_palette["upper"]
        lower_palette = background_palette["lower"]

    # Background palette per pas:
    # Pas 0 (line 8): upper
    # Pas 1 (line 24): upper
    # Pas 2 (line 40): lower (swapped in Faza C at line 44)
    # Pas 3 (line 56): lower
    # Pas 4 (line 72): lower
    # Pas 5 (line 88): lower (the lower scheme owns everything below line 44, including the
    # strip under the lowest platform row - the upper palette is never restored on screen;
    # the status line is drawn separately, with its own black background)
    bg_colpf0 = [upper_palette[0], upper_palette[0], lower_palette[0], lower_palette[0], lower_palette[0], lower_palette[0]]
    bg_colpf1 = [upper_palette[1], upper_palette[1], lower_palette[1], lower_palette[1], lower_palette[1], lower_palette[1]]
    bg_colpf2 = [upper_palette[2], upper_palette[2], lower_palette[2], lower_palette[2], lower_palette[2], lower_palette[2]]

    # 2. Compile platforms for the 6 pas
    hpos_p1 = [0] * 6
    hpos_p2 = [0] * 6
    hpos_p3 = [0] * 6
    hpos_m0 = [0xFF] * 6
    hpos_m1 = [0xFF] * 6
    hpos_m2 = [0xFF] * 6
    hpos_m3 = [0xFF] * 6

    sizep1 = [0] * 6
    sizep2 = [0] * 6
    sizep3 = [0] * 6
    sizem = [0] * 6

    pas_color_sl = [[0] * 6 for _ in range(8)]
    plat_scroll = [0] * 6

    hpos_p_all = [hpos_p1, hpos_p2, hpos_p3]
    hpos_m_all = [hpos_m0, hpos_m1, hpos_m2, hpos_m3]
    sizep_all = [sizep1, sizep2, sizep3]

    pmg_patterns_list = [0xFF] * 18

    for pas_idx, pas_y in enumerate(PAS_Y_COORDS):
        pas_platforms = [p for p in platforms if p.y == pas_y]

        sprite_plats = sorted([p for p in pas_platforms if p.type_code == 0], key=lambda p: p.x)
        missile_plats = sorted([p for p in pas_platforms if p.type_code == 1], key=lambda p: p.x)

        if pas_platforms:
            row_colors = pas_platforms[0].colors
            for sl in range(8):
                pas_color_sl[sl][pas_idx] = row_colors[sl]
            # Scroll is row-wide and "none" (0) means "not set": the first explicitly set value in
            # the row wins and the whole row follows it (mirrors the editor's _ensure_row_scroll).
            plat_scroll[pas_idx] = next((code for code in (p.scroll for p in pas_platforms) if code), 0)

        ch_p = 0
        ch_m = 0

        # Assign sprite platforms
        for p in sprite_plats:
            if p.width not in SUPPORTED_SPRITE_WIDTHS:
                raise ValueError(
                    f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                    f"platform '{p.id}' has unsupported width {p.width} px (supported: 8, 16, 24, 32, 48, 64, 96)."
                )
            seg_offset = 0
            for seg_w, p_sizep in SUPPORTED_SPRITE_WIDTHS[p.width]:
                if ch_p < 3:
                    hpos_p_all[ch_p][pas_idx] = min(255, max(0, 48 + p.x + seg_offset))
                    sizep_all[ch_p][pas_idx] = p_sizep
                    pmg_patterns_list[pas_idx * 3 + ch_p] = WIDTH_TO_PMG_PATTERN.get(seg_w, 0xFF)
                    ch_p += 1
                seg_offset += seg_w

        # Assign missile platforms
        for p in missile_plats:
            if p.width == 32:
                for ms in range(4):
                    if ch_m < 4:
                        hpos_m_all[ch_m][pas_idx] = min(255, max(0, 48 + p.x + ms * 8))
                        ch_m += 1
                sizem[pas_idx] = 0xFF
            elif p.width == 8:
                if ch_m < 4:
                    hpos_m_all[ch_m][pas_idx] = min(255, max(0, 48 + p.x))
                    sizem[pas_idx] |= (3 << (ch_m * 2))
                    ch_m += 1
            else:
                raise ValueError(
                    f"Scene '{scene_name}' pas {pas_idx} (y={pas_y}): "
                    f"missile platform '{p.id}' has unsupported width {p.width} px (supported: 8, 32)."
                )

    # 3. Compile enemies and secrets for the 7 zone table slots.
    # The DLI applies slot `s` on the guard line of pas `s`, i.e. one platform row *before* the
    # row whose sprites stand on it, so an object on the platform row with pas `p` must be
    # stored in slot `p - 1`; the first platform row (y = 8) uses the pre-frame `z0_*` values.
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

    # Zone 0 initial values (applied in VBLANK before Pas 0): objects of the first platform row
    # (y = 8), whose sprites are already visible above that row.
    z0_channels = zone_channel_occupants(zone_objects[0])
    z0_occ_p1, z0_occ_p2, z0_occ_p3, z0_occ_m = z0_channels

    z0_hpos_p1 = min(255, max(0, 48 + z0_occ_p1.x)) if z0_occ_p1 else 0
    z0_col_p1  = z0_occ_p1.atari_color if z0_occ_p1 else 0
    z0_hpos_p2 = min(255, max(0, 48 + z0_occ_p2.x)) if z0_occ_p2 else 0
    z0_col_p2  = z0_occ_p2.atari_color if z0_occ_p2 else 0
    z0_hpos_p3 = min(255, max(0, 48 + z0_occ_p3.x)) if z0_occ_p3 else 0
    z0_col_p3  = z0_occ_p3.atari_color if z0_occ_p3 else 0

    if z0_occ_m is not None:
        z0_hpos_m0 = min(255, max(0, 48 + z0_occ_m.x))
        z0_hpos_m1 = min(255, max(0, 48 + z0_occ_m.x + 2))
        z0_hpos_m2 = min(255, max(0, 48 + z0_occ_m.x + 4))
        z0_hpos_m3 = min(255, max(0, 48 + z0_occ_m.x + 6))
        z0_secret_col = z0_occ_m.atari_color
    else:
        z0_hpos_m0 = 0xFF
        z0_hpos_m1 = 0xFF
        z0_hpos_m2 = 0xFF
        z0_hpos_m3 = 0xFF
        z0_secret_col = 0
    z0_prior = 0x11

    # Zones 1..6 (set up in Faza C of pas 0..5, 6 entries)
    zone_hpos_p1 = [0] * 6
    zone_col_p1  = [0] * 6
    zone_hpos_p2 = [0] * 6
    zone_col_p2  = [0] * 6
    zone_hpos_p3 = [0] * 6
    zone_col_p3  = [0] * 6

    zone_hpos_m0 = [0xFF] * 6
    zone_hpos_m1 = [0xFF] * 6
    zone_hpos_m2 = [0xFF] * 6
    zone_hpos_m3 = [0xFF] * 6
    zone_secret_col = [0] * 6
    zone_prior = [0x11] * 6

    zone_hpos_players = (zone_hpos_p1, zone_hpos_p2, zone_hpos_p3)
    zone_col_players = (zone_col_p1, zone_col_p2, zone_col_p3)

    for z_idx in range(6):
        # Slot z_idx carries the objects of the platform row whose pas is z_idx + 1, so their
        # sprites are set up one zone before the row they stand on.
        occupants = zone_channel_occupants(zone_objects[z_idx + 1])

        for channel in range(MAX_CHANNELS_PER_ROW - 1):
            occupant = occupants[channel]
            if occupant is None:
                continue
            zone_hpos_players[channel][z_idx] = min(255, max(0, 48 + occupant.x))
            zone_col_players[channel][z_idx] = occupant.atari_color

        missile = occupants[MAX_CHANNELS_PER_ROW - 1]
        if missile is not None:
            zone_hpos_m0[z_idx] = min(255, max(0, 48 + missile.x))
            zone_hpos_m1[z_idx] = min(255, max(0, 48 + missile.x + 2))
            zone_hpos_m2[z_idx] = min(255, max(0, 48 + missile.x + 4))
            zone_hpos_m3[z_idx] = min(255, max(0, 48 + missile.x + 6))
            zone_secret_col[z_idx] = missile.atari_color
        zone_prior[z_idx] = 0x11

    compiled_dli = SceneDliCompiledData(
        hpos_p1=hpos_p1,
        hpos_p2=hpos_p2,
        hpos_p3=hpos_p3,
        hpos_m0=hpos_m0,
        hpos_m1=hpos_m1,
        hpos_m2=hpos_m2,
        hpos_m3=hpos_m3,
        sizep1=sizep1,
        sizep2=sizep2,
        sizep3=sizep3,
        sizem=sizem,
        bg_colpf0=bg_colpf0,
        bg_colpf1=bg_colpf1,
        bg_colpf2=bg_colpf2,
        pas_color_sl=pas_color_sl,
        plat_scroll=plat_scroll,
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
        pmg_patterns=ScenePmgPatterns(patterns=pmg_patterns_list),
    )

    validate_scene_dli_platforms(platforms, compiled_dli, scene_name)
    return compiled_dli


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
    secrets: list[SceneSecretData] = field(default_factory=list)
    enemies: list[SceneEnemyData] = field(default_factory=list)
    dli_data: SceneDliCompiledData | None = None
    pmg_patterns: ScenePmgPatterns | None = None
    player_start_x: int = 20
    player_start_y: int = 68
    player_color: int = 0x98


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
    enemies_file: Path, secrets_file: Path, sprites_file: Optional[Path] = None
) -> tuple[dict[int, CatalogueItem], dict[int, CatalogueItem]]:
    """Load enemies and secrets definitions for attribute and color resolution."""
    # Check if enemies_file is or points to unified definitions.json or definitions_resolved.json
    def_file: Optional[Path] = None
    if enemies_file.name in ("definitions.json", "definitions_resolved.json") and enemies_file.is_file():
        def_file = enemies_file
    elif (enemies_file.parent / "definitions_resolved.json").is_file():
        def_file = enemies_file.parent / "definitions_resolved.json"
    elif (enemies_file.parent / "definitions.json").is_file() and not enemies_file.is_file():
        def_file = enemies_file.parent / "definitions.json"
    elif (Path("gen") / "definitions_resolved.json").is_file() and not enemies_file.is_file():
        def_file = Path("gen") / "definitions_resolved.json"
    elif (Path("scenes") / "definitions.json").is_file() and not enemies_file.is_file():
        def_file = Path("scenes") / "definitions.json"

    enemies: dict[int, CatalogueItem] = {}
    secrets: dict[int, CatalogueItem] = {}

    if def_file and def_file.is_file():
        try:
            data = json.loads(def_file.read_text(encoding="utf-8"))
            reg = None
            if sprites_file and sprites_file.is_file():
                try:
                    from scripts.sprite_links import SpriteRegistry
                    reg = SpriteRegistry(sprites_file)
                except Exception:
                    reg = None
            elif Path("sprites/objects.sprite.json").is_file():
                try:
                    from scripts.sprite_links import SpriteRegistry
                    reg = SpriteRegistry(Path("sprites/objects.sprite.json"))
                except Exception:
                    reg = None

            for item in data.get("enemies", []):
                sid = item.get("sprite_id")
                sname = item.get("sprite")
                if sid is None and sname and reg:
                    try:
                        sid, sname = reg.resolve_by_name(sname)
                    except Exception:
                        pass
                enemies[item["id"]] = CatalogueItem(
                    id=item["id"],
                    name=item.get("name", f"Enemy {item['id']}"),
                    atari_color=item.get("atari_color", 0x42),
                    blink=bool(item.get("blink", False)),
                    sprite_id=sid,
                    sprite=sname,
                )
            for item in data.get("secrets", []):
                raw_dep = item.get("dependency")
                dep = int(raw_dep) if (raw_dep is not None and str(raw_dep).strip() != "") else None
                sid = item.get("sprite_id")
                sname = item.get("sprite")
                if sid is None and sname and reg:
                    try:
                        sid, sname = reg.resolve_by_name(sname)
                    except Exception:
                        pass
                secrets[item["id"]] = CatalogueItem(
                    id=item["id"],
                    name=item.get("name", f"Secret {item['id']}"),
                    atari_color=item.get("atari_color", 0x1A),
                    blink=bool(item.get("blink", False)),
                    dependency=dep,
                    special=bool(item.get("special", False)),
                    sprite_id=sid,
                    sprite=sname,
                    channel=secret_channel_of(item),
                )
            return enemies, secrets
        except Exception as exc:
            print(f"Warning: Failed loading definitions catalog ({exc})", file=sys.stderr)

    if not enemies_file.is_file():
        alt_e = enemies_file.parent / "scenes" / enemies_file.name
        if alt_e.is_file():
            enemies_file = alt_e
        elif (Path("scenes") / enemies_file.name).is_file():
            enemies_file = Path("scenes") / enemies_file.name

    if enemies_file.is_file():
        try:
            data = json.loads(enemies_file.read_text(encoding="utf-8"))
            for item in data.get("enemies", []):
                enemies[item["id"]] = CatalogueItem(
                    id=item["id"],
                    name=item.get("name", f"Enemy {item['id']}"),
                    atari_color=item.get("atari_color", 0x42),
                    blink=bool(item.get("blink", False)),
                    sprite_id=item.get("sprite_id"),
                )
        except Exception as exc:
            print(f"Warning: Failed loading enemies catalog ({exc})", file=sys.stderr)

    if not secrets_file.is_file():
        alt_s = secrets_file.parent / "scenes" / secrets_file.name
        if alt_s.is_file():
            secrets_file = alt_s
        elif (Path("scenes") / secrets_file.name).is_file():
            secrets_file = Path("scenes") / secrets_file.name

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
                    special=bool(item.get("special", False)),
                    sprite_id=item.get("sprite_id"),
                    channel=secret_channel_of(item),
                )
        except Exception as exc:
            print(f"Warning: Failed loading secrets catalog ({exc})", file=sys.stderr)

    return enemies, secrets


DEFAULT_PLATFORM_COLORS: list[int] = [0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80]


def load_platform_profiles(profiles_file: Path) -> dict[int, list[int]]:
    """Load platform color profiles (8 scanline GTIA color bytes each)."""
    target_file = profiles_file
    if not target_file.is_file():
        if (profiles_file.parent / "definitions.json").is_file():
            target_file = profiles_file.parent / "definitions.json"
        elif (Path("scenes") / "definitions.json").is_file():
            target_file = Path("scenes") / "definitions.json"
        else:
            alt_p = target_file.parent / "scenes" / target_file.name
            if alt_p.is_file():
                target_file = alt_p
            elif (Path("scenes") / target_file.name).is_file():
                target_file = Path("scenes") / target_file.name

    profiles: dict[int, list[int]] = {}
    if target_file.is_file():
        try:
            data = json.loads(target_file.read_text(encoding="utf-8"))
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
    profiles: dict[int, list[int]] | None = None,
    sprites: dict[int, SpriteDefinition] | None = None,
    primary_tileset_id: int | None = None,
    require_secret: bool = False,
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

        # Clip the element against the playfield. engine/render.asm only reduces width/height
        # when an element runs past the right/bottom edge and skips anything whose byte column is
        # >= 40 or whose destination line is >= 96; an element partially above or left of the screen
        # (negative position, e.g. a tileset bleeding off the top) must therefore be clipped here:
        # advance the source pointer and shrink the extent so the visible part lands exactly where
        # the editor shows it.
        if dst_y < 0:
            clipped_lines = min(h_lines, -dst_y)
            src_y += clipped_lines
            h_lines -= clipped_lines
            dst_y = 0

        if dst_x < 0:
            # Source reads are byte aligned, so only whole 4-pixel columns can be dropped.
            # A flipped element is drawn from the high end of the source range, so clipping its
            # left edge means shrinking the range instead of advancing the source pointer.
            clipped_bytes = min(w_bytes, (-dst_x) // 4)
            w_bytes -= clipped_bytes
            if not flip_x:
                src_x_byte += clipped_bytes
            dst_x_byte = 0

        # Clip the right edge here as well. engine/render.asm shrinks the width to
        # `40 - dst_x_byte` but always reads the source range from its start, so for a flipped
        # element (drawn right-to-left from the high end) the visible leftmost bytes are the
        # *high* end of the source: advance the source pointer so the emitted range begins at
        # the byte that must appear leftmost. Non-flipped elements need no shift (the engine
        # simply stops earlier).
        if dst_x_byte + w_bytes > GAME_VRAM_PITCH:
            clipped_bytes = (dst_x_byte + w_bytes) - GAME_VRAM_PITCH
            w_bytes -= clipped_bytes
            if flip_x:
                src_x_byte += clipped_bytes

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

    # 2. Row color profiles mapping
    raw_row_profiles = data.get("row_color_profiles")
    if raw_row_profiles is None and isinstance(data.get("scene"), dict):
        raw_row_profiles = data["scene"].get("row_color_profiles")

    row_cprof_map: dict[int, Optional[int]] = {}
    if isinstance(raw_row_profiles, list):
        for r_idx, val in enumerate(raw_row_profiles):
            if val is not None and str(val).strip() != "":
                try:
                    row_cprof_map[r_idx] = int(val)
                except (ValueError, TypeError):
                    row_cprof_map[r_idx] = None
            else:
                row_cprof_map[r_idx] = None
    elif isinstance(raw_row_profiles, dict):
        for k, val in raw_row_profiles.items():
            try:
                row_cprof_map[int(k)] = int(val) if val is not None else None
            except (ValueError, TypeError):
                pass

    # Validate that all platforms in the same row share the exact same color_profile_id
    # and match the scene-level row_color_profiles if defined
    row_platform_profiles: dict[int, tuple[str, Optional[int]]] = {}
    for idx, p in enumerate(raw_platforms):
        pid = str(p.get("id", f"platform-{idx}"))
        ppos = p.get("position", {})
        py = int(ppos.get("y", 0))
        ridx = (py - 8) // 16

        raw_cprof_id = p.get("color_profile_id")
        p_cprof_id: Optional[int] = None
        if raw_cprof_id is not None and str(raw_cprof_id).strip() != "":
            try:
                p_cprof_id = int(raw_cprof_id)
            except (ValueError, TypeError):
                p_cprof_id = None

        expected_row_cprof = row_cprof_map.get(ridx)
        if expected_row_cprof is not None and p_cprof_id is not None and p_cprof_id != expected_row_cprof:
            raise ValueError(
                f"Błąd w scenie '{name}' ({scene_file.name}): platforma '{pid}' w wierszu y={py} (wiersz {ridx}) "
                f"ma przypisany profil kolorów {p_cprof_id}, podczas gdy profil zdefiniowany dla tego wiersza "
                f"to {expected_row_cprof}. Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów."
            )

        if py in row_platform_profiles:
            first_pid, first_cprof = row_platform_profiles[py]
            if p_cprof_id != first_cprof:
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): niezgodność profilu kolorów w wierszu y={py}. "
                    f"Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów. "
                    f"Platforma '{first_pid}' ma profil {first_cprof}, a platforma '{pid}' ma profil {p_cprof_id}."
                )
        else:
            row_platform_profiles[py] = (pid, p_cprof_id)
            if ridx not in row_cprof_map and p_cprof_id is not None:
                row_cprof_map[ridx] = p_cprof_id

    for idx, p in enumerate(raw_platforms):
        pid = str(p.get("id", f"platform-{idx}"))
        ptype_str = str(p.get("type", "sprite")).lower()
        ptype = 1 if ptype_str == "missile" else 0
        ppos = p.get("position", {})
        px = int(ppos.get("x", 0))
        py = int(ppos.get("y", 0))
        pw = int(p.get("width", 16))
        ph = int(p.get("height", 4))

        ridx = (py - 8) // 16
        cprof_id = row_cprof_map.get(ridx)
        if cprof_id is None:
            raw_cprof_id = p.get("color_profile_id")
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
                scroll=SCROLL_CODES.get(str(p.get("scroll", "none")).strip().lower(), 0),
                movement=str(p.get("movement", "none")).strip().lower(),
                colors=colors,
            )
        )

    # 3. Objects
    raw_objects = data.get("objects", [])
    objects: list[SceneObjectData] = []
    scene_secrets: list[SceneSecretData] = []
    scene_enemies: list[SceneEnemyData] = []
    zone_enemy_counts: dict[int, int] = {}

    for obj in raw_objects:
        oid = int(obj.get("id", 0))
        otype_str = str(obj.get("type", "enemy")).lower()
        is_secret = otype_str in ("secret", "treasure")
        type_code = 1 if is_secret else 0
        # Sprite channel in this row: enemies take Players 1..3 in order (set below), secrets get
        # theirs from the channel-budget pass that runs after all objects are parsed.
        obj_channel = MAX_CHANNELS_PER_ROW - 1
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
            special = bool(getattr(cat_item, "special", False)) if cat_item else False
            dep_val = obj.get("dependency")
            if dep_val is None and "dependency_id" in obj:
                dep_val = obj.get("dependency_id")
            if dep_val is None and cat_item and getattr(cat_item, "dependency", None) is not None:
                dep_val = cat_item.dependency
            dep_id = int(dep_val) if dep_val is not None else 0

            # Rendering channel comes from the definition ("player" or "missiles"). The channel
            # budget (MAX_CHANNELS_PER_ROW sprite channels per platform row and dependency stage)
            # is enforced in the assignment pass below, because it also depends on the enemies
            # that stand in the same row.
            channel_kind = secret_channel_of(cat_item)

            spr_id = resolve_object_sprite_id(obj, secrets, name, scene_file.name, sprites_dict=sprites)
            if sprites and spr_id not in sprites:
                avail_str = ", ".join(f"{s.id}: {getattr(s, 'description', f'Sprite_{s.id}')}" for s in sorted(sprites.values(), key=lambda x: x.id))
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): sekret '{oid}' (typ {def_id}): "
                    f"podany sprite_id={spr_id} nie istnieje w pliku sprite'ów. Dostępne sprite'y: [{avail_str}]."
                )
            spr_def = sprites.get(spr_id) if sprites else None

            spr_h = spr_def.height if spr_def else 16
            spr_dur = spr_def.frame_duration if spr_def else 4
            spr_cnt = len(spr_def.frames) if spr_def else 1

            if spr_h > MAX_ZONE_SPRITE_HEIGHT:
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): sekret '{oid}' ma wysokość sprite'a {spr_h} px, "
                    f"co przekracza dopuszczalną wysokość strefy {MAX_ZONE_SPRITE_HEIGHT} px (exceeds maximum safe height)."
                )

            # Verify role against sprite manifest / definition format: the packing format must
            # match the channel the definition asks for (player bitmap vs 5th-player missiles).
            if spr_def is not None:
                spr_fmt = getattr(spr_def, "format", "missiles")
                if spr_fmt != channel_kind:
                    raise ValueError(
                        f"Błąd w scenie '{name}' ({scene_file.name}): sekret '{oid}' wskazuje sprite ID {spr_id} "
                        f"skompilowany w formacie '{spr_fmt}', a zdefiniowany kanał '{channel_kind}' wymaga "
                        f"formatu '{channel_kind}'."
                    )

            # Platform base scanline in PMG: 32 + (plat_y * 2) (its first visible scanline;
            # the DLI commits the platform's HPOSP/SIZEP on the two scanlines just before it).
            # Secrets end SPRITE_TAIL_MARGIN scanlines above the base.
            p_base = 32 + (plat_y * 2)
            pmg_y = max(0, p_base - spr_h - SPRITE_TAIL_MARGIN)

            active = (dep_id == 0)
            zid = (plat_y - 8) // 16 if plat_y >= 8 else 0

            scene_secrets.append(
                SceneSecretData(
                    id=oid,
                    def_id=def_id,
                    sprite_id=spr_id,
                    x=ox,
                    y=oy,
                    pmg_y=pmg_y,
                    height=spr_h,
                    frame_dur=spr_dur,
                    frame_count=spr_cnt,
                    atari_color=color,
                    active=active,
                    dep_id=dep_id,
                    zone_idx=zid,
                    blink=blink,
                    special=special,
                    channel_kind=channel_kind,
                )
            )
        else:
            cat_item = enemies.get(def_id)
            color = cat_item.atari_color if cat_item else 0x42
            blink = cat_item.blink if cat_item else False
            dep_id = 0

            spr_id = resolve_object_sprite_id(obj, enemies, name, scene_file.name, sprites_dict=sprites)
            if sprites and spr_id not in sprites:
                avail_str = ", ".join(f"{s.id}: {getattr(s, 'description', f'Sprite_{s.id}')}" for s in sorted(sprites.values(), key=lambda x: x.id))
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): wróg '{oid}' (typ {def_id}): "
                    f"podany sprite_id={spr_id} nie istnieje w pliku sprite'ów. Dostępne sprite'y: [{avail_str}]."
                )

            spr_def = sprites.get(spr_id) if sprites else None

            spr_h = spr_def.height if spr_def else 20
            spr_dur = spr_def.frame_duration if spr_def else 4
            spr_cnt = len(spr_def.frames) if spr_def else 1

            if spr_h > MAX_ZONE_SPRITE_HEIGHT:
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): wróg '{oid}' ma wysokość sprite'a {spr_h} px, "
                    f"co przekracza dopuszczalną wysokość strefy {MAX_ZONE_SPRITE_HEIGHT} px (exceeds maximum safe height)."
                )

            # Verify role against sprite manifest / definition format
            if spr_def is not None:
                spr_fmt = getattr(spr_def, "format", "player")
                if spr_fmt != "player":
                    raise ValueError(
                        f"Błąd w scenie '{name}' ({scene_file.name}): wróg '{oid}' wskazuje sprite ID {spr_id} "
                        f"skompilowany w formacie '{spr_fmt}' (pociski), a wrogowie wymagają formatu 'player'."
                    )

            plat = platforms[plat_idx] if plat_idx < len(platforms) else None
            plat_x = plat.x if plat else 0
            plat_w = plat.width if plat else 32
            min_x = plat_x
            max_x = max(min_x, plat_x + plat_w - 8)
            clamped_x = min(max_x, max(min_x, ox))

            # Platform base scanline in PMG: 32 + (plat_y * 2) (its first visible scanline;
            # the DLI sets the platform sprites up on p_base - 3 .. p_base - 1).
            # Enemies end SPRITE_TAIL_MARGIN scanlines above the base.
            p_base = 32 + (plat_y * 2)
            pmg_y = max(0, p_base - spr_h - SPRITE_TAIL_MARGIN)

            initial_dir = 1 if strat_code in (1, 3) else 0

            zid = (plat_y - 8) // 16 if plat_y >= 8 else 0
            ch = zone_enemy_counts.get(zid, 0)
            if ch >= MAX_ENEMIES_PER_ZONE:
                raise ValueError(
                    f"Błąd w scenie '{name}' ({scene_file.name}): przekroczono limit maksymalnie {MAX_ENEMIES_PER_ZONE} wrogów "
                    f"w strefie {zid} (próba dodania wroga '{oid}')."
                )
            zone_enemy_counts[zid] = ch + 1
            obj_channel = ch

            scene_enemies.append(
                SceneEnemyData(
                    id=oid,
                    def_id=def_id,
                    sprite_id=spr_id,
                    platform_idx=plat_idx,
                    zone_idx=zid,
                    channel=ch,
                    min_x=min_x,
                    max_x=max_x,
                    x=clamped_x,
                    y=oy,
                    pmg_y=pmg_y,
                    height=spr_h,
                    frame_dur=spr_dur,
                    frame_count=spr_cnt,
                    speed=speed_code,
                    strategy=strat_code,
                    direction=initial_dir,
                    atari_color=color,
                )
            )

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
                channel=obj_channel,
            )
        )
    if len(scene_enemies) > MAX_ENEMIES_TOTAL:
        raise ValueError(
            f"Błąd w scenie '{name}' ({scene_file.name}): liczba wrogów ({len(scene_enemies)}) "
            f"przekracza dopuszczalny limit MAX_ENEMIES={MAX_ENEMIES_TOTAL}."
        )

    if len(scene_secrets) > MAX_SECRETS_TOTAL:
        raise ValueError(
            f"Błąd w scenie '{name}' ({scene_file.name}): liczba sekretów ({len(scene_secrets)}) "
            f"przekracza pojemność tablic silnika MAX_SECRETS={MAX_SECRETS_TOTAL} "
            f"(engine/secrets.asm). Ograniczenie projektowe dotyczy tylko jednego sekretu na "
            f"unikalną zależność w wierszu platformy - rozłóż sekrety na kolejne wiersze albo "
            f"podnieś MAX_SECRETS (engine/secrets.asm) razem z MAX_SECRETS_TOTAL "
            f"(scripts/sprite_roles.py)."
        )

    if require_secret and len(scene_secrets) < 1:
        raise ValueError(
            f"Błąd w scenie '{name}' ({scene_file.name}): na każdej scenie włączanej do gry "
            f"powinien być ustawiony co najmniej jeden sekret (znaleziono {len(scene_secrets)})."
        )

    # 3b. Sprite channel budget. Every platform row (= one DLI zone slot) provides
    # MAX_CHANNELS_PER_ROW channels: Players 1..3 plus the 5th player (the four missiles combined).
    # Enemies are on screen in every stage, so they claim their channels first; secrets of one
    # dependency stage fill the remaining ones. Different stages may reuse a channel because they
    # are never visible at the same time (the runtime patches the channel when a stage unlocks).
    enemy_channels_by_zone: dict[int, set[int]] = {}
    for enemy in scene_enemies:
        enemy_channels_by_zone.setdefault(enemy.zone_idx, set()).add(enemy.channel)

    channels_used_by_stage: dict[tuple[int, int], set[int]] = {}
    for secret in scene_secrets:
        row_y = 8 + secret.zone_idx * 16
        used = set(enemy_channels_by_zone.get(secret.zone_idx, set()))
        used |= channels_used_by_stage.get((secret.zone_idx, secret.dep_id), set())
        if secret.channel_kind == SECRET_CHANNEL_PLAYER:
            candidates = range(MAX_CHANNELS_PER_ROW - 1)   # Players 1..3
        else:
            candidates = (MAX_CHANNELS_PER_ROW - 1,)       # 5th player (missiles)
        channel = next((c for c in candidates if c not in used), None)
        if channel is None:
            raise ValueError(
                f"Błąd w scenie '{name}' ({scene_file.name}): wiersz platformy y={row_y} przekracza budżet "
                f"kanałów sprite'ów dla etapu (dependency) {secret.dep_id}: zajęte kanały {sorted(used)}/"
                f"{MAX_CHANNELS_PER_ROW} (wrogowie + sekrety tego etapu), a sekret '{secret.id}' wymaga kanału "
                f"'{secret.channel_kind}'. Użyj innego wiersza, zmień 'channel' definicji sekretu albo usuń wroga."
            )
        secret.channel = channel
        channels_used_by_stage.setdefault((secret.zone_idx, secret.dep_id), set()).add(channel)

    # The DLI compiler reads the generic object list, so mirror the assignment there.
    secret_channel_by_id = {s.id: s.channel for s in scene_secrets}
    for obj in objects:
        if obj.type_code == 1 and obj.id in secret_channel_by_id:
            obj.channel = secret_channel_by_id[obj.id]

    # Player start position and color (defaults to X=20, Y=68, Color=$98 if not defined)
    player_spawn_raw = data.get("player_spawn") or scene_meta.get("player_spawn")
    if isinstance(player_spawn_raw, dict):
        player_start_x = int(player_spawn_raw.get("x", 20))
        player_start_y = int(player_spawn_raw.get("y", 68))
        raw_color = player_spawn_raw.get("color", player_spawn_raw.get("atari_color", 0x98))
        if isinstance(raw_color, str):
            cleaned = raw_color.strip()
            if cleaned.startswith("$"):
                player_color = int(cleaned[1:], 16)
            elif cleaned.startswith("0x") or cleaned.startswith("0X"):
                player_color = int(cleaned[2:], 16)
            else:
                player_color = int(cleaned, 16)
        else:
            player_color = int(raw_color)
        player_color = player_color & 0xFE
    else:
        player_start_x = 20
        player_start_y = 68
        player_color = 0x98

    dli_data = compile_scene_dli_data(
        elements,
        platforms,
        objects,
        primary_tileset_id,
        scene_name=name,
        background_palette=parse_scene_background_palette(data, name),
    )

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
        secrets=scene_secrets,
        enemies=scene_enemies,
        dli_data=dli_data,
        pmg_patterns=dli_data.pmg_patterns if dli_data else None,
        player_start_x=player_start_x,
        player_start_y=player_start_y,
        player_color=player_color,
    )



def generate_scenes_asm(scenes: list[SceneCompiledData]) -> str:
    """Generate MADS 6502 assembly defining Structure-of-Arrays (SoA) scene structures."""
    special_total = status_special_total(scenes)
    name_max = status_name_max(special_total)
    if name_max < 1:
        raise ValueError(
            f"Status line: {special_total} special secrets need that many HUD columns, which "
            f"leaves no room for the scene name (columns {STATUS_NAME_COL}..{STATUS_LINE_WIDTH - 1}). "
            f"Remove a special secret or shorten the icon row."
        )

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
        "OBJ_STRAT_STATIONARY        = 0",
        "OBJ_STRAT_LEFT_RIGHT        = 1",
        "OBJ_STRAT_RIGHT_LEFT        = 2",
        "OBJ_STRAT_LEFT_PAUSE_RIGHT  = 3",
        "OBJ_STRAT_RIGHT_PAUSE_LEFT  = 4",
        "OBJ_STRAT_PATROL            = 3",
        "OBJ_STRAT_AMBUSH            = 4",
        "",
        "; Platform Type Equates",
        "PLATFORM_TYPE_SPRITE    = 0",
        "PLATFORM_TYPE_MISSILE   = 1",
        "",
        "; Status Line Layout (bottom HUD): one glyph per collected special secret is",
        "; drawn at the right end, so the scene name stops STATUS_NAME_MAX columns in.",
        f"SCENE_SPECIAL_TOTAL = {special_total}",
        f"STATUS_NAME_MAX = {name_max}",
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
        lines.append(f"{prefix}_SECRET_COUNT = {len(sc.secrets)}")
        lines.append(f"{prefix}_ENEMY_COUNT  = {len(sc.enemies)}")
        lines.append(f"{prefix}_PLAYER_START_X = {sc.player_start_x}")
        lines.append(f"{prefix}_PLAYER_START_Y = {sc.player_start_y}")
        lines.append(f"{prefix}_PLAYER_COLOR   = ${sc.player_color:02X}")
    lines.append("")


    # Per-scene data blocks
    for idx, sc in enumerate(scenes):
        sym = sc.symbol_name
        screencodes = text_to_screencodes_line(sc.name, width=40)
        sc_bytes = ", ".join(f"${b:02X}" for b in screencodes)
        # Status line (bottom HUD): same name, but left-aligned at STATUS_NAME_COL and
        # truncated before the special-secret icon area on the right.
        hud_screencodes = text_to_screencodes_line_at(
            sc.name, start_col=STATUS_NAME_COL, width=STATUS_LINE_WIDTH, max_len=name_max
        )
        hud_bytes = ", ".join(f"${b:02X}" for b in hud_screencodes)
        lines.extend([
            "; " + "=" * 78,
            f"; SCENE {idx}: {sc.name} ({sc.file_stem}.json)",
            "; " + "=" * 78,
            f"scene_{sym}_name_line",
            f"    .byte {sc_bytes}",
            f"scene_{sym}_hud_line",
            f"    .byte {hud_bytes}",
            "",
        ])

        # Scene elements
        lines.append(f"; --- Elements ({len(sc.elements)}) ---")
        if sc.elements:
            lines.append(f"scene_{sym}_elem_tileset")
            lines.append("    .byte " + ", ".join(TILESET_ID_TO_EQUATE[e.tileset_id] for e in sc.elements))
            lines.append(f"scene_{sym}_elem_src_x_byte")
            lines.append("    .byte " + ", ".join(str(e.src_x_byte) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_src_y")
            lines.append("    .byte " + ", ".join(str(e.src_y) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_w_byte")
            lines.append("    .byte " + ", ".join(str(e.w_bytes) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_h_lines")
            lines.append("    .byte " + ", ".join(str(e.h_lines) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_dst_x_byte")
            lines.append("    .byte " + ", ".join(str(e.dst_x_byte) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_dst_y")
            lines.append("    .byte " + ", ".join(str(e.dst_y) for e in sc.elements))
            lines.append(f"scene_{sym}_elem_flags")
            lines.append("    .byte " + ", ".join(str(1 if e.flip_x else 0) for e in sc.elements))
        else:
            lines.extend([
                f"scene_{sym}_elem_tileset    .byte 0",
                f"scene_{sym}_elem_src_x_byte .byte 0",
                f"scene_{sym}_elem_src_y      .byte 0",
                f"scene_{sym}_elem_w_byte     .byte 0",
                f"scene_{sym}_elem_h_lines    .byte 0",
                f"scene_{sym}_elem_dst_x_byte .byte 0",
                f"scene_{sym}_elem_dst_y      .byte 0",
                f"scene_{sym}_elem_flags      .byte 0",
            ])
        lines.append("")

        # Scene platforms (geometry only: platform type, height and the per-row colour profiles are
        # compiled into gen/scenes_dli_data.asm, which the DLI reads at runtime)
        lines.append(f"; --- Platforms ({len(sc.platforms)}) ---")
        if sc.platforms:
            lines.append(f"scene_{sym}_plat_x")
            lines.append("    .byte " + ", ".join(str(p.x) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_y")
            lines.append("    .byte " + ", ".join(str(p.y) for p in sc.platforms))
            lines.append(f"scene_{sym}_plat_w")
            lines.append("    .byte " + ", ".join(str(p.width) for p in sc.platforms))
        else:
            lines.extend([
                f"scene_{sym}_plat_x         .byte 0",
                f"scene_{sym}_plat_y         .byte 0",
                f"scene_{sym}_plat_w         .byte 0",
            ])
        lines.append("")

        # Scene objects: the enemy_*/secret_* tables carry everything the engine reads, so no
        # object mirror tables are emitted (no engine module ever referenced them).

        # Scene secrets
        lines.append(f"; --- Secrets ({len(sc.secrets)}) ---")
        if sc.secrets:
            lines.append(f"scene_{sym}_secret_active")
            lines.append("    .byte " + ", ".join(str(1 if s.active else 0) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_dep_id")
            lines.append("    .byte " + ", ".join(str(s.dep_id) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_def_id")
            lines.append("    .byte " + ", ".join(str(s.def_id) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_sprite_id")
            lines.append("    .byte " + ", ".join(str(s.sprite_id) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_x")
            lines.append("    .byte " + ", ".join(str(s.x) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_pmg_y")
            lines.append("    .byte " + ", ".join(str(s.pmg_y) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_height")
            lines.append("    .byte " + ", ".join(str(s.height) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_frame_dur")
            lines.append("    .byte " + ", ".join(str(s.frame_dur) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_frame_count")
            lines.append("    .byte " + ", ".join(str(s.frame_count) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_color")
            lines.append("    .byte " + ", ".join(f"${s.atari_color:02X}" for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_zone")
            lines.append("    .byte " + ", ".join(str(s.zone_idx) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_blink")
            lines.append("    .byte " + ", ".join(str(1 if s.blink else 0) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_special")
            lines.append("    .byte " + ", ".join(str(1 if s.special else 0) for s in sc.secrets))
            lines.append(f"scene_{sym}_secret_channel")
            lines.append("    .byte " + ", ".join(str(s.channel) for s in sc.secrets))
            lines.append(f"scene_{sym}_plat_scroll")
            lines.append(
                "    .byte " + ", ".join(str(c) for c in (sc.dli_data.plat_scroll if sc.dli_data else [0] * 6))
            )
        else:
            lines.extend([
                f"scene_{sym}_secret_active      .byte 0",
                f"scene_{sym}_secret_dep_id     .byte 0",
                f"scene_{sym}_secret_def_id     .byte 0",
                f"scene_{sym}_secret_sprite_id  .byte 0",
                f"scene_{sym}_secret_x          .byte 0",
                f"scene_{sym}_secret_pmg_y      .byte 0",
                f"scene_{sym}_secret_height     .byte 0",
                f"scene_{sym}_secret_frame_dur  .byte 0",
                f"scene_{sym}_secret_frame_count .byte 0",
                f"scene_{sym}_secret_color      .byte 0",
                f"scene_{sym}_secret_zone       .byte 0",
                f"scene_{sym}_secret_blink      .byte 0",
                f"scene_{sym}_secret_special    .byte 0",
                f"scene_{sym}_secret_channel    .byte 0",
                f"scene_{sym}_plat_scroll       .byte 0",
            ])
        lines.append(f"; --- Enemies ({len(sc.enemies)}) ---")
        if sc.enemies:
            lines.append(f"scene_{sym}_enemy_def_id")
            lines.append("    .byte " + ", ".join(str(e.def_id) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_sprite_id")
            lines.append("    .byte " + ", ".join(str(e.sprite_id) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_min_x")
            lines.append("    .byte " + ", ".join(str(e.min_x) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_max_x")
            lines.append("    .byte " + ", ".join(str(e.max_x) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_x")
            lines.append("    .byte " + ", ".join(str(e.x) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_pmg_y")
            lines.append("    .byte " + ", ".join(str(e.pmg_y) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_height")
            lines.append("    .byte " + ", ".join(str(e.height) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_frame_dur")
            lines.append("    .byte " + ", ".join(str(e.frame_dur) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_frame_count")
            lines.append("    .byte " + ", ".join(str(e.frame_count) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_speed")
            lines.append("    .byte " + ", ".join(str(e.speed) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_strategy")
            lines.append("    .byte " + ", ".join(str(e.strategy) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_dir")
            lines.append("    .byte " + ", ".join(str(e.direction) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_color")
            lines.append("    .byte " + ", ".join(f"${e.atari_color:02X}" for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_channel")
            lines.append("    .byte " + ", ".join(str(e.channel) for e in sc.enemies))
            lines.append(f"scene_{sym}_enemy_zone")
            lines.append("    .byte " + ", ".join(str(e.zone_idx) for e in sc.enemies))
        else:
            lines.extend([
                f"scene_{sym}_enemy_def_id       .byte 0",
                f"scene_{sym}_enemy_sprite_id    .byte 0",
                f"scene_{sym}_enemy_min_x        .byte 0",
                f"scene_{sym}_enemy_max_x        .byte 0",
                f"scene_{sym}_enemy_x            .byte 0",
                f"scene_{sym}_enemy_pmg_y        .byte 0",
                f"scene_{sym}_enemy_height       .byte 0",
                f"scene_{sym}_enemy_frame_dur    .byte 0",
                f"scene_{sym}_enemy_frame_count  .byte 0",
                f"scene_{sym}_enemy_speed        .byte 0",
                f"scene_{sym}_enemy_strategy     .byte 0",
                f"scene_{sym}_enemy_dir          .byte 0",
                f"scene_{sym}_enemy_color        .byte 0",
                f"scene_{sym}_enemy_channel      .byte 0",
                f"scene_{sym}_enemy_zone         .byte 0",
            ])
        lines.append("")

    # Master Table (Structure-of-Arrays across all scenes)
    lines.extend([
        "; " + "=" * 78,
        "; MASTER SCENE INDEX TABLES (Structure-of-Arrays)",
        "; " + "=" * 78,
        "scene_name_line_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_name_line" for sc in scenes),
        "scene_name_line_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_name_line" for sc in scenes),
        "scene_hud_line_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_hud_line" for sc in scenes),
        "scene_hud_line_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_hud_line" for sc in scenes),
        "",
        "scene_width_px",
        "    .byte " + ", ".join(str(sc.width) for sc in scenes),
        "scene_height_lines",
        "    .byte " + ", ".join(str(sc.height) for sc in scenes),
        "scene_primary_tileset",
        "    .byte " + ", ".join(TILESET_ID_TO_EQUATE[sc.primary_tileset_id] for sc in scenes),
        "scene_player_start_x",
        "    .byte " + ", ".join(str(sc.player_start_x) for sc in scenes),
        "scene_player_start_y",
        "    .byte " + ", ".join(str(sc.player_start_y) for sc in scenes),
        "scene_player_color",
        "    .byte " + ", ".join(f"${sc.player_color:02X}" for sc in scenes),
        "",

        "scene_elem_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_ELEM_COUNT" for sc in scenes),
        "scene_plat_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_PLAT_COUNT" for sc in scenes),
        "scene_obj_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_OBJ_COUNT" for sc in scenes),
        "scene_secret_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_SECRET_COUNT" for sc in scenes),
        "scene_enemy_count",
        "    .byte " + ", ".join(f"SCENE_{sc.symbol_name.upper()}_ENEMY_COUNT" for sc in scenes),
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
        "; --- Platform Pointer Tables (geometry only: type/height/row colours live in the DLI block) ---",
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
        "",
        "; --- Secret Pointer Tables ---",
        "scene_secret_active_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_active" for sc in scenes),
        "scene_secret_active_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_active" for sc in scenes),
        "scene_secret_dep_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_dep_id" for sc in scenes),
        "scene_secret_dep_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_dep_id" for sc in scenes),
        "scene_secret_def_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_def_id" for sc in scenes),
        "scene_secret_def_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_def_id" for sc in scenes),
        "scene_secret_sprite_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_sprite_id" for sc in scenes),
        "scene_secret_sprite_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_sprite_id" for sc in scenes),
        "scene_secret_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_x" for sc in scenes),
        "scene_secret_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_x" for sc in scenes),
        "scene_secret_pmg_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_pmg_y" for sc in scenes),
        "scene_secret_pmg_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_pmg_y" for sc in scenes),
        "scene_secret_height_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_height" for sc in scenes),
        "scene_secret_height_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_height" for sc in scenes),
        "scene_secret_frame_dur_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_frame_dur" for sc in scenes),
        "scene_secret_frame_dur_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_frame_dur" for sc in scenes),
        "scene_secret_frame_count_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_frame_count" for sc in scenes),
        "scene_secret_frame_count_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_frame_count" for sc in scenes),
        "scene_secret_color_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_color" for sc in scenes),
        "scene_secret_color_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_color" for sc in scenes),
        "scene_secret_zone_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_zone" for sc in scenes),
        "scene_secret_zone_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_zone" for sc in scenes),
        "scene_secret_blink_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_blink" for sc in scenes),
        "scene_secret_blink_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_blink" for sc in scenes),
        "scene_secret_special_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_special" for sc in scenes),
        "scene_secret_special_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_special" for sc in scenes),
        "scene_secret_channel_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_secret_channel" for sc in scenes),
        "scene_secret_channel_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_secret_channel" for sc in scenes),
        "scene_plat_scroll_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_plat_scroll" for sc in scenes),
        "scene_plat_scroll_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_plat_scroll" for sc in scenes),
        "",
        "; --- Enemy Pointer Tables ---",
        "scene_enemy_def_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_def_id" for sc in scenes),
        "scene_enemy_def_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_def_id" for sc in scenes),
        "scene_enemy_sprite_id_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_sprite_id" for sc in scenes),
        "scene_enemy_sprite_id_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_sprite_id" for sc in scenes),
        "scene_enemy_min_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_min_x" for sc in scenes),
        "scene_enemy_min_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_min_x" for sc in scenes),
        "scene_enemy_max_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_max_x" for sc in scenes),
        "scene_enemy_max_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_max_x" for sc in scenes),
        "scene_enemy_x_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_x" for sc in scenes),
        "scene_enemy_x_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_x" for sc in scenes),
        "scene_enemy_pmg_y_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_pmg_y" for sc in scenes),
        "scene_enemy_pmg_y_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_pmg_y" for sc in scenes),
        "scene_enemy_height_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_height" for sc in scenes),
        "scene_enemy_height_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_height" for sc in scenes),
        "scene_enemy_frame_dur_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_frame_dur" for sc in scenes),
        "scene_enemy_frame_dur_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_frame_dur" for sc in scenes),
        "scene_enemy_frame_count_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_frame_count" for sc in scenes),
        "scene_enemy_frame_count_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_frame_count" for sc in scenes),
        "scene_enemy_speed_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_speed" for sc in scenes),
        "scene_enemy_speed_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_speed" for sc in scenes),
        "scene_enemy_strategy_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_strategy" for sc in scenes),
        "scene_enemy_strategy_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_strategy" for sc in scenes),
        "scene_enemy_dir_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_dir" for sc in scenes),
        "scene_enemy_dir_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_dir" for sc in scenes),
        "scene_enemy_color_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_color" for sc in scenes),
        "scene_enemy_color_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_color" for sc in scenes),
        "scene_enemy_channel_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_channel" for sc in scenes),
        "scene_enemy_channel_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_channel" for sc in scenes),
        "scene_enemy_zone_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_enemy_zone" for sc in scenes),
        "scene_enemy_zone_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_enemy_zone" for sc in scenes),
        "",
    ])

    return "\n".join(lines)


def generate_scenes_dli_asm(scenes: list[SceneCompiledData]) -> str:
    """Generate MADS 6502 assembly defining DLI SoA data tables for all scenes."""
    lines: list[str] = [
        "; ==============================================================================",
        "; SCENES DLI DATA — CALL OF THE WINTERMON (Auto-generated by compile_scenes.py)",
        "; Target: Atari 800XL / 65XE (MOS 6502, ANTIC Mode D 160x96 2bpp)",
        "; Format: 219 bytes per scene (34 tables x 6 bytes + 15 bytes Zone 0)",
        "; Segment: Loaded under SCENES_DATA segment ($5000)",
        "; ==============================================================================",
        "",
    ]

    for sc in scenes:
        sym = sc.symbol_name
        dli = sc.dli_data
        lines.append(f"; --- DLI Data for {sc.name} (219 bytes) ---")
        lines.append(f"scene_{sym}_dli_data")
        if dli:
            lines.append("    ; 1..7: Platform HPOSP1..3 and HPOSM0..3 (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_p3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m0))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.hpos_m3))

            lines.append("    ; 8..11: Platform SIZEP1..3 and SIZEM (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.sizep1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.sizep2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.sizep3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.sizem))

            lines.append("    ; 12..14: Background Palettes COLPF0..2 (6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf0))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.bg_colpf2))

            lines.append("    ; 15..22: Platform Color Scanlines 0..7 (single table for all channels)")
            for sl in range(8):
                lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.pas_color_sl[sl]))

            lines.append("    ; 23..28: Zone Enemies HPOS and Color (P1..P3, 6 bytes each)")
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p1))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p2))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_hpos_p3))
            lines.append("    .byte " + ", ".join(f"${v:02X}" for v in dli.zone_col_p3))

            lines.append("    ; 29..34: Zone Secrets HPOS (M0..M3), Color, and PRIOR (6 bytes each)")
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
            lines.append("    :219 .byte 0")
        lines.append("")

        if dli and dli.pmg_patterns:
            lines.append(f"; --- PMG Patterns for {sc.name} (18 bytes) ---")
            lines.append(f"scene_{sym}_pmg_patterns")
            for p_idx in range(6):
                p_slice = dli.pmg_patterns.patterns[p_idx * 3 : p_idx * 3 + 3]
                lines.append("    .byte " + ", ".join(f"${v:02X}" for v in p_slice))
        else:
            lines.append(f"; --- PMG Patterns for {sc.name} (18 bytes) ---")
            lines.append(f"scene_{sym}_pmg_patterns")
            lines.append("    :18 .byte $FF")
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
        "; " + "=" * 78,
        "; MASTER SCENE PMG PATTERNS POINTER TABLES",
        "; " + "=" * 78,
        "scene_pmg_patterns_lo",
        "    .byte " + ", ".join(f"<scene_{sc.symbol_name}_pmg_patterns" for sc in scenes),
        "scene_pmg_patterns_hi",
        "    .byte " + ", ".join(f">scene_{sc.symbol_name}_pmg_patterns" for sc in scenes),
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
    definitions_path: Path | None = None,
    sprites_path: Path | None = None,
) -> int:
    """Main compilation pipeline: parse manifest, compile scene JSONs, emit ASM."""
    if not manifest_path.is_file():
        print(f"Error: Manifest file '{manifest_path}' not found.", file=sys.stderr)
        return 1

    sdir = scenes_dir or manifest_path.parent
    dfile = definitions_path or (sdir / "definitions.json")
    if not dfile.is_file():
        if (manifest_path.parent.parent / "scenes" / "definitions.json").is_file():
            dfile = manifest_path.parent.parent / "scenes" / "definitions.json"
        elif Path("scenes/definitions.json").is_file():
            dfile = Path("scenes/definitions.json")

    efile = enemies_path or (dfile if dfile.is_file() else (sdir / "enemies.json"))
    if not efile.is_file():
        if (manifest_path.parent.parent / "scenes" / "enemies.json").is_file():
            efile = manifest_path.parent.parent / "scenes" / "enemies.json"
        elif Path("scenes/enemies.json").is_file():
            efile = Path("scenes/enemies.json")

    sfile = secrets_path or (dfile if dfile.is_file() else (sdir / "secrets.json"))
    if not sfile.is_file():
        if (manifest_path.parent.parent / "scenes" / "secrets.json").is_file():
            sfile = manifest_path.parent.parent / "scenes" / "secrets.json"
        elif Path("scenes/secrets.json").is_file():
            sfile = Path("scenes/secrets.json")

    pfile = profiles_path or (dfile if dfile.is_file() else (sdir / "platform_profiles.json"))
    if not pfile.is_file():
        if (manifest_path.parent.parent / "scenes" / "platform_profiles.json").is_file():
            pfile = manifest_path.parent.parent / "scenes" / "platform_profiles.json"
        elif Path("scenes/platform_profiles.json").is_file():
            pfile = Path("scenes/platform_profiles.json")

    spr_file = sprites_path or Path("sprites/objects.sprite.json")
    if not spr_file.is_file():
        if (manifest_path.parent.parent / "sprites" / "objects.sprite.json").is_file():
            spr_file = manifest_path.parent.parent / "sprites" / "objects.sprite.json"

    try:
        enemies, secrets = load_catalogues(efile, sfile)
        profiles = load_platform_profiles(pfile)
        sprites = (
            parse_sprites_json(
                spr_file,
                definitions_path=dfile if dfile.is_file() else None,
                scenes_manifest_path=manifest_path if manifest_path.is_file() else None,
            )
            if spr_file.is_file()
            else {}
        )
    except Exception as exc:
        print(f"Błąd inicjalizacji zasobów: {exc}", file=sys.stderr)
        return 1

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
            sc_data = parse_scene_json(
                scene_file,
                enemies,
                secrets,
                profiles,
                sprites,
                require_secret=True,
            )
            compiled_scenes.append(sc_data)
            print(
                f"Compiled scene: {sc_data.name} ({fname}) — "
                f"{len(sc_data.elements)} elems, {len(sc_data.platforms)} plats, "
                f"{len(sc_data.objects)} objs, {len(sc_data.secrets)} secrets"
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

    # Print resolution table for all catalogue definitions and scene objects
    res_entries: list[dict[str, Any]] = []
    for eid, e in sorted(enemies.items(), key=lambda x: x[0]):
        spr_name = getattr(sprites.get(e.sprite_id), "description", f"Sprite_{e.sprite_id}") if (sprites and e.sprite_id in sprites) else (e.sprite or f"Sprite_{e.sprite_id}")
        res_entries.append({
            "source": f"Katalog: Wróg typ {eid} ('{e.name}')",
            "sprite_id": e.sprite_id,
            "sprite_name": spr_name,
            "role": "Wróg (Player)",
        })
    for sid, s in sorted(secrets.items(), key=lambda x: x[0]):
        spr_name = getattr(sprites.get(s.sprite_id), "description", f"Sprite_{s.sprite_id}") if (sprites and s.sprite_id in sprites) else (s.sprite or f"Sprite_{s.sprite_id}")
        res_entries.append({
            "source": f"Katalog: Sekret typ {sid} ('{s.name}')",
            "sprite_id": s.sprite_id,
            "sprite_name": spr_name,
            "role": "Sekret (Pociski)",
        })
    for sc in compiled_scenes:
        for en in sc.enemies:
            spr_name = getattr(sprites.get(en.sprite_id), "description", f"Sprite_{en.sprite_id}") if (sprites and en.sprite_id in sprites) else f"Sprite_{en.sprite_id}"
            res_entries.append({
                "source": f"Scena '{sc.file_stem}': wróg {en.id} (typ {en.def_id})",
                "sprite_id": en.sprite_id,
                "sprite_name": spr_name,
                "role": "Wróg (Player)",
            })
        for sec in sc.secrets:
            spr_name = getattr(sprites.get(sec.sprite_id), "description", f"Sprite_{sec.sprite_id}") if (sprites and sec.sprite_id in sprites) else f"Sprite_{sec.sprite_id}"
            res_entries.append({
                "source": f"Scena '{sc.file_stem}': sekret {sec.id} (typ {sec.def_id})",
                "sprite_id": sec.sprite_id,
                "sprite_name": spr_name,
                "role": "Sekret (Pociski)",
            })

    try:
        try:
            from scripts.sprite_links import format_resolution_table
        except ImportError:
            from sprite_links import format_resolution_table
        print(format_resolution_table(res_entries))
    except Exception as e:
        print(f"Warning: Could not format resolution table ({e})", file=sys.stderr)

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
        "--definitions",
        "-d",
        type=Path,
        default=Path("scenes/definitions.json"),
        help="Path to unified definitions.json catalogue",
    )
    parser.add_argument(
        "--enemies",
        type=Path,
        default=None,
        help="Path to legacy enemies.json catalogue",
    )
    parser.add_argument(
        "--secrets",
        type=Path,
        default=None,
        help="Path to legacy secrets.json catalogue",
    )
    parser.add_argument(
        "--profiles",
        "-p",
        type=Path,
        default=None,
        help="Path to legacy platform_profiles.json catalogue",
    )
    parser.add_argument(
        "--sprites",
        "-s",
        type=Path,
        default=Path("sprites/objects.sprite.json"),
        help="Path to sprites JSON file",
    )

    args = parser.parse_args()
    return compile_scenes(
        manifest_path=args.manifest,
        output_path=args.output,
        scenes_dir=args.scenes_dir,
        enemies_path=args.enemies,
        secrets_path=args.secrets,
        profiles_path=args.profiles,
        definitions_path=args.definitions,
        sprites_path=args.sprites,
    )


if __name__ == "__main__":
    sys.exit(main())
