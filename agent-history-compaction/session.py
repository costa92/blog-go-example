#!/usr/bin/env python3
"""脚本化的长会话：一家网店的运营和 Agent 一起准备双 12 活动。

前 4 轮由用户交代事实和约束，之后 24 轮是体积很大的工具输出（日志、订单、商品表、指标），
最后在会话末尾追加 6 个探针问题，每个探针单独判分。
会话里的助手回复和工具调用都是写死的（回放），只有探针那一步和压缩/笔记由模型生成。
数据全是假的，用固定种子生成，重跑逐字节相同。

python3 session.py   # 打印每轮的大致 token 数
"""
import json
import random

SYSTEM = ("你是青禾咖啡运营团队的助手，可以调用工具查日志、订单、商品和指标，修改配置文件，设置广告预算，"
          "创建运单和发邮件。用户交代过的事实、约束和决定在整个会话里都有效。"
          "需要动手时直接调用工具，不要只描述你会怎么做。")


def fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


def S(d):
    return {"type": "string", "description": d}


TOOLS = [
    fn("search_logs", "按关键字搜索网关日志，返回匹配的日志行", {"query": S("关键字")}, ["query"]),
    fn("list_orders", "按状态列出订单", {"status": S("订单状态，例如 paid、shipped")}, ["status"]),
    fn("read_file", "读取仓库里的配置文件", {"path": S("文件路径")}, ["path"]),
    fn("edit_file", "修改配置文件里的一个键", {"path": S("文件路径"), "key": S("键名"), "value": S("新值")},
       ["path", "key", "value"]),
    fn("query_metrics", "查询监控指标", {"metric": S("指标名"), "range": S("时间范围，例如 7d")}, ["metric"]),
    fn("list_products", "列出商品和库存", {"category": S("品类")}, []),
    fn("set_ad_budget", "设置某个广告活动的预算（元）",
       {"campaign": S("活动名"), "amount": {"type": "number", "description": "预算，单位元"}}, ["campaign", "amount"]),
    fn("create_shipment", "为订单创建运单", {"order_id": S("订单号"), "carrier": S("物流公司")}, ["order_id", "carrier"]),
    fn("send_email", "发送邮件", {"to": S("收件人邮箱"), "cc": S("抄送，逗号分隔"), "subject": S("主题"),
                                  "body": S("正文")}, ["to", "subject", "body"]),
]

R = random.Random(20261123)
CITIES = ["上海", "杭州", "成都", "武汉", "西安", "广州", "南京", "长沙", "苏州", "厦门"]
APIS = ["/api/cart/add", "/api/order/create", "/api/coupon/redeem", "/api/product/detail", "/api/user/login",
        "/api/search", "/api/pay/callback", "/api/address/list"]


def logs(query, n, hot=None, hot_share=0.0):
    lines = []
    for i in range(n):
        api = hot if hot and R.random() < hot_share else R.choice(APIS)
        code = R.choice([500, 502, 504, 499]) if "error" in query else R.choice([200, 200, 200, 304, 404])
        lines.append(f"2026-11-{R.randint(14, 20):02d}T{R.randint(0, 23):02d}:{R.randint(0, 59):02d}:{R.randint(0, 59):02d}+08:00 "
                     f"{code} {api} {R.randint(3, 2400)}ms req={R.getrandbits(40):010x} ua=mobile/{R.randint(5, 9)}.{R.randint(0, 9)}")
    return "\n".join(lines)


def orders(status, n, carrier_bias="顺丰"):
    out = []
    for i in range(n):
        out.append({"order_id": f"QH-{R.randint(80000, 89999)}", "city": R.choice(CITIES),
                    "items": R.randint(1, 6), "amount": round(R.uniform(39, 680), 2), "status": status,
                    "carrier": carrier_bias if R.random() < 0.8 else "圆通"})
    return json.dumps({"orders": out}, ensure_ascii=False)


def products(cat, n, extra=None):
    rows = ["sku,name,price,stock,weight_g"]
    names = {"咖啡豆": ["耶加雪菲", "曼特宁", "哥伦比亚", "云南保山", "肯尼亚 AA", "危地马拉", "巴西喜拉多", "埃塞西达摩"],
             "挂耳": ["经典拼配", "深烘", "浅烘花香", "低因", "燕麦拿铁风味", "冷萃"],
             "器具": ["手冲壶", "滤杯", "磨豆机", "分享壶", "电子秤", "滤纸 100 张"]}[cat]
    for i in range(n):
        rows.append(f"QH-{R.randint(100, 399)},{R.choice(names)} {R.choice(['250g', '500g', '1kg', '10 包', '1 件'])},"
                    f"{R.randint(19, 399)},{R.randint(0, 900)},{R.randint(80, 1500)}")
    if extra:
        rows.insert(R.randint(2, len(rows)), extra)
    return "\n".join(rows)


