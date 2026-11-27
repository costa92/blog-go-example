// lab 在本机起 3 个 MCP 副本，前面放一个轮询（或按会话粘滞）的反向代理，
// 用官方 Go SDK 的客户端分别以 2025-11-25 和 2026-07-28 协议访问，记录每个 HTTP 请求。
//
//	go run ./mcp-2026-stateless/lab            # 跑全部场景，写 logs/scenarios.jsonl 和 logs/wire.jsonl
//	go run ./mcp-2026-stateless/lab -serve :8931 -log logs/claude-wire.jsonl   # 单副本，给 Claude Code 连
package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	v2025 = "2025-11-25"
	v2026 = "2026-07-28"
)

// scenario 是一组实验条件；列在 scenarios 里，main 逐个跑。
type scenario struct {
	Name     string `json:"name"`
	Version  string `json:"version"`   // 客户端请求的协议版本
	Routing  string `json:"routing"`   // round-robin | sticky
	Pending  string `json:"pending"`   // MRTR 待确认状态放哪：local（副本内存）| signed（HMAC 自包含）
	CartRepo string `json:"cart_repo"` // 购物车句柄背后的存储：local | shared
	Calls    int    `json:"calls"`
	// Stateless 对应 StreamableHTTPOptions.Stateless；2026-07-28 的请求只有在它为 true 时才被接受。
	Stateless bool `json:"stateless"`
	ListTTLMs int  `json:"list_ttl_ms"` // tools/list 结果里的 ttlMs，0 表示不让客户端缓存
}

var scenarios = []scenario{
	{"legacy-roundrobin", v2025, "round-robin", "signed", "shared", 30, false, 0},
	{"legacy-sticky", v2025, "sticky", "signed", "shared", 30, false, 0},
	{"stateless-roundrobin", v2026, "round-robin", "signed", "shared", 30, true, 0},
	{"stateless-mrtr-local-pending", v2026, "round-robin", "local", "shared", 30, true, 0},
	{"stateless-handle-local-store", v2026, "round-robin", "signed", "local", 30, true, 0},
	{"stateless-list-ttl", v2026, "round-robin", "signed", "shared", 30, true, 60_000},
	{"legacy-client-stateless-server", v2025, "round-robin", "signed", "shared", 30, true, 0},
}

// wireRec 是代理看到的一个 HTTP 请求。
type wireRec struct {
	Scenario   string `json:"scenario"`
	Seq        int    `json:"seq"`
	Backend    int    `json:"backend"`
	HTTPMethod string `json:"http_method"`
	RPCMethod  string `json:"rpc_method,omitempty"`
	ToolName   string `json:"tool,omitempty"`
	HdrVersion string `json:"hdr_protocol_version,omitempty"`
	HdrSession bool   `json:"hdr_session_id"`
	HdrMethod  string `json:"hdr_mcp_method,omitempty"`
	HdrName    string `json:"hdr_mcp_name,omitempty"`
	MetaKeys   string `json:"meta_keys,omitempty"`
	ClientCaps string `json:"client_caps,omitempty"`   // _meta 里声明的客户端能力
	InputActs  string `json:"input_actions,omitempty"` // MRTR 重试里 inputResponses 的 action
	ReqBytes   int    `json:"req_bytes"`
	Status     int    `json:"status"`
	UserAgent  string `json:"user_agent,omitempty"`
}

type result struct {
	scenario
	Op       string `json:"op"`
	OK       int    `json:"ok"`
	Failed   int    `json:"failed"`
	FirstErr string `json:"first_err,omitempty"`
}

var secret = mustRand(32) // 3 个副本共用的 HMAC 密钥，相当于部署时注入的同一个配置

func mustRand(n int) []byte {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return b
}

// sharedCarts 模拟 Redis 之类的外部存储，3 个副本看到同一份。
var sharedCarts = struct {
	sync.Mutex
	m map[string][]string
}{m: map[string][]string{}}

