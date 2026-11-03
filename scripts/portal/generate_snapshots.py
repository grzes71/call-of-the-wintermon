#!/usr/bin/env python3
"""Generate immutable historical release snapshots and latest.json.

Fetches/reads the exact official release binaries from GitHub Releases,
runs the memory analyzer to produce exact MemoryReport data,
extracts frozen game statistics from the matching git commits,
and outputs validated snapshots to reports/portal/snapshots/vX.Y.Z.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_memory_map import (
    parse_xex_segments,
    build_memory_map,
    ZERO_PAGE_ALLOCATIONS,
)
from game_stats import collect_game_stats

OFFICIAL_RELEASES = [
    {
        "tag": "v0.1.0",
        "version": "0.1.0",
        "commit": "b680bdb7020d4655a6c49937402fac7ce87dda61",
        "published_at": "2026-10-30T15:59:43Z",
        "download_url": "https://github.com/grzes71/call-of-the-wintermon/releases/download/v0.1.0/call_of_the_wintermon.xex",
        "expected_size": 40554,
        "expected_sha256": "865e621907604a7a3d4d41c81efcb6867b6041734d52cbf882bbefb0a2390fe6",
        "changelog": (
            "## Co nowego w wersji 0.1.0\n\n"
            "- Pierwsze oficjalne wydanie gry Call of the Wintermon na Atari 8-bit XL/XE.\n"
            "- 7 grywalnych scen z unikalnymi kafelkami i wyzwaniami platformowymi.\n"
            "- 4-kanałowy odtwarzacz muzyczny POKEY, dynamiczny silnik DLI i sprzętowy render Player-Missile."
        ),
    },
    {
        "tag": "v0.2.0",
        "version": "0.2.0",
        "commit": "606da4a660a076977a01d09b4be7362f392de11e",
        "published_at": "2026-10-30T16:20:47Z",
        "download_url": "https://github.com/grzes71/call-of-the-wintermon/releases/download/v0.2.0/call_of_the_wintermon.xex",
        "expected_size": 40554,
        "expected_sha256": "3d047b69eeb1f2af7ad9c3e0297bac03dcc02e98957eb6fecd26068a70f0586c",
        "changelog": (
            "## Co nowego w wersji 0.2.0\n\n"
            "- Automatyzacja numeru wersji w tekście pionowego scrollera.\n"
            "- Optymalizacje przejść między scenami i izolacji przerwań NMI."
        ),
    },
    {
        "tag": "v0.2.1",
        "version": "0.2.1",
        "commit": "f36d906d205f91b32e3076e215687d9ec9a9e458",
        "published_at": "2026-10-30T18:17:25Z",
        "download_url": "https://github.com/grzes71/call-of-the-wintermon/releases/download/v0.2.1/call_of_the_wintermon.xex",
        "expected_size": 40543,
        "expected_sha256": "93038ccefb823cc7117e152f8ff607676f047ee12f41df081dcc1a93ae291be4",
        "changelog": (
            "## Co nowego w wersji 0.2.1\n\n"
            "- Optymalizacja czyszczenia rejestrów GTIA w module game over pętlą indeksowaną (11 bajtów zysku).\n"
            "- Zwiększenie wolnej pamięci RAM poniżej $C000 do 487 bajtów."
        ),
    },
    {
        "tag": "v0.3.0",
        "version": "0.3.0",
        "commit": "166c337c7f8ffa21d208c11d572ee21b346564e3",
        "published_at": "2026-11-03T14:23:25Z",
        "download_url": "https://github.com/grzes71/call-of-the-wintermon/releases/download/v0.3.0/call_of_the_wintermon.xex",
        "expected_size": 40543,
        "expected_sha256": "77fc5f794b69538cf586686cdf18d05c99c5b00730df6e621f39b1e95ee01ff0",
        "changelog": (
            "## Co nowego w wersji 0.3.0\n\n"
            "- Wdrożenie statycznego portalu gry (GitHub Pages) z telemetryką pamięci i archiwum wydań."
        ),
    },
]


def fetch_binary(url: str, expected_size: int, expected_sha256: str) -> bytes:
    """Download binary and verify size and SHA-256 integrity."""
    print(f"Pobieranie {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "CallOfTheWintermon-Builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    actual_size = len(data)
    actual_sha256 = hashlib.sha256(data).hexdigest()

    if actual_size != expected_size:
        raise ValueError(f"Size mismatch for {url}: expected {expected_size}, got {actual_size}")
    if actual_sha256 != expected_sha256:
        raise ValueError(f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual_sha256}")

    return data


def extract_stats_from_commit(commit_sha: str) -> dict[str, int]:
    """Extract game statistics from the tree at commit_sha using git archive / show."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Extract scenes directory from git commit
        tar_cmd = ["git", "archive", commit_sha, "scenes/"]
        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_out, tar_err = tar_proc.communicate()
        if tar_proc.returncode != 0:
            raise RuntimeError(f"git archive failed: {tar_err.decode()}")

        import tarfile
        import io
        with tarfile.open(fileobj=io.BytesIO(tar_out)) as tar:
            tar.extractall(path=tmp_path)

        manifest_path = tmp_path / "scenes" / "scenes.json"
        defs_path = tmp_path / "scenes" / "definitions.json"
        stats = collect_game_stats(manifest_path, defs_path)

        return {
            "scene_count": len(stats.scenes),
            "total_platforms": stats.total_platforms,
            "total_static_platforms": stats.total_static_platforms,
            "total_moving_platforms": stats.total_moving_platforms,
            "total_enemies": stats.total_enemies,
            "total_secrets": stats.total_secrets,
        }


