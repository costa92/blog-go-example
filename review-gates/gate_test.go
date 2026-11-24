package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// newSampleRepo copies sample/ into a git repo: main holds the spec and config,
// branch promote holds the implementation, and all three gates are approved.
func newSampleRepo(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	gitc := func(args ...string) {
		t.Helper()
		cmd := exec.Command("git", args...)
		cmd.Dir = dir
		cmd.Env = append(os.Environ(),
			"GIT_AUTHOR_NAME=t", "GIT_AUTHOR_EMAIL=t@example.com",
			"GIT_COMMITTER_NAME=t", "GIT_COMMITTER_EMAIL=t@example.com")
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v\n%s", args, err, out)
		}
	}
	copyFile := func(src, dst string) {
		t.Helper()
		b, err := os.ReadFile(filepath.Join("sample", src))
		if err != nil {
			t.Fatal(err)
		}
		writeFile(t, dir, dst, string(b))
	}
	for _, f := range []string{"SPEC.md", "go.mod", "review-gates.json", ".gitignore"} {
		copyFile(f, f)
	}
	writeFile(t, dir, "README.md", "# promote\n")
	writeFile(t, dir, "promote/promote.go", "package promote\n")
	gitc("init", "-q", "-b", "main")
	gitc("add", "-A")
	gitc("commit", "-qm", "spec")
	gitc("switch", "-q", "-c", "promote")
	for _, f := range []string{"promote.go", "promote_test.go", "promote_weak_test.go", "helpers_test.go"} {
		copyFile("promote/"+f, "promote/"+f)
	}
	gitc("add", "-A")
	gitc("commit", "-qm", "implement")
	for _, g := range gates {
		if rc, out := gate(t, dir, "approve", g, "--by", "reviewer"); rc != 0 {
			t.Fatalf("approve %s: %s", g, out)
		}
	}
	return dir
}

func writeFile(t *testing.T, dir, name, content string) {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func appendFile(t *testing.T, dir, name, content string) {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		t.Fatal(err)
	}
	writeFile(t, dir, name, string(b)+content)
}

func gitIn(t *testing.T, dir string, args ...string) {
	t.Helper()
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(),
		"GIT_AUTHOR_NAME=t", "GIT_AUTHOR_EMAIL=t@example.com",
		"GIT_COMMITTER_NAME=t", "GIT_COMMITTER_EMAIL=t@example.com")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
}

func gate(t *testing.T, dir string, args ...string) (int, string) {
	t.Helper()
	var out bytes.Buffer
	rc := run(dir, args, &out)
	return rc, out.String()
}

var statusLine = regexp.MustCompile(`(?m)^(design|tests|code|tree|base)\s+(OK|STALE|MISSING|ERROR|FAIL)\b`)

// notOK lists "gate=STATUS" for every line that is not OK.
func notOK(out string) string {
	var bad []string
	for _, m := range statusLine.FindAllStringSubmatch(out, -1) {
		if m[2] != "OK" {
			bad = append(bad, m[1]+"="+m[2])
		}
	}
	sort.Strings(bad)
	return strings.Join(bad, " ")
}

func commitAll(t *testing.T, dir, msg string) {
	gitIn(t, dir, "commit", "-qam", msg)
}

