"""Game statistics compiler and reporter for Atari 8-bit game scenes.

Analyzes game scenes manifest and definitions to report:
- Total and per-scene counts of platforms (including static vs moving), enemies, and secrets.
- Breakdown of enemy and secret types/definitions both per scene and globally.

Usage:
    python scripts/game_stats.py
    python scripts/game_stats.py --manifest scenes/scenes.json --definitions scenes/definitions.json
    python scripts/game_stats.py --json
    python scripts/game_stats.py --markdown
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DefinitionInfo:
    id: int
    name: str
    kind: str  # "enemy" or "secret"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneStats:
    filename: str
    name: str
    platform_count: int
    static_platform_count: int
    moving_platform_count: int
    platform_widths: Dict[int, int]
    enemy_count: int
    enemies_by_type: Dict[int, int]  # def_id -> count
    secret_count: int
    secrets_by_type: Dict[int, int]  # def_id -> count


@dataclass
class GameStats:
    scenes: List[SceneStats]
    enemy_definitions: Dict[int, DefinitionInfo]
    secret_definitions: Dict[int, DefinitionInfo]
    total_platforms: int = 0
    total_static_platforms: int = 0
    total_moving_platforms: int = 0
    total_enemies: int = 0
    total_secrets: int = 0
    global_enemies_by_type: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    global_secrets_by_type: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    enemy_scenes: Dict[int, List[str]] = field(default_factory=lambda: defaultdict(list))
    secret_scenes: Dict[int, List[str]] = field(default_factory=lambda: defaultdict(list))

    def compute_totals(self) -> None:
        self.total_platforms = sum(s.platform_count for s in self.scenes)
        self.total_static_platforms = sum(s.static_platform_count for s in self.scenes)
        self.total_moving_platforms = sum(s.moving_platform_count for s in self.scenes)
        self.total_enemies = sum(s.enemy_count for s in self.scenes)
        self.total_secrets = sum(s.secret_count for s in self.scenes)

        self.global_enemies_by_type.clear()
        self.global_secrets_by_type.clear()
        self.enemy_scenes.clear()
        self.secret_scenes.clear()

        for s in self.scenes:
            for def_id, count in s.enemies_by_type.items():
                self.global_enemies_by_type[def_id] += count
                self.enemy_scenes[def_id].append(s.name)
            for def_id, count in s.secrets_by_type.items():
                self.global_secrets_by_type[def_id] += count
                self.secret_scenes[def_id].append(s.name)


def load_definitions(defs_path: Path) -> Tuple[Dict[int, DefinitionInfo], Dict[int, DefinitionInfo]]:
    """Load enemy and secret definitions from definitions.json."""
    if not defs_path.is_file():
        raise FileNotFoundError(f"Definitions file not found: {defs_path}")

    data = json.loads(defs_path.read_text(encoding="utf-8"))

    enemy_defs: Dict[int, DefinitionInfo] = {}
    for item in data.get("enemies", []):
        eid = int(item["id"])
        name = str(item.get("name", f"Enemy #{eid}"))
        enemy_defs[eid] = DefinitionInfo(id=eid, name=name, kind="enemy", extra=item)

    secret_defs: Dict[int, DefinitionInfo] = {}
    for item in data.get("secrets", []):
        sid = int(item["id"])
        name = str(item.get("name", f"Secret #{sid}"))
        secret_defs[sid] = DefinitionInfo(id=sid, name=name, kind="secret", extra=item)

    return enemy_defs, secret_defs


def analyze_scene(scene_path: Path) -> SceneStats:
    """Analyze a single scene JSON file."""
    if not scene_path.is_file():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")

    data = json.loads(scene_path.read_text(encoding="utf-8"))

    scene_meta = data.get("scene", {})
    name = str(scene_meta.get("name", scene_path.stem))

    platforms = data.get("platforms", [])
    static_count = 0
    moving_count = 0
    widths: Dict[int, int] = defaultdict(int)

    for p in platforms:
        w = int(p.get("width", 32))
        widths[w] += 1
        movement = p.get("movement", "none")
        if movement and movement != "none":
            moving_count += 1
        else:
            static_count += 1

    objects = data.get("objects", [])
    enemies_by_type: Dict[int, int] = defaultdict(int)
    secrets_by_type: Dict[int, int] = defaultdict(int)
    enemy_count = 0
    secret_count = 0

    for obj in objects:
        otype = str(obj.get("type", "")).lower()
        def_id = int(obj.get("definition_id", 0))

        if otype == "enemy":
            enemy_count += 1
            enemies_by_type[def_id] += 1
        elif otype in ("secret", "treasure"):
            secret_count += 1
            secrets_by_type[def_id] += 1

    return SceneStats(
        filename=scene_path.name,
        name=name,
        platform_count=len(platforms),
        static_platform_count=static_count,
        moving_platform_count=moving_count,
        platform_widths=dict(sorted(widths.items())),
        enemy_count=enemy_count,
        enemies_by_type=dict(sorted(enemies_by_type.items())),
        secret_count=secret_count,
        secrets_by_type=dict(sorted(secrets_by_type.items())),
    )


def collect_game_stats(manifest_path: Path, definitions_path: Path) -> GameStats:
    """Collect statistics for all scenes in the manifest."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_files = manifest_data.get("scenes", [])

    enemy_defs, secret_defs = load_definitions(definitions_path)
    scenes_dir = manifest_path.parent

    scene_stats_list: List[SceneStats] = []
    for s_fn in scene_files:
        s_path = scenes_dir / s_fn
        scene_stats_list.append(analyze_scene(s_path))

    stats = GameStats(
        scenes=scene_stats_list,
        enemy_definitions=enemy_defs,
        secret_definitions=secret_defs,
    )
    stats.compute_totals()
    return stats


