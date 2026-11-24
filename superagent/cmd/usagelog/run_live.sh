#!/bin/bash
# usage: run_live.sh START END
D="${D:?set D to a work dir containing sa, usagelog and the blog-go-example clone}"
mkdir -p $D/runs && cd $D/blog-go-example
for i in $(seq $1 $2); do
  n=$(printf %02d $i)
  rm -rf $D/runs/live-$n; mkdir -p $D/runs/live-$n
  $D/usagelog -addr 127.0.0.1:18793 -log $D/runs/live-$n.jsonl & P=$!
  sleep 0.5
  t0=$(date +%s)
  GOAGENT_API_KEY="$DEEPSEEK_API_KEY" GOAGENT_BASE_URL=http://127.0.0.1:18793 GOAGENT_MODEL=deepseek-flash \
    $D/sa -mode coding-demo -live -coding-image golang:1.27 -state-dir $D/runs/live-$n > $D/runs/live-$n.out 2> $D/runs/live-$n.err
  ec=$?
  echo "run=$n exit=$ec secs=$(( $(date +%s)-t0 ))" | tee -a $D/runs/summary.txt
  kill $P; wait $P 2>/dev/null
done
