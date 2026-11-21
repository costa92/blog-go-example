from lib import *
M = 'qwen2.5-coder:7b'
msg = [{'role': 'user', 'content': '用一句话描述秋天的傍晚。'}]
def v1(extra):
    c, r, _ = post('/v1/chat/completions', {'model': M, 'messages': msg, 'max_tokens': 60, **extra})
    return r['choices'][0]['message']['content']
def nat(opts):
    c, r, _ = post('/api/chat', {'model': M, 'messages': msg, 'stream': False, 'options': {'num_predict': 60, **opts}})
    return r['message']['content']
cases = [
 ('A /v1 seed=7 (未设 temperature/top_p)', lambda: v1({'seed': 7})),
 ('B /api/chat seed=7 (未设 temperature/top_p)', lambda: nat({'seed': 7})),
 ('C /api/chat seed=7 temperature=1.0 top_p=1.0', lambda: nat({'seed': 7, 'temperature': 1.0, 'top_p': 1.0})),
 ('D /v1 seed=7 temperature=0.8 top_p=0.9', lambda: v1({'seed': 7, 'temperature': 0.8, 'top_p': 0.9})),
]
res = {}
for name, fn in cases:
    outs = [fn() for _ in range(2)]
    res[name] = outs
    print(name); [print('   ', repr(o)) for o in outs]
save('e1_seed.json', res)
# diversity: 10 runs no seed
div = {}
for name, fn in [('/v1 默认', lambda: v1({})), ('/api/chat 默认', lambda: nat({}))]:
    outs = [fn() for _ in range(10)]
    div[name] = outs
    print(name, 'distinct', len(set(outs)), 'of 10; avg len', sum(len(o) for o in outs)/10)
save('e1_div.json', div)
