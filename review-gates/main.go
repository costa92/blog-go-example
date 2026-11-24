// Command gate binds review approvals to content digests: design approval to
// the spec files, the test record to test files plus the go test outcome, and
// code review to the diff of selected paths. Approvals live in .review/.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
)

const usage = `usage:
  gate approve <design|tests|code> --by NAME
  gate check
  gate merge-check`

func run(dir string, args []string, out io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(out, usage)
		return 2
	}
	r, err := loadRepo(dir)
	if err != nil {
		fmt.Fprintln(out, "gate:", err)
		return 2
	}
	switch args[0] {
	case "approve":
		if len(args) < 2 {
			fmt.Fprintln(out, usage)
			return 2
		}
		fs := flag.NewFlagSet("approve", flag.ContinueOnError)
		fs.SetOutput(out)
		by := fs.String("by", "", "reviewer name")
		if err := fs.Parse(args[2:]); err != nil {
			return 2
		}
		if err := r.approve(args[1], *by, out); err != nil {
			fmt.Fprintln(out, "gate: approve refused:", err)
			return 1
		}
		return 0
	case "check":
		if !r.check(out) {
			fmt.Fprintln(out, "check: FAIL")
			return 1
		}
		fmt.Fprintln(out, "check: OK")
		return 0
	case "merge-check":
		if !r.mergeCheck(out) {
			fmt.Fprintln(out, "merge-check: FAIL")
			return 1
		}
		fmt.Fprintln(out, "merge-check: OK")
		return 0
	}
	fmt.Fprintln(out, usage)
	return 2
}

func main() {
	dir, err := os.Getwd()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	os.Exit(run(dir, os.Args[1:], os.Stdout))
}
