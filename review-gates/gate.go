package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// Config lives in review-gates.json at the repository root and is committed.
type Config struct {
	Base    string   `json:"base"`
	Design  []string `json:"design"` // spec file globs
	Tests   []string `json:"tests"`  // test file globs
	TestCmd []string `json:"test_cmd"`
	Code    []string `json:"code"` // pathspecs whose diff against base is reviewed
}

// Approval is one gate's record in .review/<gate>.json (kept out of the tree).
type Approval struct {
	Gate       string            `json:"gate"`
	Digest     string            `json:"digest"`
	Parts      map[string]string `json:"parts"`
	ApprovedBy string            `json:"approved_by"`
	ApprovedAt string            `json:"approved_at"`
	Head       string            `json:"head"`
	Tree       string            `json:"tree"`
}

var gates = []string{"design", "tests", "code"}

type repo struct {
	dir string
	cfg Config
}

func loadRepo(dir string) (*repo, error) {
	b, err := os.ReadFile(filepath.Join(dir, "review-gates.json"))
	if err != nil {
		return nil, err
	}
	r := &repo{dir: dir}
	if err := json.Unmarshal(b, &r.cfg); err != nil {
		return nil, fmt.Errorf("review-gates.json: %w", err)
	}
	return r, nil
}

func (r *repo) git(args ...string) (string, error) {
	cmd := exec.Command("git", args...)
	cmd.Dir = r.dir
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("git %s: %v: %s", strings.Join(args, " "), err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(string(out)), nil
}

func sum(b []byte) string {
	h := sha256.Sum256(b)
	return fmt.Sprintf("%x", h)
}

// combine hashes the sorted parts, so the overall digest changes iff a part does.
func combine(parts map[string]string) string {
	keys := make([]string, 0, len(parts))
	for k := range parts {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		fmt.Fprintf(&b, "%s %s\n", k, parts[k])
	}
	return sum([]byte(b.String()))
}

func (r *repo) fileParts(globs []string) (map[string]string, error) {
	parts := map[string]string{}
	for _, g := range globs {
		matches, err := filepath.Glob(filepath.Join(r.dir, g))
		if err != nil {
			return nil, err
		}
		if len(matches) == 0 {
			return nil, fmt.Errorf("pattern %q matches no file", g)
		}
		for _, m := range matches {
			b, err := os.ReadFile(m)
			if err != nil {
				return nil, err
			}
			rel, _ := filepath.Rel(r.dir, m)
			parts["file:"+filepath.ToSlash(rel)] = sum(b)
		}
	}
	return parts, nil
}

// testResult runs the test command with -json and reduces it to the sorted
// list of per-test outcomes, so timings do not leak into the digest.
func (r *repo) testResult() (string, bool, error) {
	if len(r.cfg.TestCmd) == 0 {
		return "", false, errors.New("test_cmd is empty")
	}
	args := append(append([]string{}, r.cfg.TestCmd[1:]...), "-json")
	cmd := exec.Command(r.cfg.TestCmd[0], args...)
	cmd.Dir = r.dir
	out, runErr := cmd.Output()
	var lines []string
	sc := bufio.NewScanner(bytes.NewReader(out))
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var ev struct{ Action, Package, Test string }
		if json.Unmarshal(sc.Bytes(), &ev) != nil || ev.Test == "" {
			continue
		}
		switch ev.Action {
		case "pass", "fail", "skip":
			lines = append(lines, ev.Action+" "+ev.Package+" "+ev.Test)
		}
	}
	sort.Strings(lines)
	passed := runErr == nil
	status := "ok"
	if !passed {
		status = "FAIL"
	}
	return fmt.Sprintf("status %s\n%s", status, strings.Join(lines, "\n")), passed, nil
}

func (r *repo) mergeBase() (string, error) {
	return r.git("merge-base", r.cfg.Base, "HEAD")
}

// codeParts hashes the committed diff base...HEAD of each changed file under
// the configured paths. Uncommitted changes there are refused, not hashed.
func (r *repo) codeParts() (map[string]string, error) {
	dirty, err := r.git(append([]string{"status", "--porcelain", "--"}, r.cfg.Code...)...)
	if err != nil {
		return nil, err
	}
	if dirty != "" {
		return nil, fmt.Errorf("uncommitted changes under code paths:\n%s", dirty)
	}
	mb, err := r.mergeBase()
	if err != nil {
		return nil, err
	}
	names, err := r.git(append([]string{"diff", "--name-only", mb, "HEAD", "--"}, r.cfg.Code...)...)
	if err != nil {
		return nil, err
	}
	parts := map[string]string{"base": mb}
	for _, name := range strings.Fields(names) {
		d, err := r.git("diff", mb, "HEAD", "--", name)
		if err != nil {
			return nil, err
		}
		parts["diff:"+name] = sum([]byte(d))
	}
	return parts, nil
}

// compute returns the current parts of a gate. ok=false means the gate's
// inputs are in a state that may never be approved (failing tests).
func (r *repo) compute(gate string) (parts map[string]string, ok bool, err error) {
	switch gate {
	case "design":
		parts, err = r.fileParts(r.cfg.Design)
		return parts, err == nil, err
	case "tests":
		parts, err = r.fileParts(r.cfg.Tests)
		if err != nil {
			return nil, false, err
		}
		res, passed, err := r.testResult()
		if err != nil {
			return nil, false, err
		}
		parts["go test result"] = sum([]byte(res))
		return parts, passed, nil
	case "code":
		parts, err = r.codeParts()
		return parts, err == nil, err
	}
	return nil, false, fmt.Errorf("unknown gate %q (want design, tests or code)", gate)
}

