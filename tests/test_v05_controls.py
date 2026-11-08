import copy,json,tempfile,unittest,base64
from pathlib import Path
from unittest.mock import patch
import pymupdf as fitz
from core.benchmark_config import load_config,validate_config
from core.benchmark_pipeline import plan_documents,run_batch
from core.provider_config import provider_options,public_config
from content.benchmark_content import number
from assets.figure_provider import prepare_figures,generate_image,ImageAPIError
from verify_dataset import verify


class NewControlsTests(unittest.TestCase):
    def cfg(self):
        c=load_config('all','joint');c['content_provider']='template';c['count']=10;c['figures']['mode']='placeholder';return c
    def test_explicit_hierarchy_document_quota_and_edges(self):
        c=self.cfg();c['heading_numbering']['explicit_document_ratio']=.7
        docs,_=plan_documents('all',c,42)
        self.assertEqual(sum(d.explicit_hierarchy for d in docs),7)
        for doc in docs:
            if doc.explicit_hierarchy:
                self.assertIn(doc.numbering_family,('arabic_dotted','alpha_dotted'))
                for h in doc.headings:
                    self.assertEqual(h.text,h.title if h.is_document_title else number(h.path,doc.numbering_family)+' '+h.title)
        c['heading_numbering']['explicit_document_ratio']=1
        docs,_=plan_documents('all',c,42);self.assertTrue(all(d.explicit_hierarchy for d in docs))
        c['heading_numbering']['explicit_document_ratio']=0
        docs,_=plan_documents('all',c,42);self.assertFalse(any(d.explicit_hierarchy for d in docs))
    def test_placeholder_never_calls_api_and_preserves_ownership(self):
        c=self.cfg();docs,_=plan_documents('all',c,42);edges=[[(o.id,o.owner_id) for o in d.objects] for d in docs]
        with patch('assets.figure_provider.generate_image',side_effect=AssertionError('placeholder called API')):prepare_figures(docs,c)
        self.assertEqual(sum(o.object_type=='figure' for d in docs for o in d.objects),20)
        self.assertEqual(edges,[[(o.id,o.owner_id) for o in d.objects] for d in docs])
        self.assertTrue(all(o.image_path is None for d in docs for o in d.objects))
    def test_local_yaml_provider_and_export_redaction(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'providers.yaml';p.write_text('llm:\n  api_key: unit-test-secret\nimages:\n  api_key: separate-image-secret\n')
            with patch.dict('os.environ',{},clear=True):
                a=provider_options({'credentials_file':str(p)},'llm');b=provider_options({'credentials_file':str(p)},'images')
            self.assertEqual(a['api_key'],'unit-test-secret');self.assertEqual(b['api_key'],'separate-image-secret')
            public=public_config({'llm':a,'figures':b})
            self.assertNotIn('secret',json.dumps(public));self.assertEqual(public['llm']['api_key'],'[REDACTED]')
    def test_mixed_objects_numbering_and_centered_title(self):
        c=self.cfg();c['count']=2;c['depths']={4:1};c['conflict_ratio']=0;c['objects_per_document']=12;c['figures']['ratio']=.5
        c['has_title']={'yes':1};c['dpi']=36;c['llm']['api_key']='unit-test-secret'
        with tempfile.TemporaryDirectory() as tmp:
            root,comp,stats=run_batch('paper','joint',c,tmp,'L3')
            self.assertNotIn('unit-test-secret',(root/'docanno/config.json').read_text())
            self.assertEqual(comp['by_object_type'],{'table':12,'figure':12});self.assertTrue(verify(root/'docanno')['passed'])
            for p in (root/'documents').glob('*/document.json'):
                doc=json.loads(p.read_text());layout=json.loads(p.with_name('layout.json').read_text())
                title=[o for o in layout['pages'][0]['operations'] if o['block_id']==doc['headings'][0]['id']]
                self.assertTrue(all(abs((o['box'][0]+o['box'][2])/2-doc['page_width']/2)<.1 for o in title))
                self.assertTrue(any(o['kind']=='figure' for page in layout['pages'] for o in page['operations']))
    def test_openai_image_adapter_and_same_origin_credentials(self):
        pdf=fitz.open();page=pdf.new_page(width=16,height=16);png=page.get_pixmap().tobytes('png');pdf.close()
        payload={'data':[{'b64_json':base64.b64encode(png).decode()}]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps(payload).encode()
        with patch('urllib.request.OpenerDirector.open',return_value=Response()) as api:
            raw,meta=generate_image('draw a block',{'api_base':'https://images.example/v1','model':'test-image','api_key':'unit-test-image-secret'})
            self.assertTrue(raw.startswith(b'\x89PNG'));request=api.call_args.args[0]
            self.assertEqual(request.full_url,'https://images.example/v1/images/generations')
            self.assertEqual(request.get_header('Authorization'),'Bearer unit-test-image-secret')
        with self.assertRaises(ImageAPIError):generate_image('x',{'api_base':'http://example.com','model':'x','api_key':'secret'})
    def test_invalid_new_controls_rejected(self):
        for k,v in [('ratio',1.1),('mode','chat_completions'),('height_pt',0)]:
            c=self.cfg();c['figures'][k]=v
            with self.assertRaises(ValueError):validate_config(c)

if __name__=='__main__':unittest.main()
