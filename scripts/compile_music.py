"""Compile Atari Music Composer JSON composition to relocatable MADS assembly.

Uses the atari_music engine to compile JSON music into POKEY IR and export MADS ASM.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from atari_music.ai.client import (
    generate_music_from_composition,
    generate_music_from_dsl,
    load_composition_json,
)
from atari_music.mads_exporter import export_mads_asm


def compile_music(
    input_path: Path,
    output_path: Path,
    song_label: str = "music_title_data",
) -> int:
    """Compile a composition JSON or DSL file into relocatable MADS assembly.

    Args:
        input_path: Path to source composition JSON or DSL.
        output_path: Path to generated ASM file.
        song_label: Base label name for the song data structure.

    Returns:
        0 on success, non-zero on failure.
    """
    if not input_path.exists():
        print(f"Error: Music file '{input_path}' not found.", file=sys.stderr)
        return 1

    try:
        if input_path.suffix.lower() == ".dsl":
            result = generate_music_from_dsl(input_path.read_text(encoding="utf-8"))
        else:
            composition = load_composition_json(input_path)
            result = generate_music_from_composition(composition)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_mads_asm(result.pokey_ir, output_path, song_label=song_label)
        print(
            f"Compiled music: '{input_path}' -> '{output_path}' (label: {song_label})"
        )
        return 0
    except Exception as exc:
        print(f"Error compiling music: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile Atari Music Composer JSON to MADS ASM."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Path to input composition JSON",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path to output ASM file",
    )
    parser.add_argument(
        "-l",
        "--label",
        type=str,
        default="music_title_data",
        help="Base label name for exported song (default: music_title_data)",
    )
    args = parser.parse_args()
    return compile_music(args.input, args.output, args.label)


if __name__ == "__main__":
    sys.exit(main())
