package codingworker

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	example "github.com/costa92/blog-go-example/superagent"
	"github.com/kart-io/goagent/core/durable"
	"github.com/kart-io/goagent/interfaces"
	"github.com/kart-io/goagent/llm"
)

const request = `{"Mandate":"csv-export","Inputs":[{"text":"修复 CSV 空输出，保留测试并验证"}]}`

func makeRunner(t *testing.T, root string, factory example.ModelFactory, executor, image string) *Runner {
	t.Helper()
	st, err := durable.NewFileStore(filepath.Join(root, "journal"))
	if err != nil {
		t.Fatal(err)
	}
	r, err := New(Config{Root: root, Store: st, Models: factory, Executor: executor, Image: image, ModelID: "offline-script-v1"})
	if err != nil {
		t.Fatal(err)
	}
	return r
}
func TestHarnessRepairsCSVAndReplaysCompletedGraph(t *testing.T) {
	root := t.TempDir()
	var calls atomic.Int32
	factory := func(role, id string) (llm.Client, error) {
		m := NewScriptModel()
		m.OnRequest = func() { calls.Add(1) }
		return m, nil
	}
	r := makeRunner(t, root, factory, "local", "")
	ctx := context.Background()
	out, err := r.Run(ctx, "worker/ticket-one/1", request)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.BeforeTests, "TestExportRows") || !strings.Contains(out.TestOutput, "ok") || !strings.Contains(out.Diff, "+\twriter.Flush()") {
		t.Fatalf("missing real repair evidence: %+v", out)
	}
	if calls.Load() < 4 {
		t.Fatal("script did not execute the harness tool loop")
	}
	before := calls.Load()
	reopened := makeRunner(t, root, factory, "local", "")
	again, err := reopened.Run(ctx, "worker/ticket-one/1", request)
	if err != nil {
		t.Fatal(err)
	}
	if calls.Load() != before || again.SourceSHA256 != out.SourceSHA256 {
		t.Fatal("completed graph repeated model/tool calls")
	}
	if err = r.Verify(ctx, out); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(out.Workspace, "export.go")
	data, _ := os.ReadFile(path)
	if err = os.WriteFile(path, append(data, []byte("\n// edited after review\n")...), 0600); err != nil {
		t.Fatal(err)
	}
	if err = r.Verify(ctx, out); err == nil {
		t.Fatal("stale evidence accepted")
	}
}
func TestHostRejectsModelSuccessWithoutRepair(t *testing.T) {
	factory := func(_, _ string) (llm.Client, error) { return &noRepairModel{ScriptModel: NewScriptModel()}, nil }
	r := makeRunner(t, t.TempDir(), factory, "local", "")
	if _, err := r.Run(context.Background(), "worker/false-success/1", request); err == nil || !strings.Contains(err.Error(), "host verification") {
		t.Fatal("model text replaced independent verification")
	}
}
func TestPolicyRejectsScopeAndCommands(t *testing.T) {
	for _, tc := range []struct {
		name string
		args map[string]any
	}{
		{"edit_file", map[string]any{"path": "export_test.go"}},
		{"edit_file", map[string]any{"path": "../outside.go"}},
		{"run_command", map[string]any{"command": "go test -exec sh ./..."}},
		{"run_command", map[string]any{"command": TestCommand + "; echo injected"}},
		{"run_command", map[string]any{"command": TestCommand, "work_dir": ".."}},
		{"write_file", map[string]any{"path": "export.go"}},
	} {
		if err := authorize(context.Background(), tc.name, &interfaces.ToolInput{Args: tc.args}); err == nil {
			t.Fatalf("allowed %s: %v", tc.name, tc.args)
		}
	}
	if err := authorize(context.Background(), "run_command", &interfaces.ToolInput{Args: map[string]any{"command": TestCommand}}); err != nil {
		t.Fatal(err)
	}
	r := makeRunner(t, t.TempDir(), ScriptFactory, "local", "")
	if _, err := r.Run(context.Background(), "worker/scope/1", `{"Mandate":"auth-rewrite"}`); err == nil {
		t.Fatal("expanded scope accepted")
	}
}
func TestAcceptanceChecksSavedCodingEvidence(t *testing.T) {
	root := t.TempDir()
	r := makeRunner(t, root, ScriptFactory, "local", "")
	st, _ := durable.NewFileStore(filepath.Join(root, "journal"))
	e, err := example.New(example.Config{Store: st, Models: example.OfflineFactory, MaxWorkers: 1, Mode: example.Observe, Worker: r})
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	route, err := e.Handle(ctx, example.Event{ID: "csv", Thread: "issue/csv", Text: "修复 CSV 导出", Scope: "csv-export", Actor: example.Human, Authorized: true, Explicit: true})
	if err != nil {
		t.Fatal(err)
	}
	plain, _ := example.New(example.Config{Store: st, Models: example.OfflineFactory, MaxWorkers: 1, Mode: example.Observe})
	if err = plain.RunPending(ctx); err == nil {
		t.Fatal("coding task silently downgraded to a plan")
	}
	if err = e.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	s, _ := e.Snapshot(ctx)
	ticket := s.Tickets[route.Created]
	if ticket.Evidence == nil || ticket.Status != example.Ready {
		t.Fatal("missing reviewable coding result")
	}
	path := filepath.Join(ticket.Evidence.Workspace, "export_test.go")
	original, _ := os.ReadFile(path)
	_ = os.WriteFile(path, []byte("package csvbug\n"), 0600)
	if err = e.Accept(ctx, route.Created, true); err == nil {
		t.Fatal("modified test suite accepted")
	}
	_ = os.WriteFile(path, original, 0600)
	if err = e.Accept(ctx, route.Created, true); err != nil {
		t.Fatal(err)
	}
}
func TestDockerCodingLoop(t *testing.T) {
	image := os.Getenv("SUPERAGENT_TEST_DOCKER_IMAGE")
	if image == "" {
		t.Skip("set SUPERAGENT_TEST_DOCKER_IMAGE to run isolated container execution")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatal(err)
	}
	root, err := os.MkdirTemp(home, ".superagent-docker-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(root) })
	r := makeRunner(t, root, ScriptFactory, "docker", image)
	out, err := r.Run(context.Background(), "worker/docker/1", request)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.TestOutput, "ok") || out.Executor != "docker" {
		t.Fatalf("docker result: %+v", out)
	}
}

type noRepairModel struct{ *ScriptModel }

func (m *noRepairModel) CompleteToolsStream(context.Context, *llm.CompletionRequest, []interfaces.Tool) (<-chan *llm.StreamChunk, error) {
	ch := make(chan *llm.StreamChunk, 1)
	ch <- &llm.StreamChunk{Content: "已经修好", Delta: "已经修好", Done: true, FinishReason: "stop"}
	close(ch)
	return ch, nil
}
