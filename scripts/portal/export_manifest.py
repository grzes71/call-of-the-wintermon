#!/usr/bin/env python3
"""Export manifest.yaml metadata to reports/portal/assets.json.

Compiles SSOT asset specifications (tilesets, fonts, sprites, audio,
narrative texts, scenes, levels) into validated JSON format for the portal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_manifest_yaml(yaml_path: Path) -> dict:
    """Parse manifest.yaml using pyyaml if available, or lightweight native parser."""
    text = yaml_path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass

    # Lightweight fallback parser for manifest.yaml structure
    data: dict = {
        "name": "Call of the Wintermon",
        "version": "0.2.0",
        "target": {},
        "source_code": {},
        "graphics": {"tilesets": [], "fonts": [], "sprites": []},
        "audio": {"music": []},
        "texts": [],
        "scenes": {"levels": []},
        "tools": [],
    }

    current_section = None
    current_sub = None
    current_item: dict | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Top level keys
        if indent == 0 and ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val:
                data[key] = val
            current_section = key
            current_sub = None
            current_item = None
            continue

        # Subsections like graphics:, audio:, scenes:
        if indent == 2 and ":" in stripped and not stripped.startswith("-"):
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if current_section:
                if isinstance(data.get(current_section), dict):
                    if val:
                        data[current_section][key] = val
                    else:
                        current_sub = key
                        if key not in data[current_section]:
                            data[current_section][key] = []
            continue

        # List items
        if stripped.startswith("- "):
            current_item = {}
            if current_section and current_sub and isinstance(data.get(current_section), dict):
                sub_target = data[current_section].get(current_sub)
                if isinstance(sub_target, list):
                    sub_target.append(current_item)
            elif current_section and isinstance(data.get(current_section), list):
                data[current_section].append(current_item)

            item_content = stripped[2:].strip()
            if ":" in item_content:
                k, v = item_content.split(":", 1)
                current_item[k.strip()] = v.strip().strip('"').strip("'")
            continue

        # Item properties
        if current_item is not None and ":" in stripped:
            k, v = stripped.split(":", 1)
            current_item[k.strip()] = v.strip().strip('"').strip("'")

    return data


def export_assets_json(manifest_path: Path, output_path: Path) -> dict:
    """Compile manifest data and verify asset file existence."""
    manifest_data = parse_manifest_yaml(manifest_path)

    # Gather file size telemetry for existing assets
    graphics = manifest_data.get("graphics", {})
    for item in graphics.get("tilesets", []):
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    for item in graphics.get("fonts", []):
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    for item in graphics.get("sprites", []):
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    audio = manifest_data.get("audio", {})
    for item in audio.get("music", []):
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    texts = manifest_data.get("texts", [])
    for item in texts:
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    scenes = manifest_data.get("scenes", {})
    for item in scenes.get("levels", []):
        p = REPO_ROOT / item.get("path", "")
        item["size_bytes"] = p.stat().st_size if p.is_file() else 0
        item["exists"] = p.is_file()

    result = {
        "schema_version": "3.2.0",
        "game_name": manifest_data.get("name", "Call of the Wintermon"),
        "version": manifest_data.get("version", "0.2.1"),
        "target": manifest_data.get("target", {}),
        "graphics": graphics,
        "audio": audio,
        "texts": texts,
        "scenes": scenes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported assets metadata to {output_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export manifest.yaml to portal assets.json")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "manifest.yaml",
        help="Path to manifest.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "portal" / "assets.json",
        help="Output path for assets.json",
    )
    args = parser.parse_args()

    try:
        export_assets_json(args.manifest, args.output)
        return 0
    except Exception as exc:
        print(f"Error exporting manifest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

