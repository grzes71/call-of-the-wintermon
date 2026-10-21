"""Tests for the new secret row constraint: at most one secret per unique Dependency per platform row.

Acceptance Criteria:
1. Multiple secrets with different Dependency values in one row allowed.
2. Two secrets with Dependency = None in one row rejected.
3. Two secrets with Dependency = Gold Key in one row rejected, even if different secret types.
4. The same Dependency can appear across different rows.
5. Moving a secret (or platform) to a row with the same Dependency is blocked.
6. Changing Dependency property cannot introduce a conflict.
7. Duplicating a secret cannot violate the constraint.
8. Import and export detect invalid configurations.
9. Existing valid scenes continue to work without errors.
"""

from pathlib import Path
import pytest

from scene_editor.scene_model import (
    OBJECT_TYPE_TREASURE,
    OBJECT_TYPE_SECRET,
    ObjectLimitExceededError,
    PlatformElement,
    PLATFORM_TYPE_SPRITE,
    Position,
    Scene,
    SceneObjectElement,
)
from scene_editor.catalogue_model import (
    ProjectCatalogues,
    SecretDefinition,
)
from scene_editor.json_serializer import SceneSerializer, CorruptedFileError
from scripts.compile_scenes import parse_scene_json, load_catalogues


@pytest.fixture
def mock_catalogues() -> ProjectCatalogues:
    """Fixture with chain:
    - 1: Gold Key (dep=None)
    - 2: Silver Key (dep=None)
    - 3: Exit Door (dep=1)
    - 4: Chest (dep=1)
    - 5: CD (dep=3)
    - 6: Artifact (dep=5)
    """
    cats = ProjectCatalogues()
    cats.secrets[1] = SecretDefinition(id=1, name="Gold Key", dependency=None)
    cats.secrets[2] = SecretDefinition(id=2, name="Silver Key", dependency=None)
    cats.secrets[3] = SecretDefinition(id=3, name="Exit Door", dependency=1)
    cats.secrets[4] = SecretDefinition(id=4, name="Chest", dependency=1)
    cats.secrets[5] = SecretDefinition(id=5, name="CD", dependency=3)
    cats.secrets[6] = SecretDefinition(id=6, name="Artifact", dependency=5)
    return cats


@pytest.fixture
def test_scene(mock_catalogues: ProjectCatalogues) -> Scene:
    """Scene with two rows:
    - row y=24: plat-01 (x=10, w=32), plat-02 (x=50, w=32)
    - row y=40: plat-03 (x=10, w=32)
    """
    sc = Scene(name="test_scene", width=160, height=96)
    sc.catalogues = mock_catalogues
    sc.add_platform(PlatformElement(id="plat-01", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 24)))
    sc.add_platform(PlatformElement(id="plat-02", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(50, 24)))
    sc.add_platform(PlatformElement(id="plat-03", type=PLATFORM_TYPE_SPRITE, width=32, position=Position(10, 40)))
    return sc


