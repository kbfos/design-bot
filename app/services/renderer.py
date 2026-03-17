"""
Renderer — orchestrates the full pipeline:
  CardSpec → SVG render (cairosvg) → [Pillow composite bg] → PNG file

Background image flow:
  1. SVG template renders with transparent bg (bg_color=None in context)
  2. cairosvg produces a PNG with transparent background areas
  3. Pillow opens the background image, crops/resizes to fill target size
  4. Pillow pastes the SVG layer on top → final RGB PNG
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from PIL import Image

from app.config import settings
from app.services.card_spec import BackgroundMode, CardSpec
from app.templates.engine import load_template_config, render_svg

# Single universal template — all cards use this
CARD_TEMPLATE_ID = "card_v1"

# ---------------------------------------------------------------------------
# Gradient definitions
# ---------------------------------------------------------------------------

# Each entry: (top_colour_rgb, bottom_colour_rgb)
GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "gradient_1": ((26, 26, 46),   (83, 52, 131)),   # deep blue → purple
    "gradient_2": ((15, 52, 96),   (22, 160, 133)),  # navy → teal
    "gradient_3": ((45, 27, 105),  (186, 73, 73)),   # indigo → rose
}


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

    Values from template_config (template.json) take precedence over built-in
    defaults, so designers can change fonts, colours and spacing via JSON
    without touching either the renderer or the SVG templates.
    """
    palette_name = spec.palette.value  # "light" or "dark"

    # ── Palette colours ───────────────────────────────────────────────────────
    # Fallback values match the legacy hardcoded SVG colours
    _fallback: dict[str, dict] = {
        "dark":  {"bg": "#1A1A2E", "text": "#FFFFFF", "sub": "#AAAACC",
                  "tag_bg": "#2E2E4E", "tag_fg": "#E8C547"},
        "light": {"bg": "#F5F5F0", "text": "#111111", "sub": "#555555",
                  "tag_bg": "#E8F0FE", "tag_fg": "#1A73E8"},
    }
    pal = template_config.get("palettes", {}).get(palette_name, {})
    fb  = _fallback[palette_name]

    c_bg     = pal.get("bg",     fb["bg"])
    c_title  = pal.get("text",   fb["text"])
    c_sub    = pal.get("sub",    fb["sub"])
    c_tag_bg = pal.get("tag_bg", fb["tag_bg"])
    c_tag_fg = pal.get("tag_fg", fb["tag_fg"])

    # ── Background colour for the SVG rect ────────────────────────────────────
    if has_bg_image:
        bg_color = None
        # Dark overlay (rgba(0,0,0,0.45) in SVG) makes light text mandatory
        c_title  = "#FFFFFF"
        c_sub    = "#DDDDDD"
        c_tag_bg = "#FFFFFF"
        c_tag_fg = "#111111"
    else:
        bg_color = spec.bg_color or c_bg

    # ── Layout ────────────────────────────────────────────────────────────────
    layout = template_config.get("layout", {})
    pad    = layout.get("padding", 40)
    gap    = layout.get("spacing", 64)

    # ── Font styles ───────────────────────────────────────────────────────────
    _default_styles: dict[str, dict] = {
        "title":    {"font_family": "'Panama', 'Arial Black', sans-serif",
                     "font_weight": "700", "font_size": 96,
                     "line_height": 106, "line_chars": 20, "max_lines": 2},
        "subtitle": {"font_family": "'Inter', Arial, sans-serif",
                     "font_weight": "400", "font_size": 40,
                     "line_height": 48,  "line_chars": 25, "max_lines": 2},
        "tag":      {"font_family": "'Inter', Arial, sans-serif",
                     "font_weight": "600", "font_size": 24,
                     "line_height": 48,  "line_chars": 40, "max_lines": 1},
    }
    json_styles = template_config.get("styles", {})
    style_title    = json_styles.get("title",    _default_styles["title"])
    style_subtitle = json_styles.get("subtitle", _default_styles["subtitle"])
    style_tag      = json_styles.get("tag",      _default_styles["tag"])

    return {
        # ── Content ───────────────────────────────────────────────────────────
        "title":    spec.title,
        "subtitle": spec.subtitle or "",
        "tag":      spec.tag or "",
        # ── Legacy vars (backward-compat with old SVG templates) ──────────────
        "palette":  palette_name,
        "bg_color": bg_color,
        # ── Resolved palette colours ──────────────────────────────────────────
        "c_bg":     c_bg,
        "c_title":  c_title,
        "c_sub":    c_sub,
        "c_tag_bg": c_tag_bg,
        "c_tag_fg": c_tag_fg,
        # ── Layout ────────────────────────────────────────────────────────────
        "pad": pad,
        "gap": gap,
        # ── Font styles (dicts) ───────────────────────────────────────────────
        "style_title":    style_title,
        "style_subtitle": style_subtitle,
        "style_tag":      style_tag,
        # ── Canvas size ───────────────────────────────────────────────────────
        "canvas_w": spec.size.width,
        "canvas_h": spec.size.height,
        # ── Text position ─────────────────────────────────────────────────────
        "text_layout": spec.text_layout.value,  # "top" | "center" | "bottom"
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
