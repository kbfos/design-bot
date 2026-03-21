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

import json
from app.services.card_spec import BackgroundMode, CardSize, CardSpec, Palette, TextLayout
from app.services.renderer import _TOKENS, _build_context, _resolve_component, render_card
from app.templates.engine import load_template_config, render_svg
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


def test_template_config_structure() -> None:
    """card_v1.json should contain only structural data (slots, background) — no design values."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    assert cfg, "card_v1.json not found or empty"
    assert "slots" in cfg, "missing 'slots' key"
    assert "background" in cfg, "missing 'background' key"
    assert "styles" not in cfg, "design values (styles) must be in design_tokens.json, not card_v1.json"
    assert "palettes" not in cfg, "design values (palettes) must be in design_tokens.json, not card_v1.json"
    assert "layout" not in cfg, "design values (layout) must be in design_tokens.json, not card_v1.json"
    print(f"[OK] card_v1.json  → structural only, slots={list(cfg['slots'])}")


def test_design_tokens_loaded() -> None:
    """design_tokens.json must load and contain all design values synced with Figma (node 3:521)."""
    t = _TOKENS

    # ── Resolved component specs (primitives merged, sub-objects flattened) ───
    title    = _resolve_component("title")
    subtitle = _resolve_component("subtitle")
    tag      = _resolve_component("tag")
    layout   = t["layout"]
    light    = t["themes"]["light"]
    dark     = t["themes"]["dark"]
    photo    = t["themes"]["photo"]

    # Typography primitives via resolved components (Figma node 3:521)
    assert title["font_size"] == 104,        f"title font_size: {title['font_size']}"
    assert title["letter_spacing"] == -3.12, f"title letter_spacing: {title['letter_spacing']}"
    assert title["line_height"] == 104,      f"title line_height: {title['line_height']}"
    assert title["line_chars"] == 18,        f"title line_chars: {title['line_chars']}"
    assert subtitle["font_size"] == 40,      f"subtitle font_size: {subtitle['font_size']}"
    assert subtitle["line_height"] == 48,    f"subtitle line_height: {subtitle['line_height']}"

    # Tag component (typography + shape + colors, all flattened)
    assert tag["font_size"] == 24,           f"tag font_size: {tag['font_size']}"
    assert tag["font_weight"] == 400,        f"tag font_weight: {tag['font_weight']}"
    assert tag["border_width"] == 2,         f"tag border_width: {tag['border_width']}"
    assert tag["padding_h"] == 32,           f"tag padding_h: {tag['padding_h']}"
    assert tag["padding_v"] == 16,           f"tag padding_v: {tag['padding_v']}"
    assert tag["style"] == "outline",        f"tag style: {tag['style']}"
    assert tag["radius_mode"] == "full",     f"tag radius_mode: {tag['radius_mode']}"
    assert tag["border_color"] == "#000000", f"tag border_color: {tag['border_color']}"
    assert tag["text_color"] == "#000000",   f"tag text_color: {tag['text_color']}"
    assert tag["background_color"] == "transparent", f"tag background_color: {tag['background_color']}"

    # Structure — primitives exist as separate atoms
    assert "primitives" in t,               "primitives block missing"
    assert "typography" in t["primitives"], "primitives.typography missing"
    assert "shape" in t["primitives"],      "primitives.shape missing"
    assert "components" in t,              "components block missing"
    assert "render_rules" in t,            "render_rules block missing"

    # Layout
    assert layout["padding"] == 40,  f"layout padding: {layout['padding']}"
    assert layout["spacing"] == 64,  f"layout spacing: {layout['spacing']}"

    # Themes — light has no tag overrides (uses component defaults)
    assert "tag_bg" not in light,  "light theme must not have tag_bg (moved to components.tag)"
    assert "tag_fg" not in light,  "light theme must not have tag_fg (moved to components.tag)"
    # Dark/photo override tag to white
    assert dark["tag_border_color"].lower() == "#ffffff", f"dark tag_border_color: {dark.get('tag_border_color')}"
    assert dark["tag_text_color"].lower()   == "#ffffff", f"dark tag_text_color: {dark.get('tag_text_color')}"
    assert "overlay" in photo,  "photo theme missing 'overlay'"
    assert photo["tag_border_color"].lower() == "#ffffff"
    assert photo["tag_text_color"].lower()   == "#ffffff"

    # Gradients
    assert "gradient_1" in t["gradients"]
    assert "gradient_2" in t["gradients"]
    assert "gradient_3" in t["gradients"]

    print(f"[OK] design_tokens → title {title['font_size']}px, "
          f"tracking={title['letter_spacing']}, gap={layout['spacing']}, "
          f"tag={tag['style']!r} radius_mode={tag['radius_mode']!r}")


# --- Tag rendering tests ---

def _make_tag_spec(palette: Palette, **kwargs) -> CardSpec:
    return CardSpec(
        title="Dubai Hills или Palm Jumeirah?",
        tag="Недвижимость",
        palette=palette,
        **kwargs,
    )


def test_tag_context_light() -> None:
    """Light palette: tag uses token defaults — border/text #000000, fill transparent."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    spec = _make_tag_spec(Palette.LIGHT)
    ctx = _build_context(spec, has_bg_image=False, template_config=cfg)

    assert ctx["c_tag_border"] == "#000000", f"c_tag_border expected '#000000', got {ctx['c_tag_border']!r}"
    assert ctx["c_tag_text"]   == "#000000", f"c_tag_text expected '#000000', got {ctx['c_tag_text']!r}"
    print(f"[OK] tag ctx light  → border={ctx['c_tag_border']!r} text={ctx['c_tag_text']!r}")


