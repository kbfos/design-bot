"""
Figma SVG integration test.

Проверяет что SVG-шаблон card_v1 корректно рендерится.
При добавлении нового шаблона из Figma — добавь кейс в FIGMA_CASES.

Usage:
    DYLD_LIBRARY_PATH=/opt/homebrew/lib venv/bin/python figma_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.services.card_spec import CardSpec, CardSize, BackgroundMode, Palette, ALLOWED_SIZES
from app.services.renderer import render_card, CARD_TEMPLATE_ID
from app.templates.engine import TemplateVariantNotFound

FIGMA_CASES = [
    {
        "label": "light, title + subtitle + tag",
        "spec": {
            "title": "Тест шаблона из Figma",
            "subtitle": "Проверка Jinja2-переменных",
            "tag": "Figma",
            "palette": "light",
        },
    },
    {
        "label": "dark, title only",
        "spec": {
            "title": "Design is how it works",
            "palette": "dark",
        },
    },
    {
        "label": "light, tag only (no subtitle)",
        "spec": {
            "title": "Новый шаблон из Figma",
            "tag": "Tech",
            "palette": "light",
        },
    },
    {
        "label": "square 1080x1080",
        "spec": {
            "size": {"width": 1080, "height": 1080},
            "title": "Square from Figma",
            "palette": "light",
        },
    },
]


def test_template_files_exist() -> list[str]:
    """Проверяет наличие SVG файлов для универсального шаблона."""
    errors = []
    templates_dir = Path("assets/templates")
    for w, h in sorted(ALLOWED_SIZES):
        filename = f"{CARD_TEMPLATE_ID}_{w}x{h}.svg"
        if not (templates_dir / filename).exists():
            errors.append(f"Missing: assets/templates/{filename}")
    return errors


def test_render_case(case: dict) -> tuple[bool, str]:
    label = case["label"]
    try:
        spec = CardSpec.model_validate(case["spec"])
    except ValidationError as exc:
        return False, f"Validation error: {exc.errors()[0]['msg']}"

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            path = render_card(spec, output_dir=Path(tmpdir))
        except TemplateVariantNotFound as exc:
            return False, f"Template not found: {exc}"
        except Exception as exc:
            return False, f"Render error: {exc}"

        if not path.exists():
            return False, "PNG not created"
        size = path.stat().st_size
        if size < 1000:
            return False, f"PNG too small: {size} bytes"

    return True, f"OK ({size:,} bytes)"


def main() -> None:
    print("=" * 60)
    print(f"Figma SVG integration test  (template: {CARD_TEMPLATE_ID})")
    print("=" * 60)

    print("\n[Files]")
    file_errors = test_template_files_exist()
    if file_errors:
        for e in file_errors:
            print(f"  FAIL: {e}")
    else:
        print("  OK — all template files present")

    print(f"\n[Render] {len(FIGMA_CASES)} cases")
    passed = failed = 0
    for case in FIGMA_CASES:
        ok, msg = test_render_case(case)
        print(f"  {'PASS' if ok else 'FAIL'}  {case['label']}: {msg}")
        if ok:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed + len(file_errors)} failed")
    print("=" * 60)

    if failed or file_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
