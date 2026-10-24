"""Test suite for numeric sprite_id links, resolver, migration, and PMG invariants.

Covers tests required by Section 4:
1. Powiązanie po sprite_id -> build przechodzi, PMG zgodne z referencją liczoną niezależnie.
2. Nieistniejące id -> błąd z listą sprite'ów; brak powiązania -> błąd; ten sam sprite jako wróg i Sekret -> błąd;
   duplikat id sprite'a -> błąd; duplikat nazwy -> bez błędu.
3. Pole sprite (nazwa) -> buduje się z ostrzeżeniem, wynik taki sam jak dla sprite_id.
4. Nadpisanie w scenie ma pierwszeństwo przed katalogiem.
5. Zmiana numeracji w pliku sprite'ów BEZ aktualizacji powiązań -> build przechodzi albo zgłasza błąd tylko gdy numer nie istnieje
   (dokumentacja zachowania: numer wskazuje inny sprite, brak detekcji).
6. Migracja: dry-run nic nie zapisuje; --apply zapisuje tylko jednoznaczne; idempotencja; po migracji brak pola sprite.
7. Scene Editor: odczyt dwóch formatów, zapis sprite_id, brak zapisu sprite'a równego domyślnemu.
8. Repozytorium: wszyscy wrogowie i Sekrety mają rozstrzygnięty sprite; PMG wrogów (Player) i Sekretów (pociski) zgodne z referencją.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.compile_sprites import (
    pack_row_to_player_bitmap,
    pack_row_to_5th_player_missiles,
    parse_sprites_json,
    compile_sprites,
)
from scripts.compile_scenes import compile_scenes
from scripts.migrate_sprite_links import (
    analyze_catalog_migration,
    analyze_scenes_migration,
    run_migration,
)
from scripts.sprite_links import (
    SpriteLinkError,
    SpriteRegistry,
    resolve_definitions,
    resolve_object_sprite,
    format_resolution_table,
)
from scripts.sprite_roles import (
    SpriteRoleConflictError,
    SpriteValidationError,
    determine_sprite_roles_from_scenes,
)
from scene_editor.catalogue_model import EnemyDefinition, ProjectCatalogues, SecretDefinition
from scene_editor.scene_model import (
    Scene,
    SceneObjectElement,
    PlatformElement,
    Position,
    OBJECT_TYPE_ENEMY,
    OBJECT_TYPE_SECRET,
)
from scene_editor.json_serializer import SceneSerializer


# -----------------------------------------------------------------------------
# 1. Powiązanie po sprite_id -> build przechodzi, PMG zgodne z referencją
# -----------------------------------------------------------------------------
def test_sprite_id_linkage_and_pmg_reference(tmp_path: Path):
    """Powiązanie po sprite_id -> build przechodzi, PMG zgodne z referencją niezależną."""
    spr_json = {
        "sprites": [
            {
                "id": 1,
                "description": "Monster",
                "width": 8,
                "height": 4,
                "color": 0x44,
                "frames": [{"pixels": ["11000011", "00111100", "01011010", "11111111"]}],
            },
            {
                "id": 2,
                "description": "GoldCoin",
                "width": 8,
                "height": 4,
                "color": 0x28,
                "frames": [{"pixels": ["00111100", "01111110", "01111110", "00111100"]}],
            },
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    defs_data = {
        "enemies": [{"id": 1, "name": "Monster", "sprite_id": 1, "atari_color": 0x44}],
        "secrets": [{"id": 1, "name": "Coin", "sprite_id": 2, "atari_color": 0x28}],
        "platform_profiles": [],
    }
    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps(defs_data), encoding="utf-8")

    scene_data = {
        "scene": {"name": "TestLevel", "tileset": "trees", "background_color": 0},
        "platforms": [{"id": "p1", "type": "ground", "position": {"x": 0, "y": 80}, "width": 160, "height": 16}],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 20},
            {"id": 2, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 60},
        ],
    }
    sc_file = tmp_path / "scene1.json"
    sc_file.write_text(json.dumps(scene_data), encoding="utf-8")
    man_file = tmp_path / "scenes.json"
    man_file.write_text(json.dumps({"scenes": ["scene1.json"]}), encoding="utf-8")

    # 1. Resolve definitions
    resolved_path = tmp_path / "definitions_resolved.json"
    resolve_definitions(defs_path, spr_path, resolved_path)
    res_data = json.loads(resolved_path.read_text(encoding="utf-8"))
    assert res_data["enemies"][0]["sprite_id"] == 1
    assert res_data["secrets"][0]["sprite_id"] == 2

    # 2. Determine roles
    roles, _, _ = determine_sprite_roles_from_scenes(
        man_file, resolved_path, scenes_dir=tmp_path, sprites_path=spr_path
    )
    assert roles[1] == "player"
    assert roles[2] == "missiles"

    # 3. Parse and verify PMG bytes against independent calculation
    parsed = parse_sprites_json(
        spr_path, mode="missiles", scenes_manifest_path=man_file, definitions_path=resolved_path
    )
    assert parsed[1].format == "player"
    assert parsed[2].format == "missiles"

    # Enemy rows packed as player
    raw_enemy_pixels = spr_json["sprites"][0]["frames"][0]["pixels"]
    expected_enemy_bytes = [pack_row_to_player_bitmap(r) for r in raw_enemy_pixels]
    assert parsed[1].frames[0].rows == expected_enemy_bytes

    # Secret rows packed as 5th player missiles
    raw_secret_pixels = spr_json["sprites"][1]["frames"][0]["pixels"]
    expected_secret_bytes = [pack_row_to_5th_player_missiles(r) for r in raw_secret_pixels]
    assert parsed[2].frames[0].rows == expected_secret_bytes


# -----------------------------------------------------------------------------
# 2. Błędy resolvera, brak powiązania, konflikt ról, duplikaty ID i nazw
# -----------------------------------------------------------------------------
def test_resolver_errors_missing_conflict_and_duplicates(tmp_path: Path):
    """Nieistniejące id -> błąd z listą; brak -> błąd; konflikt ról -> błąd;
    duplikat id sprite'a -> błąd; duplikat nazwy -> BEZ błędu."""
    # 2a. Duplikat ID sprite'a -> błąd
    dup_id_json = {
        "sprites": [
            {"id": 1, "description": "SpriteA", "width": 8, "height": 8, "frames": []},
            {"id": 1, "description": "SpriteB", "width": 8, "height": 8, "frames": []},
        ]
    }
    dup_id_path = tmp_path / "dup_id.sprite.json"
    dup_id_path.write_text(json.dumps(dup_id_json), encoding="utf-8")
    with pytest.raises(SpriteLinkError) as exc_dup_id:
        SpriteRegistry(dup_id_path)
    assert "zduplikowane id sprite'a 1" in str(exc_dup_id.value).lower()

    # 2b. Duplikat NAZWY sprite'a -> BEZ błędu (nazwy nie są kluczami!)
    dup_name_json = {
        "sprites": [
            {"id": 1, "description": "Ghost", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "Ghost", "width": 8, "height": 8, "frames": []},
        ]
    }
    dup_name_path = tmp_path / "dup_name.sprite.json"
    dup_name_path.write_text(json.dumps(dup_name_json), encoding="utf-8")
    reg_dup_name = SpriteRegistry(dup_name_path)
    assert 1 in reg_dup_name.sprites_by_id
    assert 2 in reg_dup_name.sprites_by_id

    # 2c. Nieistniejące id -> czytelny błąd po polsku z listą dostępnych sprite'ów
    valid_spr_json = {
        "sprites": [
            {"id": 1, "description": "Ghoul", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "Key", "width": 8, "height": 8, "frames": []},
        ]
    }
    valid_spr_path = tmp_path / "valid.sprite.json"
    valid_spr_path.write_text(json.dumps(valid_spr_json), encoding="utf-8")
    reg_valid = SpriteRegistry(valid_spr_path)

    bad_defs = {
        "enemies": [{"id": 1, "name": "Unknown", "sprite_id": 99}],
        "secrets": [],
    }
    bad_defs_path = tmp_path / "bad_defs.json"
    bad_defs_path.write_text(json.dumps(bad_defs), encoding="utf-8")
    out_path = tmp_path / "out.json"

    with pytest.raises(SpriteLinkError) as exc_notfound:
        resolve_definitions(bad_defs_path, valid_spr_path, out_path)
    msg = str(exc_notfound.value)
    assert "sprite_id=99 nie istnieje w pliku sprite'ów" in msg
    assert "Dostępne sprite'y:" in msg
    assert "1: Ghoul" in msg
    assert "2: Key" in msg

    # 2d. Brak powiązania w obiekcie i w katalogu -> błąd
    empty_obj = {"id": 10, "type": "enemy", "definition_id": 5}
    catalog_without_sprite = {"id": 5, "name": "NoSpriteEnemy"}
    with pytest.raises(SpriteLinkError) as exc_missing:
        resolve_object_sprite(empty_obj, catalog_without_sprite, reg_valid, scene_name="Cave", scene_file="cave.json")
    assert "nie ma przypisanego sprite_id" in str(exc_missing.value).lower()

    # 2e. Konflikt ról: ten sam sprite jako wróg i jako Sekret -> błąd
    sc_enemy = {
        "scene": {"name": "A"},
        "objects": [{"id": 1, "type": "enemy", "definition_id": 1, "sprite_id": 1}],
    }
    sc_secret = {
        "scene": {"name": "B"},
        "objects": [{"id": 2, "type": "secret", "definition_id": 1, "sprite_id": 1}],
    }
    (tmp_path / "sc_a.json").write_text(json.dumps(sc_enemy), encoding="utf-8")
    (tmp_path / "sc_b.json").write_text(json.dumps(sc_secret), encoding="utf-8")
    man = tmp_path / "man_conflict.json"
    man.write_text(json.dumps({"scenes": ["sc_a.json", "sc_b.json"]}), encoding="utf-8")
    empty_defs = tmp_path / "empty_defs.json"
    empty_defs.write_text(json.dumps({"enemies": [], "secrets": []}), encoding="utf-8")

    with pytest.raises(SpriteRoleConflictError) as exc_conflict:
        determine_sprite_roles_from_scenes(man, empty_defs, scenes_dir=tmp_path, sprites_path=valid_spr_path)
    assert "Konflikt ról" in str(exc_conflict.value)
    assert "sc_a.json" in str(exc_conflict.value)
    assert "sc_b.json" in str(exc_conflict.value)


