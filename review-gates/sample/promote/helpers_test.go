package promote

import (
	"os"
	"path/filepath"
	"testing"
)

type crash struct{}

// newRoot builds replicas r1, r2 (ready) and r3 (blocked) with current -> replicas/r1.
func newRoot(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	for name, status := range map[string]string{"r1": "ready", "r2": "ready", "r3": "blocked"} {
		dir := filepath.Join(root, "replicas", name)
		must(t, os.MkdirAll(dir, 0o755))
		must(t, os.WriteFile(filepath.Join(dir, "STATUS"), []byte(status+"\n"), 0o644))
	}
	must(t, os.Symlink(filepath.Join("replicas", "r1"), filepath.Join(root, "current")))
	return root
}

func must(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func touch(t *testing.T, path, content string) {
	t.Helper()
	must(t, os.WriteFile(path, []byte(content), 0o644))
}

func current(t *testing.T, root string) string {
	t.Helper()
	target, err := os.Readlink(filepath.Join(root, "current"))
	if err != nil {
		return "<" + err.Error() + ">"
	}
	return target
}

func intent(root string) string {
	b, err := os.ReadFile(filepath.Join(root, "intent"))
	if err != nil {
		return ""
	}
	return string(b)
}

// unreadableOld points current at a directory whose parent has mode 000.
func unreadableOld(t *testing.T, root string) {
	t.Helper()
	dir := filepath.Join(root, "locked")
	must(t, os.MkdirAll(filepath.Join(dir, "app"), 0o755))
	must(t, os.Remove(filepath.Join(root, "current")))
	must(t, os.Symlink(filepath.Join("locked", "app"), filepath.Join(root, "current")))
	must(t, os.Chmod(dir, 0))
	t.Cleanup(func() { _ = os.Chmod(dir, 0o755) })
}

// crashAt makes the hook panic, runs fn and swallows the simulated crash.
func crashAt(t *testing.T, hook *func(), fn func() error) {
	t.Helper()
	old := *hook
	*hook = func() { panic(crash{}) }
	defer func() {
		*hook = old
		if r := recover(); r != nil {
			if _, ok := r.(crash); !ok {
				panic(r)
			}
		}
	}()
	_ = fn()
	t.Fatal("expected simulated crash")
}
