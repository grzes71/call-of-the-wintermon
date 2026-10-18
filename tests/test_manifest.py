from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.yaml"


def test_manifest_file_exists():
    assert MANIFEST_PATH.is_file(), f"Manifest file {MANIFEST_PATH} does not exist"


def test_manifest_paths_exist_and_no_generated_files():
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    
    # Extract all path values
    path_matches = re.findall(r'(?:path|entry_point|manifest|catalogues):\s*["\']([^"\']+)["\']', content)
    
    assert len(path_matches) > 15, "Expected manifest to reference multiple input resources"
    
    for rel_path in path_matches:
        # Check no generated build artifacts are referenced
        assert not rel_path.startswith("gen/"), f"Generated file referenced in manifest: {rel_path}"
        assert not rel_path.startswith("gen\\"), f"Generated file referenced in manifest: {rel_path}"
        
        # Check path actually exists
        full_path = REPO_ROOT / rel_path
        assert full_path.exists(), f"Manifest referenced file does not exist: {rel_path}"
