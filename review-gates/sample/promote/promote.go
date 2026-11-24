// Package promote switches a service entry (the "current" symlink) to a
// restored replica. It is the sample project the review-gates demo reviews.
package promote

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

var (
	ErrLocked        = errors.New("old instance still holds old.lock")
	ErrOldUnreadable = errors.New("old directory unreadable")
	ErrBlocked       = errors.New("replica not ready")
	ErrPending       = errors.New("another switch is pending")
)

// Test hooks that simulate a crash at a given point.
var (
	afterIntent = func() {}
	afterSwitch = func() {}
)

// Promote points root/current at root/replicas/<name>.
func Promote(root, name string) error {
	if err := checkLock(root); err != nil {
		return err
	}
	pending, err := readIntent(root)
	if err != nil {
		return err
	}
	if pending != "" && pending != name {
		return fmt.Errorf("%w: %s", ErrPending, pending)
	}
	if err := checkOld(root); err != nil {
		return err
	}
	if err := checkReplica(root, name); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, "intent"), []byte(name), 0o644); err != nil {
		return err
	}
	afterIntent()
	if err := switchCurrent(root, name); err != nil {
		return err
	}
	afterSwitch()
	return os.Remove(filepath.Join(root, "intent"))
}

// Resume finishes a switch that was interrupted after intent was written.
func Resume(root string) error {
	pending, err := readIntent(root)
	if err != nil || pending == "" {
		return err
	}
	return Promote(root, pending)
}

func checkLock(root string) error {
	_, err := os.Stat(filepath.Join(root, "old.lock"))
	if err == nil {
		return ErrLocked
	}
	if !os.IsNotExist(err) {
		return err
	}
	return nil
}

func readIntent(root string) (string, error) {
	b, err := os.ReadFile(filepath.Join(root, "intent"))
	if os.IsNotExist(err) {
		return "", nil
	}
	return strings.TrimSpace(string(b)), err
}

func checkOld(root string) error {
	_, err := os.Stat(filepath.Join(root, "current"))
	if err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("%w: %v", ErrOldUnreadable, err)
	}
	return nil
}

func checkReplica(root, name string) error {
	b, err := os.ReadFile(filepath.Join(root, "replicas", name, "STATUS"))
	if err != nil {
		return err
	}
	if status := strings.TrimSpace(string(b)); status != "ready" {
		return fmt.Errorf("%w: %s is %q", ErrBlocked, name, status)
	}
	return nil
}

func switchCurrent(root, name string) error {
	tmp := filepath.Join(root, "current.tmp")
	_ = os.Remove(tmp)
	if err := os.Symlink(filepath.Join("replicas", name), tmp); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(root, "current"))
}
