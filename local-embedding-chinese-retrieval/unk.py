import json, urllib.request, re, numpy as np
from corpus import DOCS, QUERIES
def emb(ts):
    r=json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/embed',json.dumps({'model':'nomic-embed-text','input':ts}).encode(),{'Content-Type':'application/json'})).read())
    return np.array(r['embeddings'])
text=''.join(d[1] for d in DOCS)+''.join(q[1] for q in QUERIES)
chars=sorted(set(re.findall(r'[一-鿿]',text)))
ref=emb(['龘'])[0]
E=emb(chars)
unk=[c for c,v in zip(chars,E) if v@ref>0.9999]
known=[c for c,v in zip(chars,E) if v@ref<=0.9999]
cnt=sum(text.count(c) for c in unk); tot=len(re.findall(r'[一-鿿]',text))
print(f'语料+查询里不同汉字 {len(chars)} 个；与「龘」向量相同（余弦>0.9999，判为同一个未知 token）的 {len(unk)} 个')
print(f'按出现次数算：{cnt}/{tot} = {cnt/tot:.1%} 的汉字落到这个 token')
print('判为未知的部分汉字:', ''.join(unk[:80]))
print('能区分的部分汉字:', ''.join(known[:80]))
for a,b in [('存','就'),('活','绪'),('容','镜'),('被','被')]:
    va,vb=emb([a,b]); print(f'cos({a},{b})={va@vb:.4f}')
