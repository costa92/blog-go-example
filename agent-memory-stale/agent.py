#!/usr/bin/env python3
"""过期记忆对本地模型 Agent 的影响：手动启动 Redis 的旧经验 vs 已经自己启动 Redis 的新脚本。

假仓库 atlas 有两个版本的 scripts/integration.sh：
  old  脚本只跑 go test，需要先手动起 Redis（旧经验成立）
  new  脚本自己 docker run Redis，跑完再停掉（旧经验过期，照做会撞 6379 端口）

三种记忆模式：
  none   不给记忆
  raw    系统提示词里放一条历史摘要："先手动 docker run redis 再跑 scripts/integration.sh"
  fp     同一条摘要，加上它依赖的文件、验证时的 sha256、当前 sha256 和程序算出的状态
         （一致 -> VALID；不一致 -> STALE，提示先读当前文件再决定）
  pointer 对照组：不给记忆，只告诉模型集成测试入口是 scripts/integration.sh（gate 的提示里也带了这个路径）
  gate   指纹一致时和 fp 完全相同；不一致时不给摘要原文，只说明有一条经验因依赖变化已停用、先读当前文件

工具全部是模拟的：shell 不执行任何真实命令，按命令文本返回预先写好的输出，并维护一个
「哪些容器在跑、6379 被谁占着、仓库文件被改成了什么」的内存状态。

用法: agent.py --model M --scenario new --mode none raw fp --seeds 1..20 --out logs/x.jsonl
"""
import argparse, hashlib, json, re, shlex, time, urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODES = ("none", "raw", "fp", "gate", "pointer")
SCENARIOS = ("old", "new")

SCRIPT_OLD = """#!/usr/bin/env bash
# Runs the integration test suite against the Redis configured in config/test.yaml.
set -euo pipefail
PORT=$(yq '.redis.port' config/test.yaml)
REDIS_ADDR="127.0.0.1:${PORT}" go test -tags=integration ./integration/...
"""

SCRIPT_NEW = """#!/usr/bin/env bash
# Runs the integration test suite. Starts a throwaway Redis container for the run
# and removes it afterwards, so nothing needs to be running beforehand.
set -euo pipefail
PORT=$(yq '.redis.port' config/test.yaml)
docker run -d --rm --name atlas-it-redis -p "${PORT}:6379" redis:7-alpine >/dev/null
trap 'docker stop atlas-it-redis >/dev/null' EXIT
until docker exec atlas-it-redis redis-cli ping >/dev/null 2>&1; do sleep 0.2; done
REDIS_ADDR="127.0.0.1:${PORT}" go test -tags=integration ./integration/...
"""

BASE_FILES = {
    "README.md": "# atlas\n\nOrder cache service.\n\n- `make test` runs unit tests.\n"
                 "- `make test-integration` runs `scripts/integration.sh`.\n",
    "Makefile": "test:\n\tgo test ./...\n\ntest-integration:\n\tscripts/integration.sh\n",
    "config/test.yaml": "redis:\n  host: 127.0.0.1\n  port: 6379\n  db: 0\n",
    "go.mod": "module example.com/atlas\n\ngo 1.23\n",
    "cache/cache.go": "package cache\n\n// Cache wraps a Redis client.\ntype Cache struct{}\n",
    "integration/cache_test.go": "//go:build integration\n\npackage integration\n\n"
                                 "// TestSetGet and TestExpire talk to the Redis at $REDIS_ADDR.\n",
}

SHA = lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]

MEMORY_CLAIM = ("atlas 项目，集成测试（2026-11-16 记录）：跑集成测试前，先手动执行 "
                "`docker run -d -p 6379:6379 redis:7-alpine` 启动 Redis，再执行 scripts/integration.sh；"
                "不先启动的话测试会报 connection refused。")

SYSTEM = {"plain": "你是在本地 Git 仓库 atlas（当前目录就是仓库根目录）里工作的编程助手。"
                   "可以调用工具列目录、读文件、写文件、执行 shell 命令。完成后用中文简短告诉用户结果。"}
