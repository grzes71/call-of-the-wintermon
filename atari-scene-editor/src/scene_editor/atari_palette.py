"""Atari 8-bit GTIA color register palette and conversion utilities.

Target: Atari 800XL / 65XE (GTIA hardware color registers)
The GTIA palette consists of 16 hues (bits 7..4) and 8 luminances (bits 3..1).
The least significant bit (bit 0) is ignored by hardware (always even).
"""

from __future__ import annotations

import re
from typing import Any, Optional, Union

# Standard Atari 8-bit 256-color palette (Altirra default / NTSC-PAL composite model).
# Indexed by byte value 0x00 .. 0xFF.
# Odd byte values mirror the even value below them since bit 0 is ignored by GTIA.
ATARI_GTIA_PALETTE: list[tuple[int, int, int]] = [
    # 0x00 - 0x0F: Grayscale
    (0, 0, 0), (0, 0, 0), (32, 32, 32), (32, 32, 32),
    (64, 64, 64), (64, 64, 64), (96, 96, 96), (96, 96, 96),
    (128, 128, 128), (128, 128, 128), (168, 168, 168), (168, 168, 168),
    (208, 208, 208), (208, 208, 208), (255, 255, 255), (255, 255, 255),

    # 0x10 - 0x1F: Gold / Light Orange
    (38, 21, 0), (38, 21, 0), (69, 41, 0), (69, 41, 0),
    (102, 63, 0), (102, 63, 0), (137, 86, 0), (137, 86, 0),
    (172, 111, 0), (172, 111, 0), (209, 137, 10), (209, 137, 10),
    (245, 166, 49), (245, 166, 49), (255, 196, 99), (255, 196, 99),

    # 0x20 - 0x2F: Orange-Gold
    (54, 10, 0), (54, 10, 0), (88, 27, 0), (88, 27, 0),
    (124, 46, 0), (124, 46, 0), (161, 68, 0), (161, 68, 0),
    (198, 92, 0), (198, 92, 0), (235, 118, 17), (235, 118, 17),
    (255, 147, 57), (255, 147, 57), (255, 179, 106), (255, 179, 106),

    # 0x30 - 0x3F: Red-Orange
    (63, 2, 0), (63, 2, 0), (99, 16, 0), (99, 16, 0),
    (137, 32, 0), (137, 32, 0), (174, 52, 0), (174, 52, 0),
    (212, 74, 0), (212, 74, 0), (249, 100, 27), (249, 100, 27),
    (255, 130, 67), (255, 130, 67), (255, 163, 116), (255, 163, 116),

    # 0x40 - 0x4F: Pink-Red
    (64, 0, 7), (64, 0, 7), (101, 7, 21), (101, 7, 21),
    (139, 21, 38), (139, 21, 38), (177, 39, 58), (177, 39, 58),
    (215, 60, 80), (215, 60, 80), (251, 85, 106), (251, 85, 106),
    (255, 115, 137), (255, 115, 137), (255, 150, 172), (255, 150, 172),

    # 0x50 - 0x5F: Purple / Magenta
    (57, 0, 37), (57, 0, 37), (93, 2, 60), (93, 2, 60),
    (130, 13, 85), (130, 13, 85), (168, 29, 113), (168, 29, 113),
    (206, 49, 142), (206, 49, 142), (242, 73, 173), (242, 73, 173),
    (255, 104, 206), (255, 104, 206), (255, 140, 239), (255, 140, 239),

    # 0x60 - 0x6F: Purple-Violet
    (42, 0, 68), (42, 0, 68), (75, 1, 98), (75, 1, 98),
    (110, 9, 130), (110, 9, 130), (147, 23, 163), (147, 23, 163),
    (184, 42, 197), (184, 42, 197), (220, 64, 232), (220, 64, 232),
    (255, 93, 255), (255, 93, 255), (255, 131, 255), (255, 131, 255),

    # 0x70 - 0x7F: Blue-Violet
    (20, 3, 91), (20, 3, 91), (49, 9, 126), (49, 9, 126),
    (81, 19, 162), (81, 19, 162), (115, 34, 199), (115, 34, 199),
    (151, 53, 235), (151, 53, 235), (187, 75, 255), (187, 75, 255),
    (225, 102, 255), (225, 102, 255), (255, 138, 255), (255, 138, 255),

    # 0x80 - 0x8F: Blue
    (0, 12, 99), (0, 12, 99), (18, 24, 137), (18, 24, 137),
    (45, 39, 176), (45, 39, 176), (75, 57, 214), (75, 57, 214),
    (109, 78, 252), (109, 78, 252), (145, 102, 255), (145, 102, 255),
    (183, 128, 255), (183, 128, 255), (222, 159, 255), (222, 159, 255),

    # 0x90 - 0x9F: Light Blue / Cyan
    (0, 23, 91), (0, 23, 91), (0, 40, 127), (0, 40, 127),
    (14, 59, 164), (14, 59, 164), (43, 79, 203), (43, 79, 203),
    (74, 103, 242), (74, 103, 242), (108, 128, 255), (108, 128, 255),
    (146, 156, 255), (146, 156, 255), (186, 186, 255), (186, 186, 255),

    # 0xA0 - 0xAF: Turquoise / Aqua
    (0, 31, 67), (0, 31, 67), (0, 52, 98), (0, 52, 98),
    (0, 74, 131), (0, 74, 131), (13, 97, 167), (13, 97, 167),
    (45, 122, 204), (45, 122, 204), (79, 149, 243), (79, 149, 243),
    (117, 177, 255), (117, 177, 255), (158, 207, 255), (158, 207, 255),

    # 0xB0 - 0xBF: Green-Cyan
    (0, 36, 30), (0, 36, 30), (0, 58, 54), (0, 58, 54),
    (0, 81, 81), (0, 81, 81), (0, 106, 111), (0, 106, 111),
    (24, 133, 144), (24, 133, 144), (60, 161, 178), (60, 161, 178),
    (98, 191, 215), (98, 191, 215), (140, 222, 252), (140, 222, 252),

    # 0xC0 - 0xCF: Green
    (0, 36, 0), (0, 36, 0), (0, 58, 10), (0, 58, 10),
    (0, 82, 30), (0, 82, 30), (0, 108, 53), (0, 108, 53),
    (17, 136, 79), (17, 136, 79), (54, 165, 109), (54, 165, 109),
    (93, 196, 142), (93, 196, 142), (134, 227, 178), (134, 227, 178),

    # 0xD0 - 0xDF: Yellow-Green
    (0, 32, 0), (0, 32, 0), (5, 53, 0), (5, 53, 0),
    (25, 76, 0), (25, 76, 0), (52, 101, 0), (52, 101, 0),
    (81, 128, 21), (81, 128, 21), (113, 157, 53), (113, 157, 53),
    (148, 187, 88), (148, 187, 88), (186, 219, 127), (186, 219, 127),

    # 0xE0 - 0xEF: Orange-Green / Olive
    (6, 25, 0), (6, 25, 0), (30, 44, 0), (30, 44, 0),
    (57, 65, 0), (57, 65, 0), (86, 88, 0), (86, 88, 0),
    (119, 114, 0), (119, 114, 0), (153, 141, 13), (153, 141, 13),
    (189, 170, 54), (189, 170, 54), (226, 201, 98), (226, 201, 98),

    # 0xF0 - 0xFF: Light Orange / Brown
    (24, 16, 0), (24, 16, 0), (52, 33, 0), (52, 33, 0),
    (82, 52, 0), (82, 52, 0), (114, 73, 0), (114, 73, 0),
    (149, 97, 0), (149, 97, 0), (184, 123, 0), (184, 123, 0),
    (222, 151, 38), (222, 151, 38), (255, 180, 87), (255, 180, 87),
]


