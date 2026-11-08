"""Integration coverage for standalone resources, saved PDF extraction and float placement."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from assets.charts import create_chart
from content.providers import build
from core.audit import audit
from core.fonts import verify_resources
from render.python_pdf import render


class PortableRendering(unittest.TestCase):
    def test_render_types_languages_and_float_modes_without_external_commands(self):
        verify_resources()
        modes=['adjacent','top','bottom','next_page','float_page']
        with tempfile.TemporaryDirectory(prefix='pdf 项目 with spaces ') as tmp:
            # Fails if rendering invokes any OS executable or opens a network connection.
            with patch('subprocess.Popen',side_effect=AssertionError('External command used')), patch('socket.create_connection',side_effect=AssertionError('Network used')):
                for index,(kind,language) in enumerate((k,l) for k in ['paper','annual_report','official'] for l in ['zh','en']):
                    folder=Path(tmp)/str(index)
                    folder.mkdir()
                    doc=build(kind,language,42,[modes[index%5],modes[(index+1)%5]],3,1+index%3)
                    create_chart(doc.facts,folder/'chart.pdf')
                    render(doc,folder)
                    result=audit(folder,doc)
                    self.assertFalse(result['unembedded_fonts'])
                    for asset in result['assets']:
                        self.assertIsNotNone(asset['reference_bbox'])
                        self.assertIsNotNone(asset['caption_bbox'])
                        self.assertLess((folder/'document.pdf').stat().st_size,2_000_000)
                        if asset['target']=='float_page':
                            self.assertGreater(asset['page_delta'],0)
                            self.assertEqual(asset['actual_location'],'float_page')
                        if asset['target']=='next_page':
                            self.assertGreater(asset['page_delta'],0)
                        # Independently extracted reference must not intersect the float's box.
                        if asset['page_delta']==0:
                            import pymupdf as fitz
                            intersection=fitz.Rect(asset['reference_bbox']) & fitz.Rect(asset['asset_bbox'])
                            self.assertTrue(intersection.is_empty)

if __name__=='__main__': unittest.main()
