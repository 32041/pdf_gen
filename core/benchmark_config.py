from pathlib import Path
import copy, math
import yaml
from content.benchmark_content import DOMAINS

ROOT=Path(__file__).resolve().parents[1]


def merge(base,extra):
    result=copy.deepcopy(base)
    for k,v in extra.items():
        result[k]=merge(result[k],v) if isinstance(v,dict) and isinstance(result.get(k),dict) else copy.deepcopy(v)
    return result


def load_config(kind,task,custom=None):
    def read(p):return yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    config=read(ROOT/'configs/base.yaml')
    # Distribution dictionaries replace their base values; deep-merge only explicit override groups.
    def overlay(values):
        for key,value in values.items():
            if key in ('relation_weights','template_profiles','style_profiles','llm','figures','heading_numbering'):config[key]=merge(config[key],value)
            else:config[key]=value
    if kind not in ('mixed','all'):overlay(read(ROOT/'configs'/f'{kind}.yaml'))
    overlay(read(ROOT/'configs'/f'{task}.yaml'))
    if custom:overlay(read(custom))
    return config


def validate_config(c):
    legacy=set(c)&{'heading_depths','placements','paragraphs_per_subsection'}
    if legacy:raise ValueError('Old v0.2 config keys are unsupported: '+', '.join(sorted(legacy))+'. Use depths/subtype_weights/relation_weights; extract v0.3 into a new directory.')
    distributions=['languages','depths','has_title','numbering_modes','numbering_families','styles','templates','domains','subtype_weights','paper_sizes']
    if c.get('columns') is not None:distributions+=['columns']
    for key in distributions:
        weights=c[key]
        if not isinstance(weights,dict) or not weights or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())<=0:
            raise ValueError(f'Invalid distribution: {key}')
    if set(c['paper_sizes'])-{'A4','Letter'}:raise ValueError('paper_sizes supports A4/Letter')
    if set(c['depths'])-set(range(2,7)):raise ValueError('depths must be 2..6')
    if set(c['languages'])-{'zh','en'}:raise ValueError('languages must be zh/en')
    if set(c['has_title'])-{'yes','no'}:raise ValueError('has_title keys must be yes/no strings')
    if set(c['numbering_modes'])-{'numbered','none','mixed','misleading'}:raise ValueError('Unknown numbering mode')
    if set(c['numbering_families'])-{'arabic_dotted','cn_outline','alpha_dotted','roman_outline'}:raise ValueError('Unknown numbering family')
    if set(c['styles'])-set(c['style_profiles']):raise ValueError('Unknown style')
    if set(c['domains'])-set(DOMAINS):raise ValueError('Unknown domain')
    if c.get('columns') and set(c['columns'])-{1,2}:raise ValueError('columns supports 1 or 2')
    if set(c['subtype_weights'])-{'after_section','far_float','before_heading','plate'}:raise ValueError('Unknown conflict subtype')
    for subtype,weights in c['relation_weights'].items():
        if not weights or any(v<0 or not math.isfinite(v) for v in weights.values()) or sum(weights.values())<=0:raise ValueError('Invalid relation weights')
        if set(weights)-{'owner_is_ancestor','siblings','cross_branch','prev_is_ancestor'}:raise ValueError('Unknown tree relation')
    for key in ['seed','count','objects_per_document','plate_max_objects','max_attempts','dpi']:
        if not isinstance(c[key],int) or isinstance(c[key],bool):raise ValueError(f'{key} must be integer')
    if c['count']<1 or c['objects_per_document']<0 or c['max_attempts']<1:raise ValueError('Counts must be nonnegative; count/max_attempts positive')
    if c['objects_per_document']==1:raise ValueError('Use 0 or >=2 objects per document')
    if not 2<=c['plate_max_objects']<=6:raise ValueError('plate_max_objects must be 2..6')
    if not 36<=c['dpi']<=300:raise ValueError('dpi must be 36..300')
    if not isinstance(c['conflict_ratio'],(int,float)) or not 0<=c['conflict_ratio']<=1:raise ValueError('conflict_ratio must be in [0,1]')

    if set(c['templates'])-set(c['template_profiles']):raise ValueError('Unknown template')
    for profile in c['template_profiles'].values():
        if not 44<=profile['margin_pt']<=90 or not 8<=profile['font_size']<=13:raise ValueError('Template margins/fonts outside supported bounds')
    for group,bounds in c.get('level_share_constraints',{}).items():
        if any(int(v) not in range(1,7) for v in str(group).split(',')) or len(bounds)!=2 or not 0<=bounds[0]<=bounds[1]<=1:raise ValueError('Invalid level_share_constraints')
    if set(c['subtype_weights'])-set(c['relation_weights']):raise ValueError('Missing relation weights for a subtype')

    if not isinstance(c.get('document_retries',3),int) or not 0<=c.get('document_retries',3)<=10:raise ValueError('document_retries must be 0..10')

    import re
    for profile in c['style_profiles'].values():
        if len(profile['sizes'])!=6 or len(profile['indents'])!=6:raise ValueError('Each style ladder needs 6 sizes/indents')
        if any(not 8<=s<=24 for s in profile['sizes']) or any(not 0<=i<=36 for i in profile['indents']):raise ValueError('Style size/indent outside supported bounds')
        if len(set(zip(profile['sizes'],profile['indents'])))!=6:raise ValueError('Each depth needs a distinct size/indent combination')
        if profile.get('colors') and (len(profile['colors'])!=6 or any(not re.fullmatch('[0-9a-fA-F]{6}',v) for v in profile['colors'])):raise ValueError('Style colors must be six RGB hex strings')

    if c.get('content_provider','template') not in ('template','llm','library'):raise ValueError('content_provider must be template/llm/library')
    if c.get('content_provider','template')!='template':
        options=c['llm']
        if options.get('table_mode') not in ('llm','derived'):raise ValueError('llm.table_mode must be llm/derived')
        if not 1<=options.get('workers',2)<=4:raise ValueError('llm.workers must be 1..4')
        if not 16<=options.get('continuation_count',32)<=96:raise ValueError('llm.continuation_count must be 16..96')

    policy=c.get('heading_numbering',{})
    share=policy.get('explicit_document_ratio')
    if share is not None and (isinstance(share,bool) or not isinstance(share,(int,float)) or not 0<=share<=1):raise ValueError('heading_numbering.explicit_document_ratio must be null or 0..1')
    for name,allowed in [('explicit_families',{'arabic_dotted','alpha_dotted'}),('remaining_modes',{'none','mixed','misleading'})]:
        weights=policy.get(name,{})
        if weights and (set(weights)-allowed or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())<=0):raise ValueError('Invalid heading_numbering.'+name)
    if c.get('title_alignment','center') not in ('left','center'):raise ValueError('title_alignment must be left/center')
    figures=c.get('figures',{})
    if not isinstance(figures.get('ratio',0),(int,float)) or not 0<=figures.get('ratio',0)<=1:raise ValueError('figures.ratio must be 0..1')
    if figures.get('mode','placeholder') not in ('placeholder','api','library'):raise ValueError('figures.mode must be placeholder/api/library')
    if figures.get('on_error','fail') not in ('fail','placeholder'):raise ValueError('figures.on_error must be fail/placeholder')
    height=figures.get('height_pt')
    if height is not None and (not isinstance(height,(int,float)) or not 30<=height<=450):raise ValueError('figures.height_pt must be null or 30..450')
    if figures.get('protocol','openai_images')!='openai_images':raise ValueError('Unsupported figure API protocol; implement a provider adapter first')
