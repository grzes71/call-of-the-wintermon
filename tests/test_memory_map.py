"""Unit and integration tests for memory map generator (scripts/generate_memory_map.py)."""

from __future__ import annotations

from pathlib import Path
import pytest

from scripts.generate_memory_map import (
    parse_xex_segments,
    identify_segment,
    build_memory_map,
    generate_graphical_pdf,
    main,
)


def test_parse_xex_segments_from_built_binary():
    xex_path = Path("call_of_the_wintermon.xex")
    if not xex_path.is_file():
        pytest.skip("call_of_the_wintermon.xex not found, build binary first")

    data = xex_path.read_bytes()
    segments = parse_xex_segments(data)

    assert len(segments) >= 10
    starts = [s[0] for s in segments]
    assert 0x2000 in starts  # Code
    assert 0x3000 in starts  # Gameplay VRAM
    assert 0x4000 in starts  # Title VRAM
    assert 0x8000 in starts  # Tilesets


def test_identify_segment():
    name, cat, col, _ = identify_segment(0x2000, 0x235B, 860)
    assert cat == "CODE"
    assert "Engine" in name

    name, cat, col, _ = identify_segment(0x3000, 0x3F88, 3977)
    assert cat == "GRAPHICS"
    assert "VRAM" in name

    name, cat, col, _ = identify_segment(0x8000, 0xBF6C, 16237)
    assert cat == "BITMAPS"
    assert "Tilesets" in name


def test_build_memory_map_bounds_and_continuity():
    xex_path = Path("call_of_the_wintermon.xex")
    if not xex_path.is_file():
        pytest.skip("call_of_the_wintermon.xex not found, build binary first")

    data = xex_path.read_bytes()
    raw_segments = parse_xex_segments(data)
    all_regions, free_gaps = build_memory_map(raw_segments)

    # All regions must span exactly $2000 to $BFFF contiguously
    assert all_regions[0].start == 0x2000
    assert all_regions[-1].end == 0xBFFF

    for i in range(len(all_regions) - 1):
        assert all_regions[i].end + 1 == all_regions[i + 1].start, (
            f"Discontinuity between {all_regions[i].name} and {all_regions[i+1].name}"
        )

    # Total bytes must sum to exactly 40,960 bytes ($2000 to $BFFF)
    total_bytes = sum(r.size for r in all_regions)
    assert total_bytes == 40960

    # Ensure free gaps are detected and non-empty
    assert len(free_gaps) >= 5
    largest_gap = max(g.size for g in free_gaps)
    assert largest_gap >= 1800  # $60CA-$67FF is 1,846 bytes


def test_generate_graphical_pdf(tmp_path: Path):
    xex_path = Path("call_of_the_wintermon.xex")
    if not xex_path.is_file():
        pytest.skip("call_of_the_wintermon.xex not found, build binary first")

    data = xex_path.read_bytes()
    raw_segments = parse_xex_segments(data)
    all_regions, free_gaps = build_memory_map(raw_segments)

    out_pdf = tmp_path / "test_memory_map.pdf"
    generate_graphical_pdf(out_pdf, xex_path.name, all_regions, free_gaps)

    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 10_000  # Ensure valid non-trivial vector PDF
