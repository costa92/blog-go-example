"""统计 nomic-embed-text 词表里的单个汉字。用法: python3 vocab.py <模型 GGUF 文件>
模型文件路径用 `ollama show --modelfile nomic-embed-text` 输出里 FROM 那一行。"""
import re, sys
from gguf import GGUFReader
from corpus import DOCS, QUERIES
r = GGUFReader(sys.argv[1])
f = r.fields['tokenizer.ggml.tokens']
toks = [bytes(f.parts[i]).decode('utf-8', 'replace') for i in f.data]
for k in ['tokenizer.ggml.model', 'general.name', 'nomic-bert.context_length']:
    if k in r.fields:
        fld = r.fields[k]; v = fld.parts[fld.data[0]]
        print(k, '=', bytes(v).decode() if v.dtype.kind == 'u' and v.dtype.itemsize == 1 else v.tolist())
vocab = set(toks)
cjk = [t for t in toks if re.fullmatch(r'[一-鿿]', t)]
print('词表大小', len(toks), '；其中单个汉字的 token', len(cjk))
text = ''.join(d[1] for d in DOCS) + ''.join(q[1] for q in QUERIES)
chars = sorted(set(re.findall(r'[一-鿿]', text)))
inv = [c for c in chars if c in vocab]
print(f'语料里 541 个不同汉字中，在词表里的 {len(inv)} 个')
for c in '存活就绪容镜的一不':
    print(c, c in vocab)
