#!/usr/bin/env python3
"""Migracja powiązań typów i scen ze sprite'ami na numeryczny sprite_id.

Zastępuje pole 'sprite' (nazwa) numerycznym 'sprite_id' i usuwa pole 'sprite'.
Pozostawia wpisy z samym 'sprite_id' bez zmian.
Usuwa nadpisania w scenach równe wartości z katalogu.
Domyślnie działa w trybie dry-run (bez modyfikacji plików).
Flaga --apply zapisuje zmiany na dysku (tworząc kopie zapasowe *.bak).
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from scripts.sprite_links import SpriteRegistry, SpriteLinkError
except ImportError:
    from sprite_links import SpriteRegistry, SpriteLinkError  # type: ignore


def build_name_registry(sprites_path: Path) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[int, str]]:
    """Buduje mapę unikalnych nazw na ID oraz wykrywa nazwy zduplikowane."""
    data = json.loads(sprites_path.read_text(encoding="utf-8"))
    raw_sprites = data.get("sprites", [])

    name_to_ids: Dict[str, List[int]] = {}
    id_to_name: Dict[int, str] = {}

    for s in raw_sprites:
        sid = int(s["id"])
        desc = str(s.get("description", "")).strip()
        if not desc:
            desc = f"Sprite_{sid}"
        id_to_name[sid] = desc
        norm = desc.lower()
        name_to_ids.setdefault(norm, []).append(sid)

    unique_name_to_id: Dict[str, int] = {}
    duplicated_names: Dict[str, List[int]] = {}

    for norm, sids in name_to_ids.items():
        if len(sids) == 1:
            unique_name_to_id[norm] = sids[0]
        else:
            duplicated_names[norm] = sids

    return unique_name_to_id, duplicated_names, id_to_name


def order_definition_keys(item: Dict[str, Any], is_enemy: bool) -> Dict[str, Any]:
    """Zapewnia identyczną kolejność kluczy jak w zapisie Scene Editora."""
    ordered: Dict[str, Any] = {
        "id": int(item["id"]),
        "name": item.get("name", ""),
        "blink": bool(item.get("blink", False)),
    }
    if "rgb_color" in item and item["rgb_color"] is not None:
        ordered["rgb_color"] = [int(c) for c in item["rgb_color"]]
    if "atari_color" in item and item["atari_color"] is not None:
        ordered["atari_color"] = int(item["atari_color"])
    if not is_enemy and "dependency" in item and item["dependency"] is not None:
        ordered["dependency"] = int(item["dependency"])
    if "sprite_id" in item and item["sprite_id"] is not None:
        ordered["sprite_id"] = int(item["sprite_id"])
    return ordered


def analyze_catalog_migration(
    definitions_data: Dict[str, Any],
    sprites_path: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analizuje katalog typów i migruje pole 'sprite' na 'sprite_id'.
    
    Zwraca (nowy_katalog, migracje_jednoznaczne, wpisy_bez_zmian, wpisy_niejednoznaczne).
    """
    new_defs = copy.deepcopy(definitions_data)
    name_to_id, dup_names, id_to_name = build_name_registry(sprites_path)

    migrated_entries: List[Dict[str, Any]] = []
    unchanged_entries: List[Dict[str, Any]] = []
    ambiguous_entries: List[Dict[str, Any]] = []

    for category in ("enemies", "secrets"):
        is_enemy = (category == "enemies")
        items = new_defs.get(category, [])
        migrated_items: List[Dict[str, Any]] = []

        for item in items:
            t_id = item.get("id")
            name = item.get("name", "")
            raw_sprite = item.get("sprite")
            raw_sprite_id = item.get("sprite_id")

            # Przypadek 1: Ma pole 'sprite' (nazwa)
            if raw_sprite is not None and str(raw_sprite).strip():
                clean_name = str(raw_sprite).strip()
                norm = clean_name.lower()
                if norm in name_to_id:
                    sid = name_to_id[norm]
                    item.pop("sprite", None)
                    item["sprite_id"] = sid
                    migrated_entries.append({
                        "category": category,
                        "id": t_id,
                        "name": name,
                        "old_sprite_name": clean_name,
                        "new_sprite_id": sid,
                        "sprite_desc": id_to_name.get(sid, ""),
                    })
                elif norm in dup_names:
                    ambiguous_entries.append({
                        "category": category,
                        "id": t_id,
                        "name": name,
                        "problem": f"Zduplikowana nazwa sprite'a '{clean_name}' (ID: {dup_names[norm]})",
                    })
                else:
                    ambiguous_entries.append({
                        "category": category,
                        "id": t_id,
                        "name": name,
                        "problem": f"Nieznana nazwa sprite'a '{clean_name}' (brak w objects.sprite.json)",
                    })
            # Przypadek 2: Ma tylko 'sprite_id' (np. Yog-Sothoth, Gold Key)
            elif raw_sprite_id is not None:
                unchanged_entries.append({
                    "category": category,
                    "id": t_id,
                    "name": name,
                    "sprite_id": raw_sprite_id,
                    "sprite_desc": id_to_name.get(int(raw_sprite_id), f"<nieznany ID {raw_sprite_id}>"),
                })
            else:
                ambiguous_entries.append({
                    "category": category,
                    "id": t_id,
                    "name": name,
                    "problem": "Brak pola 'sprite' oraz 'sprite_id'",
                })

            migrated_items.append(order_definition_keys(item, is_enemy))

        new_defs[category] = migrated_items

    return new_defs, migrated_entries, unchanged_entries, ambiguous_entries


