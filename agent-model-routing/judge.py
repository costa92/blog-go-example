"""判分和格式校验，grade.py、cascade.py 共用。

correct(t, out)  按标准答案判对错。JSON 必须写在答案行同一行（文章的主口径）。
correct_lenient  同上，但 JSON 题取整段输出里最后一个 {...}，允许拆成多行、不写答案行。
valid(t, out)    不看标准答案，只检查答案行在不在、类型对不对：这是路由时能拿到的「外部信号」。
"""
import json
import re

ANS = re.compile(r"答案\s*[：:]\s*(.+)")
CONF = re.compile(r"把握\s*[：:]\s*<?\s*(\d{1,3})")
WEEK = "一二三四五六日"
CITIES = ["杭州", "成都", "武汉", "西安", "南京", "苏州", "长沙", "青岛"]


def has_answer_line(out):
    return bool(ANS.findall(out or ""))


def answer_line(out):
    """取最后一个「答案：」行；没有就退回到最后一个非空、非代码围栏、非「把握：」的行（只答一个名字之类）。"""
    m = ANS.findall(out or "")
    if m:
        a = m[-1]
    else:
        lines = [l.strip() for l in (out or "").splitlines() if l.strip() and not l.strip().startswith("```") and not CONF.search(l)]
        if not lines:
            return None
        a = lines[-1]
    a = a.strip().strip("「」『』<>\"'`*").strip()
    return a.rstrip("。.").strip() or None


def confidence(out):
    m = CONF.findall(out or "")
    return min(int(m[-1]), 100) if m else None


def _num(a):
    m = re.findall(r"-?\d+(?:\.\d+)?", a.replace(",", "").replace("，", ""))
    return float(m[-1]) if m else None     # 「9小时45分钟 = 585分钟」取最后一个数


def _week(a):
    m = re.search(r"(?:星期|周|礼拜)([一二三四五六日天])", a)
    return "星期" + ("日" if m.group(1) == "天" else m.group(1)) if m else None


def _json(a):
    m = re.search(r"\{.*\}", a)
    if not m:
        return None
    try:
        v = json.loads(m.group())
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _date(a):
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", a)
    return m.group() if m else None


def _time(a):
    m = re.search(r"\b(\d{1,2})[:：](\d{2})\b", a)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _names(t):
    m = re.search(r"有五个人：(.*?)。", t["prompt"])
    return m.group(1).split("、") if m else None


def valid(t, out):
    a = answer_line(out)
    if a is None:
        return False
    typ = t["type"]
    if typ == "number":
        return _num(a) is not None
    if typ == "date":
        return _date(a) is not None
    if typ == "time":
        return _time(a) is not None
    if typ == "weekday":
        return _week(a) is not None
    if typ == "upper":
        return re.fullmatch(r"[A-Z ]+", a) is not None
    if typ == "json":
        v = _json(a)
        return v is not None and set(v) == {"name", "age", "city"} and isinstance(v["age"], int)
    if typ == "city":
        return a in CITIES
    if typ == "name":    # 只能是题面里出现过的名字
        return a in (_names(t) or []) or (t["kind"] != "order" and re.fullmatch(r"[一-鿿]{2,3}", a) is not None)
    raise ValueError(typ)


def correct(t, out):
    a = answer_line(out)
    if a is None:
        return False
    typ, gold = t["type"], t["answer"]
    if typ == "number":
        n = _num(a)
        return n is not None and abs(n - gold) < 1e-6
    if typ == "date":
        return _date(a) == gold
    if typ == "time":
        return _time(a) == gold
    if typ == "weekday":
        return _week(a) == gold
    if typ == "upper":
        return a == gold
    if typ == "json":
        return _json(a) == gold
    return a == gold          # name / city


def correct_lenient(t, out):
    if t["type"] != "json":
        return correct(t, out)
    for m in reversed(re.findall(r"\{[^{}]*\}", out or "", re.S)):
        try:
            return json.loads(m) == t["answer"]
        except ValueError:
            continue
    return False


def by_fallback(out):
    """没有「答案：」行、判分用的是最后一个非空行。"""
    return not has_answer_line(out) and answer_line(out) is not None


def canon(t, out):
    """按题型把答案归一化，用来比较几次采样是否一致（「62」和「62瓶」算同一个答案）。"""
    a = answer_line(out)
    if a is None:
        return None
    f = {"number": _num, "date": _date, "time": _time, "weekday": _week}.get(t["type"])
    if f:
        return f(a)
    if t["type"] == "json":
        v = _json(a)
        return json.dumps(v, sort_keys=True, ensure_ascii=False) if v is not None else None
    return a
