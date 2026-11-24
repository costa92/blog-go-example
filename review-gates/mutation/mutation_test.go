// Package mutation copies review-gates into a temp dir, applies one source
// mutation at a time and runs the relevant test suite. A mutation is caught
// when the suite fails.
package mutation

import (
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"testing"
)

type edit struct{ old, new string }

type mutation struct {
	name   string
	target string // "sample" or "gate"
	file   string // relative to review-gates/
	edits  []edit
}

const intentBlock = `	if err := os.WriteFile(filepath.Join(root, "intent"), []byte(name), 0o644); err != nil {
		return err
	}
	afterIntent()
	if err := switchCurrent(root, name); err != nil {
		return err
	}
	afterSwitch()
`

const switchFirst = `	if err := switchCurrent(root, name); err != nil {
		return err
	}
	afterSwitch()
	if err := os.WriteFile(filepath.Join(root, "intent"), []byte(name), 0o644); err != nil {
		return err
	}
	afterIntent()
`

const replicaCheck = `	if err := checkReplica(root, name); err != nil {
		return err
	}
`

var mutations = []mutation{
	// The nine behaviour mutations of the sample promote package.
	{"M1 lock not held is ignored", "sample", "sample/promote/promote.go",
		[]edit{{"if err == nil {\n\t\treturn ErrLocked", "if false {\n\t\treturn ErrLocked"}}},
	{"M2 permission error treated as missing old dir", "sample", "sample/promote/promote.go",
		[]edit{{"err != nil && !os.IsNotExist(err)", "err != nil && false"}}},
	{"M3 blocked replica status ignored", "sample", "sample/promote/promote.go",
		[]edit{{`status != "ready"`, `status == "never"`}}},
	{"M4 pending intent for another replica ignored", "sample", "sample/promote/promote.go",
		[]edit{{`pending != "" && pending != name`, "false"}}},
	{"M5 intent written after the switch", "sample", "sample/promote/promote.go",
		[]edit{{intentBlock, switchFirst}}},
	{"M6 intent not cleared on success", "sample", "sample/promote/promote.go",
		[]edit{{`return os.Remove(filepath.Join(root, "intent"))`, "return nil"}}},
	{"M7 resume skips the safety checks", "sample", "sample/promote/promote.go",
		[]edit{{"\treturn Promote(root, pending)", "\tif err := switchCurrent(root, pending); err != nil {\n\t\treturn err\n\t}\n\treturn os.Remove(filepath.Join(root, \"intent\"))"}}},
	{"M8 switch error swallowed", "sample", "sample/promote/promote.go",
		[]edit{{"\tif err := switchCurrent(root, name); err != nil {\n\t\treturn err\n\t}\n\tafterSwitch()", "\t_ = switchCurrent(root, name)\n\tafterSwitch()"}}},
	{"M9 replica checked only after switching", "sample", "sample/promote/promote.go",
		[]edit{{replicaCheck, ""}, {"\tafterSwitch()\n", "\tafterSwitch()\n" + replicaCheck}}},

	// Mutations of the gate tool itself, judged by gate_test.go.
	{"G1 code digest ignores merge base", "gate", "gate.go",
		[]edit{{`parts := map[string]string{"base": mb}`, `parts := map[string]string{}`}}},
	{"G2 merge-check skips tree comparison", "gate", "gate.go",
		[]edit{{"if candTree != code.Tree {", "if false {"}}},
	{"G3 test digest ignores go test result", "gate", "gate.go",
		[]edit{{`parts["go test result"] = sum([]byte(res))`, `_ = res`}}},
	{"G4 uncommitted code changes not refused", "gate", "gate.go",
		[]edit{{`if dirty != "" {`, "if false {"}}},
	{"G5 approve accepts failing tests", "gate", "gate.go",
		[]edit{{"\tif !ok {\n\t\treturn fmt.Errorf(\"%s: inputs not approvable", "\tif !ok && false {\n\t\treturn fmt.Errorf(\"%s: inputs not approvable"}}},
	{"G6 base ancestry not checked", "gate", "gate.go",
		[]edit{{`r.git("merge-base", "--is-ancestor", r.cfg.Base, "HEAD"); err != nil {`, `r.git("merge-base", "--is-ancestor", r.cfg.Base, "HEAD"); false && err != nil {`}}},
}

