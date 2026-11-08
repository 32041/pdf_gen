"""Semantic truth, fixed before pagination. No geometric inference of ownership."""
from dataclasses import dataclass, asdict, field


@dataclass
class Heading:
    id: str
    title: str
    level: int
    parent_id: str
    path: tuple
    text: str = ''
    is_document_title: bool = False


@dataclass
class TableObject:
    id: str
    owner_id: str
    target_previous_id: str
    target_subtype: str
    target_relation: str
    topic: str
    caption: str
    rows: list
    reference_text: str
    plate_group: str | None = None
    row_height: float = 19
    display_number: int | None = None
    caption_text: str | None = None
    reference_template: str | None = None
    owner_locked: bool = False
    object_type: str = 'table'
    image_path: str | None = None
    figure_prompt: str | None = None
    figure_status: str | None = None
    figure_height: float | None = None
    figure_provenance: dict = field(default_factory=dict)
    content_provenance: dict = field(default_factory=dict)


@dataclass
class BenchmarkDocument:
    doc_id: str
    kind: str
    domain: str
    language: str
    title: str
    seed: int
    target_depth: int
    has_title: bool
    numbering_mode: str
    numbering_family: str
    style: str
    template: str
    columns: int
    margin_pt: float
    font_size: float
    headings: list[Heading]
    facts: dict
    page_width: float = 595.276
    page_height: float = 841.89
    paper: str = 'A4'
    style_ladder: dict = field(default_factory=dict)
    repair_count: int = 0
    repair_seed: int | None = None
    objects: list[TableObject] = field(default_factory=list)
    content: dict = field(default_factory=dict)
    variant_index: int = 1
    augmentation_ids: list[str] = field(default_factory=list)
    explicit_hierarchy: bool = False
    title_alignment: str = 'center'

    def to_dict(self):
        return asdict(self)


def ancestors(heading_id, headings):
    by_id = {h.id:h for h in headings}
    seen = set()
    while heading_id != 'root':
        if heading_id in seen or heading_id not in by_id:
            raise ValueError('Heading graph contains a cycle or broken parent')
        seen.add(heading_id)
        heading_id = by_id[heading_id].parent_id
        if heading_id != 'root':
            yield heading_id


def relation(owner_id, previous_id, headings):
    if owner_id == previous_id: return 'same'
    by_id = {h.id:h for h in headings}
    if owner_id in set(ancestors(previous_id,headings)): return 'owner_is_ancestor'
    if previous_id in set(ancestors(owner_id,headings)): return 'prev_is_ancestor'
    if by_id[owner_id].parent_id == by_id[previous_id].parent_id: return 'siblings'
    return 'cross_branch'


def validate_graph(doc):
    hs = doc.headings
    if len({h.id for h in hs}) != len(hs): raise ValueError('Duplicate heading ID')
    if len({h.text for h in hs}) != len(hs): raise ValueError('Duplicate heading text')
    by_id = {h.id:h for h in hs}
    children = {}
    for h in hs:
        list(ancestors(h.id,hs))
        if h.parent_id != 'root' and h.level != by_id[h.parent_id].level+1:
            raise ValueError('Non-consecutive heading level')
        if h.parent_id == 'root' and h.level != 1: raise ValueError('Top heading must be L1')
        children.setdefault(h.parent_id,[]).append(h.id)
    for parent,nodes in children.items():
        if parent != 'root' and len(nodes)==1: raise ValueError('Singleton child heading')
    if max(h.level for h in hs) != doc.target_depth: raise ValueError('Target depth not reached')
    if doc.has_title and (sum(h.is_document_title for h in hs)!=1 or len(children['root'])!=1):
        raise ValueError('Document-title layer must have exactly one semantic title')
    for obj in doc.objects:
        if obj.owner_id not in by_id or obj.target_previous_id not in by_id: raise ValueError('Unknown object heading')
        if relation(obj.owner_id,obj.target_previous_id,hs) != obj.target_relation:
            raise ValueError('Requested tree relation is inconsistent')
