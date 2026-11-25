"""Logging reverse proxy in front of Ollama: records every /api/chat request
(model, tool names, message sizes, options) and the final prompt_eval_count."""
import http.server, json, os, sys, time, urllib.request

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:11434")
LOG = os.environ.get("PROXY_LOG", "proxy.jsonl")
PORT = int(os.environ.get("PROXY_PORT", "11435"))

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _fwd(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        req = urllib.request.Request(UPSTREAM + self.path, data=body, method=method)
        for k in ("Content-Type", "Accept"):
            if self.headers.get(k): req.add_header(k, self.headers[k])
        rec = None
        if self.path.startswith("/api/chat") and body:
            j = json.loads(body)
            msgs = j.get("messages", [])
            rec = {"ts": time.time(), "model": j.get("model"),
                   "tools": [t.get("function", {}).get("name") for t in j.get("tools") or []],
                   "tools_json_chars": len(json.dumps(j.get("tools") or [], ensure_ascii=False)),
                   "roles": [m.get("role") for m in msgs],
                   "system_chars": sum(len(m.get("content") or "") for m in msgs if m.get("role") == "system"),
                   "options": j.get("options"), "think": j.get("think")}
            if os.environ.get("DUMP_DIR"):
                with open(os.path.join(os.environ["DUMP_DIR"], f"req-{int(time.time()*1000)}.json"), "w") as f:
                    f.write(body.decode())
        try:
            r = urllib.request.urlopen(req, timeout=900)
        except urllib.error.HTTPError as e:
            r = e
        self.send_response(r.status if hasattr(r, "status") else r.code)
        for k, v in r.headers.items():
            if k.lower() in ("content-type",): self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        last = b""
        calls = []
        while True:
            chunk = r.readline()
            if not chunk: break
            last = chunk if chunk.strip() else last
            if rec is not None and b"tool_calls" in chunk:
                try:
                    for c in json.loads(chunk).get("message", {}).get("tool_calls") or []:
                        calls.append(c.get("function", {}).get("name"))
                except Exception:
                    pass
            self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk)); self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()
        if rec is not None:
            try:
                fin = json.loads(last)
                rec["tool_calls"] = calls
                rec.update({k: fin.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration", "prompt_eval_duration", "done_reason")})
            except Exception as e:
                rec["parse_error"] = str(e)
            with open(LOG, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    def do_GET(self): self._fwd("GET")
    def do_POST(self): self._fwd("POST")
    def do_DELETE(self): self._fwd("DELETE")

http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
