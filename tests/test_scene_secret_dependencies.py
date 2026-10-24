import os
from pathlib import Path
import sys

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

import pytest

from scene_editor.catalogue_model import ProjectCatalogues, SecretDefinition, EnemyDefinition
from scene_editor.scene_model import (
    Scene,
    SceneObjectElement,
    PlatformElement,
    Position,
    OBJECT_TYPE_SECRET,
    OBJECT_TYPE_ENEMY,
    ModelValidationError,
)
from PySide6.QtWidgets import QApplication
from scene_editor.main_window import MainWindow
from scene_editor.json_serializer import SceneSerializer
from scene_editor.commands import UpdateSceneObjectPropsCommand


class TestSceneSecretDependencies:
    @pytest.fixture
    def catalogues(self):
        cats = ProjectCatalogues()
        cats.add_secret(SecretDefinition(id=1, name="Keys"))
        cats.add_secret(SecretDefinition(id=2, name="Skulls"))
        cats.add_secret(SecretDefinition(id=3, name="Scrolls"))
        return cats

    def test_scene_object_element_dependency_serialization(self):
        obj = SceneObjectElement(
            id=10,
            type=OBJECT_TYPE_SECRET,
            definition_id=2,
            platform_id="plat-1",
            x=50,
            dependency=1,
        )
        data = obj.to_dict()
        assert data["dependency"] == 1

        restored = SceneObjectElement.from_dict(data)
        assert restored.dependency == 1

    def test_scene_object_element_no_dependency_serialization(self):
        obj = SceneObjectElement(
            id=11,
            type=OBJECT_TYPE_SECRET,
            definition_id=1,
            platform_id="plat-1",
            x=50,
            dependency=None,
        )
        data = obj.to_dict()
        assert "dependency" not in data

        restored = SceneObjectElement.from_dict(data)
        assert restored.dependency is None

    def test_secret_cannot_depend_on_itself(self):
        obj = SceneObjectElement(
            id=12,
            type=OBJECT_TYPE_SECRET,
            definition_id=2,
            platform_id="plat-1",
            x=50,
            dependency=2,
        )
        with pytest.raises(ModelValidationError, match="cannot depend on itself"):
            obj.validate()

    def test_get_secret_dependency_priority(self, catalogues):
        scene = Scene(name="Test Scene")
        scene.catalogues = catalogues

        # Object 1: Secret 1 has dependency None
        obj1 = SceneObjectElement(
            id=1,
            type=OBJECT_TYPE_SECRET,
            definition_id=1,
            platform_id="plat-1",
            x=20,
            dependency=None,
        )
        # Object 2: Secret 2 has scene-level dependency 1
        obj2 = SceneObjectElement(
            id=2,
            type=OBJECT_TYPE_SECRET,
            definition_id=2,
            platform_id="plat-1",
            x=80,
            dependency=1,
        )
        scene.objects = [obj1, obj2]

        # Explicit object passed
        assert scene.get_secret_dependency(1, obj=obj1) is None
        assert scene.get_secret_dependency(2, obj=obj2) == 1

        # Without obj, resolves from scene objects matching definition_id
        assert scene.get_secret_dependency(2) == 1

    def test_row_allows_multiple_secrets_with_different_scene_dependencies(self, catalogues):
        scene = Scene(name="Test Scene")
        scene.catalogues = catalogues

        plat = PlatformElement(
            id="plat-1",
            type="sprite",
            position=Position(x=10, y=24),
            width=96,
            height=4,
        )
        scene.platforms = [plat]

        # Two secrets on the same platform row, but obj1 has dep=None and obj2 has dep=1
        obj1 = SceneObjectElement(
            id=1,
            type=OBJECT_TYPE_SECRET,
            definition_id=1,
            platform_id="plat-1",
            x=20,
            dependency=None,
        )
        obj2 = SceneObjectElement(
            id=2,
            type=OBJECT_TYPE_SECRET,
            definition_id=2,
            platform_id="plat-1",
            x=80,
            dependency=1,
        )
        scene.objects = [obj1, obj2]

        # Must validate cleanly without collision error
        scene.validate()

    def test_row_rejects_multiple_secrets_with_same_scene_dependency(self, catalogues):
        scene = Scene(name="Test Scene")
        scene.catalogues = catalogues

        plat = PlatformElement(
            id="plat-1",
            type="sprite",
            position=Position(x=10, y=24),
            width=96,
            height=4,
        )
        scene.platforms = [plat]

        # Both secrets on the same platform row with dependency=None
        obj1 = SceneObjectElement(
            id=1,
            type=OBJECT_TYPE_SECRET,
            definition_id=1,
            platform_id="plat-1",
            x=20,
            dependency=None,
        )
        obj2 = SceneObjectElement(
            id=2,
            type=OBJECT_TYPE_SECRET,
            definition_id=2,
            platform_id="plat-1",
            x=80,
            dependency=None,
        )
        scene.objects = [obj1, obj2]

        with pytest.raises(ModelValidationError, match="ask for the 5th player channel"):
            scene.validate()

    def test_circular_dependency_detection_on_scene(self, catalogues):
        scene = Scene(name="Test Scene")
        scene.catalogues = catalogues

        plat1 = PlatformElement(id="plat-1", type="sprite", position=Position(x=10, y=8), width=32, height=4)
        plat2 = PlatformElement(id="plat-2", type="sprite", position=Position(x=10, y=24), width=32, height=4)
        scene.platforms = [plat1, plat2]

        # Cycle: Secret 1 depends on Secret 2, and Secret 2 depends on Secret 1
        obj1 = SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-1", x=15, dependency=2)
        obj2 = SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="plat-2", x=15, dependency=1)
        scene.objects = [obj1, obj2]

        with pytest.raises(ModelValidationError, match="Cyclic dependency detected on scene"):
            scene.validate()

    def test_update_scene_object_dependency_command_undo_redo(self, catalogues):
        scene = Scene(name="Test Scene")
        scene.catalogues = catalogues

        plat = PlatformElement(id="plat-1", type="sprite", position=Position(x=10, y=8), width=32, height=4)
        scene.platforms = [plat]
        obj = SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="plat-1", x=15, dependency=None)
        scene.objects = [obj]

        cmd = UpdateSceneObjectPropsCommand(scene, 1, new_dependency=1)
        cmd.redo()
        assert obj.dependency == 1

        cmd.undo()
        assert obj.dependency is None

    def test_main_window_secret_dependency_ui(self, tmp_path):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication.instance() or QApplication([])

        window = MainWindow(base_dir=tmp_path)
        window.catalogues.add_secret(SecretDefinition(id=1, name="Keys"))
        window.catalogues.add_secret(SecretDefinition(id=2, name="Skulls"))

        # Switch to Secrets in object creator
        idx = window.new_obj_type_combo.findData(OBJECT_TYPE_SECRET)
        window.new_obj_type_combo.setCurrentIndex(idx)
        assert not window.new_obj_dependency_combo.isHidden()
        assert not window.new_obj_dependency_lbl.isHidden()

        # Add platforms
        plat1 = PlatformElement(id="plat-1", type="sprite", position=Position(x=10, y=8), width=32, height=4)
        plat2 = PlatformElement(id="plat-2", type="sprite", position=Position(x=10, y=24), width=32, height=4)
        window.scene_model.add_platform(plat1)
        window.scene_model.add_platform(plat2)
        window._refresh_object_creator_platforms()

        # Add secret 1 on plat-1 with dep=None
        window.new_obj_platform_combo.setCurrentIndex(window.new_obj_platform_combo.findData("plat-1"))
        window.new_obj_definition_combo.setCurrentIndex(window.new_obj_definition_combo.findData(1))
        window.new_obj_dependency_combo.setCurrentIndex(0)  # None
        window.new_obj_x_spin.setValue(12)
        window._on_add_object_clicked()
        assert len(window.scene_model.objects) == 1
        assert window.scene_model.objects[0].dependency is None

        # Add secret 2 on plat-2 with dep=1
        window.new_obj_platform_combo.setCurrentIndex(window.new_obj_platform_combo.findData("plat-2"))
        window.new_obj_definition_combo.setCurrentIndex(window.new_obj_definition_combo.findData(2))
        dep_idx = window.new_obj_dependency_combo.findData(1)
        assert dep_idx >= 0
        window.new_obj_dependency_combo.setCurrentIndex(dep_idx)
        window.new_obj_x_spin.setValue(18)
        window._on_add_object_clicked()
        assert len(window.scene_model.objects) == 2
        assert window.scene_model.objects[1].dependency == 1

        # Select object 2 and check property panel
        obj2 = window.scene_model.objects[1]
        window._on_object_selected(obj2.id)
        assert not window.obj_prop_dependency_combo.isHidden()
        assert window.obj_prop_dependency_combo.currentData() == 1

        # Change dependency of object 2 to None via property combo
        window.obj_prop_dependency_combo.setCurrentIndex(0)
        assert obj2.dependency is None

        # Undo
        window.undo_stack.undo()
        assert obj2.dependency == 1

        # Redo
        window.undo_stack.redo()
        assert obj2.dependency is None