func TestGates(t *testing.T) {
	cases := []struct {
		name      string
		change    func(t *testing.T, dir string)
		wantCheck string // non-OK lines of `gate check`
		wantMerge string // non-OK lines of `gate merge-check`
	}{
		{
			name: "no change",
		},
		{
			name: "spec edited",
			change: func(t *testing.T, dir string) {
				appendFile(t, dir, "SPEC.md", "9. AC9 new rule\n")
				commitAll(t, dir, "spec")
			},
			wantCheck: "design=STALE",
			wantMerge: "design=STALE tree=FAIL",
		},
		{
			name: "test file edited, tests still pass",
			change: func(t *testing.T, dir string) {
				appendFile(t, dir, "promote/promote_test.go", "\n// reviewed\n")
				commitAll(t, dir, "test comment")
			},
			wantCheck: "tests=STALE",
			wantMerge: "tests=STALE tree=FAIL",
		},
		{
			name: "code edited, tests still pass",
			change: func(t *testing.T, dir string) {
				appendFile(t, dir, "promote/promote.go", "\n// tweak\n")
				commitAll(t, dir, "code comment")
			},
			wantCheck: "code=STALE",
			wantMerge: "code=STALE tree=FAIL",
		},
		{
			name: "code edit breaks a test",
			change: func(t *testing.T, dir string) {
				p := filepath.Join(dir, "promote/promote.go")
				b, _ := os.ReadFile(p)
				writeFile(t, dir, "promote/promote.go", strings.Replace(string(b), `status != "ready"`, `status == "never"`, 1))
				commitAll(t, dir, "break")
			},
			wantCheck: "code=STALE tests=STALE",
			wantMerge: "code=STALE tests=STALE tree=FAIL",
		},
		{
			name: "new test package outside the test globs",
			change: func(t *testing.T, dir string) {
				writeFile(t, dir, "extra/extra_test.go", "package extra\n\nimport \"testing\"\n\nfunc TestExtra(t *testing.T) {}\n")
				gitIn(t, dir, "add", "-A")
				commitAll(t, dir, "extra test")
			},
			wantCheck: "tests=STALE",
			wantMerge: "tests=STALE tree=FAIL",
		},
		{
			name: "uncommitted code edit",
			change: func(t *testing.T, dir string) {
				appendFile(t, dir, "promote/promote.go", "\n// wip\n")
			},
			wantCheck: "code=ERROR",
			wantMerge: "code=ERROR",
		},
		{
			name: "README edited outside every gate",
			change: func(t *testing.T, dir string) {
				appendFile(t, dir, "README.md", "more\n")
				commitAll(t, dir, "docs")
			},
			wantMerge: "tree=FAIL",
		},
		{
			name: "main moved ahead",
			change: func(t *testing.T, dir string) {
				gitIn(t, dir, "switch", "-q", "main")
				writeFile(t, dir, "HOTFIX.md", "x\n")
				gitIn(t, dir, "add", "-A")
				gitIn(t, dir, "commit", "-qm", "hotfix")
				gitIn(t, dir, "switch", "-q", "promote")
			},
			wantMerge: "base=FAIL",
		},
		{
			name: "rebased onto moved main",
			change: func(t *testing.T, dir string) {
				gitIn(t, dir, "switch", "-q", "main")
				writeFile(t, dir, "HOTFIX.md", "x\n")
				gitIn(t, dir, "add", "-A")
				gitIn(t, dir, "commit", "-qm", "hotfix")
				gitIn(t, dir, "switch", "-q", "promote")
				gitIn(t, dir, "rebase", "-q", "main")
			},
			wantCheck: "code=STALE",
			wantMerge: "code=STALE tree=FAIL",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			dir := newSampleRepo(t)
			if tc.change != nil {
				tc.change(t, dir)
			}
			_, out := gate(t, dir, "check")
			if got := notOK(out); got != tc.wantCheck {
				t.Errorf("check: got %q, want %q\n%s", got, tc.wantCheck, out)
			}
			_, out = gate(t, dir, "merge-check")
			if got := notOK(out); got != tc.wantMerge {
				t.Errorf("merge-check: got %q, want %q\n%s", got, tc.wantMerge, out)
			}
		})
	}
}

func TestApproveRefusesFailingTests(t *testing.T) {
	dir := newSampleRepo(t)
	p := filepath.Join(dir, "promote/promote.go")
	b, _ := os.ReadFile(p)
	writeFile(t, dir, "promote/promote.go", strings.Replace(string(b), `status != "ready"`, `status == "never"`, 1))
	commitAll(t, dir, "break")
	if rc, out := gate(t, dir, "approve", "tests", "--by", "reviewer"); rc == 0 {
		t.Fatalf("approve tests succeeded with failing tests:\n%s", out)
	}
}
