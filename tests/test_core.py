import random, unittest
from core.planner import allocate, validate_sections, validate_document
from core.schema import Section
from content.providers import build

class Invariants(unittest.TestCase):
    def test_quotas(self):
        result=allocate({'a':.3,'b':.7},10,random.Random(1))
        self.assertEqual(result.count('a'),3)
    def test_single_child_rejected(self):
        with self.assertRaises(ValueError): validate_sections([Section('A',children=[Section('A.1')])])
    def test_data_and_structure(self):
        for kind in ['paper','annual_report','official']:
            for lang in ['en','zh']:
                for depth in [1,2,3]:
                    validate_document(build(kind,lang,42,['adjacent','top'],2,depth))
if __name__=='__main__': unittest.main()
