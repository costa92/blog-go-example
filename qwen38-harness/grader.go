package main

import (
	"bytes"
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// All acceptance tests and references stay out of the agent working directory.
// They are public teaching fixtures, not secret or adversarially isolated tests.
//
//go:embed tasks
var taskFiles embed.FS

var taskIDs = []string{"bytesize", "retry-delay", "csv-record"}

const taskModule = "module exercise\n\ngo 1.25.0\n"

func asset(task, file string) []byte {
	b, err := taskFiles.ReadFile("tasks/" + task + "/" + file)
	if err != nil {
		panic(err) // Fixed embedded assets; a packaging error, not model input.
	}
	return b
}

func writeFile(path string, data []byte) error { return os.WriteFile(path, data, 0600) }

func prepareTask(dir, task string) error {
	for name, data := range map[string][]byte{
		"go.mod": []byte(taskModule), "TASK.md": asset(task, "prompt.md"),
		"solution.go": asset(task, "solution.go.txt"), "solution_test.go": asset(task, "visible_test.go.txt"),
	} {
		if err := writeFile(filepath.Join(dir, name), data); err != nil {
			return err
		}
	}
	return nil
}

func replaceEnv(base []string, values map[string]string) []string {
	out := make([]string, 0, len(base)+len(values))
	for _, entry := range base {
		key, _, _ := strings.Cut(entry, "=")
		if _, replaced := values[key]; !replaced {
			out = append(out, entry)
		}
	}
	for key, value := range values {
		out = append(out, key+"="+value)
	}
	return out
}

// macOS/Linux: only the process group created for this command is cancelled.
// A shell tool may have child processes; killing only Pi would leave them alive.
func ownedCommand(ctx context.Context, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return os.ErrProcessDone
		}
		// Let Pi's SIGTERM handler clean up its tracked detached tools too.
		err := syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
		if err == syscall.ESRCH {
			return os.ErrProcessDone
		}
		return err
	}
	cmd.WaitDelay = 2 * time.Second
	return cmd
}

type Grade struct {
	Passed bool   `json:"passed"`
	Status string `json:"status"`
	Log    string `json:"-"`
}

func gradeSource(ctx context.Context, task string, source []byte) Grade {
	dir, err := os.MkdirTemp("", "harness-grade-")
	if err != nil {
		return Grade{Status: "grader_error", Log: err.Error()}
	}
	defer os.RemoveAll(dir)
	for name, data := range map[string][]byte{
		"go.mod": []byte(taskModule), "solution.go": source,
		"acceptance_test.go": asset(task, "acceptance_test.go.txt"),
	} {
		if err := writeFile(filepath.Join(dir, name), data); err != nil {
			return Grade{Status: "grader_error", Log: err.Error()}
		}
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	cmd := ownedCommand(ctx, "go", "test", "-json", "-count=1", "-timeout=10s", ".")
	cmd.Dir = dir
	cmd.Env = replaceEnv(os.Environ(), map[string]string{
		"GOWORK": "off", "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0",
	})
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err = cmd.Run()
	result := Grade{Status: "failed", Log: stdout.String() + stderr.String()}
	if ctx.Err() != nil {
		result.Status = "timeout"
		return result
	}
	if err != nil {
		if _, ok := err.(*exec.ExitError); !ok {
			result.Status = "grader_error"
		}
		return result
	}
	// Exit 0 alone is insufficient: the expected test must actually run and pass.
	var testPassed, packagePassed bool
	decoder := json.NewDecoder(&stdout)
	for {
		var event struct{ Action, Test string }
		err := decoder.Decode(&event)
		if err == io.EOF {
			break
		}
		if err != nil {
			return Grade{Status: "grader_error", Log: "invalid go test JSON output"}
		}
		if event.Action == "pass" {
			testPassed = testPassed || event.Test == "TestAcceptance"
			packagePassed = packagePassed || event.Test == ""
		}
	}
	if testPassed && packagePassed {
		result.Passed, result.Status = true, "passed"
	}
	return result
}

func readSolution(dir string) ([]byte, error) {
	p := filepath.Join(dir, "solution.go")
	info, err := os.Lstat(p)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > 1<<20 {
		return nil, fmt.Errorf("solution.go must be a regular file, at most 1 MiB")
	}
	return os.ReadFile(p)
}
