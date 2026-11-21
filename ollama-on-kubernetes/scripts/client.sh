#!/usr/bin/env bash
# Start a curl Pod named ${CLIENT:-kclient} that sends N (default 600) /api/chat
# requests to the ollama Service, SLEEP (default 1) seconds apart, one line each:
#   <http_code> <time_total> <body; bodies over 900 bytes keep the first 300 and last 500 bytes>
# Env: MODEL, N, SLEEP, OPTS (JSON for "options", default {"num_predict":8}), PROMPT, KA (keep_alive field)
set -euo pipefail
cd "$(dirname "$0")"
MODEL=${MODEL:-qwen2.5-coder:0.5b}; N=${N:-600}; SLEEP=${SLEEP:-1}
OPTS=${OPTS:-'{"num_predict":8}'}; PROMPT=${PROMPT:-hi}
ka=""; [[ -n "${KA:-}" ]] && ka=",\"keep_alive\":\"$KA\""
body="{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"stream\":false,\"options\":$OPTS$ka}"
./k delete pod ${CLIENT:-kclient} --ignore-not-found --wait >/dev/null
./k run ${CLIENT:-kclient} --image=curlimages/curl:8.11.1 --restart=Never --command -- sh -c "
i=0; while [ \$i -lt $N ]; do
  r=\$(curl -s -m 600 -o /tmp/b -w '%{http_code} %{time_total}' -d '$body' http://ollama:11434/api/chat)
  if [ \$(wc -c < /tmp/b) -gt 900 ]; then t=\"\$(head -c 300 /tmp/b) ... \$(tail -c 500 /tmp/b)\"; else t=\$(cat /tmp/b); fi; echo \"\$r \$(echo \"\$t\" | tr -d '\n')\"; rm -f /tmp/b; i=\$((i+1)); sleep $SLEEP
done" >/dev/null
