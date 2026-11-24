# blog-go-example

[翼舞成梦博客](https://github.com/costa92/hexo_blog)的文章配套代码：Go 案例，以及文章实验用的 Python 和 shell 脚本。

## 仓库分工

- `costa92/hexo_blog`：博客正文、Hexo 主题、发布流程和写作 skill。
- `costa92/blog-go-example`：文章中的可运行 Go 案例、实验脚本，及其测试、使用说明。

按文章主题组织示例；示例说明应链接对应文章，并写明运行方法与演示边界。本仓库不承载 Hexo 博客源码，也不发布博客网站。

## 案例

- [AI-Native 批准与执行检查](ai-native-change-gate/README.md)：用单进程 Go 模型验证过期批准、条件写入、幂等回执与并发竞争，不调用模型或生产集群。
- [审核结论绑定内容摘要](review-gates/README.md)：`gate` 命令把设计批准、测试记录和代码复核绑到摘要上，附一次补错误分支后旧批准被拒的交接重放，以及 15 个变异的测试结果。
- [Super-agent 协调层](superagent/README.md)：基于 `kart-io/goagent v0.33.0`，包含任务分工、消息路由、可恢复 Worker 和 Outbox 通知重试；另提供 [GoAgent Harness CSV 编码执行案例](superagent/codingworker/README.md)。
- [encoding/json v1 与 v2 对比](jsonv2/README.md)：用测试断言两个版本的默认行为差异、迁移选项和基准，需要 Go 1.27。
- [Go 内存上限在 Kubernetes 里的表现](gomemlimit/README.md)：文章 GOMEMLIMIT / GOMAXPROCS 实验用的负载程序和 kind 脚本，独立 go.mod，用 Docker 构建。
- [Go 长连接与 Kubernetes 扩容后的流量不均](keepalive/README.md)：文章 keep-alive 实验用的回显服务、压测客户端和 kind 脚本，独立 go.mod，用 Docker 构建。
- [Go 服务在 CPU limit 下的尾延迟](cpulimit/README.md)：文章 CPU limit 实验用的服务端、开环压测器和 kind 脚本，独立 go.mod，用 Docker 构建。
- [tz-verify：构建期校验镜像时区别名](tzverify/README.md)：文章 tzdata-legacy 排查里的构建期校验程序，两段式 Dockerfile，镜像缺旧时区名时让构建失败。

## 实验脚本

下面这些目录是文章实验的 Go 程序及 Python / shell 脚本，只保留代码和小输入，不含原始日志。

- [Qwen3.8-27B Harness 适配器对照](qwen38-harness/README.md)：Go 驱动真实的 Pi 1.5.2 与 DeepSeek Harness 0.2.2-rc.1，对照基座与 Pi LoRA 的三道修复题；包含 V1/V2 外部验收、工具/token/耗时统计，以及不调用真实模型的自检和接口集成测试。

- [Ollama /v1 兼容接口的静默差异](ollama-openai-compat/README.md)：同一请求分别发给 `/v1` 和原生接口，对照温度、上下文、`response_format`、工具调用和错误处理。
- [Ollama 长提示词静默截断](ollama-context-truncation/README.md)：截断规则、任务说明写在哪里、`num_ctx` 的来源和显存代价。
- [Ollama 提示词前缀缓存](ollama-prefix-cache/README.md)：时间戳位置、工具顺序、多轮对话和接口混用对缓存命中和首字延迟的影响。
- [12GB 显卡上的 Ollama 参数](ollama-12gb-tuning/README.md)：`num_ctx`、Flash Attention、KV 缓存量化和 `OLLAMA_NUM_PARALLEL` 的显存、速度和长上下文检索判分脚本，附原始结果。
- [本地代码模型的采样温度](local-model-temperature/README.md)：10 道带隐藏测试的 Python 题，5 档温度下的通过率、多样性和可复现性，附 MiniMax 对照。
- [本地嵌入模型的中文检索](local-embedding-chinese-retrieval/README.md)：48 段中英文语料、40 条问题，测 recall、词表覆盖和长文档截断。
- [大模型结构化 JSON 输出](llm-json-output/README.md)：36 条客服消息抽字段，对比提示词、`format: json` 和 JSON Schema，附 MiniMax 对照。
- [本地模型多步工具调用](local-model-tool-calling/README.md)：假工单系统加最小工具循环，按第一处出错的地方给每次运行打标签。
- [同一个小模型的量化版本对比](local-model-quantization/README.md)：qwen2.5:3b 六个量化版本和 imatrix 重新量化的题库、判分、KL 散度和速度显存脚本，附原始结果。
- [本地模型 Agent 的间接提示注入](local-agent-prompt-injection/README.md)：假工具沙箱里的注入用例、六种防护和判分脚本，附原始结果。
- [工具目录的大小和描述](local-model-tool-catalog/README.md)：100 个虚构工具、24 条单步请求，按目录大小、描述档位和上下文长度测选工具与填参数。
- [工具报错写法与 Agent 恢复](agent-tool-error-format/README.md)：假业务服务注入 6 种失败、四种报错写法和报错处理规则的对比与判分脚本。
- [本地模型当裁判的偏差](local-llm-judge-bias/README.md)：32 道一对一判题，测位置、长度、格式偏差和几种补救办法。
- [Ollama 在 Kubernetes 里的冷启动和资源限制](ollama-on-kubernetes/README.md)：kind 集群里的冷启动、`keep_alive`、CPU / 内存 limit 和滚动重启实验脚本。
- [Claude Code 无头调用的 token 账](claude-code-token-budget/README.md)：逐块测内置工具、MCP、CLAUDE.md、技能和缓存的上下文开销，含一个无依赖的 MCP 服务器。
- [小模型先答、大模型兜底的模型路由](agent-model-routing/README.md)：150 道自动判分题上比较 3b 判难度、自报把握、答案 logprob、格式校验和自一致性几种升级规则，附 Ollama 换模型的加载计时和原始结果。
- [Agent 长会话的历史策略](agent-history-compaction/README.md)：28 轮脚本化会话、7 种历史策略（截断、滑窗、钉住开头、规则进 system、LLM 摘要、状态笔记）和 6 个探针的判分脚本，附原始结果。
- [本地模型 Agent 的自查](agent-self-check/README.md)：112 道自动判分题上比较“请检查”、“我觉得不对”、校验/测试报错和另起一次审查四种追问的对改错与错改对，附原始结果。
- [过期的项目记忆](agent-memory-stale/README.md)：假仓库的集成测试脚本改成自己起 Redis 后，比较不给记忆、原文注入、带文件指纹标 STALE 和按指纹停用四种做法，模拟 shell 与判分脚本，附原始结果。
- [Superpowers 计划导入 GSD](superpowers-gsd-workflow/README.md)：一个小 Go 命令行上实跑 brainstorming → writing-plans → `/gsd-import` 的三种导入情形，再比较 `/gsd-execute-phase` 和 `executing-plans` 的耗时与费用，附汇总数据。
- [CLAUDE.md 长度与规则遵守率](claude-md-length/README.md)：同样 8 条可判定规则放进 50 到 1500 行、`@import`、埋进列表和改用 hook 的各版 CLAUDE.md，10 个 Go 小任务上打分，附首轮 token 和原始结果。
