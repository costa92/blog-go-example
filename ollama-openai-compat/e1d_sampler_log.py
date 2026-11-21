from lib import *
import subprocess, re
M='qwen2.5-coder:7b'; msg=[{'role':'user','content':'用一句话描述秋天的傍晚。'}]
def cursor():
    out=subprocess.run(['journalctl','-u','ollama','-n','0','--show-cursor','--no-pager'],capture_output=True,text=True).stdout
    return re.search(r'cursor: (.+)', out).group(1).strip()
for tag, path, body in [
  ('/v1 不设 temperature/top_p', '/v1/chat/completions', {'model':M,'messages':msg,'max_tokens':20}),
  ('/api/chat 不设 options', '/api/chat', {'model':M,'messages':msg,'stream':False,'options':{'num_predict':20}}),
  ('/v1 只设 temperature=0.2', '/v1/chat/completions', {'model':M,'messages':msg,'max_tokens':20,'temperature':0.2}),
  ('/v1 temperature=0.8 top_p=0.9', '/v1/chat/completions', {'model':M,'messages':msg,'max_tokens':20,'temperature':0.8,'top_p':0.9}),
]:
    cur=cursor(); post(path, body)
    j=subprocess.run(['journalctl','-u','ollama','--after-cursor',cur,'--no-pager','-o','cat'],capture_output=True,text=True).stdout
    print('==', tag)
    for l in j.splitlines():
        if 'top_k =' in l: print(l.strip())
