"""Tests for the per-scene background palette (upper/lower zone COLPF0..2 colours)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PIL import Image
from PySide6.QtWidgets import QApplication
import pytest

from scene_editor.commands import SetBackgroundPaletteCommand
from scene_editor.json_serializer import CorruptedFileError, SceneSerializer
from scene_editor.main_window import MainWindow
from scene_editor.scene_model import (
    BG_PALETTE_COLORS_PER_ZONE,
    BG_PALETTE_ZONES,
    DEFAULT_BACKGROUND_PALETTE_COLORS,
    BackgroundPalette,
    ModelValidationError,
    Scene,
)
from scripts.compile_scenes import (
    DEFAULT_BACKGROUND_PALETTE,
    TILESET_PALETTES,
    load_catalogues,
    parse_scene_background_palette,
    parse_scene_json,
)
from tests.scene_expectations import BG_ZONE_ORDER

_qapp = QApplication.instance() or QApplication([])

# Zone order used by the DLI: pas 0,1 = upper; pas 2,3,4 = lower; pas 5 = upper
ZONE_ORDER = BG_ZONE_ORDER


def _scene_dict(palette=None, elements=None, name: str = "Palette Scene") -> dict:
    data: dict = {
        "schema_version": 1,
        "scene": {"name": name, "width": 160, "height": 96},
        "elements": elements or [],
    }
    if palette is not None:
        data["background_palette"] = palette
    return data


def _trees_element(element_id: str = "element-001", y: int = 0, height: int = 44) -> dict:
    return {
        "id": element_id,
        "source": "tiles/trees.png",
        "source_rect": {"x": 0, "y": 0, "width": 80, "height": height},
        "position": {"x": 0, "y": y},
    }


def _write_scene(tmp_path: Path, data: dict, filename: str = "scene.json") -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _compile(tmp_path: Path, data: dict):
    scene_file = _write_scene(tmp_path, data)
    enemies, secrets = load_catalogues(
        Path("scenes/definitions.json"), Path("scenes/definitions.json")
    )
    return parse_scene_json(scene_file, enemies, secrets)


class TestBackgroundPaletteModel:
    def test_defaults_zones_and_sizes(self):
        palette = BackgroundPalette()
        assert tuple(palette.upper) == DEFAULT_BACKGROUND_PALETTE_COLORS
        assert tuple(palette.lower) == DEFAULT_BACKGROUND_PALETTE_COLORS
        assert BG_PALETTE_ZONES == ("upper", "lower")
        assert BG_PALETTE_COLORS_PER_ZONE == 3

    def test_clone_is_independent(self):
        palette = BackgroundPalette(upper=[0x94, 0xD6, 0xEA], lower=[0xC4, 0xC8, 0xDC])
        clone = palette.clone()
        clone.upper[0] = 0x10
        assert palette.upper[0] == 0x94

    def test_set_color_masks_lowest_bit(self):
        palette = BackgroundPalette()
        palette.set_color("upper", 1, 0xC5)
        assert palette.upper[1] == 0xC4

    def test_set_color_and_get_colors_reject_bad_arguments(self):
        palette = BackgroundPalette()
        with pytest.raises(ModelValidationError, match="colour index"):
            palette.set_color("upper", 3, 0x10)
        with pytest.raises(ModelValidationError, match="Unknown background palette zone"):
            palette.get_colors("middle")

    def test_validate_rejects_malformed_values(self):
        with pytest.raises(ModelValidationError, match="exactly 3 colours"):
            BackgroundPalette(upper=[0x10, 0x20], lower=[0x10, 0x20, 0x30]).validate()
        with pytest.raises(ModelValidationError, match="bit 0 clear"):
            BackgroundPalette(upper=[0x11, 0x20, 0x30], lower=[0x10, 0x20, 0x30]).validate()
        with pytest.raises(ModelValidationError, match="0x00-0xFF"):
            BackgroundPalette(upper=[0x100, 0x20, 0x30], lower=[0x10, 0x20, 0x30]).validate()
        with pytest.raises(ModelValidationError, match="must be an integer"):
            BackgroundPalette(upper=["$10", 0x20, 0x30], lower=[0x10, 0x20, 0x30]).validate()

    def test_from_dict_accepts_int_and_hex_forms(self):
        palette = BackgroundPalette.from_dict(
            {"upper": [148, "$D6", "0xEA"], "lower": ["C4", "C8", "DC"]}
        )
        assert palette.upper == [0x94, 0xD6, 0xEA]
        assert palette.lower == [0xC4, 0xC8, 0xDC]
        assert palette.to_dict() == {"upper": [148, 214, 234], "lower": [196, 200, 220]}

    @pytest.mark.parametrize(
        "bad_data, match",
        [
            ("nope", "must be a dictionary"),
            ({"upper": [0x10, 0x20, 0x30]}, "missing the 'lower' zone"),
            ({"upper": [0x10, 0x20], "lower": [0x10, 0x20, 0x30]}, "exactly 3 colours"),
            ({"upper": 0x10, "lower": [0x10, 0x20, 0x30]}, "must be a list of colours"),
            ({"upper": [0x100, 0x20, 0x30], "lower": [0x10, 0x20, 0x30]}, "0x00-0xFF"),
            ({"upper": ["zz", 0x20, 0x30], "lower": [0x10, 0x20, 0x30]}, "not a valid Atari colour"),
        ],
    )
    def test_from_dict_rejects_malformed(self, bad_data, match):
        with pytest.raises(ModelValidationError, match=match):
            BackgroundPalette.from_dict(bad_data)

    def test_scene_defaults_and_validation(self):
        scene = Scene(name="palette scene", width=160, height=96)
        assert scene.background_palette is None
        assert scene.get_background_colors("upper") == list(DEFAULT_BACKGROUND_PALETTE_COLORS)
        assert scene.effective_background_palette().lower == list(DEFAULT_BACKGROUND_PALETTE_COLORS)

        scene.background_palette = BackgroundPalette(
            upper=[0x94, 0xD6, 0xEA], lower=[0xC4, 0xC8, 0xDC]
        )
        scene.validate()
        assert scene.get_background_colors("upper") == [0x94, 0xD6, 0xEA]

        scene.background_palette.upper[0] = 0x11
        with pytest.raises(ModelValidationError, match="bit 0 clear"):
            scene.validate()


class TestBackgroundPaletteSerialization:
    def test_roundtrip_stores_explicit_palette(self, tmp_path: Path):
        scene = Scene(name="pal", width=160, height=96)
        scene.background_palette = BackgroundPalette(
            upper=[0x94, 0xD6, 0xEA], lower=[0xC4, 0xC8, 0xDC]
        )

        data = SceneSerializer.to_dict(scene)
        assert data["background_palette"] == {"upper": [148, 214, 234], "lower": [196, 200, 220]}

        path = tmp_path / "palette_scene.json"
        SceneSerializer.save_to_file(scene, path)
        loaded = SceneSerializer.load_from_file(path)
        assert loaded.background_palette.to_dict() == data["background_palette"]

    def test_scene_without_palette_keeps_the_key_absent(self):
        scene = Scene(name="legacy", width=160, height=96)
        data = SceneSerializer.to_dict(scene)
        assert "background_palette" not in data
        assert SceneSerializer.from_dict(data).background_palette is None

    def test_nested_location_and_hex_strings_are_accepted(self):
        data = {
            "schema_version": 1,
            "scene": {
                "name": "nested",
                "width": 160,
                "height": 96,
                "background_palette": {"upper": ["$94", "$D6", "$EA"], "lower": ["$C4", "$C8", "$DC"]},
            },
            "elements": [],
        }
        scene = SceneSerializer.from_dict(data)
        assert scene.background_palette.to_dict() == {
            "upper": [148, 214, 234],
            "lower": [196, 200, 220],
        }

    def test_odd_values_are_masked_on_load(self):
        scene = SceneSerializer.from_dict(
            _scene_dict({"upper": [0xC5, 0xD7, 0xEB], "lower": [0xC4, 0xC8, 0xDC]})
        )
        assert scene.background_palette.upper == [0xC4, 0xD6, 0xEA]

    @pytest.mark.parametrize(
        "palette",
        [
            {"upper": [0x10, 0x20], "lower": [0x10, 0x20, 0x30]},
            {"upper": [0x100, 0x20, 0x30], "lower": [0x10, 0x20, 0x30]},
            {"upper": [0x10, 0x20, 0x30]},
            "nope",
        ],
    )
    def test_malformed_palette_is_reported_as_corrupted(self, palette):
        with pytest.raises(CorruptedFileError, match="background_palette"):
            SceneSerializer.from_dict(_scene_dict(palette))


class TestBackgroundPaletteCommand:
    def test_set_and_clear_with_undo(self):
        scene = Scene(name="cmd", width=160, height=96)
        new_palette = BackgroundPalette(upper=[0x94, 0xD6, 0xEA], lower=[0xC4, 0xC8, 0xDC])
        calls: list[int] = []

        set_cmd = SetBackgroundPaletteCommand(
            scene, new_palette, callback=lambda: calls.append(1)
        )
        set_cmd.redo()
        assert scene.background_palette.to_dict() == new_palette.to_dict()
        assert set_cmd.text() == "Set scene background palette"

        set_cmd.undo()
        assert scene.background_palette is None
        assert len(calls) == 2

        # Clearing a stored palette restores it on undo
        scene.background_palette = new_palette.clone()
        clear_cmd = SetBackgroundPaletteCommand(scene, None)
        assert clear_cmd.text() == "Clear scene background palette"
        clear_cmd.redo()
        assert scene.background_palette is None
        clear_cmd.undo()
        assert scene.background_palette.to_dict() == new_palette.to_dict()


class TestBackgroundPaletteCompiler:
    def test_editor_and_compiler_default_agree(self):
        assert tuple(DEFAULT_BACKGROUND_PALETTE) == DEFAULT_BACKGROUND_PALETTE_COLORS

    def test_absent_palette_parses_to_none(self):
        assert parse_scene_background_palette({"scene": {"name": "x"}}, "x") is None
        assert (
            parse_scene_background_palette(
                {"scene": {"name": "x"}, "background_palette": None}, "x"
            )
            is None
        )

    def test_root_and_nested_locations_are_accepted(self):
        nested = {
            "scene": {
                "name": "x",
                "background_palette": {"upper": ["$94", "$D6", "$EA"], "lower": [196, 200, 220]},
            }
        }
        assert parse_scene_background_palette(nested, "x") == {
            "upper": (0x94, 0xD6, 0xEA),
            "lower": (0xC4, 0xC8, 0xDC),
        }

    @pytest.mark.parametrize(
        "bad_palette, match",
        [
            ("nope", "must be an object"),
            ({"upper": [0x10, 0x20, 0x30]}, "missing the 'lower' zone"),
            ({"upper": [0x10, 0x20], "lower": [0x10, 0x20, 0x30]}, "exactly 3 Atari colours"),
            ({"upper": [0x11, 0x20, 0x30], "lower": [0x10, 0x20, 0x30]}, "bit 0 set"),
            ({"upper": [0x100, 0x20, 0x30], "lower": [0x10, 0x20, 0x30]}, "outside the 0x00-0xFF"),
            ({"upper": ["zz", 0x20, 0x30], "lower": [0x10, 0x20, 0x30]}, "not a valid Atari colour"),
        ],
    )
    def test_malformed_palette_is_rejected(self, bad_palette, match):
        with pytest.raises(ValueError, match=match):
            parse_scene_background_palette({"background_palette": bad_palette}, "Scene X")

    def test_explicit_palette_drives_the_dli_tables(self, tmp_path: Path):
        compiled = _compile(
            tmp_path,
            _scene_dict(
                {"upper": [0x94, 0xD6, 0xEA], "lower": [0x32, 0x26, 0x1C]},
                [_trees_element()],
            ),
        )
        dli = compiled.dli_data
        upper = (0x94, 0xD6, 0xEA)
        lower = (0x32, 0x26, 0x1C)
        for channel_idx, channel in enumerate(("bg_colpf0", "bg_colpf1", "bg_colpf2")):
            expected = [
                upper[channel_idx] if z == "upper" else lower[channel_idx] for z in ZONE_ORDER
            ]
            assert getattr(dli, channel) == expected
        # Zone 0 (the first playfield scanline) starts in the upper zone
        assert (dli.z0_colpf0, dli.z0_colpf1, dli.z0_colpf2) == upper

    def test_tileset_derivation_remains_the_fallback(self, tmp_path: Path):
        compiled = _compile(tmp_path, _scene_dict(None, [_trees_element()]))
        dli = compiled.dli_data
        palette = TILESET_PALETTES[compiled.elements[0].tileset_id]
        for channel_idx, channel in enumerate(("bg_colpf0", "bg_colpf1", "bg_colpf2")):
            assert getattr(dli, channel) == [palette[channel_idx]] * 6

    def test_game_scenes_store_the_palette_their_dli_uses(self):
        """Every game scene must store the palette the compiled DLI tables actually use."""
        manifest = json.loads(Path("scenes/scenes.json").read_text(encoding="utf-8"))
        enemies, secrets = load_catalogues(
            Path("scenes/definitions.json"), Path("scenes/definitions.json")
        )

        for fname in manifest["scenes"]:
            scene_path = Path("scenes") / fname
            raw = json.loads(scene_path.read_text(encoding="utf-8"))
            palette = raw.get("background_palette")
            assert palette is not None, f"{fname} must store an explicit background_palette"

            dli = parse_scene_json(scene_path, enemies, secrets).dli_data
            for channel_idx, channel in enumerate(("bg_colpf0", "bg_colpf1", "bg_colpf2")):
                expected = [palette[zone][channel_idx] for zone in ZONE_ORDER]
                assert getattr(dli, channel) == expected, (
                    f"{fname}: {channel} does not match the stored background_palette"
                )


class TestBackgroundPaletteGui:
    @pytest.fixture
    def test_app(self, tmp_path: Path):
        tiles_dir = tmp_path / "tiles"
        tiles_dir.mkdir()
        Image.new("RGBA", (64, 32), color=(100, 150, 200, 255)).save(tiles_dir / "grass.png")
        return MainWindow(base_dir=tmp_path), tmp_path

    def test_tab_defaults_and_status(self, test_app):
        window, _tmp_path = test_app
        assert window.prop_tabs.tabText(4) == "Background Colors"

        defaults = list(DEFAULT_BACKGROUND_PALETTE_COLORS)
        for zone in BG_PALETTE_ZONES:
            assert [s.value() for s in window.bg_palette_spins[zone]] == defaults
            assert [lbl.text() for lbl in window.bg_palette_hex_lbls[zone]] == ["$C4", "$C8", "$DC"]

        assert window.scene_model.background_palette is None
        assert "No palette stored yet" in window.bg_palette_status_lbl.text()
        assert window.btn_clear_bg_palette.isEnabled() is False

    def test_spinbox_stores_palette_through_undoable_command(self, test_app):
        window, _tmp_path = test_app

        window.bg_palette_spins["upper"][0].setValue(0x94)
        assert window.scene_model.background_palette is not None
        assert window.scene_model.background_palette.upper[0] == 0x94
        assert window.bg_palette_hex_lbls["upper"][0].text() == "$94"
        assert window.undo_stack.count() == 1
        assert "Palette stored in this scene" in window.bg_palette_status_lbl.text()
        assert window.btn_clear_bg_palette.isEnabled() is True

        # Odd values are snapped to even (GTIA ignores bit 0)
        window.bg_palette_spins["lower"][2].setValue(0x1F)
        assert window.bg_palette_spins["lower"][2].value() == 0x1E
        assert window.scene_model.background_palette.lower[2] == 0x1E

        # Undo restores the previous palette and the panel follows
        window.undo_stack.undo()
        assert window.scene_model.background_palette.lower[2] == DEFAULT_BACKGROUND_PALETTE_COLORS[2]
        assert window.bg_palette_spins["lower"][2].value() == DEFAULT_BACKGROUND_PALETTE_COLORS[2]
        window.undo_stack.undo()
        assert window.scene_model.background_palette is None
        assert "No palette stored yet" in window.bg_palette_status_lbl.text()

    def test_palette_picker_sets_colour(self, test_app, monkeypatch):
        window, _tmp_path = test_app
        window.bg_palette_spins["upper"][0].setValue(0x94)  # create an explicit palette

        monkeypatch.setattr(
            "scene_editor.main_window.AtariColorPickerDialog.get_color",
            classmethod(lambda cls, parent=None, initial_color=0: (0x32, True)),
        )
        window.bg_palette_swatches["upper"][1].click()
        assert window.scene_model.background_palette.upper == [0x94, 0x32, 0xDC]
        assert window.bg_palette_hex_lbls["upper"][1].text() == "$32"

        # Cancelling the dialog must not change anything
        monkeypatch.setattr(
            "scene_editor.main_window.AtariColorPickerDialog.get_color",
            classmethod(lambda cls, parent=None, initial_color=0: (initial_color, False)),
        )
        undo_count = window.undo_stack.count()
        window.bg_palette_swatches["lower"][0].click()
        assert window.undo_stack.count() == undo_count

    def test_clear_button_removes_palette(self, test_app):
        window, _tmp_path = test_app
        window.bg_palette_spins["lower"][1].setValue(0x26)
        assert window.scene_model.background_palette is not None

        window.btn_clear_bg_palette.click()
        assert window.scene_model.background_palette is None
        assert window.btn_clear_bg_palette.isEnabled() is False

        window.undo_stack.undo()
        assert window.scene_model.background_palette.lower[1] == 0x26

    def test_saved_and_reopened_scene_keeps_the_palette(self, test_app):
        window, tmp_path = test_app
        window.bg_palette_spins["upper"][0].setValue(0x94)
        window.bg_palette_spins["lower"][2].setValue(0x1C)

        target = tmp_path / "palette_scene.json"
        window.current_file_path = target
        assert window.save_scene() is True

        window.new_scene(prompt_dialog=False)
        assert window.scene_model.background_palette is None
        assert [s.value() for s in window.bg_palette_spins["upper"]] == list(
            DEFAULT_BACKGROUND_PALETTE_COLORS
        )

        window.open_scene(target)
        assert window.scene_model.background_palette.to_dict() == {
            "upper": [0x94, 0xC8, 0xDC],
            "lower": [0xC4, 0xC8, 0x1C],
        }
        assert window.bg_palette_spins["upper"][0].value() == 0x94
        assert window.bg_palette_spins["lower"][2].value() == 0x1C
        assert "Palette stored in this scene" in window.bg_palette_status_lbl.text()
