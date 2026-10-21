"""Unit and integration tests for title/title.json and scripts/convert_title_logo.py."""

from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

from scripts.convert_title_logo import (
    convert_title_logo,
    validate_and_parse_logo,
)


def parse_labels(lab_path: Path) -> dict[str, int]:
    """Parse MADS symbol table (.lab) into dictionary of UPPERCASE label -> address."""
    labels: dict[str, int] = {}
    pattern = re.compile(r"^[0-9a-fA-F]{2}\t([0-9a-fA-F]{4})\t([^\s]+)")
    for line in lab_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.match(line)
        if m:
            addr = int(m.group(1), 16)
            name = m.group(2).upper()
            labels[name] = addr
    return labels


def load_xex_into_memory(xex_path: Path, mem: bytearray) -> None:
    """Parse Atari DOS XEX segments and load payload into memory."""
    data = xex_path.read_bytes()
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0

    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4

        if start == 0xFFFF:
            if pos + 4 > len(data):
                break
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4

        size = end - start + 1
        if size <= 0 or pos + size > len(data):
            break

        mem[start : end + 1] = data[pos : pos + size]
        pos += size


def test_title_logo_codes_in_built_xex():
    """Integration test: Verify title_logo_codes in built XEX binary matches title/title.json row by row."""
    xex_path = Path("call_of_the_wintermon.xex")
    lab_path = Path("gen/main.lab")
    json_path = Path("title/title.json")

    assert xex_path.is_file(), "call_of_the_wintermon.xex missing. Run make first."
    assert lab_path.is_file(), "gen/main.lab missing. Run make first."
    assert json_path.is_file(), "title/title.json missing."

    mem = bytearray(65536)
    load_xex_into_memory(xex_path, mem)
    labels = parse_labels(lab_path)

    assert "TITLE_LOGO_CODES" in labels, "Symbol TITLE_LOGO_CODES not found in main.lab"
    codes_addr = labels["TITLE_LOGO_CODES"]

    logo_data = json.loads(json_path.read_text(encoding="utf-8"))
    expected_flat = [c for line in logo_data["logo"]["codes"] for c in line]
    actual_flat = [mem[codes_addr + i] for i in range(len(expected_flat))]

    assert actual_flat == expected_flat, (
        f"title_logo_codes in binary ({actual_flat}) does not match title.json ({expected_flat})"
    )


def test_repo_title_json_valid_and_matches_specs():
    """Verify that title/title.json in the repository is valid and conforms to specs."""
    repo_json = Path("title/title.json")
    assert repo_json.is_file(), "title/title.json must exist in repository root"

    cols, rows, codes = validate_and_parse_logo(repo_json)
    assert cols == 5
    assert rows == 4
    assert len(codes) == 4
    for r in codes:
        assert len(r) == 5
        for c in r:
            assert isinstance(c, int) and not isinstance(c, bool)
            assert 0 <= c <= 127


def test_successful_conversion(tmp_path: Path):
    """Verify that a valid JSON produces the exact expected MADS .inc format."""
    input_file = tmp_path / "valid.json"
    output_file = tmp_path / "gen" / "title_logo.inc"

    content = {
        "description": "Test Atari Logo",
        "logo": {
            "columns": 5,
            "rows": 4,
            "codes": [
                [0, 125, 126, 127, 0],
                [0, 124, 80, 96, 0],
                [75, 76, 77, 78, 79],
                [91, 92, 93, 94, 95],
            ],
        },
    }
    input_file.write_text(json.dumps(content), encoding="utf-8")

    ret = convert_title_logo(input_file, output_file)
    assert ret == 0
    assert output_file.is_file()

    text = output_file.read_text(encoding="utf-8")
    assert "TITLE_LOGO_COLS  = 5" in text
    assert "TITLE_LOGO_LINES = 4" in text
    assert "title_logo_codes:" in text
    assert ".byte   0,125,126,127,  0" in text
    assert ".byte   0,124, 80, 96,  0" in text
    assert ".byte  75, 76, 77, 78, 79" in text
    assert ".byte  91, 92, 93, 94, 95" in text


def test_boundary_codes_accepted(tmp_path: Path):
    """Verify that boundary codes 0 and 127 are accepted."""
    input_file = tmp_path / "boundary.json"
    output_file = tmp_path / "boundary.inc"

    content = {
        "logo": {
            "columns": 5,
            "rows": 4,
            "codes": [
                [0, 127, 0, 127, 0],
                [127, 0, 127, 0, 127],
                [0, 0, 0, 0, 0],
                [127, 127, 127, 127, 127],
            ],
        }
    }
    input_file.write_text(json.dumps(content), encoding="utf-8")

    ret = convert_title_logo(input_file, output_file)
    assert ret == 0
    assert output_file.is_file()


@pytest.mark.parametrize(
    "case_id, raw_content",
    [
        ("syntax_error", "{ not a valid json"),
        ("not_a_dict", "[1, 2, 3]"),
        ("missing_logo", '{"description": "no logo object"}'),
        (
            "missing_columns",
            '{"logo": {"rows": 4, "codes": [[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "missing_rows",
            '{"logo": {"columns": 5, "codes": [[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        ("missing_codes", '{"logo": {"columns": 5, "rows": 4}}'),
        (
            "columns_not_5",
            '{"logo": {"columns": 4, "rows": 4, "codes": [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]]}}',
        ),
        (
            "rows_not_4",
            '{"logo": {"columns": 5, "rows": 3, "codes": [[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "three_rows_declared_four",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "row_with_four_codes",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[0,0,0,0,0],[0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "row_with_six_codes",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[0,0,0,0,0],[0,0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_negative",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[-1,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_too_large",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[128,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_string",
            '{"logo": {"columns": 5, "rows": 4, "codes": [["12",0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_float",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[3.5,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_bool_true",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[true,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
        (
            "code_bool_false",
            '{"logo": {"columns": 5, "rows": 4, "codes": [[false,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}}',
        ),
    ],
)
def test_invalid_json_inputs_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case_id: str, raw_content: str
):
    """Verify that malformed or out-of-range inputs return non-zero exit code, error message, and no output."""
    input_file = tmp_path / f"invalid_{case_id}.json"
    output_file = tmp_path / f"output_{case_id}.inc"
    input_file.write_text(raw_content, encoding="utf-8")

    ret = convert_title_logo(input_file, output_file)
    assert ret != 0, f"Expected non-zero return code for case: {case_id}"

    captured = capsys.readouterr()
    assert str(input_file) in captured.err or input_file.name in captured.err
    assert not output_file.exists(), (
        f"Output file must not be created for invalid input {case_id}"
    )


def test_nonexistent_file_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Verify that a nonexistent file returns non-zero error."""
    nonexistent = tmp_path / "does_not_exist.json"
    output_file = tmp_path / "out.inc"
    ret = convert_title_logo(nonexistent, output_file)
    assert ret != 0
    assert not output_file.exists()
    captured = capsys.readouterr()
    assert "does_not_exist.json" in captured.err