def atari_color_to_rgb(atari_color: int) -> tuple[int, int, int]:
    """Return RGB (0..255) tuple corresponding to the Atari GTIA color register value."""
    clamped = max(0, min(255, int(atari_color)))
    return ATARI_GTIA_PALETTE[clamped]


def atari_color_to_hex_rgb(atari_color: int) -> str:
    """Return CSS/Qt color hex string '#RRGGBB' for the Atari GTIA color register value."""
    r, g, b = atari_color_to_rgb(atari_color)
    return f"#{r:02X}{g:02X}{b:02X}"


def format_atari_color_hex(atari_color: int) -> str:
    """Format an Atari register color byte as standard hex string (e.g. '0xC6')."""
    return f"0x{int(atari_color) & 0xFF:02X}"


def parse_atari_color_hex(value: Union[str, int]) -> int:
    """Parse a string or int into a validated Atari register color value.

    Accepts formats: '0xC6', '$C6', 'C6', 'c6', 198.
    Raises ValueError if invalid hex, outside 0x00..0xFF, or if bit 0 is not 0 (not even).
    """
    if isinstance(value, int):
        val = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Color value cannot be empty.")
        if cleaned.startswith("$"):
            val = int(cleaned[1:], 16)
        elif cleaned.startswith("0x") or cleaned.startswith("0X"):
            val = int(cleaned[2:], 16)
        else:
            val = int(cleaned, 16)
    else:
        raise ValueError(f"Expected int or str, got {type(value).__name__}.")

    if not (0 <= val <= 255):
        raise ValueError(f"Atari color value out of range (0x00-0xFF): {value}")

    if (val & 1) != 0:
        raise ValueError(
            f"Invalid Atari color value 0x{val:02X}: lowest bit must be 0 (even luminance step)."
        )

    return val


def is_valid_atari_color_string(value: str) -> bool:
    """Check if the string is a valid representation of an Atari color value (0x00..0xFE, even)."""
    try:
        parse_atari_color_hex(value)
        return True
    except (ValueError, TypeError):
        return False
