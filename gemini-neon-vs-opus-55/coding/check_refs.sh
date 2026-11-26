#!/usr/bin/env bash
# Runs each task's hidden tests against its reference solution in an isolated temp module.
# Usage: ./check_refs.sh [task ...]   (default: all tasks)
set -u
cd "$(dirname "$0")"
tasks=("$@")
if [ ${#tasks[@]} -eq 0 ]; then
  for d in */; do [ -f "$d/solution_test.go" ] && tasks+=("${d%/}"); done
fi
fail=0
for t in "${tasks[@]}"; do
  tmp=$(mktemp -d)
  cp "$t/ref/solution.go" "$t/solution_test.go" "$tmp/"
  printf 'module solution\n\ngo 1.27\n' > "$tmp/go.mod"
  if out=$(cd "$tmp" && go test -race -count=1 -timeout 120s 2>&1); then
    echo "PASS $t"
  else
    echo "FAIL $t"
    echo "$out" | tail -n 30 | sed 's/^/    /'
    fail=1
  fi
  rm -rf "$tmp"
done
exit $fail
