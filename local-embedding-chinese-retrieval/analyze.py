"""按查询是否含英文字母拆分 zh→zh 结果，并列出 zh→zh 排名最差的查询。用法: python3 analyze.py results-*.json"""
import json, re, sys
import numpy as np
from corpus import QUERIES
for path in sys.argv[1:]:
    r = json.load(open(path)); run = r['runs']['zh->zh']; ranks = np.array(run['ranks'])
    has = np.array([bool(re.search('[A-Za-z]', q[1])) for q in QUERIES])
    print(f'== {path}')
    for name, m in [('中文查询含英文字母', has), ('中文查询不含英文字母', ~has)]:
        rk = ranks[m]
        print(f'  {name}: {m.sum()} 条, R@1 {np.mean(rk==1):.3f}, R@5 {np.mean(rk<=5):.3f}, MRR {np.mean(1/rk):.3f}')
    worst = np.argsort(-ranks)[:5]
    for i in worst:
        print(f'  rank {ranks[i]:>2}  {QUERIES[i][1]}  → top1 {run["top5"][i][0]}（应为 {QUERIES[i][0]}）')
