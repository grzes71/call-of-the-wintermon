import os
import sys
from pathlib import Path

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication

from sprite_studio.models import Project, Sprite, Frame, Animation
from sprite_studio.validation import validate_project
from sprite_studio.io import load_project, save_project
from sprite_studio.widgets.properties import PropertiesWidget
from sprite_studio.widgets.sprite_list import SpriteListWidget
from sprite_studio.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sprite_model_defaults():
    sprite = Sprite()
    assert isinstance(sprite.id, int)
    assert sprite.id == 1
    assert isinstance(sprite.description, str)
    assert sprite.description == ""


def test_validation_valid_sprite_ids_and_descriptions():
    project = Project(version=1)
    s1 = Sprite(id=1, description="Player Idle", height=8, frames=[Frame(pixels=["00000000"] * 8)])
    s2 = Sprite(id=255, description="A" * 40, height=8, frames=[Frame(pixels=["00000000"] * 8)])
    project.sprites = [s1, s2]

    errors = validate_project(project)
    assert errors == []


def test_validation_invalid_sprite_ids():
    # ID not integer or boolean
    project = Project(version=1)
    s1 = Sprite(id="SPRITE_1", height=8, frames=[Frame(pixels=["00000000"] * 8)])
    project.sprites = [s1]
    errors = validate_project(project)
    assert any("invalid_sprite_id" in e for e in errors)

    # Boolean True (which is subclass of int in Python)
    s1.id = True  # type: ignore
    errors = validate_project(project)
    assert any("invalid_sprite_id" in e for e in errors)

    # ID out of range: 0
    s1.id = 0
    errors = validate_project(project)
    assert any("invalid_sprite_id" in e for e in errors)

    # ID out of range: 256
    s1.id = 256
    errors = validate_project(project)
    assert any("invalid_sprite_id" in e for e in errors)


def test_validation_duplicate_sprite_ids():
    project = Project(version=1)
    s1 = Sprite(id=42, description="First", height=8, frames=[Frame(pixels=["00000000"] * 8)])
    s2 = Sprite(id=42, description="Second", height=8, frames=[Frame(pixels=["00000000"] * 8)])
    project.sprites = [s1, s2]

    errors = validate_project(project)
    assert any("duplicate_sprite_id" in e for e in errors)


def test_validation_invalid_descriptions():
    # Description > 40 chars
    project = Project(version=1)
    s1 = Sprite(id=1, description="A" * 41, height=8, frames=[Frame(pixels=["00000000"] * 8)])
    project.sprites = [s1]
    errors = validate_project(project)
    assert any("invalid_description" in e for e in errors)

    # Non-string description
    s1.description = 123  # type: ignore
    errors = validate_project(project)
    assert any("invalid_description" in e for e in errors)


def test_io_save_and_load_round_trip(tmp_path: Path):
    project = Project(version=1)
    sprite = Sprite(
        id=7,
        description="Enemy Bat",
        width=8,
        height=4,
        color=14,
        animation=Animation(frame_duration=6, loop=False),
        frames=[Frame(pixels=["00111100", "01111110", "11111111", "00100100"])],
    )
    project.sprites.append(sprite)

    file_path = tmp_path / "test.sprite.json"
    assert save_project(file_path, project) is True

    loaded = load_project(file_path)
    assert len(loaded.sprites) == 1
    loaded_spr = loaded.sprites[0]
    assert loaded_spr.id == 7
    assert isinstance(loaded_spr.id, int)
    assert loaded_spr.description == "Enemy Bat"
    assert loaded_spr.animation.frame_duration == 6
    assert loaded_spr.animation.loop is False


def test_io_legacy_string_id_and_missing_description(tmp_path: Path):
    # Backward compatibility with older string ID json
    json_content = """{
      "version": 1,
      "sprites": [
        {
          "id": "15",
          "width": 8,
          "height": 2,
          "color": 0,
          "animation": {"frame_duration": 4, "loop": true},
          "frames": [{"pixels": ["11111111", "00000000"]}]
        }
      ]
    }"""
    file_path = tmp_path / "legacy.sprite.json"
    file_path.write_text(json_content, encoding="utf-8")

    loaded = load_project(file_path)
    assert len(loaded.sprites) == 1
    assert loaded.sprites[0].id == 15
    assert isinstance(loaded.sprites[0].id, int)
    assert loaded.sprites[0].description == ""


def test_properties_widget(qapp):
    widget = PropertiesWidget()
    sprite = Sprite(id=12, description="Coin", height=16)

    widget.update_from_sprite(sprite)
    assert widget.spin_id.value() == 12
    assert widget.edit_description.text() == "Coin"

    # Test signal emission
    received_id = []
    widget.id_changed.connect(received_id.append)
    widget.spin_id.setValue(20)
    assert received_id == [20]

    received_desc = []
    widget.description_changed.connect(received_desc.append)
    widget.edit_description.setText("Silver Coin")
    widget.edit_description.textEdited.emit("Silver Coin")
    assert received_desc == ["Silver Coin"]


def test_sprite_list_widget(qapp):
    widget = SpriteListWidget()
    project = Project(version=1)
    s1 = Sprite(id=1, description="Hero")
    s2 = Sprite(id=2, description="")
    project.sprites = [s1, s2]

    widget.set_project(project)
    assert widget.list_widget.count() == 2
    assert widget.list_widget.item(0).text() == "1: Hero"
    assert widget.list_widget.item(1).text() == "2"

    # Test in-place update display
    s1.description = "Hero Knight"
    widget.update_sprite_display(s1)
    assert widget.list_widget.item(0).text() == "1: Hero Knight"


