#!/usr/bin/env python3
"""Record a contract deployment in DEPLOYMENTS.md.

Updates the "Current Addresses" row for the contract/network pair (or adds it)
and appends a row to the "History" table. Tables are parsed and rewritten
cell-wise, so the column count of each table is always preserved.
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "DEPLOYMENTS.md"

CURRENT_HEADING = "Current Addresses"
HISTORY_HEADING = "History"
CURRENT_COLUMNS = ["Contract", "Network", "Address", "WASM Hash"]
HISTORY_COLUMNS = [
    "Date",
    "Network",
    "Contract",
    "Address",
    "WASM Hash",
    "Git SHA",
    "CLI Version",
]


def split_row(line):
    """Split a Markdown table row into stripped cells (honours `\\|` escapes)."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [cell.strip() for cell in cells]


def format_row(cells):
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def is_row(line):
    return line.strip().startswith("|")


def is_separator(cells):
    return all(re.fullmatch(r":?-+:?", cell) for cell in cells)


def find_table(lines, heading):
    """Return (header_idx, first_row_idx, end_idx) of the table under `heading`."""
    start = None
    for i, line in enumerate(lines):
        if re.fullmatch(r"#+\s+" + re.escape(heading) + r"\s*", line.strip()):
            start = i
            break
    if start is None:
        raise SystemExit(f"error: section '{heading}' not found")

    header = next((i for i in range(start + 1, len(lines)) if is_row(lines[i])), None)
    if header is None or header + 1 >= len(lines):
        raise SystemExit(f"error: no table under '{heading}'")
    if not is_separator(split_row(lines[header + 1])):
        raise SystemExit(f"error: malformed table under '{heading}'")

    first = header + 2
    end = first
    while end < len(lines) and is_row(lines[end]):
        end += 1
    return header, first, end


def check_columns(lines, header, heading, expected):
    actual = split_row(lines[header])
    if actual != expected:
        raise SystemExit(
            f"error: '{heading}' table has columns {actual}, expected {expected}"
        )


def upsert_current(lines, row):
    header, first, end = find_table(lines, CURRENT_HEADING)
    check_columns(lines, header, CURRENT_HEADING, CURRENT_COLUMNS)
    for i in range(first, end):
        cells = split_row(lines[i])
        if len(cells) >= 2 and cells[0] == row[0] and cells[1] == row[1]:
            lines[i] = format_row(row)
            return
    lines.insert(end, format_row(row))


def append_history(lines, row):
    header, _, end = find_table(lines, HISTORY_HEADING)
    check_columns(lines, header, HISTORY_HEADING, HISTORY_COLUMNS)
    lines.insert(end, format_row(row))


def detect_cli_version():
    for binary in ("stellar", "soroban"):
        try:
            out = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, check=True
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        first = out.strip().splitlines()
        if first:
            return first[0].strip()
    raise SystemExit(
        "error: could not determine CLI version from `stellar --version`; "
        "pass --cli-version"
    )


def git_sha():
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, help="Contract name")
    parser.add_argument("--network", required=True, help="Network (testnet, mainnet)")
    parser.add_argument("--contract-id", required=True, help="Deployed contract address")
    parser.add_argument("--wasm-hash", required=True, help="Deployed WASM hash")
    parser.add_argument("--git-sha", default=None, help="Git SHA (default: HEAD)")
    parser.add_argument(
        "--cli-version",
        default=None,
        help="Stellar CLI version (default: first line of `stellar --version`)",
    )
    parser.add_argument(
        "--file", type=Path, default=DEFAULT_FILE, help="Markdown file to update"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cli_version = args.cli_version or detect_cli_version()
    sha = args.git_sha or git_sha()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    text = args.file.read_text()
    lines = text.splitlines()

    upsert_current(
        lines, [args.contract, args.network, args.contract_id, args.wasm_hash]
    )
    append_history(
        lines,
        [
            date,
            args.network,
            args.contract,
            args.contract_id,
            args.wasm_hash,
            sha,
            cli_version,
        ],
    )

    args.file.write_text("\n".join(lines) + "\n")
    print(f"updated {args.file}")


if __name__ == "__main__":
    sys.exit(main())
