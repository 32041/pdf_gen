"""Fonts are loaded ONLY from bundled files; system fonts are never queried."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import pymupdf as fitz
from core.pdf_unicode import record_characters, install_unicode_maps

FONT_DIR = Path(__file__).resolve().parents[1] / 'resources' / 'fonts'
FONT_FILES = {'cjk': 'NotoSansSC-Regular.ttf', 'latin': 'DejaVuSans.ttf', 'bold': 'DejaVuSans-Bold.ttf'}


def verify_resources():
    manifest = json.loads((FONT_DIR / 'manifest.json').read_text(encoding='utf-8'))
    for name, checksum in manifest.items():
        path = FONT_DIR / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise RuntimeError(f'Bundled font missing or damaged: {path}. Extract the complete project ZIP again.')


@lru_cache(maxsize=3)
def get_font(key):
    path = FONT_DIR / FONT_FILES[key]
    if not path.is_file():
        raise RuntimeError(f'Bundled font not found: {path}. Extract resources/ with the project.')
    return fitz.Font(fontfile=str(path))


def embed_fonts(page, keys=()):
    for key in keys:
        filename = FONT_FILES[key]
        page.insert_font(fontname=key, fontfile=str(FONT_DIR / filename))


def draw_text(page, x, top, text, size, key='latin', color=(.12, .16, .19), resource_prefix=''):
    font = get_font(key)
    resource_name = resource_prefix + key
    font_xref = page.insert_font(fontname=resource_name, fontfile=str(FONT_DIR / FONT_FILES[key]))
    record_characters(page.parent, font_xref, font, text)
    # PDF coordinates below use top-of-line; insert_text expects the baseline.
    page.insert_text((x, top + font.ascender * size), text, fontname=resource_name, fontsize=size, color=color)


def wrap_text(text, font, size, width):
    """Width-aware wrapping for Chinese, Latin and mixed text, without system shaping tools."""
    if width <= 0:
        raise ValueError('Text area width must be positive')
    lines = []
    for paragraph in text.split('\n'):
        rest = paragraph.strip()
        if not rest:
            lines.append('')
        while rest:
            length = 0
            end = 0
            for index, char in enumerate(rest):
                char_width = font.text_length(char, fontsize=size)
                if length + char_width > width + .001:
                    break
                length += char_width
                end = index + 1
            if end == 0:
                raise ValueError('Text area too narrow for a character')
            if end < len(rest):
                last_space = rest.rfind(' ', 0, end + 1)
                if last_space >= end // 2:
                    end = last_space
                # Avoid starting a line with common Chinese punctuation.
                elif rest[end] in '，。；：！？、）》」』】' and end > 1:
                    end -= 1
            lines.append(rest[:end].rstrip())
            rest = rest[end:].lstrip()
    return lines