def format_text_report(stats: GameStats) -> str:
    """Format human-readable CLI text report."""
    lines: List[str] = []

    def line(text: str = "") -> None:
        lines.append(text)

    line("=" * 82)
    line("                       STATYSTYKI GRY / GAME STATISTICS                    ")
    line("=" * 82)
    line(f"Liczba scen w grze:    {len(stats.scenes)}")
    line(f"Liczba platform:       {stats.total_platforms} (statyczne: {stats.total_static_platforms}, ruchome: {stats.total_moving_platforms})")
    line(f"Liczba przeciwnikow:   {stats.total_enemies}")
    line(f"Liczba sekretow:       {stats.total_secrets}")
    line("-" * 82)

    # 1. Tabela per scena
    line("\n[1] ZESTAWIENIE KLUCZOWYCH WARTOSCI PER SCENA:")
    line("-" * 82)
    line(f"{'Plik':<22} | {'Nazwa Sceny':<26} | {'Plat. (S/R)':<12} | {'Wrogowie':<8} | {'Sekrety':<7}")
    line("-" * 82)
    for s in stats.scenes:
        plat_str = f"{s.platform_count} ({s.static_platform_count}/{s.moving_platform_count})"
        line(f"{s.filename:<22} | {s.name:<26} | {plat_str:<12} | {s.enemy_count:<8} | {s.secret_count:<7}")
    line("-" * 82)
    line(f"{'RAZEM (TOTAL)':<22} | {'-':<26} | {f'{stats.total_platforms} ({stats.total_static_platforms}/{stats.total_moving_platforms})':<12} | {stats.total_enemies:<8} | {stats.total_secrets:<7}")
    line("=" * 82)

    # 2. Szczegoly dla kazdej sceny
    line("\n[2] SZCZEGOLOWE RODZAJE PRZECIWNIKOW I SEKRETOW DLA KAZDEJ SCENY:")
    line("=" * 82)
    for idx, s in enumerate(stats.scenes, 1):
        line(f"\nScena {idx}: {s.name} [{s.filename}]")
        line(f"  * Platformy ({s.platform_count}): {s.static_platform_count} statycznych, {s.moving_platform_count} ruchomych")
        widths_str = ", ".join(f"{w}px: {c}" for w, c in s.platform_widths.items())
        line(f"    Szerokosci platform: {widths_str}")

        # Przeciwnicy
        line(f"  * Przeciwnicy ({s.enemy_count}):")
        if s.enemies_by_type:
            for def_id, count in s.enemies_by_type.items():
                ename = stats.enemy_definitions.get(def_id, DefinitionInfo(def_id, f"Nieznany #{def_id}", "enemy")).name
                line(f"      - {ename} [ID {def_id}]: {count} szt.")
        else:
            line("      - Brak przeciwnikow")

        # Sekrety
        line(f"  * Sekrety ({s.secret_count}):")
        if s.secrets_by_type:
            for def_id, count in s.secrets_by_type.items():
                sname = stats.secret_definitions.get(def_id, DefinitionInfo(def_id, f"Nieznany #{def_id}", "secret")).name
                line(f"      - {sname} [ID {def_id}]: {count} szt.")
        else:
            line("      - Brak sekretow")

    # 3. Globalne zestawienie rodzajow
    line("\n" + "=" * 82)
    line("[3] GLOBALNY ROZKLAD RODZAJOW PRZECIWNIKOW (CALA GRA):")
    line("-" * 82)
    line(f"{'ID':<4} | {'Nazwa Przeciwnika':<24} | {'Ilosc':<7} | {'Wystepuje w scenach'}")
    line("-" * 82)
    for def_id in sorted(stats.enemy_definitions.keys()):
        edef = stats.enemy_definitions[def_id]
        total_cnt = stats.global_enemies_by_type.get(def_id, 0)
        scenes_str = ", ".join(stats.enemy_scenes.get(def_id, [])) if total_cnt > 0 else "Brak"
        line(f"{def_id:<4} | {edef.name:<24} | {total_cnt:<7} | {scenes_str}")
    line("-" * 82)

    line("\n[4] GLOBALNY ROZKLAD RODZAJOW SEKRETOW (CALA GRA):")
    line("-" * 82)
    line(f"{'ID':<4} | {'Nazwa Sekretu':<24} | {'Ilosc':<7} | {'Wystepuje w scenach'}")
    line("-" * 82)
    for def_id in sorted(stats.secret_definitions.keys()):
        sdef = stats.secret_definitions[def_id]
        total_cnt = stats.global_secrets_by_type.get(def_id, 0)
        scenes_str = ", ".join(stats.secret_scenes.get(def_id, [])) if total_cnt > 0 else "Brak"
        line(f"{def_id:<4} | {sdef.name:<24} | {total_cnt:<7} | {scenes_str}")
    line("=" * 82)

    return "\n".join(lines)


