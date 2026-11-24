"""判分工具。arith 取最后一个“答案：数字”，没写这一行就算错（题面要求了这个格式，程序要靠它取答案）；
lenient=True 时退而取最后一个 \\boxed{数字}，用来区分“算错”和“只是没按格式写”；fact 有“最终答案：”时只看那一行，否则看整段输出；
code 取最后一个 ```python 代码块，逐条断言放进独立 python3 -I 进程跑，5 秒超时，没有沙箱。"""
import json, re, subprocess, tempfile
from pathlib import Path

HERE = Path(__file__).parent
TASKS = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "tasks.jsonl").read_text().splitlines()}


def num(v):
    try:
        return int(str(v).replace(",", "").strip())
    except ValueError:
        return None


ANS = r"答案\s*(?:是|为)?\s*[:：]?\s*\**\s*(-?[\d,]+)"


def arith_value(o, lenient=False):
    m = re.findall(ANS, o)
    if m:
        return num(m[-1])
    if not lenient:
        return None
    b = re.findall(r"\\boxed\{\s*(-?[\d,]+)", o)
    return num(b[-1]) if b else None


def code_of(o):
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", o, re.S)
    return m[-1] if m else o


def run_code(code, test):
    """返回 None 表示全部通过，否则返回第一条失败的断言和报错的最后一行。"""
    asserts = test   # tasks.jsonl 里已经是逐条断言的列表
    with tempfile.TemporaryDirectory() as d:
        for a in asserts:
            try:
                p = subprocess.run(["python3", "-I", "-c", code + "\n" + a], cwd=d, capture_output=True, text=True, timeout=5)
            except subprocess.TimeoutExpired:
                return f"{a}\n超时（5 秒）"
            if p.returncode:
                err = [l for l in p.stderr.strip().splitlines() if l.strip()]
                return f"{a}\n{err[-1] if err else 'exit ' + str(p.returncode)}"
    return None


def check(tid, o, lenient=False):
    """返回 (是否正确, 给外部校验用的报错信息)"""
    t = TASKS[tid]
    if t["kind"] == "arith":
        v = arith_value(o, lenient)
        return (v is not None and v == t["answer"], None)
    if t["kind"] == "fact":
        m = re.findall(r"最终答案\s*[:：]\s*(.+)", o)
        s = re.sub(r"\s", "", m[-1] if m else o)
        return (any(a in s for a in t["answers"]), None)
    err = run_code(code_of(o), t["test"])
    return (err is None, err)


def final_answer(tid, o):
    """用来判断修改前后答案是否相同：arith 比数字，fact 比最终答案行，code 比代码块（去掉空白）。"""
    t = TASKS[tid]
    if t["kind"] == "arith":
        return arith_value(o, True)
    if t["kind"] == "fact":
        m = re.findall(r"最终答案\s*[:：]\s*(.+)", o)
        return re.sub(r"[\s。.!！]", "", m[-1] if m else o)
    return re.sub(r"\s", "", code_of(o))
