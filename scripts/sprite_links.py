"""Sprite linkage and numeric ID resolution for Atari 8-bit pipeline.

Kluczem powiązania typ/obiekt -> sprite jest wyłącznie numeryczny `sprite_id`.
Nazwy sprite'ów pełnią wyłącznie funkcję informacyjną w logach/narzędziach.
Pole 'sprite' (nazwa) jest obsługiwane wyłącznie dla zgodności wstecznej z ostrzeżeniem.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional
import warnings


class SpriteLinkError(ValueError):
    """Błąd rozstrzygania powiązania sprite'a (brak ID, nieistniejące ID, duplikat ID)."""
    pass


class SpriteRegistry:
    """Rejestr definicji sprite'ów załadowanych z pliku Sprite Studio JSON."""

    def __init__(self, sprites_path: Path | str) -> None:
        self.path = Path(sprites_path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Błąd: plik definicji sprite'ów nie istnieje: {self.path}")

        data = json.loads(self.path.read_text(encoding="utf-8"))
        raw_sprites = data.get("sprites", [])

        self.sprites_by_id: dict[int, dict[str, Any]] = {}
        self.id_to_name: dict[int, str] = {}
        self.name_to_id: dict[str, int] = {}

        for s in raw_sprites:
            if "id" not in s:
                raise SpriteLinkError(f"Błąd pliku sprite'ów '{self.path.name}': brak pola 'id' w definicji sprite'a.")
            try:
                sid = int(s["id"])
            except (ValueError, TypeError):
                raise SpriteLinkError(f"Błąd pliku sprite'ów '{self.path.name}': nieprawidłowe ID sprite'a '{s['id']}'.")

            if sid in self.sprites_by_id:
                raise SpriteLinkError(
                    f"Błąd pliku sprite'ów '{self.path.name}': zduplikowane ID sprite'a {sid}."
                )

            raw_desc = str(s.get("description", "")).strip()
            if not raw_desc:
                raw_desc = f"Sprite_{sid}"

            self.sprites_by_id[sid] = s
            self.id_to_name[sid] = raw_desc
            norm_name = raw_desc.lower()
            if norm_name not in self.name_to_id:
                self.name_to_id[norm_name] = sid

    def format_available_sprites(self) -> str:
        """Zwraca czytelną listę dostępnych sprite'ów w formacie 'id: nazwa'."""
        if not self.sprites_by_id:
            return "(brak sprite'ów w pliku)"
        return ", ".join(f"{sid}: {self.id_to_name.get(sid, f'Sprite_{sid}')}" for sid in sorted(self.sprites_by_id.keys()))

    def get_all_names(self) -> list[str]:
        """Zwraca listę nazw wszystkich sprite'ów."""
        return list(self.id_to_name.values())

    def resolve_by_id(self, sprite_id: int, context: str = "") -> tuple[int, str]:
        """Rozstrzyga sprite_id do krotki (sprite_id, nazwa).
        
        W przypadku nieistniejącego ID zgłasza czytelny błąd po polsku z listą dostępnych sprite'ów.
        """
        if sprite_id in self.sprites_by_id:
            return sprite_id, self.id_to_name.get(sprite_id, f"Sprite_{sprite_id}")
        ctx_str = f" ({context})" if context else ""
        avail = self.format_available_sprites()
        raise SpriteLinkError(
            f"Błąd{ctx_str}: podany sprite_id={sprite_id} nie istnieje w pliku sprite'ów. "
            f"Dostępne sprite'y: [{avail}]."
        )

    def resolve_by_name(self, name: str, context: str = "") -> tuple[int, str]:
        """Rozstrzyga nazwę sprite'a (ścieżka zgodności wstecznej dla pola 'sprite')."""
        if not isinstance(name, str) or not name.strip():
            raise SpriteLinkError(f"Błąd{f' ({context})' if context else ''}: pusta nazwa sprite'a.")

        clean_name = name.strip()
        norm_name = clean_name.lower()

        if norm_name in self.name_to_id:
            sid = self.name_to_id[norm_name]
            return sid, self.id_to_name[sid]

        avail = self.format_available_sprites()
        raise SpriteLinkError(
            f"Błąd rozstrzygania przestarzałego pola 'sprite'{f' ({context})' if context else ''}: "
            f"nieznana nazwa sprite'a '{clean_name}'. Dostępne sprite'y: [{avail}]."
        )

    def find_by_name(self, name: str) -> Optional[dict[str, Any]]:
        """Zwraca surowy słownik sprite'a według nazwy (lub None)."""
        norm_name = str(name).strip().lower()
        if norm_name in self.name_to_id:
            sid = self.name_to_id[norm_name]
            return self.sprites_by_id.get(sid)
        return None

    def get_by_id(self, sprite_id: int) -> str:
        """Zwraca nazwę sprite'a dla danego ID lub zgłasza błąd."""
        if sprite_id in self.id_to_name:
            return self.id_to_name[sprite_id]
        avail = self.format_available_sprites()
        raise SpriteLinkError(
            f"Nieznany sprite ID {sprite_id}. Dostępne sprite'y: [{avail}]."
        )


def resolve_object_sprite(
    obj: dict[str, Any],
    catalog_item: Optional[dict[str, Any] | Any],
    registry: SpriteRegistry,
    scene_name: str = "",
    scene_file: str = "",
) -> tuple[int, str, bool]:
    """Rozstrzyga sprite obiektu sceny wg priorytetu:
    1. Jawny sprite_id w obiekcie sceny
    2. Przestarzały jawny 'sprite' (nazwa) w obiekcie sceny (z ostrzeżeniem)
    3. Domyślny sprite_id w typie katalogu
    4. Przestarzały 'sprite' (nazwa) w typie katalogu (z ostrzeżeniem)
    5. Brak powiązania -> SpriteLinkError
    
    Zwraca (sprite_id, sprite_name, is_legacy).
    """
    oid = obj.get("id", "?")
    otype = obj.get("type", "unknown")
    def_id = obj.get("definition_id")
    ctx = f"scena '{scene_name}' ({scene_file}), obiekt '{oid}' ({otype}, typ katalogu {def_id})"

    # 1. Jawny sprite_id w obiekcie sceny
    raw_sprite_id = obj.get("sprite_id")
    if raw_sprite_id is not None and str(raw_sprite_id).strip() != "" and str(raw_sprite_id).lower() != "none":
        try:
            sid_num = int(raw_sprite_id)
        except (ValueError, TypeError):
            raise SpriteLinkError(f"{ctx}: nieprawidłowa wartość 'sprite_id': '{raw_sprite_id}'.")
        sid, sname = registry.resolve_by_id(sid_num, context=ctx)
        return sid, sname, False

    # 2. Przestarzały jawny sprite (nazwa) w obiekcie sceny
    raw_sprite = obj.get("sprite")
    if raw_sprite is not None and str(raw_sprite).strip() and str(raw_sprite).lower() != "none":
        warnings.warn(
            f"Ostrzeżenie: {ctx} używa przestarzałego pola 'sprite': '{raw_sprite}'. "
            f"Zalecane pole 'sprite_id' z numerem ID sprite'a.",
            UserWarning,
            stacklevel=2,
        )
        sid, sname = registry.resolve_by_name(str(raw_sprite).strip(), context=ctx)
        return sid, sname, True

    # 3. Domyślny sprite_id w typie katalogu
    if catalog_item is not None:
        cat_sid = getattr(catalog_item, "sprite_id", None)
        if cat_sid is None and isinstance(catalog_item, dict):
            cat_sid = catalog_item.get("sprite_id")
        if cat_sid is not None and str(cat_sid).strip() != "" and str(cat_sid).lower() != "none":
            try:
                cat_sid_num = int(cat_sid)
            except (ValueError, TypeError):
                raise SpriteLinkError(f"Typ katalogu {def_id}: nieprawidłowa wartość 'sprite_id': '{cat_sid}'.")
            sid, sname = registry.resolve_by_id(cat_sid_num, context=f"katalog typ {def_id}")
            return sid, sname, False

    # 4. Przestarzały sprite (nazwa) w typie katalogu
    if catalog_item is not None:
        cat_sprite = getattr(catalog_item, "sprite", None)
        if cat_sprite is None and isinstance(catalog_item, dict):
            cat_sprite = catalog_item.get("sprite")
        if cat_sprite is not None and str(cat_sprite).strip() and str(cat_sprite).lower() != "none":
            warnings.warn(
                f"Ostrzeżenie: typ katalogu {def_id} używa przestarzałego pola 'sprite': '{cat_sprite}'. "
                f"Zalecane pole 'sprite_id' z numerem ID sprite'a.",
                UserWarning,
                stacklevel=2,
            )
            cat_ctx = f"katalog typ {def_id}"
            sid, sname = registry.resolve_by_name(str(cat_sprite).strip(), context=f"{ctx} -> {cat_ctx}")
            return sid, sname, True

    # 5. Brak powiązania
    raise SpriteLinkError(
        f"Błąd w scenie '{scene_name}' ({scene_file}): obiekt '{oid}' ({otype}, typ katalogu {def_id}) "
        f"nie ma przypisanego sprite_id w scenie ani w katalogu."
    )


def format_resolution_table(entries: list[dict[str, Any]]) -> str:
    """Formatuje tabelę rozstrzygnięć powiązań sprite'ów (informacja w buildzie)."""
    lines: list[str] = [
        "",
        "=" * 94,
        "TABELA ROZSTRZYGNIEC POWIAZAN SPRITE'OW (Informacja kompilacji)",
        "=" * 94,
        f"{'Zrodlo / Element':<42} | {'sprite_id':^9} | {'Nazwa sprite\'a':<18} | {'Rola logiczna':<18}",
        "-" * 42 + "-+-" + "-" * 9 + "-+-" + "-" * 18 + "-+-" + "-" * 18,
    ]
    for e in entries:
        src = str(e.get("source", ""))[:42]
        sid = str(e.get("sprite_id", "?"))
        name = str(e.get("sprite_name", ""))[:18]
        role = str(e.get("role", ""))[:18]
        lines.append(f"{src:<42} | {sid:^9} | {name:<18} | {role:<18}")
    lines.append("=" * 94)
    lines.append("")
    return "\n".join(lines)


def resolve_definitions(
    definitions_path: Path,
    sprites_path: Path,
    output_path: Optional[Path] = None,
    print_table: bool = True,
) -> dict[str, Any]:
    """Rozstrzyga powiązania katalogu definitions.json i generuje gen/definitions_resolved.json."""
    if not definitions_path.is_file():
        raise FileNotFoundError(f"Błąd: plik katalogu nie istnieje: {definitions_path}")

    registry = SpriteRegistry(sprites_path)
    defs = json.loads(definitions_path.read_text(encoding="utf-8"))

    resolution_entries: list[dict[str, Any]] = []

    for idx, enemy in enumerate(defs.get("enemies", [])):
        ename = enemy.get("name", f"Enemy_{idx+1}")
        eid = enemy.get("id", idx + 1)
        ctx = f"katalog: wróg '{ename}' (ID {eid})"

        # 1. sprite_id
        if enemy.get("sprite_id") is not None and str(enemy["sprite_id"]).strip() != "" and str(enemy["sprite_id"]).lower() != "none":
            try:
                sid_num = int(enemy["sprite_id"])
            except (ValueError, TypeError):
                raise SpriteLinkError(f"{ctx}: nieprawidłowa wartość 'sprite_id': '{enemy.get('sprite_id')}'.")
            sid, resolved_name = registry.resolve_by_id(sid_num, context=ctx)
        # 2. legacy sprite (name)
        elif enemy.get("sprite") is not None and str(enemy["sprite"]).strip() and str(enemy["sprite"]).lower() != "none":
            warnings.warn(
                f"Ostrzeżenie: {ctx} w '{definitions_path.name}' używa przestarzałego pola 'sprite': '{enemy['sprite']}'. "
                f"Zalecane pole 'sprite_id'.",
                UserWarning,
                stacklevel=2,
            )
            sid, resolved_name = registry.resolve_by_name(str(enemy["sprite"]).strip(), context=ctx)
        else:
            raise SpriteLinkError(
                f"Błąd w '{definitions_path.name}': {ctx} nie posiada pola 'sprite_id'."
            )

        enemy["sprite_id"] = sid
        enemy["sprite"] = resolved_name
        resolution_entries.append({
            "source": f"Katalog: Wróg typ {eid} ('{ename}')",
            "sprite_id": sid,
            "sprite_name": resolved_name,
            "role": "Wróg (Player)",
        })

    for idx, secret in enumerate(defs.get("secrets", [])):
        sname = secret.get("name", f"Secret_{idx+1}")
        sid_val = secret.get("id", idx + 1)
        ctx = f"katalog: sekret '{sname}' (ID {sid_val})"

        # 1. sprite_id
        if secret.get("sprite_id") is not None and str(secret["sprite_id"]).strip() != "" and str(secret["sprite_id"]).lower() != "none":
            try:
                sid_num = int(secret["sprite_id"])
            except (ValueError, TypeError):
                raise SpriteLinkError(f"{ctx}: nieprawidłowa wartość 'sprite_id': '{secret.get('sprite_id')}'.")
            sid, resolved_name = registry.resolve_by_id(sid_num, context=ctx)
        # 2. legacy sprite (name)
        elif secret.get("sprite") is not None and str(secret["sprite"]).strip() and str(secret["sprite"]).lower() != "none":
            warnings.warn(
                f"Ostrzeżenie: {ctx} w '{definitions_path.name}' używa przestarzałego pola 'sprite': '{secret['sprite']}'. "
                f"Zalecane pole 'sprite_id'.",
                UserWarning,
                stacklevel=2,
            )
            sid, resolved_name = registry.resolve_by_name(str(secret["sprite"]).strip(), context=ctx)
        else:
            raise SpriteLinkError(
                f"Błąd w '{definitions_path.name}': {ctx} nie posiada pola 'sprite_id'."
            )

        secret["sprite_id"] = sid
        secret["sprite"] = resolved_name
        resolution_entries.append({
            "source": f"Katalog: Sekret typ {sid_val} ('{sname}')",
            "sprite_id": sid,
            "sprite_name": resolved_name,
            "role": "Sekret (Pociski)",
        })

    if print_table:
        print(format_resolution_table(resolution_entries))

    if output_path is not None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(defs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return defs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rozstrzyga sprite_id w definitions.json i generuje definitions_resolved.json"
    )
    parser.add_argument(
        "--definitions",
        "-d",
        type=Path,
        default=Path("scenes/definitions.json"),
        help="Ścieżka do autorskiego definitions.json",
    )
    parser.add_argument(
        "--sprites",
        "-s",
        type=Path,
        default=Path("sprites/objects.sprite.json"),
        help="Ścieżka do objects.sprite.json",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("gen/definitions_resolved.json"),
        help="Ścieżka wyjściowa definitions_resolved.json",
    )
    args = parser.parse_args()

    try:
        resolve_definitions(args.definitions, args.sprites, args.output, print_table=True)
        return 0
    except Exception as err:
        print(f"BŁĄD: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
