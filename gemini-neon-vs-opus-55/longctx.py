"""生成长上下文检索题 longctx/<size>.json。

干草堆是 Go 标准库源码（按路径排序拼接，带文件头），埋入 8 条真记录和 4 条干扰记录：
真记录写成 `// NOTE(ops-ledger)`，干扰记录写成 `// NOTE(test-fixture)`，服务名与真记录相同但配额不同。
要求模型只报真记录的配额、总和与最大者。字符数按 Go 源码约 2.75 字符/token（Gemini 分词）估算，实际 token 以 API 返回为准。
"""
import json
import os
import pathlib
import random
import subprocess

GOROOT = pathlib.Path(subprocess.check_output(["go", "env", "GOROOT"], text=True).strip())
SIZES = {"100k": 275_000, "300k": 825_000, "600k": 1_650_000}  # 目标字符数，Go 源码实测约 2.75 字符/token
SERVICES = ["atlas", "beacon", "cinder", "dynamo", "ember", "fjord", "garnet", "harbor"]


def corpus():
    files = sorted(p for p in (GOROOT / "src").rglob("*.go") if "testdata" not in p.parts and not p.name.endswith("_test.go"))
    for p in files:
        yield f"\n// ===== FILE: {p.relative_to(GOROOT)} =====\n" + p.read_text(errors="replace")


def build(name, target, seed):
    rng = random.Random(seed)
    chunks, n = [], 0
    for c in corpus():
        chunks.append(c)
        n += len(c)
        if n >= target:
            break
    text = "".join(chunks)
    lines = text.split("\n")
    quotas = {s: rng.randint(100, 9999) for s in SERVICES}
    inserts = [f"// NOTE(ops-ledger): service {s} quota is {q} units." for s, q in quotas.items()]
    for s in rng.sample(SERVICES, 4):
        fake = rng.randint(100, 9999)
        inserts.append(f"// NOTE(test-fixture): service {s} quota is {fake} units (fixture data, not real).")
    rng.shuffle(inserts)
    # 均匀分布在 5%~95% 深度，各自附近随机抖动
    k = len(inserts)
    positions = sorted(int(len(lines) * (0.05 + 0.9 * (i + rng.random()) / k)) for i in range(k))
    depth = {}
    for pos, ins in sorted(zip(positions, inserts), reverse=True):
        lines.insert(pos, ins)
    for i, l in enumerate(lines):
        if l.startswith("// NOTE("):
            depth[l] = round(i / len(lines), 3)
    doc = "\n".join(lines)
    prompt = (
        "下面是一大段 Go 源码。其中散布着若干以 `// NOTE(ops-ledger):` 开头的注释，记录了一些服务的配额；"
        "以 `// NOTE(test-fixture):` 开头的是测试假数据，必须忽略。\n\n"
        "<source>\n" + doc + "\n</source>\n\n"
        "请找出所有 ops-ledger 记录，只输出一个 JSON 对象，不要其他文字，格式为："
        '{"quotas": {"<服务名>": <配额>, ...}, "total": <所有配额之和>, "max_service": "<配额最大的服务名>"}'
    )
    ans = {"quotas": quotas, "total": sum(quotas.values()), "max_service": max(quotas, key=quotas.get)}
    os.makedirs("longctx", exist_ok=True)
    with open(f"longctx/{name}.json", "w") as f:
        json.dump({"id": name, "chars": len(prompt), "answer": ans, "needle_depth": depth, "prompt": prompt}, f, ensure_ascii=False)
    print(name, len(prompt), "chars")


if __name__ == "__main__":
    for i, (name, target) in enumerate(SIZES.items()):
        build(name, target, 100 + i)
