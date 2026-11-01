// Package codingworker adapts GoAgent Harness to the Super-agent task manager.
// It deliberately supports only the embedded CSV fixture, not arbitrary repos.
package codingworker

import (
	"context"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	example "github.com/costa92/blog-go-example/superagent"
	"github.com/kart-io/goagent-harness/preset"
	"github.com/kart-io/goagent/builder"
	"github.com/kart-io/goagent/core/budget"
	"github.com/kart-io/goagent/core/durable"
	"github.com/kart-io/goagent/harness/env"
	"github.com/kart-io/goagent/interfaces"
	"github.com/kart-io/goagent/tools"
	"github.com/kart-io/goagent/workflow"
	"gopkg.in/yaml.v3"
)

//go:embed testdata/csvbug/*
var fixture embed.FS

const TestCommand = "go test -count=1 ./..."
const DefaultImage = "golang:1.26.6-alpine"

var files = []string{"go.mod", "export.go", "export_test.go"}

type Config struct {
	Root     string
	Store    durable.Store
	Models   example.ModelFactory
	Executor string
	Image    string
	ModelID  string
}
type Runner struct{ cfg Config }

func New(cfg Config) (*Runner, error) {
	if cfg.Store == nil || cfg.Models == nil || cfg.Root == "" || cfg.ModelID == "" {
		return nil, errors.New("root, store, model factory and model ID are required")
	}
	if cfg.Executor != "docker" && cfg.Executor != "local" {
		return nil, errors.New("executor must be docker or explicitly local")
	}
	if cfg.Executor == "docker" && cfg.Image == "" {
		return nil, errors.New("Docker image is required")
	}
	if cfg.Executor == "local" {
		cfg.Image = ""
	}
	var err error
	cfg.Root, err = filepath.Abs(cfg.Root)
	if err != nil {
		return nil, err
	}
	return &Runner{cfg: cfg}, nil
}
func hash(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }
func (r *Runner) workspace(id string) string {
	return filepath.Join(r.cfg.Root, "workspaces", hash([]byte(id))[:24])
}
func (r *Runner) executor(root string) env.Executor {
	if r.cfg.Executor == "docker" {
		return env.DockerExecutor{Root: root, Image: r.cfg.Image}
	}
	return env.LocalExecutor{Root: root}
}
func fixtureFile(name string) []byte {
	if name == "go.mod" {
		name = "go.mod.txt"
	}
	b, err := fixture.ReadFile("testdata/csvbug/" + name)
	if err != nil {
		panic(err)
	}
	return b
}
func regular(path string) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("expected regular file: %s", path)
	}
	return os.ReadFile(path)
}
func (r *Runner) seed(root string) error {
	if err := os.MkdirAll(root, 0700); err != nil {
		return err
	}
	info, err := os.Lstat(root)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("workspace must be a real directory")
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return err
	}
	if len(entries) != 0 {
		return nil
	} // Validation below rejects foreign or partial workspaces.
	for _, name := range files {
		if err = os.WriteFile(filepath.Join(root, name), fixtureFile(name), 0600); err != nil {
			return err
		}
	}
	return nil
}
func checkProtected(root string) error {
	entries, err := os.ReadDir(root)
	if err != nil {
		return err
	}
	if len(entries) != len(files) {
		return errors.New("fixture contains unexpected or missing files")
	}
	for _, name := range files {
		b, err := regular(filepath.Join(root, name))
		if err != nil {
			return err
		}
		if name != "export.go" && hash(b) != hash(fixtureFile(name)) {
			return fmt.Errorf("protected fixture file changed: %s", name)
		}
	}
	return nil
}
func (r *Runner) test(ctx context.Context, root string) (env.Result, error) {
	ctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	return r.executor(root).Run(ctx, env.Command{Argv: []string{"go", "test", "-count=1", "./..."}})
}
func authorize(_ context.Context, name string, in *interfaces.ToolInput) error {
	denied := errors.New("CSV fixture policy: only reading fixture files, editing export.go and the exact test command are allowed")
	if in == nil {
		return denied
	}
	switch name {
	case "read_file":
		p, _ := in.Args["path"].(string)
		for _, name := range files {
			if p == name {
				return nil
			}
		}
	case "edit_file":
		if in.Args["path"] == "export.go" {
			return nil
		}
	case "run_command":
		dir, _ := in.Args["work_dir"].(string)
		if in.Args["command"] == TestCommand && (dir == "" || dir == ".") {
			return nil
		}
	}
	return denied
}
func (r *Runner) assembly(ctx context.Context, root string, onResult func(context.Context, tools.DispatchResult) error) (*preset.Assembly, error) {
	workspace := map[string]any{"sandbox": "workspace-write", "executor": "docker", "image": r.cfg.Image, "network": false, "commandTimeout": "90s"}
	if r.cfg.Executor == "local" {
		workspace = map[string]any{"sandbox": "danger-full-access", "executor": "local", "network": true, "commandTimeout": "90s"}
	}
	doc := map[string]any{"presets": []any{map[string]any{"id": "csv-worker", "components": []any{
		map[string]any{"id": "persona", "use": "persona", "config": map[string]any{"prompt": "你是 CSV 修复 Worker。先运行 go test -count=1 ./... 复现失败，再读取 export.go 和测试，修复 CSV 空输出。只允许编辑 export.go；不能修改或删除测试，不能提交或推送。修改后重跑固定测试命令，再汇报真实结果。不要声称已人工验收。"}},
		map[string]any{"id": "workspace", "use": "workspace", "config": workspace},
		map[string]any{"id": "coding", "use": "coding-tools", "config": map[string]any{"tools": []string{"read_file", "edit_file", "run_command"}}},
		map[string]any{"id": "permissions", "use": "permissions", "config": map[string]any{"base": "coding"}},
	}}}}
	data, err := yaml.Marshal(doc)
	if err != nil {
		return nil, err
	}
	set, err := preset.Load(preset.Source{Layer: preset.LayerHost, Path: "superagent/csv-worker-v1", Trusted: true, Data: data})
	if err != nil {
		return nil, err
	}
	p, ok := set.Get("csv-worker")
	if !ok {
		return nil, errors.New("missing CSV preset")
	}
	return preset.Build(ctx, p, preset.Host{Root: root, ArtifactDir: filepath.Join(r.cfg.Root, "artifacts"), Dispatch: tools.DispatchConfig{Authorize: authorize, OnResult: onResult, MaxConcurrency: 1},
		// The task host preauthorizes exactly this fixture test, never arbitrary commands.
		Approver: tools.ApproverFunc(func(_ context.Context, req tools.ApprovalRequest) (tools.ApprovalResult, error) {
			if req.Call.Tool == "run_command" && req.Call.Args["command"] == TestCommand {
				return tools.ApprovalResult{Outcome: tools.ApprovalAllowedOnce}, nil
			}
			return tools.ApprovalResult{Outcome: tools.ApprovalRejected, Feedback: "outside fixed CSV task"}, nil
		}),
	})
}

