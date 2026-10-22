"""Tests for Atari Scene Editor auto-loading from manifest.json on startup."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from scene_editor.catalogue_model import (
    CorruptedCatalogueFileError,
    ProjectCatalogues,
    SecretDefinition,
    EnemyDefinition,
)
from scene_editor.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_find_manifest_path_absent(tmp_path: Path):
    """find_manifest_path returns None when manifest.json does not exist."""
    assert ProjectCatalogues.find_manifest_path(tmp_path) is None


def test_find_manifest_path_present(tmp_path: Path):
    """find_manifest_path returns path when manifest.json exists in base_dir."""
    m_file = tmp_path / "manifest.json"
    m_file.write_text("{}", encoding="utf-8")
    assert ProjectCatalogues.find_manifest_path(tmp_path) == m_file.resolve()


def test_load_from_manifest_dict_and_list_formats(tmp_path: Path):
    """Test load_from_manifest parses scenes.catalogues and graphics.sprites.objects."""
    # Create sample definitions
    defs_file = tmp_path / "custom_definitions.json"
    defs_data = {
        "version": 1,
        "enemies": [{"id": 1, "name": "Demon", "rgb_color": [255, 0, 0], "atari_color": 40}],
        "secrets": [{"id": 1, "name": "Gold Key", "rgb_color": [255, 255, 0], "atari_color": 20}],
    }
    defs_file.write_text(json.dumps(defs_data), encoding="utf-8")

    # Create sample sprite project
    sprites_file = tmp_path / "custom_sprites.json"
    sprites_data = {
        "sprites": [
            {"id": 1, "description": "KeySprite"},
            {"id": 2, "description": "DoorSprite"},
        ]
    }
    sprites_file.write_text(json.dumps(sprites_data), encoding="utf-8")

    # Format 1: dict for graphics.sprites.objects
    manifest_data_1 = {
        "scenes": {"catalogues": "custom_definitions.json"},
        "graphics": {"sprites": {"objects": "custom_sprites.json"}},
    }
    m1_file = tmp_path / "manifest_1.json"
    m1_file.write_text(json.dumps(manifest_data_1), encoding="utf-8")

    cat1 = ProjectCatalogues.load_from_manifest(m1_file, base_dir=tmp_path)
    assert 1 in cat1.enemies
    assert cat1.enemies[1].name == "Demon"
    assert 1 in cat1.secrets
    assert len(cat1.sprites) == len(sprites_data["sprites"])
    assert cat1.manifest_path == m1_file.resolve()

    # Format 2: list for graphics.sprites (like manifest.yaml) and dict with 'path' for catalogues
    manifest_data_2 = {
        "scenes": {"catalogues": {"path": "custom_definitions.json"}},
        "graphics": {
            "sprites": [
                {"id": "objects", "path": "custom_sprites.json"},
                {"id": "other", "path": "nonexistent.json"},
            ]
        },
    }
    m2_file = tmp_path / "manifest_2.json"
    m2_file.write_text(json.dumps(manifest_data_2), encoding="utf-8")

    cat2 = ProjectCatalogues.load_from_manifest(m2_file, base_dir=tmp_path)
    assert 1 in cat2.enemies
    assert 1 in cat2.secrets
    assert len(cat2.sprites) == len(sprites_data["sprites"])


def test_load_from_manifest_invalid_json(tmp_path: Path):
    """Corrupted JSON raises CorruptedCatalogueFileError."""
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(CorruptedCatalogueFileError):
        ProjectCatalogues.load_from_manifest(bad_manifest, base_dir=tmp_path)


def test_main_window_startup_without_manifest(qapp, monkeypatch, tmp_path: Path):
    """When manifest.json is absent, MainWindow preserves default behavior."""
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    win = MainWindow(base_dir=tmp_path)

    assert win.manifest_path is None
    # No sprites loaded initially
    assert not win.new_obj_sprite_combo.isEnabled()
    assert len(win.catalogues.sprites) == 0


def test_main_window_startup_with_manifest(qapp, monkeypatch, tmp_path: Path):
    """When manifest.json is present, MainWindow auto-loads catalogues and sprites."""
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    defs_file = tmp_path / "definitions.json"
    defs_data = {
        "version": 1,
        "enemies": [{"id": 10, "name": "Spectral Bat", "rgb_color": [100, 0, 0], "atari_color": 50}],
        "secrets": [{"id": 20, "name": "Mystic Orb", "rgb_color": [0, 100, 255], "atari_color": 80}],
    }
    defs_file.write_text(json.dumps(defs_data), encoding="utf-8")

    sprites_file = tmp_path / "objects.sprite.json"
    sprites_data = {
        "sprites": [
            {"id": 1, "description": "OrbSprite"},
        ]
    }
    sprites_file.write_text(json.dumps(sprites_data), encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "scenes": {"catalogues": "definitions.json"},
        "graphics": {"sprites": {"objects": "objects.sprite.json"}},
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    win = MainWindow(base_dir=tmp_path)

    assert win.manifest_path == manifest_file.resolve()
    assert 10 in win.catalogues.enemies
    assert 20 in win.catalogues.secrets
    assert len(win.catalogues.sprites) == 1
    # Sprites combo must be enabled because sprites were auto-loaded on startup
    assert win.new_obj_sprite_combo.isEnabled()


def test_main_window_startup_with_yaml_manifest(qapp, monkeypatch, tmp_path: Path):
    """When manifest.yaml is present, MainWindow auto-loads catalogues and sprites."""
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    defs_file = tmp_path / "definitions.json"
    defs_data = {
        "version": 1,
        "enemies": [{"id": 30, "name": "Ghoul", "rgb_color": [0, 255, 0], "atari_color": 60}],
        "secrets": [{"id": 40, "name": "Amulet", "rgb_color": [255, 200, 0], "atari_color": 30}],
    }
    defs_file.write_text(json.dumps(defs_data), encoding="utf-8")

    sprites_file = tmp_path / "objects.sprite.json"
    sprites_data = {
        "sprites": [
            {"id": 1, "description": "AmuletSprite"},
        ]
    }
    sprites_file.write_text(json.dumps(sprites_data), encoding="utf-8")

    yaml_manifest = tmp_path / "manifest.yaml"
    yaml_content = (
        "graphics:\n"
        "  sprites:\n"
        "    - id: \"objects\"\n"
        "      path: \"objects.sprite.json\"\n"
        "scenes:\n"
        "  catalogues: \"definitions.json\"\n"
    )
    yaml_manifest.write_text(yaml_content, encoding="utf-8")

    win = MainWindow(base_dir=tmp_path)

    assert win.manifest_path == yaml_manifest.resolve()
    assert 30 in win.catalogues.enemies
    assert 40 in win.catalogues.secrets
    assert len(win.catalogues.sprites) == 1
    assert win.new_obj_sprite_combo.isEnabled()


def test_cli_log_level_argument(monkeypatch):
    """Test --log-level argument configuration in scene_editor app."""
    from scene_editor.app import main
    import logging

    # Test help exit
    with pytest.raises(SystemExit) as exc:
        main(["atari-scene-editor", "--help"])
    assert exc.value.code == 0

    # Test debug log level
    monkeypatch.setattr("scene_editor.app.MainWindow", lambda: type("DummyWindow", (), {"show": lambda self: None, "open_scene": lambda self, p: None})())
    monkeypatch.setattr("scene_editor.app.QApplication.exec", lambda self: 0)

    code = main(["atari-scene-editor", "--log-level", "DEBUG"])
    assert code == 0
    assert logging.getLogger().level == logging.DEBUG

    code_info = main(["atari-scene-editor", "--log-level", "WARNING"])
    assert code_info == 0
    assert logging.getLogger().level == logging.WARNING


def test_open_scene_preserves_sprites_and_manifest(qapp, monkeypatch, tmp_path: Path):
    """Opening a scene must preserve manifest-loaded sprites and not wipe out catalogues."""
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    defs_file = tmp_path / "definitions.json"
    defs_data = {
        "version": 1,
        "enemies": [{"id": 1, "name": "Beast", "rgb_color": [255, 0, 0], "atari_color": 40, "sprite_id": 1}],
        "secrets": [],
    }
    defs_file.write_text(json.dumps(defs_data), encoding="utf-8")

    sprites_file = tmp_path / "objects.sprite.json"
    sprites_data = {
        "sprites": [
            {"id": 1, "description": "BeastSprite"},
        ]
    }
    sprites_file.write_text(json.dumps(sprites_data), encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "scenes": {"catalogues": "definitions.json"},
        "graphics": {"sprites": {"objects": "objects.sprite.json"}},
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    scene_file = tmp_path / "test_scene.json"
    scene_data = {
        "schema_version": 1,
        "scene": {"name": "test_scene", "width": 160, "height": 96},
        "elements": [],
        "platforms": [],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 10}
        ],
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    win = MainWindow(base_dir=tmp_path)
    assert len(win.catalogues.sprites) == 1
    assert win.new_obj_sprite_combo.isEnabled()

    win.open_scene(scene_file)
    assert len(win.catalogues.sprites) == 1
    assert win.new_obj_sprite_combo.isEnabled()
    assert "definicje nie załadowane" not in win.new_obj_sprite_combo.itemText(0)
    assert "definicje nie załadowane" not in win.obj_prop_sprite_combo.itemText(0)


