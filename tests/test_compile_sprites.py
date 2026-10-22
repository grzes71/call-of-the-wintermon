"""Automated tests for sprite compilation and 5th-player missile bit packing."""

from pathlib import Path
import pytest

from scripts.compile_sprites import (
    pack_row_to_5th_player_missiles,
    parse_sprites_json,
    generate_sprites_asm,
)


def test_pack_row_all_zeros():
    """Verify all blank pixels pack to $00."""
    assert pack_row_to_5th_player_missiles("00000000") == 0x00


def test_pack_row_all_ones():
    """Verify all solid pixels pack to $FF."""
    assert pack_row_to_5th_player_missiles("11111111") == 0xFF


def test_pack_row_individual_missiles():
    """Verify each 2-pixel pair maps to the correct missile bit positions in 5th player mode.

    M0 (bits 1,0): pixels 0, 1
    M1 (bits 3,2): pixels 2, 3
    M2 (bits 5,4): pixels 4, 5
    M3 (bits 7,6): pixels 6, 7
    """
    # Pixel 0 (M0 left) -> bit 1
    assert pack_row_to_5th_player_missiles("10000000") == 0x02
    # Pixel 1 (M0 right) -> bit 0
    assert pack_row_to_5th_player_missiles("01000000") == 0x01
    # Both M0 pixels -> bits 1, 0
    assert pack_row_to_5th_player_missiles("11000000") == 0x03

    # Pixel 2 (M1 left) -> bit 3
    assert pack_row_to_5th_player_missiles("00100000") == 0x08
    # Pixel 3 (M1 right) -> bit 2
    assert pack_row_to_5th_player_missiles("00010000") == 0x04
    # Both M1 pixels -> bits 3, 2
    assert pack_row_to_5th_player_missiles("00110000") == 0x0C

    # Pixel 4 (M2 left) -> bit 5
    assert pack_row_to_5th_player_missiles("00001000") == 0x20
    # Pixel 5 (M2 right) -> bit 4
    assert pack_row_to_5th_player_missiles("00000100") == 0x10
    # Both M2 pixels -> bits 5, 4
    assert pack_row_to_5th_player_missiles("00001100") == 0x30

    # Pixel 6 (M3 left) -> bit 7
    assert pack_row_to_5th_player_missiles("00000010") == 0x80
    # Pixel 7 (M3 right) -> bit 6
    assert pack_row_to_5th_player_missiles("00000001") == 0x40
    # Both M3 pixels -> bits 7, 6
    assert pack_row_to_5th_player_missiles("00000011") == 0xC0


def test_pack_row_mixed_pattern():
    """Verify mixed patterns: e.g. '00011000' -> pixel 3 (bit 2) + pixel 4 (bit 5) = 4 + 32 = $24."""
    assert pack_row_to_5th_player_missiles("00011000") == 0x24


import json

def test_parse_sprites_json_objects():
    """Verify parsing of sprites/objects.sprite.json dynamically matches file definition."""
    json_path = Path("sprites/objects.sprite.json")
    raw_data = json.loads(json_path.read_text(encoding="utf-8"))
    sprites = parse_sprites_json(json_path)

    raw_sprites_by_id = {s["id"]: s for s in raw_data["sprites"]}
    assert set(sprites.keys()) == set(raw_sprites_by_id.keys())

    for spr_id, spr in sprites.items():
        raw_spr = raw_sprites_by_id[spr_id]
        assert spr.description == raw_spr["description"]
        assert spr.width == raw_spr["width"]
        assert spr.height == raw_spr["height"]
        assert spr.frame_duration == raw_spr["animation"]["frame_duration"]
        assert spr.loop == raw_spr["animation"].get("loop", True)
        assert len(spr.frames) == len(raw_spr["frames"])
        assert len(spr.frames) > 0


def test_generate_sprites_asm():
    """Verify MADS assembly generation from sprites model."""
    json_path = Path("sprites/objects.sprite.json")
    sprites = parse_sprites_json(json_path)
    asm_text = generate_sprites_asm(sprites)

    max_id = max(sprites.keys()) if sprites else 0
    assert f"MAX_SPRITE_ID = {max_id}" in asm_text
    for sid in sprites:
        assert f"sprite_{sid}_frame_0" in asm_text
    assert "sprite_height" in asm_text
    assert "sprite_frame_count" in asm_text
    assert "sprite_frame_dur" in asm_text
    assert "sprite_frames_table_lo" in asm_text
    assert "sprite_frames_table_hi" in asm_text


from scripts.compile_sprites import pack_row_to_player_bitmap, generate_player_sprites_asm


def test_pack_row_player_bitmap():
    """Verify MSB-first bit packing for Player 0."""
    assert pack_row_to_player_bitmap("00000000") == 0x00
    assert pack_row_to_player_bitmap("11111111") == 0xFF
    assert pack_row_to_player_bitmap("10000000") == 0x80
    assert pack_row_to_player_bitmap("00000001") == 0x01
    assert pack_row_to_player_bitmap("00001000") == 0x08
    assert pack_row_to_player_bitmap("00011100") == 0x1C


def test_generate_player_sprites_asm():
    """Verify Player 0 animation frames and direction tables."""
    json_path = Path("sprites/player.sprite.json")
    sprites = parse_sprites_json(json_path, mode="player")
    asm_text = generate_player_sprites_asm(sprites)

    assert "PLAYER_SPRITE_WIDTH  = 8" in asm_text
    assert "PLAYER_SPRITE_HEIGHT = 20" in asm_text
    assert "PLAYER_FRAME_COUNT   = 5" in asm_text
    assert "PLAYER_ANIM_DEATH_COUNT = 3" in asm_text
    assert "PLAYER_ANIM_DEATH_DUR   = 10" in asm_text
    assert "PLAYER_ANIM_DEATH_HOLD  = 60" in asm_text
    assert "player_anim_right_frame_0" in asm_text
    assert "player_anim_right_frames" in asm_text
    assert "player_anim_left_frame_0" in asm_text
    assert "player_anim_left_frames" in asm_text
    assert "player_anim_death_frame_0" in asm_text
    assert "player_anim_death_frames" in asm_text
    assert "player_anim_table_lo" in asm_text
    assert "player_anim_table_hi" in asm_text