func (r *repo) approvalPath(gate string) string {
	return filepath.Join(r.dir, ".review", gate+".json")
}

func (r *repo) load(gate string) (*Approval, error) {
	b, err := os.ReadFile(r.approvalPath(gate))
	if err != nil {
		return nil, err
	}
	var a Approval
	return &a, json.Unmarshal(b, &a)
}

func short(d string) string {
	if len(d) > 12 {
		return d[:12]
	}
	return d
}

func (r *repo) approve(gate, by string, out io.Writer) error {
	if by == "" {
		return errors.New("--by is required")
	}
	parts, ok, err := r.compute(gate)
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("%s: inputs not approvable (tests failing)", gate)
	}
	head, err := r.git("rev-parse", "HEAD")
	if err != nil {
		return err
	}
	tree, err := r.git("rev-parse", "HEAD^{tree}")
	if err != nil {
		return err
	}
	a := Approval{Gate: gate, Digest: combine(parts), Parts: parts, ApprovedBy: by,
		ApprovedAt: time.Now().UTC().Format(time.RFC3339), Head: head, Tree: tree}
	if err := os.MkdirAll(filepath.Join(r.dir, ".review"), 0o755); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(a, "", "  ")
	if err := os.WriteFile(r.approvalPath(gate), append(b, '\n'), 0o644); err != nil {
		return err
	}
	fmt.Fprintf(out, "approved %-6s digest=%s by=%s head=%s\n", gate, short(a.Digest), by, short(head))
	return nil
}

// checkGate prints one line per gate plus the parts that changed.
func (r *repo) checkGate(gate string, out io.Writer) bool {
	a, err := r.load(gate)
	if err != nil {
		fmt.Fprintf(out, "%-6s MISSING  no approval record (%v)\n", gate, err)
		return false
	}
	parts, ok, err := r.compute(gate)
	if err != nil {
		fmt.Fprintf(out, "%-6s ERROR    %v\n", gate, err)
		return false
	}
	now := combine(parts)
	if now == a.Digest && ok {
		fmt.Fprintf(out, "%-6s OK       %s approved by %s\n", gate, short(now), a.ApprovedBy)
		return true
	}
	fmt.Fprintf(out, "%-6s STALE    approved %s by %s, now %s\n", gate, short(a.Digest), a.ApprovedBy, short(now))
	if !ok {
		fmt.Fprintf(out, "         tests are failing\n")
	}
	keys := map[string]bool{}
	for k := range a.Parts {
		keys[k] = true
	}
	for k := range parts {
		keys[k] = true
	}
	var names []string
	for k := range keys {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		old, had := a.Parts[k]
		cur, has := parts[k]
		switch {
		case !had:
			fmt.Fprintf(out, "         + %s (new)\n", k)
		case !has:
			fmt.Fprintf(out, "         - %s (gone)\n", k)
		case old != cur:
			fmt.Fprintf(out, "         ~ %s %s -> %s\n", k, short(old), short(cur))
		}
	}
	return false
}

func (r *repo) check(out io.Writer) bool {
	ok := true
	for _, g := range gates {
		if !r.checkGate(g, out) {
			ok = false
		}
	}
	return ok
}

// mergeCheck builds the squash candidate in a throwaway worktree and compares
// its tree with the tree the code approval was given for.
func (r *repo) mergeCheck(out io.Writer) bool {
	ok := r.check(out)
	if _, err := r.git("merge-base", "--is-ancestor", r.cfg.Base, "HEAD"); err != nil {
		fmt.Fprintf(out, "base   FAIL     %s is not an ancestor of HEAD; rebase and re-review\n", r.cfg.Base)
		return false
	}
	code, err := r.load("code")
	if err != nil {
		fmt.Fprintf(out, "tree   FAIL     no code approval to compare against\n")
		return false
	}
	wt, err := os.MkdirTemp("", "gate-candidate-")
	if err != nil {
		fmt.Fprintf(out, "tree   ERROR    %v\n", err)
		return false
	}
	_ = os.Remove(wt)
	defer func() {
		_, _ = r.git("worktree", "remove", "--force", wt)
		_ = os.RemoveAll(wt)
	}()
	head, err := r.git("rev-parse", "HEAD")
	if err == nil {
		_, err = r.git("worktree", "add", "--quiet", "--detach", wt, r.cfg.Base)
	}
	cand := &repo{dir: wt, cfg: r.cfg}
	if err == nil {
		_, err = cand.git("merge", "--squash", head)
	}
	if err == nil {
		_, err = cand.git("-c", "user.name=gate", "-c", "user.email=gate@example.com",
			"commit", "--quiet", "--allow-empty", "-m", "squash candidate")
	}
	if err != nil {
		fmt.Fprintf(out, "tree   ERROR    building squash candidate: %v\n", err)
		return false
	}
	candTree, _ := cand.git("rev-parse", "HEAD^{tree}")
	if candTree != code.Tree {
		fmt.Fprintf(out, "tree   FAIL     squash candidate %s != reviewed tree %s\n", short(candTree), short(code.Tree))
		diff, _ := r.git("diff", "--name-status", code.Tree, candTree)
		for _, l := range strings.Split(diff, "\n") {
			if l != "" {
				fmt.Fprintf(out, "         %s\n", l)
			}
		}
		return false
	}
	fmt.Fprintf(out, "tree   OK       squash candidate %s == reviewed tree\n", short(candTree))
	return ok
}
