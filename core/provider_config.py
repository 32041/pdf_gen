"""Resolve local provider settings without copying secrets into dataset metadata."""
from pathlib import Path
import copy,os
import yaml
ROOT=Path(__file__).resolve().parents[1]
SECRET_KEYS={'api_key','token','authorization','password','secret','access_token'}


def provider_options(options,section):
    result=copy.deepcopy(options)
    file=result.get('credentials_file','configs/providers.local.yaml')
    if file:
        path=Path(file)
        if not path.is_absolute():path=ROOT/path
        if path.is_file():
            data=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            local=data.get(section,{})
            if not isinstance(local,dict):raise ValueError(f'{section} provider settings must be a mapping')
            for k,v in local.items():
                if v is not None and v!='':result[k]=v
    env=result.get('api_key_env','DEEPSEEK_API_KEY' if section=='llm' else 'IMAGE_API_KEY')
    if env and os.environ.get(env):result['api_key']=os.environ[env].strip()
    return result


def public_config(value):
    if isinstance(value,dict):return {k:('[REDACTED]' if str(k).lower() in SECRET_KEYS and v else public_config(v)) for k,v in value.items()}
    if isinstance(value,list):return [public_config(v) for v in value]
    return value
