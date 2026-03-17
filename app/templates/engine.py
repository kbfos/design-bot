"""
Template engine — renders an SVG template via Jinja2
and returns the final SVG string ready for PNG conversion.

Template filename convention:
    {template_id}_{width}x{height}.svg
    e.g.  blog_cover_v1_1080x1350.svg
          blog_cover_v1_1080x1080.svg

Background images are NOT embedded here.
Pillow handles compositing in renderer.py after cairosvg renders the SVG overlay.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import settings


def _word_wrap(text: str, width: int = 25, max_lines: int = 2) -> list[str]:
    """
    Wrap text at word boundaries and return a list of lines.

    Used as a Jinja2 filter in SVG templates:
        {% for line in title | word_wrap(20, 2) %}

    Parameters
    ----------
    text      : input string
    width     : max characters per line
    max_lines : max number of lines to return (excess is truncated with …)
    """
    if not text:
        return []
    lines = textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[: width - 1] + "…") if len(last) >= width else (last + "…")
    return lines


class TemplateVariantNotFound(Exception):
    """Raised when no SVG file exists for a given template_id + size combination."""

    def __init__(self, template_id: str, width: int, height: int, templates_dir: Path) -> None:
        self.template_id = template_id
        self.width = width
        self.height = height
        expected = f"{template_id}_{width}x{height}.svg"
        super().__init__(
            f"No template variant found for '{template_id}' at {width}x{height}. "
            f"Expected file: {templates_dir / expected}"
        )


def _load_jinja_env(templates_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        autoescape=True,  # SVG is XML — escape & < > in user-provided values
    )
    env.filters["word_wrap"] = _word_wrap
    return env


def load_template_config(template_id: str, templates_dir: Path) -> dict:
    """
    Load {template_id}.json from templates_dir.

    Returns an empty dict if the file does not exist — callers must
    provide sensible fallback values when the JSON is absent.
    """
    path = templates_dir / f"{template_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def resolve_template_filename(
    template_id: str,
    width: int,
    height: int,
    templates_dir: Path,
) -> str:
    """
    Return the SVG filename for the requested template variant.

    Raises TemplateVariantNotFound if the file does not exist.
    """
    filename = f"{template_id}_{width}x{height}.svg"
    if not (templates_dir / filename).exists():
        raise TemplateVariantNotFound(template_id, width, height, templates_dir)
    return filename


def render_svg(
    template_id: str,
    width: int,
    height: int,
    context: dict,
    templates_dir: Optional[Path] = None,
) -> str:
    """
    Render an SVG template with the given context dict.

    Background images are handled by Pillow in renderer.py, not here.
    Pass ``bg_color=None`` (or omit it) in context to get a transparent
    background canvas that Pillow can composite behind.

    Parameters
    ----------
    template_id : str
        Template base name, e.g. "blog_cover_v1".
    width, height : int
        Output dimensions used to select the correct template variant.
    context : dict
        Variables injected into the Jinja2 template.
    templates_dir : Path, optional
        Override the default templates directory from settings.

    Returns
    -------
    str
        Fully rendered SVG as a string.

    Raises
    ------
    TemplateVariantNotFound
        If no SVG file exists for the given template_id + size combination.
    """
    tdir = templates_dir or settings.templates_dir
    env = _load_jinja_env(tdir)
    template_file = resolve_template_filename(template_id, width, height, tdir)
    template = env.get_template(template_file)
    return template.render(**context)
