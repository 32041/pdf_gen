from core.pdf_unicode import install_unicode_maps
"""Shared renderer for hierarchy/ownership; all fonts are bundled, all coordinates in pt."""
from collections import defaultdict
import json
import pymupdf as fitz
from core.fonts import get_font, draw_text, wrap_text
from content.benchmark_content import paragraph
from render.table_cells import draw_cell
from render.python_pdf import Column, PAGE_W, PAGE_H


class BenchmarkPaginator:
    def __init__(self,doc):
        self.doc=doc;self.pages=[];self.page=None;self.col_index=0;self.serial=0;self.continuation_cursor=0
        self.key='cjk' if doc.language=='zh' else 'latin'
        self.width=doc.page_width;self.height=doc.page_height
        self.heading_pages={};self.new_page()

    @property
    def column(self): return self.page['columns'][self.col_index]

    def op(self,kind,box,**metadata):
        op=dict(kind=kind,box=list(box),**metadata)
        self.page['operations'].append(op)
        return op

    def new_page(self,plate=False):
        page=dict(operations=[],columns=[],plate=plate)
        self.pages.append(page);self.page=page;self.col_index=0
        margin=self.doc.margin_pt;gap=20
        width=(self.width-2*margin-gap*(self.doc.columns-1))/self.doc.columns
        for c in range(self.doc.columns):
            page['columns'].append(Column(margin+c*(width+gap),width,margin,self.height-margin-14,margin))
        n=len(self.pages)
        self.fixed_text('SYNTHETIC DOCUMENT | RESEARCH PROTOTYPE',margin,23,8,'latin',f'furniture_header_{n}','page_furniture','root','spanning_top')
        self.fixed_text(str(n),self.width/2, self.height-32,8,'latin',f'furniture_footer_{n}','page_furniture','root','footer')

    def next_column(self):
        if self.col_index+1<self.doc.columns:self.col_index+=1
        else:self.new_page()

    def fixed_text(self,text,x,y,size,key,block_id,type_,parent,lane,level=None,width=None,align='left'):
        font=get_font(key);height=max(1.55,font.ascender-font.descender)*size
        area=width or self.width-2*self.doc.margin_pt
        for i,line in enumerate(wrap_text(text,font,size,area)):
            left=x+(area-font.text_length(line,fontsize=size))/2 if align=='center' else x
            self.op('text',[left,y+i*height,left+font.text_length(line,fontsize=size),y+(i+1)*height],
                    block_id=block_id,type=type_,text=line,font=key,size=size,parent_id=parent,level=level,lane=lane,color_hex=self.doc.style_ladder.get('colors',['18384a']*6)[level-1] if level else None)
        return height*(i+1)

    def heading_style(self,level):
        if self.doc.style_ladder:return self.doc.style_ladder['sizes'][level-1],self.doc.style_ladder['indents'][level-1]
        if self.doc.style=='clear':sizes=[18,14,12,11,10.5,10];indents=[0,0,4,10,16,22]
        else:sizes=[18,12,11,11,10.5,10.5];indents=[0,0,0,10,0,10]
        return sizes[level-1],indents[level-1]

    def text(self,text,block_id,type_='text',parent='root',level=None,keep_heading=False,**metadata):
        size,indent=self.heading_style(level) if level else (self.doc.font_size,0)
        key=self.key if self.doc.language=='zh' or not level else 'bold'
        if any(not c.isspace() and not get_font(key).has_glyph(ord(c)) for c in text): key='cjk'
        font=get_font(key);height=max(1.55,font.ascender-font.descender)*size
        missing=[c for c in set(text) if not c.isspace() and not font.has_glyph(ord(c))]
        if missing:raise ValueError(f'Bundled font lacks {missing!r}')
        lines=wrap_text(text,font,size,self.column.width-indent)
        minimum=height*(len(lines)+2) if keep_heading else height
        if self.column.cursor+minimum>self.column.bottom:self.next_column()
        for line in lines:
            if self.column.cursor+height>self.column.bottom:self.next_column()
            col=self.column;x=col.x+indent;y=col.cursor
            self.op('text',[x,y,x+font.text_length(line,fontsize=size),y+height],block_id=block_id,type=type_,text=line,
                    parent_id=parent,level=level,size=size,font=key,lane=f'column{self.col_index}',color_hex=self.doc.style_ladder.get('colors',['18384a']*6)[level-1] if level else None,**metadata)
            col.cursor+=height
        self.column.cursor+=6 if not level else 4

    def body(self,heading,continuation=False):
        self.serial+=1
        self.text(paragraph(self.doc,heading,continuation,self.continuation_cursor),f't{self.serial:05d}',parent=heading.id)
        if continuation and self.doc.content:self.continuation_cursor+=1

    def fill_to_page(self,minimum,heading):
        attempts=0
        while len(self.pages)<minimum:
            self.body(heading,True);attempts+=1
            if attempts>200:raise RuntimeError('Capacity-fill loop did not advance')

    def table_height(self,obj,width):
        cap_height=len(wrap_text(obj.caption,get_font(self.key),8.5,width))*14
        return (obj.figure_height or len(obj.rows)*obj.row_height+4)+7+cap_height+12 if obj.object_type=='figure' else len(obj.rows)*obj.row_height+4+7+cap_height+12

    def table(self,obj,full_width=False):
        col=self.column;width=self.width-2*self.doc.margin_pt if full_width else col.width
        height=self.table_height(obj,width)
        if not full_width and col.cursor+height>col.bottom:
            self.next_column();col=self.column
        if not full_width and obj.target_subtype!='before_heading':
            heading_count=sum(o['type']=='title' for o in self.page['operations'])
            table_count=sum(o['kind'] in ('table','figure') for o in self.page['operations'])
            if not heading_count and table_count:
                # Do not accidentally turn a non-plate scenario into a plate.
                h=next(h for h in self.doc.headings if h.id==obj.target_previous_id)
                self.fill_to_page(len(self.pages)+1,h);col=self.column
                if col.cursor+height>col.bottom:self.next_column();col=self.column
        x=self.doc.margin_pt if full_width else col.x;y=col.cursor
        lane='spanning_body' if full_width else f'column{self.col_index}'
        body_height=(obj.figure_height or len(obj.rows)*obj.row_height+4) if obj.object_type=='figure' else len(obj.rows)*obj.row_height+4
        self.op(obj.object_type,[x,y,x+width,y+body_height],block_id=obj.id,type=obj.object_type,text='',level=None,
                parent_id=obj.owner_id,belongs_to=obj.owner_id,caption_ids=[obj.id+'_caption'],lane=lane,
                rows=obj.rows,row_height=obj.row_height,image_path=obj.image_path,figure_status=obj.figure_status,float_box=[x,y,x+width,y+height],target_subtype=obj.target_subtype)
        self.fixed_text(obj.caption,x,y+body_height+7,8.5,self.key,obj.id+'_caption','caption',obj.id,lane,width=width)
        col.cursor+=height

    def heading(self,h):
        if h.is_document_title or h.id==self.doc.headings[0].id:
            y=self.column.cursor
            height=self.fixed_text(h.text,self.doc.margin_pt,y,self.heading_style(1)[0],self.key,h.id,'title',h.parent_id,'spanning_top',h.level,align=self.doc.title_alignment)
            for c in self.page['columns']:c.cursor=y+height+12;c.top=c.cursor
        else:self.text(h.text,h.id,'title',h.parent_id,h.level,True)
        pages=[i+1 for i,p in enumerate(self.pages) if any(o['block_id']==h.id for o in p['operations'])]
        self.heading_pages[h.id]=pages[0]

    def build(self):
        refs=defaultdict(list);before=defaultdict(list);after=defaultdict(list);plate=defaultdict(list)
        for obj in self.doc.objects:
            refs[obj.owner_id].append(obj)
            if obj.plate_group:plate[obj.plate_group].append(obj)
            elif obj.target_subtype=='before_heading':before[obj.owner_id].append(obj)
            else:after[obj.target_previous_id].append(obj)
        for heading in self.doc.headings:
            group=before[heading.id]
            if group:
                size,indent=self.heading_style(heading.level)
                key=self.key if self.doc.language=='zh' else 'bold'
                if any(not c.isspace() and not get_font(key).has_glyph(ord(c)) for c in heading.text):key='cjk'
                lines=len(wrap_text(heading.text,get_font(key),size,self.column.width-indent))
                required=sum(self.table_height(o,self.column.width) for o in group)+(lines+2)*size*1.55+4
                if required>self.column.bottom-self.column.top:
                    raise ValueError('Too many before-heading tables at one heading; increase document depth or reduce objects.')
                if self.column.cursor+required>self.column.bottom:self.next_column()
                for obj in group:self.table(obj)
            immediate=[o for o in after[heading.id] if o.target_subtype=='after_section']
            reserve=sum(self.table_height(o,self.column.width) for o in immediate)
            size,indent=self.heading_style(heading.level)
            if not group and reserve and reserve+size*5<self.column.bottom-self.column.top and self.column.cursor+reserve+size*5>self.column.bottom:self.next_column()
            self.heading(heading)
            for obj in immediate:self.table(obj)
            self.body(heading)
            for obj in refs[heading.id]:
                self.text(obj.reference_text,'ref_'+obj.id,parent=heading.id,refers_to=obj.id)
            # Earlier scenarios are placed before capacity-fill can advance pages.
            for obj in sorted([o for o in after[heading.id] if o.target_subtype!='after_section'],key=lambda o:o.target_subtype=='far_float'):
                if obj.target_subtype=='far_float':self.fill_to_page(self.heading_pages[obj.owner_id]+2,heading)
                self.table(obj)
        for group in plate.values():
            self.new_page(plate=True)
            if sum(self.table_height(o,self.width-2*self.doc.margin_pt) for o in group)>self.column.bottom-self.column.top:
                raise ValueError('Plate group exceeds a page; reduce plate_max_objects')
            for obj in group:self.table(obj,True)
        return self.pages


