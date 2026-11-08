from core.pdf_unicode import install_unicode_maps
"""Pure-Python pagination with explicit float scheduling and recorded geometry."""
import json
from dataclasses import dataclass, field
import pymupdf as fitz
from core.fonts import get_font, embed_fonts, draw_text, wrap_text
from document_types import PROFILES

PAGE_W, PAGE_H = 595.276, 841.89


@dataclass
class Column:
    x: float
    width: float
    top: float
    bottom: float
    cursor: float
    reserved_top: float = 0
    reserved_bottom: float = 0
    flow: list = field(default_factory=list)


class Paginator:
    def __init__(self, doc):
        self.doc = doc
        self.profile = PROFILES[doc.kind]
        self.margin = float(self.profile['margin'].removesuffix('mm')) * 72 / 25.4
        self.size = self.profile['font_size']
        self.key = 'cjk' if doc.language == 'zh' else 'latin'
        self.pages = []
        self.page = None
        self.col_index = 0
        self.missing = set()
        self.new_page(first=True)

    def operation(self, kind, x, y, width, height, **kwargs):
        op = dict(kind=kind, bbox=[x,y,x+width,y+height], **kwargs)
        self.page['operations'].append(op)
        return op

    def fixed_text(self, text, top, size, key, centered=False):
        width = PAGE_W - self.margin*2
        lines = wrap_text(text, get_font(key), size, width)
        height = max(1.55, get_font(key).ascender-get_font(key).descender) * size
        for line in lines:
            x = (PAGE_W-get_font(key).text_length(line,fontsize=size))/2 if centered else self.margin
            self.operation('text',x,top,width,height,text=line,size=size,font=key)
            top += height
        return top

    def new_page(self, first=False, floating=False):
        self.page = dict(operations=[],float_only=floating,columns=[])
        self.pages.append(self.page)
        top = self.margin
        if first:
            top = self.fixed_text(self.doc.title, top, 18, self.key, centered=True)+12
            top = self.fixed_text('SYNTHETIC DOCUMENT | 2025',top,9,'latin',centered=True)+14
            notice = '本文件为合成样例，所有数据与机构均为虚构。' if self.doc.language=='zh' else 'Synthetic example. All data and organisations are fictional.'
            top = self.fixed_text(notice,top,9,self.key)+15
        count = self.profile['columns']
        gap = 20
        width = (PAGE_W-self.margin*2-gap*(count-1))/count
        for i in range(count):
            self.page['columns'].append(Column(self.margin+i*(width+gap),width,top,PAGE_H-self.margin-10,top))
        self.col_index = 0

    @property
    def column(self):
        return self.page['columns'][self.col_index]

    def next_column(self):
        if self.col_index+1 < len(self.page['columns']):
            self.col_index += 1
        else:
            self.new_page()

    def text(self, text, size=None, heading=False, ref_id=None):
        size = size or self.size
        key = self.key if self.doc.language=='zh' else ('bold' if heading else 'latin')
        font = get_font(key)
        self.missing.update(c for c in set(text) if not c.isspace() and not font.has_glyph(ord(c)))
        lines = wrap_text(text,font,size,self.column.width)
        height = max(1.55,font.ascender-font.descender)*size
        keep = height*(len(lines)+2) if heading else height
        if self.column.cursor+keep > self.column.bottom-self.column.reserved_bottom:
            self.next_column()
        for index,line in enumerate(lines):
            col = self.column
            if col.cursor+height > col.bottom-col.reserved_bottom:
                self.next_column()
                col = self.column
            op = self.operation('text',col.x,col.cursor,col.width,height,text=line,size=size,font=key,
                                reference_id=ref_id if index==0 else None)
            col.flow.append(op)
            col.cursor += height
        self.column.cursor += 7 if not heading else 4

    def asset_height(self, asset_id, width):
        caption = self.caption(asset_id)
        cap_lines = wrap_text(caption,get_font(self.key),8.5,width)
        body = width*310/560 if asset_id==0 else 113
        return body+8+len(cap_lines)*14+10

    def caption(self, asset_id):
        if self.doc.language=='zh':
            return '图 1：模拟产出与成本趋势' if asset_id==0 else '表 1：统一口径的分期数据'
        return 'Figure 1: Simulated output and cost' if asset_id==0 else 'Table 1: Canonical period ledger'

    def asset(self, asset_id, mode):
        if mode=='float_page':
            self.new_page(floating=True)
            width = PAGE_W-self.margin*2
            height = self.asset_height(asset_id,width)
            self.operation('asset',self.margin,(PAGE_H-height)/2,width,height,asset_id=asset_id,target=mode)
            self.new_page()
            return
        if mode=='next_page':
            self.new_page()
        col = self.column
        height = self.asset_height(asset_id,col.width)
        if height > col.bottom-col.top:
            raise ValueError('Asset exceeds a full column')
        if col.cursor+height > col.bottom-col.reserved_bottom:
            self.next_column()
            col = self.column
        if mode=='top':
            y = col.top+col.reserved_top
            # Move already planned flow down; geometry changes before PDF drawing.
            for op in col.flow:
                op['bbox'][1] += height
                op['bbox'][3] += height
            col.reserved_top += height
            col.cursor += height
        elif mode=='bottom':
            y = col.bottom-col.reserved_bottom-height
            col.reserved_bottom += height
        else:
            y = col.cursor
            col.cursor += height
        op = self.operation('asset',col.x,y,col.width,height,asset_id=asset_id,target=mode)
        if mode in ('adjacent','next_page'):
            col.flow.append(op)

    def build(self):
        cn = self.doc.language=='zh'
        if self.doc.kind=='official': self.text('各试点责任单位：' if cn else 'To: Pilot programme teams')
        if self.doc.kind=='annual_report':
            f = self.doc.facts
            self.text(('核心指标（模拟单位）：' if cn else 'Key indicators (synthetic units): ')+f"Output {f['revenue'][-1]:.2f}; Cost {f['cost'][-1]:.2f}; Balance {f['profit'][-1]:.2f}.")
        index = 0
        def walk(nodes, prefix=()):
            for i,node in enumerate(nodes,1):
                numbers = prefix+(i,)
                yield node,numbers
                yield from walk(node.children,numbers)
        for node,numbers in walk(self.doc.sections):
            size = self.size + {1:4,2:2,3:0}[len(numbers)]
            self.text('.'.join(map(str,numbers))+'  '+node.title,size,heading=True)
            for j,paragraph in enumerate(node.paragraphs):
                self.text(paragraph)
                if j==0 and index<2:
                    reference = ('趋势见图 1。' if index==0 else '明细见表 1。') if cn else ('The trend is shown in Figure 1.' if index==0 else 'Details are reported in Table 1.')
                    self.text(reference,ref_id=index)
                    self.asset(index,self.doc.placements[index])
                    index += 1
        if self.doc.kind=='official':
            self.text('模拟项目办公室　2025-12-31' if cn else 'Fictional Programme Office | 2025-12-31')
        if self.missing:
            raise ValueError('Bundled fonts do not cover these characters: '+repr(''.join(sorted(self.missing))))
        while len(self.pages)>1 and not self.pages[-1]['operations']:
            self.pages.pop()
        return self.pages


