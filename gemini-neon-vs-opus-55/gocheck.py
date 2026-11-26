"""对 logs/coding.jsonl 里每个回答跑隐藏测试，结果写 logs/coding-tests.jsonl。

取回答里第一个 ```go 代码块，和题目的 solution_test.go 放进临时模块，
`go test -race -count=3`：同一个顶层测试三遍都过才算过（parmap 这类并发题对部分错误实现结果不稳定）。
编译失败记为该题全部测试不过；整包超时或 panic 时逐个测试单独重跑，算部分得分。
"""
import collections
import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import tempfile

GOMOD = "module solution\n\ngo 1.27\n"


def code_of(text):
    m = re.search(r"```go\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else None


def tests_of(task):
    src = open(f"coding/{task}/solution_test.go").read()
    return re.findall(r"^func (Test\w+)\(t \*testing\.T\)", src, re.M)


def check(r):
    names = tests_of(r["id"])
    code = code_of(r["text"])
    res = {"id": r["id"], "model": r["model"], "run": r["run"], "tests": len(names)}
    if code is None:
        return {**res, "passed": 0, "status": "no_code"}
    d = tempfile.mkdtemp(prefix="gocheck-")
    try:
        open(f"{d}/go.mod", "w").write(GOMOD)
        open(f"{d}/solution.go", "w").write(code)
        shutil.copy(f"coding/{r['id']}/solution_test.go", d)
        p = subprocess.run(["go", "test", "-race", "-count=3", "-json", "-timeout", "300s", "."],
                           cwd=d, capture_output=True, text=True)
        fails, seen = collections.Counter(), collections.Counter()
        for line in p.stdout.splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get("Test", "")
            if t in names and e.get("Action") in ("pass", "fail"):
                seen[t] += 1
                fails[t] += e["Action"] == "fail"
        passed = [t for t in names if seen[t] == 3 and fails[t] == 0]
        if seen and any(seen[t] < 3 for t in names):
            # 某个测试卡死或 panic 会让同包后面的测试没机会跑：逐个单独重跑
            passed = [t for t in names if subprocess.run(
                ["go", "test", "-race", "-count=3", "-timeout", "60s", "-run", f"^{t}$", "."],
                cwd=d, capture_output=True).returncode == 0]
        status = "ok" if len(passed) == len(names) else ("build_fail" if not seen else "partial")
        return {**res, "passed": len(passed), "failed_tests": [t for t in names if t not in passed],
                "status": status, "stderr": (p.stderr or "")[-400:] if not seen else ""}
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    rows = [r for r in map(json.loads, open("logs/coding.jsonl")) if "error" not in r]
    with cf.ThreadPoolExecutor(4) as ex:
        out = list(ex.map(check, rows))
    with open("logs/coding-tests.jsonl", "w") as f:
        for o in sorted(out, key=lambda o: (o["id"], o["model"], o["run"])):
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(len(out), "checked")