def format_markdown_report(stats: GameStats) -> str:
    """Format markdown report."""
    lines: List[str] = []

    lines.append("# Statystyki Gry Atari Call of the Wintermoon\n")
    lines.append("## Podsumowanie Globalne\n")
    lines.append(f"- **Liczba scen**: {len(stats.scenes)}")
    lines.append(f"- **Liczba platform**: {stats.total_platforms} (statyczne: {stats.total_static_platforms}, ruchome: {stats.total_moving_platforms})")
    lines.append(f"- **Liczba przeciwnikow**: {stats.total_enemies}")
    lines.append(f"- **Liczba sekretow**: {stats.total_secrets}\n")

    lines.append("## Zestawienie wg Scen\n")
    lines.append("| Plik | Nazwa Sceny | Platformy (stat/ruch) | Przeciwnicy | Sekrety |")
    lines.append("|---|---|---|---|---|")
    for s in stats.scenes:
        plat_str = f"{s.platform_count} ({s.static_platform_count}/{s.moving_platform_count})"
        lines.append(f"| `{s.filename}` | {s.name} | {plat_str} | {s.enemy_count} | {s.secret_count} |")
    lines.append(f"| **SUMA** | - | **{stats.total_platforms} ({stats.total_static_platforms}/{stats.total_moving_platforms})** | **{stats.total_enemies}** | **{stats.total_secrets}** |\n")

    lines.append("## Rodzaje Przeciwnikow w Grze\n")
    lines.append("| ID | Nazwa Przeciwnika | Ilosc w Grze | Wystepuje w Scenach |")
    lines.append("|---|---|---|---|")
    for def_id in sorted(stats.enemy_definitions.keys()):
        edef = stats.enemy_definitions[def_id]
        total_cnt = stats.global_enemies_by_type.get(def_id, 0)
        scenes_str = ", ".join(stats.enemy_scenes.get(def_id, [])) if total_cnt > 0 else "Brak"
        lines.append(f"| {def_id} | {edef.name} | {total_cnt} | {scenes_str} |")
    lines.append("")

    lines.append("## Rodzaje Sekretow w Grze\n")
    lines.append("| ID | Nazwa Sekretu | Ilosc w Grze | Wystepuje w Scenach |")
    lines.append("|---|---|---|---|")
    for def_id in sorted(stats.secret_definitions.keys()):
        sdef = stats.secret_definitions[def_id]
        total_cnt = stats.global_secrets_by_type.get(def_id, 0)
        scenes_str = ", ".join(stats.secret_scenes.get(def_id, [])) if total_cnt > 0 else "Brak"
        lines.append(f"| {def_id} | {sdef.name} | {total_cnt} | {scenes_str} |")

    return "\n".join(lines)


