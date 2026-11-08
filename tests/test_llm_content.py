import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.benchmark_config import load_config
from core.benchmark_pipeline import plan_documents
from core.benchmark_plan import replan_bindings
from content.llm_provider import make_request,validate_bundle,apply_bundle,prepare_documents


def fake_response(doc,request):
    sections=[{'id':h.id,'title':h.title,'paragraph':f'This section develops the practical evidence and implementation responsibilities associated with {h.title.lower()}. The observations use a shared record and a consistent review procedure, so conclusions remain limited to the simulated setting.'} for h in doc.headings]
    notes=['Supporting observation '+chr(65+i//26)+chr(65+i%26)+' addresses a distinct practical review consideration within the same synthetic programme and maintains a consistent evidence boundary.' for i in range(request['continuation_count'])]
    rows=[['Period','Output','Cost','Balance']]+[[f'[[F:year_{i}]]',f'[[F:output_{i}]]',f'[[F:cost_{i}]]',f'[[F:balance_{i}]]'] for i in range(1,5)]
    return {'document_title':doc.title,'sections':sections,'continuations':notes,
            'tables':[{'id':o.id,'caption':'Evidence and review summary','reference':'Supporting records are presented in Table {number}.','rows':copy.deepcopy(rows)} for o in doc.objects]}


class LlmContentTests(unittest.TestCase):
    def fixture(self):
        cfg=load_config('paper','joint');cfg['languages']={'en':1}
        docs,targets=plan_documents('paper',cfg,42);doc=docs[0]
        request=make_request(doc,cfg['llm']);return cfg,doc,request,fake_response(doc,request)
    def test_numeric_fact_resolution_and_fixed_graph(self):
        cfg,doc,request,response=self.fixture();edges=[(h.id,h.parent_id,h.level) for h in doc.headings]
        owners=[o.owner_id for o in doc.objects]
        validated=validate_bundle(response,request);apply_bundle(doc,validated,{'provider':'test'})
        self.assertEqual(edges,[(h.id,h.parent_id,h.level) for h in doc.headings])
        self.assertTrue(all(o.owner_locked for o in doc.objects))
        self.assertNotIn('[[F:',json.dumps(doc.content))
        replan_bindings(doc,79,[])
        self.assertEqual(owners,[o.owner_id for o in doc.objects])
    def test_rejects_numbers_duplicate_sections_and_wrong_tables(self):
        cfg,doc,request,response=self.fixture()
        broken=copy.deepcopy(response);broken['sections'][0]['paragraph']+=' Unsupported figure 999.'
        with self.assertRaises(ValueError):validate_bundle(broken,request)
        broken=copy.deepcopy(response);broken['sections'].pop()
        with self.assertRaises(ValueError):validate_bundle(broken,request)
        broken=copy.deepcopy(response);broken['tables'][0]['rows'][0].pop()
        with self.assertRaises(ValueError):validate_bundle(broken,request)
    def test_offline_library_needs_no_api_key(self):
        cfg,doc,request,response=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            cfg['content_provider']='llm';cfg['llm']['library_dir']=tmp
            with patch('content.llm_provider.DeepSeekClient.complete_json',return_value=(response,{'model':'fake','usage':{}})) as api:
                prepare_documents([doc],cfg);self.assertEqual(api.call_count,1)
            cfg['content_provider']='library'
            fresh=plan_documents('paper',cfg,42)[0][0]
            with patch.dict('os.environ',{},clear=True),patch('content.llm_provider.DeepSeekClient.complete_json',side_effect=AssertionError('Offline replay made a network request')):
                prepare_documents([fresh],cfg)
            self.assertEqual(doc.content['sections'],fresh.content['sections'])
            self.assertTrue(fresh.content['provenance']['cache_hit'])
    def test_deep_balance_preserves_existing_owners(self):
        from collections import Counter
        from content.benchmark_content import DOMAINS
        cfg=load_config('all','joint');cfg['count']=40;cfg['domains']={k:1 for k in DOMAINS}
        before,targets=plan_documents('all',cfg,42)
        cfg['auto_balance_levels']=True;cfg['level_share_constraints']={'1,2':[0,.3],'4,5':[.4,.5]}
        after,targets=plan_documents('all',cfg,42)
        self.assertEqual([[o.owner_id for o in d.objects] for d in before],[[o.owner_id for o in d.objects] for d in after])
        counts=Counter(h.level for d in after for h in d.headings)
        self.assertGreaterEqual((counts[4]+counts[5])/sum(counts.values()),.4)
        self.assertLessEqual((counts[1]+counts[2])/sum(counts.values()),.3)
        self.assertEqual(sum(len(d.augmentation_ids) for d in after),12)
    def test_all_types_have_exactly_five_variants(self):
        from collections import Counter
        from content.benchmark_content import DOMAINS
        cfg=load_config('all','joint');cfg['count']=40;cfg['domains']={kind:1 for kind in DOMAINS}
        docs,targets=plan_documents('all',cfg,42)
        self.assertEqual(Counter(d.kind for d in docs),Counter({kind:5 for kind in DOMAINS}))
        for kind in DOMAINS:self.assertEqual({d.variant_index for d in docs if d.kind==kind},set(range(1,6)))

if __name__=='__main__':unittest.main()
