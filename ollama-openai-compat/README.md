# Ollama /v1 兼容接口与原生接口的对照脚本

配套文章：[Ollama /v1 兼容接口的 7 处静默差异](https://costalong.com/2026/11/20/ollama-openai-compat/)。

每个脚本把同一个请求分别发给 Ollama 的 OpenAI 兼容接口 `/v1/chat/completions` 和原生接口 `/api/chat`，打印两边的响应，有的还会读 `journalctl -u ollama` 里 llama-server 打出的采样参数行，或者用 `ollama ps` 看模型的上下文和驻留状态。原始响应用 `save()` 写成当前目录下的 json 文件。

这是教学用的对照脚本，只用来观察兼容层怎么转换参数，不是基准，结论也只对文章里的 Ollama 版本成立。

## 文件

| 文件 | 作用 |
|---|---|
| `lib.py` | 公共函数：`post()` 发 JSON 请求，`save()` 保存原始响应，`ps()` 读 `ollama ps` |
| `e1_sampling.py` | 不传温度时两个接口各用什么值，对照 `/v1` 显式传 `temperature` |
| `e1d_sampler_log.py` | 从 `journalctl -u ollama` 截取每次请求的采样参数行 |
| `e2_ctx.py` | `options.num_ctx` 在 `/v1` 里被丢掉：同一段长提示词在两个接口的 token 数和回答 |
| `e4_format.py` | `response_format` 的几种写法，写错时是否报错 |
| `e6_tools.py` | 工具调用在两个接口上的请求和返回 |
| `e7_errors.py` | 非法参数、不存在的模型等错误请求，各接口是报错还是静默接受 |
| `e9_sdk.py` | 用 openai SDK 复核关键几条（含 `extra_body={'keep_alive': 0}`） |
| `Modelfile.16k` | 写死 `num_ctx 16384` 的模型变体，文章里用来给 `/v1` 开大上下文 |

## 运行

文章数据来自 Ollama 0.35.0（systemd 服务，监听 127.0.0.1:11434，服务配置没改），RTX 3060 12 GiB，模型 qwen2.5-coder:7b 和 llama3.1:8b，Python 3.14，openai SDK 3.57.0。

```bash
cd ollama-openai-compat
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b

python3 e1_sampling.py
python3 e1d_sampler_log.py     # 需要能读 ollama 服务的 journal，见下
python3 e2_ctx.py
python3 e4_format.py
python3 e6_tools.py
python3 e7_errors.py

# SDK 复核，装在临时虚拟环境里
python3 -m venv .venv && .venv/bin/pip install openai==3.57.0
.venv/bin/python e9_sdk.py

# Modelfile 变体：/v1 请求把 model 换成 qwen-coder-16k
ollama create qwen-coder-16k -f Modelfile.16k
ollama rm qwen-coder-16k       # 用完删除
```

`e9_sdk.py` 里的 `api_key='ollama'` 只是占位，Ollama 不校验它。

## 验证与边界

- `e1d_sampler_log.py`、`e2_ctx.py` 依赖服务日志里有采样参数行。文章那台机器的日志级别较高才打得出来；默认级别下可能看不到，可以试着给服务加 `OLLAMA_DEBUG=1` 后重启。脚本还假设服务由 systemd 管理、unit 名为 `ollama`，当前用户能读它的 journal。
- 文章里 `keep_alive`（SDK 那条除外）、流式响应的 `usage`、`id` 和 `n` 几项是在终端里直接发的请求，没有留下脚本。用 `lib.post()` 照文章给出的请求体发一次即可复现。
- 大部分结论只跑了一次。温度不为 0 的请求每次输出不同，看的是参数和字段，不是回答内容。
- 兼容层的行为会随 Ollama 版本变化，源码对照用的是 v0.35.0 tag 的 `openai/openai.go`。