def test_main_window_add_copy_and_undo_redo(qapp):
    window = MainWindow()
    assert len(window.project.sprites) == 0

    # Add sprite
    window._on_add_sprite()
    assert len(window.project.sprites) == 1
    spr1 = window.project.sprites[0]
    assert spr1.id == 1
    assert spr1.description == ""

    # Add second sprite
    window._on_add_sprite()
    assert len(window.project.sprites) == 2
    spr2 = window.project.sprites[1]
    assert spr2.id == 2

    # Change description with undo/redo
    window._on_sprite_selected(spr1)
    window._on_prop_description("Main Hero")
    assert spr1.description == "Main Hero"

    window._undo()
    assert spr1.description == ""

    window._redo()
    assert spr1.description == "Main Hero"

    # Change ID with undo/redo
    window._on_prop_id(50)
    assert spr1.id == 50

    window._undo()
    assert spr1.id == 1

    window._redo()
    assert spr1.id == 50

    # Copy sprite generates unique integer id and preserves/tags description
    window._on_copy_sprite(spr1)
    assert len(window.project.sprites) == 3
    copied = window.project.sprites[2]
    assert copied.id == 1  # IDs used were {50, 2}, next smallest available ID is 1
    assert "Main Hero (Copy)" in copied.description


def test_frame_copy_and_paste(qapp):
    window = MainWindow()
    window._on_add_sprite()
    spr = window.project.sprites[0]
    window._on_sprite_selected(spr)
    window._on_add_frame()
    assert len(spr.frames) == 2

    # Set distinct patterns in frame 0 and frame 1
    spr.frames[0].pixels = ["11000000"] * spr.height
    spr.frames[1].pixels = ["00000011"] * spr.height

    # Copy frame 0 to clipboard
    window._on_frame_selected(0)
    window._on_copy_frame()
    assert window.clipboard_frame_pixels == ["11000000"] * spr.height

    # Paste into frame 1
    window._on_frame_selected(1)
    window._on_paste_frame()
    assert spr.frames[1].pixels == ["11000000"] * spr.height

    # Undo should restore original frame 1 content
    window._undo()
    assert spr.frames[1].pixels == ["00000011"] * spr.height

    # Redo should re-apply pasted content
    window._redo()
    assert spr.frames[1].pixels == ["11000000"] * spr.height


def test_frame_copy_paste_empty_or_no_frame(qapp):
    MainWindow.clipboard_frame_pixels = None
    window = MainWindow()
    # With no sprite selected, copy and paste should safely do nothing
    window._on_copy_frame()
    assert window.clipboard_frame_pixels is None
    window._on_paste_frame()

    # Add sprite but empty clipboard
    window._on_add_sprite()
    spr = window.project.sprites[0]
    window._on_sprite_selected(spr)
    original_pixels = list(spr.frames[0].pixels)
    window._on_paste_frame()
    assert spr.frames[0].pixels == original_pixels


def test_timeline_copy_paste_signals(qapp):
    from sprite_studio.widgets.timeline import TimelineWidget
    widget = TimelineWidget()
    widget.set_frames(3, 1)

    copy_calls = []
    paste_calls = []
    widget.copy_requested.connect(copy_calls.append)
    widget.paste_requested.connect(paste_calls.append)

    widget.btn_copy.click()
    assert copy_calls == [1]

    widget.btn_paste.click()
    assert paste_calls == [1]


def test_timeline_mirror_h_and_v_signals(qapp):
    from sprite_studio.widgets.timeline import TimelineWidget
    widget = TimelineWidget()
    widget.set_frames(3, 1)

    assert widget.btn_mirror_h.text() == "H Mirror"
    assert widget.btn_mirror_v.text() == "V Mirror"

    h_calls = []
    v_calls = []
    legacy_calls = []
    widget.mirror_h_requested.connect(h_calls.append)
    widget.mirror_v_requested.connect(v_calls.append)
    widget.mirror_requested.connect(legacy_calls.append)

    widget.btn_mirror_h.click()
    assert h_calls == [1]
    assert legacy_calls == [1]

    widget.btn_mirror_v.click()
    assert v_calls == [1]


def test_frame_h_and_v_mirror_with_undo_redo(qapp):
    window = MainWindow()
    window._on_add_sprite()
    spr = window.project.sprites[0]
    window._on_sprite_selected(spr)

    original_pixels = [
        "11000000",
        "11110000",
        "00000000",
        "00000011",
    ]
    spr.height = 4
    spr.frames[0].pixels = list(original_pixels)

    # Test H Mirror (horizontal pixel flip per row)
    window._on_mirror_h_frame(0)
    expected_h = [
        "00000011",
        "00001111",
        "00000000",
        "11000000",
    ]
    assert spr.frames[0].pixels == expected_h

    # Undo restores original
    window._undo()
    assert spr.frames[0].pixels == original_pixels

    # Redo re-applies H mirror
    window._redo()
    assert spr.frames[0].pixels == expected_h

    # Reset back to original
    window._undo()
    assert spr.frames[0].pixels == original_pixels

    # Test V Mirror (vertical row order flip)
    window._on_mirror_v_frame(0)
    expected_v = [
        "00000011",
        "00000000",
        "11110000",
        "11000000",
    ]
    assert spr.frames[0].pixels == expected_v

    # Undo restores original
    window._undo()
    assert spr.frames[0].pixels == original_pixels

    # Redo re-applies V mirror
    window._redo()
    assert spr.frames[0].pixels == expected_v


