#!/usr/bin/env python3
"""Conventional Commits Analyzer and Release Helper for Call of the Wintermon.

Analyzes GitHub pull requests or workflow dispatch events, derives semantic version bumps
(major, minor, patch), generates Polish Markdown changelogs, updates version strings
in manifest.yaml / scroll text, and outputs variables for GitHub Actions workflows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

CONVENTIONAL_COMMIT_REGEX = re.compile(
    r"^(?P<type>[a-zA-Z0-9_-]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)


def parse_commit_message(message: str) -> dict[str, Any] | None:
    """Parse a commit message or PR title according to Conventional Commits.

    Returns a dict with keys: type, scope, desc, is_breaking, raw, body,
    or None if the message does not match conventional commits format.
    """
    if not message:
        return None

    lines = [line.strip() for line in message.strip().splitlines() if line.strip()]
    if not lines:
        return None

    first_line = lines[0]
    match = CONVENTIONAL_COMMIT_REGEX.match(first_line)
    if not match:
        return None

    c_type = match.group("type").lower()
    scope = match.group("scope")
    breaking_marker = bool(match.group("breaking"))
    desc = match.group("desc")

    # Check for BREAKING CHANGE / BREAKING-CHANGE in message body/footer
    has_breaking_body = any(
        line.startswith("BREAKING CHANGE:") or line.startswith("BREAKING-CHANGE:")
        for line in lines[1:]
    )
    is_breaking = breaking_marker or has_breaking_body

    return {
        "type": c_type,
        "scope": scope,
        "desc": desc,
        "is_breaking": is_breaking,
        "raw": first_line,
        "body": "\n".join(lines[1:]) if len(lines) > 1 else "",
    }


def determine_bump_type(parsed_commits: list[dict[str, Any]]) -> str | None:
    """Determine whether a bump is 'major', 'minor', 'patch', or None.

    Priority: major > minor > patch > None.
    """
    has_major = False
    has_minor = False
    has_patch = False

    for c in parsed_commits:
        if not c:
            continue
        if c.get("is_breaking"):
            has_major = True
        elif c.get("type") == "feat":
            has_minor = True
        elif c.get("type") in ("fix", "perf", "bugfix"):
            has_patch = True

    if has_major:
        return "major"
    if has_minor:
        return "minor"
    if has_patch:
        return "patch"
    return None


def parse_semver(tag: str) -> tuple[int, int, int]:
    """Parse a git tag like 'v1.2.3' or '1.2.3' into (major, minor, patch)."""
    clean_tag = tag.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", clean_tag)
    if not match:
        raise ValueError(f"Invalid semver tag: {tag}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def get_latest_git_tag(cwd: Path | None = None) -> str | None:
    """Find the latest semver tag in the repository."""
    try:
        res = subprocess.run(
            ["git", "tag", "-l", "v*"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        tags = [t.strip() for t in res.stdout.splitlines() if t.strip()]
        if not tags:
            return None

        valid_tags: list[tuple[tuple[int, int, int], str]] = []
        for t in tags:
            try:
                ver = parse_semver(t)
                valid_tags.append((ver, t))
            except ValueError:
                continue

        if not valid_tags:
            return None

        valid_tags.sort(key=lambda item: item[0])
        return valid_tags[-1][1]
    except Exception:
        return None


def get_pr_commit_messages(merge_sha: str | None) -> list[str]:
    """Return the commit messages introduced by the merged PR, using its merge commit.

    - For a merge commit (two parents), `merge_sha^1..merge_sha` lists exactly
      the commits brought in by the PR.
    - For squash/rebase merges (one parent) the merge commit itself is the PR
      commit, so we fall back to that single message.
    """
    if not merge_sha:
        return []

    messages: list[str] = []
    try:
        res = subprocess.run(
            ["git", "log", "--format=%B%x1e", f"{merge_sha}^1..{merge_sha}"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            messages = [c.strip() for c in res.stdout.split("\x1e") if c.strip()]
    except Exception:
        messages = []

    if not messages:
        try:
            res = subprocess.run(
                ["git", "log", "-n", "1", "--format=%B", merge_sha],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                messages = [res.stdout.strip()]
        except Exception:
            messages = []

    return messages


def compute_next_version(latest_tag: str | None, bump_type: str) -> str:
    """Compute the next tag given the latest tag and bump type ('major', 'minor', 'patch')."""
    if not latest_tag:
        if bump_type == "major":
            return "v1.0.0"
        if bump_type == "minor":
            return "v0.1.0"
        return "v0.0.1"

    major, minor, patch = parse_semver(latest_tag)

    if bump_type == "major":
        return f"v{major + 1}.0.0"
    if bump_type == "minor":
        return f"v{major}.{minor + 1}.0"
    if bump_type == "patch":
        return f"v{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump type: {bump_type}")


def generate_changelog(
    parsed_commits: list[dict[str, Any]],
    pr_number: int | None = None,
    pr_author: str | None = None,
    pr_url: str | None = None,
) -> str:
    """Generate a Markdown changelog categorized by commit type."""
    breaking_items: list[str] = []
    features: list[str] = []
    fixes: list[str] = []
    perfs: list[str] = []
    others: list[str] = []

    for c in parsed_commits:
        if not c:
            continue
        scope_prefix = f"**{c['scope']}:** " if c.get("scope") else ""
        item_text = f"- {scope_prefix}{c['desc']}"

        if c.get("is_breaking"):
            breaking_items.append(item_text)
        elif c.get("type") == "feat":
            features.append(item_text)
        elif c.get("type") in ("fix", "bugfix"):
            fixes.append(item_text)
        elif c.get("type") == "perf":
            perfs.append(item_text)
        else:
            others.append(item_text)

    sections: list[str] = []
    if breaking_items:
        sections.append("### 💥 Breaking Changes\n" + "\n".join(breaking_items))
    if features:
        sections.append("### 🚀 Nowości (Features)\n" + "\n".join(features))
    if fixes:
        sections.append("### 🐛 Poprawki (Bug Fixes)\n" + "\n".join(fixes))
    if perfs:
        sections.append("### ⚡ Wydajność (Performance)\n" + "\n".join(perfs))
    if others and not (features or fixes or perfs or breaking_items):
        sections.append("### 🔧 Inne zmiany\n" + "\n".join(others))

    if pr_number and pr_url:
        author_str = f" przez @{pr_author}" if pr_author else ""
        sections.append(f"\n*Pull Request: [#{pr_number}]({pr_url}){author_str}*")

    return "\n\n".join(sections).strip()


def process_github_pr_event(
    event_data: dict[str, Any], git_commits: list[str] | None = None
) -> dict[str, Any]:
    """Analyze a GitHub pull_request or workflow_dispatch event and return release metadata."""
    # Check for manual workflow_dispatch inputs first
    inputs = event_data.get("inputs")
    if inputs and "bump_type" in inputs:
        bump_type = str(inputs["bump_type"]).lower()
        latest_tag = get_latest_git_tag()
        new_tag = compute_next_version(latest_tag, bump_type)
        return {
            "should_release": True,
            "bump_type": bump_type,
            "previous_tag": latest_tag or "none",
            "tag_name": new_tag,
            "version": new_tag.lstrip("v"),
            "release_title": f"Call of the Wintermon {new_tag}",
            "changelog": f"### 🚀 Manual Release ({bump_type})\n- Triggered via GitHub Actions workflow_dispatch.",
        }

    pr = event_data.get("pull_request", {})
    if not pr.get("merged", False):
        return {"should_release": False, "reason": "PR not merged"}

    pr_title = pr.get("title", "")
    pr_body = pr.get("body", "") or ""
    pr_number = pr.get("number")
    pr_url = pr.get("html_url")
    pr_author = pr.get("user", {}).get("login")

    # Collect candidates: PR title + body, and any git commit messages
    candidates = [f"{pr_title}\n\n{pr_body}"]
    if git_commits:
        candidates.extend(git_commits)

    parsed_commits: list[dict[str, Any]] = []
    for raw_msg in candidates:
        p = parse_commit_message(raw_msg)
        if p:
            # Deduplicate by raw description
            if not any(existing["desc"] == p["desc"] for existing in parsed_commits):
                parsed_commits.append(p)

    bump_type = determine_bump_type(parsed_commits)
    if not bump_type:
        return {
            "should_release": False,
            "reason": f"No releasing conventional commit types found in PR #{pr_number} ('{pr_title}')",
        }

    latest_tag = get_latest_git_tag()
    new_tag = compute_next_version(latest_tag, bump_type)
    changelog = generate_changelog(
        parsed_commits,
        pr_number=pr_number,
        pr_author=pr_author,
        pr_url=pr_url,
    )

    return {
        "should_release": True,
        "bump_type": bump_type,
        "previous_tag": latest_tag or "none",
        "tag_name": new_tag,
        "version": new_tag.lstrip("v"),
        "release_title": f"Call of the Wintermon {new_tag}",
        "changelog": changelog,
    }


def update_manifest_version(version: str, manifest_path: Path | None = None) -> bool:
    """Update the version string in manifest.yaml to reflect the new release version."""
    if manifest_path is None:
        manifest_path = Path("manifest.yaml")
    if isinstance(manifest_path, str):
        manifest_path = Path(manifest_path)

    if not manifest_path.exists():
        return False

    content = manifest_path.read_text(encoding="utf-8")
    clean_version = version.lstrip("v").strip()

    pattern = re.compile(r'^(version:\s*["\']?)[^"\'\r\n]+(["\']?)', re.MULTILINE)
    if not pattern.search(content):
        return False

    new_content = pattern.sub(rf"\g<1>{clean_version}\g<2>", content)
    manifest_path.write_text(new_content, encoding="utf-8")
    return True


def update_scroll_version(version: str, scroll_file: Path | None = None) -> bool:
    """Update the version string in a scroll text file if a version pattern is present."""
    if scroll_file is None:
        scroll_file = Path("scroll/title.txt")
    if isinstance(scroll_file, str):
        scroll_file = Path(scroll_file)

    if not scroll_file.exists():
        return False

    content = scroll_file.read_text(encoding="utf-8")
    clean_version = version.lstrip("v").strip()

    pattern = re.compile(r"version\s+v?[0-9]+(?:\.[0-9]+)*", re.IGNORECASE)
    if not pattern.search(content):
        return False

    new_content = pattern.sub(f"version {clean_version}", content)
    scroll_file.write_text(new_content, encoding="utf-8")
    return True


def main() -> int:
    """CLI entrypoint for release analysis and metadata generation."""
    parser = argparse.ArgumentParser(
        description="Analyze PR/event and determine release version for Call of the Wintermon"
    )
    parser.add_argument("--event-path", help="Path to GITHUB_EVENT_PATH JSON file")
    parser.add_argument("--output-file", help="Path to save GITHUB_OUTPUT key-value pairs")
    parser.add_argument("--changelog-file", help="Path to save changelog markdown")
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Update manifest.yaml with the release version",
    )
    parser.add_argument(
        "--manifest-file",
        default="manifest.yaml",
        help="Path to manifest.yaml (default: manifest.yaml)",
    )
    parser.add_argument(
        "--update-scroll",
        action="store_true",
        help="Update scroll text file with the release version (if pattern found)",
    )
    parser.add_argument(
        "--scroll-file",
        default="scroll/title.txt",
        help="Path to scroll text file (default: scroll/title.txt)",
    )
    parser.add_argument(
        "--version", help="Specific version string for standalone --update-manifest/--update-scroll"
    )
    args = parser.parse_args()

    # Standalone update mode
    if args.version and (args.update_manifest or args.update_scroll):
        success = True
        if args.update_manifest:
            if update_manifest_version(args.version, Path(args.manifest_file)):
                print(f"Updated {args.manifest_file} with version {args.version}")
            else:
                print(f"Failed to update {args.manifest_file}", file=sys.stderr)
                success = False
        if args.update_scroll:
            if update_scroll_version(args.version, Path(args.scroll_file)):
                print(f"Updated {args.scroll_file} with version {args.version}")
            else:
                print(
                    f"Warning: No version pattern found in {args.scroll_file}",
                    file=sys.stderr,
                )
        return 0 if success else 1

    if not args.event_path:
        print("Error: --event-path or (--version with --update-manifest) required", file=sys.stderr)
        return 1

    event_file = Path(args.event_path)
    if not event_file.is_file():
        print(f"Error: event file '{args.event_path}' not found", file=sys.stderr)
        return 1

    event_data = json.loads(event_file.read_text(encoding="utf-8"))

    merge_sha = event_data.get("pull_request", {}).get("merge_commit_sha")
    git_commits = get_pr_commit_messages(merge_sha)

    result = process_github_pr_event(event_data, git_commits)
    print(f"Release Decision: {json.dumps(result, indent=2)}")

    # Update manifest if requested and release is approved
    if args.update_manifest and result.get("should_release"):
        if update_manifest_version(result["version"], Path(args.manifest_file)):
            print(f"Updated {args.manifest_file} with version {result['version']}")
        else:
            print(f"Warning: Failed to update {args.manifest_file}", file=sys.stderr)

    # Update scroll text if requested and release is approved
    if args.update_scroll and result.get("should_release"):
        if update_scroll_version(result["version"], Path(args.scroll_file)):
            print(f"Updated {args.scroll_file} with version {result['version']}")
        else:
            print(
                f"Info: No version pattern found to update in {args.scroll_file}",
                file=sys.stderr,
            )

    # Write to GITHUB_OUTPUT if specified
    if args.output_file:
        with open(args.output_file, "a", encoding="utf-8") as f:
            f.write(f"should_release={str(result['should_release']).lower()}\n")
            if result.get("should_release"):
                f.write(f"tag_name={result['tag_name']}\n")
                f.write(f"version={result['version']}\n")
                f.write(f"release_title={result['release_title']}\n")
                f.write(f"bump_type={result['bump_type']}\n")
                f.write(f"previous_tag={result['previous_tag']}\n")

    if args.changelog_file and result.get("should_release"):
        with open(args.changelog_file, "w", encoding="utf-8") as f:
            f.write(result.get("changelog", ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())