# -----------------------------------------------------------------------------
# 3. Pole sprite (nazwa) -> buduje się z ostrzeżeniem, wynik taki sam jak dla sprite_id
# -----------------------------------------------------------------------------
def test_legacy_sprite_name_builds_with_warning(tmp_path: Path):
    """Pole sprite (nazwa) -> buduje się z ostrzeżeniem, wynik taki sam jak dla sprite_id."""
    spr_json = {
        "sprites": [
            {"id": 4, "description": "Shub-Niggurath", "width": 8, "height": 8, "frames": [{"pixels": ["11111111"] * 8}]},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    # Catalog with legacy 'sprite' string field
    defs_legacy = {
        "enemies": [{"id": 1, "name": "Shub", "sprite": "Shub-Niggurath"}],
        "secrets": [],
    }
    defs_path = tmp_path / "definitions_legacy.json"
    defs_path.write_text(json.dumps(defs_legacy), encoding="utf-8")

    out_resolved = tmp_path / "resolved.json"
    with pytest.warns(UserWarning, match="przestarzałego pola 'sprite'"):
        resolve_definitions(defs_path, spr_path, out_resolved)

    res = json.loads(out_resolved.read_text(encoding="utf-8"))
    assert res["enemies"][0]["sprite_id"] == 4
    assert res["enemies"][0]["sprite"] == "Shub-Niggurath"


# -----------------------------------------------------------------------------
# 4. Nadpisanie w scenie ma pierwszeństwo przed katalogiem
# -----------------------------------------------------------------------------
def test_scene_override_priority(tmp_path: Path):
    """Nadpisanie w scenie ma pierwszeństwo przed katalogiem."""
    spr_json = {
        "sprites": [
            {"id": 1, "description": "StandardEnemy", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "BossEnemy", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")
    reg = SpriteRegistry(spr_path)

    catalog_item = {"id": 1, "name": "Enemy", "sprite_id": 1}
    # Scene overrides sprite_id to 2
    scene_obj = {"id": 10, "type": "enemy", "definition_id": 1, "sprite_id": 2}

    sid, sname, is_legacy = resolve_object_sprite(
        scene_obj, catalog_item, reg, scene_name="Forest", scene_file="01-forest.json"
    )
    assert sid == 2
    assert sname == "BossEnemy"
    assert is_legacy is False


# -----------------------------------------------------------------------------
# 5. Zmiana numeracji w pliku sprite'ów BEZ aktualizacji powiązań
# -----------------------------------------------------------------------------
def test_sprite_renumbering_without_link_update_documents_no_detection(tmp_path: Path):
    """Zmiana numeracji w pliku sprite'ów BEZ aktualizacji powiązań -> build przechodzi
    albo zgłasza błąd tylko gdy numer nie istnieje (dokumentacja zachowania: numer
    wskazuje inny sprite, nie ma wykrywania zmian po nazwach)."""
    # Wersja 1: ID 1 = Goblin, ID 2 = Chest
    spr_v1 = {
        "sprites": [
            {"id": 1, "description": "Goblin", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "Chest", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_v1), encoding="utf-8")

    defs_data = {
        "enemies": [{"id": 1, "name": "GoblinEnemy", "sprite_id": 1}],
        "secrets": [],
    }
    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps(defs_data), encoding="utf-8")

    out_v1 = tmp_path / "out_v1.json"
    resolve_definitions(defs_path, spr_path, out_v1)
    res1 = json.loads(out_v1.read_text(encoding="utf-8"))
    assert res1["enemies"][0]["sprite_id"] == 1
    assert res1["enemies"][0]["sprite"] == "Goblin"

    # Wersja 2: Zmiana numeracji w Sprite Studio bez aktualizacji powiązań:
    # ID 1 to teraz Chest, a Goblin ma ID 2!
    spr_v2 = {
        "sprites": [
            {"id": 1, "description": "Chest", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "Goblin", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path.write_text(json.dumps(spr_v2), encoding="utf-8")

    out_v2 = tmp_path / "out_v2.json"
    resolve_definitions(defs_path, spr_path, out_v2)
    res2 = json.loads(out_v2.read_text(encoding="utf-8"))

    # ZACHOWANIE SYSTEMU:
    # Build przechodzi bez błędu, ponieważ sprite_id 1 istnieje.
    # Wskazuje on teraz na nowy sprite (Chest), a nie na Goblin. Nie ma wykrywania nazw!
    assert res2["enemies"][0]["sprite_id"] == 1
    assert res2["enemies"][0]["sprite"] == "Chest"

    # Jeśli numer został usunięty (np. zmieniono na 2 i 3, a w katalogu zostało 1) -> błąd nieistniejącego id
    spr_v3 = {
        "sprites": [
            {"id": 2, "description": "Goblin", "width": 8, "height": 8, "frames": []},
            {"id": 3, "description": "Chest", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path.write_text(json.dumps(spr_v3), encoding="utf-8")
    with pytest.raises(SpriteLinkError) as exc_v3:
        resolve_definitions(defs_path, spr_path, tmp_path / "out_v3.json")
    assert "sprite_id=1 nie istnieje w pliku sprite'ów" in str(exc_v3.value)


# -----------------------------------------------------------------------------
# 6. Migracja: dry-run, --apply, idempotencja, brak pola sprite
# -----------------------------------------------------------------------------
def test_migration_workflow_numeric_id(tmp_path: Path):
    """Migracja: dry-run nic nie zapisuje; --apply zapisuje tylko jednoznaczne;
    idempotencja; po migracji brak pola sprite."""
    spr_json = {
        "sprites": [
            {"id": 1, "description": "Azathoth", "width": 8, "height": 8, "frames": []},
            {"id": 2, "description": "Nyarlathotep", "width": 8, "height": 8, "frames": []},
            {"id": 3, "description": "Yog-Sothoth", "width": 8, "height": 8, "frames": []},
            {"id": 8, "description": "Gold Key", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    defs_orig = {
        "enemies": [
            {"id": 1, "name": "Azathoth", "sprite": "Azathoth", "atari_color": 0x34},
            {"id": 2, "name": "Nyarlathotep", "sprite": "Nyarlathotep", "atari_color": 0x76},
            {"id": 3, "name": "Yog-Sothoth", "sprite_id": 3, "atari_color": 0x48},  # Już miało samo sprite_id
        ],
        "secrets": [
            {"id": 8, "name": "Gold Key", "sprite_id": 8, "atari_color": 0x1A},     # Już miało samo sprite_id
        ],
        "platform_profiles": [],
    }
    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps(defs_orig), encoding="utf-8")

    scene_orig = {
        "scene": {"name": "TestScene"},
        "platforms": [],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 1, "sprite_id": 1},  # redundantne (równe domyślnemu) -> do usunięcia
            {"id": 2, "type": "enemy", "definition_id": 1, "sprite": "Nyarlathotep"},  # nadpisanie legacy -> do zamiany na sprite_id: 2
        ],
    }
    sc_path = tmp_path / "scene.json"
    sc_path.write_text(json.dumps(scene_orig), encoding="utf-8")
    man_path = tmp_path / "scenes.json"
    man_path.write_text(json.dumps({"scenes": ["scene.json"]}), encoding="utf-8")

    # 6a. Dry-run nic nie zapisuje
    ok_dry = run_migration(defs_path, spr_path, man_path, apply=False)
    assert ok_dry is True
    assert json.loads(defs_path.read_text(encoding="utf-8")) == defs_orig
    assert json.loads(sc_path.read_text(encoding="utf-8")) == scene_orig
    assert not (tmp_path / "definitions.json.bak").exists()

    # 6b. Apply zapisuje zmiany i tworzy kopie .bak
    ok_apply = run_migration(defs_path, spr_path, man_path, apply=True)
    assert ok_apply is True
    assert (tmp_path / "definitions.json.bak").exists()
    assert (tmp_path / "scene.json.bak").exists()

    migrated_defs = json.loads(defs_path.read_text(encoding="utf-8"))
    # Wpisy z polem sprite przekształcone w sprite_id
    assert migrated_defs["enemies"][0]["sprite_id"] == 1
    assert "sprite" not in migrated_defs["enemies"][0]
    assert migrated_defs["enemies"][1]["sprite_id"] == 2
    assert "sprite" not in migrated_defs["enemies"][1]
    # Yog-Sothoth i Gold Key bez zmian
    assert migrated_defs["enemies"][2]["sprite_id"] == 3
    assert "sprite" not in migrated_defs["enemies"][2]
    assert migrated_defs["secrets"][0]["sprite_id"] == 8
    assert "sprite" not in migrated_defs["secrets"][0]

    # Scena: redundantne nadpisanie usunięte, nadpisanie sprite zamienione na sprite_id
    migrated_scene = json.loads(sc_path.read_text(encoding="utf-8"))
    assert "sprite_id" not in migrated_scene["objects"][0]
    assert "sprite" not in migrated_scene["objects"][0]
    assert migrated_scene["objects"][1]["sprite_id"] == 2
    assert "sprite" not in migrated_scene["objects"][1]

    # 6c. Idempotencja: ponowne uruchomienie nie zmienia niczego
    defs_text_before = defs_path.read_text(encoding="utf-8")
    scene_text_before = sc_path.read_text(encoding="utf-8")
    ok_again = run_migration(defs_path, spr_path, man_path, apply=True)
    assert ok_again is True
    assert defs_path.read_text(encoding="utf-8") == defs_text_before
    assert sc_path.read_text(encoding="utf-8") == scene_text_before


# -----------------------------------------------------------------------------
# 7. Scene Editor: odczyt dwóch formatów, zapis sprite_id, brak zapisu domyślnego
# -----------------------------------------------------------------------------
def test_scene_editor_model_formats_and_default_omission():
    """Scene Editor: odczyt dwóch formatów, zapis sprite_id, brak zapisu sprite'a równego domyślnemu."""
    cats = ProjectCatalogues()
    cats.add_enemy(EnemyDefinition(id=1, name="Spider", sprite_id=3))

    scene = Scene(name="TestScene", width=160, height=96)
    scene.add_platform(PlatformElement(id="p1", type="sprite", position=Position(x=0, y=24), width=32))

    # Obiekt 1: sprite_id równe domyślnemu z katalogu (3) -> pole sprite_id NIE jest zapisywane
    obj1 = SceneObjectElement(id=1, type=OBJECT_TYPE_ENEMY, definition_id=1, platform_id="p1", x=10, sprite_id=3)
    # Obiekt 2: nadpisanie sprite_id (7 != 3) -> pole sprite_id JEST zapisywane
    obj2 = SceneObjectElement(id=2, type=OBJECT_TYPE_ENEMY, definition_id=1, platform_id="p1", x=20, sprite_id=7)
    scene.add_object(obj1)
    scene.add_object(obj2)

    data = SceneSerializer.to_dict(scene, catalogues=cats)
    assert "sprite_id" not in data["objects"][0]
    assert "sprite" not in data["objects"][0]
    assert data["objects"][1]["sprite_id"] == 7
    assert "sprite" not in data["objects"][1]

    # Odczyt przestarzałego formatu z polem 'sprite' (z ostrzeżeniem UserWarning)
    legacy_dict = {"id": 3, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 30, "sprite": "Ghost"}
    with pytest.warns(UserWarning, match="przestarzałego pola 'sprite'"):
        obj_legacy = SceneObjectElement.from_dict(legacy_dict)
    assert obj_legacy.sprite == "Ghost"

    # Odczyt nowego formatu z polem 'sprite_id'
    new_dict = {"id": 4, "type": "enemy", "definition_id": 1, "platform_id": "p1", "x": 40, "sprite_id": 5}
    obj_new = SceneObjectElement.from_dict(new_dict)
    assert obj_new.sprite_id == 5


# -----------------------------------------------------------------------------
# 8. Repozytorium: Wszyscy wrogowie i Sekrety mają rozstrzygnięty sprite; PMG zgodne
# -----------------------------------------------------------------------------
def test_repo_data_resolution_and_pmg_invariants():
    """Na danych repozytorium: wszyscy wrogowie i Sekrety mają rozstrzygnięty sprite;
    PMG wrogów (Player) i Sekretów (pociski) zgodne z referencją."""
    repo_root = Path(__file__).resolve().parent.parent
    spr_path = repo_root / "sprites" / "objects.sprite.json"
    defs_path = repo_root / "scenes" / "definitions.json"
    man_path = repo_root / "scenes" / "scenes.json"

    assert spr_path.is_file()
    assert defs_path.is_file()
    assert man_path.is_file()

    registry = SpriteRegistry(spr_path)
    defs_data = json.loads(defs_path.read_text(encoding="utf-8"))

    # Upewniamy się, że w pliku autorskim definitions.json NIE MA pola 'sprite'
    for enemy in defs_data.get("enemies", []):
        assert "sprite" not in enemy, f"Enemy {enemy.get('id')} nadal zawiera pole 'sprite'"
        assert "sprite_id" in enemy, f"Enemy {enemy.get('id')} brak 'sprite_id'"
        assert enemy["sprite_id"] in registry.sprites_by_id

    for secret in defs_data.get("secrets", []):
        assert "sprite" not in secret, f"Secret {secret.get('id')} nadal zawiera pole 'sprite'"
        assert "sprite_id" in secret, f"Secret {secret.get('id')} brak 'sprite_id'"
        assert secret["sprite_id"] in registry.sprites_by_id

    # Sprawdzamy role i formaty ze scen
    roles, _, _ = determine_sprite_roles_from_scenes(man_path, defs_path, sprites_path=spr_path)
    assert roles[1] == "player", "Sprite 1 (Azathoth) użyty w 01-forest musi mieć format player"
    assert roles[2] == "player", "Sprite 2 (Nyarlathotep) użyty w 01-forest musi mieć format player"

    # Weryfikacja bajtów PMG z niezależną referencją
    parsed_sprites = parse_sprites_json(
        spr_path, mode="missiles", scenes_manifest_path=man_path, definitions_path=defs_path
    )
    spr_data = json.loads(spr_path.read_text(encoding="utf-8"))
    for spr in spr_data.get("sprites", []):
        sid = spr["id"]
        role = roles.get(sid, "missiles")
        parsed_def = parsed_sprites[sid]
        assert parsed_def.format == role

        for f_idx, frame in enumerate(spr.get("frames", [])):
            raw_pixels = frame.get("pixels", [])
            ref_bytes = []
            for row_str in raw_pixels:
                if role == "player":
                    ref_bytes.append(pack_row_to_player_bitmap(row_str))
                else:
                    ref_bytes.append(pack_row_to_5th_player_missiles(row_str))
            assert parsed_def.frames[f_idx].rows == ref_bytes, f"Niezgodność PMG dla sprite {sid} klatka {f_idx}"


# -----------------------------------------------------------------------------
# 9. Nieużywany w repozytorium sprite z katalogu działa po dodaniu do nowej sceny
# -----------------------------------------------------------------------------
def test_unused_catalog_sprite_resolves_when_added_to_new_scene(tmp_path: Path):
    """Sprite zdefiniowany w katalogu, ale nieużywany w scenach repozytorium (np. Hastog lub Mjolnir),
    działa automatycznie i natychmiast po umieszczeniu go w nowej scenie (Hastog -> Player, Mjolnir -> Pociski)."""
    repo_root = Path(__file__).resolve().parent.parent
    spr_path = repo_root / "sprites" / "objects.sprite.json"
    defs_path = repo_root / "scenes" / "definitions.json"

    # Tworzymy nową syntetyczną scenę w tmp_path, która stawia wroga Hastog (typ 5 w katalogu, sprite_id: 5)
    # oraz sekret Mjolnir (typ 4 w katalogu, sprite_id: 9).
    new_scene_data = {
        "scene": {
            "name": "New Test Cave",
            "tileset": "castles",
            "background_color": 0
        },
        "platforms": [
            {"id": "p1", "type": "ground", "position": {"x": 0, "y": 80}, "width": 160, "height": 16}
        ],
        "objects": [
            {"id": 1, "type": "enemy", "definition_id": 5, "platform_id": "p1", "x": 30},
            {"id": 2, "type": "secret", "definition_id": 4, "platform_id": "p1", "x": 60}
        ]
    }
    sc_file = tmp_path / "03-cave.json"
    sc_file.write_text(json.dumps(new_scene_data), encoding="utf-8")

    man_file = tmp_path / "scenes.json"
    man_file.write_text(json.dumps({"scenes": ["03-cave.json"]}), encoding="utf-8")

    # 1. Sprawdzamy role sprite'ów w nowej scenie
    roles, enemy_usages, secret_usages = determine_sprite_roles_from_scenes(
        man_file, defs_path, scenes_dir=tmp_path, sprites_path=spr_path
    )
    # Hastog ma sprite_id 5 -> rola 'player'
    assert roles[5] == "player"
    # Mjolnir ma sprite_id 9 -> rola 'missiles'
    assert roles[9] == "missiles"

    # 2. Kompilujemy sprite'y i sprawdzamy wygenerowany manifest
    out_asm = tmp_path / "sprites_data.asm"
    out_manifest = tmp_path / "sprites_manifest.json"
    res_spr = compile_sprites(
        input_path=spr_path,
        output_path=out_asm,
        mode="missiles",
        definitions_path=defs_path,
        scenes_manifest_path=man_file,
        manifest_output_path=out_manifest,
    )
    assert res_spr == 0
    man_content = json.loads(out_manifest.read_text(encoding="utf-8"))
    assert man_content["sprites"]["5"]["format"] == "player"
    assert man_content["sprites"]["9"]["format"] == "missiles"

    # 3. Kompilujemy nową scenę przez compile_scenes - asercja braku błędów i poprawnego wygenerowania ASM
    resolved_defs = tmp_path / "definitions_resolved.json"
    resolve_definitions(defs_path, spr_path, resolved_defs, print_table=False)
    out_scenes_asm = tmp_path / "scenes_data.asm"
    res_scenes = compile_scenes(
        manifest_path=man_file,
        output_path=out_scenes_asm,
        definitions_path=resolved_defs,
        sprites_path=spr_path,
    )
    assert res_scenes == 0
    assert out_scenes_asm.is_file()
    scenes_asm_text = out_scenes_asm.read_text(encoding="utf-8")
    assert "03-cave.json" in scenes_asm_text or "New Test Cave" in scenes_asm_text

# -----------------------------------------------------------------------------
# 10. Nowe pola kartoteki (np. flaga 'special' sekretów) muszą przetrwać narzędzia
# -----------------------------------------------------------------------------
def test_migration_preserves_secret_special_flag(tmp_path: Path):
    """Migracja sprite'ów przebudowuje wpisy katalogu - nowe pola nie mogą ginąć."""
    spr_json = {
        "sprites": [
            {"id": 7, "description": "Skull", "width": 8, "height": 8, "frames": []},
            {"id": 8, "description": "Gold Key", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    defs_orig = {
        "enemies": [],
        "secrets": [
            {"id": 8, "name": "Gold Key", "sprite": "Gold Key", "blink": True, "special": True},
            {"id": 7, "name": "Skull", "sprite_id": 7},
        ],
        "platform_profiles": [],
    }
    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps(defs_orig), encoding="utf-8")

    scene_orig = {
        "scene": {"name": "TestScene"},
        "platforms": [],
        "objects": [{"id": 1, "type": "secret", "definition_id": 8}],
    }
    sc_path = tmp_path / "scene.json"
    sc_path.write_text(json.dumps(scene_orig), encoding="utf-8")
    man_path = tmp_path / "scenes.json"
    man_path.write_text(json.dumps({"scenes": ["scene.json"]}), encoding="utf-8")

    assert run_migration(defs_path, spr_path, man_path, apply=True) is True

    migrated = json.loads(defs_path.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in migrated["secrets"]}
    # Legacy 'sprite' name migrated to sprite_id, the new flag survived untouched.
    assert by_id[8]["sprite_id"] == 8
    assert "sprite" not in by_id[8]
    assert by_id[8]["blink"] is True
    assert by_id[8]["special"] is True
    # Entries that never used the flag must not gain it.
    assert "special" not in by_id[7]


def test_resolver_preserves_secret_special_flag(tmp_path: Path):
    """Resolve definitions -> definitions_resolved.json: nowe pola przechodzą 1:1."""
    spr_json = {
        "sprites": [
            {"id": 8, "description": "Gold Key", "width": 8, "height": 8, "frames": []},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    defs_orig = {
        "enemies": [],
        "secrets": [{"id": 8, "name": "Gold Key", "sprite_id": 8, "special": True}],
        "platform_profiles": [],
    }
    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps(defs_orig), encoding="utf-8")

    out_path = tmp_path / "definitions_resolved.json"
    resolve_definitions(defs_path, spr_path, out_path)

    resolved = json.loads(out_path.read_text(encoding="utf-8"))
    assert resolved["secrets"][0]["sprite_id"] == 8
    assert resolved["secrets"][0]["special"] is True


# -----------------------------------------------------------------------------
# 12. Kanał sekretu z definicji wybiera format pakowania sprite'a
# -----------------------------------------------------------------------------
def _channel_fixture(tmp_path: Path, secrets_defs: list[dict[str, Any]], objects: list[dict[str, Any]]) -> tuple[Path, Path, dict[str, Any]]:
    """Zapisuje sprite'y, definitions.json, scenę i manifest; zwraca ścieżki i surowe sprite'y."""
    spr_json = {
        "sprites": [
            {"id": 8, "description": "Gold Key", "width": 8, "height": 4,
             "frames": [{"pixels": ["11000011", "00111100", "01011010", "11111111"]}]},
            {"id": 9, "description": "Skull", "width": 8, "height": 4,
             "frames": [{"pixels": ["00111100", "01111110", "01111110", "00111100"]}]},
            {"id": 10, "description": "CD", "width": 8, "height": 4,
             "frames": [{"pixels": ["11111111", "10000001", "10000001", "11111111"]}]},
        ]
    }
    spr_path = tmp_path / "objects.sprite.json"
    spr_path.write_text(json.dumps(spr_json), encoding="utf-8")

    defs_path = tmp_path / "definitions.json"
    defs_path.write_text(json.dumps({"enemies": [], "secrets": secrets_defs, "platform_profiles": []}), encoding="utf-8")

    scene_data = {
        "scene": {"name": "Channels", "tileset": "trees", "background_color": 0},
        "platforms": [
            {"id": "p1", "type": "ground", "position": {"x": 0, "y": 24}, "width": 160, "height": 16},
            {"id": "p2", "type": "ground", "position": {"x": 0, "y": 56}, "width": 160, "height": 16},
        ],
        "objects": objects,
    }
    (tmp_path / "scene1.json").write_text(json.dumps(scene_data), encoding="utf-8")
    man_file = tmp_path / "scenes.json"
    man_file.write_text(json.dumps({"scenes": ["scene1.json"]}), encoding="utf-8")
    return spr_path, defs_path, spr_json


def test_secret_channel_selects_sprite_packing_format(tmp_path: Path):
    """'channel' z definitions.json: 'player' -> bitmapa gracza, 'missiles'/brak -> 5. gracz."""
    secrets_defs = [
        {"id": 1, "name": "Player Key", "sprite_id": 8, "atari_color": 0x1A, "channel": "player"},
        {"id": 2, "name": "Missile Skull", "sprite_id": 9, "atari_color": 0xFC, "channel": "missiles"},
        {"id": 3, "name": "Default CD", "sprite_id": 10, "atari_color": 0x3C},  # brak 'channel'
    ]
    objects = [
        {"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 20},
        {"id": 2, "type": "secret", "definition_id": 2, "platform_id": "p2", "x": 60},
    ]
    spr_path, defs_path, spr_json = _channel_fixture(tmp_path, secrets_defs, objects)
    man_file = tmp_path / "scenes.json"

    # 'channel' musi przetrwać kroki powiązania sprite'ów (resolved -> compile_sprites/scenes)
    resolved_path = tmp_path / "definitions_resolved.json"
    resolve_definitions(defs_path, spr_path, resolved_path)
    resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    assert [s.get("channel") for s in resolved["secrets"]] == ["player", "missiles", None]

    roles, _, _ = determine_sprite_roles_from_scenes(
        man_file, resolved_path, scenes_dir=tmp_path, sprites_path=spr_path
    )
    assert roles[8] == "player"
    assert roles[9] == "missiles"
    assert roles[10] == "missiles"  # brak 'channel' = zachowanie sprzed zmiany

    parsed = parse_sprites_json(
        spr_path, mode="missiles", scenes_manifest_path=man_file, definitions_path=resolved_path
    )
    assert parsed[8].format == "player"
    assert parsed[9].format == "missiles"
    assert parsed[10].format == "missiles"
    assert parsed[8].frames[0].rows == [
        pack_row_to_player_bitmap(r) for r in spr_json["sprites"][0]["frames"][0]["pixels"]
    ]
    assert parsed[9].frames[0].rows == [
        pack_row_to_5th_player_missiles(r) for r in spr_json["sprites"][1]["frames"][0]["pixels"]
    ]



def test_secret_channel_conflict_when_one_sprite_needs_both_formats(tmp_path: Path):
    """Ten sam sprite użyty przez sekret 'player' i 'missiles' -> SpriteRoleConflictError."""
    secrets_defs = [
        {"id": 1, "name": "Player Key", "sprite_id": 8, "atari_color": 0x1A, "channel": "player"},
        {"id": 2, "name": "Missile Key", "sprite_id": 8, "atari_color": 0x1A, "channel": "missiles"},
    ]
    objects = [
        {"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 20},
        {"id": 2, "type": "secret", "definition_id": 2, "platform_id": "p2", "x": 60},
    ]
    spr_path, defs_path, _ = _channel_fixture(tmp_path, secrets_defs, objects)
    man_file = tmp_path / "scenes.json"

    with pytest.raises(SpriteRoleConflictError, match="nie może być użyty jednocześnie na kanale"):
        determine_sprite_roles_from_scenes(
            man_file, defs_path, scenes_dir=tmp_path, sprites_path=spr_path
        )


def test_secret_channel_rejects_unknown_value(tmp_path: Path):
    """Nieznana wartość 'channel' -> SpriteValidationError z listą dozwolonych wartości."""
    secrets_defs = [{"id": 1, "name": "Key", "sprite_id": 8, "atari_color": 0x1A, "channel": "fifth"}]
    objects = [{"id": 1, "type": "secret", "definition_id": 1, "platform_id": "p1", "x": 20}]
    spr_path, defs_path, _ = _channel_fixture(tmp_path, secrets_defs, objects)
    man_file = tmp_path / "scenes.json"

    with pytest.raises(SpriteValidationError, match="nieznany 'channel' sekretu"):
        determine_sprite_roles_from_scenes(
            man_file, defs_path, scenes_dir=tmp_path, sprites_path=spr_path
        )

