"""生成题库 tasks.jsonl：简单、中等、困难各 50 题，每题带标准答案和答案类型。
输出是确定的（固定随机种子），重跑结果逐字节相同。"""
import datetime as dt
import json
import random

R = random.Random(20261124)
NAMES = ["张伟", "李娜", "王芳", "刘洋", "陈静", "杨磊", "赵敏", "黄强", "周婷", "吴昊"]
CITIES = ["杭州", "成都", "武汉", "西安", "南京", "苏州", "长沙", "青岛"]
WEEK = "一二三四五六日"
WORDS = ["green apple", "blue river", "quiet morning", "fast train", "open window",
         "silver coin", "late night", "paper boat", "cold coffee", "small garden"]
TAIL = "\n\n可以先写推理过程。回答的最后单独写一行，以「答案：」开头，冒号后面直接写结果。"
tasks = []


def add(tier, kind, q, ans, typ, **extra):
    tasks.append(dict(id=f"{tier[0]}{len([t for t in tasks if t['tier'] == tier]) + 1:02d}",
                      tier=tier, kind=kind, prompt=q + TAIL, answer=ans, type=typ, **extra))


def rdate(y0=2024, y1=2027):
    start = dt.date(y0, 1, 1)
    return start + dt.timedelta(days=R.randrange((dt.date(y1, 1, 1) - start).days))


# ---------- 简单 ----------
for _ in range(10):
    d = rdate()
    add("easy", "date_fmt", f"把日期「{d.year}年{d.month}月{d.day}日」改写成 YYYY-MM-DD 格式。", d.isoformat(), "date")
for _ in range(10):
    a, b, c = R.randint(10, 99), R.randint(10, 99), R.randint(10, 60)
    add("easy", "arith", f"{a} + {b} - {c} 等于多少？", a + b - c, "number")
for _ in range(10):
    oid, name, city, amt = f"A{R.randint(1000, 9999)}", R.choice(NAMES), R.choice(CITIES), R.randint(20, 900)
    field, ans, typ = R.choice([("客户", name, "name"), ("城市", city, "city"), ("金额（元）", amt, "number")])
    add("easy", "extract", f"订单记录：编号 {oid}，客户 {name}，城市 {city}，金额 {amt} 元。这条记录的{field}是什么？", ans, typ)
for _ in range(10):
    h, m = R.randint(1, 9), R.randint(5, 55)
    add("easy", "unit", f"{h} 小时 {m} 分钟一共是多少分钟？", h * 60 + m, "number")
for w in WORDS:
    add("easy", "upper", f"把这个英文短语全部改成大写字母：{w}", w.upper(), "upper")

# ---------- 中等 ----------
for _ in range(10):
    a, b, c, d = R.randint(6, 24), R.randint(3, 9), R.randint(5, 30), R.randint(5, 40)
    add("medium", "word", f"每箱有 {a} 瓶水。小王买了 {b} 箱，送给邻居 {c} 瓶，后来又单独买了 {d} 瓶。他现在一共有多少瓶水？",
        a * b - c + d, "number")
for _ in range(10):
    nums = [R.randint(1, 99) for _ in range(12)]
    t = R.randint(30, 60)
    add("medium", "count", f"下面这些数里，大于 {t} 的偶数有几个？\n{', '.join(map(str, nums))}",
        sum(1 for x in nums if x > t and x % 2 == 0), "number")
for _ in range(10):
    d, n = rdate(), R.randint(9, 45)
    add("medium", "weekday", f"{d.year}年{d.month}月{d.day}日是星期{WEEK[d.weekday()]}。那么 {n} 天之后是星期几？",
        "星期" + WEEK[(d + dt.timedelta(days=n)).weekday()], "weekday")
