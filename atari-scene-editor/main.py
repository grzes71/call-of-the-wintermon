#!/usr/bin/env python3
"""Entry point for Atari 8-bit Scene Editor."""

from pathlib import Path
import sys

# Add src to sys.path
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from scene_editor.app import main

if __name__ == "__main__":
    sys.exit(main())
