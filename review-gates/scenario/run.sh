#!/usr/bin/env bash
# Replays the hand-off: implement -> approve -> implementer adds an error
# branch -> stale approvals rejected -> re-review -> pass. Then extra
# cases: a change outside the reviewed paths, main moving ahead, rebase.
# Usage: scenario/run.sh [workdir]   (run from review-gates/)
set -euo pipefail

here=$(cd "$(dirname "$0")/.." && pwd)
work=${1:-$(mktemp -d)}
mkdir -p "$work/bin"
(cd "$here" && go build -o "$work/bin/gate" .)
export PATH="$work/bin:$PATH"
export GIT_AUTHOR_NAME=implementer GIT_AUTHOR_EMAIL=implementer@example.com
export GIT_COMMITTER_NAME=implementer GIT_COMMITTER_EMAIL=implementer@example.com

repo="$work/promote"
rm -rf "$repo"
mkdir -p "$repo/promote"
cd "$repo"

say() { printf '\n# %s\n' "$*"; }
# step prints the command, runs it and prints a non-zero exit code.
step() {
	printf '$ %s\n' "$*"
	set +e
	"$@" 2>&1
	local rc=$?
	set -e
	[ $rc -eq 0 ] || printf '[exit %d]\n' "$rc"
}

say "main: spec, config, empty package"
cp "$here/sample/SPEC.md" "$here/sample/go.mod" "$here/sample/review-gates.json" "$here/sample/.gitignore" .
printf '# promote\n' > README.md
printf 'package promote\n' > promote/promote.go
git init -q -b main
git add -A && git commit -qm "spec and config"

say "implementer: feature branch"
git switch -q -c promote
rm promote/promote.go
cp "$here/sample/promote/"*.go promote/
git add -A && git commit -qm "promote: implement switch with intent file"
step git log --oneline

say "reviewer: approve the three gates"
step gate approve design --by reviewer-b
step gate approve tests --by reviewer-b
step gate approve code --by reviewer-b
step cat .review/code.json
step gate merge-check

say "implementer: add an error branch and tweak a test after approval"
git apply "$here/scenario/error-branch.patch"
git commit -qam "promote: treat missing STATUS as blocked"
step git diff --stat HEAD~1
step gate check
step gate merge-check

say "reviewer: re-review the delta, approve tests and code again"
step git diff HEAD~1 -- promote/promote.go
step gate approve tests --by reviewer-b
step gate approve code --by reviewer-b
step gate merge-check

say "implementer: change only README (outside every gate)"
printf '# promote\n\nSwitches current to a restored replica.\n' > README.md
git commit -qam "docs: describe promote"
step gate check
step gate merge-check

say "re-approve code to bind the new tree, then main moves ahead"
step gate approve code --by reviewer-b
git switch -q main
printf 'hotfix\n' > HOTFIX.md
git add -A && git commit -qm "main: unrelated hotfix"
git switch -q promote
step gate merge-check

say "implementer: rebase onto main; the code digest moves with the merge base"
git rebase -q main
step gate check
step gate approve code --by reviewer-b
step gate merge-check
