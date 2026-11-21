"""生成题库 tasks.jsonl：算术应用题、中文常识、信息抽取成 JSON、Python 小函数。答案都能自动判。"""
import json, random
from pathlib import Path

R = random.Random(20261121)
out = []

# 1. 中文常识：答案为若干可接受写法，命中任一即对
FACTS = [
    ("澳大利亚的首都是哪个城市？", ["堪培拉"]), ("加拿大的首都是哪个城市？", ["渥太华"]),
    ("日本的首都是哪个城市？", ["东京"]), ("法国的首都是哪个城市？", ["巴黎"]),
    ("中国最长的河流是哪条？", ["长江"]), ("地球上面积最大的大洋是哪个？", ["太平洋"]),
    ("世界上国土面积最大的国家是哪个？", ["俄罗斯"]), ("太阳系中最大的行星是哪颗？", ["木星"]),
    ("元素周期表中原子序数为 1 的元素是什么？", ["氢"]), ("水的化学式是什么？", ["H2O", "H₂O"]),
    ("“床前明月光”的下一句是什么？", ["疑是地上霜"]), ("“白日依山尽”的下一句是什么？", ["黄河入海流"]),
    ("“春眠不觉晓”的下一句是什么？", ["处处闻啼鸟"]), ("“举头望明月”的下一句是什么？", ["低头思故乡"]),
    ("“锄禾日当午”的下一句是什么？", ["汗滴禾下土"]), ("“海内存知己”的下一句是什么？", ["天涯若比邻"]),
    ("“谁言寸草心”的下一句是什么？", ["报得三春晖"]), ("“欲穷千里目”的下一句是什么？", ["更上一层楼"]),
    ("《红楼梦》的作者是谁？", ["曹雪芹"]), ("《西游记》的作者是谁？", ["吴承恩"]),
    ("《三国演义》的作者是谁？", ["罗贯中"]), ("《史记》的作者是谁？", ["司马迁"]),
    ("《论语》主要记录了哪位思想家及其弟子的言行？", ["孔子"]), ("《静夜思》的作者是谁？", ["李白"]),
    ("《春望》“国破山河在”的作者是谁？", ["杜甫"]), ("唐朝的都城是哪里？", ["长安"]),
    ("第一个统一中国的封建王朝是哪个朝代？", ["秦"]), ("二十四节气中的第一个节气是什么？", ["立春"]),
    ("中秋节是农历几月几日？", ["八月十五"]), ("端午节是农历几月初几？", ["五月初五"]),
    ("成语“画蛇添_”空缺的字是什么？", ["足"]), ("成语“守株待_”空缺的字是什么？", ["兔"]),
    ("成语“亡羊补_”空缺的字是什么？", ["牢"]), ("成语“掩耳盗_”空缺的字是什么？", ["铃"]),
    ("成语“对牛弹_”空缺的字是什么？", ["琴"]), ("成语“井底之_”空缺的字是什么？", ["蛙"]),
    ("成语“胸有成_”空缺的字是什么？", ["竹"]), ("成语“破釜沉_”空缺的字是什么？", ["舟"]),
    ("计算机中 1 个字节等于多少个二进制位？", ["8", "八"]), ("HTTP 状态码 404 表示什么？", ["未找到", "找不到", "Not Found", "not found", "不存在"]),
    ("一个直角是多少度？", ["90", "九十"]), ("一千克等于多少克？", ["1000", "一千"]),
    ("珠穆朗玛峰位于中国和哪个国家的边境上？", ["尼泊尔"]), ("光在真空中的速度约为每秒多少万公里？", ["30", "三十"]),
    ("世界上人口最多的洲是哪个？", ["亚洲"]),
]
for i, (q, ans) in enumerate(FACTS):
    out.append(dict(id=f"fact-{i:02d}", kind="fact", prompt=q + "只回答答案，不要解释。", answers=ans))