def test_tag_context_dark() -> None:
    """Dark palette: tag border/text must be white (#ffffff)."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    spec = _make_tag_spec(Palette.DARK)
    ctx = _build_context(spec, has_bg_image=False, template_config=cfg)

    assert ctx["c_tag_border"].lower() == "#ffffff", f"c_tag_border expected '#ffffff', got {ctx['c_tag_border']!r}"
    assert ctx["c_tag_text"].lower()   == "#ffffff", f"c_tag_text expected '#ffffff', got {ctx['c_tag_text']!r}"
    print(f"[OK] tag ctx dark   → border={ctx['c_tag_border']!r} text={ctx['c_tag_text']!r}")


def test_tag_context_photo() -> None:
    """Photo mode: tag border/text must be white (#FFFFFF), NOT dark."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    spec = _make_tag_spec(Palette.LIGHT)
    ctx = _build_context(spec, has_bg_image=True, template_config=cfg)

    assert ctx["c_tag_border"].upper() == "#FFFFFF", (
        f"c_tag_border expected '#FFFFFF' on photo overlay, got {ctx['c_tag_border']!r}"
    )
    assert ctx["c_tag_text"].upper() == "#FFFFFF", (
        f"c_tag_text expected '#FFFFFF' on photo overlay, got {ctx['c_tag_text']!r}"
    )
    print(f"[OK] tag ctx photo  → border={ctx['c_tag_border']!r} text={ctx['c_tag_text']!r}")


def test_tag_svg_outline() -> None:
    """Rendered SVG must use fill='transparent' + stroke on tag pill (outline style)."""
    cfg = load_template_config("card_v1", settings.templates_dir)
    spec = _make_tag_spec(Palette.LIGHT)
    ctx = _build_context(spec, has_bg_image=False, template_config=cfg)

    svg = render_svg("card_v1", width=1080, height=1350, context=ctx)

    assert 'id="tag_bg"' in svg, "tag_bg rect missing from SVG"
    assert 'fill="transparent"' in svg, "tag pill must have fill='transparent' (outline style)"
    assert "stroke=" in svg, "tag pill must have stroke= attribute"
    # rx = tag_h // 2 = (font_size + padding_v*2) // 2 = (24 + 32) // 2 = 28
    assert 'rx="28"' in svg, "tag pill rx must equal tag_h // 2"
    assert 'fill="#eeeeee"' not in svg, "old filled tag_bg still present in SVG"
    assert 'fill="#222222"' not in svg, "old filled tag_bg still present in SVG"
    print("[OK] tag svg outline → fill=transparent, stroke present, rx=28")


def test_tag_dark_render() -> None:
    """Dark palette with tag must render without errors."""
    spec = _make_tag_spec(
        Palette.DARK,
        subtitle="Сравниваем районы",
        output_filename="test_tag_dark.png",
    )
    path = render_card(spec)
    assert path.exists(), f"output file not created: {path}"
    print(f"[OK] tag dark render → {path}")


def test_tag_square_dark_render() -> None:
    """Square format, dark palette with tag."""
    spec = _make_tag_spec(
        Palette.DARK,
        size=CardSize(width=1080, height=1080),
        output_filename="test_tag_square_dark.png",
    )
    path = render_card(spec)
    assert path.exists(), f"output file not created: {path}"
    print(f"[OK] tag square dark → {path}")


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
        test_template_config_structure()
        test_design_tokens_loaded()
        print()
        test_tag_context_light()
        test_tag_context_dark()
        test_tag_context_photo()
        test_tag_svg_outline()
        test_tag_dark_render()
        test_tag_square_dark_render()
        print("\nAll tests passed.")
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        raise