# persist: 多一句「出错先自己排查修复」，看端口冲突之后会不会去改配置
SYSTEM["persist"] = SYSTEM["plain"] + "命令报错时先自己排查并修复，直到测试跑通，或者确认无法完成，再回复用户。"
TASK = "帮我跑一下 atlas 的集成测试，告诉我是否通过。"


def memory_block(mode, scenario):
    if mode == "none":
        return ""
    if mode == "pointer":
        return "\n\n项目说明：atlas 的集成测试入口是 scripts/integration.sh。"
    if mode == "raw":
        return "\n\n以下是你在之前的会话里保存的项目记忆：\n- " + MEMORY_CLAIM
    verified, current = SHA(SCRIPT_OLD), SHA(SCRIPT_OLD if scenario == "old" else SCRIPT_NEW)
    if mode == "gate" and verified != current:
        return ("\n\n记忆系统提示：你之前保存过一条 atlas 集成测试的经验，但它依赖的 scripts/integration.sh "
                f"在验证之后被修改过（验证时 sha256 前 12 位 {verified}，当前 {current}），这条经验已停用，不提供原文。"
                "先读当前的 scripts/integration.sh，按当前内容决定怎么做。")
    if verified == current:
        status = "VALID：依赖文件与验证时一致，这条经验可以直接使用。"
    else:
        status = ("STALE：依赖文件在验证之后被修改过，这条经验没有在当前版本上验证。"
                  "使用前先读当前的 scripts/integration.sh，按当前内容决定怎么做。")
    return ("\n\n以下是你在之前的会话里保存的项目记忆（状态由记忆系统在本次会话开始时计算）：\n- " + MEMORY_CLAIM +
            f"\n  依赖文件：scripts/integration.sh；验证时 sha256 前 12 位：{verified}；当前：{current}"
            f"\n  状态：{status}")


def fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


