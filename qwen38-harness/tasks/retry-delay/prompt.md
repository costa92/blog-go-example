# Task: retry-delay

Fix `Delay` in solution.go. Only modify solution.go, keep its public signature,
use only Go's standard library, and do not change go.mod or the visible tests.

Attempt numbering starts at 1: delay is base * 2^(attempt-1), capped at limit.
Return zero if attempt, base or limit is nonpositive. Avoid time.Duration overflow
and avoid a loop proportional to attempt when it is very large. If base exceeds
limit, return limit. No random jitter is required.

Run the visible tests and explain your change briefly. Additional acceptance
tests will be run after the agent exits. They are not in this working directory.
