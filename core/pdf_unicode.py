"""Portable, explicit CID -> UTF-16BE maps for the characters actually drawn.

PyMuPDF's generated full-font CMaps can contain odd-length non-BMP targets
(e.g. <1f600> instead of UTF-16 <d83dde00>). Some readers reject such maps.
Rebuild after subsetting using used CIDs only, with <=100 bfchar entries/batch.
"""
import re
import unicodedata


def record_characters(pdf,font_xref,font,text):
    if not hasattr(pdf,'_synth_unicode_maps'):pdf._synth_unicode_maps={}
    mapping=pdf._synth_unicode_maps.setdefault(font_xref,{})
    for char in text:
        if char in '\r\n':continue
        gid=font.has_glyph(ord(char))
        if not gid:raise ValueError(f'Font cannot encode U+{ord(char):04X}')
        previous=mapping.get(gid)
        if previous is not None and previous!=char:
            # A single glyph can be shared by compatibility characters. Prefer
            # its canonical spelling; templates never need two distinct spellings.
            if unicodedata.normalize('NFKC',previous)!=unicodedata.normalize('NFKC',char):
                raise ValueError('Different characters share one CID; use a distinct font or explicit run separation.')
            canonical=unicodedata.normalize('NFKC',char)
            if len(canonical)==1 and font.has_glyph(ord(canonical))==gid:char=canonical
            else:char=previous
        mapping[gid]=char


def install_unicode_maps(pdf):
    maps=getattr(pdf,'_synth_unicode_maps',{})
    for font_xref,mapping in maps.items():
        lines=['/CIDInit /ProcSet findresource begin','12 dict begin','begincmap',
               '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
               f'/CMapName /SynthUnicode{font_xref} def','/CMapType 2 def',
               '1 begincodespacerange','<0000> <FFFF>','endcodespacerange']
        items=sorted(mapping.items())
        for start in range(0,len(items),100):
            chunk=items[start:start+100];lines.append(f'{len(chunk)} beginbfchar')
            for cid,text in chunk:
                if not 0<cid<=65535:raise ValueError('CID outside two-byte encoding')
                encoded=text.encode('utf-16-be').hex().upper()
                lines.append(f'<{cid:04X}> <{encoded}>')
            lines.append('endbfchar')
        lines+=['endcmap','CMapName currentdict /CMap defineresource pop','end','end']
        cmap_xref=pdf.get_new_xref();pdf.update_object(cmap_xref,'<<>>')
        pdf.update_stream(cmap_xref,('\n'.join(lines)+'\n').encode('ascii'))
        pdf.xref_set_key(font_xref,'ToUnicode',f'{cmap_xref} 0 R')


def audit_unicode_maps(pdf):
    """Strict grammar/UTF-16 checks; do not trust the renderer's own extraction alone."""
    checked=set()
    for page in pdf:
        for entry in page.get_fonts():
            xref=entry[0]
            if xref in checked:continue
            checked.add(xref)
            kind,value=pdf.xref_get_key(xref,'ToUnicode')
            if kind!='xref':raise ValueError(f'Font {xref}: missing ToUnicode')
            data=pdf.xref_stream(int(value.split()[0])).decode('ascii')
            if 'beginbfrange' in data or 'SynthUnicode' not in data:raise ValueError('Unexpected Unicode-map format')
            count=0
            for group in re.finditer(r'(\d+) beginbfchar\s*(.*?)\s*endbfchar',data,re.S):
                pairs=re.findall(r'<([0-9A-F]+)>\s*<([0-9A-F]+)>',group[2])
                if len(pairs)!=int(group[1]) or len(pairs)>100:raise ValueError('Bad bfchar entry count')
                for source,target in pairs:
                    if len(source)!=4 or len(target)%4:raise ValueError('Invalid CID or UTF-16 target length')
                    text=bytes.fromhex(target).decode('utf-16-be',errors='strict')
                    if not text or '\ufffd' in text:raise ValueError('Invalid Unicode mapping')
                    count+=1
            if not count:raise ValueError('Empty Unicode map')
    return len(checked)
