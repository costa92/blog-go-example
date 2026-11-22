# Task: bytesize

Fix `ParseBytes` in solution.go. Only modify solution.go, keep its public signature,
use only Go's standard library, and do not change go.mod or the visible tests.

Accept a nonnegative decimal integer followed by an optional case-sensitive unit
B, KiB, MiB, or GiB. No unit means bytes. Surrounding whitespace is ignored;
between number and unit only ASCII spaces and tabs are allowed. No signs,
fractions, unknown units, or overflow of uint64 are accepted. Empty input is an
error. Examples: "12" => 12, " 2 KiB " => 2048, "3MiB" => 3145728.

Run the visible tests and explain your change briefly. Additional acceptance
tests will be run after the agent exits. They are not in this working directory.
