"""Run this from any directory: only Python packages and bundled resources are needed."""
import sys
from pathlib import Path


def main():
    if sys.version_info < (3,10):
        raise SystemExit('Python 3.10 or newer is required.')
    try:
        import pymupdf
        import yaml
    except ImportError:
        raise SystemExit('Dependencies missing. Run: python -m pip install -r requirements.txt')
    from core.fonts import verify_resources, get_font
    verify_resources()
    for key,text in [('cjk','中文字体测试，图表。'),('latin','English font test 0123456789'),('bold','Heading 1.2')]:
        font=get_font(key)
        assert all(font.has_glyph(ord(c)) for c in text if not c.isspace()),key
    print('OK: Python',sys.version.split()[0],'| PyMuPDF',pymupdf.VersionBind)
    print('OK: Bundled fonts verified. No TeX or system fonts required.')
    print('Project:',Path(__file__).resolve().parent)

if __name__=='__main__': main()
