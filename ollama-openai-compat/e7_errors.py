from lib import *
M='qwen2.5-coder:7b'
cases=[
 ('/v1 未知模型', '/v1/chat/completions', {'model':'gpt-4o-mini','messages':[{'role':'user','content':'hi'}]}),
 ('/api/chat 未知模型', '/api/chat', {'model':'gpt-4o-mini','messages':[{'role':'user','content':'hi'}],'stream':False}),
 ('/v1 messages 为空', '/v1/chat/completions', {'model':M,'messages':[]}),
 ('/api/chat messages 为空', '/api/chat', {'model':M,'messages':[],'stream':False}),
 ('/v1 temperature 传字符串', '/v1/chat/completions', {'model':M,'messages':[{'role':'user','content':'hi'}],'temperature':'0.2'}),
 ('/v1 未知 role', '/v1/chat/completions', {'model':M,'messages':[{'role':'robot','content':'hi'}],'max_tokens':5}),
]
for tag,path,body in cases:
    c,raw,dt=post(path,body,raw=True)
    print(f'== {tag}: HTTP {c}'); print('  ', raw[:300].strip())
# malformed JSON body
import urllib.request, urllib.error
for path in ['/v1/chat/completions','/api/chat']:
    req=urllib.request.Request(BASE+path,data=b'{"model": "x", ',headers={'Content-Type':'application/json'})
    try: r=urllib.request.urlopen(req); print(path,r.status,r.read()[:200])
    except urllib.error.HTTPError as e: print(f'== {path} 非法 JSON: HTTP {e.code}'); print('  ', e.read().decode()[:300])