# 2. 算术应用题：两到三步，三位数以内
def mk_arith(i):
    t = i % 6
    a, b, c, d = R.randint(12, 99), R.randint(3, 19), R.randint(6, 48), R.randint(5, 60)
    if t == 0:
        return f"仓库原有 {a*10} 箱货，运来 {b} 车，每车 {c} 箱，又运走 {d} 箱。现在仓库有多少箱？", a*10 + b*c - d
    if t == 1:
        return f"一本书 {a} 元，一支笔 {c} 元。买 {b} 本书和 {b+2} 支笔，付了 {(a*b + c*(b+2)) // 100 * 100 + 200} 元，应找回多少元？", (a*b + c*(b+2)) // 100 * 100 + 200 - (a*b + c*(b+2))
    if t == 2:
        return f"一个长方形长 {a} 米，宽 {c} 米。沿着它的四周每隔 1 米种一棵树，四个角都种，一共种多少棵？", 2 * (a + c)
    if t == 3:
        return f"小王每天读 {c} 页书，读了 {b} 天后还剩 {d} 页没读。这本书一共多少页？", c*b + d
    if t == 4:
        return f"甲班有 {a} 人，乙班比甲班多 {b} 人，丙班人数是乙班的 2 倍少 {d % 20} 人。三个班一共多少人？", a + (a+b) + (2*(a+b) - d % 20)
    return f"一辆车每小时行驶 {c+40} 千米，先行驶了 {b} 小时，又以每小时 {c+20} 千米行驶了 {b+1} 小时。一共行驶多少千米？", (c+40)*b + (c+20)*(b+1)
for i in range(60):
    q, a = mk_arith(i)
    out.append(dict(id=f"arith-{i:02d}", kind="arith", prompt=q + "请一步步计算，最后单独一行写“答案：数字”。", answer=a))

# 3. 信息抽取：句式打乱，total 需要自己算
NAMES = ["张伟", "王芳", "李娜", "刘洋", "陈静", "杨磊", "赵敏", "黄强", "周婷", "吴昊"]
CITIES = ["成都", "杭州", "西安", "武汉", "南京", "长沙", "青岛", "厦门", "昆明", "沈阳"]
ITEMS = ["保温杯", "台灯", "背包", "键盘", "雨伞", "耳机", "水壶", "笔记本"]
TPL = [
    "{name}在{m}月{d}日从{city}下了一单，订单号 {oid}，买了{qty}个{item}，每个 {price} 元。",
    "订单 {oid}：收货城市{city}，{item}{qty}件，单价{price}元，下单人{name}，日期{m}月{d}日。",
    "{m}月{d}日，订单号为 {oid} 的客户{name}购买了{item}，单价 {price} 元，数量 {qty}，寄往{city}。",
    "寄往{city}的包裹里是{qty}个{item}（{price} 元一个），对应订单 {oid}，是{name}{m}月{d}日下的单。",
]
for i in range(40):
    f = dict(name=R.choice(NAMES), city=R.choice(CITIES), item=R.choice(ITEMS), qty=R.randint(2, 12),
             price=R.randint(15, 260), m=R.randint(1, 12), d=R.randint(1, 28), oid=f"SO{R.randint(100000, 999999)}")
    text = TPL[i % 4].format(**f)
    exp = dict(name=f["name"], city=f["city"], order_id=f["oid"], qty=f["qty"], total=f["qty"] * f["price"])
    out.append(dict(id=f"json-{i:02d}", kind="json", expected=exp, prompt=(
        "从下面这句话中抽取信息，只输出一个 JSON 对象，不要其他文字。字段：name（下单人）、city（城市）、"
        "order_id（订单号）、qty（数量，整数）、total（总金额=数量×单价，整数）。\n\n" + text)))

