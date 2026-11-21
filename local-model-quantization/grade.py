"""判分：python3 grade.py [tag ...]  默认 q2_K q3_K_M q4_K_M q8_0 fp16。
fact 命中任一可接受写法；arith 取最后一个“答案：数字”（也接受“答案是”“答案为”）；json 解析第一个对象逐字段比对；
code 把代码块和断言放进独立 python3 -I 进程跑，5 秒超时。"""
import collections, json, re, subprocess, sys, tempfile
from pathlib import Path

TAGS = sys.argv[1:] or ["q2_K", "q3_K_M", "q4_K_M", "q8_0", "fp16"]
TASKS = {json.loads(l)["id"]: json.loads(l) for l in Path("tasks.jsonl").read_text().splitlines()}
FIELDS = ["name", "city", "order_id", "qty", "total"]

def num(v):
    try:
        return int(str(v).replace(",", "").strip())
    except ValueError:
        return None

def grade(r):
    """返回 (是否正确, 失败原因或 None, 附加信息)"""
    t, o = TASKS[r["id"]], r["out"]
    if r.get("error"):
        return (False, "server_abort", None)
    if t["kind"] == "fact":
        flat = re.sub(r"\s", "", o)
        return (any(a.replace(" ", "") in flat for a in t["answers"]), None, None)
    if t["kind"] == "arith":
        m = re.findall(r"答案\s*(?:是|为)?\s*[:：]?\s*\**\s*(-?[\d,]+)", o)   # 也接受“答案是：114 棵”
        if not m:
            return (False, "no_answer_line", None)
        return (num(m[-1]) == t["answer"], None if num(m[-1]) == t["answer"] else "wrong_number", None)
    if t["kind"] == "json":
        i = o.find("{")
        try:
            d, _ = json.JSONDecoder().raw_decode(o[i:]) if i >= 0 else (None, 0)
        except json.JSONDecodeError:
            d = None
        if not isinstance(d, dict):
            return (False, "bad_json", None)
        e = t["expected"]
        bad = [k for k in FIELDS if (num(d.get(k)) != e[k] if k in ("qty", "total") else str(d.get(k, "")).strip() != e[k])]
        return (not bad, ("field:" + ",".join(bad)) if bad else None, bad)
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", o, re.S)
    code = m[0] if m else o   # 没写代码块时把整段输出当代码跑，格式不扣分
    with tempfile.TemporaryDirectory() as d:
        try:
            p = subprocess.run(["python3", "-I", "-c", code + "\n" + t["test"]], cwd=d, capture_output=True, timeout=5)
        except subprocess.TimeoutExpired:
            return (False, "timeout", None)
    return (p.returncode == 0, None if p.returncode == 0 else ("test_fail" if m else "unfenced_fail"), None)

def load(tag):
    p = Path(f"logs/{tag}.jsonl")
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

if __name__ == "__main__":
    res = {}
    for tag in TAGS:
        rows = load(tag)
        if not rows:
            continue
        res[tag] = {r["id"]: grade(r) for r in rows}
        by = collections.Counter(); n = collections.Counter(); why = collections.Counter(); fld = collections.Counter()
        for r in rows:
            ok, w, bad = res[tag][r["id"]]
            n[r["kind"]] += 1; by[r["kind"]] += ok
            if w: why[w.split(":")[0]] += 1
            for k in bad or []: fld[k] += 1
        tot = sum(by.values()), sum(n.values())
        print(f"{tag:7s} 总 {tot[0]}/{tot[1]}  " + "  ".join(f"{k} {by[k]}/{n[k]}" for k in ("fact", "arith", "json", "code"))
              + f"  | 失败 {dict(why)} 字段 {dict(fld)}")
    if "fp16" in res:
        print("\n与 fp16 逐题对比（fp16对本错 / fp16错本对）与输出完全一致的题数：")
        f16 = load("fp16"); same = {r["id"]: r["out"] for r in f16}
        for tag in res:
            if tag == "fp16": continue
            a = sum(res["fp16"][i][0] and not res[tag][i][0] for i in res[tag])
            b = sum(not res["fp16"][i][0] and res[tag][i][0] for i in res[tag])
            ident = sum(r["out"] == same[r["id"]] for r in load(tag))
            print(f"{tag:7s} 丢 {a}  得 {b}  输出一字不差 {ident}/{len(res[tag])}")
