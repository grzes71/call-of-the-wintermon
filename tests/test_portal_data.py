"""Automated unit and regression tests for Call of the Wintermon portal data pipeline.

Verifies:
1. Mathematical invariants on memory reports (conservation of memory, bounds, contiguity).
2. Segment size exactness and overlap detection.
3. Category summation matching total allocated user RAM.
4. Zero Page equates synchronization between zeropage.asm and zeropage_manifest.json.
5. Invariant enforcement rejecting corrupted or overlapping memory segments.
6. Verification of all official historical release snapshots (v0.1.0, v0.2.0, v0.2.1).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import pytest
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "portal"))

from validate_data import (
    validate_memory_report_invariants,
    validate_zeropage_manifest_sync,
    validate_all_portal_data,
)
from export_manifest import export_assets_json
from export_releases import export_releases_json


@pytest.fixture
def portal_dir() -> Path:
    return REPO_ROOT / "reports" / "portal"


@pytest.fixture
def schemas_dir() -> Path:
    return REPO_ROOT / "website" / "src" / "data" / "schemas"


class TestPortalMemoryInvariants:
    """Validate mathematical exactness and structural contracts on memory reports."""

    def test_latest_memory_report_valid(self, portal_dir: Path) -> None:
        latest_file = portal_dir / "latest.json"
        assert latest_file.is_file(), "latest.json must exist"
        data = json.loads(latest_file.read_text(encoding="utf-8"))

        # Invariants must pass without error
        validate_memory_report_invariants(data, report_name="latest.json")

        summary = data["memory_summary"]
        assert summary["total_allocated_bytes"] + summary["total_free_bytes"] == 40960
        assert summary["total_user_ram_bytes"] == 40960
        assert summary["is_valid"] is True
        assert sum(summary["category_totals"].values()) == summary["total_allocated_bytes"]

    def test_all_release_snapshots_valid(self, portal_dir: Path) -> None:
        snapshots_dir = portal_dir / "snapshots"
        assert snapshots_dir.is_dir(), "snapshots directory must exist"
        snapshot_files = list(snapshots_dir.glob("v*.json"))
        assert len(snapshot_files) >= 3, "At least 3 historical snapshots required (v0.1.0, v0.2.0, v0.2.1)"

        expected_tags = {"v0.1.0", "v0.2.0", "v0.2.1"}
        found_tags = set()

        for sf in snapshot_files:
            snap = json.loads(sf.read_text(encoding="utf-8"))
            found_tags.add(snap["release_tag"])
            assert snap["schema_version"] == "3.2.0"
            assert len(snap["binary_sha256"]) == 64
            assert snap["binary_size_bytes"] > 0
            assert "frozen_game_stats" in snap

            mem = snap["memory_report"]
            validate_memory_report_invariants(mem, report_name=sf.name)
            assert snap["binary_sha256"] == mem["game"]["binary_sha256"]

        assert expected_tags.issubset(found_tags), f"Missing snapshots: {expected_tags - found_tags}"

    def test_detector_catches_memory_overlap(self, portal_dir: Path) -> None:
        latest_file = portal_dir / "latest.json"
        data = json.loads(latest_file.read_text(encoding="utf-8"))

        corrupted = copy.deepcopy(data)
        # Introduce an intentional overlap: shift 2nd allocated segment into the 1st segment
        # without changing segment size or total sum
        if len(corrupted["allocated_segments"]) >= 2:
            seg1_size = corrupted["allocated_segments"][1]["size"]
            corrupted["allocated_segments"][1]["start"] = corrupted["allocated_segments"][0]["start"]
            corrupted["allocated_segments"][1]["end"] = corrupted["allocated_segments"][1]["start"] + seg1_size - 1

        with pytest.raises(ValueError, match="Memory overlap detected"):
            validate_memory_report_invariants(corrupted, report_name="corrupted")

    def test_detector_catches_conservation_violation(self, portal_dir: Path) -> None:
        latest_file = portal_dir / "latest.json"
        data = json.loads(latest_file.read_text(encoding="utf-8"))

        corrupted = copy.deepcopy(data)
        corrupted["memory_summary"]["total_free_bytes"] += 100

        with pytest.raises(ValueError, match="Conservation of memory violated"):
            validate_memory_report_invariants(corrupted, report_name="corrupted")


class TestZeroPageSynchronization:
    """Validate that assembly equates in zeropage.asm synchronize with the manifest."""

    def test_zeropage_manifest_matches_assembly(self) -> None:
        zp_asm = REPO_ROOT / "zeropage.asm"
        zp_manifest = REPO_ROOT / "scripts" / "portal" / "zeropage_manifest.json"

        assert zp_asm.is_file()
        assert zp_manifest.is_file()

        # Must validate with zero errors
        validate_zeropage_manifest_sync(zp_asm, zp_manifest)

    def test_zeropage_detects_out_of_range_symbol(self, tmp_path: Path) -> None:
        zp_manifest = REPO_ROOT / "scripts" / "portal" / "zeropage_manifest.json"

        # Create a mock zeropage.asm with a symbol in OS range ($40)
        mock_asm = tmp_path / "mock_zeropage.asm"
        mock_asm.write_text("bad_os_sym = $40\n", encoding="utf-8")

        with pytest.raises(ValueError, match="not declared in zeropage_manifest.json"):
            validate_zeropage_manifest_sync(mock_asm, zp_manifest)


class TestPipelineExporters:
    """Verify that export scripts produce complete, valid output files."""

    def test_export_manifest(self, tmp_path: Path) -> None:
        manifest_yaml = REPO_ROOT / "manifest.yaml"
        out_json = tmp_path / "assets.json"

        res = export_assets_json(manifest_yaml, out_json)
        assert out_json.is_file()
        assert res["schema_version"] == "3.2.0"
        assert len(res["graphics"]["tilesets"]) == 4
        assert len(res["audio"]["music"]) >= 2

    def test_export_releases(self, tmp_path: Path) -> None:
        snapshots_dir = REPO_ROOT / "reports" / "portal" / "snapshots"
        out_json = tmp_path / "releases.json"

        res = export_releases_json("grzes71/call-of-the-wintermon", snapshots_dir, out_json)
        assert out_json.is_file()
        assert len(res["releases"]) >= 3
        tags = [r["tag"] for r in res["releases"]]
        assert "v0.1.0" in tags
        assert "v0.2.0" in tags
        assert "v0.2.1" in tags
