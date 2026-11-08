"""Official DeepSeek API only. Credentials can come from local YAML or environment."""
import json,os,time,urllib.request,urllib.error

ENDPOINT='https://api.deepseek.com/chat/completions'


class ContentAPIError(RuntimeError):pass


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        from urllib.parse import urlsplit
        if urlsplit(newurl).scheme!='https' or urlsplit(newurl).netloc!='api.deepseek.com':
            raise ContentAPIError('Refusing to forward API credentials to a different origin')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class DeepSeekClient:
    def __init__(self,model='deepseek-flash',timeout=180,options=None):
        from core.provider_config import provider_options
        self.options=provider_options(options or {},'llm')
        self.model=self.options.get('model',model);self.timeout=self.options.get('timeout_seconds',timeout)

    def complete_json(self,messages,max_tokens=14000):
        key=self.options.get('api_key','').strip()
        if not key:raise ContentAPIError('LLM api_key is missing. Set llm.api_key in configs/providers.local.yaml, or use DEEPSEEK_API_KEY; --content library is offline.')
        payload={'model':self.model,'messages':messages,'response_format':{'type':'json_object'},
                 'max_tokens':max_tokens,'temperature':.65,'thinking':{'type':'disabled'}}
        opener=urllib.request.build_opener(SameOriginRedirect())
        for attempt in range(3):
            request=urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
                    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            try:
                with opener.open(request,timeout=self.timeout) as response:data=json.load(response)
                choice=data['choices'][0]
                if choice.get('finish_reason')=='length':raise ContentAPIError('Model output truncated; increase llm.max_tokens or reduce requested text length')
                text=choice['message'].get('content','')
                return json.loads(text),{'model':data.get('model',self.model),'usage':data.get('usage',{}),'finish_reason':choice.get('finish_reason')}
            except urllib.error.HTTPError as error:
                status=error.code
                if status in (429,500,502,503,504) and attempt<2:
                    time.sleep(min(2**attempt*2,8));continue
                raise ContentAPIError(f'DeepSeek HTTP {status}; check account balance/model access or network. Authorization header is not logged.') from None
            except (urllib.error.URLError,TimeoutError) as error:
                if attempt<2:time.sleep(2**attempt*2);continue
                raise ContentAPIError('DeepSeek connection failed or timed out; no credential details logged') from None
            except (KeyError,json.JSONDecodeError) as error:
                raise ContentAPIError('DeepSeek did not return the required JSON object') from None
