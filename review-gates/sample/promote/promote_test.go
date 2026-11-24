//go:build !weak

package promote

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// Full suite: every case checks the returned error AND the state on disk.
func TestPromote(t *testing.T) {
	cases := []struct {
		name        string
		setup       func(t *testing.T, root string)
		run         func(root string) error
		wantErr     error
		wantCurrent string
		wantIntent  string
	}{
		{
			name:        "AC1 old lock held rejects",
			setup:       func(t *testing.T, root string) { touch(t, filepath.Join(root, "old.lock"), "") },
			run:         func(root string) error { return Promote(root, "r2") },
			wantErr:     ErrLocked,
			wantCurrent: "replicas/r1",
		},
		{
			name:        "AC2 old dir permission error rejects",
			setup:       unreadableOld,
			run:         func(root string) error { return Promote(root, "r2") },
			wantErr:     ErrOldUnreadable,
			wantCurrent: "locked/app",
		},
		{
			name:        "AC3 blocked replica rejects",
			run:         func(root string) error { return Promote(root, "r3") },
			wantErr:     ErrBlocked,
			wantCurrent: "replicas/r1",
		},
		{
			name:        "AC4 pending intent for another replica rejects",
			setup:       func(t *testing.T, root string) { touch(t, filepath.Join(root, "intent"), "r3") },
			run:         func(root string) error { return Promote(root, "r2") },
			wantErr:     ErrPending,
			wantCurrent: "replicas/r1",
			wantIntent:  "r3",
		},
		{
			name:        "AC6 success switches and clears intent",
			run:         func(root string) error { return Promote(root, "r2") },
			wantCurrent: "replicas/r2",
		},
		{
			name:        "AC7 resume finishes pending switch",
			setup:       func(t *testing.T, root string) { touch(t, filepath.Join(root, "intent"), "r2") },
			run:         Resume,
			wantCurrent: "replicas/r2",
		},
		{
			name: "AC7 resume still honours old lock",
			setup: func(t *testing.T, root string) {
				touch(t, filepath.Join(root, "intent"), "r2")
				touch(t, filepath.Join(root, "old.lock"), "")
			},
			run:         Resume,
			wantErr:     ErrLocked,
			wantCurrent: "replicas/r1",
			wantIntent:  "r2",
		},
		{
			name:        "AC7 resume still honours blocked replica",
			setup:       func(t *testing.T, root string) { touch(t, filepath.Join(root, "intent"), "r3") },
			run:         Resume,
			wantErr:     ErrBlocked,
			wantCurrent: "replicas/r1",
			wantIntent:  "r3",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := newRoot(t)
			if tc.setup != nil {
				tc.setup(t, root)
			}
			err := tc.run(root)
			if tc.wantErr == nil && err != nil || tc.wantErr != nil && !errors.Is(err, tc.wantErr) {
				t.Fatalf("err = %v, want %v", err, tc.wantErr)
			}
			if got := current(t, root); got != tc.wantCurrent {
				t.Errorf("current = %s, want %s", got, tc.wantCurrent)
			}
			if got := intent(root); got != tc.wantIntent {
				t.Errorf("intent = %q, want %q", got, tc.wantIntent)
			}
		})
	}
}

func TestCrashAfterSwitchKeepsIntent(t *testing.T) {
	root := newRoot(t)
	crashAt(t, &afterSwitch, func() error { return Promote(root, "r2") })
	if got := intent(root); got != "r2" {
		t.Fatalf("intent after crash = %q, want r2 (AC5)", got)
	}
	must(t, Resume(root))
	if got := current(t, root); got != "replicas/r2" || intent(root) != "" {
		t.Fatalf("after resume current=%s intent=%q", got, intent(root))
	}
}

func TestCrashAfterIntentResumes(t *testing.T) {
	root := newRoot(t)
	crashAt(t, &afterIntent, func() error { return Promote(root, "r2") })
	if got := current(t, root); got != "replicas/r1" {
		t.Fatalf("current before resume = %s", got)
	}
	must(t, Resume(root))
	if got := current(t, root); got != "replicas/r2" {
		t.Fatalf("current after resume = %s", got)
	}
}

func TestSwitchFailureKeepsIntent(t *testing.T) {
	root := newRoot(t)
	must(t, os.Remove(filepath.Join(root, "current")))
	must(t, os.MkdirAll(filepath.Join(root, "current", "data"), 0o755))
	if err := Promote(root, "r2"); err == nil {
		t.Fatal("want error when current cannot be replaced (AC8)")
	}
	if got := intent(root); got != "r2" {
		t.Fatalf("intent = %q, want r2 (AC8)", got)
	}
}
