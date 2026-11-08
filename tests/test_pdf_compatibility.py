import json,re,tempfile,unittest
from pathlib import Path
import pymupdf as fitz
from core.fonts import draw_text
from core.pdf_unicode import install_unicode_maps,audit_unicode_maps
from core.benchmark_config import load_config
from core.benchmark_pipeline import run_batch


class PdfCompatibilityTests(unittest.TestCase):
    def test_exact_unicode_and_surrogate_pair_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'copy.pdf';pdf=fitz.open();page=pdf.new_page()
            draw_text(page,30,30,'Copy test: A 123 😀 𝔸',12,'latin')
            chinese='中文复制测试：年，不，量。'
            draw_text(page,30,60,chinese,12,'cjk')
            pdf.subset_fonts();install_unicode_maps(pdf);pdf.save(p,garbage=4,deflate=True);pdf.close()
            pdf=fitz.open(p);audit_unicode_maps(pdf)
            self.assertIn(chinese,pdf[0].get_text())
            self.assertIn('😀 𝔸',pdf[0].get_text())
            maps=[]
            for font in pdf[0].get_fonts():
                _,value=pdf.xref_get_key(font[0],'ToUnicode');maps.append(pdf.xref_stream(int(value.split()[0])).decode('ascii'))
            self.assertIn('D83DDE00',''.join(maps));self.assertIn('D835DD38',''.join(maps))
            # A malformed Unicode map is rejected even if one reader tolerates it.
            _,value=pdf.xref_get_key(pdf[0].get_fonts()[0][0],'ToUnicode');xref=int(value.split()[0])
            data=pdf.xref_stream(xref).replace(b'<0041>',b'<1F600>')
            pdf.update_stream(xref,data)
            with self.assertRaises(ValueError):audit_unicode_maps(pdf)
            pdf.close()
    def test_double_digit_visual_numbers_and_reference_updates(self):
        cfg=load_config('paper','joint');cfg['content_provider']='template';cfg['count']=1;cfg['figures']['ratio']=0;cfg['objects_per_document']=12;cfg['conflict_ratio']=0
        cfg['depths']={4:1};cfg['has_title']={'yes':1};cfg['columns']={2:1}
        with tempfile.TemporaryDirectory() as tmp:
            path,c,s=run_batch('paper','joint',cfg,Path(tmp),'L1')
            record=json.loads((path/'docanno/docs.jsonl').read_text(encoding='utf-8'))
            by_id={b['id']:b for b in record['blocks']}
            tables=[b for b in record['blocks'] if b['type']=='table']
            labels=[int(re.match(r'(?:表|Table)\s*(\d+)',by_id[b['caption_ids'][0]]['text'])[1]) for b in tables]
            self.assertEqual(labels,list(range(1,13)))
            self.assertNotEqual([b['id'] for b in tables],[f'o{i:04d}' for i in range(1,13)])
            for number,b in enumerate(tables,1):
                reference=' '.join(x['text'] for x in record['blocks'] if x.get('refers_to')==b['id'])
                self.assertRegex(reference,r'(?:表|Table)\s*'+str(number)+r'(?!\d)')

if __name__=='__main__':unittest.main()
