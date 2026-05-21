from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import SUPPORTED_FORMATS, convert_file, convert_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gptsession-convert",
        description="Convert ChatGPT session JSON/text into CPA, sub2api, Cockpit, 9router, or AxonHub JSON.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=SUPPORTED_FORMATS,
        default="cockpit",
        help="Output format. Defaults to cockpit.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help="Input .json/.txt file. If omitted, stdin is used.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSON path. If omitted, JSON is printed to stdout.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation. Use 0 for compact JSON.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Return an empty output document instead of failing when no session is found.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.input:
            result = convert_file(args.input, output_format=args.format)
        else:
            result = convert_text(sys.stdin.read(), output_format=args.format, source_name="stdin")
    except Exception as exc:  # noqa: BLE001 - CLI should show a short actionable error.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not result.converted and not args.allow_empty:
        print("error: no convertible session object found", file=sys.stderr)
        if result.skipped:
            for item in result.skipped[:5]:
                print(f"- {item.source_name} {item.path}: {item.reason}", file=sys.stderr)
        return 2

    indent = None if args.indent == 0 else args.indent
    output_text = json.dumps(result.output, ensure_ascii=False, indent=indent)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n", encoding="utf-8")
        print(
            f"wrote {args.output} ({len(result.converted)} converted, {len(result.skipped)} skipped)",
            file=sys.stderr,
        )
        return 0

    print(output_text)
    return 0
