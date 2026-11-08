import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from core.benchmark_config import load_config,validate_config
from core.benchmark_pipeline import plan_documents,run_batch
from core.benchmark_schema import validate_graph
from content.benchmark_content import build_document
from verify_dataset import verify


class BenchmarkTests(unittest.TestCase):
    def test_all_depths_title_layers_and_numbering(self):
        for depth in range(2,7):
            for has_title in (True,False):
                for mode in ['numbered','none','mixed','misleading']:
                    for family in ['arabic_dotted','alpha_dotted','cn_outline','roman_outline']:
                        doc=build_document('0001','paper','zh',42,depth,has_title,mode,family,'similar','classic',2,62,10.5)
                        validate_graph(doc)
    def test_integer_ownership_plan(self):
        cfg=load_config('mixed','joint');cfg['count']=20
        docs,targets=plan_documents('mixed',cfg,42)
        self.assertEqual(sum(len(d.objects) for d in docs),120)
        self.assertEqual(targets['conflicts'],60)
        for doc in docs:validate_graph(doc)
        subtypes={o.target_subtype for d in docs for o in d.objects}
        self.assertEqual(subtypes,{'normal','after_section','far_float','before_heading','plate'})
    def test_full_delivery_and_no_external_commands(self):
        cfg=load_config('paper','joint');cfg['content_provider']='template';cfg['dpi']=72
        with tempfile.TemporaryDirectory(prefix='PDF 标注 with spaces ') as tmp:
            with patch('subprocess.Popen',side_effect=AssertionError('External command')),patch('socket.create_connection',side_effect=AssertionError('Network')):
                path,c,s=run_batch('paper','joint',cfg,Path(tmp),'L3')
            self.assertEqual(c['conflict_ratio'],.5)
            self.assertTrue(verify(path/'docanno')['passed'])
            self.assertEqual(s['baselines']['nearest_heading'],.5)
            docs=[json.loads(l) for l in (path/'docanno/docs.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all((path/'docanno'/p['image']).is_file() for d in docs for p in d['pages']))
            # Tampering a semantic edge must be detected by independent export validation.
            target=next(b for b in docs[0]['blocks'] if b['type']=='table')
            target['belongs_to']='not-a-heading'
            (path/'docanno/docs.jsonl').write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in docs),encoding='utf-8')
            with self.assertRaises(ValueError):verify(path/'docanno')
    def test_level_only_and_l2_hides_coordinates(self):
        cfg=load_config('official','level');cfg['content_provider']='template';cfg['count']=2;cfg['depths']={2:1,6:1};cfg['dpi']=72
        with tempfile.TemporaryDirectory() as tmp:
            path,c,s=run_batch('official','level',cfg,Path(tmp),'L2')
            self.assertEqual(c['objects'],0)
            self.assertEqual(c['by_max_depth'],{2:1,6:1})
            self.assertTrue(verify(path/'docanno')['passed'])
            for line in (path/'docanno/docs.jsonl').read_text(encoding='utf-8').splitlines():
                for b in json.loads(line)['blocks']:
                    self.assertNotIn('box',b);self.assertNotIn('page',b);self.assertIn('image',b)
    def test_extreme_conflict_rates_and_six_table_plate(self):
        for subtype in ['normal','after_section','far_float','before_heading','plate']:
            cfg=load_config('paper','joint');cfg['content_provider']='template';cfg['count']=1;cfg['depths']={4:1};cfg['has_title']={'yes':1};cfg['columns']={2:1}
            cfg['conflict_ratio']=0 if subtype=='normal' else 1
            cfg['subtype_weights']={subtype:1} if subtype!='normal' else {'after_section':1}
            cfg['plate_max_objects']=6
            if subtype!='normal':cfg['relation_weights'][subtype]={'prev_is_ancestor':1} if subtype=='before_heading' else {'owner_is_ancestor':1}
            with tempfile.TemporaryDirectory() as tmp:
                path,c,s=run_batch('paper','joint',cfg,Path(tmp),'L1')
                self.assertEqual(c['by_subtype'],{subtype:6})
                self.assertEqual(c['conflict_ratio'],cfg['conflict_ratio'])
                self.assertTrue(verify(path/'docanno')['passed'])
    def test_depth_numbering_grid(self):
        from core.benchmark_config import ROOT
        cfg=load_config('official','level',ROOT/'configs/level_grid.yaml')
        docs,targets=plan_documents('official',cfg,42)
        for depth in range(2,7):
            self.assertEqual({d.numbering_mode for d in docs if d.target_depth==depth},{'numbered','none','mixed','misleading'})
    def test_impossible_quota_does_not_replace_previous_data(self):
        cfg=load_config('paper','joint');cfg['content_provider']='template';cfg['count']=1;cfg['depths']={2:1};cfg['has_title']={'yes':1}
        cfg['conflict_ratio']=1;cfg['subtype_weights']={'before_heading':1};cfg['relation_weights']['before_heading']={'cross_branch':1};cfg['max_attempts']=1
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):run_batch('paper','joint',cfg,Path(tmp),'L1')
            self.assertFalse((Path(tmp)/'paper/joint').exists())
            self.assertTrue((Path(tmp)/'paper/joint_failure_report.json').is_file())

if __name__=='__main__':unittest.main()
