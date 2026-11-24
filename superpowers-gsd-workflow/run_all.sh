#!/usr/bin/env bash
# 按文章里的顺序重跑一遍。需要已装好 Superpowers 插件和 GSD（get-shit-done-cc 1.42.3）。
# 会调用付费 API，整套在 2026-11-24 花了约 4.4 美元。
set -eu
here=$(cd "$(dirname "$0")" && pwd)
W=${WORK:-$here/work}
rm -rf "$W"; mkdir -p "$W"
NOTE='I am running you non-interactively and cannot answer questions: wherever a skill or workflow would ask me to choose, take the recommended option and continue. Do not push or open PRs.'
PLAN=docs/superpowers/plans/2026-11-24-top-flag.md   # 文件名带日期，重跑时按实际生成的改

# 0. 基础项目
cp -a "$here/tally" "$W/p1"
(cd "$W/p1" && git init -q && git config user.name demo && git config user.email demo@example.com \
  && git add -A && git commit -qm "init tally")

# 1. brainstorming + writing-plans
"$here/run.sh" "$W/p1" 01-brainstorm-plan "Use the superpowers:brainstorming skill, then the superpowers:writing-plans skill, for this feature: add a \`-top N\` flag to the tally CLI that, after the line/word counts, prints the N most frequent words (case-insensitive, ties broken alphabetically), one per line as \"word count\". N=0 (default) keeps current output unchanged. I am running you non-interactively and cannot answer questions: where brainstorming would ask me something, pick the option you would recommend, state it in the design doc, and continue. Do not implement any code; stop after the plan file is written and committed."
PLAN=$(cd "$W/p1" && ls docs/superpowers/plans/*.md | head -1)

# 2. 没有 .planning/ 时导入
cp -a "$W/p1" "$W/g0"
"$here/run.sh" "$W/g0" 02-import-no-planning "/gsd-import --from $PLAN"

# 3. 有 ROADMAP、不指定 phase
cp -a "$W/p1" "$W/g1"; cp -a "$here/planning-seed/.planning" "$W/g1/"
(cd "$W/g1" && git add .planning && git commit -qm "planning: seed roadmap")
cp -a "$W/g1" "$W/g5"
"$here/run.sh" "$W/g1" 03-import-with-roadmap "/gsd-import --from $PLAN"

# 4. 指定一个 ROADMAP 里没有的 phase
"$here/run.sh" "$W/g5" 04-import-phase5 "/gsd-import --from $PLAN 导入到 Phase 5"

# 5. 回答第 3 步留下的问题，让导入走完（提示词见 README）
#    这一步的提示词依赖第 3 步 plan-checker 的具体输出，需要按实际结果改写。

# 6. 两种执行方式，各跑若干次
for i in 1 2; do
  cp -a "$W/g1" "$W/exec-gsd-$i"; cp -a "$W/p1" "$W/exec-sp-$i"
  "$here/run.sh" "$W/exec-gsd-$i" "1$i-exec-gsd-$i" "/gsd-execute-phase 2
$NOTE"
  "$here/run.sh" "$W/exec-sp-$i" "2$i-exec-sp-$i" "Use the superpowers:executing-plans skill to execute $PLAN.
$NOTE"
  (cd "$W/exec-gsd-$i" && go test -count=1 ./...)
  (cd "$W/exec-sp-$i" && go test -count=1 ./...)
done
