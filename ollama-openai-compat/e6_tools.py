from lib import *
import json as J
tool={'type':'function','function':{'name':'get_weather','description':'查询城市当前天气','parameters':{'type':'object','properties':{'city':{'type':'string','description':'城市名'}},'required':['city']}}}
msg=[{'role':'user','content':'杭州现在天气怎么样？'}]
res={}
for M in ['qwen2.5-coder:7b','llama3.1:8b']:
    for tag, extra in [('tools', {}), ('tools + tool_choice="none"', {'tool_choice':'none'}), ('tools + tool_choice 指定函数', {'tool_choice':{'type':'function','function':{'name':'get_weather'}}})]:
        c,r,dt=post('/v1/chat/completions',{'model':M,'messages':msg,'tools':[tool],'temperature':0,**extra})
        ch=r['choices'][0]; m=ch['message']
        print(f'== {M} /v1 {tag}: http={c} finish_reason={ch["finish_reason"]}')
        print('   tool_calls=', J.dumps(m.get('tool_calls'), ensure_ascii=False)); print('   content=', repr(m.get('content'))[:120])
        res[f'{M} v1 {tag}']=r
    c,r,dt=post('/api/chat',{'model':M,'messages':msg,'tools':[tool],'stream':False,'options':{'temperature':0}})
    print(f'== {M} /api/chat tools: done_reason={r.get("done_reason")}')
    print('   tool_calls=', J.dumps(r['message'].get('tool_calls'), ensure_ascii=False)); print('   content=', repr(r['message'].get('content'))[:120])
    res[f'{M} native']=r
# round trip: send tool result back via /v1
M='qwen2.5-coder:7b'
c,r,dt=post('/v1/chat/completions',{'model':M,'messages':msg,'tools':[tool],'temperature':0})
tc=r['choices'][0]['message']['tool_calls'][0]
msgs=msg+[r['choices'][0]['message'],{'role':'tool','tool_call_id':tc['id'],'content':J.dumps({'city':'杭州','temp_c':14,'sky':'小雨'},ensure_ascii=False)}]
c,r2,dt=post('/v1/chat/completions',{'model':M,'messages':msgs,'tools':[tool],'temperature':0})
print('== round trip second turn:', c, repr(r2['choices'][0]['message']['content']), r2['choices'][0]['finish_reason'])
res['roundtrip']=[r,r2]
save('e6_tools.json',res)
