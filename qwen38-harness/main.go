package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func selfcheck(ctx context.Context, out io.Writer) error {
	for _, task := range taskIDs {
		bad := gradeSource(ctx, task, asset(task, "solution.go.txt"))
		good := gradeSource(ctx, task, asset(task, "reference.go.txt"))
		if bad.Passed || !good.Passed || bad.Status != "failed" {
			return fmt.Errorf("%s: unexpected grader result: buggy=%s reference=%s\n%s\n%s", task, bad.Status, good.Status, bad.Log, good.Log)
		}
		fmt.Fprintf(out, "%s: buggy=rejected reference=accepted\n", task)
	}
	fmt.Fprintln(out, "selfcheck passed: 3 graders checked; no Pi or model invoked")
	return nil
}

func execute(ctx context.Context, args []string, out io.Writer) error {
	if len(args) == 0 {
		return errors.New("usage: go run . selfcheck | run [flags] | summarize results.json | regrade [flags]")
	}
	switch args[0] {
	case "selfcheck":
		return selfcheck(ctx, out)
	case "summarize":
		if len(args) < 2 {
			return errors.New("usage: go run . summarize results.json [more-results.json ...]")
		}
		var trials []Trial
		seen := map[string]bool{}
		models, hashes := map[string]string{}, map[string]string{}
		harnesses := map[string]bool{}
		for _, path := range args[1:] {
			b, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			var part []Trial
			if err := json.Unmarshal(b, &part); err != nil {
				return err
			}
			for _, trial := range part {
				harness := trial.Harness
				if harness == "" {
					harness = "pi"
				}
				harnesses[harness] = true
				if len(harnesses) > 1 {
					return errors.New("different harnesses must be summarized separately")
				}
				key := fmt.Sprintf("%s/%d/%s", trial.Task, trial.Repetition, trial.Condition)
				if seen[key] {
					return fmt.Errorf("duplicate trial %s; do not select among repeated outcomes", key)
				}
				seen[key] = true
				if old := models[trial.Condition]; old != "" && old != trial.Model {
					return errors.New("different models mixed in one condition")
				}
				models[trial.Condition] = trial.Model
				h := trial.TaskHash + "/" + trial.PromptHash
				if old := hashes[trial.Task]; old != "" && old != h {
					return errors.New("different task or prompt hashes mixed")
				}
				hashes[trial.Task] = h
			}
			trials = append(trials, part...)
		}
		encoder := json.NewEncoder(out)
		encoder.SetIndent("", "  ")
		return encoder.Encode(summarize(trials))
	case "run":
		flags := flag.NewFlagSet("run", flag.ContinueOnError)
		var c Config
		flags.StringVar(&c.Harness, "harness", "pi", "pi or deepseek-harness; summarize each harness separately")
		flags.StringVar(&c.BaseURL, "url", "http://127.0.0.1:8000/v1", "OpenAI-compatible API base URL")
		flags.StringVar(&c.BaseModel, "base-model", "qwen-base", "base model ID advertised by /models")
		flags.StringVar(&c.AdapterModel, "adapter-model", "qwen-pi", "Pi LoRA model ID advertised by /models")
		flags.IntVar(&c.Runs, "runs", 1, "attempts per task per model")
		flags.IntVar(&c.RunOffset, "run-offset", 0, "completed repetition count; new numbering starts at offset + 1")
		flags.DurationVar(&c.Timeout, "timeout", 5*time.Minute, "wall clock limit per Pi process")
		flags.StringVar(&c.Pi, "pi", "pi", "path to Pi 1.5.2 executable")
		flags.StringVar(&c.DSH, "dsh", "dsh", "path to DeepSeek Harness 0.2.2-rc.1 executable")
		flags.StringVar(&c.Out, "out", "results/"+time.Now().UTC().Format("20060102T150405.000000000Z"), "new output directory, never overwritten")
		flags.IntVar(&c.ContextWindow, "context-window", 131072, "context window actually configured on the server")
		flags.BoolVar(&c.LlamaLoRA, "llama-lora", false, "llama.cpp: adapter ID 0, scale 0 for base and 1 for adapter")
		flags.StringVar(&c.OnlyPairs, "only-pairs", "", "optional comma-separated task:condition pairs for unfinished trials")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if flags.NArg() != 0 {
			return errors.New("unexpected positional arguments")
		}
		return runExperiment(ctx, c, out)
	case "regrade":
		flags := flag.NewFlagSet("regrade", flag.ContinueOnError)
		var evidence, outDir string
		var roots pathList
		flags.StringVar(&evidence, "evidence", "", "original curated evidence JSON, kept unchanged")
		flags.Var(&roots, "run-dir", "saved raw run directory; repeat for segmented results")
		flags.StringVar(&outDir, "out", "", "new directory for post-hoc V2 grades, never overwritten")
		if err := flags.Parse(args[1:]); err != nil {
			return err
		}
		if flags.NArg() != 0 || evidence == "" || outDir == "" || len(roots) == 0 {
			return errors.New("regrade requires -evidence, at least one -run-dir, and -out")
		}
		return runRegrade(ctx, evidence, roots, outDir, out)
	default:
		return fmt.Errorf("unknown command %q", args[0])
	}
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := execute(ctx, os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
