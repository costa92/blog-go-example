package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
)

const regradeVersion = "acceptance-v2-post-hoc"
const v2Root = "TestAcceptanceV2"

type CaseGrade struct {
	Name   string `json:"name"`
	Status string `json:"status"` // passed, failed, or not_run
}
type DetailedGrade struct {
	Version     string      `json:"version"`
	Status      string      `json:"status"`
	Scorable    bool        `json:"scorable"`
	Passed      bool        `json:"passed"`
	Expected    int         `json:"expected_cases"`
	PassedCases int         `json:"passed_cases"`
	FailedCases int         `json:"failed_cases"`
	NotRun      int         `json:"not_run_cases"`
	Cases       []CaseGrade `json:"cases"`
	Log         string      `json:"-"`
}

// Cases have literal names in trusted embedded test code. This derives the
// denominator from the frozen suite, never from how far a candidate gets.
func v2CaseNames(task string) ([]string, error) {
	f, err := parser.ParseFile(token.NewFileSet(), "acceptance_v2_test.go", asset(task, "acceptance_v2_test.go.txt"), 0)
	if err != nil {
		return nil, err
	}
	var names []string
	seen := map[string]bool{}
	ast.Inspect(f, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		sel, ok := call.Fun.(*ast.SelectorExpr)
		if !ok || sel.Sel.Name != "Run" {
			return true
		}
		if len(call.Args) == 0 {
			err = errors.New("missing V2 case name")
			return false
		}
		lit, ok := call.Args[0].(*ast.BasicLit)
		if !ok || lit.Kind != token.STRING {
			err = errors.New("V2 case names must be string literals")
			return false
		}
		name, e := strconv.Unquote(lit.Value)
		if e != nil || name == "" || strings.ContainsAny(name, "/ \t\r\n") || seen[name] {
			err = errors.New("invalid or duplicate V2 case name")
			return false
		}
		seen[name] = true
		names = append(names, name)
		return true
	})
	if err != nil {
		return nil, err
	}
	if len(names) == 0 {
		return nil, errors.New("empty V2 suite")
	}
	return names, nil
}

func parseV2Events(data []byte, names []string) (DetailedGrade, bool, bool, error) {
	g := DetailedGrade{Version: regradeVersion, Expected: len(names), Status: "failed"}
	states := map[string]string{}
	started := map[string]bool{}
	for _, name := range names {
		states[name] = "not_run"
	}
	rootPass, packagePass, buildFailed := false, false, false
	decoder := json.NewDecoder(bytes.NewReader(data))
	for {
		var e struct{ Action, Test, FailedBuild string }
		err := decoder.Decode(&e)
		if err == io.EOF {
			break
		}
		if err != nil {
			return g, false, false, fmt.Errorf("invalid go test JSON: %w", err)
		}
		if e.Action == "build-fail" || e.FailedBuild != "" {
			buildFailed = true
		}
		if e.Action == "pass" && e.Test == v2Root {
			rootPass = true
		}
		if e.Action == "pass" && e.Test == "" {
			packagePass = true
		}
		if !strings.HasPrefix(e.Test, v2Root+"/") {
			continue
		}
		name := strings.TrimPrefix(e.Test, v2Root+"/")
		if _, ok := states[name]; !ok {
			return g, false, false, fmt.Errorf("unknown V2 case %q", name)
		}
		if e.Action == "run" {
			if started[name] {
				return g, false, false, errors.New("duplicate V2 case run")
			}
			started[name] = true
		}
		if e.Action == "pass" || e.Action == "fail" || e.Action == "skip" {
			if !started[name] || states[name] != "not_run" {
				return g, false, false, errors.New("invalid V2 case terminal event")
			}
			if e.Action == "pass" {
				states[name] = "passed"
			} else if e.Action == "fail" {
				states[name] = "failed"
			}
		}
	}
	for _, name := range names {
		status := states[name]
		g.Cases = append(g.Cases, CaseGrade{Name: name, Status: status})
		switch status {
		case "passed":
			g.PassedCases++
		case "failed":
			g.FailedCases++
		default:
			g.NotRun++
		}
	}
	return g, rootPass && packagePass, buildFailed, nil
}

