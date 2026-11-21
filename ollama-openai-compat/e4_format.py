from lib import *
import json as J
M='qwen2.5-coder:7b'
msg=[{'role':'user','content':'介绍一下 Go 语言：它叫什么名字，哪一年首次公开发布？'}]
schema={'type':'object','properties':{'name':{'type':'string'},'year':{'type':'integer'}},'required':['name','year']}
cases=[
 ('v1 json_schema 标准写法', '/v1/chat/completions', {'response_format':{'type':'json_schema','json_schema':{'name':'lang','schema':schema,'strict':True}}}),
 ('v1 json_schema 缺 schema 对象', '/v1/chat/completions', {'response_format':{'type':'json_schema','json_schema':{'name':'lang'}}}),
 ('v1 schema 放错层级', '/v1/chat/completions', {'response_format':{'type':'json_schema','schema':schema}}),
 ('v1 json_object', '/v1/chat/completions', {'response_format':{'type':'json_object'}}),
 ('v1 type 拼错 json-schema', '/v1/chat/completions', {'response_format':{'type':'json-schema','json_schema':{'name':'lang','schema':schema}}}),
 ('native format=schema', '/api/chat', {'format':schema}),
 ('native format="json"', '/api/chat', {'format':'json'}),
]
res={}
for tag,path,extra in cases:
    body={'model':M,'messages':msg,'temperature':0,'max_tokens':120,**extra} if path.startswith('/v1') else {'model':M,'messages':msg,'stream':False,'options':{'temperature':0,'num_predict':120},**extra}
    c,r,dt=post(path,body)
    if c!=200:
        print('==',tag,'http',c,r); res[tag]=r; continue
    text=r['choices'][0]['message']['content'] if path.startswith('/v1') else r['message']['content']
    try: ok=J.loads(text); verdict='合法 JSON'+(' 且含 name/year' if isinstance(ok,dict) and {'name','year'}<=ok.keys() else ' 但缺字段')
    except Exception: verdict='不是 JSON'
    print('==',tag,'http',c,verdict); print('   ',repr(text[:200]))
    res[tag]={'http':c,'text':text,'verdict':verdict}
save('e4_format.json',res)
