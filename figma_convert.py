"""
figma_convert.py — конвертер Figma SVG → Jinja2-шаблон

Что делает автоматически:
  1. Сливает <tspan>-фрагменты одного <text> в одну строку
  2. Раскодирует HTML-сущности (&#39; → ', &#x2026; → …)
  3. Убирает clip-path обёртку (мешает cairosvg)
  4. Заменяет плейсхолдеры на Jinja2-выражения:
       TITLE    → {% for line in t_lines %} ... {% endfor %}
       SUBTITLE → {% if subtitle %} ... {% endif %}
       TAG      → {% if tag %} pill + text {% endif %}
       BG       → {% if bg_color %} / {% else %} overlay {% endif %}
  5. Добавляет блок вычисления позиций и цветов палитры

Соглашение о плейсхолдерах в Figma:
  Слой id  | Текст в Figma | Результат
  ---------|---------------|-----------------------------
  title    | TITLE         | заголовок, word_wrap(20, 2)
  subtitle | SUBTITLE      | подзаголовок, word_wrap(25, 2)
  tag      | TAG           | тег-пилюля по центру
  BG       | (любой rect)  | фоновый прямоугольник

Usage:
    python figma_convert.py input.svg output.svg
    python figma_convert.py input.svg   # перезаписывает input.svg
"""

import re
import sys
import html
from pathlib import Path


# ── Блоки, которые вставляются в начало SVG ──────────────────────────────────

PALETTE_BLOCK = """\
  <!-- ── Цвета палитры ─────────────────────────────────────────── -->
  {% if palette == "dark" %}
    {% set c_bg     = "#1A1A2E" %}
    {% set c_title  = "#FFFFFF" %}
    {% set c_sub    = "#AAAACC" %}
    {% set c_tag_bg = "#2E2E4E" %}
    {% set c_tag_fg = "#E8C547" %}
  {% else %}
    {% set c_bg     = "#F5F5F0" %}
    {% set c_title  = "#111111" %}
    {% set c_sub    = "#555555" %}
    {% set c_tag_bg = "#E8F0FE" %}
    {% set c_tag_fg = "#1A73E8" %}
  {% endif %}"""

POSITIONS_BLOCK = """\
  <!-- ── Позиции (вычисляются динамически) ─────────────────────── -->
  {% set pad      = 40  %}
  {% set gap      = 64  %}
  {% set tag_h    = 48  %}
  {% set title_lh = 106 %}
  {% set sub_lh   = 48  %}

  {% set t_lines  = title    | word_wrap(20, 2) %}
  {% set s_lines  = subtitle | word_wrap(25, 2) if subtitle else [] %}

  {% set title_y      = (pad + tag_h + gap) if tag else pad %}
  {% set title_bottom = title_y + (t_lines | length) * title_lh %}
  {% set sub_y        = title_bottom + gap %}"""

# ── Jinja2-блоки для замены плейсхолдеров ────────────────────────────────────

# Вставляется вместо <text id="title" ...>TITLE</text>
TITLE_BLOCK = """\
  <text font-family="'Panama', 'Arial Black', sans-serif"
        font-size="96" font-weight="700"
        fill="{{ c_title }}"
        text-anchor="middle"
        dominant-baseline="hanging">
    {% for line in t_lines %}
    <tspan x="W_PX_HALF"
           {% if loop.first %}y="{{ title_y }}"{% else %}dy="{{ title_lh }}"{% endif %}>{{ line }}</tspan>
    {% endfor %}
  </text>"""

# Вставляется вместо <text id="subtitle" ...>SUBTITLE</text>
SUBTITLE_BLOCK = """\
  {% if subtitle %}
  <text font-family="'Inter', 'Arial', sans-serif"
        font-size="40" font-weight="400"
        fill="{{ c_sub }}"
        text-anchor="middle"
        dominant-baseline="hanging">
    {% for line in s_lines %}
    <tspan x="W_PX_HALF"
           {% if loop.first %}y="{{ sub_y }}"{% else %}dy="{{ sub_lh }}"{% endif %}>{{ line }}</tspan>
    {% endfor %}
  </text>
  {% endif %}"""

# Вставляется вместо <text id="tag" ...>TAG</text>
TAG_BLOCK = """\
  {% if tag %}
  {% set pill_w = (tag | length) * 14 + 48 %}
  {% set pill_x = ((W_PX - pill_w) / 2) | int %}
  <rect x="{{ pill_x }}" y="{{ pad }}"
        width="{{ pill_w }}" height="{{ tag_h }}"
        rx="1000"
        fill="{{ c_tag_bg }}"/>
  <text x="W_PX_HALF" y="{{ pad + (tag_h // 2) }}"
        font-family="'Inter', 'Arial', sans-serif"
        font-size="24" font-weight="600"
        fill="{{ c_tag_fg }}"
        text-anchor="middle"
        dominant-baseline="middle">{{ tag }}</text>
  {% endif %}"""