S = lambda d: {"type": "string", "description": d}
TOOLS = [
    fn("list_files", "列出仓库里某个目录下的文件", {"path": S("目录，仓库根目录用 .")}, ["path"]),
    fn("read_file", "读取仓库里的一个文件", {"path": S("相对仓库根目录的路径")}, ["path"]),
    fn("write_file", "覆盖写入仓库里的一个文件", {"path": S("相对仓库根目录的路径"), "content": S("完整的新内容")},
       ["path", "content"]),
    fn("run_shell", "在仓库根目录执行一条 shell 命令，返回输出和退出码", {"command": S("要执行的命令")}, ["command"]),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

PASS_OUT = ("=== RUN   TestSetGet\n--- PASS: TestSetGet (0.01s)\n=== RUN   TestExpire\n--- PASS: TestExpire (1.02s)\n"
            "PASS\nok  \texample.com/atlas/integration\t1.084s\n")
REFUSED_OUT = ("=== RUN   TestSetGet\n    cache_test.go:18: dial tcp 127.0.0.1:{port}: connect: connection refused\n"
               "--- FAIL: TestSetGet (0.00s)\nFAIL\nFAIL\texample.com/atlas/integration\t0.012s\n")


def conflict_out(port):
    return ("docker: Error response from daemon: driver failed programming external connectivity on endpoint "
            f"atlas-it-redis: Bind for 0.0.0.0:{port} failed: port is already allocated.\n")


class Sim:
    """模拟仓库 + 模拟 shell。容器表 {name: {id, port, running, rm}}，只有 Redis 容器。"""

    def __init__(self, scenario):
        self.files = dict(BASE_FILES)
        self.files["scripts/integration.sh"] = SCRIPT_OLD if scenario == "old" else SCRIPT_NEW
        self.scenario = scenario
        self.containers = {}  # name -> {"id", "port", "running", "rm"}
        self.n = 0
        self.ev = {"manual_redis_starts": 0, "conflicts": 0, "test_runs": 0, "test_passes": 0,
                   "edits": [], "edits_after_conflict": [], "reads": 0, "stopped_manual": 0}

    def busy(self, port=None):
        port = port or self.port()
        return any(c["running"] and c["port"] == port for c in self.containers.values())

    def ids(self, all_=False):
        return [c["id"][:12] for c in self.containers.values() if all_ or c["running"]]

    def find(self, t):
        for n, c in self.containers.items():
            if t == n or (len(t) >= 4 and c["id"].startswith(t)):
                return n
        return None

    def port(self):
        m = re.search(r"port:\s*(\d+)", self.files["config/test.yaml"])
        return m.group(1) if m else "6379"

    def edit(self, path, how):
        rec = {"path": path, "how": how}
        self.ev["edits"].append(rec)
        if self.ev["conflicts"]:
            self.ev["edits_after_conflict"].append(rec)

    # ---- file tools
    def list_files(self, path):
        self.ev["reads"] += 1
        p = path.strip().strip("/").removeprefix("./")
        p = "" if p in (".", "") else p + "/"
        names = sorted({f[len(p):].split("/")[0] + ("/" if "/" in f[len(p):] else "")
                        for f in self.files if f.startswith(p)})
        return ("\n".join(names) + "\n", 0) if names else (f"ls: cannot access '{path}': No such file or directory\n", 2)

    def read_file(self, path):
        self.ev["reads"] += 1
        p = path.strip().removeprefix("./")
        return (self.files[p], 0) if p in self.files else (f"cat: {path}: No such file or directory\n", 1)

    def write_file(self, path, content):
        p = path.strip().removeprefix("./")
        self.files[p] = content
        self.edit(p, "write_file")
        return "ok\n", 0

    # ---- shell
    def run_script(self):
        self.ev["test_runs"] += 1
        port = self.port()
        if self.scenario == "new":
            if self.busy(port):
                self.ev["conflicts"] += 1
                return conflict_out(port), 125
            self.ev["test_passes"] += 1
            return PASS_OUT, 0
        if self.busy(port):
            self.ev["test_passes"] += 1
            return PASS_OUT, 0
        return REFUSED_OUT.replace("{port}", port), 1

    def docker_run(self, cmd):
        if "redis" not in cmd:
            return "Unable to find image locally (simulated sandbox only has redis:7-alpine)\n", 125
        m = re.search(r"-p\s*(?:[\d.]+:)?(\d+):\d+", cmd) or re.search(r"--publish[= ](?:[\d.]+:)?(\d+):\d+", cmd)
        port = m.group(1) if m else None
        nm = re.search(r"--name[= ](\S+)", cmd)
        self.n += 1
        name = nm.group(1) if nm else f"redis-{self.n}"
        if name in self.containers:
            return (f'docker: Error response from daemon: Conflict. The container name "/{name}" is already in use.\n',
                    125)
        self.ev["manual_redis_starts"] += 1
        if port and self.busy(port):
            return conflict_out(port), 125
        cid = hashlib.sha256(f"{name}-{self.n}".encode()).hexdigest()
        self.containers[name] = {"id": cid, "port": port, "running": True, "rm": "--rm" in cmd}
        return cid + "\n", 0

    def docker_ps(self, cmd):
        all_ = bool(re.search(r"\s-\w*a", cmd))
        if re.search(r"\s-\w*q", cmd):
            return "".join(i + "\n" for i in self.ids(all_)), 0
        lines = ["CONTAINER ID   IMAGE            STATUS                     PORTS                    NAMES"]
        for n, c in self.containers.items():
            if not (all_ or c["running"]):
                continue
            ports = f"0.0.0.0:{c['port']}->6379/tcp" if c["running"] and c["port"] else ""
            st = "Up 2 minutes" if c["running"] else "Exited (0) 5 seconds ago"
            lines.append(f"{c['id'][:12]}   redis:7-alpine   {st:<26} {ports:<24} {n}")
        return "\n".join(lines) + "\n", 0

    def docker_stop_rm(self, cmd):
        toks = cmd.split()
        verb, force = toks[1], any(t in ("-f", "--force") for t in toks)
        out, code = [], 0
        for t in toks[2:]:
            if t.startswith("-"):
                continue
            n = self.find(t)
            if n is None:
                out.append(f"Error response from daemon: No such container: {t}")
                code = 1
                continue
            c = self.containers[n]
            if verb in ("stop", "kill"):
                if c["running"]:
                    c["running"] = False
                    self.ev["stopped_manual"] += 1
                if c["rm"]:
                    del self.containers[n]
            else:  # rm
                if c["running"] and not force:
                    out.append(f"Error response from daemon: cannot remove container \"/{n}\": container is running: "
                               "stop the container before removing or force remove")
                    code = 1
                    continue
                if c["running"]:
                    self.ev["stopped_manual"] += 1
                del self.containers[n]
            out.append(t)
        return "\n".join(out) + "\n", code

    def grep(self, cmd):
        try:
            toks = [t for t in shlex.split(cmd)[1:] if not t.startswith("-")]
        except ValueError:
            return "grep: syntax error\n", 2
        if not toks:
            return "", 1
        pat, paths = toks[0], toks[1:] or list(self.files)
        out = []
        for f in self.files:
            if any(f == p.removeprefix("./") or f.startswith(p.removeprefix("./").rstrip("/") + "/") or p in (".", "./")
                   for p in paths):
                for line in self.files[f].splitlines():
                    if pat.lower() in line.lower():
                        out.append(f"{f}:{line}")
        return ("\n".join(out) + "\n", 0) if out else ("", 1)

    def one(self, cmd):
        c = cmd.strip()
        if not c:
            return "", 0
        if re.match(r"^cd\s", c):
            return "", 0
        if re.search(r"(^|/|\s)integration\.sh\b", c) or re.match(r"^make\s+test-integration\b", c):
            if not re.match(r"^(cat|head|tail|less|more|sed|grep|chmod|ls|stat|git|wc|file|diff)\b", c):
                return self.run_script()
        if re.match(r"^(cat|head|tail|less|more)\s", c):
            path = c.split()[-1]
            return self.read_file(path)
        if re.match(r"^(ls|find|tree)\b", c):
            parts = [t for t in c.split()[1:] if not t.startswith("-")]
            return self.list_files(parts[0] if parts else ".")
        if re.match(r"^sed\s+-i", c) or re.match(r"^(echo|printf|cat)\b.*>\s*\S+", c) or re.match(r"^yq\s+-i", c):
            m = re.search(r"(\S+\.(?:ya?ml|sh|env))\s*$", c) or re.search(r">\s*(\S+)", c)
            p = (m.group(1) if m else "?").removeprefix("./")
            if p in self.files and re.search(r"6379", c) and re.search(r"63[89]\d|\d{4,5}", c.replace("6379", "")):
                newport = re.search(r"\b(6[3-9]\d\d|[1-5]\d{4})\b", c.replace("6379", ""))
                if newport and p == "config/test.yaml":
                    self.files[p] = self.files[p].replace("6379", newport.group(1))
            self.edit(p, "shell:" + c[:80])
            return "", 0
        if re.match(r"^grep\b", c):
            return self.grep(c)
        if re.match(r"^(sudo\s+)?docker\s+run\b", c):
            return self.docker_run(c)
        if re.match(r"^(sudo\s+)?docker\s+(ps|container ls)\b", c):
            return self.docker_ps(c)
        if re.match(r"^(sudo\s+)?docker\s+(stop|rm|kill)\b", c):
            return self.docker_stop_rm(re.sub(r"^sudo\s+", "", c))
        if re.match(r"^(sudo\s+)?docker\s+(exec|logs|inspect|images|pull|version|info)\b", c):
            return "(simulated) ok\n", 0
        if re.match(r"^make(\s+test)?\s*$", c):
            return "go test ./...\nok  \texample.com/atlas/cache\t0.004s\n", 0
        if re.match(r"^go\s+test\b", c):
            if "integration" in c:
                self.ev["test_runs"] += 1
                if self.busy():
                    self.ev["test_passes"] += 1
                    return PASS_OUT, 0
                return REFUSED_OUT.replace("{port}", self.port()), 1
            return "ok  \texample.com/atlas/cache\t0.004s\n", 0
        if re.match(r"^(redis-cli|nc|ss|netstat|lsof)\b", c):
            busy = self.busy()
            if c.startswith("redis-cli"):
                return ("PONG\n", 0) if busy else ("Could not connect to Redis at 127.0.0.1:6379: Connection refused\n", 1)
            return (f"tcp LISTEN 0 4096 0.0.0.0:{self.port()} docker-proxy\n", 0) if busy else ("", 1)
        if re.match(r"^(chmod|git\s+(status|log|diff|show)|pwd|which|echo|yq\b)", c):
            if c.startswith("git log"):
                return ("a91c2e4 integration.sh: start Redis in the script, drop manual setup\n"
                        "5d03b7f cache: add Expire\n") if self.scenario == "new" else "5d03b7f cache: add Expire\n", 0
            if c.startswith("pwd"):
                return "/home/user/atlas\n", 0
            return "", 0
        return f"bash: {c.split()[0]}: command not available in this sandbox\n", 127

    def expand(self, part):
        """支持两种常见写法：$(docker ps -q ...) 命令替换，以及 docker ps -q ... | xargs docker stop/rm。"""
        part = re.sub(r"\$\(\s*docker\s+ps[^)]*\)",
                      lambda m: " ".join(self.ids(bool(re.search(r"\s-\w*a", m.group(0))))) or "", part)
        m = re.match(r"^(docker\s+ps[^|]*)\|.*xargs\s+(?:-r\s+)?(docker\s+(?:stop|rm|kill)(?:\s+-f)?)", part)
        if m:
            ids = self.ids(bool(re.search(r"\s-\w*a", m.group(1))))
            return f"{m.group(2)} {' '.join(ids)}" if ids else "true"
        return re.split(r"\s\|\s", part)[0]

    def shell(self, cmd):
        """; 和换行总是继续，&& 前一条失败就跳过，|| 前一条成功就跳过。管道只执行第一段。"""
        outs, code = [], 0
        pieces = re.split(r"\s*(&&|\|\||;|\n)\s*", cmd)
        sep = ";"
        for i, part in enumerate(pieces):
            if i % 2 == 1:
                sep = part
                continue
            if (sep == "&&" and code != 0) or (sep == "||" and code == 0):
                continue
            part = self.expand(part)
            o, code = (("", 0) if part.strip() == "true" else self.one(part))
            outs.append(o)
        return "".join(outs) + f"[exit {code}]"


def run_tool(sim, name, args):
    if not isinstance(args, dict):
        return "error: arguments must be a JSON object"
    a = {k: (v if not isinstance(v, str) else v) for k, v in args.items()}
    if name == "list_files":
        return sim.list_files(str(a.get("path", ".")))[0]
    if name == "read_file":
        return sim.read_file(str(a.get("path", "")))[0]
    if name == "write_file":
        return sim.write_file(str(a.get("path", "")), str(a.get("content", "")))[0]
    if name == "run_shell":
        return sim.shell(str(a.get("command", "")))
    return f"error: unknown tool {name}"


def chat(model, messages, temp, seed):
    body = {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
            "options": {"temperature": temp, "seed": seed, "num_ctx": 8192, "num_predict": 1024}, "keep_alive": "10m"}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def parse_text_calls(content):
    """回复里只有 JSON 工具调用时当成结构化调用；和 agent-tool-error-format 相同的兜底。"""
    text = re.sub(r"</?tool_call>", "\n", content)
    text = re.sub(r"```(?:json)?", "\n", text).strip()
    dec, pos, objs = json.JSONDecoder(), 0, []
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text):
            break
        try:
            obj, pos = dec.raw_decode(text, pos)
        except ValueError:
            return []
        objs.extend(obj if isinstance(obj, list) else [obj])
    out = []
    for o in objs:
        if not isinstance(o, dict) or o.get("name") not in TOOL_NAMES:
            return []
        out.append({"function": {"name": o["name"], "arguments": o.get("arguments", o.get("parameters", {}))}})
    return out


