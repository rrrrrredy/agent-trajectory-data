"""Small, explicit transports for the workspace usefulness study.

Credentials enter through process environment only. Persist only visible output,
usage and transport metadata; never hidden reasoning or authorization headers.
"""
from __future__ import annotations
import json, os, subprocess, tempfile, time, urllib.request, urllib.error
from pathlib import Path

PROVIDERS = {
    'deepseek': {'model':'deepseek-flash', 'url':'https://api.deepseek.com/chat/completions', 'env':'DEEPSEEK_API_KEY', 'params':{'reasoning_effort':'high'}},
    'kimi': {'model':'kimi-k3', 'url':'https://api.moonshot.cn/v1/chat/completions', 'env':'KIMI_API_KEY', 'params':{'reasoning_effort':'high'}},
    'longcat': {'model':'LongCat-2.0', 'url':'https://api.longcat.chat/openai/v1/chat/completions', 'env':'LONGCAT_API_KEY', 'params':{'thinking':{'type':'enabled'}}},
    'glm': {'model':'glm-5.3', 'url':'https://open.bigmodel.cn/api/anthropic', 'env':'GLM_API_KEY', 'runtime':'claude_code_coding_plan', 'params':{'reasoning_effort':'high'}},
}
MAX_OUTPUT = 16384
CLAUDE = os.environ.get('STUDY_CLAUDE_EXE', 'C:/tools/nodejs/node_modules/@anthropic-ai/claude-code/bin/claude.exe')

def sanitized(value):
    text=json.dumps(value, ensure_ascii=False)
    for config in PROVIDERS.values():
        key=os.environ.get(config['env'])
        if key: text=text.replace(key, '[REDACTED]')
    return json.loads(text)

def http_call(config, system, user):
    key=os.environ[config['env']]
    body={'model':config['model'], 'messages':[{'role':'system','content':system},{'role':'user','content':user}], 'max_tokens':MAX_OUTPUT, **config['params']}
    request=urllib.request.Request(config['url'], json.dumps(body,ensure_ascii=False).encode('utf-8'), {'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    start=time.monotonic()
    meta={'requested_model':config['model'],'endpoint':config['url'],'runtime':'chat_completions','parameters':config['params'],'max_output_tokens':MAX_OUTPUT}
    try:
        with urllib.request.urlopen(request,timeout=240) as response:
            raw=json.load(response)
            meta['http_status']=response.status
        choices=raw.get('choices',[]);choice=choices[0] if choices else {};message=choice.get('message',{})
        visible=message.get('content') or ''
        meta.update(visible_text=visible, resolved_model=raw.get('model'), request_id=raw.get('id'), usage=raw.get('usage',{}), finish_reason=choice.get('finish_reason'), complete=bool(visible) and choice.get('finish_reason')=='stop')
        if 'error' in raw:meta['error']=raw['error']
    except urllib.error.HTTPError as exc:
        meta.update(http_status=exc.code,complete=False,error=exc.read(4096).decode('utf-8',errors='replace'))
    except Exception as exc:
        meta.update(complete=False,error_type=type(exc).__name__,error=str(exc))
    meta['elapsed_seconds']=round(time.monotonic()-start,3)
    return sanitized(meta)

def coding_plan_call(config,system,user):
    key=os.environ[config['env']]
    workspace=Path(tempfile.mkdtemp(prefix='runtime-glm-',dir='D:/Codex/_tmp'))
    cfg=workspace/'config';cfg.mkdir()
    allowed={'PATH','PATHEXT','SYSTEMROOT','SYSTEMDRIVE','WINDIR','COMSPEC','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','NODE_EXTRA_CA_CERTS','SSL_CERT_FILE','SSL_CERT_DIR','CLAUDE_CODE_GIT_BASH_PATH'}
    child={k:v for k,v in os.environ.items() if k.upper() in allowed}
    child.update(ANTHROPIC_AUTH_TOKEN=key,ANTHROPIC_BASE_URL=config['url'],ANTHROPIC_DEFAULT_OPUS_MODEL=config['model'],ANTHROPIC_DEFAULT_SONNET_MODEL=config['model'],ANTHROPIC_DEFAULT_HAIKU_MODEL=config['model'],CLAUDE_CONFIG_DIR=str(cfg),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS='1',CLAUDE_CODE_MAX_RETRIES='0',CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(MAX_OUTPUT),DISABLE_TELEMETRY='1',DISABLE_ERROR_REPORTING='1',TEMP='D:/Codex/_tmp',TMP='D:/Codex/_tmp')
    args=[CLAUDE,'--print','--model',config['model'],'--effort','high','--tools','','--disable-slash-commands','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','','--no-session-persistence','--max-turns','1','--output-format','stream-json','--verbose','--no-chrome','--system-prompt',system]
    start=time.monotonic();meta={'requested_model':config['model'],'endpoint':config['url'],'runtime':'claude_code_coding_plan','parameters':config['params'],'max_output_tokens':MAX_OUTPUT,'client_version':'2.1.114'}
    try:
        result=subprocess.run(args,input=user.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=workspace,env=child,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        events=[json.loads(line) for line in result.stdout.decode('utf-8').split('\n') if line.strip()]
        initial=next((x for x in events if x.get('type')=='system' and x.get('subtype')=='init'),{})
        terminal=next((x for x in reversed(events) if x.get('type')=='result'),{})
        messages=[x['message'] for x in events if x.get('type')=='assistant']
        visible=''.join(b.get('text','') for m in messages for b in m.get('content',[]) if b.get('type')=='text')
        isolated=all(initial.get(k)==[] for k in ('tools','mcp_servers','plugins','slash_commands'))
        models=sorted({m.get('model') for m in messages if m.get('model')})
        meta.update(exit_code=result.returncode,visible_text=visible,resolved_models=models,request_ids=[m.get('id') for m in messages],usage=terminal.get('usage',{}),finish_reason=terminal.get('stop_reason'),terminal_subtype=terminal.get('subtype'),isolated=isolated,complete=result.returncode==0 and isolated and terminal.get('is_error') is False and terminal.get('subtype')=='success' and bool(visible))
        if not meta['complete']:
            meta['error']={'terminal_errors':terminal.get('errors'),'terminal_result':terminal.get('result'),'stderr':result.stderr.decode('utf-8',errors='replace')[-3000:]}
    except Exception as exc:
        meta.update(complete=False,error_type=type(exc).__name__,error=str(exc))
    meta['elapsed_seconds']=round(time.monotonic()-start,3)
    return sanitized(meta)

def invoke(provider,system,user,config=None):
    config=config or PROVIDERS[provider]
    return coding_plan_call(config,system,user) if config.get('runtime')=='claude_code_coding_plan' else http_call(config,system,user)