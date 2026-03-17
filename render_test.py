#!/usr/bin/env python3
"""
render_test.py — local smoke test for the renderer pipeline.

Usage:
    DYLD_LIBRARY_PATH=/opt/homebrew/lib venv/bin/python render_test.py
    make test

No Telegram, no AI, no network required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pydantic import ValidationError

from app.services.card_spec import BackgroundMode, CardSize, CardSpec, Palette
from app.services.renderer import render_card
from app.templates.engine import load_template_config
from app.config import settings


def test_light_no_bg() -> None:
    spec = CardSpec(
        title="Как AI ускоряет работу маркетинга",
        subtitle="5 практических сценариев",
        tag="AI",
        palette=Palette.LIGHT,
        output_filename="test_light.png",
    )
    path = render_card(spec)
    print(f"[OK] light, no bg  → {path}")


def test_dark_no_bg() -> None:
    spec = CardSpec(
        title="Лучший способ предсказать будущее —",
        subtitle="это создать его самому.",
        palette=Palette.DARK,
        output_filename="test_dark.png",
    )
    path = render_card(spec)
    print(f"[OK] dark, no bg   → {path}")


def test_with_tag_only() -> None:
    spec = CardSpec(
        title="Новый отчёт: рынок ИИ вырос на 40%",
        tag="Новости",
        palette=Palette.LIGHT,
        output_filename="test_tag.png",
    )
    path = render_card(spec)
    print(f"[OK] with tag      → {path}")


def test_square() -> None:
    spec = CardSpec(
        size=CardSize(width=1080, height=1080),
        title="Квадратная карточка",
        subtitle="Instagram / VK",
        tag="Social",
        palette=Palette.LIGHT,
        output_filename="test_square.png",
    )
    path = render_card(spec)
    print(f"[OK] square        → {path}")


def test_with_bg_file() -> None:
    bg = Path("assets/images/sample_bg.png")
    if not bg.exists():
        print(f"[SKIP] bg_file  (place a PNG at {bg} to enable)")
        return
    spec = CardSpec(
        title="Карточка с фотофоном",
        subtitle="Pillow compositing",
        tag="Design",
        palette=Palette.LIGHT,
        background_mode=BackgroundMode.FILE,
        background_file=bg,
        output_filename="test_bg.png",
    )
    path = render_card(spec)
    print(f"[OK] with bg file  → {path}")


# --- Validation tests ---

def test_invalid_size() -> None:
    try:
        CardSpec(size=CardSize(width=800, height=600), title="x")
        print("[FAIL] expected ValidationError")
    except ValidationError as exc:
        print(f"[OK] invalid size  → {exc.errors()[0]['msg']}")


def test_empty_title() -> None:
    try:
        CardSpec(title="   ")
        print("[FAIL] expected ValidationError")
    except ValidationError as exc:
        print(f"[OK] empty title   → {exc.errors()[0]['msg']}")


def test_bad_bg_color() -> None:
    try:
        CardSpec(title="x", bg_color="red")
        print("[FAIL] expected ValidationError")
    except ValidationError as exc:
        print(f"[OK] bad bg_color  → {exc.errors()[0]['msg']}")


def test_long_title_wraps() -> None:
    """Long title (>50 chars) should render — max is now 120."""
    spec = CardSpec(
        title="Искусственный интеллект меняет правила игры в корпоративном маркетинге",
        subtitle="Обзор 2025",
        palette=Palette.DARK,
        output_filename="test_long_title.png",
    )
    path = render_card(spec)
    print(f"[OK] long title    → {path}")


def test_json_config_loaded() -> None:
    """template.json should load and contain expected keys."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    assert cfg, "card_v1.json not found or empty"
    assert "styles" in cfg, "missing 'styles' key"
    assert "palettes" in cfg, "missing 'palettes' key"
    assert cfg["styles"]["title"]["font_size"] == 96
    print(f"[OK] json config   → template_id={cfg['template_id']!r}, "
          f"title font_size={cfg['styles']['title']['font_size']}")


if __name__ == "__main__":
    print("Running renderer tests...\n")
    try:
        test_light_no_bg()
        test_dark_no_bg()
        test_with_tag_only()
        test_square()
        test_with_bg_file()
        test_long_title_wraps()
        print()
        test_invalid_size()
        test_empty_title()
        test_bad_bg_color()
        test_json_config_loaded()
        print("\nAll tests passed.")
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        raise
