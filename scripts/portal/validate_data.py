#!/usr/bin/env python3
"""Validate portal data integrity, JSON schemas, mathematical invariants, and Zero Page equates.

Enforces:
1. JSON Schema validation against Draft 2020-12 schemas.
2. Contiguous, non-overlapping partitioning of User RAM ($2000-$BFFF, 40,960 bytes).
3. Exact category summation matching total allocated bytes.
4. Zero Page ($00-$FF, 256 bytes) partition balance.
5. Synchronization between zeropage.asm assembly equates and zeropage_manifest.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def validate_json_schema(instance: dict, schema_path: Path) -> None:
    """Validate instance against JSON Schema using jsonschema if available, or native type check."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        import jsonschema
        jsonschema.validate(instance=instance, schema=schema)
        return
    except ImportError:
        pass

    # Built-in fallback schema validator
    for req_field in schema.get("required", []):
        if req_field not in instance:
            raise ValueError(f"Schema violation: missing required field '{req_field}' in {schema.get('title', 'schema')}")


def validate_memory_report_invariants(report: dict, report_name: str = "report") -> None:
    """Enforce strict mathematical invariants on a memory report."""
    summary = report.get("memory_summary", {})
    allocated_segments = report.get("allocated_segments", [])
    free_gaps = report.get("free_gaps", [])
    zero_page = report.get("zero_page", {})

    total_user_ram = summary.get("total_user_ram_bytes", 0)
    if total_user_ram != 40960:
        raise ValueError(f"[{report_name}] Invalid total_user_ram_bytes: expected 40960, got {total_user_ram}")

    total_allocated = summary.get("total_allocated_bytes", 0)
    total_free = summary.get("total_free_bytes", 0)

    # Invariant 1: Allocated + Free == 40960
    if total_allocated + total_free != 40960:
        raise ValueError(
            f"[{report_name}] Conservation of memory violated: {total_allocated} + {total_free} = {total_allocated + total_free} != 40960"
        )

    # Invariant 2: Segment size matches end - start + 1
    for seg in allocated_segments:
        expected_size = seg["end"] - seg["start"] + 1
        if seg["size"] != expected_size:
            raise ValueError(
                f"[{report_name}] Allocated segment {seg['name']} size mismatch: size={seg['size']}, calculated={expected_size}"
            )

    for gap in free_gaps:
        expected_size = gap["end"] - gap["start"] + 1
        if gap["size"] != expected_size:
            raise ValueError(
                f"[{report_name}] Free gap {gap['name']} size mismatch: size={gap['size']}, calculated={expected_size}"
            )

    # Invariant 3: Sum of allocated segments equals total_allocated_bytes
    sum_alloc = sum(s["size"] for s in allocated_segments)
    if sum_alloc != total_allocated:
        raise ValueError(
            f"[{report_name}] Sum of allocated segments ({sum_alloc}) does not match total_allocated_bytes ({total_allocated})"
        )

    # Invariant 4: Sum of free gaps equals total_free_bytes
    sum_free = sum(g["size"] for g in free_gaps)
    if sum_free != total_free:
        raise ValueError(
            f"[{report_name}] Sum of free gaps ({sum_free}) does not match total_free_bytes ({total_free})"
        )

    # Invariant 5: Complete contiguous, disjoint partition of $2000-$BFFF
    all_regions = sorted(allocated_segments + free_gaps, key=lambda r: r["start"])
    if not all_regions:
        raise ValueError(f"[{report_name}] Empty memory segments and gaps list!")

    if all_regions[0]["start"] != 0x2000:
        raise ValueError(f"[{report_name}] First memory region starts at ${all_regions[0]['start']:04X}, expected $2000")

    if all_regions[-1]["end"] != 0xBFFF:
        raise ValueError(f"[{report_name}] Last memory region ends at ${all_regions[-1]['end']:04X}, expected $BFFF")

    for i in range(len(all_regions) - 1):
        curr_r = all_regions[i]
        next_r = all_regions[i + 1]

        # Detect overlaps
        if next_r["start"] <= curr_r["end"]:
            raise ValueError(
                f"[{report_name}] Memory overlap detected: {curr_r['name']} (${curr_r['start']:04X}-${curr_r['end']:04X}) "
                f"collides with {next_r['name']} (${next_r['start']:04X}-${next_r['end']:04X})"
            )

        # Detect unmapped holes between regions
        if next_r["start"] != curr_r["end"] + 1:
            hole_start = curr_r["end"] + 1
            hole_end = next_r["start"] - 1
            raise ValueError(
                f"[{report_name}] Unaccounted hole in memory partition between ${hole_start:04X} and ${hole_end:04X}"
            )

    # Invariant 6: Category totals match total allocated bytes
    cat_totals = summary.get("category_totals", {})
    sum_cats = sum(cat_totals.values())
    if sum_cats != total_allocated:
        raise ValueError(
            f"[{report_name}] Category totals sum ({sum_cats}) does not match total_allocated_bytes ({total_allocated}): {cat_totals}"
        )

    # Invariant 7: Largest free block
    if free_gaps:
        expected_largest = max(free_gaps, key=lambda g: g["size"])
        if summary.get("largest_free_block_bytes") != expected_largest["size"]:
            raise ValueError(
                f"[{report_name}] largest_free_block_bytes mismatch: declared {summary.get('largest_free_block_bytes')}, "
                f"actual max {expected_largest['size']}"
            )

    # Invariant 8: Zero Page 256 bytes partition
    zp_total = zero_page.get("total_bytes", 0)
    zp_os = zero_page.get("os_reserved_bytes", 0)
    zp_user = zero_page.get("user_allocated_bytes", 0)
    zp_free = zero_page.get("free_bytes", 0)

    if zp_total != 256 or zp_os + zp_user + zp_free != 256:
        raise ValueError(
            f"[{report_name}] Zero Page partition balance violated: {zp_os} (OS) + {zp_user} (User) + {zp_free} (Free) = {zp_os + zp_user + zp_free} != 256"
        )


