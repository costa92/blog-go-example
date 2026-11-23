# 工具目录的大小和描述对本地模型选工具、填参数的影响

配套文章：[本地模型挂 100 个工具：选对率几乎不掉，先出问题的是参数和上下文](https://costalong.com/2026/11/21/local-model-tool-catalog/)。

24 条单步请求，每条只有一个正确工具和一组标准参数。把工具目录从 5 个加到 100 个，工具描述分「只有名字」「一句话」「完整描述+参数说明+枚举」三档，在 Ollama 的 `/api/chat` 上看模型第一次调用选没选对工具、参数对不对，以及提示词长度和耗时。另外测了正确工具放在目录最前或最后、去掉相似工具、不设 `num_ctx` 三种情况。

这是教学用的复现脚本，请求和工具都是虚构的，每个条件每条请求只跑一次，不是工具调用能力的基准。

## 文件

| 文件 | 作用 |
|---|---|
| `catalog.py` | 100 个办公和电商工具，每个工具有一句话描述、补充说明和参数说明；`render()` 按描述档位生成工具定义：`name`、`short`、`full`，以及补测用的 `enum`（一句话描述加枚举） |
| `cases.py` | 24 条请求、正确工具、标准参数，以及每条请求固定带上的 3 个相似工具 |
| `run.py` | 按条件组装目录并调用 Ollama，温度 0、seed 1，每次调用写一行到 `logs/<模型>.jsonl`，已跑过的条件会跳过 |
| `batch.sh` | 文章用到的三批条件：a 是 5/10/20 个工具和去掉相似工具，b 是 50/100 个工具，c 是工具位置和默认上下文，d 是一句话加枚举 |
| `grade.py` | 判分：只看第一个调用，分成 ok、参数错、选错工具、不存在的工具、调用写成文本、没调用；参数合法性按完整定义检查 |
| `stats.py` | 文章里的配对比较（精确 McNemar 检验） |
| `show.py` | 打印某个模型在某条请求上各条件下的调用 |
| `logs/` | 文章所用的原始结果，每个模型一个 jsonl，`run-*.out` 是各批次的运行输出 |

## 运行

文章数据来自 Ollama 0.35.0、RTX 3060 12GB。

```bash
cd local-model-tool-catalog

ollama pull qwen2.5:7b-instruct   # 另外用到 llama3.1:8b、gemma4、qwen2.5-coder:7b、qwen2.5-coder:3b

# a、b、c、d 四批共 648 次调用，在 3060 上请求耗时合计 10 到 24 分钟
for p in a b c d; do ./batch.sh qwen2.5:7b-instruct $p; done
for p in a b c d; do ./batch.sh gemma4:latest $p --think false; done

python3 grade.py logs/*.jsonl --by n,level,order,nb,num_ctx      # 全部条件；文章主表是 order=shuffle、nb=1、num_ctx=16384 的行
python3 grade.py logs/qwen2.5-coder_7b.jsonl --text              # 把文本里的 JSON 当作调用来判
python3 stats.py logs/llama3.1_8b.jsonl logs/gemma4_latest.jsonl logs/qwen2.5_7b-instruct.jsonl
python3 show.py logs/llama3.1_8b.jsonl llama3.1:8b r14 full

ollama rm qwen2.5:7b-instruct
```

`logs/` 是文章所用的原始结果，不想重跑时可以直接用上面的 `grade.py`、`stats.py`、`show.py` 核对文章里的数字。`run.py` 会跳过日志里已经跑过的条件，自己重跑前先把它移走：`mv logs logs.article`。

`grade.py` 和 `stats.py` 覆盖文章里的选对率、参数全对、配对检验和 2023 年日期的计数；gemma4 反问的分类、llama3.1 乱码参数的计数和枚举补测的 5 条请求小表，是用 `show.py` 逐条看输出后人工统计的。

## 验证与边界

- 温度 0、固定 seed，同一条件重跑结果基本相同，所以每个条件只跑一次；条件之间的差别用逐条配对检验，同一条请求在不同目录大小下会重复出现，配对并不独立，p 值偏乐观。
- 目录变大时只加入和请求无关的工具，3 个相似工具从 5 个工具起就在目录里，所以这里测的是「数量」本身，不是「相似工具变多」。
- 「参数全对」指标准参数都在且取值匹配，多填的参数不扣分；`grade.py` 另有一列 `valid` 按完整定义做结构校验，文章没有用。
- 自由文本参数（原因、标题、正文等）只检查是否包含关键字；日期时间比到分钟，接受常见写法。
- 「只有名字」和「一句话」两档不带参数说明和枚举，但判分仍按完整定义检查枚举值，模拟后端真实的校验。
- `--num-ctx 0` 表示请求里不传 `num_ctx`，用 Ollama 的默认值；默认值和显存有关，文章环境下是 4096。
- 请求和工具都是中文场景，换成英文请求结果可能不同。
