package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRunTrialDoesNotTrustExitCode(t *testing.T) {
	for _, tc := range []struct{ name, script string }{
		{"model-error", `printf '%s\n' '{"type":"message_end","message":{"role":"assistant","stopReason":"error"}}' '{"type":"agent_settled","aborted":false}'`},
		{"invalid-json", `printf '%s\n' 'not JSON'`},
		{"empty-stream", `exit 0`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "pi-fixture")
			if err := os.WriteFile(path, []byte("#!/bin/sh\n"+tc.script+"\n"), 0700); err != nil {
				t.Fatal(err)
			}
			trial := runTrial(context.Background(), Config{Pi: path, Timeout: time.Second}, "bytesize", "base", "fixture", 1, t.TempDir())
			if trial.Scorable || trial.Passed || trial.Status != "agent_error" {
				t.Fatalf("invalid model run was scored: %+v", trial)
			}
		})
	}
}

func TestTimeoutKeepsPartialUsageUnknown(t *testing.T) {
	path := filepath.Join(t.TempDir(), "pi-fixture")
	script := `#!/bin/sh
printf '%s\n' '{"type":"message_end","message":{"role":"assistant","stopReason":"toolUse","usage":{"input":10,"output":5}}}'
sleep 10
`
	if err := os.WriteFile(path, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	trial := runTrial(context.Background(), Config{Pi: path, Timeout: 100 * time.Millisecond}, "bytesize", "base", "fixture", 1, t.TempDir())
	if trial.Status != "timeout" || !trial.Scorable || trial.Passed || trial.Metrics.GeneratedTokens != nil {
		t.Fatalf("bad timeout accounting: %+v", trial)
	}
	if time.Since(start) > 5*time.Second {
		t.Fatal("owned child process was not cancelled promptly")
	}
}
