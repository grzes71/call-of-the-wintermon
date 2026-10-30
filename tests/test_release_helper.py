"""Unit tests for release helper utility (scripts/release_helper.py)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.release_helper import (
    parse_commit_message,
    determine_bump_type,
    parse_semver,
    compute_next_version,
    generate_changelog,
    process_github_pr_event,
    get_pr_commit_messages,
    update_manifest_version,
    update_scroll_version,
    main,
)


def test_parse_commit_message_feat():
    msg = "feat(scenes): add deeper cave levels"
    parsed = parse_commit_message(msg)
    assert parsed is not None
    assert parsed["type"] == "feat"
    assert parsed["scope"] == "scenes"
    assert parsed["desc"] == "add deeper cave levels"
    assert parsed["is_breaking"] is False


def test_parse_commit_message_fix():
    msg = "fix: resolve player collision on moving platforms"
    parsed = parse_commit_message(msg)
    assert parsed is not None
    assert parsed["type"] == "fix"
    assert parsed["scope"] is None
    assert parsed["desc"] == "resolve player collision on moving platforms"
    assert parsed["is_breaking"] is False


def test_parse_commit_message_breaking_marker():
    msg = "feat!: redesign memory map layout"
    parsed = parse_commit_message(msg)
    assert parsed is not None
    assert parsed["type"] == "feat"
    assert parsed["is_breaking"] is True


def test_parse_commit_message_breaking_body():
    msg = "refactor: restructure engine scheduler\n\nBREAKING CHANGE: changes module signature"
    parsed = parse_commit_message(msg)
    assert parsed is not None
    assert parsed["type"] == "refactor"
    assert parsed["is_breaking"] is True


def test_determine_bump_type():
    c_chore = parse_commit_message("chore: update documentation")
    assert determine_bump_type([c_chore]) is None

    c_fix = parse_commit_message("fix: fix typo in status line")
    assert determine_bump_type([c_chore, c_fix]) == "patch"

    c_feat = parse_commit_message("feat: add new music track")
    assert determine_bump_type([c_chore, c_fix, c_feat]) == "minor"

    c_breaking = parse_commit_message("feat!: rewrite display list engine")
    assert determine_bump_type([c_chore, c_fix, c_feat, c_breaking]) == "major"


def test_compute_next_version():
    # Initial versions when no previous tag exists
    assert compute_next_version(None, "minor") == "v0.1.0"
    assert compute_next_version(None, "patch") == "v0.0.1"
    assert compute_next_version(None, "major") == "v1.0.0"

    # Incremental bumps
    assert compute_next_version("v0.1.0", "patch") == "v0.1.1"
    assert compute_next_version("v0.1.0", "minor") == "v0.2.0"
    assert compute_next_version("v0.1.0", "major") == "v1.0.0"
    assert compute_next_version("v1.2.3", "patch") == "v1.2.4"
    assert compute_next_version("v1.2.3", "minor") == "v1.3.0"
    assert compute_next_version("v1.2.3", "major") == "v2.0.0"


def test_generate_changelog():
    c1 = parse_commit_message("feat(audio): add victory fanfare")
    c2 = parse_commit_message("fix(dli): correct double buffer index")

    changelog = generate_changelog(
        [c1, c2],
        pr_number=12,
        pr_author="winterdev",
        pr_url="https://github.com/grzes71/call-of-the-wintermon/pull/12",
    )
    assert "### 🚀 Nowości (Features)" in changelog
    assert "**audio:** add victory fanfare" in changelog
    assert "### 🐛 Poprawki (Bug Fixes)" in changelog
    assert "**dli:** correct double buffer index" in changelog
    assert "[#12](https://github.com/grzes71/call-of-the-wintermon/pull/12)" in changelog
    assert "@winterdev" in changelog


def test_process_github_pr_event_not_merged():
    event = {
        "pull_request": {
            "merged": False,
            "title": "feat: new feature",
        }
    }
    res = process_github_pr_event(event)
    assert res["should_release"] is False


def test_process_github_pr_event_merged_feat():
    event = {
        "pull_request": {
            "merged": True,
            "number": 5,
            "html_url": "https://github.com/grzes71/call-of-the-wintermon/pull/5",
            "title": "feat: integrate game over and victory audio",
            "body": "Adds POKEY music for game over screens.",
            "user": {"login": "grzes71"},
        }
    }
    res = process_github_pr_event(event)
    assert res["should_release"] is True
    assert res["bump_type"] == "minor"
    assert res["tag_name"].startswith("v")
    assert res["release_title"] == f"Call of the Wintermon {res['tag_name']}"
    assert "integrate game over and victory audio" in res["changelog"]


def test_process_github_pr_event_workflow_dispatch():
    event = {
        "inputs": {
            "bump_type": "patch",
        }
    }
    res = process_github_pr_event(event)
    assert res["should_release"] is True
    assert res["bump_type"] == "patch"
    assert res["tag_name"].startswith("v")
    assert res["release_title"] == f"Call of the Wintermon {res['tag_name']}"


def test_get_pr_commit_messages_none():
    assert get_pr_commit_messages(None) == []
    assert get_pr_commit_messages("") == []


def test_update_manifest_version(tmp_path: Path):
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        'name: "Call of the Wintermon"\nversion: "0.1.0"\ntarget:\n  cpu: "MOS 6502"\n',
        encoding="utf-8",
    )

    assert update_manifest_version("v0.2.0", manifest_file) is True
    content = manifest_file.read_text(encoding="utf-8")
    assert 'version: "0.2.0"' in content
    assert 'version: "0.1.0"' not in content
    assert 'name: "Call of the Wintermon"' in content


def test_update_manifest_version_no_pattern(tmp_path: Path):
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("name: Test\n", encoding="utf-8")
    assert update_manifest_version("0.1.0", manifest_file) is False


def test_update_manifest_version_nonexistent(tmp_path: Path):
    assert update_manifest_version("0.1.0", tmp_path / "nonexistent.yaml") is False


def test_update_scroll_version(tmp_path: Path):
    scroll_file = tmp_path / "title.txt"
    scroll_file.write_text(
        "CALL OF THE WINTERMON\nATARI 8-BIT GAME - version 0.1.0\nPRESS FIRE",
        encoding="utf-8",
    )

    assert update_scroll_version("v0.2.0", scroll_file) is True
    content = scroll_file.read_text(encoding="utf-8")
    assert "version 0.2.0" in content
    assert "version 0.1.0" not in content


def test_update_scroll_version_no_pattern(tmp_path: Path):
    scroll_file = tmp_path / "title.txt"
    scroll_file.write_text("CALL OF THE WINTERMON\nPRESS FIRE", encoding="utf-8")
    assert update_scroll_version("0.1.0", scroll_file) is False


def test_cli_execution(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scripts.release_helper.get_latest_git_tag", lambda cwd=None: "v0.1.0")
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(
            {
                "pull_request": {
                    "merged": True,
                    "number": 1,
                    "html_url": "https://github.com/grzes71/call-of-the-wintermon/pull/1",
                    "title": "fix: correct jump physics",
                    "user": {"login": "tester"},
                }
            }
        ),
        encoding="utf-8",
    )
    out_file = tmp_path / "output.txt"
    changelog_file = tmp_path / "changelog.md"
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text('version: "0.1.0"\n', encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "release_helper.py",
            "--event-path",
            str(event_file),
            "--output-file",
            str(out_file),
            "--changelog-file",
            str(changelog_file),
            "--update-manifest",
            "--manifest-file",
            str(manifest_file),
        ],
    )

    ret = main()
    assert ret == 0
    assert out_file.exists()
    assert "should_release=true" in out_file.read_text(encoding="utf-8")
    assert changelog_file.exists()
    assert "correct jump physics" in changelog_file.read_text(encoding="utf-8")
    assert 'version: "0.1.1"' in manifest_file.read_text(encoding="utf-8")