// newServer 构造一个副本。id 写进每个结果，用来看请求落在了哪台。
func newServer(id int, sc scenario) *mcp.Server {
	opts := &mcp.ServerOptions{}
	if sc.ListTTLMs > 0 {
		opts.SetCacheable = func(_ context.Context, req mcp.Request, c *mcp.Cacheable) {
			if _, ok := req.(*mcp.ListToolsRequest); ok {
				c.TTLMs, c.CacheScope = sc.ListTTLMs, "public"
			}
		}
	}
	s := mcp.NewServer(&mcp.Implementation{Name: "lab", Version: "v1"}, opts)

	mcp.AddTool(s, &mcp.Tool{Name: "whoami", Description: "返回处理本次请求的副本编号"},
		func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, map[string]any, error) {
			return nil, map[string]any{"replica": id}, nil
		})

	localCarts := map[string][]string{}
	var localMu sync.Mutex
	type cartIn struct {
		Cart string `json:"cart" jsonschema:"上一次返回的购物车句柄，首次调用留空"`
		Item string `json:"item"`
	}
	mcp.AddTool(s, &mcp.Tool{Name: "cart_add", Description: "往购物车加一件商品，返回购物车句柄和当前内容"},
		func(ctx context.Context, req *mcp.CallToolRequest, in cartIn) (*mcp.CallToolResult, map[string]any, error) {
			h := in.Cart
			if h == "" {
				h = "cart_" + base64.RawURLEncoding.EncodeToString(mustRand(6))
			}
			var items []string
			if sc.CartRepo == "shared" {
				sharedCarts.Lock()
				sharedCarts.m[h] = append(sharedCarts.m[h], in.Item)
				items = append(items, sharedCarts.m[h]...)
				sharedCarts.Unlock()
			} else {
				localMu.Lock()
				localCarts[h] = append(localCarts[h], in.Item)
				items = append(items, localCarts[h]...)
				localMu.Unlock()
			}
			return nil, map[string]any{"cart": h, "items": items, "replica": id}, nil
		})

	pending := map[string]string{} // Pending=local 时：requestState -> 分支名，只存在本副本
	var pendMu sync.Mutex
	type delIn struct {
		Branch string `json:"branch"`
	}
	mcp.AddTool(s, &mcp.Tool{Name: "delete_branch", Description: "删除远端分支，执行前要用户确认"},
		func(ctx context.Context, req *mcp.CallToolRequest, in delIn) (*mcp.CallToolResult, map[string]any, error) {
			p := req.Params
			if len(p.InputResponses) == 0 {
				var state string
				if sc.Pending == "local" {
					state = base64.RawURLEncoding.EncodeToString(mustRand(9))
					pendMu.Lock()
					pending[state] = in.Branch
					pendMu.Unlock()
				} else {
					state = sign(in.Branch, time.Now().Add(5*time.Minute))
				}
				return &mcp.CallToolResult{
					InputRequests: mcp.InputRequestMap{"confirm": &mcp.ElicitParams{
						Message:         "确认删除分支 " + in.Branch + "？",
						RequestedSchema: map[string]any{"type": "object", "properties": map[string]any{}},
					}},
					RequestState: state,
				}, nil, nil
			}
			var branch string
			var ok bool
			if sc.Pending == "local" {
				pendMu.Lock()
				branch, ok = pending[p.RequestState]
				delete(pending, p.RequestState)
				pendMu.Unlock()
			} else {
				branch, ok = verify(p.RequestState)
			}
			if !ok || branch != in.Branch {
				return nil, nil, fmt.Errorf("replica %d: unknown or expired requestState", id)
			}
			if r, _ := p.InputResponses["confirm"].(*mcp.ElicitResult); r == nil || r.Action != "accept" {
				return nil, map[string]any{"deleted": false, "replica": id}, nil
			}
			return nil, map[string]any{"deleted": true, "branch": branch, "replica": id}, nil
		})
	return s
}

// sign 把分支名和过期时间签进 requestState，任何持有密钥的副本都能验证，不需要查表。
func sign(branch string, exp time.Time) string {
	body := fmt.Sprintf("%s|%d", branch, exp.Unix())
	m := hmac.New(sha256.New, secret)
	m.Write([]byte(body))
	return base64.RawURLEncoding.EncodeToString([]byte(body)) + "." + base64.RawURLEncoding.EncodeToString(m.Sum(nil))
}

func verify(state string) (string, bool) {
	b64, mac, ok := strings.Cut(state, ".")
	if !ok {
		return "", false
	}
	body, err := base64.RawURLEncoding.DecodeString(b64)
	if err != nil {
		return "", false
	}
	m := hmac.New(sha256.New, secret)
	m.Write(body)
	want := base64.RawURLEncoding.EncodeToString(m.Sum(nil))
	if !hmac.Equal([]byte(want), []byte(mac)) {
		return "", false
	}
	branch, expS, _ := strings.Cut(string(body), "|")
	var exp int64
	fmt.Sscan(expS, &exp)
	return branch, time.Now().Unix() < exp
}

// recorder 收集代理看到的请求，写成 jsonl。
type recorder struct {
	mu   sync.Mutex
	recs []wireRec
}

