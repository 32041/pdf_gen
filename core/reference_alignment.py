"""Coarse reference diagnostics, not a claim of complete DocHieNet alignment."""
import json,statistics
from pathlib import Path
from collections import defaultdict
from render.python_pdf import PAGE_W,PAGE_H


def compare_reference(block_sets,layouts):
    path=Path(__file__).resolve().parents[1]/'resources/reference_layout.json'
    reference=json.loads(path.read_text(encoding='utf-8'))
    levels=defaultdict(list)
    aspects=[]
    for blocks,layout in zip(block_sets,layouts):
        width,height=layout[0]["width"],layout[0]["height"]
        aspects.append(width/height)
        for b in blocks:
            if b['type']=='title':levels[str(b['level'])].append((b['box'][3]-b['box'][1])/height)
    generated={level:statistics.median(values) for level,values in levels.items()}
    return dict(reference=reference,generated=dict(page_aspect_ratio_median=statistics.median(aspects),page_aspect_ratio_per_doc=aspects,heading_box_height_fraction_median=generated),
                differences={level:generated[level]-reference['heading_box_height_fraction_median'][level] for level in generated if level in reference['heading_box_height_fraction_median']},
                status='partial_diagnostic_only',limits=['Only page aspect ratio and normalized heading block height are compared.',
                'Reference labels include noise; box height includes wrapping and is NOT font size.',
                'L6 has no reference examples. Style clarity is intentionally controlled independently.',
                'No body-density, column-detection, photo/scan or pixel-similarity alignment has been validated.'])
