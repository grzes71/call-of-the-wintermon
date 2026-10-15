"""Comprehensive tests for Enemy and Secret Catalogues and Scene Object integration."""

import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from scene_editor.catalogue_dialog import CataloguePathsDialog, CataloguesDialog
from scene_editor.catalogue_model import (
    CatalogDefinition,
    CatalogueValidationError,
    CorruptedCatalogueFileError,
    DuplicateDefinitionIdError,
    EnemyDefinition,
    ProjectCatalogues,
    SecretDefinition,
)
from scene_editor.json_serializer import SceneSerializer
from scene_editor.main_window import MainWindow
from scene_editor.scene_items import SceneObjectGraphicsItem
from scene_editor.scene_model import (
    OBJECT_TYPE_ENEMY,
    OBJECT_TYPE_SECRET,
    PLATFORM_HEIGHT,
    PLATFORM_TYPE_SPRITE,
    PlatformElement,
    Position,
    Rect,
    Scene,
    SceneObjectElement,
)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# =============================================================================
# 1. Models & Validation Tests
# =============================================================================

class TestCatalogueModelValidation:
    def test_valid_enemy_definition_minimal(self):
        enemy = EnemyDefinition(id=1, name="Orc Warrior")
        enemy.validate()
        assert enemy.id == 1
        assert enemy.name == "Orc Warrior"
        assert enemy.rgb_color is None
        assert enemy.atari_color is None
        assert enemy.blink is False

    def test_valid_secret_definition_full(self):
        secret = SecretDefinition(
            id=255,
            name="Golden Chalice",
            rgb_color=(255, 215, 0),
            atari_color=0x28,  # Atari gold / yellow
            blink=True,
        )
        secret.validate()
        assert secret.id == 255
        assert secret.rgb_color == (255, 215, 0)
        assert secret.atari_color == 40
        assert secret.blink is True

    def test_valid_numeric_string_id_converted_to_int(self):
        enemy = EnemyDefinition(id="42", name="Skeleton")
        enemy.validate()
        assert enemy.id == 42
        assert isinstance(enemy.id, int)

    @pytest.mark.parametrize(
        "invalid_id",
        [0, -1, 256, 1000, "", "   ", None, "orc_warrior", True, False, 12.5],
    )
    def test_rejects_invalid_id(self, invalid_id):
        with pytest.raises(CatalogueValidationError, match="Definition 'id' must be an integer between 1 and 255"):
            defn = EnemyDefinition(id=invalid_id, name="Valid Name")
            defn.validate()

    @pytest.mark.parametrize(
        "invalid_name",
        ["", "   ", None],
    )
    def test_rejects_empty_name(self, invalid_name):
        with pytest.raises(CatalogueValidationError, match="Definition 'name' must be a non-empty string"):
            defn = SecretDefinition(id=1, name=invalid_name)
            defn.validate()

    @pytest.mark.parametrize(
        "invalid_rgb",
        [
            (256, 0, 0),
            (-1, 50, 50),
            (0, 0),
            (0, 0, 0, 255),
            ("255", 0, 0),
            (100.5, 0, 0),
        ],
    )
    def test_rejects_invalid_rgb(self, invalid_rgb):
        with pytest.raises(CatalogueValidationError, match="rgb_color"):
            defn = EnemyDefinition(id=1, name="Enemy", rgb_color=invalid_rgb)
            defn.validate()

    @pytest.mark.parametrize(
        "invalid_atari_color",
        [-1, 256, 1000, 12.5],
    )
    def test_rejects_invalid_atari_color(self, invalid_atari_color):
        with pytest.raises(CatalogueValidationError, match="atari_color"):
            defn = SecretDefinition(id=1, name="Secret", atari_color=invalid_atari_color)
            defn.validate()

    def test_serialization_roundtrip_enemy(self):
        defn = EnemyDefinition(
            id=10,
            name="Skeleton Archer",
            rgb_color=(220, 220, 220),
            atari_color=0x0E,
            blink=False,
        )
        data = defn.to_dict()
        assert data["id"] == 10
        assert data["name"] == "Skeleton Archer"
        assert data["rgb_color"] == [220, 220, 220]
        assert data["atari_color"] == 14
        assert data["blink"] is False

        restored = EnemyDefinition.from_dict(data)
        assert restored == defn
        assert restored.id == 10

    def test_serialization_roundtrip_omits_none_defaults(self):
        defn = SecretDefinition(id=5, name="Rune Stone")
        data = defn.to_dict()
        assert data["id"] == 5
        assert "rgb_color" not in data or data["rgb_color"] is None
        assert "atari_color" not in data or data["atari_color"] is None
        assert data.get("blink", False) is False

        restored = SecretDefinition.from_dict(data)
        assert restored.id == 5
        assert restored.atari_color is None
        assert restored.rgb_color is None


