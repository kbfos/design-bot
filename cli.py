"""
CLI — render a card from a JSON CardSpec.

Usage:
    # inline JSON
    python cli.py '{"template_id": "blog_cover_v1", "title": "Hello"}'

    # JSON file
    python cli.py spec.json

    # with output directory
    python cli.py spec.json --output /tmp/cards

    # pretty-print the spec before rendering
    python cli.py spec.json --dry-run

Exit codes:
    0 — success, PNG path printed to stdout
    1 — validation error or render error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.services.card_spec import CardSpec
from app.services.renderer import render_card


def _load_json(source: str) -> dict:
    """Load JSON from a file path or inline string."""
    path = Path(source)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # treat as inline JSON string
    return json.loads(source)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a design card from a JSON CardSpec.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "spec",
        help="Path to a JSON file or an inline JSON string.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="DIR",
        help="Output directory for the PNG (default: assets/output).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the spec without rendering.",
    )
    args = parser.parse_args()

    # 1. Load JSON
    try:
        data = _load_json(args.spec)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: cannot read spec — {exc}", file=sys.stderr)
        return 1

    # 2. Validate
    try:
        spec = CardSpec.model_validate(data)
    except ValidationError as exc:
        print("Validation error:", file=sys.stderr)
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"]) if err["loc"] else "spec"
            print(f"  {loc}: {err['msg']}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(spec.model_dump_json(indent=2, exclude_none=True))
        return 0

    # 3. Render
    output_dir = Path(args.output) if args.output else None
    try:
        path = render_card(spec, output_dir=output_dir)
        print(path)
        return 0
    except Exception as exc:
        print(f"Render error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
