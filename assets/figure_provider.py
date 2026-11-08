"""Configurable image-generation adapter. Placeholder mode never calls any API."""
from pathlib import Path
import base64,hashlib,json,random,urllib.request,urllib.error
import pymupdf as fitz
from core.provider_config import ROOT,provider_options
from core.planner import allocate


class ImageAPIError(RuntimeError):pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ImageAPIError('Image API redirects are disabled; configure the final HTTPS endpoint')


def generate_image(prompt,options):
    from urllib.parse import urlsplit
    base=options.get('api_base','').rstrip('/')
    if urlsplit(base).scheme!='https' or not urlsplit(base).netloc or urlsplit(base).username or urlsplit(base).password or urlsplit(base).query:
        raise ImageAPIError('Set a valid HTTPS images.api_base without credentials/query in providers.local.yaml')
    if not options.get('model') or not options.get('api_key'):raise ImageAPIError('Set images.model and images.api_key for a model with image-generation capability')
    if options.get('protocol','openai_images')!='openai_images':raise ImageAPIError('Only openai_images is implemented; add an adapter for other vendor protocols')
    endpoint=base if base.endswith('/images/generations') else base+'/images/generations'
    payload={'model':options['model'],'prompt':prompt,'n':1,'size':options.get('size','1024x1024')}
    if options.get('response_format'):payload['response_format']=options['response_format']
    request=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+options['api_key']})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=options.get('timeout_seconds',180)) as response:
            raw=response.read(24*1024*1024+1)
        if len(raw)>24*1024*1024:raise ImageAPIError('Image response exceeded 24 MiB')
        data=json.loads(raw);item=data['data'][0]
        if item.get('b64_json'):content=base64.b64decode(item['b64_json'],validate=True)
        elif item.get('url'):
            image_url=item['url'];parts=urlsplit(image_url)
            if parts.scheme!='https' or parts.username or parts.password:raise ImageAPIError('Image download must use HTTPS')
            # Do not attach the API key to a returned image/CDN URL.
            with opener.open(urllib.request.Request(image_url),timeout=options.get('timeout_seconds',180)) as response:content=response.read(20*1024*1024+1)
        else:raise ImageAPIError('Image API returned neither b64_json nor url')
        if len(content)>20*1024*1024:raise ImageAPIError('Image exceeded 20 MiB')
        pix=fitz.Pixmap(content)
        if pix.width<1 or pix.height<1 or pix.width*pix.height>40_000_000:raise ImageAPIError('Image dimensions outside supported bounds')
        return pix.tobytes('png'),{'provider':'openai_images','model':options['model'],'status':'generated'}
    except urllib.error.HTTPError as exc:raise ImageAPIError(f'Image API HTTP {exc.code}; credential and response body omitted') from None
    except (urllib.error.URLError,TimeoutError):raise ImageAPIError('Image API connection failed or timed out') from None
    except (ValueError,KeyError,TypeError,IndexError):raise ImageAPIError('Invalid image API response; check protocol/model settings') from None


def prepare_figures(documents,cfg):
    settings=cfg.get('figures',{});ratio=settings.get('ratio',0)
    jobs=[(d,o) for d in documents for o in d.objects]
    flags=allocate({'figure':ratio,'table':1-ratio},len(jobs),random.Random(cfg['seed']+19781)) if jobs else []
    options=provider_options(settings,'images');mode=settings.get('mode','placeholder')
    cache=Path(settings.get('cache_dir','image_library'))
    if not cache.is_absolute():cache=ROOT/cache
    for (doc,obj),flag in zip(jobs,flags):
        if flag!='figure':continue
        obj.object_type='figure';obj.figure_height=settings.get('height_pt')
        h=next(h for h in doc.headings if h.id==obj.owner_id)
        section=doc.content.get('sections',{}).get(h.id,{})
        variables={'kind':doc.kind,'document_title':doc.title,'heading':h.title,'caption':obj.caption_text or obj.topic,
                   'paragraph':section.get('paragraph',''),'records':json.dumps(obj.rows,ensure_ascii=False)}
        try:prompt=settings.get('prompt_template','Illustrate {heading}: {caption}. {paragraph}').format(**variables)
        except (KeyError,ValueError):raise ValueError('Unknown or malformed figures.prompt_template placeholder') from None
        obj.figure_prompt=prompt
        obj.figure_provenance={'status':'placeholder','requested_mode':mode,'image_generated':False,'semantic_source':doc.content.get('provenance',{}).get('request_hash'),'adapter':options.get('protocol','openai_images')}
        obj.figure_status='placeholder'
        # The figure is derived from the same fixed semantic section; no edge changes.
        if obj.reference_template:
            obj.reference_template=obj.reference_template.replace('Table','Figure').replace('table','figure').replace('表','图')
        if mode=='placeholder':continue
        digest=hashlib.sha256(json.dumps({'prompt':prompt,'model':options.get('model'),'api_base':options.get('api_base'),'size':options.get('size')},sort_keys=True).encode()).hexdigest()
        path=cache/(digest+'.png');metadata=cache/(digest+'.json')
        try:
            cache_hit=path.exists()
            if not cache_hit:
                if mode=='library':raise ImageAPIError('Image cache miss; library mode does not call the API')
                content,meta=generate_image(prompt,options);cache.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
                metadata.write_text(json.dumps(meta|{'prompt':prompt,'request_hash':digest},ensure_ascii=False,indent=2),encoding='utf-8')
            fitz.Pixmap(str(path))
            obj.image_path=str(path);obj.figure_status='generated';obj.figure_provenance.update(status='generated',image_generated=True,model=options.get('model'),request_hash=digest,cache_hit=cache_hit)
        except (ImageAPIError,RuntimeError) as exc:
            if settings.get('on_error','fail')!='placeholder':raise
            obj.figure_provenance['fallback_reason']=str(exc)
