import json, urllib.request, urllib.error, time, os
BASE = 'http://127.0.0.1:11434'
OUT = os.path.dirname(os.path.abspath(__file__))

def post(path, body, raw=False):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read().decode(); code = r.status
    except urllib.error.HTTPError as e:
        data = e.read().decode(); code = e.code
    dt = time.time() - t
    if raw:
        return code, data, dt
    try:
        return code, json.loads(data), dt
    except Exception:
        return code, data, dt

def save(name, obj):
    with open(os.path.join(OUT, name), 'w') as f:
        if isinstance(obj, str): f.write(obj)
        else: json.dump(obj, f, ensure_ascii=False, indent=1)

def ps():
    return os.popen('ollama ps').read()
