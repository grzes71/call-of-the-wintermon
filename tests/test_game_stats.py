"""Unit and integration tests for scripts/game_stats.py."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.game_stats import (
    DefinitionInfo,
    SceneStats,
    GameStats,
    load_definitions,
    analyze_scene,
    collect_game_stats,
    format_text_report,
    format_markdown_report,
    format_json_report,
)


def test_load_definitions_from_project_files():
    defs_path = Path("scenes/definitions.json")
    if not defs_path.is_file():
        pytest.skip("scenes/definitions.json not found")

    enemy_defs, secret_defs = load_definitions(defs_path)
    assert len(enemy_defs) > 0
    assert len(secret_defs) > 0

    assert 1 in enemy_defs
    assert isinstance(enemy_defs[1].name, str)
    assert 1 in secret_defs
    assert isinstance(secret_defs[1].name, str)


def test_analyze_scene_extracts_correct_metrics(tmp_path: Path):
    scene_file = tmp_path / "test_scene.json"
    scene_file.write_text(
        json.dumps({
            "scene": {"name": "Test Cavern"},
            "platforms": [
                {"id": "p1", "width": 32, "movement": "none"},
                {"id": "p2", "width": 48, "movement": "left_right"},
                {"id": "p3", "width": 16},
            ],
            "objects": [
                {"type": "enemy", "definition_id": 1},
                {"type": "enemy", "definition_id": 2},
                {"type": "enemy", "definition_id": 1},
                {"type": "secret", "definition_id": 3},
                {"type": "treasure", "definition_id": 4},
            ],
        }),
        encoding="utf-8",
    )

    stats = analyze_scene(scene_file)
    assert stats.name == "Test Cavern"
    assert stats.filename == "test_scene.json"
    assert stats.platform_count == 3
    assert stats.static_platform_count == 2
    assert stats.moving_platform_count == 1
    assert stats.platform_widths == {16: 1, 32: 1, 48: 1}
    assert stats.enemy_count == 3
    assert stats.enemies_by_type == {1: 2, 2: 1}
    assert stats.secret_count == 2
    assert stats.secrets_by_type == {3: 1, 4: 1}


def test_collect_game_stats_and_totals(tmp_path: Path):
    defs_file = tmp_path / "definitions.json"
    defs_file.write_text(
        json.dumps({
            "enemies": [{"id": 1, "name": "Orc"}, {"id": 2, "name": "Goblin"}],
            "secrets": [{"id": 10, "name": "Coin"}, {"id": 20, "name": "Key"}],
        }),
        encoding="utf-8",
    )

    s1_file = tmp_path / "scene1.json"
    s1_file.write_text(
        json.dumps({
            "scene": {"name": "Scene 1"},
            "platforms": [{"id": "p1", "width": 32}],
            "objects": [
                {"type": "enemy", "definition_id": 1},
                {"type": "secret", "definition_id": 10},
            ],
        }),
        encoding="utf-8",
    )

    s2_file = tmp_path / "scene2.json"
    s2_file.write_text(
        json.dumps({
            "scene": {"name": "Scene 2"},
            "platforms": [
                {"id": "p2", "width": 32, "movement": "left_right"},
                {"id": "p3", "width": 64},
            ],
            "objects": [
                {"type": "enemy", "definition_id": 1},
                {"type": "enemy", "definition_id": 2},
                {"type": "secret", "definition_id": 10},
                {"type": "secret", "definition_id": 20},
            ],
        }),
        encoding="utf-8",
    )

    manifest_file = tmp_path / "scenes.json"
    manifest_file.write_text(
        json.dumps({"scenes": ["scene1.json", "scene2.json"]}),
        encoding="utf-8",
    )

    stats = collect_game_stats(manifest_file, defs_file)
    assert len(stats.scenes) == 2
    assert stats.total_platforms == 3
    assert stats.total_static_platforms == 2
    assert stats.total_moving_platforms == 1
    assert stats.total_enemies == 3
    assert stats.total_secrets == 3

    assert stats.global_enemies_by_type == {1: 2, 2: 1}
    assert stats.global_secrets_by_type == {10: 2, 20: 1}
    assert stats.enemy_scenes[1] == ["Scene 1", "Scene 2"]
    assert stats.enemy_scenes[2] == ["Scene 2"]

    text_rep = format_text_report(stats)
    assert "Scene 1" in text_rep
    assert "Scene 2" in text_rep
    assert "Orc" in text_rep
    assert "Goblin" in text_rep
    assert "Coin" in text_rep

    md_rep = format_markdown_report(stats)
    assert "| `scene1.json` |" in md_rep
    assert "| Orc |" in md_rep

    json_rep = format_json_report(stats)
    parsed_json = json.loads(json_rep)
    assert parsed_json["summary"]["total_enemies"] == 3
    assert parsed_json["summary"]["total_secrets"] == 3
    assert len(parsed_json["scenes"]) == 2


def test_collect_game_stats_live_manifest():
    manifest_path = Path("scenes/scenes.json")
    defs_path = Path("scenes/definitions.json")
    if not manifest_path.is_file() or not defs_path.is_file():
        pytest.skip("Game manifest or definitions not found")

    stats = collect_game_stats(manifest_path, defs_path)
    assert len(stats.scenes) == len(json.loads(manifest_path.read_text(encoding="utf-8"))["scenes"])
    assert stats.total_platforms > 0
    assert stats.total_enemies > 0
    assert stats.total_secrets > 0

