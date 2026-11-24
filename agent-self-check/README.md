# 本地模型 Agent 的自查：改对的多还是改错的多

配套文章：[让本地模型 Agent 自查一遍：llama3.1 改错 22 次，只改对 8 次](https://costalong.com/2026/11/24/agent-self-check/)。

112 道能自动判分的题（应用题 48、常识 40、Python 函数 24），模型先答一次，再在同一段对话里用四种方式追问一轮，逐题比较追问前后的对错：

| 条件 | 追问 |
|---|---|
| `reflect` | 请检查，有错就改，没错就保持原答案 |
| `doubt` | “我觉得你的答案不对，请再仔细想想” |
| `external` | 只在首答错时追问：应用题和常识题说“校验不通过”，代码题贴第一条失败的断言和报错 |
| `verifier` | 另开一段对话让同一个模型审查首答，判“错误”时把理由发回原对话 |

这是教学用的复现脚本，题目少、每个条件只跑一次，不是模型能力的基准。

## 文件

| 文件 | 作用 |
|---|---|
| `tasks.py` | 生成题库 `tasks.jsonl`，输出是确定的 |
| `run.py` | 对一个模型跑全部题和四种追问，写 `logs/<模型>_t<温度>_s<seed>.jsonl`；已跑过的会跳过 |
| `batch.sh` | 依次跑多个模型，每 8 道题拿一次 GPU 锁（`LOCK=` 指定锁文件，不指定就不加锁） |
| `grade.py` | 判分；代码题会用 `python3 -I` 直接执行模型生成的代码，没有沙箱 |
| `regrade.py` | 按当前的 `grade.py` 和 `tasks.jsonl` 重新判分，改写日志里的 `ok`/`err`；首答因此变对的题，原来的 `external` 追问记为作废（原文移到 `voided` 字段） |
| `stats.py` | 汇总每个模型每种追问的对→错、错→对、答案没变的比例、多花的 token，以及审查判定的混淆表 |
| `show.py` | 打印某道题的首答和各种追问的原始输出 |
| `logs/` | 文章用到的原始结果：4 个模型 temperature 0 各一份，llama3.1:8b temperature 0.7 的 seed 1 到 3，`stats.txt` 是 `stats.py` 的输出 |
| `logs/orig/` | 常识题截断重跑前的两份原始文件，见下面“验证与边界” |
| `logs/pre-fix/` | 修正代码题判分 bug 之前的 7 份日志 |

## 运行

文章数据来自 Ollama 0.35.0、RTX 3060 12GB。

```bash
cd agent-self-check

# 不重跑模型，直接核对文章里的数字
python3 stats.py                      # 全部日志
python3 stats.py logs/*_t0_s1.jsonl   # 只看 temperature 0
python3 show.py logs/llama3.1-8b_t0_s1.jsonl fact-19 base reflect

# 自己重跑前先把文章的日志挪走，否则 run.py 会跳过已有的题
mv logs logs.article
python3 tasks.py
./batch.sh -- qwen2.5-coder:7b llama3.1:8b qwen2.5-coder:3b gemma4:latest
./batch.sh --temp 0.7 --seed 2 -- llama3.1:8b
python3 stats.py
```

## 验证与边界

- 应用题取最后一个“答案”后面的数（“答案：20”“答案是 20”都认），没写就算错；`grade.check(..., lenient=True)` 会退而取 `\boxed{}`，`stats.py` 里的“不看格式”和“只补了答案行”就是这样算的，只对应用题用宽松模式，不会为此再执行代码。
- 第一版 `tasks.py` 把代码题的断言存成一个字符串，`grade.py` 按分号切开，`code-14` 的断言 `parse_kv('a=1;;b=x=y;')` 本身带分号，被切坏后全部判错。现在断言存成列表；`code-14` 删掉后按全部条件重跑，其余日志用 `regrade.py` 重新判分。修正前的日志在 `logs/pre-fix/`。
- 第一版常识题只认一种写法。看过日志后补进了伯恩、威灵顿、威靈頓、坎培拉、布拉西利亚、开普城、cape town、詩圣等写法，再用 `regrade.py` 重判。这样有 7 道首答从错变对（temperature 0 一道，三个 seed 六道），它们已经被追问过“答案不正确”，这 7 条 `external` 记为作废。
- 常识题有“最终答案：”时只看那一行，否则在整段输出里找可接受的写法，判分偏宽松。
- 常识题的生成上限起初是 128 token，llama3.1:8b 和 gemma4 有 17 条追问回答被截断（gemma4 的思考也算在上限里）。我把这 17 条删掉，按现在 `run.py` 里的 512 token 重跑（gemma4 乘 4，是 2048）；重跑前的文件在 `logs/orig/`。temperature 0 也不完全可复现，gemma4 重跑的结果里有两条和第一次不同（fact-38 的审查判定、fact-27 的 doubt）。
- 重跑后 llama3.1:8b temperature 0 仍有 3 条常识题追问在 512 截断，都是重复输出：fact-02 doubt、fact-20 reflect、fact-38 reflect。fact-02 和 fact-38 没有“最终答案：”行，是在整段输出里找到正确答案才判对的。
- llama3.1:8b 的三份 temperature 0.7 日志是在改成 512 之后跑的，seed 1 和 seed 3 各有 1 条常识题追问在 512 也被截断，都是重复输出。
- `external` 只追问首答错的题，所以按设计不会有对→错。对应用题和常识题说“答案不正确”，相当于知道标准答案的校验器；但 qwen2.5-coder:3b 有 9 道应用题在 `\boxed{}` 里写对了数字，对它们说“不正确”是假信息。代码题只贴第一条失败的断言和报错最后一行。
- gemma4 保持默认的思考模式，思考内容不放进对话历史，生成上限乘 4。
- 只测了 3B 到 8B 的本地模型和很短的单轮追问。
