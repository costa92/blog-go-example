import json, urllib.request, urllib.error, numpy as np
exec(open('longdoc.py').read().split("q = np.array")[0].replace("M = sys.argv[1]","M = 'bge-m3'"))
q = np.array(call(QUERY)[1]['embeddings'][0])
for n in [60, 120]:
    doc = filler(n) + ' ' + FACT
    for tag, kw in [('默认', {}), ('truncate:false', {'truncate': False}),
                    ('options num_ctx=8192', {'options': {'num_ctx': 8192}}),
                    ('options num_ctx=8192 num_batch=8192', {'options': {'num_ctx': 8192, 'num_batch': 8192}})]:
        c, r = call(doc, **kw)
        if c == 200:
            print(f'{n} 句 事实在末尾 {tag}: HTTP 200 prompt_eval_count={r["prompt_eval_count"]} cos={q @ np.array(r["embeddings"][0]):.3f}')
        else:
            print(f'{n} 句 事实在末尾 {tag}: HTTP {c} {r}')
