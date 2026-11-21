# 同一个小模型的量化版本对比

配套文章：[qwen2.5:3b 六个量化版本实测：Q4_K_M 和 FP16 打平，Q3_K_M 掉到 49/165，Q2_K 只会输出 4333...](https://costalong.com/2026/11/21/local-model-quantization/)。

用 165 道能自动判分的中文题（常识 45、应用题 60、JSON 抽取 40、Python 函数 20），比较 qwen2.5:3b-instruct 的 FP16、Q8_0、Q4_K_M、Q3_K_L、Q3_K_M、Q2_K 和三个 imatrix 重新量化版本；另外用 llama.cpp 测各版本相对 FP16 的困惑度和 KL 散度，用 Ollama 的计时字段测速度和显存。

这是教学用的复现脚本，只覆盖一个模型、一套题、每题一次运行，不是量化质量的基准。

## 文件

| 文件 | 作用 |
|---|---|
| `tasks.py` | 生成题库 `tasks.jsonl`，输出是确定的，重跑结果逐字节相同 |
| `run.py` | 对一个 Ollama 模型跑完整题库，温度 0、seed 1，写 `logs/<tag>.jsonl` |
| `grade.py` | 判分并和 FP16 逐题对比；代码题会用 `python3 -I` 直接执行模型生成的代码，没有沙箱 |
| `show.py` | 打印某道题在几个版本上的原始输出 |
| `bench.py` | 速度与显存：冷加载、`nvidia-smi` 显存增量、5 次长提示词的首 token 时间和两段速度 |
| `quant.sh` | llama.cpp 的自己量化、imatrix 量化、KL 散度，以及把 imatrix 版本导入 Ollama |
| `kld.py` | 汇总 `logs/kld/*.log` 里的困惑度、KL 散度和首选 token 一致率 |
| `corpus.txt` | 评测 KL 散度用的文本（作者博客 4 篇正文） |
| `calib.txt` | imatrix 校准文本（另外 5 篇正文，和评测文本不重合） |
| `logs/` | 文章用到的原始结果，本机路径已替换成 `./models/`、`<ollama-blob>` 等占位 |

## 运行

文章数据来自 Ollama 0.35.0、RTX 3060 12GB、llama.cpp b12596 的 CPU 构建（从 llama.cpp 的 Releases 下载的预编译包）。

```bash
cd local-model-quantization

# 1. 拉模型并跑题库（每个版本约几分钟）
for q in fp16 q8_0 q4_K_M q3_K_L q3_K_M q2_K; do
  ollama pull qwen2.5:3b-instruct-$q
  python3 run.py qwen2.5:3b-instruct-$q
done

# 2. 判分，和 FP16 逐题对比
python3 grade.py q2_K q3_K_M q3_K_L q4_K_M q8_0 fp16

# 3. 速度与显存（需要 nvidia-smi，测之前别让其他程序占 GPU）
for q in fp16 q8_0 q4_K_M q3_K_M; do python3 bench.py qwen2.5:3b-instruct-$q; done

# 4. 自己量化、imatrix 和 KL 散度，然后跑 imatrix 版本的题库
LLAMA=./llama-b12596 FP16=<fp16 的 GGUF 路径> ./quant.sh
for q in q4_K_M q3_K_M q2_K; do python3 run.py qwen2.5:3b-instruct-imat-$q; done
python3 grade.py imat-q2_K imat-q3_K_M imat-q4_K_M fp16
python3 kld.py

# 5. 清理
ollama rm qwen2.5:3b-instruct-{fp16,q8_0,q4_K_M,q3_K_L,q3_K_M,q2_K} qwen2.5:3b-instruct-imat-{q4_K_M,q3_K_M,q2_K}
rm -rf models
```

不想重跑模型时，`python3 grade.py` 和 `python3 kld.py` 直接读仓库里的 `logs/`，可以先核对文章里的数字。

## 验证与边界

- 温度 0 没有采样随机性，但几道题的差距仍可能来自临界题被量化误差扰动后翻转。文章按逐题配对检验处理，Q4_K_M 和 FP16、Q8_0 和 FP16 的差距都不显著。
- 常识题只要输出里含有答案就算对，判分偏宽松；应用题取最后一个「答案：数字」，没写出这一行就算错。
- 生成上限按题型设：常识 64、应用题 512、JSON 160、代码 512 token，低位版本有不少输出被截断。
- `quant.sh` 是按实验时的命令整理的，和当时逐条手动执行的步骤一致，但没有作为一个整体重跑过。
- `run.py` 和 `bench.py` 从模型名里的 `instruct-` 取 tag，换别的模型要改这一行。
- 只测了 3B 一个尺寸，大模型对低位量化的敏感程度可能不同。
