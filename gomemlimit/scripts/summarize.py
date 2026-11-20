#!/usr/bin/env python3
"""Per-run averages over samples with t >= 5s: live, goal, runtime, GC/s, GC CPU, churn."""
import re, sys
from pathlib import Path

PAT = re.compile(r"t=\s*([\d.]+)s live=\s*(\d+)MiB goal=\s*(\d+)MiB runtime=\s*(\d+)MiB gc=\s*(\d+) \(\+\s*(\d+)/s\) "
                 r"gcCPU=\s*([\d.]+)% churn=\s*(\d+)MiB/s cg.cur=(\S+)MiB cg.peak=(\S+)MiB")
for name in sys.argv[1:]:
    log = Path(__file__).resolve().parent.parent / "logs" / f"{name}.log"
    rows = [tuple(map(float, m.groups()[:8])) for m in map(PAT.search, log.read_text().splitlines()) if m]
    steady = [r for r in rows if r[0] >= 5] or rows
    if not steady:
        print(f"{name:16s} no samples"); continue
    avg = lambda i: sum(r[i] for r in steady) / len(steady)
    ev = (Path(__file__).resolve().parent.parent / "logs" / f"{name}.events").read_text()
    m = re.search(r"memory.peak=(\d+)", ev)
    peak = int(m.group(1)) / 2**20 if m else float("nan")
    m = re.search(r"oom_kill (\d+)", ev)
    ook = m.group(1) if m else "-"
    print(f"{name:16s} n={len(steady):3d} live={avg(1):5.0f} goal={avg(2):5.0f} runtime={avg(3):5.0f} "
          f"gc/s={avg(5):5.1f} gcCPU={avg(6):5.1f}% churn={avg(7):6.0f} podPeak={peak:6.1f}MiB oom_kill={ook}")