func (r *recorder) add(w wireRec) {
	r.mu.Lock()
	w.Seq = len(r.recs) + 1
	r.recs = append(r.recs, w)
	r.mu.Unlock()
}

func peek(req *http.Request) (wireRec, []byte) {
	var body []byte
	if req.Body != nil {
		body, _ = io.ReadAll(req.Body)
		req.Body = io.NopCloser(bytes.NewReader(body))
	}
	w := wireRec{
		HTTPMethod: req.Method,
		HdrVersion: req.Header.Get("Mcp-Protocol-Version"),
		HdrSession: req.Header.Get("Mcp-Session-Id") != "",
		HdrMethod:  req.Header.Get("Mcp-Method"),
		HdrName:    req.Header.Get("Mcp-Name"),
		ReqBytes:   len(body),
		UserAgent:  req.Header.Get("User-Agent"),
	}
	var msg struct {
		Method string `json:"method"`
		Params struct {
			Name   string                     `json:"name"`
			Meta   map[string]json.RawMessage `json:"_meta"`
			Inputs map[string]struct {
				Action string `json:"action"`
			} `json:"inputResponses"`
		} `json:"params"`
	}
	if json.Unmarshal(body, &msg) == nil {
		w.RPCMethod, w.ToolName = msg.Method, msg.Params.Name
		var keys []string
		for k := range msg.Params.Meta {
			keys = append(keys, k)
		}
		w.MetaKeys = strings.Join(sortStrings(keys), ",")
		w.ClientCaps = string(msg.Params.Meta["io.modelcontextprotocol/clientCapabilities"])
		var acts []string
		for id, in := range msg.Params.Inputs {
			acts = append(acts, id+"="+in.Action)
		}
		w.InputActs = strings.Join(sortStrings(acts), ",")
	}
	return w, body
}

func sortStrings(s []string) []string {
	for i := range s {
		for j := i + 1; j < len(s); j++ {
			if s[j] < s[i] {
				s[i], s[j] = s[j], s[i]
			}
		}
	}
	return s
}

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (s *statusWriter) WriteHeader(c int) { s.code = c; s.ResponseWriter.WriteHeader(c) }
func (s *statusWriter) Flush() {
	if f, ok := s.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func handler(s *mcp.Server, stateless bool) http.Handler {
	return mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return s },
		&mcp.StreamableHTTPOptions{Stateless: stateless})
}

func listen(h http.Handler) (*url.URL, func()) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatal(err)
	}
	srv := &http.Server{Handler: h}
	go srv.Serve(ln)
	u, _ := url.Parse("http://" + ln.Addr().String())
	return u, func() { srv.Close() }
}