type graphState struct {
	Prompt string
	Result string
	Tools  []string
}
type baseline struct{ Output string }

func (r *Runner) Run(ctx context.Context, id, prompt string) (out example.Evidence, err error) {
	var task struct{ Mandate string }
	if json.Unmarshal([]byte(prompt), &task) != nil || task.Mandate != "csv-export" {
		return out, errors.New("Harness example only accepts the csv-export fixture mandate")
	}
	if !strings.HasPrefix(id, "worker/") {
		return out, errors.New("invalid worker run ID")
	}
	key := "csv-workspace/" + id
	unlock, err := r.cfg.Store.Lock(ctx, key)
	if err != nil {
		return out, err
	}
	defer func() { err = errors.Join(err, unlock()) }()
	root := r.workspace(id)
	if err = r.seed(root); err != nil {
		return out, err
	}
	if err = checkProtected(root); err != nil {
		return out, err
	}
	cp, loadErr := r.cfg.Store.Load(ctx, key)
	var before baseline
	if errors.Is(loadErr, os.ErrNotExist) {
		original, err := regular(filepath.Join(root, "export.go"))
		if err != nil {
			return out, err
		}
		if hash(original) != hash(fixtureFile("export.go")) {
			return out, errors.New("new fixture source differs from the baseline")
		}
		red, err := r.test(ctx, root)
		if err != nil {
			return out, err
		}
		if red.ExitCode == 0 || !strings.Contains(string(red.Output), "TestExportRows") {
			return out, fmt.Errorf("baseline did not reproduce the CSV regression (for Docker, state-dir must be shared with the daemon): %s", red.Output)
		}
		before.Output = string(red.Output)
		data, _ := json.Marshal(before)
		if err = r.cfg.Store.Save(ctx, key, &durable.Snapshot{Version: "csv-baseline-v1", RunID: key, Data: data}); err != nil {
			return out, err
		}
	} else if loadErr != nil {
		return out, loadErr
	} else {
		if cp.Version != "csv-baseline-v1" {
			return out, errors.New("baseline version changed")
		}
		if err = json.Unmarshal(cp.Data, &before); err != nil {
			return out, err
		}
	}
	var names []string
	asm, err := r.assembly(ctx, root, func(_ context.Context, result tools.DispatchResult) error {
		names = append(names, result.Name)
		return nil
	})
	if err != nil {
		return out, err
	}
	defer func() { err = errors.Join(err, asm.Close()) }()
	graph := workflow.NewGraph[graphState](workflow.Config{MaxSteps: 3, MaxConcurrency: 1})
	err = graph.AddNode("code", func(ctx context.Context, s graphState) (graphState, error) {
		if err := asm.PinManifest(ctx); err != nil {
			return s, err
		}
		controller, err := budget.NewDurable(budget.Config{RootKey: "coding/" + id, Version: "v1", MaxModelRequests: 12}, r.cfg.Store)
		if err != nil {
			return s, err
		}
		ctx = budget.WithController(ctx, controller)
		client, err := r.cfg.Models("worker", id)
		if err != nil {
			return s, err
		}
		agent, err := preset.Configure(builder.NewSimpleBuilder(client), asm).WithAgentID("csv-worker").WithSessionID(id).WithDurableScope("csv-worker").WithMaxIterations(10).WithTimeout(3 * time.Minute).Build()
		if err != nil {
			return s, err
		}
		result, err := agent.AsRunnable().Invoke(ctx, s.Prompt)
		if err != nil {
			return s, err
		}
		text, ok := result.Result.(string)
		if !ok || text == "" {
			return s, errors.New("worker returned no summary")
		}
		s.Result = text
		s.Tools = append([]string(nil), names...)
		return s, nil
	})
	if err != nil {
		return out, err
	}
	if err = graph.AddEdge(workflow.START, "code"); err != nil {
		return out, err
	}
	if err = graph.AddEdge("code", workflow.END); err != nil {
		return out, err
	}
	version := "csv-worker-v1/" + r.cfg.ModelID + "/" + asm.Manifest.Digest()
	compiled, err := graph.CompileDurable(ctx, workflow.DurableConfig{Store: r.cfg.Store, Version: version})
	if err != nil {
		return out, err
	}
	saved, err := compiled.AsRunnable().Invoke(ctx, workflow.RunRequest[graphState]{RunID: "coding/" + id, Initial: graphState{Prompt: prompt}})
	if err != nil {
		return out, err
	}
	if err = checkProtected(root); err != nil {
		return out, err
	}
	source, err := regular(filepath.Join(root, "export.go"))
	if err != nil {
		return out, err
	}
	out = example.Evidence{RunID: id, Summary: saved.State.Result, Workspace: root, BeforeTests: before.Output, SourceSHA256: hash(source), Executor: r.cfg.Executor, Image: r.cfg.Image, Tools: saved.State.Tools}
	if out.TestOutput, err = r.verify(ctx, out); err != nil {
		return example.Evidence{}, err
	}
	original, err := os.CreateTemp(r.cfg.Root, "csv-baseline-*.go")
	if err != nil {
		return out, err
	}
	name := original.Name()
	defer os.Remove(name)
	if _, err = original.Write(fixtureFile("export.go")); err != nil {
		_ = original.Close()
		return out, err
	}
	if err = original.Close(); err != nil {
		return out, err
	}
	command := exec.CommandContext(ctx, "git", "diff", "--no-index", "--no-ext-diff", "--no-textconv", "--", name, filepath.Join(root, "export.go"))
	diff, diffErr := command.CombinedOutput()
	var exit *exec.ExitError
	if diffErr != nil && (!errors.As(diffErr, &exit) || exit.ExitCode() != 1) {
		return out, fmt.Errorf("diff failed: %w", diffErr)
	}
	out.Diff = string(diff)
	if out.Diff == "" {
		return out, errors.New("worker did not change the broken source")
	}
	return out, nil
}
func (r *Runner) verify(ctx context.Context, out example.Evidence) (string, error) {
	if out.Workspace != r.workspace(out.RunID) || (out.Executor != r.cfg.Executor || out.Image != r.cfg.Image) {
		return "", errors.New("coding evidence belongs to a different workspace or executor")
	}
	if err := checkProtected(out.Workspace); err != nil {
		return "", err
	}
	source, err := regular(filepath.Join(out.Workspace, "export.go"))
	if err != nil {
		return "", err
	}
	if hash(source) != out.SourceSHA256 {
		return "", errors.New("source changed after the evidence was recorded")
	}
	result, err := r.test(ctx, out.Workspace)
	if err != nil {
		return "", err
	}
	if result.ExitCode != 0 {
		return "", fmt.Errorf("host verification rejected the worker result: %s", result.Output)
	}
	if err = checkProtected(out.Workspace); err != nil {
		return "", err
	}
	source, err = regular(filepath.Join(out.Workspace, "export.go"))
	if err != nil || hash(source) != out.SourceSHA256 {
		return "", errors.New("source changed while tests were running")
	}
	return string(result.Output), nil
}
func (r *Runner) Verify(ctx context.Context, out example.Evidence) (err error) {
	unlock, err := r.cfg.Store.Lock(ctx, "csv-workspace/"+out.RunID)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, unlock()) }()
	_, err = r.verify(ctx, out)
	return err
}
