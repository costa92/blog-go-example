"""长文档静默截断：事实句放在长文档开头或末尾，看查询与整篇向量的余弦、prompt_eval_count 和 truncate:false 的报错。
用法: python3 longdoc.py MODEL [qprefix dprefix]"""
import json, sys, subprocess, re, urllib.request, urllib.error
import numpy as np
from corpus import DOCS
M = sys.argv[1]; QP = sys.argv[2] if len(sys.argv) > 2 else ''; DP = sys.argv[3] if len(sys.argv) > 3 else ''
def call(inp, **kw):
    body = json.dumps({'model': M, 'input': inp, **kw}).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/embed', body, {'Content-Type': 'application/json'}), timeout=600).read())
        return 200, r
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
FACT = "The nightly backup job for the billing service runs at 03:17 and uploads its archives to the storage bucket named kestrel-archive."
QUERY = "When does the billing backup run, and which bucket does it upload to?"
filler_sents = [d[2] for d in DOCS if not d[0].startswith('llm')]
def filler(n_sent):
    return ' '.join(filler_sents[i % len(filler_sents)] for i in range(n_sent))
q = np.array(call(QP + QUERY)[1]['embeddings'][0])
_, rf = call(DP + FACT); f = np.array(rf['embeddings'][0])
_, r0 = call(DP + filler(40)); base = np.array(r0['embeddings'][0])
print(f'cos(查询, 事实句本身) = {q @ f:.3f}  （事实句 {rf["prompt_eval_count"]} token）')
print(f'cos(查询, 只有填充文字 40 句) = {q @ base:.3f}')
print(f'{"填充句数":>6} {"位置":4} {"prompt_eval_count":>18} {"cos(查询,整篇)":>14} {"truncate:false":>16}')
since = subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()
for n in [5, 20, 40, 60, 80, 120, 200]:
    for pos in ['开头', '末尾']:
        doc = (FACT + ' ' + filler(n)) if pos == '开头' else (filler(n) + ' ' + FACT)
        c, r = call(DP + doc)
        c2, r2 = call(DP + doc, truncate=False)
        cos = q @ np.array(r['embeddings'][0])
        tf = '200' if c2 == 200 else f'{c2} {json.loads(r2)["error"][:40]}'
        print(f'{n:>6} {pos:4} {r["prompt_eval_count"]:>18} {cos:>14.3f}   {tf}')
j = subprocess.run(['journalctl', '-u', 'ollama', '--since', since, '--no-pager', '-o', 'cat'], capture_output=True, text=True).stdout
print('同期服务日志里含 truncat / WARN 的行数:', sum(1 for l in j.splitlines() if re.search('truncat|WARN', l)))
for l in j.splitlines():
    if re.search('truncat|WARN|n_ubatch|too large|exceed', l, re.I): print('  ', l[:200])
