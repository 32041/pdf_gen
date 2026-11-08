"""Mixed-language cells with bounded wrapping; no system-font fallbacks."""
from threading import RLock
_NATIVE_FONT_LOCK=RLock()
from core.fonts import get_font,wrap_text,draw_text


def cell_layout(text,width,row_height):
    with _NATIVE_FONT_LOCK:
        return _cell_layout(text,width,row_height)


def _cell_layout(text,width,row_height):
    key='latin'
    if any(not c.isspace() and not get_font(key).has_glyph(ord(c)) for c in text):key='cjk'
    font=get_font(key)
    if any(not c.isspace() and not font.has_glyph(ord(c)) for c in text):raise ValueError('Table cell contains an unsupported glyph')
    for size in [8.5,8,7.5,7,6.5]:
        lines=wrap_text(text,font,size,width-6)
        line_height=(font.ascender-font.descender)*size
        if len(lines)*line_height<=row_height-4:return key,size,lines,line_height
    raise ValueError('Table cell is too long for a readable row; shorten LLM cell text')


def draw_cell(page,text,x,y,width,row_height):
    key,size,lines,height=cell_layout(text,width,row_height)
    top=y+(row_height-len(lines)*height)/2
    for line in lines:
        draw_text(page,x+3,top,line,size,key)
        top+=height