def format_json_report(stats: GameStats) -> str:
    """Format JSON report."""
    output = {
        "summary": {
            "scene_count": len(stats.scenes),
            "total_platforms": stats.total_platforms,
            "total_static_platforms": stats.total_static_platforms,
            "total_moving_platforms": stats.total_moving_platforms,
            "total_enemies": stats.total_enemies,
            "total_secrets": stats.total_secrets,
        },
        "enemy_types": [
            {
                "id": def_id,
                "name": stats.enemy_definitions[def_id].name,
                "total_count": stats.global_enemies_by_type.get(def_id, 0),
                "scenes": stats.enemy_scenes.get(def_id, []),
            }
            for def_id in sorted(stats.enemy_definitions.keys())
        ],
        "secret_types": [
            {
                "id": def_id,
                "name": stats.secret_definitions[def_id].name,
                "total_count": stats.global_secrets_by_type.get(def_id, 0),
                "scenes": stats.secret_scenes.get(def_id, []),
            }
            for def_id in sorted(stats.secret_definitions.keys())
        ],
        "scenes": [
            {
                "filename": s.filename,
                "name": s.name,
                "platforms": {
                    "total": s.platform_count,
                    "static": s.static_platform_count,
                    "moving": s.moving_platform_count,
                    "widths": s.platform_widths,
                },
                "enemies": {
                    "total": s.enemy_count,
                    "by_type": [
                        {
                            "id": def_id,
                            "name": stats.enemy_definitions.get(def_id, DefinitionInfo(def_id, f"Unknown #{def_id}", "enemy")).name,
                            "count": count,
                        }
                        for def_id, count in s.enemies_by_type.items()
                    ],
                },
                "secrets": {
                    "total": s.secret_count,
                    "by_type": [
                        {
                            "id": def_id,
                            "name": stats.secret_definitions.get(def_id, DefinitionInfo(def_id, f"Unknown #{def_id}", "secret")).name,
                            "count": count,
                        }
                        for def_id, count in s.secrets_by_type.items()
                    ],
                },
            }
            for s in stats.scenes
        ],
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pokaz kluczowe statystyki gry (platformy, przeciwnicy, sekrety).")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("scenes/scenes.json"),
        help="Sciezka do manifestu scen (domyslnie: scenes/scenes.json)",
    )
    parser.add_argument(
        "--definitions",
        type=Path,
        default=Path("scenes/definitions.json"),
        help="Sciezka do katalogu definicji (domyslnie: scenes/definitions.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Wypisz wynik w formacie JSON",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Wypisz wynik w formacie Markdown",
    )

    args = parser.parse_args()

    try:
        stats = collect_game_stats(args.manifest, args.definitions)
        if args.json:
            print(format_json_report(stats))
        elif args.markdown:
            print(format_markdown_report(stats))
        else:
            print(format_text_report(stats))
        return 0
    except Exception as exc:
        print(f"Blad podczas generowania statystyk: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
