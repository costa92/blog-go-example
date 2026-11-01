// Command superagent runs the article's local coordination example.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	example "github.com/costa92/blog-go-example/superagent"
	"github.com/costa92/blog-go-example/superagent/codingworker"
	"github.com/kart-io/goagent/core/durable"
	"github.com/kart-io/goagent/llm"
	"github.com/kart-io/goagent/llm/providers"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	mode := flag.String("mode", "demo", "demo | coding-demo | event | work | deliver | status | review | accept")
	dir := flag.String("state-dir", ".superagent", "local checkpoints and demo receiver directory")
	file := flag.String("event", "", "trusted local Event JSON file for event mode")
	ticket := flag.String("ticket", "", "ticket ID for local human accept mode")
	live := flag.Bool("live", false, "use configured OpenAI-compatible model; never falls back to offline")
	intake := flag.String("intake", "observe", "observe | auto")
	workers := flag.Int("workers", 2, "maximum concurrently running worker calls")
	coding := flag.Bool("coding", false, "execute the CSV fixture with GoAgent Harness")
	executor := flag.String("coding-executor", "docker", "docker (default) | local (offline scripted fixture only)")
	image := flag.String("coding-image", codingworker.DefaultImage, "Go Docker image for isolated test execution")
	flag.Parse()
	if *mode == "coding-demo" {
		*coding = true
		*mode = "demo"
	}
	if *live && *coding && *executor != "docker" {
		return errors.New("live coding requires the Docker executor")
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	timeout := 3 * time.Minute
	if *coding {
		timeout = 10 * time.Minute
	}
	ctx, cancelTimeout := context.WithTimeout(ctx, timeout)
	defer cancelTimeout()
	factory := example.ModelFactory(example.OfflineFactory)
	modelID := "offline-csv-script-v1"
	if *coding {
		factory = codingworker.ScriptFactory
	}
	if *live {
		key, base, model := os.Getenv("GOAGENT_API_KEY"), os.Getenv("GOAGENT_BASE_URL"), os.Getenv("GOAGENT_MODEL")
		if key == "" || base == "" || model == "" {
			return errors.New("live mode requires GOAGENT_API_KEY, GOAGENT_BASE_URL and GOAGENT_MODEL")
		}
		modelID = fmt.Sprintf("openai-compatible/%x", sha256.Sum256([]byte(base+"\x00"+model)))
		factory = func(_, _ string) (llm.Client, error) {
			return providers.NewOpenAIWithOptions(llm.WithAPIKey(key), llm.WithBaseURL(base), llm.WithModel(model), llm.WithMaxTokens(800), llm.WithTimeout(45*time.Second))
		}
	}
	st, err := durable.NewFileStore(filepath.Join(*dir, "engine"))
	if err != nil {
		return err
	}
	cfg := example.Config{Store: st, Models: factory, MaxWorkers: *workers, Mode: example.Mode(*intake), AutoScopes: []string{"csv-export"}}
	if *coding {
		cfg.Worker, err = codingworker.New(codingworker.Config{Root: filepath.Join(*dir, "coding"), Store: st, Models: factory, Executor: *executor, Image: *image, ModelID: modelID})
		if err != nil {
			return err
		}
	}
	e, err := example.New(cfg)
	if err != nil {
		return err
	}
	remote, err := durable.NewFileStore(filepath.Join(*dir, "demo-receiver"))
	if err != nil {
		return err
	}
	receiver := &example.DemoReceiver{Store: remote}
	switch *mode {
	case "demo":
		s, err := e.Snapshot(ctx)
		if err != nil {
			return err
		}
		if len(s.Events) != 0 {
			return errors.New("demo requires a fresh state directory; use event/work/deliver/status for existing state")
		}
		if *live {
			fmt.Println("model mode: live API; notification receiver remains a local simulator")
		} else {
			fmt.Println("model mode: offline scripted responses")
		}
		events := []example.Event{
			{ID: "csv-request", Thread: "issue/csv", Scope: "csv-export", Text: "检查 CSV 空导出问题并给出回归测试方案", Actor: example.Human, Authorized: true, Explicit: true},
			{ID: "docs-request", Thread: "issue/docs", Scope: "docs", Text: "为导出接口补使用说明方案", Actor: example.Human, Authorized: true, Explicit: true},
			{ID: "review", Thread: "issue/csv", Scope: "csv-export", Text: "补充空输入的边界用例", Actor: example.Human, Authorized: true},
			{ID: "ci", Thread: "issue/csv", Scope: "csv-export", Text: "CI 提供检查结果上下文", Actor: example.Bot, Authorized: true},
			{ID: "expanded-scope", Thread: "issue/csv", Scope: "auth", Text: "顺便重写认证模块", Actor: example.Human, Authorized: true, Explicit: true},
		}
		if *coding {
			filtered := make([]example.Event, 0, len(events))
			for _, ev := range events {
				if ev.ID != "docs-request" {
					if ev.ID == "csv-request" {
						ev.Text = "修复 CSV 空输出，保留原有测试并执行回归验证"
					}
					filtered = append(filtered, ev)
				}
			}
			events = filtered
		}
		for _, ev := range events {
			r, err := e.Handle(ctx, ev)
			if err != nil {
				return err
			}
			fmt.Printf("event=%s route=", ev.ID)
			if err = printJSON(r); err != nil {
				return err
			}
		}
		if err = e.RunPending(ctx); err != nil {
			return err
		}
		receiver.FailFirst = true
		if err = e.Deliver(ctx, receiver, time.Now()); err != nil {
			if !errors.Is(err, example.ErrSimulatedTimeout) {
				return err
			}
			fmt.Println("notification remains pending:", err)
		}
		fmt.Println("restart with -mode deliver after the retry delay; this only retries notifications")
	case "event":
		f, err := os.Open(*file)
		if err != nil {
			return err
		}
		defer f.Close()
		dec := json.NewDecoder(io.LimitReader(f, 1<<20))
		dec.DisallowUnknownFields()
		var ev example.Event
		if err = dec.Decode(&ev); err != nil {
			return err
		}
		var extra any
		if err = dec.Decode(&extra); err != io.EOF {
			return errors.New("event file must contain one JSON object")
		}
		r, err := e.Handle(ctx, ev)
		if err != nil {
			return err
		}
		return printJSON(r)
	case "work":
		if err = e.RunPending(ctx); err != nil {
			return err
		}
	case "deliver":
		if err = e.Deliver(ctx, receiver, time.Now()); err != nil {
			return err
		}
	case "review":
		state, err := e.Snapshot(ctx)
		if err != nil {
			return err
		}
		task, ok := state.Tickets[*ticket]
		if !ok || task.Evidence == nil {
			return errors.New("coding ticket with evidence is required")
		}
		proof := task.Evidence
		fmt.Printf("Ticket: %s (%s)\nWorkspace: %s\nSource SHA-256: %s\n\nModel summary:\n%s\n\nOriginal failing tests:\n%s\nHost verification:\n%s\nDiff to review:\n%s\n", task.ID, task.Status, proof.Workspace, proof.SourceSHA256, proof.Summary, proof.BeforeTests, proof.TestOutput, proof.Diff)
		return nil
	case "accept":
		// This is a trusted local command, not an authenticated web endpoint.
		if err = e.Accept(ctx, *ticket, true); err != nil {
			return err
		}
	case "status":
	default:
		return errors.New("unknown mode")
	}
	s, err := e.Snapshot(ctx)
	if err != nil {
		return err
	}
	receipts, err := receiver.Receipts(ctx)
	if err != nil {
		return err
	}
	return printJSON(struct {
		State          example.State              `json:"state"`
		RemoteReceipts map[string]example.Message `json:"demo_remote_receipts"`
	}{s, receipts})
}
func printJSON(v any) error {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}