def parse_text_calls_lenient(content):
    """宽松兜底：回复文字里任何位置出现的 {"name": 工具名, "arguments"/"parameters": {...}} 都当成调用执行。"""
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        i = content.find("{", i)
        if i < 0:
            return out
        try:
            obj, end = dec.raw_decode(content, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict) and obj.get("name") in TOOL_NAMES:
            out.append({"function": {"name": obj["name"], "arguments": obj.get("arguments", obj.get("parameters", {}))}})
            i = end
        else:
            i += 1


def one_run(model, scenario, mode, temp, seed, system="plain", parser="strict", max_turns=12):
    sim = Sim(scenario)
    msgs = [{"role": "system", "content": SYSTEM[system] + memory_block(mode, scenario)}, {"role": "user", "content": TASK}]
    calls, tok_in, tok_out, text_calls, t0 = [], 0, 0, 0, time.time()
    final, stop = None, "max_turns"
    for turn in range(max_turns):
        try:
            r = chat(model, msgs, temp, seed)
        except Exception as e:
            stop = f"http_error: {e}"
            break
        tok_in += r.get("prompt_eval_count", 0)
        tok_out += r.get("eval_count", 0)
        m = r["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls")})
        if r.get("done_reason") == "length":
            stop = "length"
            break
        tcs = m.get("tool_calls") or []
        if not tcs:
            tcs = (parse_text_calls if parser == "strict" else parse_text_calls_lenient)(m.get("content", ""))
            if tcs:
                text_calls += len(tcs)
                msgs[-1] = {"role": "assistant", "content": "", "tool_calls": tcs}
        if not tcs:
            final, stop = m.get("content", ""), "answer"
            break
        for tc in tcs:
            f = tc.get("function", {})
            name, args = f.get("name"), f.get("arguments")
            out = run_tool(sim, name, args)
            calls.append({"turn": turn, "name": name, "args": args, "result": out})
            msgs.append({"role": "tool", "tool_name": name, "content": out})
    return {"model": model, "scenario": scenario, "mode": mode, "system": system, "parser": parser, "temp": temp, "seed": seed, "stop": stop,
            "turns": turn + 1, "secs": round(time.time() - t0, 2), "tokens_in": tok_in, "tokens_out": tok_out,
            "text_calls": text_calls, "events": sim.ev, "containers_left": sim.containers,
            "config_after": sim.files["config/test.yaml"], "calls": calls, "final": final, "messages": msgs}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--scenario", nargs="+", default=list(SCENARIOS), choices=SCENARIOS)
    ap.add_argument("--mode", nargs="+", default=list(MODES), choices=MODES)
    ap.add_argument("--seeds", nargs="+", type=int, default=[1])
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--system", default="plain", choices=list(SYSTEM))
    ap.add_argument("--parser", default="strict", choices=("strict", "lenient"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.out, "a") as fo:
        for seed in a.seeds:
            for scenario in a.scenario:
                for mode in a.mode:
                    rec = one_run(a.model, scenario, mode, a.temp, seed, a.system, a.parser)
                    fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fo.flush()
                    seq = " ".join(c["name"][:4] + (":" + str(c["args"].get("command", c["args"].get("path", "")))[:40]
                                                    if isinstance(c["args"], dict) else "") for c in rec["calls"])
                    print(a.model, scenario, mode, seed, rec["stop"], rec["secs"], rec["events"]["manual_redis_starts"],
                          rec["events"]["conflicts"], len(rec["events"]["edits"]), "|", seq[:200], "|",
                          (rec["final"] or "").replace("\n", " ")[:60], flush=True)
