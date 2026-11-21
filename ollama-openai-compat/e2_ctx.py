from lib import *
import subprocess, datetime
M = 'qwen2.5-coder:7b'
lines = ['本文档开头的暗号是：蓝鲸-4729。请记住它。']
for n in range(1, 451):
    lines.append(f'第{n}条记录：服务 svc-{n:03d} 监听端口 {(n*37)%9000+1000}，负责人编号 {n*13%997}。')
lines.append('问题：本文档开头的暗号是什么？只回答暗号本身。')
prompt = '\n'.join(lines)
msg = [{'role': 'user', 'content': prompt}]
def show(tag, c, prompt_tokens, ans):
    print(f'{tag}: http={c} prompt_tokens={prompt_tokens} answer={ans!r}')
    print(subprocess.run(['ollama','ps'],capture_output=True,text=True).stdout)
since = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
c, r, dt = post('/v1/chat/completions', {'model': M, 'messages': msg, 'max_tokens': 20, 'temperature': 0})
save('e2_v1_plain.json', r); show('/v1 不带 options', c, r['usage']['prompt_tokens'], r['choices'][0]['message']['content'])
c, r, dt = post('/v1/chat/completions', {'model': M, 'messages': msg, 'max_tokens': 20, 'temperature': 0, 'options': {'num_ctx': 16384}})
save('e2_v1_options.json', r); show('/v1 带 options.num_ctx=16384', c, r['usage']['prompt_tokens'], r['choices'][0]['message']['content'])
c, r, dt = post('/v1/chat/completions', {'model': M, 'messages': msg, 'max_tokens': 20, 'temperature': 0, 'num_ctx': 16384})
save('e2_v1_toplevel.json', r); show('/v1 顶层 num_ctx=16384', c, r['usage']['prompt_tokens'], r['choices'][0]['message']['content'])
c, r, dt = post('/api/chat', {'model': M, 'messages': msg, 'stream': False, 'options': {'num_ctx': 16384, 'num_predict': 20, 'temperature': 0}})
save('e2_native_16k.json', r); show('/api/chat options.num_ctx=16384', c, r['prompt_eval_count'], r['message']['content'])
c, r, dt = post('/v1/chat/completions', {'model': M, 'messages': msg, 'max_tokens': 20, 'temperature': 0})
save('e2_v1_after.json', r); show('/v1 紧接在原生 16k 请求之后', c, r['usage']['prompt_tokens'], r['choices'][0]['message']['content'])
print('journal since', since)
print(subprocess.run(['journalctl','-u','ollama','--since',since,'--no-pager','-o','cat'],capture_output=True,text=True).stdout)
