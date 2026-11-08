from core.pdf_unicode import install_unicode_maps
"""Vector charts rendered with Python and bundled fonts; no plotting/system font dependency."""
import pymupdf as fitz
from core.fonts import embed_fonts, draw_text as _draw_text, get_font

def draw_text(*args, **kwargs):
    return _draw_text(*args, resource_prefix="chart_", **kwargs)


def create_chart(facts, path):
    pdf = fitz.open()
    page = pdf.new_page(width=560, height=310)
    embed_fonts(page)
    left, top, right, bottom = 65, 35, 535, 255
    upper = max(facts['revenue']) * 1.15
    def point(index, value):
        return (left + index * (right-left) / 3, bottom - value / upper * (bottom-top))
    draw_text(page, left, 8, 'Output and cost by period (synthetic units)', 12, 'bold')
    for i in range(5):
        value = upper * i / 4
        y = bottom - value/upper * (bottom-top)
        page.draw_line((left,y),(right,y),color=(.86,.89,.88),width=.5)
        label = f'{value:.0f}'
        draw_text(page,left-12-get_font('latin').text_length(label,fontsize=9),y-6,label,9)
    for i, year in enumerate(facts['years']):
        x, _ = point(i, 0)
        draw_text(page,x-12,bottom+8,str(year),9)
    for key, label, color in [('revenue','Output',(.12,.40,.30)),('cost','Cost',(.70,.37,.19))]:
        points=[point(i,v) for i,v in enumerate(facts[key])]
        for a,b in zip(points,points[1:]): page.draw_line(a,b,color=color,width=1.5)
        for x,y in points: page.draw_circle((x,y),2.7,color=color,fill=color)
        offset=0 if key=='revenue' else 100
        page.draw_line((left+offset,292),(left+offset+20,292),color=color,width=1.5)
        draw_text(page,left+offset+27,285,label,9)
    page.draw_line((left,top),(left,bottom),color=(.25,.32,.29),width=.7)
    page.draw_line((left,bottom),(right,bottom),color=(.25,.32,.29),width=.7)
    pdf.subset_fonts()
    install_unicode_maps(pdf)
    pdf.save(path,garbage=4,deflate=True)
    pdf.close()
