package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestGradersRejectBuggyAndAcceptReference(t *testing.T) {
	for _, task := range taskIDs {
		t.Run(task, func(t *testing.T) {
			bad := gradeSource(context.Background(), task, asset(task, "solution.go.txt"))
			good := gradeSource(context.Background(), task, asset(task, "reference.go.txt"))
			if bad.Passed || bad.Status != "failed" || !good.Passed {
				t.Fatalf("buggy=%+v reference=%+v", bad, good)
			}
		})
	}
}

func TestGraderDoesNotAcceptProcessExitInsteadOfTests(t *testing.T) {
	source := []byte("package exercise\nimport \"os\"\nfunc init(){os.Exit(0)}\nfunc ParseBytes(string)(uint64,error){return 0,nil}\n")
	if gradeSource(context.Background(), "bytesize", source).Passed {
		t.Fatal("exit without running acceptance tests passed")
	}
}

func TestTaskWorkspaceExcludesReferenceAndAcceptanceTests(t *testing.T) {
	dir := t.TempDir()
	if err := prepareTask(dir, "bytesize"); err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 4 {
		t.Fatalf("unexpected task files: %v", entries)
	}
	for _, name := range []string{"reference.go", "acceptance_test.go"} {
		if _, err := os.Stat(filepath.Join(dir, name)); !os.IsNotExist(err) {
			t.Fatalf("leaked %s", name)
		}
	}
	if err := os.Remove(filepath.Join(dir, "solution.go")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("go.mod", filepath.Join(dir, "solution.go")); err != nil {
		t.Fatal(err)
	}
	if _, err := readSolution(dir); err == nil {
		t.Fatal("accepted a symlink")
	}
}