def draw_asset(page, op, doc, chart, key):
    x,y,right,bottom = op['bbox']
    width = right-x
    aid = op['asset_id']
    if aid==0:
        body = width*310/560
        page.show_pdf_page(fitz.Rect(x,y,right,y+body),chart,0)
    else:
        body = 113
        row_h = 21
        font = get_font('latin')
        rows = [('Period','Output','Cost','Balance')]+list(zip(doc.facts['years'],doc.facts['revenue'],doc.facts['cost'],doc.facts['profit']))
        for row_index,row in enumerate(rows):
            for col_index,value in enumerate(row):
                label = str(value)
                size = min(8.5,(width/4-6)/max(font.text_length(label,fontsize=1),.1))
                cell_right=x+(col_index+1)*width/4-3
                draw_text(page,cell_right-font.text_length(label,fontsize=size),y+row_index*row_h+5,label,size)
        for at,thickness in [(0,1.0),(row_h,.6),(row_h*5,1.0)]:
            page.draw_line((x,y+at),(right,y+at),color=(.22,.32,.29),width=thickness)
    caption = ('图 1：模拟产出与成本趋势' if aid==0 else '表 1：统一口径的分期数据') if doc.language=='zh' else ('Figure 1: Simulated output and cost' if aid==0 else 'Table 1: Canonical period ledger')
    cap_top=y+body+8
    for line in wrap_text(caption,get_font(key),8.5,width):
        draw_text(page,x,cap_top,line,8.5,key)
        cap_top += 14
    op['caption_bbox']=[x,y+body+8,right,cap_top]


def render(doc,folder):
    pages = Paginator(doc).build()
    pdf = fitz.open()
    chart = fitz.open(folder/'chart.pdf')
    for page_number,planned in enumerate(pages,1):
        page = pdf.new_page(width=PAGE_W,height=PAGE_H)
        embed_fonts(page)
        for op in planned['operations']:
            if op['kind']=='text':
                draw_text(page,op['bbox'][0],op['bbox'][1],op['text'],op['size'],op['font'])
            else:
                draw_asset(page,op,doc,chart,'cjk' if doc.language=='zh' else 'latin')
        draw_text(page,PAGE_W/2-3,PAGE_H-33,str(page_number),9)
    chart.close()
    pdf.set_metadata({'title':doc.title,'author':'Synthetic Document Laboratory','subject':'Synthetic data; Python renderer v0.2'})
    pdf.subset_fonts()
    install_unicode_maps(pdf)
    pdf.save(folder/'document.pdf',garbage=4,deflate=True)
    pdf.close()
    records=[]
    for index,planned in enumerate(pages,1):
        records.append(dict(page=index,float_only=planned['float_only'],operations=planned['operations']))
    (folder/'layout.json').write_text(json.dumps({'renderer':'python-v0.2','pages':records},ensure_ascii=False,indent=2),encoding='utf-8')
    return folder/'document.pdf'
