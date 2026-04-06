"""
Renderer — orchestrates the full pipeline:
  CardSpec → SVG render (cairosvg) → [Pillow composite bg] → PNG file

Background image flow:
  1. SVG template renders with transparent bg (bg_color=None in context)
  2. cairosvg produces a PNG with transparent background areas
  3. Pillow opens the background image, crops/resizes to fill target size
  4. Pillow pastes the SVG layer on top → final RGB PNG

All design values (colours, typography, spacing, gradients) are loaded from
assets/design_tokens.json — the single source of truth synced with Figma.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFont

from app.config import settings
from app.services.card_spec import BackgroundMode, CardSpec
from app.templates.engine import load_template_config, render_svg
from app.utils.typography import fix_hanging_prepositions

# Single universal template — all cards use this
CARD_TEMPLATE_ID = "card_v1"

# ---------------------------------------------------------------------------
# Design tokens — loaded once at startup
# ---------------------------------------------------------------------------

def _load_design_tokens() -> dict:
    path = settings.assets_dir / "design_tokens.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)

_TOKENS: dict = _load_design_tokens()


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _resolve_component(name: str) -> dict:
    """
    Resolve a component spec into a flat dict, ready for template injection.

    $-prefixed keys are dot-path references into _TOKENS (e.g.
    "$typography": "primitives.typography.title" → merged in-place).
    Nested dict values (e.g. "colors": {...}) are flattened one level.
    """
    result: dict = {}
    for key, val in _TOKENS["components"][name].items():
        if key.startswith("$"):
            node: dict = _TOKENS
            for segment in val.split("."):
                node = node[segment]  # type: ignore[assignment]
            result.update(node)
        elif isinstance(val, dict):
            result.update(val)          # flatten sub-objects (e.g. colors)
        else:
            result[key] = val
    return result


# Gradients built from design_tokens.json
GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    gid: (_hex_to_rgb(g["start"]), _hex_to_rgb(g["end"]))
    for gid, g in _TOKENS["gradients"].items()
}


_TAG_FONT_SEARCH = [
    Path.home() / "Library/Fonts/Inter-Regular.otf",
    Path("/Library/Fonts/Inter-Regular.otf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


def _load_tag_font(font_size: int) -> ImageFont.FreeTypeFont:
    for p in _TAG_FONT_SEARCH:
        if p.exists():
            return ImageFont.truetype(str(p), font_size)
    return ImageFont.load_default(size=font_size)


def _measure_tag_pill(text: str, font_size: int, padding_h: int) -> int:
    """Return pill width = measured text width + horizontal padding on both sides."""
    font = _load_tag_font(font_size)
    bbox = font.getbbox(text)          # (left, top, right, bottom)
    text_w = bbox[2] - bbox[0]
    return text_w + padding_h * 2


def _generate_gradient_png(
    gradient_id: str, width: int, height: int, output_path: Path
) -> None:
    """Render a vertical linear gradient and save it as PNG."""
    c1, c2 = GRADIENTS[gradient_id]
    # Build a 1×height strip, then stretch to full width
    strip = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(height - 1, 1)
        pixel = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        strip.putpixel((0, y), pixel)  # type: ignore[arg-type]
    strip.resize((width, height), Image.NEAREST).save(output_path)


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _render_png_cairosvg(svg_content: str, width: int, height: int, output_path: Path) -> None:
    import cairosvg  # type: ignore

    cairosvg.svg2png(
        bytestring=svg_content.encode(),
        write_to=str(output_path),
        output_width=width,
        output_height=height,
    )


def _render_png_resvg(svg_content: str, width: int, height: int, output_path: Path) -> None:
    """Stub for resvg CLI backend. Install: cargo install resvg"""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="w") as tmp:
        tmp.write(svg_content)
        tmp_path = tmp.name

    subprocess.run(
        ["resvg", "--width", str(width), "--height", str(height), tmp_path, str(output_path)],
        check=True,
    )
    Path(tmp_path).unlink(missing_ok=True)


_BACKENDS = {
    "cairosvg": _render_png_cairosvg,
    "resvg": _render_png_resvg,
}


# ---------------------------------------------------------------------------
# Pillow compositing
# ---------------------------------------------------------------------------

def _composite_background(bg_path: Path, overlay_path: Path, width: int, height: int) -> None:
    """
    Place bg_path image behind the SVG overlay PNG and save the result.

    Uses cover-fit (fill canvas, centre-crop) for the background image.
    The overlay PNG must have an alpha channel so transparent areas
    reveal the background.
    """
    bg = Image.open(bg_path).convert("RGBA")
    bg_w, bg_h = bg.size
    scale = max(width / bg_w, height / bg_h)
    new_w, new_h = int(bg_w * scale), int(bg_h * scale)
    bg = bg.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    bg = bg.crop((left, top, left + width, top + height))

    overlay = Image.open(overlay_path).convert("RGBA")
    bg.paste(overlay, (0, 0), overlay)
    bg.convert("RGB").save(overlay_path, "PNG", optimize=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve_bg_image(spec: CardSpec) -> Optional[Path]:
    """Return a local Path to the background image, or None."""
    # ── Gradient: generate PNG on-the-fly ────────────────────────────────────
    if spec.background_mode == BackgroundMode.GRADIENT:
        gid = spec.background_gradient_id or ""
        if gid not in GRADIENTS:
            return None
        tmp = settings.output_dir / f"_grad_{gid}_{spec.size.width}x{spec.size.height}.png"
        _generate_gradient_png(gid, spec.size.width, spec.size.height, tmp)
        return tmp

    # ── File / Generate: load from disk ──────────────────────────────────────
    if spec.background_mode not in (BackgroundMode.FILE, BackgroundMode.GENERATE):
        return None
    if not spec.background_file:
        return None

    p = Path(spec.background_file)
    if p.exists():
        return p
    fallback = settings.assets_dir / "images" / p
    return fallback if fallback.exists() else None


def _build_context(spec: CardSpec, has_bg_image: bool, template_config: dict) -> dict:
    """
    Map CardSpec fields to Jinja2 template variables.

    All design values come from assets/design_tokens.json (single source of
    truth synced with Figma). template_config is kept for structural metadata
    only (slots, background modes).
    """
    palette_name = spec.palette.value  # "light" or "dark"

    # ── Theme colours — from design_tokens.json → themes ──────────────────────
    theme = _TOKENS["themes"][palette_name]

    c_bg    = theme["bg"]
    c_title = theme["title"]
    c_sub   = theme["subtitle"]

    # ── Resolved component specs (primitives merged, colors flattened) ─────────
    tag_style = _resolve_component("tag")

    # Tag colours: theme overrides (dark/photo) take precedence over component defaults
    c_tag_border = theme.get("tag_border_color", tag_style["border_color"])
    c_tag_text   = theme.get("tag_text_color",   tag_style["text_color"])

    # ── Background colour / photo overlay ─────────────────────────────────────
    photo = _TOKENS["themes"]["photo"]
    if has_bg_image:
        bg_color     = None
        bg_overlay   = photo["overlay"]
        c_title      = photo["title"]
        c_sub        = photo["subtitle"]
        c_tag_border = photo.get("tag_border_color", tag_style["border_color"])
        c_tag_text   = photo.get("tag_text_color",   tag_style["text_color"])
    else:
        bg_color   = spec.bg_color or c_bg
        bg_overlay = photo["overlay"]  # passed to template but unused when bg_color is set

    # ── Layout — from design_tokens.json ──────────────────────────────────────
    layout = _TOKENS["layout"]
    pad    = layout["padding"]
    gap    = layout["spacing"]

    # ── Tag geometry — measured precisely, not estimated ──────────────────────
    tag_h  = tag_style["font_size"] + tag_style["padding_v"] * 2
    tag_rx = tag_h // 2
    pill_w = (
        _measure_tag_pill(spec.tag, tag_style["font_size"], tag_style["padding_h"])
        if spec.tag else 0
    )

    return {
        # ── Content ───────────────────────────────────────────────────────────
        "title":    fix_hanging_prepositions(spec.title),
        "subtitle": fix_hanging_prepositions(spec.subtitle) if spec.subtitle else "",
        "tag":      spec.tag or "",
        # ── Theme info ────────────────────────────────────────────────────────
        "palette":     palette_name,
        "bg_color":    bg_color,
        "bg_overlay":  bg_overlay,
        # ── Resolved theme colours ────────────────────────────────────────────
        "c_bg":         c_bg,
        "c_title":      c_title,
        "c_sub":        c_sub,
        "c_tag_border": c_tag_border,
        "c_tag_text":   c_tag_text,
        # ── Layout ────────────────────────────────────────────────────────────
        "pad": pad,
        "gap": gap,
        # ── Component specs (flat dicts, resolved from primitives) ────────────
        "style_title":    _resolve_component("title"),
        "style_subtitle": _resolve_component("subtitle"),
        "style_tag":      tag_style,
        # ── Tag geometry (pre-computed) ───────────────────────────────────────
        "pill_w":  pill_w,
        "tag_rx":  tag_rx,
        # ── Canvas size ───────────────────────────────────────────────────────
        "canvas_w": spec.size.width,
        "canvas_h": spec.size.height,
        # ── Text position ─────────────────────────────────────────────────────
        "text_layout": spec.text_layout.value,
    }


def render_card(spec: CardSpec, output_dir: Optional[Path] = None) -> Path:
    """
    Full render pipeline: SVG template → PNG file.

    Parameters
    ----------
    spec : CardSpec
        Complete card specification.
    output_dir : Path, optional
        Where to write the PNG. Defaults to settings.output_dir.

    Returns
    -------
    Path
        Absolute path to the generated PNG file.

    Raises
    ------
    TemplateVariantNotFound
        If no SVG file exists for the given size combination.
    """
    out_dir = output_dir or settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = spec.output_filename or f"card_{uuid.uuid4().hex[:8]}.png"
    output_path = out_dir / filename

    bg_path = _resolve_bg_image(spec)
    template_config = load_template_config(CARD_TEMPLATE_ID, settings.templates_dir)
    context = _build_context(spec, has_bg_image=bg_path is not None,
                             template_config=template_config)

    svg_content = render_svg(
        template_id=CARD_TEMPLATE_ID,
        width=spec.size.width,
        height=spec.size.height,
        context=context,
    )
    backend_fn = _BACKENDS.get(settings.renderer_backend, _render_png_cairosvg)
    backend_fn(svg_content, spec.size.width, spec.size.height, output_path)

    if bg_path is not None:
        _composite_background(bg_path, output_path, spec.size.width, spec.size.height)

    return output_path.resolve()