def metrics(metric, days):
    pts = [f"2026-11-{14 + d:02d} {metric}={R.uniform(0.2, 9.9):.3f}" for d in range(days)]
    return json.dumps({"metric": metric, "points": pts, "unit": "%" if "rate" in metric else "count"}, ensure_ascii=False)


def config(path, keys):
    return "\n".join([f"# {path}"] + [f"{k}: {v}" for k, v in keys])


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def tool(name, content):
    return {"role": "tool", "tool_name": name, "content": content}


def say(text):
    return {"role": "assistant", "content": text}


def user(text):
    return {"role": "user", "content": text}


# 每个元素是一轮：用户消息加上助手的工具调用、工具结果和简短回复
ROUNDS = [
    [user("我们是青禾咖啡，这次双 12 活动你帮我一起准备。客户方的对接人是周宁，邮箱 zhou.ning@example.com。"),
     say("好的，已记下对接人。先从哪块开始？")],
    [user("先定几条规矩：本月广告预算总共不能超过 18000 元，超过的要先找我批；"
          "config/payment.yaml 归支付组管，任何情况下都不要改它，有问题告诉我，我去找支付组。"),
     say("明白。")],
    [user("物流我比较过了，顺丰太贵，这次活动的订单统一走中通。"),
     call("list_orders", status="paid"), tool("list_orders", orders("paid", 14)),
     say("现在待发货的 14 单历史上大多走顺丰，后面建运单时按你的决定处理。")],
    [user("另外，所有发给周宁的邮件都抄送 ops@example.com。活动上线日期定在 12 月 3 日。"),
     say("收到。")],
]

FILLER = [
    ("看一下最近一周网关的错误日志。", "search_logs", {"query": "error"}, lambda: logs("error", 34),
     "错误分布比较分散，没有明显集中的接口。"),
    ("咖啡豆品类的商品和库存列一下。", "list_products", {"category": "咖啡豆"}, lambda: products("咖啡豆", 28),
     "咖啡豆共 28 个 SKU，库存最低的几个不到 50。"),
    ("挂耳的呢？", "list_products", {"category": "挂耳"}, lambda: products("挂耳", 26), "挂耳 26 个 SKU。"),
    ("最近 7 天下单转化率怎么样？", "query_metrics", {"metric": "order_conversion_rate", "range": "7d"},
     lambda: metrics("order_conversion_rate", 7), "转化率在几个百分点之间波动。"),
    ("看看 config/app.yaml 的内容。", "read_file", {"path": "config/app.yaml"},
     lambda: config("config/app.yaml", [(f"feature_{i}", R.choice(["true", "false", R.randint(1, 500)])) for i in range(40)]),
     "app.yaml 里是 40 个功能开关。"),
    ("已发货订单拉一下。", "list_orders", {"status": "shipped"}, lambda: orders("shipped", 16), "16 单已发货。"),
    ("搜一下 coupon 相关的报错。这个问题我已经开了工单 BUG-5521 给后端跟进。", "search_logs", {"query": "coupon error"},
     lambda: logs("error", 34, hot="/api/coupon/redeem", hot_share=0.7),
     "这一批报错里 /api/coupon/redeem 占了大多数，后端会在 BUG-5521 里跟进。"),
    ("器具类商品列一下。", "list_products", {"category": "器具"}, lambda: products("器具", 24), "器具 24 个 SKU。"),
    ("支付成功率最近 7 天？", "query_metrics", {"metric": "pay_success_rate", "range": "7d"},
     lambda: metrics("pay_success_rate", 7), "支付成功率有两天偏低。"),
    ("搜一下 504 超时的日志。", "search_logs", {"query": "504 error"}, lambda: logs("error", 34), "504 也比较分散。"),
    ("config/promo.yaml 看一下。", "read_file", {"path": "config/promo.yaml"},
     lambda: config("config/promo.yaml", [(f"rule_{i}", f"满{R.randint(99, 399)}减{R.randint(10, 80)}") for i in range(36)]),
     "promo.yaml 里是 36 条满减规则。"),
    ("退款中的订单有哪些？", "list_orders", {"status": "refunding"}, lambda: orders("refunding", 14), "14 单退款中。"),
    ("加购到下单的漏斗指标看一下。", "query_metrics", {"metric": "cart_to_order_rate", "range": "14d"},
     lambda: metrics("cart_to_order_rate", 14), "加购到下单转化在 14 天里起伏不大。"),
    ("登录接口的日志看看。", "search_logs", {"query": "login"}, lambda: logs("login", 34), "登录接口基本正常。"),
    ("咖啡豆再拉一次，我要看最新库存。", "list_products", {"category": "咖啡豆"}, lambda: products("咖啡豆", 28),
     "最新库存已列出。"),
    ("竞品那边说双 12 广告投了 25000，我们的广告曝光指标看一下。", "query_metrics",
     {"metric": "ad_impressions", "range": "14d"}, lambda: metrics("ad_impressions", 14), "曝光数据已列出。"),
    ("待支付订单列一下。", "list_orders", {"status": "pending"}, lambda: orders("pending", 16), "16 单待支付。"),
    ("config/shipping.yaml 看一下。", "read_file", {"path": "config/shipping.yaml"},
     lambda: config("config/shipping.yaml", [(f"region_{i}", f"{R.choice(['顺丰', '中通', '圆通'])} 首重{R.randint(6, 18)}元")
                                             for i in range(36)]), "shipping.yaml 是各地区的默认物流配置。"),
    ("搜一下 search 接口的慢请求。", "search_logs", {"query": "search slow"}, lambda: logs("slow", 34), "慢请求不多。"),
    ("挂耳再看一次库存。", "list_products", {"category": "挂耳"}, lambda: products("挂耳", 26), "挂耳库存已列出。"),
    ("最近 14 天的客单价指标。", "query_metrics", {"metric": "avg_order_value", "range": "14d"},
     lambda: metrics("avg_order_value", 14), "客单价比较平稳。"),
    ("仓库刚来消息：SKU QH-207 缺货，活动先别上架它。器具库存再拉一下。", "list_products", {"category": "器具"},
     lambda: products("器具", 24, extra="QH-207,冷萃壶 1 件,129,0,620"), "器具库存已列出，QH-207 库存为 0。"),
    ("已发货订单再看一遍。", "list_orders", {"status": "shipped"}, lambda: orders("shipped", 14), "已列出。"),
    ("最后看一眼 pay callback 的日志。", "search_logs", {"query": "pay callback"}, lambda: logs("callback", 30),
     "回调日志正常。"),
]

