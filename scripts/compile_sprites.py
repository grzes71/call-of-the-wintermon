"""Compile sprite definitions (sprites/*.sprite.json) into Atari 8-bit 6502 MADS assembly.

Target: Atari 800XL / 65XE (MOS 6502, 64 KB RAM)
Display: ANTIC Mode E + Player-Missile Graphics (5th Player / 4 Missiles Mode)

In 5th Player mode:
- 4 Missiles (M0, M1, M2, M3) are combined to form one 8-pixel wide sprite.
- SIZEM = 0 (1x normal missile width = 2 color clocks per missile).
- Each scanline in PMG_MISSILES ($6B00 + Y) stores the 4 missiles in 1 byte:
    Bits 1-0: Missile 0 (Pixel 0 = bit 1, Pixel 1 = bit 0)
    Bits 3-2: Missile 1 (Pixel 2 = bit 3, Pixel 3 = bit 2)
    Bits 5-4: Missile 2 (Pixel 4 = bit 5, Pixel 5 = bit 4)
    Bits 7-6: Missile 3 (Pixel 6 = bit 7, Pixel 7 = bit 6)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.sprite_roles import (
        MAX_ZONE_SPRITE_HEIGHT,
        SpriteValidationError,
        determine_sprite_roles_from_scenes,
        validate_sprite_definition_data,
        check_sprite_id_uniqueness,
    )
except ImportError:
    try:
        from sprite_roles import (
            MAX_ZONE_SPRITE_HEIGHT,
            SpriteValidationError,
            determine_sprite_roles_from_scenes,
            validate_sprite_definition_data,
            check_sprite_id_uniqueness,
        )
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.resolve()))
        from sprite_roles import (
            MAX_ZONE_SPRITE_HEIGHT,
            SpriteValidationError,
            determine_sprite_roles_from_scenes,
            validate_sprite_definition_data,
            check_sprite_id_uniqueness,
        )


@dataclass
class SpriteFrame:
    """A single frame of an 8-pixel wide sprite converted to 5th player missile bytes."""

    rows: list[int]  # List of packed missile bytes, one per scanline


@dataclass
class SpriteDefinition:
    """Compiled sprite definition with animation metadata."""

    id: int
    description: str
    width: int
    height: int
    frame_duration: int
    loop: bool
    format: str = "missiles"  # 'player' | 'missiles'
    frames: list[SpriteFrame] = field(default_factory=list)


def pack_row_to_5th_player_missiles(pixel_row: str) -> int:
    """Convert an 8-character binary pixel string (e.g. '00011000') into a GTIA 5th player missile byte.

    Pixel 0-1 -> Missile 0 (bits 1, 0)
    Pixel 2-3 -> Missile 1 (bits 3, 2)
    Pixel 4-5 -> Missile 2 (bits 5, 4)
    Pixel 6-7 -> Missile 3 (bits 7, 6)
    """
    cleaned = pixel_row.strip().replace(" ", "")
    if len(cleaned) < 8:
        cleaned = cleaned.ljust(8, "0")
    elif len(cleaned) > 8:
        cleaned = cleaned[:8]

    p = [1 if c in ("1", "X", "#") else 0 for c in cleaned]

    m0 = (p[0] << 1) | p[1]
    m1 = (p[2] << 3) | (p[3] << 2)
    m2 = (p[4] << 5) | (p[5] << 4)
    m3 = (p[6] << 7) | (p[7] << 6)

    return m3 | m2 | m1 | m0


def pack_row_to_player_bitmap(pixel_row: str) -> int:
    """Convert an 8-character binary pixel string (e.g. '00001000') into an Atari Player 0 byte.

    Bit 7 is the leftmost pixel (pixel 0), Bit 0 is the rightmost pixel (pixel 7).
    """
    cleaned = pixel_row.strip().replace(" ", "")
    if len(cleaned) < 8:
        cleaned = cleaned.ljust(8, "0")
    elif len(cleaned) > 8:
        cleaned = cleaned[:8]

    val = 0
    for idx, c in enumerate(cleaned):
        if c in ("1", "X", "#"):
            val |= (1 << (7 - idx))

    return val


def parse_sprites_json(
    json_path: Path,
    mode: str = "missiles",
    definitions_path: Path | None = None,
    scenes_manifest_path: Path | None = None,
) -> dict[int, SpriteDefinition]:
    """Parse sprite studio JSON file into validated SpriteDefinition models.

    Validates:
    - Width == 8, height in 1..MAX_ZONE_SPRITE_HEIGHT
    - Non-empty frames with valid rows
    - Duplicate ID checks across sprite files in sprites/ folder
    - Roles resolved from actual scene usage (or fallback to definitions)
    """
    if not json_path.is_file():
        raise FileNotFoundError(f"Plik JSON sprite'ów nie istnieje: {json_path}")

    # Check unused files in sprites/ directory
    sprites_dir = json_path.parent
    all_sprite_files = sorted(sprites_dir.glob("*.sprite.json"))
    if all_sprite_files:
        for sf in all_sprite_files:
            if sf.resolve() != json_path.resolve() and sf.name != "player.sprite.json":
                print(f"Ostrzeżenie: nieużywany plik: {sf.name}", file=sys.stderr)

        # Check internal duplicate IDs within json_path itself
        raw_sprites_peek = json.loads(json_path.read_text(encoding="utf-8")).get("sprites", [])
        seen_ids: dict[int, str] = {}
        for s in raw_sprites_peek:
            sid = int(s.get("id", 0))
            if sid in seen_ids:
                raise SpriteValidationError(
                    f"Błąd integralności sprite'ów: powtórzony sprite ID {sid} w pliku '{json_path.name}'."
                )
            seen_ids[sid] = s.get("description", f"Sprite {sid}")

    # Determine per-sprite packing format based on scenes manifest or definitions
    sprite_roles: dict[int, str] = {}
    if mode == "player":
        pass
    elif scenes_manifest_path and scenes_manifest_path.is_file() and definitions_path and definitions_path.is_file():
        roles, e_usages, s_usages = determine_sprite_roles_from_scenes(
            manifest_path=scenes_manifest_path,
            definitions_path=definitions_path,
            sprites_path=json_path,
        )
        sprite_roles = roles
    elif definitions_path and definitions_path.is_file():
        try:
            try:
                from scripts.sprite_links import SpriteRegistry
            except ImportError:
                from sprite_links import SpriteRegistry
            reg = None
            if json_path.is_file():
                try:
                    reg = SpriteRegistry(json_path)
                except Exception:
                    reg = None

            defs = json.loads(definitions_path.read_text(encoding="utf-8"))
            for enemy in defs.get("enemies", []):
                sid = None
                if reg and enemy.get("sprite"):
                    try:
                        sid, _ = reg.resolve_by_name(enemy["sprite"])
                    except Exception:
                        sid = None
                if sid is None and enemy.get("sprite_id") is not None:
                    sid = int(enemy["sprite_id"])
                if sid is not None:
                    sprite_roles[sid] = "player"

            for secret in defs.get("secrets", []):
                sid = None
                if reg and secret.get("sprite"):
                    try:
                        sid, _ = reg.resolve_by_name(secret["sprite"])
                    except Exception:
                        sid = None
                if sid is None and secret.get("sprite_id") is not None:
                    sid = int(secret["sprite_id"])
                if sid is not None:
                    sprite_roles[sid] = "missiles"
        except Exception as exc:
            print(f"Warning: Failed to read definitions for sprite packing mode: {exc}", file=sys.stderr)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    raw_sprites = data.get("sprites", [])
    sprites: dict[int, SpriteDefinition] = {}

    for raw in raw_sprites:
        validate_sprite_definition_data(raw, source_file=json_path.name)

        sid = int(raw["id"])
        desc = str(raw.get("description", f"Sprite {sid}"))
        w = int(raw.get("width", 8))
        h = int(raw.get("height", 16))

        anim_data = raw.get("animation", {})
        frame_dur = max(1, int(anim_data.get("frame_duration", 4)))
        loop = bool(anim_data.get("loop", True))

        if mode == "player":
            chosen_format = "player"
        else:
            chosen_format = sprite_roles.get(sid, "missiles")
            if sid not in sprite_roles and mode == "missiles":
                print(f"Informacja: Sprite {sid} ('{desc}') nie jest używany w żadnej scenie -> format pocisków (domyślny).")

        raw_frames = raw.get("frames", [])
        frames: list[SpriteFrame] = []

        for f in raw_frames:
            pixel_rows = f.get("pixels", [])
            packed_rows: list[int] = []
            for r_idx in range(h):
                r_str = pixel_rows[r_idx] if r_idx < len(pixel_rows) else "00000000"
                if chosen_format == "player":
                    packed_rows.append(pack_row_to_player_bitmap(r_str))
                else:
                    packed_rows.append(pack_row_to_5th_player_missiles(r_str))
            frames.append(SpriteFrame(rows=packed_rows))

        sprites[sid] = SpriteDefinition(
            id=sid,
            description=desc,
            width=w,
            height=h,
            frame_duration=frame_dur,
            loop=loop,
            format=chosen_format,
            frames=frames,
        )

    return sprites


def generate_player_sprites_asm(sprites: dict[int, SpriteDefinition]) -> str:
    """Generate MADS 6502 assembly defining Player 0 animation frames and direction tables."""
    lines: list[str] = [
        "; ==============================================================================",
        "; PLAYER SPRITES DATA — CALL OF THE WINTERMON (Auto-generated by compile_sprites.py)",
        "; Target: Atari 800XL / 65XE (Player 0 PMG)",
        "; Format: 1 byte per scanline, 1bpp MSB-first (bit 7 = left, bit 0 = right)",
        "; ==============================================================================",
        "",
    ]

    first_spr = next(iter(sprites.values())) if sprites else None
    spr_w = first_spr.width if first_spr else 8
    spr_h = first_spr.height if first_spr else 20
    spr_dur = first_spr.frame_duration if first_spr else 4
    spr_cnt = len(first_spr.frames) if first_spr else 5

    lines.append(f"PLAYER_SPRITE_WIDTH  = {spr_w}")
    lines.append(f"PLAYER_SPRITE_HEIGHT = {spr_h}")
    lines.append(f"PLAYER_FRAME_COUNT   = {spr_cnt}")
    lines.append(f"PLAYER_FRAME_DUR     = {spr_dur}")

    death_spr = next((s for s in sprites.values() if s.description.lower().strip() == "death"), None)
    if death_spr:
        lines.append(f"PLAYER_ANIM_DEATH_COUNT = {len(death_spr.frames)}")
        lines.append(f"PLAYER_ANIM_DEATH_DUR   = {death_spr.frame_duration}")
        lines.append(f"PLAYER_ANIM_DEATH_HOLD  = {death_spr.frame_duration + 50}")
    lines.append("")

    anim_symbols: dict[str, str] = {}

    for sid in sorted(sprites.keys()):
        spr = sprites[sid]
        raw_name = spr.description.lower().strip()
        anim_name = "".join(c if (c.isalnum() or c == "_") else "_" for c in raw_name)
        sym_name = f"player_anim_{anim_name}"
        anim_symbols[anim_name] = sym_name

        lines.extend([
            "; " + "-" * 78,
            f"; Animation: {spr.description} (ID {sid}, {spr.width}x{spr.height}, {len(spr.frames)} frames, duration {spr.frame_duration})",
            "; " + "-" * 78,
        ])

        for f_idx, frame in enumerate(spr.frames):
            lines.append(f"{sym_name}_frame_{f_idx}")
            bytes_str = ", ".join(f"${b:02X}" for b in frame.rows)
            lines.append(f"    .byte {bytes_str}")

        lines.append(f"{sym_name}_frames")
        lines.append("    .word " + ", ".join(f"{sym_name}_frame_{f_idx}" for f_idx in range(len(spr.frames))))
        lines.append("")

    # Direction lookup tables (0 = right, 1 = left)
    right_sym = anim_symbols.get("right", next(iter(anim_symbols.values()), "0"))
    left_sym = anim_symbols.get("left", right_sym)

    lines.extend([
        "; " + "=" * 78,
        "; DIRECTION ANIMATION TABLES (0 = right, 1 = left)",
        "; " + "=" * 78,
        "player_anim_table_lo",
        f"    .byte <{right_sym}_frames, <{left_sym}_frames",
        "player_anim_table_hi",
        f"    .byte >{right_sym}_frames, >{left_sym}_frames",
        "",
    ])

    return "\n".join(lines)


def generate_sprites_asm(sprites: dict[int, SpriteDefinition]) -> str:
    """Generate MADS 6502 assembly defining sprite frames and master lookup tables."""
    lines: list[str] = [
        "; ==============================================================================",
        "; SPRITES DATA — CALL OF THE WINTERMON (Auto-generated by compile_sprites.py)",
        "; Target: Atari 800XL / 65XE (5th Player / 4 Missiles Mode)",
        "; Format: 1 byte per scanline packed for M0..M3 (SIZEM=0)",
        "; ==============================================================================",
        "",
    ]

    max_id = max(sprites.keys()) if sprites else 0
    lines.append(f"MAX_SPRITE_ID = {max_id}")
    lines.append("")

    # Output each sprite's frame data
    for sid in sorted(sprites.keys()):
        spr = sprites[sid]
        lines.extend([
            "; " + "-" * 78,
            f"; Sprite ID {sid}: {spr.description} ({spr.width}x{spr.height}, {len(spr.frames)} frames, duration {spr.frame_duration})",
            "; " + "-" * 78,
        ])

        for f_idx, frame in enumerate(spr.frames):
            lines.append(f"sprite_{sid}_frame_{f_idx}")
            bytes_str = ", ".join(f"${b:02X}" for b in frame.rows)
            lines.append(f"    .byte {bytes_str}")

        lines.append(f"sprite_{sid}_frames")
        lines.append("    .word " + ", ".join(f"sprite_{sid}_frame_{f_idx}" for f_idx in range(len(spr.frames))))
        lines.append("")

    # Master Lookup Tables (1-based index, 0 is dummy)
    lines.extend([
        "; " + "=" * 78,
        "; MASTER SPRITE LOOKUP TABLES (1-based index by sprite_id)",
        "; " + "=" * 78,
    ])

    heights: list[str] = ["0"]
    frame_counts: list[str] = ["0"]
    frame_durs: list[str] = ["0"]
    frames_table_lo: list[str] = ["0"]
    frames_table_hi: list[str] = ["0"]

    for i in range(1, max_id + 1):
        if i in sprites:
            sp = sprites[i]
            heights.append(str(sp.height))
            frame_counts.append(str(len(sp.frames)))
            frame_durs.append(str(sp.frame_duration))
            frames_table_lo.append(f"<sprite_{i}_frames")
            frames_table_hi.append(f">sprite_{i}_frames")
        else:
            heights.append("0")
            frame_counts.append("0")
            frame_durs.append("0")
            frames_table_lo.append("0")
            frames_table_hi.append("0")

    lines.append("sprite_height")
    lines.append("    .byte " + ", ".join(heights))
    lines.append("sprite_frame_count")
    lines.append("    .byte " + ", ".join(frame_counts))
    lines.append("sprite_frame_dur")
    lines.append("    .byte " + ", ".join(frame_durs))
    lines.append("sprite_frames_table_lo")
    lines.append("    .byte " + ", ".join(frames_table_lo))
    lines.append("sprite_frames_table_hi")
    lines.append("    .byte " + ", ".join(frames_table_hi))
    lines.append("")

    return "\n".join(lines)


def generate_sprites_manifest(sprites: dict[int, SpriteDefinition]) -> dict[str, Any]:
    """Generate manifest dictionary for gen/sprites_manifest.json."""
    manifest: dict[str, Any] = {
        "version": 1,
        "max_sprite_id": max(sprites.keys()) if sprites else 0,
        "sprites": {},
    }

    for sid in sorted(sprites.keys()):
        sp = sprites[sid]
        data_bytes = sum(len(f.rows) for f in sp.frames)
        pointer_bytes = len(sp.frames) * 2
        manifest["sprites"][str(sid)] = {
            "id": sp.id,
            "name": sp.description,
            "format": sp.format,
            "width": sp.width,
            "height": sp.height,
            "frame_count": len(sp.frames),
            "frame_duration": sp.frame_duration,
            "loop": sp.loop,
            "data_size_bytes": data_bytes,
            "pointer_size_bytes": pointer_bytes,
            "total_bytes": data_bytes + pointer_bytes,
            "frame_labels": [f"sprite_{sid}_frame_{f}" for f in range(len(sp.frames))],
            "frames_label": f"sprite_{sid}_frames",
        }

    return manifest


def compile_sprites(
    input_path: Path,
    output_path: Path,
    mode: str = "missiles",
    definitions_path: Path | None = None,
    scenes_manifest_path: Path | None = None,
    manifest_output_path: Path | None = None,
) -> int:
    """Compile sprite studio JSON into 6502 assembly and emit manifest."""
    try:
        sprites = parse_sprites_json(
            input_path,
            mode=mode,
            definitions_path=definitions_path,
            scenes_manifest_path=scenes_manifest_path,
        )
    except Exception as exc:
        print(f"Błąd kompilacji sprite'ów '{input_path}': {exc}", file=sys.stderr)
        return 1

    if mode == "player":
        asm_code = generate_player_sprites_asm(sprites)
    else:
        asm_code = generate_sprites_asm(sprites)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(asm_code, encoding="utf-8")
    print(f"Generated ASM sprite tables ({mode}): {output_path} ({len(asm_code)} chars, {len(sprites)} sprites)")

    # Emit manifest for objects sprites
    if mode != "player":
        m_out = manifest_output_path or (output_path.parent / "sprites_manifest.json")
        manifest_data = generate_sprites_manifest(sprites)
        m_out.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        print(f"Generated sprites manifest: {m_out}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile sprite definitions into Atari 6502 MADS assembly.")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("sprites/objects.sprite.json"),
        help="Path to sprite studio JSON file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("gen/sprites_data.asm"),
        help="Path to output ASM file",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["missiles", "player"],
        default="missiles",
        help="Compilation mode: missiles (5th player M0..M3) or player (Player 0 1bpp bitmap)",
    )
    parser.add_argument(
        "--definitions",
        "-d",
        type=Path,
        default=Path("scenes/definitions.json"),
        help="Path to definitions.json to identify enemy vs secret sprites",
    )
    parser.add_argument(
        "--scenes",
        "-s",
        type=Path,
        default=Path("scenes/scenes.json"),
        help="Path to scenes.json manifest to inspect all scenes for sprite roles",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=Path("gen/sprites_manifest.json"),
        help="Path to output sprites_manifest.json",
    )
    args = parser.parse_args()
    return compile_sprites(
        args.input,
        args.output,
        mode=args.mode,
        definitions_path=args.definitions,
        scenes_manifest_path=args.scenes,
        manifest_output_path=args.manifest_out,
    )


if __name__ == "__main__":
    sys.exit(main())

