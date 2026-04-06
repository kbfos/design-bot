"""
Typography utilities for text preprocessing before card rendering.
"""
import re

# Non-breaking space (U+00A0)
_NBSP = "\u00A0"

# Match any single-character word followed by a regular space.
# (?<!\w) — not preceded by a word character (i.e. it IS the start of a word)
# (\w)    — captures exactly one word character (letter/digit, any Unicode script)
# ' '     — followed by a regular space
_SINGLE_WORD_RE = re.compile(r"(?<!\w)(\w) ")


def fix_hanging_prepositions(text: str) -> str:
    """
    Replace the space after any single-character word with a non-breaking space.

    Prevents short prepositions and conjunctions (в, к, с, и, а, о, у, a, I…)
    from being left alone at the end of a line during SVG word-wrap.

    Works for Russian, Latin, and mixed text. Does not affect multi-character words.

    Examples:
        "в мире"  → "в\u00A0мире"
        "к нам"   → "к\u00A0нам"
        "a big"   → "a\u00A0big"
        "на рынке" → "на рынке"  (unchanged — "на" is 2 chars)
    """
    return _SINGLE_WORD_RE.sub(r"\1" + _NBSP, text)
