#!/usr/bin/env python3
"""One row per log: median over reps of p50/p99/max, throttled periods, GC count.

    python3 scripts/summarize.py logs/*.log
"""
import re
import statistics
import sys
from pathlib import Path

KV = re.compile(r"(\w+)=(\S+)")


def parse(path):
    text = Path(path).read_text()
    procs = re.search(r"GOMAXPROCS=(\d+)", text)
    runs = [dict(KV.findall(l)) for l in text.splitlines() if l.startswith("RESULT ")]
    hists = [dict((k, int(v)) for k, v in re.findall(r"(\S+ms):(\d+)", l))
             for l in text.splitlines() if l.startswith("HIST ")]
    return procs.group(1) if procs else "?", runs, hists


def med(runs, key):
    return statistics.median(float(r[key]) for r in runs)


def main():
    print(f"{'name':22} {'procs':>5} {'n':>2} {'p50':>6} {'p99':>7} {'p99 range':>15} {'max':>7} "
          f"{'thr/per':>9} {'thr_ms':>7} {'cpu%':>5} {'gc':>4} {'>=100ms':>7}")
    for p in sys.argv[1:]:
        procs, runs, hists = parse(p)
        if not runs:
            continue
        dur = 30  # seconds measured per rep (DURATION default)
        p99s = sorted(float(r["p99"]) for r in runs)
        slow = statistics.median(sum(v for k, v in h.items() if int(k.split("-")[0]) >= 100) for h in hists)
        print(f"{Path(p).stem:22} {procs:>5} {len(runs):>2} {med(runs, 'p50'):6.1f} {med(runs, 'p99'):7.1f} "
              f"{p99s[0]:7.1f}-{p99s[-1]:<7.1f} {med(runs, 'max'):7.1f} "
              f"{med(runs, 'throttled'):4.0f}/{med(runs, 'periods'):<4.0f} {med(runs, 'throttled_ms'):7.0f} "
              f"{med(runs, 'usage_ms') / dur / 10:5.1f} {med(runs, 'gc'):4.0f} {slow:7.0f}")


if __name__ == "__main__":
    main()