class TestSecretRowConstraints:
    """Comprehensive test suite for the new secret row dependency limit."""

    def test_criterion_1_multiple_secrets_with_different_dependencies_allowed(self, test_scene: Scene):
        """1. In one row, secrets with different Dependency values can be placed (Example A & D)."""
        # Row y=24:
        # Secret 1: Gold Key (dep=None)
        # Secret 2: Exit Door (dep=Gold Key / 1)
        # Secret 3: CD (dep=Exit Door / 3)
        # Secret 4: Artifact (dep=CD / 5)
        # All 4 have different dependencies: None, 1, 3, 5
        can1, _ = test_scene.can_add_object_to_platform("plat-01", obj_type=OBJECT_TYPE_SECRET, definition_id=1)
        assert can1 is True
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-01", x=10))

        can2, _ = test_scene.can_add_object_to_platform("plat-01", obj_type=OBJECT_TYPE_SECRET, definition_id=3)
        assert can2 is True
        test_scene.add_object(SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=3, platform_id="plat-01", x=20))

        can3, _ = test_scene.can_add_object_to_platform("plat-02", obj_type=OBJECT_TYPE_SECRET, definition_id=5)
        assert can3 is True
        test_scene.add_object(SceneObjectElement(id=3, type=OBJECT_TYPE_SECRET, definition_id=5, platform_id="plat-02", x=52))

        can4, _ = test_scene.can_add_object_to_platform("plat-02", obj_type=OBJECT_TYPE_SECRET, definition_id=6)
        assert can4 is True
        test_scene.add_object(SceneObjectElement(id=4, type=OBJECT_TYPE_SECRET, definition_id=6, platform_id="plat-02", x=62))

        assert len(test_scene.get_row_objects(24)) == 4
        test_scene.validate()

    def test_criterion_2_two_secrets_with_none_dependency_rejected(self, test_scene: Scene):
        """2. In one row, two secrets with Dependency = None are rejected (Example B)."""
        # Place Gold Key (dep=None) on plat-01 (row y=24)
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-01", x=10))

        # Attempt to add Silver Key (also dep=None) on plat-02 (same row y=24)
        can_add, reason = test_scene.can_add_object_to_platform(
            "plat-02", obj_type=OBJECT_TYPE_SECRET, definition_id=2
        )
        assert can_add is False
        assert "Platform row y=24 already contains secret '1' with dependency None" in reason

        with pytest.raises(ObjectLimitExceededError) as exc:
            test_scene.add_object(SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="plat-02", x=50))
        assert "already contains secret '1' with dependency None" in str(exc.value)

    def test_criterion_3_two_secrets_with_same_dependency_rejected_different_types(self, test_scene: Scene):
        """3. In one row, two secrets with Dependency = Gold Key are rejected, even if different types (Example C)."""
        # Secret 3 (Exit Door) depends on Gold Key (1)
        # Secret 4 (Chest) also depends on Gold Key (1)
        test_scene.add_object(SceneObjectElement(id=10, type=OBJECT_TYPE_SECRET, definition_id=3, platform_id="plat-01", x=12))

        can_add, reason = test_scene.can_add_object_to_platform(
            "plat-02", obj_type=OBJECT_TYPE_SECRET, definition_id=4
        )
        assert can_add is False
        assert "Platform row y=24 already contains secret '10' with dependency 'Gold Key' (ID 1)" in reason

        with pytest.raises(ObjectLimitExceededError) as exc:
            test_scene.add_object(SceneObjectElement(id=11, type=OBJECT_TYPE_SECRET, definition_id=4, platform_id="plat-02", x=50))
        assert "already contains secret '10' with dependency 'Gold Key' (ID 1)" in str(exc.value)

    def test_criterion_4_same_dependency_in_different_rows_allowed(self, test_scene: Scene):
        """4. The same Dependency can appear in different rows."""
        # Row 24: Gold Key (dep=None)
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-01", x=10))

        # Row 40: Silver Key (dep=None)
        can_add, _ = test_scene.can_add_object_to_platform("plat-03", obj_type=OBJECT_TYPE_SECRET, definition_id=2)
        assert can_add is True
        test_scene.add_object(SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="plat-03", x=10))

        # Both rows have dep=None, but on different rows -> passes validation
        test_scene.validate()
        assert len(test_scene.get_row_objects(24)) == 1
        assert len(test_scene.get_row_objects(40)) == 1

    def test_criterion_5_move_secret_to_conflicting_row_blocked(self, test_scene: Scene):
        """5. Moving a secret or platform to a row with the same Dependency is blocked."""
        # Row 24: Secret 1 (dep=None)
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-01", x=10))
        # Row 40: Secret 2 (dep=None)
        test_scene.add_object(SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=2, platform_id="plat-03", x=10))

        # Moving secret 2 to plat-02 (row 24) must be blocked
        with pytest.raises(ObjectLimitExceededError) as exc:
            test_scene.move_object(2, new_x=50, new_platform_id="plat-02")
        assert "already contains secret '1' with dependency None" in str(exc.value)

        # Moving platform plat-03 (with secret 2) to row 24 must also be blocked
        with pytest.raises(ObjectLimitExceededError) as exc_plat:
            test_scene.move_platform("plat-03", new_x=90, new_y=24)
        assert "causes a secret dependency conflict" in str(exc_plat.value)

    def test_criterion_6_changing_dependency_cannot_introduce_conflict(self, test_scene: Scene, mock_catalogues: ProjectCatalogues):
        """6. Changing Dependency property cannot introduce a conflict."""
        # Row 24 has Secret A (Door, dep=1) and Secret B (CD, dep=3)
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=3, platform_id="plat-01", x=10))
        test_scene.add_object(SceneObjectElement(id=2, type=OBJECT_TYPE_SECRET, definition_id=5, platform_id="plat-02", x=50))
        test_scene.validate()

        # Attempt to change definition of Secret 2 from 5 (dep=3) to 4 (dep=1) -> conflict on row 24!
        with pytest.raises(ObjectLimitExceededError) as exc:
            test_scene.update_object_props(2, new_definition_id="4")
        assert "conflict between secret '1' and secret '2'" in str(exc.value)
        # Original definition remained untouched
        assert test_scene.get_object(2).definition_id == 5

        # Check catalogue-level dependency change conflict detector
        # If user tries to edit definition 5 in catalogue to depend on 1 instead of 3:
        ok, msg = mock_catalogues.check_scene_secret_dependency_conflict(test_scene, target_secret_id=5, new_dependency=1)
        assert ok is False
        assert "causes a conflict on platform row y=24" in msg

    def test_criterion_7_duplicating_secret_cannot_violate_constraint(self, test_scene: Scene):
        """7. Duplicating a secret on the same row is blocked; duplicating on another row is allowed."""
        test_scene.add_object(SceneObjectElement(id=1, type=OBJECT_TYPE_SECRET, definition_id=1, platform_id="plat-01", x=10))

        # Duplicating on plat-02 (same row y=24) must raise ObjectLimitExceededError
        with pytest.raises(ObjectLimitExceededError):
            test_scene.duplicate_object(1, new_id=99, new_platform_id="plat-02", new_x=50)

        # Duplicating on plat-03 (different row y=40) succeeds
        dup = test_scene.duplicate_object(1, new_id=99, new_platform_id="plat-03", new_x=12)
        assert dup.id == 99
        assert dup.platform_id == "plat-03"
        test_scene.validate()

    def test_criterion_8_import_and_export_detect_invalid_configuration(self, tmp_path: Path, mock_catalogues: ProjectCatalogues):
        """8. Import (SceneSerializer) and export (compile_scenes) detect invalid configurations."""
        # Create invalid scene JSON with 2 secrets with dep=None on same row
        invalid_data = {
            "schema_version": 1,
            "scene": {"name": "invalid_scene", "width": 160, "height": 96},
            "platforms": [
                {"id": "p1", "type": "sprite", "position": {"x": 10, "y": 24}, "width": 32, "height": 4}
            ],
            "objects": [
                {"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 10},
                {"id": 2, "type": "secret", "definition_id": 2, "platform_id": "p1", "x": 20},
            ]
        }

        # 8a: SceneSerializer.from_dict / from_json rejects with CorruptedFileError
        with pytest.raises(CorruptedFileError) as exc_import:
            SceneSerializer.from_dict(invalid_data, catalogues=mock_catalogues)
        assert "already contains a secret with dependency None" in str(exc_import.value)

        # 8b: compile_scenes.parse_scene_json rejects during export
        scene_file = tmp_path / "invalid_scene.json"
        import json
        with open(scene_file, "w", encoding="utf-8") as f:
            json.dump(invalid_data, f)

        from scripts.compile_scenes import CatalogueItem
        sec_items = {
            1: CatalogueItem(id=1, name="Gold Key", atari_color=0x1A, blink=False, dependency=None, sprite_id=3),
            2: CatalogueItem(id=2, name="Silver Key", atari_color=0x1A, blink=False, dependency=None, sprite_id=3),
        }
        with pytest.raises(ValueError) as exc_export:
            parse_scene_json(
                scene_file,
                enemies={},
                secrets=sec_items,
            )
        assert "violates secret row constraint at platform row y=24" in str(exc_export.value)

    def test_criterion_9_existing_scenes_continue_to_work(self):
        """9. Existing scenes (01-forest.json and 02-forest-castle.json) satisfy the new rule and compile cleanly."""
        repo_root = Path(__file__).resolve().parent.parent
        cats = ProjectCatalogues.load_from_dir(repo_root)

        forest1_path = repo_root / "scenes" / "01-forest.json"
        forest2_path = repo_root / "scenes" / "02-forest-castle.json"

        # Both load and validate cleanly in SceneSerializer
        sc1 = SceneSerializer.load_from_file(forest1_path, base_dir=repo_root, catalogues=cats)
        sc1.validate()

        sc2 = SceneSerializer.load_from_file(forest2_path, base_dir=repo_root, catalogues=cats)
        sc2.validate()

        # Both compile cleanly with compile_scenes
        from scripts.compile_scenes import load_platform_profiles
        def_file = repo_root / "scenes" / "definitions.json"
        enemies, secrets = load_catalogues(def_file, def_file)
        profiles = load_platform_profiles(def_file)
        data1 = parse_scene_json(forest1_path, enemies=enemies, secrets=secrets, profiles=profiles)
        assert data1.name != ""

        data2 = parse_scene_json(forest2_path, enemies=enemies, secrets=secrets, profiles=profiles)
        assert data2.name != ""
