#!/usr/bin/env python3
"""Export releases telemetry and changelogs to reports/portal/releases.json.

Fetches GitHub Releases via GitHub API (with optional GITHUB_TOKEN authentication)
and merges them with immutable snapshot telemetry from reports/portal/snapshots/*.json.
Falls back to local snapshot files if the network or GitHub API is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def fetch_github_releases(repo_slug: str, token: str | None = None) -> list[dict]:
    """Fetch releases from GitHub API with optional auth token."""
    url = f"https://api.github.com/repos/{repo_slug}/releases"
    headers = {
        "User-Agent": "CallOfTheWintermon-PortalExporter/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"Warning: Could not fetch releases from GitHub API ({exc}). Falling back to local snapshots.", file=sys.stderr)
        return []


def load_local_snapshots(snapshots_dir: Path) -> dict[str, dict]:
    """Load all local snapshot files indexed by tag name."""
    snapshots: dict[str, dict] = {}
    if not snapshots_dir.is_dir():
        return snapshots

    for f in snapshots_dir.glob("v*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tag = data.get("release_tag", f.stem)
            snapshots[tag] = data
        except Exception as exc:
            print(f"Warning: Failed to load snapshot {f}: {exc}", file=sys.stderr)

    return snapshots


def export_releases_json(
    repo_slug: str,
    snapshots_dir: Path,
    output_path: Path,
    token: str | None = None,
) -> dict:
    """Compile releases.json combining GitHub Release info and immutable snapshots."""
    local_snapshots = load_local_snapshots(snapshots_dir)
    api_releases = fetch_github_releases(repo_slug, token=token)

    releases_list: list[dict] = []
    processed_tags: set[str] = set()

    # Process releases returned by GitHub API
    for rel in api_releases:
        tag = rel.get("tag_name", "")
        if not tag:
            continue
        processed_tags.add(tag)

        # Find matching XEX and PDF assets (including localized PL and EN builds)
        xex_url = None
        xex_pl_url = None
        xex_en_url = None
        pdf_url = None
        for a in rel.get("assets", []):
            aname = a.get("name", "")
            if aname.endswith("_pl.xex"):
                xex_pl_url = a.get("browser_download_url")
            elif aname.endswith("_en.xex"):
                xex_en_url = a.get("browser_download_url")
            elif aname.endswith(".xex"):
                xex_url = a.get("browser_download_url")
            elif aname.endswith(".pdf"):
                pdf_url = a.get("browser_download_url")

        if not xex_pl_url and xex_url:
            xex_pl_url = xex_url

        # Merge with local snapshot data if available
        snap = local_snapshots.get(tag, {})
        mem_rep = snap.get("memory_report", {})
        mem_sum = mem_rep.get("memory_summary", {})
        game_meta = mem_rep.get("game", {})
        frozen_stats = snap.get("frozen_game_stats", {})
        commit_sha = snap.get("source_commit_sha", "") or rel.get("target_commitish", "")

        entry = {
            "tag": tag,
            "tag_name": tag,
            "version": tag.lstrip("v"),
            "name": rel.get("name", f"Release {tag}"),
            "published_at": rel.get("published_at", snap.get("published_at", "")),
            "commit_sha": commit_sha,
            "source_commit_sha": commit_sha,
            "binary_size_bytes": snap.get("binary_size_bytes", game_meta.get("binary_size_bytes", 0)),
            "binary_sha256": snap.get("binary_sha256", game_meta.get("binary_sha256", "")),
            "allocated_user_ram_bytes": mem_sum.get("total_allocated_bytes", 0),
            "free_user_ram_bytes": mem_sum.get("total_free_bytes", 0),
            "utilization_percent": mem_sum.get("utilization_percent", 0.0),
            "largest_free_block_bytes": mem_sum.get("largest_free_block_bytes", 0),
            "largest_free_block_range": mem_sum.get("largest_free_block_range", ""),
            "scene_count": frozen_stats.get("scene_count", 0),
            "enemy_count": frozen_stats.get("total_enemies", 0),
            "secret_count": frozen_stats.get("total_secrets", 0),
            "xex_download_url": xex_url or snap.get("xex_download_url", ""),
            "xex_pl_download_url": xex_pl_url or snap.get("xex_pl_download_url") or xex_url or snap.get("xex_download_url", ""),
            "xex_en_download_url": xex_en_url or snap.get("xex_en_download_url"),
            "pdf_download_url": pdf_url or snap.get("pdf_download_url"),
            "changelog_body": rel.get("body") or snap.get("changelog_body", ""),
        }
        releases_list.append(entry)

    # Add any local snapshots not returned by the API (offline fallback)
    for tag, snap in sorted(local_snapshots.items(), reverse=True):
        if tag in processed_tags:
            continue
        mem_rep = snap.get("memory_report", {})
        mem_sum = mem_rep.get("memory_summary", {})
        game_meta = mem_rep.get("game", {})
        frozen_stats = snap.get("frozen_game_stats", {})

        entry = {
            "tag": tag,
            "version": snap.get("version", tag.lstrip("v")),
            "published_at": snap.get("published_at", ""),
            "commit_sha": snap.get("source_commit_sha", ""),
            "binary_size_bytes": snap.get("binary_size_bytes", game_meta.get("binary_size_bytes", 0)),
            "binary_sha256": snap.get("binary_sha256", game_meta.get("binary_sha256", "")),
            "allocated_user_ram_bytes": mem_sum.get("total_allocated_bytes", 0),
            "free_user_ram_bytes": mem_sum.get("total_free_bytes", 0),
            "utilization_percent": mem_sum.get("utilization_percent", 0.0),
            "largest_free_block_bytes": mem_sum.get("largest_free_block_bytes", 0),
            "largest_free_block_range": mem_sum.get("largest_free_block_range", ""),
            "scene_count": frozen_stats.get("scene_count", 0),
            "enemy_count": frozen_stats.get("total_enemies", 0),
            "secret_count": frozen_stats.get("total_secrets", 0),
            "xex_download_url": snap.get("xex_download_url", ""),
            "pdf_download_url": snap.get("pdf_download_url"),
            "changelog_body": snap.get("changelog_body", ""),
        }
        releases_list.append(entry)

    # Sort releases descending by version/tag
    releases_list.sort(key=lambda r: r.get("tag", ""), reverse=True)

    result = {
        "schema_version": "3.2.0",
        "releases": releases_list,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(releases_list)} releases to {output_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export release metadata to reports/portal/releases.json")
    parser.add_argument(
        "--repo",
        type=str,
        default="grzes71/call-of-the-wintermon",
        help="GitHub repository slug (e.g. grzes71/call-of-the-wintermon)",
    )
    parser.add_argument(
        "--snapshots-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "portal" / "snapshots",
        help="Directory containing release snapshots",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "portal" / "releases.json",
        help="Output path for releases.json",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    try:
        export_releases_json(args.repo, args.snapshots_dir, args.output, token=token)
        return 0
    except Exception as exc:
        print(f"Error exporting releases: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