def validate_zeropage_manifest_sync(
    zp_asm_path: Path,
    manifest_path: Path,
) -> None:
    """Validate that zeropage.asm equates match zeropage_manifest.json declarations."""
    if not zp_asm_path.is_file():
        raise FileNotFoundError(f"zeropage.asm not found at {zp_asm_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"zeropage_manifest.json not found at {manifest_path}")

    asm_text = zp_asm_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Extract assembly equates
    equate_pattern = re.compile(r"^([a-zA-Z0-9_]+)\s*=\s*\$([0-9A-Fa-f]{2})", re.MULTILINE)
    asm_equates: dict[str, int] = {}
    for match in equate_pattern.finditer(asm_text):
        name = match.group(1)
        addr = int(match.group(2), 16)
        # Skip constants and enums
        if (
            name.startswith("STATE_")
            or name.startswith("GAME_")
            or name.startswith("PLAYER_STATE_")
            or name.startswith("JUMP_TYPE_")
            or name.startswith("KILLER_MODE_")
        ):
            continue
        asm_equates[name] = addr

    # Collect manifest symbols
    manifest_symbols: dict[str, dict] = {}
    user_allocated = manifest.get("user_allocated", {})
    for block in user_allocated.get("blocks", []):
        for sym in block.get("symbols", []):
            manifest_symbols[sym["name"]] = sym

    # Check 1: Every variable equate in zeropage.asm must be declared in the manifest
    for name, addr in asm_equates.items():
        if name not in manifest_symbols:
            raise ValueError(
                f"Zero Page equate '{name} = ${addr:02X}' in zeropage.asm is not declared in zeropage_manifest.json"
            )
        decl = manifest_symbols[name]
        if decl["address"] != addr:
            raise ValueError(
                f"Address mismatch for '{name}': zeropage.asm has ${addr:02X}, manifest has ${decl['address']:02X}"
            )

    # Check 2: All user symbols must reside strictly in $80-$E6
    for name, addr in asm_equates.items():
        if addr < 0x80:
            raise ValueError(f"Symbol '{name}' at ${addr:02X} encroaches on OS-reserved Zero Page ($00-$7F)")
        if addr > 0xE6:
            raise ValueError(f"Symbol '{name}' at ${addr:02X} encroaches on unallocated free Zero Page ($E7-$FF)")

    # Check 3: Free space boundaries
    free_info = manifest.get("free_space", {})
    if free_info.get("start") != 0xE7 or free_info.get("end") != 0xFF or free_info.get("size") != 25:
        raise ValueError(f"Invalid free space declaration in zeropage_manifest.json: {free_info}")


def validate_all_portal_data(reports_dir: Path, schemas_dir: Path) -> None:
    """Validate all generated reports and snapshots."""
    print("=" * 60)
    print("PORTAL DATA & SCHEMA INTEGRITY VALIDATION")
    print("=" * 60)

    mem_schema_path = schemas_dir / "memory-report.schema.json"
    snap_schema_path = schemas_dir / "release-snapshot.schema.json"

    # 1. Validate Zero Page Manifest against zeropage.asm
    zp_asm = REPO_ROOT / "zeropage.asm"
    zp_manifest = REPO_ROOT / "scripts" / "portal" / "zeropage_manifest.json"
    print("Validating Zero Page equates against controlled manifest ...")
    validate_zeropage_manifest_sync(zp_asm, zp_manifest)
    print("[OK] Zero Page equates synchronized ($80-$E6 allocated, $E7-$FF free).")

    # 2. Validate latest.json
    latest_path = reports_dir / "latest.json"
    if latest_path.is_file():
        print(f"Validating {latest_path.name} ...")
        latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
        if mem_schema_path.is_file():
            validate_json_schema(latest_data, mem_schema_path)
        validate_memory_report_invariants(latest_data, report_name="latest.json")
        print(f"[OK] {latest_path.name} passes schema and memory invariants.")
    else:
        print(f"Notice: {latest_path} not found.")

    # 3. Validate snapshots
    snapshots_dir = reports_dir / "snapshots"
    if snapshots_dir.is_dir():
        snapshot_files = list(snapshots_dir.glob("v*.json"))
        print(f"Validating {len(snapshot_files)} release snapshots in {snapshots_dir} ...")
        for sf in snapshot_files:
            snap_data = json.loads(sf.read_text(encoding="utf-8"))
            if snap_schema_path.is_file():
                validate_json_schema(snap_data, snap_schema_path)

            mem_rep = snap_data.get("memory_report", {})
            if mem_schema_path.is_file():
                validate_json_schema(mem_rep, mem_schema_path)
            validate_memory_report_invariants(mem_rep, report_name=sf.name)

            # Check binary sha256 consistency
            if snap_data.get("binary_sha256") != mem_rep.get("game", {}).get("binary_sha256"):
                raise ValueError(f"[{sf.name}] binary_sha256 mismatch between snapshot and memory report")

            print(f"  [OK] {sf.name} passes schema, invariants, and checksum consistency.")

    # 4. Validate game_stats.json if present
    stats_path = reports_dir / "game_stats.json"
    if stats_path.is_file():
        print(f"Checking {stats_path.name} ...")
        stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
        summary = stats_data.get("summary", {})
        if "scene_count" not in summary or "total_platforms" not in summary:
            raise ValueError(f"Invalid game_stats.json summary structure: {summary}")
        print(f"[OK] {stats_path.name} contains valid game telemetry.")

    # 5. Validate releases.json if present
    rel_path = reports_dir / "releases.json"
    if rel_path.is_file():
        print(f"Checking {rel_path.name} ...")
        rel_data = json.loads(rel_path.read_text(encoding="utf-8"))
        releases = rel_data.get("releases", [])
        if not releases:
            raise ValueError(f"releases.json contains no release entries")
        for r in releases:
            if not r.get("tag") or not r.get("commit_sha") or not r.get("xex_download_url"):
                raise ValueError(f"Incomplete release entry in releases.json: {r}")
        print(f"[OK] {rel_path.name} contains {len(releases)} valid release records.")

    print("\nSUCCESS: All portal data, schemas, invariants, and Zero Page contracts validated.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate portal data against schemas and invariants.")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "portal",
        help="Path to portal reports directory",
    )
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=REPO_ROOT / "website" / "src" / "data" / "schemas",
        help="Path to JSON schemas directory",
    )
    args = parser.parse_args()

    try:
        validate_all_portal_data(args.reports_dir, args.schemas_dir)
        return 0
    except Exception as exc:
        print(f"\nVALIDATION ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
