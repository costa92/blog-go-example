#!/usr/bin/env python3
"""chatstats.py CLIENT_LOG... : one row per request from client.sh logs (/api/chat bodies).
Columns: time, http code, curl total s, load s, prompt tokens @ tok/s, eval tokens @ tok/s, or the error."""
import re, sys
def num(k, s):
    m = re.search(r'"%s":(\d+)' % k, s); return int(m.group(1)) if m else None
for path in sys.argv[1:]:
    print('==', path)
    for line in open(path):
        ts, _, rest = line.rstrip('\n').partition(' ')
        parts = rest.split(' ', 2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        code, tt = parts[0], float(parts[1]); body = parts[2] if len(parts) > 2 else ''
        e = re.search(r'"error":"([^"]*)"', body)
        if e or num('eval_count', body) is None:
            print(f'{ts[11:23]} {code} {tt:7.2f} {("error=" + e.group(1)) if e else body[:80]}'); continue
        ld = num('load_duration', body) / 1e9
        pc, pd = num('prompt_eval_count', body) or 0, (num('prompt_eval_duration', body) or 0) / 1e9
        ec, ed = num('eval_count', body), num('eval_duration', body) / 1e9
        print(f'{ts[11:23]} {code} {tt:7.2f} load={ld:6.2f}s prompt={pc}@{pc/pd if pd else 0:6.1f}t/s eval={ec}@{ec/ed if ed else 0:6.1f}t/s')
