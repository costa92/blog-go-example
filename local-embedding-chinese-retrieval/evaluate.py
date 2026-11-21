"""用法: python3 evaluate.py MODEL [qprefix dprefix]
对 zh→zh、en→en、zh→en、en→zh 四种组合计算 recall@1、recall@5、MRR，结果写 results-<tag>.json。"""
import json, sys, time, urllib.request
import numpy as np
from corpus import DOCS, QUERIES
M = sys.argv[1]
QP = sys.argv[2] if len(sys.argv) > 2 else ''
DP = sys.argv[3] if len(sys.argv) > 3 else ''
tag = f"{M.replace(':','_').replace('/','_')}{'-prefix' if QP else ''}"

def embed(texts):
    body = json.dumps({'model': M, 'input': texts}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/embed', body, {'Content-Type': 'application/json'}), timeout=600).read())
    return np.array(r['embeddings']), r.get('prompt_eval_count')

ids = [d[0] for d in DOCS]
D = {}
for li, lang in [(1, 'zh'), (2, 'en')]:
    D[lang], ntok = embed([DP + d[li] for d in DOCS])
    print(f'docs {lang}: {len(DOCS)} 段, prompt_eval_count 合计 {ntok}')
Q = {}
for li, lang in [(1, 'zh'), (2, 'en')]:
    Q[lang], ntok = embed([QP + q[li] for q in QUERIES])
    print(f'queries {lang}: {len(QUERIES)} 条, prompt_eval_count 合计 {ntok}')
gold = [ids.index(q[0]) for q in QUERIES]
out = {'model': M, 'qprefix': QP, 'dprefix': DP, 'runs': {}}
print(f'{"组合":8} {"R@1":>6} {"R@5":>6} {"MRR":>6}  正确文档平均余弦  最高错误文档平均余弦')
for ql, dl in [('zh', 'zh'), ('en', 'en'), ('zh', 'en'), ('en', 'zh')]:
    S = Q[ql] @ D[dl].T
    ranks, pos, neg, top = [], [], [], []
    for i, g in enumerate(gold):
        order = np.argsort(-S[i])
        r = int(np.where(order == g)[0][0]) + 1
        ranks.append(r); pos.append(S[i, g]); neg.append(max(S[i, j] for j in range(len(ids)) if j != g))
        top.append([ids[j] for j in order[:5]])
    ranks = np.array(ranks)
    r1, r5, mrr = (ranks == 1).mean(), (ranks <= 5).mean(), (1 / ranks).mean()
    print(f'{ql}→{dl:5} {r1:6.3f} {r5:6.3f} {mrr:6.3f}  {np.mean(pos):.3f}            {np.mean(neg):.3f}')
    out['runs'][f'{ql}->{dl}'] = {'recall@1': r1, 'recall@5': r5, 'mrr': mrr, 'ranks': ranks.tolist(), 'top5': top,
                                   'gold_cos': [float(x) for x in pos], 'best_wrong_cos': [float(x) for x in neg]}
json.dump(out, open(f'results-{tag}.json', 'w'), ensure_ascii=False, indent=1, default=float)