func run(sc scenario, rec *recorder) []result {
	var backends []*url.URL
	for i := range 3 {
		u, stop := listen(handler(newServer(i, sc), sc.Stateless))
		defer stop()
		backends = append(backends, u)
	}
	var rr atomic.Int64
	var owner sync.Map // sticky：会话 ID -> 创建它的副本，相当于负载均衡器的会话保持表
	proxy := &httputil.ReverseProxy{Rewrite: func(pr *httputil.ProxyRequest) {
		i := int(rr.Add(1)-1) % len(backends)
		if b, ok := owner.Load(pr.In.Header.Get("Mcp-Session-Id")); sc.Routing == "sticky" && ok {
			i = b.(int)
		}
		pr.SetURL(backends[i])
		pr.In.Header.Set("X-Lab-Backend", fmt.Sprint(i))
		pr.Out.Header.Set("X-Lab-Backend", fmt.Sprint(i))
	}, ModifyResponse: func(r *http.Response) error {
		if sid := r.Header.Get("Mcp-Session-Id"); sid != "" {
			var b int
			fmt.Sscan(r.Request.Header.Get("X-Lab-Backend"), &b)
			owner.LoadOrStore(sid, b)
		}
		return nil
	}, FlushInterval: -1}
	front, stopFront := listen(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		wr, _ := peek(r)
		sw := &statusWriter{ResponseWriter: w, code: 200}
		proxy.ServeHTTP(sw, r)
		wr.Scenario, wr.Status = sc.Name, sw.code
		fmt.Sscan(r.Header.Get("X-Lab-Backend"), &wr.Backend)
		rec.add(wr)
	}))
	defer stopFront()

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	client := mcp.NewClient(&mcp.Implementation{Name: "lab-client", Version: "v1"}, &mcp.ClientOptions{
		ElicitationHandler: func(context.Context, *mcp.ElicitRequest) (*mcp.ElicitResult, error) {
			return &mcp.ElicitResult{Action: "accept", Content: map[string]any{}}, nil
		},
	})
	res := func(op string) *result { return &result{scenario: sc, Op: op} }
	note := func(r *result, err error) {
		if err != nil {
			r.Failed++
			if r.FirstErr == "" {
				r.FirstErr = err.Error()
			}
			return
		}
		r.OK++
	}

	conn := res("connect")
	cs, err := client.Connect(ctx, &mcp.StreamableClientTransport{Endpoint: front.String()},
		&mcp.ClientSessionOptions{ProtocolVersion: sc.Version})
	note(conn, err)
	if err != nil {
		return []result{*conn}
	}
	defer cs.Close()

	list := res("tools/list x3")
	for range 3 {
		_, err := cs.ListTools(ctx, nil)
		note(list, err)
	}
	who := res("whoami")
	for range sc.Calls {
		_, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "whoami"})
		note(who, err)
	}
	cart := res("cart_add (3 items per cart)")
	for range sc.Calls / 3 {
		h := ""
		var lastErr error
		for _, item := range []string{"a", "b", "c"} {
			r, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "cart_add", Arguments: map[string]any{"cart": h, "item": item}})
			if err == nil && r.IsError {
				err = fmt.Errorf("%v", text(r))
			}
			if err != nil {
				lastErr = err
				break
			}
			sc := r.StructuredContent.(map[string]any)
			h = sc["cart"].(string)
			if item == "c" && len(sc["items"].([]any)) != 3 {
				lastErr = fmt.Errorf("cart lost items: got %v on replica %v", sc["items"], sc["replica"])
			}
		}
		note(cart, lastErr)
	}
	del := res("delete_branch (confirm)")
	for i := range sc.Calls {
		r, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "delete_branch", Arguments: map[string]any{"branch": fmt.Sprintf("feat-%d", i)}})
		if err == nil && r.IsError {
			err = fmt.Errorf("%v", text(r))
		} else if err == nil && r.StructuredContent.(map[string]any)["deleted"] != true {
			err = fmt.Errorf("not deleted: %v", r.StructuredContent)
		}
		note(del, err)
	}
	return []result{*conn, *list, *who, *cart, *del}
}

func text(r *mcp.CallToolResult) string {
	var b strings.Builder
	for _, c := range r.Content {
		if t, ok := c.(*mcp.TextContent); ok {
			b.WriteString(t.Text)
		}
	}
	return b.String()
}

func writeJSONL(path string, v any) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	switch xs := v.(type) {
	case []result:
		for _, x := range xs {
			enc.Encode(x)
		}
	case []wireRec:
		for _, x := range xs {
			enc.Encode(x)
		}
	}
}

func main() {
	serve := flag.String("serve", "", "只起一个 2026-07-28 无状态副本（同时兼容旧协议），监听这个地址")
	logPath := flag.String("log", "logs/claude-wire.jsonl", "-serve 模式下请求日志的路径")
	flag.Parse()
	os.MkdirAll("logs", 0o755)

	if *serve != "" {
		f, err := os.OpenFile(*logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
		if err != nil {
			log.Fatal(err)
		}
		enc := json.NewEncoder(f)
		enc.SetEscapeHTML(false)
		var mu sync.Mutex
		var seq int
		h := handler(newServer(0, scenario{Pending: "signed", CartRepo: "shared"}), true)
		log.Printf("serving on %s, logging to %s", *serve, *logPath)
		log.Fatal(http.ListenAndServe(*serve, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			wr, _ := peek(r)
			sw := &statusWriter{ResponseWriter: w, code: 200}
			h.ServeHTTP(sw, r)
			mu.Lock()
			seq++
			wr.Scenario, wr.Seq, wr.Status = "claude-code", seq, sw.code
			enc.Encode(wr)
			mu.Unlock()
		})))
	}

	rec := &recorder{}
	var all []result
	for _, sc := range scenarios {
		rs := run(sc, rec)
		all = append(all, rs...)
		for _, r := range rs {
			fmt.Printf("%-30s %-28s ok=%-3d failed=%-3d %s\n", sc.Name, r.Op, r.OK, r.Failed, trim(r.FirstErr))
		}
	}
	writeJSONL("logs/scenarios.jsonl", all)
	writeJSONL("logs/wire.jsonl", rec.recs)
}

func trim(s string) string {
	if len(s) > 110 {
		return s[:110] + "…"
	}
	return s
}
