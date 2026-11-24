//go:build weak

package promote

import (
	"os"
	"path/filepath"
	"testing"
)

// Weak suite: the same rejection cases without crash simulation; each case only
// asserts whether an error came back.
func TestPromoteWeak(t *testing.T) {
	cases := []struct {
		name    string
		setup   func(t *testing.T, root string)
		run     func(root string) error
		wantErr bool
	}{
		{"AC1 old lock held rejects", func(t *testing.T, root string) { touch(t, filepath.Join(root, "old.lock"), "") }, func(root string) error { return Promote(root, "r2") }, true},
		{"AC2 old dir permission error rejects", unreadableOld, func(root string) error { return Promote(root, "r2") }, true},
		{"AC3 blocked replica rejects", nil, func(root string) error { return Promote(root, "r3") }, true},
		{"AC4 pending intent for another replica rejects", func(t *testing.T, root string) { touch(t, filepath.Join(root, "intent"), "r3") }, func(root string) error { return Promote(root, "r2") }, true},
		{"AC6 success", nil, func(root string) error { return Promote(root, "r2") }, false},
		{"AC7 resume finishes pending switch", func(t *testing.T, root string) { touch(t, filepath.Join(root, "intent"), "r2") }, Resume, false},
		{"AC7 resume still honours old lock", func(t *testing.T, root string) {
			touch(t, filepath.Join(root, "intent"), "r2")
			touch(t, filepath.Join(root, "old.lock"), "")
		}, Resume, true},
		{"AC8 switch failure returns error", func(t *testing.T, root string) {
			must(t, os.Remove(filepath.Join(root, "current")))
			must(t, os.MkdirAll(filepath.Join(root, "current", "data"), 0o755))
		}, func(root string) error { return Promote(root, "r2") }, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := newRoot(t)
			if tc.setup != nil {
				tc.setup(t, root)
			}
			if err := tc.run(root); (err != nil) != tc.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, tc.wantErr)
			}
		})
	}
}
