package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestServingScriptPreservesPathsAndControls(t *testing.T) {
	bin := filepath.Join(t.TempDir(), "vllm-fixture")
	if err := os.WriteFile(bin, []byte("#!/bin/sh\nprintf '%s\\n' \"$@\"\n"), 0700); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("bash", "serve-vllm.sh")
	cmd.Env = replaceEnv(os.Environ(), map[string]string{"HARNESS_VLLM_BIN": bin, "HARNESS_BASE_MODEL": "/tmp/base with spaces", "HARNESS_PI_ADAPTER": "/tmp/adapter with spaces"})
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("%v: %s", err, out)
	}
	args := strings.Split(strings.TrimSpace(string(out)), "\n")
	want := map[string]string{"--served-model-name": "qwen-base", "--lora-modules": "qwen-pi=/tmp/adapter with spaces", "--max-lora-rank": "32", "--tool-call-parser": "qwen3_xml", "--default-chat-template-kwargs": `{"enable_thinking": false}`, "--max-model-len": "131072", "--max-num-seqs": "1"}
	if args[0] != "serve" || args[1] != "/tmp/base with spaces" {
		t.Fatalf("bad base path: %q", args)
	}
	for i := 2; i < len(args)-1; i++ {
		if v, ok := want[args[i]]; ok {
			if args[i+1] != v {
				t.Fatalf("%s: got %q", args[i], args[i+1])
			}
			delete(want, args[i])
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing controls: %v", want)
	}
}