def render_benchmark(doc,folder):
    from core.object_numbering import stabilize_numbering
    pages,numbering_passes=stabilize_numbering(doc,BenchmarkPaginator);pdf=fitz.open()
    for planned in pages:
        page=pdf.new_page(width=doc.page_width,height=doc.page_height)
        for op in planned['operations']:
            x,y,r,b=op['box']
            if op['kind']=='text':
                color=(.38,.42,.44) if op['type']=='page_furniture' else (.12,.22,.29) if op['type']=='title' else (.12,.16,.19)
                if op.get('color_hex'):color=tuple(int(op['color_hex'][i:i+2],16)/255 for i in (0,2,4))
                draw_text(page,x,y,op['text'],op['size'],op['font'],color)
            elif op['kind']=='figure':
                page.draw_rect(fitz.Rect(x,y,r,b),color=(.25,.3,.35),fill=(1,1,1),width=.8)
                if op.get('image_path'):page.insert_image(fitz.Rect(x+1,y+1,r-1,b-1),filename=op['image_path'],keep_proportion=True)
            else:
                rows=op['rows'];width=r-x;row_height=op['row_height']
                for i,row in enumerate(rows):
                    for j,label in enumerate(row):
                        draw_cell(page,str(label),x+j*width/4,y+i*row_height,width/4,row_height)
                for position,thickness in [(0,1),(row_height,.5),(len(rows)*row_height,1)]:
                    page.draw_line((x,y+position),(r,y+position),color=(.2,.3,.32),width=thickness)
    pdf.set_metadata({'title':doc.title,'subject':'Synthetic hierarchy and table ownership benchmark v0.5.0','author':'Synthetic Document Laboratory'})
    pdf.subset_fonts();install_unicode_maps(pdf);pdf.save(folder/'document.pdf',garbage=4,deflate=True);pdf.close()
    serializable=[dict(page=i+1,width=doc.page_width,height=doc.page_height,plate=p['plate'],operations=p['operations']) for i,p in enumerate(pages)]
    (folder/'layout.json').write_text(json.dumps({'renderer':'python-benchmark-v0.5.0','numbering_passes':numbering_passes,'pages':serializable},ensure_ascii=False,indent=2),encoding='utf-8')
    return serializable
