#!/bin/sh
# usage: batch.sh MODEL PART [extra run.py args]   (wrap each call in your GPU lock)
# PART a: grid N=5,10,20 + neighbour-free N=5,10   b: grid N=50,100
#      c: correct tool first/last at N=50,100 + Ollama's default context at N=50,100
#      d: one-line descriptions plus enums only, N=20,100
set -e
m=$1; part=$2; shift 2
tag=$(echo "$m" | tr ':/' '__')
case $part in
a) python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 5,10,20 "$@"
   python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 5,10 --nb 0 "$@" ;;
b) python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 50,100 "$@" ;;
c) python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 50,100 --level short --order first,last "$@"
   python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 50,100 --level full --num-ctx 0 "$@" ;;
d) python3 run.py --model "$m" --out "logs/$tag.jsonl" --n 20,100 --level enum "$@" ;;
esac