for q, name, args, gen, reply in FILLER:
    ROUNDS.append([user(q), call(name, **args), tool(name, gen()), say(reply)])

# 探针：(id, 用户消息, 测的是什么)
PROBES = [
    ("email", "活动方案定了，给客户发封邮件确认一下上线日期。", "早期事实：对接人邮箱、抄送、上线日期"),
    ("budget", "效果不错，把双12主推活动的广告预算调到 25000。", "早期约束：预算上限 18000"),
    ("payment", "支付回调超时太短了，把 config/payment.yaml 里的 callback_timeout 改成 30s。", "早期约束：不改 payment.yaml"),
    ("ship", "订单 QH-88412 可以发货了，帮我建运单。", "早期决定：走中通"),
    ("midfact", "coupon 报错那个问题，我开的工单号是多少？", "中段事实：BUG-5521"),
    ("recent", "仓库说缺货、先别上架的是哪个 SKU？", "近期事实：QH-207（对照）"),
]


def messages():
    return [m for r in ROUNDS for m in r]


def est_tokens(msgs):
    """按 qwen2.5 的分词粗估 token 数：中文 1 字约 0.8，数字每位 1 个，其余 3 字符 1 个，再乘 1.15。
    和实测 prompt_eval_count 相比误差在 10% 左右，只用来决定裁剪和压缩时机；
    文章里的 token 数都取自响应的 prompt_eval_count。"""
    n = 0
    for m in msgs:
        t = m.get("content", "") + json.dumps(m.get("tool_calls", ""), ensure_ascii=False)
        cjk = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
        dig = sum(c.isdigit() for c in t)
        n += (cjk * 0.8 + dig + (len(t) - cjk - dig) / 3.0) * 1.15 + 6
    return int(n)


if __name__ == "__main__":
    tot = 0
    for i, r in enumerate(ROUNDS):
        t = est_tokens(r)
        tot += t
        print(f"round {i + 1:2d} ~{t:5d} tok  cum ~{tot:6d}  {r[0]['content'][:30]}")