# =============================================================================
# 2. Project Catalogues CRUD & Uniqueness
# =============================================================================

class TestProjectCataloguesCRUD:
    def test_add_and_get_definitions(self):
        cats = ProjectCatalogues()
        e1 = EnemyDefinition(id=1, name="Cave Bat", rgb_color=(100, 50, 150))
        s1 = SecretDefinition(id=2, name="Red Ruby", rgb_color=(255, 0, 0))

        cats.add_enemy(e1)
        cats.add_secret(s1)

        assert cats.get_enemy(1) == e1
        assert cats.get_enemy("1") == e1
        assert cats.get_secret(2) == s1
        assert cats.get_secret("2") == s1
        assert cats.get_definition("enemy", 1) == e1
        assert cats.get_definition("enemy", "1") == e1
        assert cats.get_definition("secret", 2) == s1
        assert cats.get_definition("secret", "2") == s1

    def test_enforces_id_uniqueness_within_catalogue(self):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=10, name="Green Slime"))

        with pytest.raises(DuplicateDefinitionIdError, match="Enemy with ID '10' already exists"):
            cats.add_enemy(EnemyDefinition(id=10, name="Blue Slime"))

    def test_same_id_allowed_across_different_catalogues(self):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=1, name="Mimic Monster"))
        cats.add_secret(SecretDefinition(id=1, name="Mimic Chest"))

        assert cats.get_enemy(1).name == "Mimic Monster"
        assert cats.get_secret(1).name == "Mimic Chest"

    def test_update_definition(self):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=3, name="Goblin"))

        updated = EnemyDefinition(id=3, name="Goblin Shaman", atari_color=0x44, blink=True)
        cats.update_enemy(3, updated)

        stored = cats.get_enemy(3)
        assert stored.name == "Goblin Shaman"
        assert stored.atari_color == 0x44
        assert stored.blink is True

    def test_remove_definition(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=7, name="Iron Key"))
        removed = cats.remove_secret(7)
        assert removed.id == 7
        assert cats.get_secret(7) is None

        with pytest.raises(KeyError):
            cats.remove_secret(7)


# =============================================================================
# 3. File Persistence & Corrupted File Protection
# =============================================================================

