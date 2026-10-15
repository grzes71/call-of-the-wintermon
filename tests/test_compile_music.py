"""Unit tests for music compiler script (scripts/compile_music.py)."""

from pathlib import Path
import pytest

from scripts.compile_music import compile_music


def test_compile_music_valid_json(tmp_path: Path):
    source_json = Path("music/title.json")
    assert source_json.exists()

    output_asm = tmp_path / "title_music.asm"
    ret = compile_music(source_json, output_asm, song_label="test_music_data")

    assert ret == 0
    assert output_asm.exists()

    content = output_asm.read_text(encoding="utf-8")
    assert "test_music_data:" in content
    assert "test_music_data_instruments:" in content
    assert "test_music_data_sequence:" in content


def test_compile_music_missing_input(tmp_path: Path):
    missing_json = tmp_path / "does_not_exist.json"
    output_asm = tmp_path / "output.asm"
    ret = compile_music(missing_json, output_asm)
    assert ret != 0
    assert not output_asm.exists()