// suites maps a target to the test commands run against it.
var suites = map[string][]struct {
	name string
	dir  string
	args []string
}{
	"sample": {
		{"full", "sample", []string{"test", "-count=1", "./..."}},
		{"weak", "sample", []string{"test", "-count=1", "-tags", "weak", "./..."}},
	},
	"gate": {
		{"gate_test", ".", []string{"test", "-count=1", "."}},
	},
}

func copyTree(t *testing.T, src, dst string) {
	t.Helper()
	err := filepath.WalkDir(src, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		if d.IsDir() && (rel == "mutation" || d.Name() == ".git" || d.Name() == ".review") {
			return filepath.SkipDir
		}
		if d.IsDir() {
			return os.MkdirAll(filepath.Join(dst, rel), 0o755)
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		return os.WriteFile(filepath.Join(dst, rel), b, 0o644)
	})
	if err != nil {
		t.Fatal(err)
	}
}

func apply(t *testing.T, root string, m mutation) {
	t.Helper()
	p := filepath.Join(root, m.file)
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	s := string(b)
	for _, e := range m.edits {
		if n := strings.Count(s, e.old); n != 1 {
			t.Fatalf("%s: pattern found %d times: %q", m.file, n, e.old)
		}
		s = strings.Replace(s, e.old, e.new, 1)
	}
	if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
		t.Fatal(err)
	}
}

// failingTests returns the names of tests that failed, or "" if the suite passed.
func failingTests(dir string, args []string) (caught bool, failed string, err error) {
	cmd := exec.Command("go", args...)
	cmd.Dir = dir
	out, runErr := cmd.CombinedOutput()
	if runErr == nil {
		return false, "", nil
	}
	var names []string
	for _, l := range strings.Split(string(out), "\n") {
		l = strings.TrimSpace(l)
		if strings.HasPrefix(l, "--- FAIL: ") {
			names = append(names, strings.Fields(l)[2])
		}
	}
	if len(names) == 0 {
		return true, "", fmt.Errorf("suite failed without a failing test (build error?):\n%s", out)
	}
	return true, strings.Join(names, ", "), nil
}

func TestBaselinePasses(t *testing.T) {
	root := t.TempDir()
	copyTree(t, "..", root)
	for _, target := range []string{"sample", "gate"} {
		for _, s := range suites[target] {
			if caught, failed, err := failingTests(filepath.Join(root, s.dir), s.args); caught || err != nil {
				t.Fatalf("unmutated %s/%s fails: %s %v", target, s.name, failed, err)
			}
		}
	}
}

func TestMutations(t *testing.T) {
	var mu sync.Mutex
	summary := map[string]string{}
	t.Cleanup(func() {
		keys := make([]string, 0, len(summary))
		for k := range summary {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			t.Logf("%-55s %s", k, summary[k])
		}
	})
	for _, m := range mutations {
		for _, s := range suites[m.target] {
			t.Run(m.name+"/"+s.name, func(t *testing.T) {
				t.Parallel()
				root := t.TempDir()
				copyTree(t, "..", root)
				apply(t, root, m)
				caught, failed, err := failingTests(filepath.Join(root, s.dir), s.args)
				if err != nil {
					t.Fatal(err)
				}
				result := "SURVIVED"
				if caught {
					result = "caught by " + failed
				}
				mu.Lock()
				summary[m.name+" ["+s.name+"]"] = result
				mu.Unlock()
				t.Log(result)
				// The weak suite is expected to miss some; only the full
				// suites are required to catch every mutation.
				if !caught && s.name != "weak" {
					t.Errorf("mutation survived the %s suite", s.name)
				}
			})
		}
	}
}