for _ in range(10):
    name, age, city = R.choice(NAMES), R.randint(19, 65), R.choice(CITIES)
    s = R.choice([f"{name}今年{age}岁，目前在{city}工作。", f"来自{city}的{name}说，自己已经{age}岁了。",
                  f"{age}岁那年，{name}搬到了{city}，现在仍住在那里。"])
    add("medium", "json", f"从下面这句话里抽取姓名、年龄和城市，写成 JSON 对象，键名用 name、age、city，age 是整数。JSON 写在答案行里，不要换行。\n「{s}」",
        dict(name=name, age=age, city=city), "json")
for _ in range(10):
    while True:
        p, k, c = R.randrange(80, 600, 10), R.choice([6, 7, 8, 9]), R.randrange(5, 50, 5)
        if p * k % 10 == 0:
            break
    add("medium", "discount", f"一件商品原价 {p} 元，先打 {k} 折，再用一张满减券减 {c} 元。实际要付多少元？",
        p * k // 10 - c, "number")

# ---------- 困难 ----------
for _ in range(10):
    a = rdate(2025, 2026)
    b = a + dt.timedelta(days=R.randint(70, 300))
    add("hard", "days_between", f"从 {a.year}年{a.month}月{a.day}日 到 {b.year}年{b.month}月{b.day}日，两个日期相差多少天？（直接用后一个日期减前一个日期）",
        (b - a).days, "number")
for _ in range(10):
    rows = [(f"D{100 + i}", R.choice(CITIES[:3]), R.choice(["已发货", "待发货", "已取消"]),
             R.randint(1, 9), R.randrange(15, 200, 5)) for i in range(8)]
    c = R.choice(sorted({ci for _, ci, st, _, _ in rows if st == "已发货"}))   # 保证至少有一单符合
    table = "\n".join(["| 订单 | 城市 | 状态 | 数量 | 单价 |", "|---|---|---|---|---|"] +
                      [f"| {o} | {ci} | {st} | {q} | {pr} |" for o, ci, st, q, pr in rows])
    add("hard", "table", f"下面是订单表：\n{table}\n\n城市是{c}、并且状态是已发货的订单，总金额（每单数量×单价，再求和）是多少元？",
        sum(q * pr for _, ci, st, q, pr in rows if ci == c and st == "已发货"), "number")
for _ in range(10):
    people = R.sample(NAMES, 5)            # 从高到矮
    facts = [f"{people[i]}比{people[i + 1]}高" for i in range(4)]
    R.shuffle(facts)
    rank, label = R.choice([(1, "第二高"), (3, "第二矮"), (2, "身高排在正中间")])
    add("hard", "order", f"有五个人：{'、'.join(sorted(people))}。已知：{'；'.join(facts)}。谁{label}？",
        people[rank], "name")
for _ in range(10):
    a, b, c, d = R.randrange(100, 500, 10), R.randint(3, 8), R.randrange(12, 40, 2), R.randint(10, 60)
    add("hard", "multi_step", f"仓库原有 {a} 件货。周一入库 {b} 箱，每箱 {c} 件；周二出库的数量正好是周一入库量的一半；周三又出库 {d} 件，同时退回入库 {d // 2} 件。周三结束时仓库还有多少件？",
        a + b * c - b * c // 2 - d + d // 2, "number")
for _ in range(10):
    h, m = R.randint(8, 15), R.choice([0, 10, 15, 20, 30, 40, 45])
    parts, rest = [R.randrange(15, 55, 5) for _ in range(R.randint(3, 4))], R.choice([5, 10, 15])
    end = dt.datetime(2026, 1, 1, h, m) + dt.timedelta(minutes=sum(parts) + rest * (len(parts) - 1))
    add("hard", "schedule", f"一场会议 {h:02d}:{m:02d} 开始，依次有 {len(parts)} 个议程，分别用时 {'、'.join(map(str, parts))} 分钟，每两个相邻议程之间休息 {rest} 分钟。会议几点结束？用 HH:MM 回答。",
        end.strftime("%H:%M"), "time")

with open("tasks.jsonl", "w") as f:
    for t in tasks:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
print(len(tasks), "tasks")