def _get_canvas_size(svg_text: str) -> tuple[int, int]:
    """Извлекает width/height из корневого тега <svg>."""
    m = re.search(r'<svg[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', svg_text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1080, 1350


def unescape_jinja(text: str) -> str:
    """Раскодирует HTML-сущности внутри {{ }} и {% %} блоков."""
    def _unescape(m):
        return html.unescape(m.group(0))
    text = re.sub(r'\{\{.*?\}\}', _unescape, text, flags=re.DOTALL)
    text = re.sub(r'\{%.*?%\}', _unescape, text, flags=re.DOTALL)
    # Раскодируем также в атрибуте id= (там тоже бывают сущности)
    text = re.sub(r'id="[^"]*"', lambda m: html.unescape(m.group(0)), text)
    return text


def merge_tspans(svg_text: str) -> str:
    """Сливает все <tspan> внутри одного <text> в один, сохраняя позицию первого."""
    def _merge(m):
        full = m.group(0)
        tspan_texts = re.findall(r'<tspan[^>]*>(.*?)</tspan>', full, re.DOTALL)
        combined = ' '.join(t.strip() for t in tspan_texts).strip()
        # Убираем лишние пробелы внутри Jinja2-выражений
        combined = re.sub(r'\{\{\s+', '{{ ', combined)
        combined = re.sub(r'\s+\}\}', ' }}', combined)

        first_tspan = re.search(r'<tspan([^>]*)>', full)
        first_attrs = first_tspan.group(1) if first_tspan else ''
        text_attrs = re.search(r'<text([^>]*)>', full)
        text_attrs_str = text_attrs.group(1) if text_attrs else ''
        return f'<text{text_attrs_str}><tspan{first_attrs}>{combined}</tspan></text>'

    return re.sub(r'<text[^>]*>.*?</text>', _merge, svg_text, flags=re.DOTALL)


def remove_clippath_wrapper(svg_text: str) -> str:
    """Убирает clip-path атрибуты и <clipPath> определения."""
    svg_text = re.sub(r'\s+clip-path="url\(#[^)]+\)"', '', svg_text)
    svg_text = re.sub(r'\s*<clipPath[^>]*>.*?</clipPath>', '', svg_text, flags=re.DOTALL)
    svg_text = re.sub(r'\s*<defs>\s*</defs>', '', svg_text)
    return svg_text


def remove_artboard_rect(svg_text: str) -> str:
    """
    Убирает фоновый прямоугольник артборда Figma (серый/белый фон холста).
    Figma добавляет <rect> с fill цветом фона фрейма перед основным контентом.
    Определяем его как первый <rect> без id, у которого нет Jinja2-разметки.
    """
    # Ищем первый <rect> полного размера без id (артборд Figma)
    svg_text = re.sub(
        r'\n?<rect(?![^>]*\bid\s*=)[^>]*/>\n?',
        '\n',
        svg_text,
        count=1
    )
    return svg_text


def replace_placeholders(svg_text: str, width: int, height: int) -> str:
    """
    Заменяет <text> с плейсхолдерами TITLE / SUBTITLE / TAG
    на готовые Jinja2-блоки.
    Также заменяет первый фоновый <rect> на блок {% if bg_color %}.
    """

    # Подставляем реальный размер холста (W_PX → width, W_PX_HALF → width//2)
    def _fix_size(block: str) -> str:
        block = block.replace('W_PX_HALF', str(width // 2))
        block = block.replace('W_PX', str(width))
        return block

    title_block    = _fix_size(TITLE_BLOCK)
    subtitle_block = _fix_size(SUBTITLE_BLOCK)
    tag_block      = _fix_size(TAG_BLOCK)

    # TITLE — точное совпадение id="title" (не "subtitle"!)
    svg_text = re.sub(
        r'<text[^>]*\bid\s*=\s*"title"[^>]*>.*?</text>',
        title_block, svg_text, flags=re.DOTALL | re.IGNORECASE
    )
    # Запасной вариант: тspan с текстом TITLE (точный, без IGNORECASE)
    svg_text = re.sub(
        r'<text[^>]*><tspan[^>]*>\s*TITLE\s*</tspan></text>',
        title_block, svg_text, flags=re.DOTALL
    )

    # SUBTITLE — точное совпадение id="subtitle"
    svg_text = re.sub(
        r'<text[^>]*\bid\s*=\s*"subtitle"[^>]*>.*?</text>',
        subtitle_block, svg_text, flags=re.DOTALL | re.IGNORECASE
    )
    svg_text = re.sub(
        r'<text[^>]*><tspan[^>]*>\s*SUBTITLE\s*</tspan></text>',
        subtitle_block, svg_text, flags=re.DOTALL
    )

    # TAG — точное совпадение id="tag"
    svg_text = re.sub(
        r'<text[^>]*\bid\s*=\s*"tag"[^>]*>.*?</text>',
        tag_block, svg_text, flags=re.DOTALL | re.IGNORECASE
    )
    svg_text = re.sub(
        r'<text[^>]*><tspan[^>]*>\s*TAG\s*</tspan></text>',
        tag_block, svg_text, flags=re.DOTALL
    )

    # BG — первый <rect> полного размера → блок фона
    bg_block = (
        f'{{% if bg_color %}}\n'
        f'  <rect width="{width}" height="{height}" fill="{{{{ bg_color }}}}"/>\n'
        f'  {{% else %}}\n'
        f'  <rect width="{width}" height="{height}" fill="rgba(0,0,0,0.45)"/>\n'
        f'  {{% endif %}}'
    )
    svg_text = re.sub(
        rf'<(?:rect|path)[^>]*\bid\s*=\s*"[Bb][Gg][^"]*"[^>]*/?>',
        bg_block, svg_text
    )
    # Если нет id="BG", заменяем первый полноразмерный rect
    if '{% if bg_color %}' not in svg_text:
        svg_text = re.sub(
            rf'<rect\s[^>]*width="{width}"[^>]*height="{height}"[^>]*/?>',
            bg_block, svg_text, count=1
        )

    return svg_text


def add_header_blocks(svg_text: str) -> str:
    """Вставляет блоки палитры и позиций после открывающего тега <svg>."""
    if '{% if palette' in svg_text:
        return svg_text
    insert = '\n' + PALETTE_BLOCK + '\n\n' + POSITIONS_BLOCK + '\n'
    return re.sub(r'(<svg[^>]*>)', r'\1' + insert, svg_text, count=1)


def convert(input_path: Path, output_path: Path) -> None:
    src = input_path.read_text(encoding='utf-8')
    width, height = _get_canvas_size(src)

    src = remove_artboard_rect(src)
    src = merge_tspans(src)
    src = unescape_jinja(src)
    src = remove_clippath_wrapper(src)
    src = replace_placeholders(src, width, height)
    src = add_header_blocks(src)

    output_path.write_text(src, encoding='utf-8')
    print(f"✓ {input_path.name} ({width}×{height}) → {output_path}")

    # Отчёт
    issues = []
    if '&#' in src:
        issues.append("⚠️  остались HTML-сущности (&#...) — проверь вручную")
    if re.search(r'fill\s*=\s*"black"', src, re.IGNORECASE):
        n = len(re.findall(r'fill\s*=\s*"black"', src, re.IGNORECASE))
        issues.append(f"⚠️  {n}× fill=\"black\" — замени на {{ c_title }}, {{ c_sub }} и т.д.")
    if 'TITLE' in src or 'SUBTITLE' in src:
        issues.append("⚠️  остались нераспознанные плейсхолдеры TITLE / SUBTITLE")
    if not issues:
        print("   Проблем не обнаружено ✓")
    for w in issues:
        print("  ", w)


FIGMA_INPUT_DIR  = Path(__file__).parent / "figma_input"
TEMPLATES_DIR    = Path(__file__).parent / "assets" / "templates"


def convert_folder(input_dir: Path, output_dir: Path) -> int:
    """
    Обрабатывает все *.svg из input_dir → output_dir.
    Возвращает количество обработанных файлов.
    """
    files = sorted(input_dir.glob("*.svg"))
    if not files:
        print(f"В {input_dir} нет SVG-файлов.")
        return 0
    for f in files:
        convert(f, output_dir / f.name)
    return len(files)


if __name__ == '__main__':
    # Без аргументов — обрабатываем всю папку figma_input/
    if len(sys.argv) == 1:
        print(f"Обрабатываю figma_input/ → assets/templates/\n")
        n = convert_folder(FIGMA_INPUT_DIR, TEMPLATES_DIR)
        if n:
            print(f"\nГотово: {n} файл(ов). Запусти: make test")
        sys.exit(0)

    # С аргументами — режим одного файла
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp

    if not inp.exists():
        print(f"Файл не найден: {inp}")
        sys.exit(1)

    convert(inp, out)
