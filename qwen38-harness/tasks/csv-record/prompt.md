# Task: csv-record

Fix `EncodeRecord` in solution.go. Only modify solution.go, keep its public signature,
use only Go's standard library, and do not change go.mod or the visible tests.

Encode fields as one CSV record with a final LF, matching encoding/csv.Writer's
default behavior. Commas, quotes, newlines, leading spaces and a single empty field
must be handled correctly. nil or an empty slice produces a single LF. Do not use
CRLF as the record terminator. Propagate writer errors if any.

Run the visible tests and explain your change briefly. Additional acceptance
tests will be run after the agent exits. They are not in this working directory.
