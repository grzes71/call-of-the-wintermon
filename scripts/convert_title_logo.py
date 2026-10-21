#!/usr/bin/env python3
"""Convert Atari title logo JSON definition into MADS assembly include file.

Source: title/title.json
Output: gen/title_logo.inc
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def validate_and_parse_logo(
    input_path: Path,
) -> tuple[int, int, list[list[int]]]:
    """Validate JSON file and extract logo dimensions and codes.

    Raises:
        ValueError: with a descriptive Polish error message if validation fails.
    """
    if not input_path.is_file():
        raise ValueError(f"{input_path}: Plik nie istnieje lub nie jest plikiem")

    try:
        content = input_path.read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"{input_path}: Błąd odczytu pliku: {e}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{input_path}:{e.lineno}:{e.colno}: Błąd składni JSON: {e.msg}"
        )

    if not isinstance(data, dict):
        raise ValueError(
            f"{input_path}: Główny element JSON musi być obiektem (słownikiem)"
        )

    if "logo" not in data or not isinstance(data["logo"], dict):
        raise ValueError(f"{input_path}: Brak wymaganego obiektu 'logo'")

    logo = data["logo"]
    for key in ("columns", "rows", "codes"):
        if key not in logo:
            raise ValueError(
                f"{input_path}: Obiekt 'logo' musi zawierać klucz '{key}'"
            )

    cols = logo["columns"]
    rows = logo["rows"]

    if type(cols) is not int or type(rows) is not int:
        raise ValueError(
            f"{input_path}: logo.columns i logo.rows muszą być liczbami całkowitymi"
        )

    if cols != 5:
        raise ValueError(
            f"{input_path}: logo.columns wynosi {cols}, oczekiwano 5 (siatka jest stała: bufor VRAM i Display List są pod nią wymiarowane)"
        )

    if rows != 4:
        raise ValueError(
            f"{input_path}: logo.rows wynosi {rows}, oczekiwano 4 (siatka jest stała: bufor VRAM i Display List są pod nią wymiarowane)"
        )

    codes = logo["codes"]
    if not isinstance(codes, list):
        raise ValueError(f"{input_path}: logo.codes musi być listą wierszy")

    if len(codes) != rows:
        raise ValueError(
            f"{input_path}: logo.codes ma {len(codes)} wierszy, oczekiwano {rows}"
        )

    parsed_codes: list[list[int]] = []
    for r_idx, row in enumerate(codes):
        if not isinstance(row, list):
            raise ValueError(
                f"{input_path}: logo.codes[{r_idx}] musi być listą kolumn"
            )
        if len(row) != cols:
            raise ValueError(
                f"{input_path}: logo.codes[{r_idx}] ma {len(row)} kolumn, oczekiwano {cols}"
            )

        row_codes: list[int] = []
        for c_idx, val in enumerate(row):
            if type(val) is not int:
                raise ValueError(
                    f"{input_path}: logo.codes[{r_idx}][{c_idx}] ma nieprawidłowy typ {type(val).__name__} (wartość: {val!r}), oczekiwano liczby całkowitej (0-127)"
                )
            if not (0 <= val <= 127):
                raise ValueError(
                    f"{input_path}: logo.codes[{r_idx}][{c_idx}] ma wartość {val} spoza zakresu 0-127 (font ma 128 glifów)"
                )
            row_codes.append(val)
        parsed_codes.append(row_codes)

    return cols, rows, parsed_codes


def convert_title_logo(input_path: Path, output_path: Path) -> int:
    """Validate JSON and generate MADS assembly include file."""
    try:
        cols, rows, codes = validate_and_parse_logo(input_path)
    except ValueError as err:
        print(f"Błąd: {err}", file=sys.stderr)
        return 1

    # Source display path with forward slashes
    src_display = input_path.as_posix()

    lines = [
        f"; GENERATED — nie edytuj, źródło: {src_display}",
        "",
        f"TITLE_LOGO_COLS  = {cols}",
        f"TITLE_LOGO_LINES = {rows}",
        "",
        "title_logo_codes:",
    ]

    for row in codes:
        row_str = ",".join(f"{c:3d}" for c in row)
        lines.append(f"    .byte {row_str}")

    lines.append("")  # trailing newline
    asm_content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(asm_content, encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Atari title logo JSON into MADS assembly include."
    )
    parser.add_argument(
        "pos_input",
        nargs="?",
        type=Path,
        default=None,
        help="Input JSON file path",
    )
    parser.add_argument(
        "pos_output",
        nargs="?",
        type=Path,
        default=None,
        help="Output .inc file path",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        dest="flag_input",
        help="Input JSON file path",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        dest="flag_output",
        help="Output .inc file path",
    )

    args = parser.parse_args()

    input_path = args.flag_input or args.pos_input or Path("title/title.json")
    output_path = args.flag_output or args.pos_output or Path("gen/title_logo.inc")

    return convert_title_logo(input_path, output_path)


if __name__ == "__main__":
    sys.exit(main())
