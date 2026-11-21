# Ollama 长提示词静默截断的实验脚本

配套文章：[Ollama 静默截断长提示词：上下文 4096 时，4184 token 只剩 2050](https://costalong.com/2026/11/20/ollama-context-truncation/)。

脚本用重复的变更日志行拼出不同长度的提示词（105 行约 3006 token，300 行约 9051 token），发给 Ollama，记录送进模型的 token 数、服务日志里的 `truncating input prompt` 行，以及模型的回答能不能通过两个断言。结果追加到当前目录下的 `exp*.jsonl`。

这是教学用的复现脚本，用来观察截断规则和 `num_ctx` 的来源，不是基准。

## 文件

| 文件 | 作用 |
|---|---|
| `ctxlib.py` | 公共函数：拼提示词、调 `/api/chat`、`/api/generate`、`/v1/chat/completions`，读 journal 里的截断行，跑断言 |
| `exp1.py` | 截断规则：`spec = num_ctx:行数[:num_predict[:num_keep]]`，逐个组合看剩下多少 token |
| `exp1b.py` | `truncate`、`shift` 两个请求开关，以及多轮对话里整条消息被丢掉 |
| `exp2.py` | 任务说明写在开头和写在末尾，截断后各做对几次（温度 0，各 3 次） |
| `exp2b.py` | 问题放末尾，分别问开头和结尾附近的一行日志 |
| `exp3.py` | 同一个 9051 token 提示词走三个接口，截得是否一样 |
| `exp4.py` | `num_ctx` 来自哪里：请求、Modelfile、环境变量、显存档位默认值 |
| `exp5.py` | 开大 `num_ctx` 的代价：加载时间、预填充和生成速度 |
| `peaks.py` | 把 `nvidia-smi -l 1` 的采样和 `exp5.jsonl` 对齐，算每个 `num_ctx` 的显存峰值 |
| `Modelfile.ctx16k` | `exp4.py` 用的临时模型 `qwen-ctx16k-tmp` |

## 运行

文章数据来自 Ollama 0.35.0（systemd 服务，后端是自带的 llama-server），RTX 3060 12 GiB（桌面程序约占 4.1 GiB），模型 qwen2.5-coder:7b 和 llama3.1:8b，Python 3.14。12 GiB 显存下默认上下文是 4096。

```bash
cd ollama-context-truncation

# 截断规则和位置
python3 exp1.py exp1.jsonl 4096:105 4096:170 4096:170:128:200 8192:300
python3 exp1b.py
python3 exp2.py
python3 exp2b.py
python3 exp3.py

# num_ctx 的来源：默认实例读 journal
ollama create qwen-ctx16k-tmp -f Modelfile.ctx16k
python3 exp4.py 11434 journal default

# 另起一个设了 OLLAMA_CONTEXT_LENGTH 的临时实例，日志写到文件
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=/path/to/models OLLAMA_NOPRUNE=1 \
  OLLAMA_CONTEXT_LENGTH=8192 ollama serve > serve-8192.log 2>&1 &
python3 exp4.py 11435 serve-8192.log env8192
kill %1
ollama rm qwen-ctx16k-tmp

# 显存代价：另开一个终端先采样
nvidia-smi --query-gpu=timestamp,memory.used --format=csv,noheader -l 1 > vram_exp5.log &
python3 exp5.py 4096,8192,16384,32768
kill %1
python3 peaks.py exp5.jsonl
```

`OLLAMA_MODELS` 指向系统服务的模型目录，`OLLAMA_NOPRUNE=1` 避免第二个实例启动时清理共用目录。

## 验证与边界

- 截断行来自服务日志。`ctxlib.py` 假设 systemd unit 名为 `ollama`、当前用户能读它的 journal；保存输出时会把当前用户名替换成 `host`。
- 每个组合大多只跑 1 次。温度 0 下同一输入的输出在文章那几轮里没变过，但样本仍然很小。
- 默认上下文按显存档位取值（不足 23 GiB 时 4096），显存更大的机器默认值不同，截断点也会不同。
- `exp5.py` 会反复卸载和加载模型，跑的时候 GPU 上不要有别的推理任务。