def analyze_scenes_migration(
    scenes_manifest_path: Path,
    migrated_definitions: Dict[str, Any],
    sprites_path: Path,
) -> Tuple[Dict[Path, Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analizuje obiekty w scenach: zamienia 'sprite' -> 'sprite_id', usuwa nadmiarowe nadpisania równe katalogowi."""
    scenes_dir = scenes_manifest_path.parent
    manifest = json.loads(scenes_manifest_path.read_text(encoding="utf-8"))

    name_to_id, dup_names, id_to_name = build_name_registry(sprites_path)

    # Mapa domyślnych sprite_id z katalogu: (obj_type, def_id) -> sprite_id
    cat_default_sids: Dict[Tuple[str, Any], Optional[int]] = {}
    for cat in ("enemies", "secrets"):
        c_type = "enemy" if cat == "enemies" else "secret"
        for item in migrated_definitions.get(cat, []):
            d_id = item.get("id")
            s_id = item.get("sprite_id")
            cat_default_sids[(c_type, d_id)] = s_id
            cat_default_sids[(c_type, str(d_id))] = s_id

    modified_scenes: Dict[Path, Dict[str, Any]] = {}
    changes_report: List[Dict[str, Any]] = []
    ambiguous_report: List[Dict[str, Any]] = []

    for sc_info in manifest.get("scenes", []):
        sc_file = sc_info if isinstance(sc_info, str) else sc_info.get("file")
        if not sc_file:
            continue
        sc_path = scenes_dir / sc_file
        if not sc_path.is_file():
            continue

        scene_data = json.loads(sc_path.read_text(encoding="utf-8"))
        scene_changed = False
        scene_name = scene_data.get("scene", {}).get("name", sc_file)

        for obj in scene_data.get("objects", []):
            obj_id = obj.get("id")
            obj_type = obj.get("type")
            def_id = obj.get("definition_id")
            raw_sprite = obj.get("sprite")
            raw_sprite_id = obj.get("sprite_id")

            cat_sid = cat_default_sids.get((obj_type, def_id))

            # Rozstrzygnij numer sprite'a dla obiektu
            resolved_sid = None
            if raw_sprite is not None and str(raw_sprite).strip():
                clean_name = str(raw_sprite).strip()
                norm = clean_name.lower()
                if norm in name_to_id:
                    resolved_sid = name_to_id[norm]
                elif norm in dup_names:
                    ambiguous_report.append({
                        "scene": sc_file,
                        "object_id": obj_id,
                        "problem": f"Zduplikowana nazwa sprite'a '{clean_name}' (ID: {dup_names[norm]})",
                    })
                    continue
                else:
                    ambiguous_report.append({
                        "scene": sc_file,
                        "object_id": obj_id,
                        "problem": f"Nieznana nazwa sprite'a '{clean_name}'",
                    })
                    continue
            elif raw_sprite_id is not None:
                try:
                    resolved_sid = int(raw_sprite_id)
                except (ValueError, TypeError):
                    ambiguous_report.append({
                        "scene": sc_file,
                        "object_id": obj_id,
                        "problem": f"Niepoprawne sprite_id '{raw_sprite_id}'",
                    })
                    continue

            # Sprawdź czy nadpisanie jest równe domyślnemu z katalogu
            if resolved_sid is not None:
                if cat_sid is not None and resolved_sid == cat_sid:
                    # Zbędne nadpisanie równe wartości z katalogu -> usuń
                    had_sprite = "sprite" in obj
                    had_sprite_id = "sprite_id" in obj
                    if had_sprite or had_sprite_id:
                        obj.pop("sprite", None)
                        obj.pop("sprite_id", None)
                        scene_changed = True
                        changes_report.append({
                            "scene": sc_file,
                            "scene_name": scene_name,
                            "object_id": obj_id,
                            "action": "usunięto nadmiarowe nadpisanie równe katalogowi",
                            "sprite_id": resolved_sid,
                        })
                else:
                    # Rzeczywiste nadpisanie różne od katalogu -> ustaw sprite_id, usuń sprite
                    had_sprite = "sprite" in obj
                    old_sid = obj.get("sprite_id")
                    if had_sprite or old_sid != resolved_sid:
                        obj.pop("sprite", None)
                        obj["sprite_id"] = resolved_sid
                        scene_changed = True
                        changes_report.append({
                            "scene": sc_file,
                            "scene_name": scene_name,
                            "object_id": obj_id,
                            "action": "zapisano nadpisanie sprite_id",
                            "sprite_id": resolved_sid,
                        })

        if scene_changed:
            modified_scenes[sc_path] = scene_data

    return modified_scenes, changes_report, ambiguous_report


def run_migration(
    definitions_path: Path,
    sprites_path: Path,
    scenes_manifest_path: Path,
    apply: bool = False,
) -> bool:
    """Uruchamia proces analizy i ew. zastosowania migracji."""
    if not definitions_path.is_file():
        print(f"BŁĄD: Plik katalogu '{definitions_path}' nie istnieje.", file=sys.stderr)
        return False
    if not sprites_path.is_file():
        print(f"BŁĄD: Plik sprite'ów '{sprites_path}' nie istnieje.", file=sys.stderr)
        return False

    defs_data = json.loads(definitions_path.read_text(encoding="utf-8"))

    new_defs, cat_migrated, cat_unchanged, cat_ambiguous = analyze_catalog_migration(
        defs_data, sprites_path
    )

    scenes_modified, scene_changes, scene_ambiguous = analyze_scenes_migration(
        scenes_manifest_path, new_defs, sprites_path
    )

    mode_str = "ZASTOSOWANIE MIGRACJI (--apply)" if apply else "TRYB DRY-RUN (symulacja, brak zapisu na dysku)"

    print("=" * 80)
    print(f"MIGRACJA POWIĄZAŃ SPRITE'ÓW NA NUMERYCZNY SPRITE_ID — {mode_str}")
    print("=" * 80)

    print("\n1. ANALIZA KATALOGU TYPÓW (definitions.json):")
    if cat_migrated:
        print(f"  • Zmigrowane wpisy z pola 'sprite' na 'sprite_id' ({len(cat_migrated)}):")
        for m in cat_migrated:
            print(f"    - [{m['category'].upper()}] ID {m['id']} '{m['name']}': sprite='{m['old_sprite_name']}' -> sprite_id={m['new_sprite_id']} ('{m['sprite_desc']}')")
    else:
        print("  • Brak wpisów wymagających migracji pola 'sprite'.")

    if cat_unchanged:
        print(f"\n  • Wpisy posiadające już wyłącznie numeryczny 'sprite_id' (pozostawione bez zmian) ({len(cat_unchanged)}):")
        for u in cat_unchanged:
            print(f"    - [{u['category'].upper()}] ID {u['id']} '{u['name']}': sprite_id={u['sprite_id']} ('{u['sprite_desc']}')")

    if cat_ambiguous:
        print(f"\n  ⚠️ Niejednoznaczne / problematyczne wpisy w katalogu ({len(cat_ambiguous)}):")
        for a in cat_ambiguous:
            print(f"    - [{a['category'].upper()}] ID {a['id']} '{a['name']}': {a['problem']}")

    print("\n2. ANALIZA SCEN:")
    if scene_changes:
        print(f"  • Zmiany w obiektach scen ({len(scene_changes)}):")
        for sc in scene_changes:
            print(f"    - Scena '{sc['scene']}', obiekt '{sc['object_id']}': {sc['action']} (sprite_id={sc['sprite_id']})")
    else:
        print("  • Brak obiektów scen wymagających modyfikacji (wszystkie obiekty dziedziczą domyślne sprite_id z katalogu).")

    if scene_ambiguous:
        print(f"\n  ⚠️ Problematyczne obiekty w scenach ({len(scene_ambiguous)}):")
        for sa in scene_ambiguous:
            print(f"    - Scena '{sa['scene']}', obiekt '{sa['object_id']}': {sa['problem']}")

    print("\n" + "=" * 80)

    if not apply:
        print("Zakończono w trybie DRY-RUN. Pliki NIE zostały zmodyfikowane.")
        print("Aby zastosować zmiany jednoznaczne i zapisać pliki, uruchom z flagą --apply.")
        print("=" * 80)
        return True

    # Zapis plików
    if cat_ambiguous or scene_ambiguous:
        print("UWAGA: Wykryto niejednoznaczne wpisy. Zmiany zostaną zastosowane tylko dla przypadków jednoznacznych.")

    # 1. Zapis definitions.json
    shutil.copyfile(definitions_path, definitions_path.with_suffix(".json.bak"))
    definitions_path.write_text(json.dumps(new_defs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Zapisano zmigrowany katalog: {definitions_path} (kopia: {definitions_path.name}.bak)")

    # 2. Zapis zmodyfikowanych scen
    for sc_path, sc_data in scenes_modified.items():
        shutil.copyfile(sc_path, sc_path.with_suffix(".json.bak"))
        sc_path.write_text(json.dumps(sc_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[OK] Zaktualizowano scene: {sc_path} (kopia: {sc_path.name}.bak)")

    print("\nZastosowano migrację. Pliki autorskie używają teraz wyłącznie numerycznego sprite_id.")
    print("=" * 80)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Migracja powiązań sprite'ów na numeryczny sprite_id.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Zapisz zmiany w plikach (tworzy kopie *.bak). Domyślnie tryb dry-run.",
    )
    parser.add_argument(
        "--definitions",
        type=Path,
        default=Path("scenes/definitions.json"),
        help="Ścieżka do definitions.json",
    )
    parser.add_argument(
        "--sprites",
        type=Path,
        default=Path("sprites/objects.sprite.json"),
        help="Ścieżka do objects.sprite.json",
    )
    parser.add_argument(
        "--scenes-manifest",
        type=Path,
        default=Path("scenes/scenes.json"),
        help="Ścieżka do manifestu scen (scenes.json)",
    )
    args = parser.parse_args()

    success = run_migration(
        definitions_path=args.definitions,
        sprites_path=args.sprites,
        scenes_manifest_path=args.scenes_manifest,
        apply=args.apply,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
