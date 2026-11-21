# 本地嵌入模型的中文检索评测

配套文章：[nomic-embed-text 看不见 79% 的汉字](https://costalong.com/2026/11/20/local-embedding-chinese-retrieval/)。

`corpus.py` 是手写的 48 段技术短文（中英文各一份）和 40 条问题，每条问题标注 1 个正确段落。`evaluate.py` 通过 Ollama 的 `/api/embed` 给问题和段落算向量，按余弦相似度排序，对中对中、英对英、中对英、英对中四种组合算 recall@1、recall@5 和 MRR。其余脚本用来查原因：词表里有多少汉字、哪些汉字落到同一个未知 token、长文档在哪里被截断。

这是教学用的小评测，语料和问题都由作者一人写成，规模很小，不是嵌入模型的排行榜，结论只用来判断"这个模型能不能用在中文上"。

## 文件

| 文件 | 作用 |
|---|---|
| `corpus.py` | 48 段语料（中文平均 65 字）和 40 条问题，中英文各一份 |
| `evaluate.py` | `evaluate.py MODEL [查询前缀 文档前缀]`，四种组合的指标写 `results-<tag>.json` |
| `analyze.py` | `analyze.py results-*.json`，按问题里是否夹英文拆开中对中结果，列出排名最差的问题 |
| `unk.py` | 把语料里每个汉字单独嵌入，和生僻字「龘」的向量比较，统计落到未知 token 的汉字 |
| `vocab.py` | `vocab.py <GGUF 文件>`，直接读模型词表，数里面的单个汉字 |
| `longdoc.py` | `longdoc.py MODEL [查询前缀 文档前缀]`，事实句放在长文档开头或末尾，看截断和 `truncate: false` 的报错 |
| `bge-ctx.py` | 用 bge-m3 跑同样的长文档检查 |

## 运行

文章数据来自 Ollama 0.35.0（systemd 服务），RTX 3060 12 GiB，i7-14700KF，模型 nomic-embed-text:latest（nomic-embed-text-v1.5，F16，768 维），对照模型 bge-m3:latest（F16，1024 维）。脚本需要 numpy，`vocab.py` 另外需要 `gguf` 包。

```bash
cd local-embedding-chinese-retrieval
ollama pull nomic-embed-text
ollama pull bge-m3
pip install numpy gguf

python3 evaluate.py nomic-embed-text
python3 evaluate.py nomic-embed-text "search_query: " "search_document: "
python3 evaluate.py bge-m3
python3 analyze.py results-*.json

python3 unk.py
# GGUF 路径取 `ollama show --modelfile nomic-embed-text` 输出里 FROM 那一行
python3 vocab.py /path/to/models/blobs/sha256-...
python3 longdoc.py nomic-embed-text
python3 bge-ctx.py
```

## 验证与边界

- 嵌入是确定性计算，同一输入重复调用向量不变，所以每个组合只跑了一次。
- 只有 40 条问题，recall@1 差 1 条就是 2.5 个百分点，几个点以内的差别不要当真。
- 英文版语料是作者对照着写的，不是专业译文；问题的措辞也带着同一个人的习惯。
- Ollama 返回的向量已经 L2 归一化，脚本直接用点积当余弦。换别的嵌入服务时要先确认这一点。