class TestCatalogueFilePersistence:
    def test_save_and_load_from_dir(self, tmp_path: Path):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=1, name="Dire Wolf", rgb_color=(80, 80, 80), atari_color=0x06))
        cats.add_secret(SecretDefinition(id=2, name="Blue Diamond", rgb_color=(0, 200, 255), blink=True))

        cats.save_to_dir(tmp_path)

        enemies_file = tmp_path / "enemies.json"
        secrets_file = tmp_path / "secrets.json"
        assert enemies_file.is_file()
        assert secrets_file.is_file()

        # Check enemies.json structure
        with open(enemies_file, "r", encoding="utf-8") as f:
            e_data = json.load(f)
        assert "enemies" in e_data
        assert len(e_data["enemies"]) == 1
        assert e_data["enemies"][0]["id"] == 1

        # Check secrets.json structure
        with open(secrets_file, "r", encoding="utf-8") as f:
            s_data = json.load(f)
        assert "secrets" in s_data
        assert len(s_data["secrets"]) == 1
        assert s_data["secrets"][0]["id"] == 2

        # Load back in a fresh instance
        loaded = ProjectCatalogues.load_from_dir(tmp_path)
        assert len(loaded.enemies) == 1
        assert len(loaded.secrets) == 1
        assert loaded.get_enemy(1).name == "Dire Wolf"
        assert loaded.get_secret(2).blink is True

    def test_load_empty_project_without_files(self, tmp_path: Path):
        loaded = ProjectCatalogues.load_from_dir(tmp_path)
        assert len(loaded.enemies) == 0
        assert len(loaded.secrets) == 0

    def test_corrupted_json_raises_error_and_preserves_file(self, tmp_path: Path):
        enemies_file = tmp_path / "enemies.json"
        corrupt_content = '{"enemies": [ { "id": 1, '  # broken JSON
        enemies_file.write_text(corrupt_content, encoding="utf-8")

        with pytest.raises(CorruptedCatalogueFileError, match="Invalid JSON"):
            ProjectCatalogues.load_from_dir(tmp_path)

        # Ensure corrupted file was NOT silently overwritten or deleted
        assert enemies_file.read_text(encoding="utf-8") == corrupt_content

    def test_rename_definition_preserves_id_and_instance_bindings(self, tmp_path: Path):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=5, name="Giant Spider"))
        cats.save_to_dir(tmp_path)

        # Scene object referencing 5
        scene = Scene(name="dungeon", width=160, height=192)
        plat = PlatformElement(id="plat1", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        scene.add_platform(plat)
        obj = SceneObjectElement(id="enemy-001", type=OBJECT_TYPE_ENEMY, definition_id=5, platform_id="plat1", x=10)
        scene.add_object(obj)

        # Rename definition in catalogue
        updated = EnemyDefinition(id=5, name="Venomous Broodmother")
        cats.update_enemy(5, updated)
        cats.save_to_dir(tmp_path)

        # Instance on scene still points to 5, but name resolves to 'Venomous Broodmother'
        ref_def = cats.get_definition(obj.type, obj.definition_id)
        assert ref_def is not None
        assert ref_def.name == "Venomous Broodmother"


# =============================================================================
# 4. Scene Objects Separation & Serialization
# =============================================================================

class TestSceneObjectsAndCataloguesSeparation:
    def test_scene_json_does_not_duplicate_catalogue_definitions(self, tmp_path: Path):
        scene = Scene(name="cave", width=160, height=192)
        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 40))
        scene.add_platform(plat)

        obj = SceneObjectElement(
            id="secret-001",
            type=OBJECT_TYPE_SECRET,
            definition_id=12,
            platform_id="p1",
            x=15,
        )
        scene.add_object(obj)

        scene_path = tmp_path / "cave.json"
        SceneSerializer.save_to_file(scene, scene_path, base_dir=tmp_path)

        with open(scene_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Scene JSON must contain object instance reference, NOT definitions table
        assert "enemies" not in data
        assert "secrets" not in data
        obj_data = data["objects"][0]
        assert obj_data["id"] == "secret-001"
        assert obj_data["type"] == "secret"
        assert obj_data["definition_id"] == 12
        assert "rgb_color" not in obj_data
        assert "atari_color" not in obj_data

    def test_scene_load_with_missing_definition_does_not_crash(self, tmp_path: Path):
        scene_data = {
            "schema_version": 1,
            "scene": {
                "name": "orphan_scene",
                "width": 160,
                "height": 192,
            },
            "platforms": [
                {"id": "p1", "type": "sprite", "width": 32, "position": {"x": 10, "y": 40}}
            ],
            "objects": [
                {
                    "id": "e1",
                    "type": "enemy",
                    "definition_id": 99,
                    "platform_id": "p1",
                    "x": 15,
                }
            ],
        }
        scene_path = tmp_path / "orphan_scene.json"
        scene_path.write_text(json.dumps(scene_data), encoding="utf-8")

        loaded = SceneSerializer.load_from_file(scene_path, base_dir=tmp_path, validate_source_exists=False)
        assert len(loaded.objects) == 1
        assert loaded.objects[0].definition_id == 99


# =============================================================================
# 5. Visual Square Rendering & Fallback Colors
# =============================================================================

class TestSquareRenderingAndFallbackColors:
    def test_rendering_uses_rgb_color_when_provided(self):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=1, name="Ogre", rgb_color=(50, 150, 50)))

        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        obj = SceneObjectElement(id="ogre-1", type=OBJECT_TYPE_ENEMY, definition_id=1, platform_id="p1", x=10)

        item = SceneObjectGraphicsItem(obj, plat, None, catalogues=cats)
        color = item._resolve_color()
        assert color.red() == 50
        assert color.green() == 150
        assert color.blue() == 50

    def test_rendering_uses_fallback_colors_when_no_rgb(self):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=1, name="Ghost", rgb_color=None))
        cats.add_secret(SecretDefinition(id=2, name="Silver Coin", rgb_color=None))

        plat = PlatformElement(id="p1", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24))
        obj_enemy = SceneObjectElement(id="ghost-1", type=OBJECT_TYPE_ENEMY, definition_id=1, platform_id="p1", x=10)
        obj_secret = SceneObjectElement(id="coin-1", type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="p1", x=20)

        item_enemy = SceneObjectGraphicsItem(obj_enemy, plat, None, catalogues=cats)
        item_secret = SceneObjectGraphicsItem(obj_secret, plat, None, catalogues=cats)

        # Default enemy fallback is crimson (#D32F2F -> R:211, G:47, B:47)
        color_e = item_enemy._resolve_color()
        assert color_e.red() == 211
        assert color_e.green() == 47

        # Default secret fallback is amber (#FFA000 -> R:255, G:160, B:0)
        color_s = item_secret._resolve_color()
        assert color_s.red() == 255
        assert color_s.green() == 160