def build_memory_report(
    binary_data: bytes,
    version: str,
    commit_sha: str,
    published_at: str,
    executable_name: str = "call_of_the_wintermon.xex",
) -> dict:
    """Build complete validated MemoryReport dictionary from binary data."""
    raw_segments = parse_xex_segments(binary_data)
    all_regions, free_gaps = build_memory_map(raw_segments)

    total_allocated = sum(r.size for r in all_regions if not r.is_free)
    total_free = sum(r.size for r in all_regions if r.is_free)
    sorted_free = sorted(free_gaps, key=lambda g: g.size, reverse=True)
    largest = sorted_free[0] if sorted_free else None

    category_totals = {
        "CODE": 0,
        "GRAPHICS": 0,
        "BITMAPS": 0,
        "DLIST": 0,
        "PMG": 0,
        "AUDIO": 0,
        "METADATA": 0,
        "DATA": 0,
    }
    for r in all_regions:
        if not r.is_free and r.category in category_totals:
            category_totals[r.category] += r.size

    return {
        "schema_version": "3.2.0",
        "generated_at": published_at,
        "game": {
            "name": "Call of the Wintermon",
            "version": version,
            "target": "Atari 8-bit (XL/XE)",
            "executable": executable_name,
            "binary_size_bytes": len(binary_data),
            "binary_sha256": hashlib.sha256(binary_data).hexdigest(),
        },
        "build": {
            "commit_sha": commit_sha,
            "ref": f"refs/tags/v{version}",
            "mads_version": "2.1.6",
        },
        "memory_summary": {
            "user_ram_start": 8192,
            "user_ram_end": 49151,
            "total_user_ram_bytes": 40960,
            "total_allocated_bytes": total_allocated,
            "total_free_bytes": total_free,
            "utilization_percent": round(total_allocated / 40960 * 100, 2),
            "largest_free_block_bytes": largest.size if largest else 0,
            "largest_free_block_range": f"${largest.start:04X} - ${largest.end:04X}" if largest else "",
            "is_valid": total_allocated <= 40960,
            "category_totals": category_totals,
        },
        "allocated_segments": [
            {
                "start": r.start,
                "end": r.end,
                "start_hex": f"${r.start:04X}",
                "end_hex": f"${r.end:04X}",
                "size": r.size,
                "name": r.name,
                "category": r.category,
                "color": r.color,
                "details": r.details,
            }
            for r in all_regions
            if not r.is_free
        ],
        "free_gaps": [
            {
                "start": g.start,
                "end": g.end,
                "start_hex": f"${g.start:04X}",
                "end_hex": f"${g.end:04X}",
                "size": g.size,
                "name": g.name,
                "category": g.category,
                "color": g.color,
                "details": g.details,
            }
            for g in free_gaps
        ],
        "zero_page": {
            "total_bytes": 256,
            "os_reserved_bytes": 128,
            "user_allocated_bytes": 103,
            "free_bytes": 25,
            "allocations": ZERO_PAGE_ALLOCATIONS,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate immutable historical snapshots from official release assets.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "portal" / "snapshots",
        help="Directory where release snapshot JSON files are saved.",
    )
    parser.add_argument(
        "--latest-file",
        type=Path,
        default=REPO_ROOT / "reports" / "portal" / "latest.json",
        help="Path where latest.json memory report is saved.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    latest_memory_report = None

    for rel in OFFICIAL_RELEASES:
        print(f"\nProcessing release {rel['tag']} ({rel['version']}) ...")
        bin_data = fetch_binary(rel["download_url"], rel["expected_size"], rel["expected_sha256"])
        frozen_stats = extract_stats_from_commit(rel["commit"])
        mem_report = build_memory_report(
            bin_data,
            rel["version"],
            rel["commit"],
            rel["published_at"],
        )

        snapshot = {
            "schema_version": "3.2.0",
            "release_tag": rel["tag"],
            "version": rel["version"],
            "published_at": rel["published_at"],
            "source_commit_sha": rel["commit"],
            "binary_size_bytes": rel["expected_size"],
            "binary_sha256": rel["expected_sha256"],
            "xex_download_url": rel["download_url"],
            "pdf_download_url": None,
            "changelog_body": rel["changelog"],
            "memory_report": mem_report,
            "frozen_game_stats": frozen_stats,
        }

        snapshot_path = args.output_dir / f"{rel['tag']}.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"Generated snapshot: {snapshot_path}")

        latest_memory_report = mem_report

    if latest_memory_report:
        args.latest_file.parent.mkdir(parents=True, exist_ok=True)
        args.latest_file.write_text(json.dumps(latest_memory_report, indent=2), encoding="utf-8")
        print(f"Saved latest memory report to {args.latest_file}")

    print("\nPhase 0 snapshot generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