# 4. Python 小函数：每题自带断言
CODE = [
    ("is_pal(s)", "判断字符串是否为回文，忽略大小写和非字母数字字符", "assert is_pal('A man, a plan, a canal: Panama'); assert not is_pal('race a car'); assert is_pal('')"),
    ("rev_words(s)", "把句子中的单词顺序反转，单词之间用一个空格分隔，去掉首尾和多余空格", "assert rev_words('  the sky  is blue ')=='blue is sky the'; assert rev_words('a')=='a'"),
    ("merge(a, b)", "合并两个升序整数列表，返回一个新的升序列表", "assert merge([1,3,5],[2,4,6,8])==[1,2,3,4,5,6,8]; assert merge([],[1])==[1]"),
    ("fib(n)", "返回斐波那契数列第 n 项，fib(0)=0，fib(1)=1，要求 n=90 时也能很快算出", "assert fib(0)==0; assert fib(10)==55; assert fib(90)==2880067194370816120"),
    ("roman(s)", "把罗马数字字符串转成整数", "assert roman('MCMXCIV')==1994; assert roman('LVIII')==58; assert roman('IV')==4"),
    ("is_prime(n)", "判断整数 n 是否为质数，n 小于 2 返回 False", "assert not is_prime(1); assert is_prime(2); assert is_prime(97); assert not is_prime(91)"),
    ("dedup(xs)", "列表去重，保留每个元素第一次出现的顺序", "assert dedup([3,1,3,2,1])==[3,1,2]; assert dedup([])==[]"),
    ("snake(s)", "把驼峰命名转成小写下划线命名，例如 parseHTTPRequest 转成 parse_http_request", "assert snake('parseHTTPRequest')=='parse_http_request'; assert snake('userId')=='user_id'; assert snake('simple')=='simple'"),
    ("bsearch(xs, x)", "在升序列表中二分查找 x，找到返回下标，找不到返回 -1", "assert bsearch([1,3,5,7,9],7)==3; assert bsearch([1,3,5],4)==-1; assert bsearch([],1)==-1"),
    ("balanced(s)", "判断只含 ()[]{} 的字符串括号是否匹配", "assert balanced('([]{})'); assert not balanced('(]'); assert not balanced('(('); assert balanced('')"),
    ("rle(s)", "游程压缩：'aaabcc' 转成 'a3b1c2'，空串返回空串", "assert rle('aaabcc')=='a3b1c2'; assert rle('')==''; assert rle('z')=='z1'"),
    ("max_sub(xs)", "返回非空整数列表的最大连续子数组和", "assert max_sub([-2,1,-3,4,-1,2,1,-5,4])==6; assert max_sub([-3,-1,-2])==-1"),
    ("transpose(m)", "转置一个由列表组成的矩阵（每行长度相同）", "assert transpose([[1,2,3],[4,5,6]])==[[1,4],[2,5],[3,6]]; assert transpose([[1]])==[[1]]"),
    ("hms(sec)", "把秒数转成 'HH:MM:SS' 字符串，小时至少两位", "assert hms(0)=='00:00:00'; assert hms(3661)=='01:01:01'; assert hms(360000)=='100:00:00'"),
    ("count_chars(s)", "返回字典，统计字符串中每个字符出现的次数", "assert count_chars('abca')=={'a':2,'b':1,'c':1}; assert count_chars('')=={}"),
    ("second_max(xs)", "返回列表中第二大的不同数值，不存在时返回 None", "assert second_max([3,1,3,2])==2; assert second_max([5,5])is None; assert second_max([])is None"),
    ("flatten(xs)", "把任意层嵌套的列表展平成一维列表", "assert flatten([1,[2,[3,[4]]],5])==[1,2,3,4,5]; assert flatten([])==[]"),
    ("leap(y)", "判断公历年份是否为闰年", "assert leap(2000); assert not leap(1900); assert leap(2024); assert not leap(2023)"),
    ("digit_sum(n)", "返回非负整数 n 各位数字之和", "assert digit_sum(0)==0; assert digit_sum(98765)==35"),
    ("chunks(xs, k)", "把列表按每 k 个一组切分，最后一组可以不足 k 个", "assert chunks([1,2,3,4,5],2)==[[1,2],[3,4],[5]]; assert chunks([],3)==[]"),
]
for i, (sig, desc, test) in enumerate(CODE):
    out.append(dict(id=f"code-{i:02d}", kind="code", test=test, prompt=(
        f"用 Python 写一个函数 {sig}：{desc}。只输出一个 ```python 代码块，不要解释，不要写测试。")))

Path("tasks.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
print(len(out), {k: sum(x["kind"] == k for x in out) for k in ("fact", "arith", "json", "code")})
