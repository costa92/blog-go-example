import subprocess, openai
from openai import OpenAI
c = OpenAI(base_url='http://127.0.0.1:11434/v1', api_key='ollama')
lines = ['本文档开头的暗号是：蓝鲸-4729。请记住它。']
for n in range(1, 451):
    lines.append(f'第{n}条记录：服务 svc-{n:03d} 监听端口 {(n*37)%9000+1000}，负责人编号 {n*13%997}。')
lines.append('问题：本文档开头的暗号是什么？只回答暗号本身。')
msg=[{'role':'user','content':'\n'.join(lines)}]
print('openai', openai.__version__)
r = c.chat.completions.create(model='qwen2.5-coder:7b', messages=msg, max_tokens=20, temperature=0,
        extra_body={'options': {'num_ctx': 16384}})
print('extra_body options.num_ctx=16384 -> prompt_tokens', r.usage.prompt_tokens, 'answer', repr(r.choices[0].message.content))
try:
    c.chat.completions.create(model='qwen2.5-coder:7b', messages=msg, max_tokens=5, num_ctx=16384)
except TypeError as e:
    print('直接传 num_ctx=16384 ->', type(e).__name__, str(e)[:120])
r = c.chat.completions.create(model='qwen2.5-coder:7b', messages=[{'role':'user','content':'hi'}], max_tokens=5,
        extra_body={'keep_alive': 0})
print('extra_body keep_alive=0 ->', repr(r.choices[0].message.content))
print(subprocess.run(['ollama','ps'],capture_output=True,text=True).stdout)
try:
    c.chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'hi'}])
except openai.NotFoundError as e:
    print('未知模型 ->', type(e).__name__, e.status_code, e.body)