# =============================================================================
# 6. GUI Integration: Catalogues Protection & Flow
# =============================================================================

class TestGUIIntegrationCatalogues:
    @pytest.fixture(autouse=True)
    def suppress_message_boxes(self, monkeypatch):
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    def test_gui_dialog_spinbox_range_is_1_to_255(self, qapp, tmp_path: Path):
        cats = ProjectCatalogues()
        dlg = CataloguesDialog(cats, parent=None)
        assert dlg.enemy_id_spin.minimum() == 1
        assert dlg.enemy_id_spin.maximum() == 255
        assert dlg.secret_id_spin.minimum() == 1
        assert dlg.secret_id_spin.maximum() == 255

    def test_gui_blocks_adding_object_when_catalogue_empty(self, qapp, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        # Clear catalogues
        window.catalogues.enemies.clear()
        window.catalogues.secrets.clear()
        window._refresh_object_creator_definitions()

        # Add platform
        window._on_add_platform_clicked()
        assert len(window.scene_model.platforms) == 1

        # Attempt to add object
        window._on_add_object_clicked()

        # Must NOT add object when catalogue is empty
        assert len(window.scene_model.objects) == 0

    def test_gui_adds_object_referencing_selected_definition(self, qapp, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        window.catalogues.add_enemy(EnemyDefinition(id=4, name="Cave Troll", rgb_color=(70, 130, 180)))
        window._refresh_object_creator_definitions()

        window._on_add_platform_clicked()
        plat_id = window.scene_model.platforms[0].id

        window.new_obj_platform_combo.setCurrentIndex(0)
        window.new_obj_x_spin.setValue(20)
        window._on_add_object_clicked()

        assert len(window.scene_model.objects) == 1
        obj = window.scene_model.objects[0]
        assert obj.type == OBJECT_TYPE_ENEMY
        assert obj.definition_id == 4
        assert obj.platform_id == plat_id

    def test_dialog_protects_definition_currently_used_on_scene(self, qapp, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        window.catalogues.add_enemy(EnemyDefinition(id=8, name="Final Boss"))
        window._refresh_object_creator_definitions()

        window._on_add_platform_clicked()
        plat_id = window.scene_model.platforms[0].id
        obj = SceneObjectElement(id="e1", type=OBJECT_TYPE_ENEMY, definition_id=8, platform_id=plat_id, x=20)
        window.scene_model.add_object(obj)

        dlg = CataloguesDialog(window.catalogues, scene=window.scene_model, parent=window)
        dlg.enemy_list.setCurrentRow(0)
        # Try to delete '8'
        dlg._on_delete_enemy_clicked()

        # Deletion must be blocked because '8' is used on the scene
        assert 8 in window.catalogues.enemies

    def test_dialog_button_says_update_entry_when_editing(self, qapp):
        cats = ProjectCatalogues()
        cats.add_enemy(EnemyDefinition(id=1, name="Dragon"))
        cats.add_secret(SecretDefinition(id=2, name="Chalice"))

        dlg = CataloguesDialog(cats, parent=None)
        # On initialization with existing entries, first entry is selected: button says Update Entry
        assert dlg.enemy_btn_save.text() == "Update Entry"
        assert dlg.secret_btn_save.text() == "Update Entry"

        # Click new: button changes to Add Entry
        dlg._on_new_enemy_clicked()
        assert dlg.enemy_btn_save.text() == "Add Entry"

        dlg._on_new_secret_clicked()
        assert dlg.secret_btn_save.text() == "Add Entry"

        # Re-select existing: button changes back to Update Entry
        dlg.enemy_list.setCurrentRow(0)
        assert dlg.enemy_btn_save.text() == "Update Entry"

        dlg.secret_list.setCurrentRow(0)
        assert dlg.secret_btn_save.text() == "Update Entry"

    def test_menu_contains_catalogue_actions(self, qapp, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        menubar = window.menuBar()

        # Check File menu: should NOT contain catalogue actions (moved to dedicated Catalogues menu)
        file_actions = [a.text().replace("&", "") for a in menubar.actions()[0].menu().actions()]
        assert not any("Load Catalogues" in a for a in file_actions)
        assert not any("Save Catalogues" in a for a in file_actions)

        # Check top-level Catalogues menu
        menu_titles = [a.text().replace("&", "") for a in menubar.actions()]
        assert any("Catalogues" in t for t in menu_titles)
        cat_menu_action = next(a for a in menubar.actions() if "Catalogues" in a.text())
        cat_actions = [a.text().replace("&", "") for a in cat_menu_action.menu().actions()]
        assert any("Manage Catalogues" in a for a in cat_actions)
        assert any("Configure Catalogue Paths" in a for a in cat_actions)
        assert any("Load Catalogues" in a for a in cat_actions)
        assert any("Save Catalogues (JSON)" in a for a in cat_actions)
        assert any("Save Catalogues As" in a for a in cat_actions)

    def test_main_window_save_and_load_catalogues_json(self, qapp, tmp_path: Path):
        window = MainWindow(base_dir=tmp_path)
        window.catalogues.add_enemy(EnemyDefinition(id=15, name="Hydra", atari_color=0x38))
        window.catalogues.add_secret(SecretDefinition(id=20, name="Relic", blink=True))

        # Test save
        success = window.save_catalogues_to_json()
        assert success is True
        assert (tmp_path / "enemies.json").is_file()
        assert (tmp_path / "secrets.json").is_file()

        # Create a fresh window and load from the saved JSON
        window2 = MainWindow(base_dir=tmp_path)
        window2.catalogues.enemies.clear()
        window2.catalogues.secrets.clear()

        loaded_success = window2.load_catalogues_from_json(tmp_path / "enemies.json")
        assert loaded_success is True
        assert 15 in window2.catalogues.enemies
        assert window2.catalogues.enemies[15].name == "Hydra"

    def test_custom_catalogue_paths(self, tmp_path: Path):
        cats = ProjectCatalogues()
        custom_enemies = tmp_path / "custom_subdir" / "my_enemies.json"
        custom_secrets = tmp_path / "custom_subdir" / "my_secrets.json"

        cats.set_paths(custom_enemies, custom_secrets)
        eff_e, eff_s = cats.get_effective_paths(tmp_path)
        assert eff_e == custom_enemies
        assert eff_s == custom_secrets

        cats.add_enemy(EnemyDefinition(id=33, name="Specter", blink=True))
        cats.add_secret(SecretDefinition(id=44, name="Gem", rgb_color=(10, 20, 30)))
        cats.save_to_dir()

        assert custom_enemies.is_file()
        assert custom_secrets.is_file()

        # Load back from custom paths
        loaded = ProjectCatalogues.load_from_paths(custom_enemies, custom_secrets)
        assert 33 in loaded.enemies
        assert loaded.enemies[33].name == "Specter"
        assert 44 in loaded.secrets
        assert loaded.secrets[44].name == "Gem"

    def test_catalogue_paths_dialog(self, qapp, tmp_path: Path):
        dialog = CataloguePathsDialog(base_dir=tmp_path)
        default_e, default_s = ProjectCatalogues.find_catalogue_paths(tmp_path)

        assert Path(dialog.edit_enemies.text()) == default_e
        assert Path(dialog.edit_secrets.text()) == default_s

        custom_e = tmp_path / "test_enemies.json"
        custom_s = tmp_path / "test_secrets.json"
        dialog.edit_enemies.setText(str(custom_e))
        dialog.edit_secrets.setText(str(custom_s))

        e_res, s_res, reload_now = dialog.get_paths()
        assert e_res == custom_e
        assert s_res == custom_s
        assert reload_now is True

        dialog._reset_defaults()
        assert Path(dialog.edit_enemies.text()) == default_e
        assert Path(dialog.edit_secrets.text()) == default_s


# =============================================================================
# 6. Secret Linear Dependency Chain Tests
# =============================================================================

class TestSecretLinearDependencyChain:
    """Tests verifying secret linear dependency chains, stage resolution, and validation."""

    def test_secret_definition_with_dependency_valid(self):
        s1 = SecretDefinition(id=1, name="Keys", dependency=None)
        s1.validate()
        assert s1.dependency is None

        s2 = SecretDefinition(id=2, name="CDs", dependency=1)
        s2.validate()
        assert s2.dependency == 1

        s3 = SecretDefinition(id=3, name="Artifacts", dependency="2")
        s3.validate()
        assert s3.dependency == 2

    def test_secret_definition_self_dependency_rejected(self):
        with pytest.raises(CatalogueValidationError, match="cannot depend on itself"):
            s = SecretDefinition(id=10, name="Ouroboros", dependency=10)
            s.validate()

    @pytest.mark.parametrize("invalid_dep", [0, -1, 256, 1000, True, False, 12.5, "invalid"])
    def test_secret_definition_invalid_dependency_type_rejected(self, invalid_dep):
        with pytest.raises(CatalogueValidationError, match="dependency"):
            s = SecretDefinition(id=10, name="Item", dependency=invalid_dep)
            s.validate()

    def test_secret_serialization_roundtrip_with_dependency(self):
        s = SecretDefinition(
            id=42,
            name="Ancient Relic",
            rgb_color=(200, 150, 50),
            atari_color=0x34,
            blink=True,
            dependency=7,
        )
        data = s.to_dict()
        assert data["dependency"] == 7

        restored = SecretDefinition.from_dict(data)
        assert restored.dependency == 7
        assert restored == s

    def test_secret_serialization_backward_compatibility_no_dependency_key(self):
        legacy_data = {
            "id": 1,
            "name": "Legacy Key",
            "blink": False,
        }
        restored = SecretDefinition.from_dict(legacy_data)
        assert restored.dependency is None
        assert restored.id == 1

    def test_linear_chain_stages_calculation(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))
        cats.add_secret(SecretDefinition(id=3, name="Artifacts", dependency=2))

        assert cats.get_secret_stage(1) == 1
        assert cats.get_secret_stage(2) == 2
        assert cats.get_secret_stage(3) == 3
        assert cats.get_all_secret_stages() == {1: 1, 2: 2, 3: 3}

    def test_linear_chain_rejects_missing_dependency(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))

        with pytest.raises(CatalogueValidationError, match="depends on non-existent secret ID"):
            cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=99))

    def test_linear_chain_rejects_branching(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))

        # Trying to add another secret that also depends on Keys (id=1) creates branching!
        with pytest.raises(CatalogueValidationError, match="Branching is not allowed"):
            cats.add_secret(SecretDefinition(id=3, name="Artifacts", dependency=1))

    def test_linear_chain_rejects_cycles(self):
        cats = ProjectCatalogues()
        s1 = SecretDefinition(id=1, name="Secret 1", dependency=None)
        s2 = SecretDefinition(id=2, name="Secret 2", dependency=1)
        cats.add_secret(s1)
        cats.add_secret(s2)

        # Trying to update s1 to depend on s2 creates cycle 1 <-> 2
        with pytest.raises(CatalogueValidationError, match="Cyclic dependency detected"):
            s1_cyclic = SecretDefinition(id=1, name="Secret 1", dependency=2)
            cats.update_secret(1, s1_cyclic)

    def test_linear_chain_rejects_multiple_independent_chains(self):
        cats = ProjectCatalogues()
        # Chain 1: 1 -> 2
        cats.add_secret(SecretDefinition(id=1, name="Chain1-A", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="Chain1-B", dependency=1))

        # Root for Chain 2: 3 (currently Stage 1)
        cats.add_secret(SecretDefinition(id=3, name="Chain2-A", dependency=None))

        # Trying to add 4 depending on 3 creates a second independent chain (3 -> 4)!
        with pytest.raises(CatalogueValidationError, match="Multiple independent dependency chains are not allowed"):
            cats.add_secret(SecretDefinition(id=4, name="Chain2-B", dependency=3))

    def test_cannot_delete_secret_when_another_depends_on_it(self):
        from scene_editor.catalogue_model import DefinitionInUseError
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))
        cats.add_secret(SecretDefinition(id=3, name="Artifacts", dependency=2))

        # Cannot delete Keys (id=1) because CDs (id=2) depends on it
        with pytest.raises(DefinitionInUseError, match="depend on it"):
            cats.remove_secret(1)

        # Cannot delete CDs (id=2) because Artifacts (id=3) depends on it
        with pytest.raises(DefinitionInUseError, match="depend on it"):
            cats.remove_secret(2)

        # Removing Artifacts (id=3) succeeds as nothing depends on it
        removed = cats.remove_secret(3)
        assert removed.id == 3
        assert cats.get_secret(3) is None

    def test_updating_secret_id_cascades_dependency(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))

        # Change Keys id from 1 to 10
        updated_keys = SecretDefinition(id=10, name="Master Keys", dependency=None)
        cats.update_secret(1, updated_keys)

        assert 1 not in cats.secrets
        assert 10 in cats.secrets
        # Secret 2 should now depend on 10
        assert cats.get_secret(2).dependency == 10
        assert cats.get_secret_stage(2) == 2

    def test_get_valid_dependencies_for_prevents_branching_and_cycles(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))

        # For a new secret (None), valid dependency can only be Secret 2 (CDs).
        # Secret 1 (Keys) is NOT valid because it already has a child (CDs).
        valid_for_new = cats.get_valid_dependencies_for(None)
        assert len(valid_for_new) == 1
        assert valid_for_new[0].id == 2

        # For Secret 1 (which already has child 2), it cannot depend on 2 (cycle)
        valid_for_1 = cats.get_valid_dependencies_for(1)
        assert len(valid_for_1) == 0

    def test_catalogues_dialog_secrets_dependency_ui(self, qapp, tmp_path: Path):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys", dependency=None))
        cats.add_secret(SecretDefinition(id=2, name="CDs", dependency=1))

        dlg = CataloguesDialog(cats, base_dir=tmp_path, initial_tab="secrets")
        assert dlg.tabs.currentIndex() == 1

        # Check list item formatting shows clean names and dependency requirements without Stage numbers
        item0 = dlg.secret_list.item(0)
        assert "Keys [1]" in item0.text()
        assert "(from start)" in item0.text()
        assert "Stage" not in item0.text()

        item1 = dlg.secret_list.item(1)
        assert "CDs [2]" in item1.text()
        assert "(requires: Keys)" in item1.text()
        assert "Stage" not in item1.text()

        # Select second item (CDs)
        dlg.secret_list.setCurrentRow(1)
        assert dlg.secret_dep_combo.currentData() == 1
        assert "Keys" in dlg.secret_stage_lbl.text()
        assert "Unlocks after collecting all 'Keys'" in dlg.secret_stage_lbl.text()
        assert "Stage" not in dlg.secret_stage_lbl.text()

        # Click new secret
        dlg._on_new_secret_clicked()
        assert dlg.secret_dep_combo.currentData() is None
        assert "Available from the start of the scene" in dlg.secret_stage_lbl.text()
        assert "Stage" not in dlg.secret_stage_lbl.text()