func gradeSourceV2(ctx context.Context, task string, source []byte) DetailedGrade {
	names, err := v2CaseNames(task)
	if err != nil {
		return DetailedGrade{Version: regradeVersion, Status: "grader_error", Log: err.Error()}
	}
	fail := func(err error) DetailedGrade {
		g, _, _, _ := parseV2Events(nil, names)
		g.Status = "grader_error"
		g.Log = err.Error()
		return g
	}
	dir, err := os.MkdirTemp("", "harness-grade-v2-")
	if err != nil {
		return fail(err)
	}
	defer os.RemoveAll(dir)
	for name, data := range map[string][]byte{"go.mod": []byte(taskModule), "solution.go": source, "acceptance_v2_test.go": asset(task, "acceptance_v2_test.go.txt")} {
		if err := writeFile(filepath.Join(dir, name), data); err != nil {
			return fail(err)
		}
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	cmd := ownedCommand(ctx, "go", "test", "-json", "-count=1", "-timeout=10s", ".")
	cmd.Dir = dir
	cmd.Env = replaceEnv(os.Environ(), map[string]string{"GOWORK": "off", "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0"})
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	runErr := cmd.Run()
	g, complete, buildFailed, err := parseV2Events(stdout.Bytes(), names)
	if err != nil {
		return fail(fmt.Errorf("%w\n%s\n%s", err, stdout.String(), stderr.String()))
	}
	g.Log = stdout.String() + stderr.String()
	if ctx.Err() != nil {
		g.Status = "timeout"
		g.Scorable = errors.Is(ctx.Err(), context.DeadlineExceeded)
		return g
	}
	if runErr != nil {
		if _, ok := runErr.(*exec.ExitError); !ok {
			g.Status = "grader_error"
			return g
		}
	}
	if runErr == nil && (!complete || g.NotRun > 0) {
		g.Status = "grader_error"
		return g
	}
	g.Scorable = true
	if buildFailed {
		g.Status = "build_failed"
		return g
	}
	if runErr == nil && complete && g.PassedCases == g.Expected {
		g.Passed = true
		g.Status = "passed"
	}
	return g
}

type savedTrial struct {
	Trial
	Artifacts map[string]string `json:"artifact_sha256"`
}
type loadedAnswer struct {
	Saved  savedTrial
	Source []byte
}
type RegradedTrial struct {
	Original    Trial             `json:"original"`
	V2          DetailedGrade     `json:"v2"`
	GradeMS     int64             `json:"regrade_wall_ms"`
	ArtifactSHA map[string]string `json:"regrade_artifact_sha256"`
}
type RegradeTotals struct {
	Attempts       int `json:"attempts"`
	OriginalPassed int `json:"v1_passed"`
	Passed         int `json:"v2_passed"`
	Unscorable     int `json:"v2_unscorable"`
	ExpectedCases  int `json:"expected_cases"`
	PassedCases    int `json:"passed_cases"`
	FailedCases    int `json:"failed_cases"`
	NotRun         int `json:"not_run_cases"`
}
type RegradeSummary struct {
	Conditions   map[string]RegradeTotals            `json:"conditions"`
	Tasks        map[string]map[string]RegradeTotals `json:"by_task"`
	V2Efficiency Summary                             `json:"v2_success_pair_efficiency"`
}

func loadRegradeAnswers(evidencePath string, roots []string) ([]loadedAnswer, string, error) {
	b, err := os.ReadFile(evidencePath)
	if err != nil {
		return nil, "", err
	}
	var evidence struct {
		Trials []savedTrial `json:"trials"`
	}
	if err := json.Unmarshal(b, &evidence); err != nil {
		return nil, "", err
	}
	if len(evidence.Trials) == 0 || len(roots) == 0 {
		return nil, "", errors.New("evidence and run directories must contain saved trials")
	}
	seen := map[string]bool{}
	var loaded []loadedAnswer
	for _, t := range evidence.Trials {
		validTask := false
		for _, id := range taskIDs {
			validTask = validTask || t.Task == id
		}
		if !validTask || t.Repetition < 1 || (t.Condition != "base" && t.Condition != "adapter") {
			return nil, "", errors.New("invalid saved trial identity")
		}
		name := fmt.Sprintf("%02d-%s-%s", t.Repetition, t.Task, t.Condition)
		if seen[name] {
			return nil, "", fmt.Errorf("duplicate saved trial %s", name)
		}
		seen[name] = true
		var matches []string
		for _, root := range roots {
			d := filepath.Join(root, name)
			if _, err := os.Stat(filepath.Join(d, "result.json")); err == nil {
				matches = append(matches, d)
			}
		}
		if len(matches) != 1 {
			return nil, "", fmt.Errorf("expected exactly one saved result for %s, found %d", name, len(matches))
		}
		dir := matches[0]
		for _, file := range []string{"events.jsonl", "grade.jsonl", "result.json", "solution.go.txt"} {
			b, err := os.ReadFile(filepath.Join(dir, file))
			if err != nil {
				return nil, "", err
			}
			if want := t.Artifacts[file]; want == "" || digest(b) != want {
				return nil, "", fmt.Errorf("saved artifact hash mismatch: %s/%s", name, file)
			}
		}
		raw, err := os.ReadFile(filepath.Join(dir, "result.json"))
		if err != nil {
			return nil, "", err
		}
		var original Trial
		if err := json.Unmarshal(raw, &original); err != nil {
			return nil, "", err
		}
		if !reflect.DeepEqual(original, t.Trial) {
			return nil, "", fmt.Errorf("evidence differs from raw result: %s", name)
		}
		source, err := readSolutionSnapshot(dir)
		if err != nil {
			return nil, "", err
		}
		if digest(source) != t.FinalSourceHash {
			return nil, "", fmt.Errorf("final source hash mismatch: %s", name)
		}
		loaded = append(loaded, loadedAnswer{Saved: t, Source: source})
	}
	// Pair matching is retained for efficiency; an unpaired manifest is rejected.
	for _, t := range loaded {
		other := "base"
		if t.Saved.Condition == "base" {
			other = "adapter"
		}
		if !seen[fmt.Sprintf("%02d-%s-%s", t.Saved.Repetition, t.Saved.Task, other)] {
			return nil, "", errors.New("incomplete saved trial pair")
		}
	}
	return loaded, digest(b), nil
}

func readSolutionSnapshot(dir string) ([]byte, error) {
	info, err := os.Lstat(filepath.Join(dir, "solution.go.txt"))
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > 1<<20 {
		return nil, errors.New("saved source must be a regular file, at most 1 MiB")
	}
	return os.ReadFile(filepath.Join(dir, "solution.go.txt"))
}

func regradeSummary(trials []RegradedTrial) RegradeSummary {
	s := RegradeSummary{Conditions: map[string]RegradeTotals{}, Tasks: map[string]map[string]RegradeTotals{}}
	var revised []Trial
	add := func(c RegradeTotals, t RegradedTrial) RegradeTotals {
		c.Attempts++
		if t.Original.Scorable && t.Original.Passed {
			c.OriginalPassed++
		}
		if !t.V2.Scorable {
			c.Unscorable++
		}
		if t.V2.Scorable && t.V2.Passed {
			c.Passed++
		}
		c.ExpectedCases += t.V2.Expected
		c.PassedCases += t.V2.PassedCases
		c.FailedCases += t.V2.FailedCases
		c.NotRun += t.V2.NotRun
		return c
	}
	for _, t := range trials {
		s.Conditions[t.Original.Condition] = add(s.Conditions[t.Original.Condition], t)
		if s.Tasks[t.Original.Task] == nil {
			s.Tasks[t.Original.Task] = map[string]RegradeTotals{}
		}
		s.Tasks[t.Original.Task][t.Original.Condition] = add(s.Tasks[t.Original.Task][t.Original.Condition], t)
		v := t.Original
		v.Passed = t.V2.Passed
		v.Scorable = t.Original.Scorable && t.V2.Scorable
		revised = append(revised, v)
	}
	s.V2Efficiency = summarize(revised)
	return s
}

func runRegrade(ctx context.Context, evidence string, roots []string, out string, progress io.Writer) error {
	answers, evidenceHash, err := loadRegradeAnswers(evidence, roots)
	if err != nil {
		return err
	}
	// Gate the new suite with known-good answers before evaluating saved outputs.
	suites := map[string]any{}
	for _, task := range taskIDs {
		names, err := v2CaseNames(task)
		if err != nil {
			return err
		}
		g := gradeSourceV2(ctx, task, asset(task, "reference.go.txt"))
		if !g.Passed {
			return fmt.Errorf("V2 reference preflight %s: %s\n%s", task, g.Status, g.Log)
		}
		suites[task] = map[string]any{"case_names": names, "expected_cases": len(names), "test_sha256": digest(asset(task, "acceptance_v2_test.go.txt")), "task_prompt_sha256": digest(asset(task, "prompt.md"))}
	}
	if err := os.MkdirAll(filepath.Dir(out), 0700); err != nil {
		return err
	}
	if err := os.Mkdir(out, 0700); err != nil {
		return fmt.Errorf("create fresh regrade directory: %w", err)
	}
	version, err := exec.Command("go", "version").Output()
	if err != nil {
		return err
	}
	metadata := map[string]any{"version": regradeVersion, "post_hoc": true, "new_model_calls": 0, "original_results_modified": false, "source_evidence_sha256": evidenceHash, "source_artifacts_verified": true, "started_at": time.Now().UTC().Format(time.RFC3339), "go_version": strings.TrimSpace(string(version)), "os": runtime.GOOS, "arch": runtime.GOARCH, "suites": suites, "case_denominator": "all predefined cases, including not_run after build failure or interruption; see separate not_run count", "limitations": "Post-hoc finite coverage audit on three public tasks; not a blinded benchmark. A passed suite is not proof of full correctness."}
	if err := writeJSON(filepath.Join(out, "metadata.json"), metadata); err != nil {
		return err
	}
	var revised []RegradedTrial
	for _, answer := range answers {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		t := answer.Saved.Trial
		name := fmt.Sprintf("%02d-%s-%s", t.Repetition, t.Task, t.Condition)
		dir := filepath.Join(out, name)
		if err := os.Mkdir(dir, 0700); err != nil {
			return err
		}
		start := time.Now()
		grade := gradeSourceV2(ctx, t.Task, answer.Source)
		log := []byte(grade.Log)
		if err := writeFile(filepath.Join(dir, "grade-v2.jsonl"), log); err != nil {
			return err
		}
		r := RegradedTrial{Original: t, V2: grade, GradeMS: time.Since(start).Milliseconds(), ArtifactSHA: map[string]string{"grade-v2.jsonl": digest(log)}}
		if err := writeJSON(filepath.Join(dir, "result-v2.json"), r); err != nil {
			return err
		}
		revised = append(revised, r)
		if err := writeJSON(filepath.Join(out, "results-v2.json"), revised); err != nil {
			return err
		}
		fmt.Fprintf(progress, "%s: %s; cases %d/%d passed, %d failed, %d not run\n", name, grade.Status, grade.PassedCases, grade.Expected, grade.FailedCases, grade.NotRun)
	}
	summary := regradeSummary(revised)
	if err := writeJSON(filepath.Join(out, "summary-v2.json"), summary); err != nil {
		return err
	}
	conditions := []string{"base", "adapter"}
	sort.Strings(conditions)
	for _, condition := range conditions {
		c := summary.Conditions[condition]
		fmt.Fprintf(progress, "%s: V1 %d/%d -> V2 %d/%d; cases %d/%d; not run %d; unscorable %d\n", condition, c.OriginalPassed, c.Attempts, c.Passed, c.Attempts, c.PassedCases, c.ExpectedCases, c.NotRun, c.Unscorable)
	}
	for _, c := range summary.Conditions {
		if c.Unscorable > 0 {
			return errors.New("unscorable V2 results; inspect raw output")
		}
	}
	return nil
}

type pathList []string

func (p *pathList) String() string { return strings.Join(*p, ",") }
func (p *pathList) Set(s string) error {
	if s == "" {
		return errors.New("empty run directory")
	}
	*p = append(*p, s)
	return nil
}
