"""生成题库 tasks.jsonl：多步应用题、容易记混的常识、带隐藏测试的 Python 函数。答案都能自动判，输出确定。
常识题的可接受写法在第一轮判分后补过一次（坎培拉、伯恩、威灵顿等音译和繁体），见 README。"""
import json, random, re
from pathlib import Path

R = random.Random(20261124)
out = []

# 1. 应用题：三到四步，带折扣、向上取整、余数、星期这类容易错的环节，答案都是整数
def arith(i):
    t = i % 8
    a, b, c, d = R.randint(12, 89), R.randint(3, 9), R.randint(15, 60), R.randint(2, 7)
    if t == 0:
        p = c * 10
        return (f"一件衣服原价 {p} 元，先打八折，再在折后价基础上减 {d * 5} 元。小李买了 {b} 件，"
                f"付给收银员 {(p * 8 // 10 - d * 5) * b // 100 * 100 + 100} 元，应找回多少元？",
                (p * 8 // 10 - d * 5) * b // 100 * 100 + 100 - (p * 8 // 10 - d * 5) * b)
    if t == 1:
        n, k = a * 3 + b, R.randint(11, 17)
        return f"学校组织 {n} 名学生和 {d} 名老师去春游，每辆车最多坐 {k} 人。至少需要几辆车？", -(-(n + d) // k)
    if t == 2:
        days = a * 2 + b
        names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        s = R.randint(0, 6)
        return (f"今天是{names[s]}，再过 {days} 天是星期几？用数字回答，星期一记为 1，星期日记为 7。",
                (s + days) % 7 + 1)
    if t == 3:
        k = R.randint(6, 20)
        return (f"一根绳子长 {4 * d * k} 厘米，先剪去全长的四分之一，再把剩下的平均分成 {d} 段，"
                f"每段还要再剪掉 {d} 厘米。最后每段多长（厘米）？", 3 * k - d)
    if t == 4:
        x = R.randint(5, 15)
        return (f"爸爸今年的年龄是儿子的 {d} 倍，{x} 年后爸爸比儿子大 {(d - 1) * (x + b)} 岁。儿子今年几岁？",
                x + b)
    if t == 5:
        g = R.randint(3, 6)
        return (f"一项工程，甲队单独做要 {g * 4} 天，乙队单独做要 {g * 12} 天。两队合作 {g} 天后，"
                f"剩下的由乙队单独做，乙队还要几天？", 8 * g)
    if t == 6:
        n = a * 10 + c
        return (f"一个数除以 {b + 3} 商 {n} 余 {b + 1}，把这个数加上 {d * 7} 后再除以 {b + 3}，余数是多少？",
                ((b + 3) * n + b + 1 + d * 7) % (b + 3))
    h, m = R.randint(6, 10), R.choice([15, 25, 40, 50])
    dur = c + 75
    end = h * 60 + m + dur
    return (f"一场考试 {h} 点 {m} 分开始，考 {dur} 分钟，中间不休息。结束时是几点几分？用四位数字回答，"
            f"例如 9 点 05 分写成 0905。", int(f"{end // 60:02d}{end % 60:02d}"))

for i in range(48):
    q, ans = arith(i)
    out.append(dict(id=f"arith-{i:02d}", kind="arith", answer=ans,
                    prompt=q + "请一步步计算，最后单独一行写“答案：数字”。"))

# 2. 常识：混了一批常被记错的题（首都、作者、年份）
FACTS = [
    ("澳大利亚的首都是哪个城市？", ["堪培拉", "坎培拉"]), ("土耳其的首都是哪个城市？", ["安卡拉"]),
    ("瑞士的首都是哪个城市？", ["伯尔尼", "伯恩"]), ("新西兰的首都是哪个城市？", ["惠灵顿", "威灵顿", "威靈頓"]),
    ("巴西的首都是哪个城市？", ["巴西利亚", "布拉西利亚"]), ("缅甸现在的首都是哪个城市？", ["内比都"]),
    ("加拿大的首都是哪个城市？", ["渥太华"]), ("南非的立法首都是哪个城市？", ["开普敦", "开普城", "Cape Town", "cape town", "CapeTown"]),
    ("《水浒传》的作者是谁？", ["施耐庵"]), ("《聊斋志异》的作者是谁？", ["蒲松龄"]),
    ("《儒林外史》的作者是谁？", ["吴敬梓"]), ("《哈姆雷特》的作者是谁？", ["莎士比亚"]),
    ("“采菊东篱下”的作者是谁？", ["陶渊明"]), ("“停车坐爱枫林晚”的下一句是什么？", ["霜叶红于二月花"]),
    ("“会当凌绝顶”的作者是谁？", ["杜甫"]), ("“春风又绿江南岸”的作者是谁？", ["王安石"]),
    ("“但愿人长久”的下一句是什么？", ["千里共婵娟"]), ("“人生自古谁无死”的下一句是什么？", ["留取丹心照汗青"]),
    ("世界上最深的湖是哪个？", ["贝加尔"]), ("人体最大的器官是什么？", ["皮肤"]),
    ("非洲最高的山峰是哪座？", ["乞力马扎罗"]), ("中国面积最大的省级行政区是哪个？", ["新疆"]),
    ("成年人体内一共有多少块骨头？", ["206"]), ("金的元素符号是什么？", ["Au"]),
    ("钠的元素符号是什么？", ["Na"]), ("最小的质数是几？", ["2", "二"]),
    ("辛亥革命爆发于哪一年？", ["1911"]), ("八国联军侵华是哪一年？", ["1900"]),
    ("中国第一枚奥运会金牌是谁获得的？", ["许海峰"]), ("元素周期律是谁发现的？", ["门捷列夫"]),
    ("一年中北半球白天最长的节气是哪个？", ["夏至"]), ("杜甫被后人称为什么？", ["诗圣", "詩圣", "詩聖"]),
    ("太阳系中离太阳最近的行星是哪颗？", ["水星"]), ("世界上落差最大的瀑布是哪个？", ["安赫尔", "天使瀑布"]),
    ("世界上面积最大的沙漠（不算南极）是哪个？", ["撒哈拉"]), ("蜀汉的开国皇帝是谁？", ["刘备"]),
    ("“三顾茅庐”中被请的人是谁？", ["诸葛亮"]), ("圆周率小数点后第 5 位数字是几？", ["9", "九"]),
    ("日本的最高峰是哪座山？", ["富士山"]), ("我国四大发明中，哪项最早用于航海指示方向？", ["指南针", "司南"]),
]
for i, (q, ans) in enumerate(FACTS):
    out.append(dict(id=f"fact-{i:02d}", kind="fact", prompt=q + "只回答答案，不要解释。", answers=ans))

# 3. Python 函数：题面给一个例子，判分用题面没写出的边界测试
CODE = [
    ("rev_words(s)", "把句子中的单词顺序反转，单词之间用一个空格分隔，去掉首尾和多余空格。例：rev_words('a b')=='b a'",
     "assert rev_words('  the sky  is blue ')=='blue is sky the'; assert rev_words('   ')==''"),
    ("roman(s)", "把罗马数字字符串转成整数。例：roman('III')==3", "assert roman('MCMXCIV')==1994; assert roman('XLIX')==49"),
    ("to_roman(n)", "把 1 到 3999 的整数转成罗马数字字符串。例：to_roman(3)=='III'", "assert to_roman(1994)=='MCMXCIV'; assert to_roman(3999)=='MMMCMXCIX'; assert to_roman(4)=='IV'"),
    ("snake(s)", "把驼峰命名转成小写下划线命名，连续大写字母算一个单词。例：snake('userId')=='user_id'",
     "assert snake('parseHTTPRequest')=='parse_http_request'; assert snake('HTMLParser')=='html_parser'; assert snake('simple')=='simple'"),
    ("hms(sec)", "把秒数转成 'HH:MM:SS' 字符串，小时至少两位、可以超过 99。例：hms(61)=='00:01:01'",
     "assert hms(0)=='00:00:00'; assert hms(360000)=='100:00:00'; assert hms(86399)=='23:59:59'"),
    ("second_max(xs)", "返回列表中第二大的不同数值，不存在时返回 None。例：second_max([1,2])==1",
     "assert second_max([3,1,3,2])==2; assert second_max([5,5]) is None; assert second_max([]) is None; assert second_max([-1,-2])==-2"),
    ("rle(s)", "游程压缩，每段写成字符加次数。例：rle('aab')=='a2b1'", "assert rle('')==''; assert rle('z')=='z1'; assert rle('aaaaaaaaaaaa')=='a12'"),
    ("unrle(s)", "游程解压，次数可能是多位数。例：unrle('a2b1')=='aab'", "assert unrle('a12b1')=='a'*12+'b'; assert unrle('')==''"),
    ("chunks(xs, k)", "把列表按每 k 个一组切分，最后一组可以不足 k 个。例：chunks([1,2,3],2)==[[1,2],[3]]",
     "assert chunks([],3)==[]; assert chunks([1,2,3,4],2)==[[1,2],[3,4]]"),
    ("flatten(xs)", "把任意层嵌套的列表展平成一维列表，元组不展开。例：flatten([1,[2]])==[1,2]",
     "assert flatten([1,[2,[3,[4]]],5])==[1,2,3,4,5]; assert flatten([(1,2),[3]])==[(1,2),3]; assert flatten([])==[]"),
    ("leap(y)", "判断公历年份是否为闰年。例：leap(2024) 为 True", "assert leap(2000); assert not leap(1900); assert not leap(2023); assert leap(2400)"),
    ("days_between(a, b)", "a、b 是 'YYYY-MM-DD' 字符串，返回两个日期相差的天数（非负）。例：days_between('2024-01-01','2024-01-02')==1",
     "assert days_between('2024-03-01','2024-02-28')==2; assert days_between('2023-03-01','2023-02-28')==1; assert days_between('2020-01-01','2020-01-01')==0"),
    ("median(xs)", "返回非空数字列表的中位数，偶数个时取中间两个的平均值。例：median([3,1,2])==2",
     "assert median([4,1,3,2])==2.5; assert median([5])==5; assert median([1,1,2,9])==1.5"),
    ("word_freq(s)", "统计英文句子里每个单词出现次数，忽略大小写和标点，返回字典。例：word_freq('a a')=={'a':2}",
     "assert word_freq('Hi, hi! HI.')=={'hi':3}; assert word_freq('')=={}"),
    ("parse_kv(s)", "解析 'k1=v1;k2=v2' 格式的字符串为字典，忽略空段，值里可能含 '='。例：parse_kv('a=1')=={'a':'1'}",
     "assert parse_kv('a=1;;b=x=y;')=={'a':'1','b':'x=y'}; assert parse_kv('')=={}"),
    ("int_to_base(n, b)", "把整数 n 转成 b 进制字符串（2<=b<=36，用 0-9a-z），支持负数和 0。例：int_to_base(5,2)=='101'",
     "assert int_to_base(0,2)=='0'; assert int_to_base(-255,16)=='-ff'; assert int_to_base(35,36)=='z'"),
    ("rotate(xs, k)", "把列表向右循环移动 k 位，k 可能大于长度或为负数，返回新列表。例：rotate([1,2,3],1)==[3,1,2]",
     "assert rotate([1,2,3],4)==[3,1,2]; assert rotate([1,2,3],-1)==[2,3,1]; assert rotate([],5)==[]"),
    ("merge_intervals(xs)", "合并重叠区间，输入是 [起,止] 列表、未排序，首尾相接也算重叠，返回按起点排序的列表。例：merge_intervals([[1,3],[2,4]])==[[1,4]]",
     "assert merge_intervals([[5,6],[1,2],[2,3]])==[[1,3],[5,6]]; assert merge_intervals([])==[]; assert merge_intervals([[1,10],[2,3]])==[[1,10]]"),
    ("title_case(s)", "把每个单词首字母大写、其余小写，单词间原有的空格数量保持不变。例：title_case('hi')=='Hi'",
     "assert title_case('hELLO  wORLD')=='Hello  World'; assert title_case(' a')==' A'; assert title_case('')==''"),
    ("is_ipv4(s)", "判断字符串是不是合法的点分十进制 IPv4 地址，每段 0-255、不允许前导零（单个 0 可以）。例：is_ipv4('1.2.3.4') 为 True",
     "assert not is_ipv4('256.1.1.1'); assert not is_ipv4('01.1.1.1'); assert is_ipv4('0.0.0.0'); assert not is_ipv4('1.2.3'); assert not is_ipv4('1.2.3.4.5'); assert not is_ipv4('a.b.c.d')"),
    ("compare_versions(a, b)", "比较 '1.2.10' 这样的版本号，a>b 返回 1，相等返回 0，否则 -1；缺的段按 0 算。例：compare_versions('1.0','1.1')==-1",
     "assert compare_versions('1.2.10','1.2.9')==1; assert compare_versions('1.0','1.0.0')==0; assert compare_versions('2','10')==-1"),
    ("count_islands(g)", "g 是由 '1' 和 '0' 字符串组成的二维列表，返回上下左右相连的 '1' 区域个数。例：count_islands([['1']])==1",
     "assert count_islands([['1','1','0'],['0','1','0'],['1','0','1']])==3; assert count_islands([])==0"),
    ("lcs_len(a, b)", "返回两个字符串最长公共子序列的长度。例：lcs_len('abc','ac')==2",
     "assert lcs_len('abcde','ace')==3; assert lcs_len('','a')==0; assert lcs_len('aaaa','aa')==2"),
    ("top_k(xs, k)", "返回列表中出现次数最多的 k 个元素，次数相同时按元素第一次出现的顺序。例：top_k([1,1,2],1)==[1]",
     "assert top_k([3,1,1,3,2],2)==[3,1]; assert top_k([4,5,6],2)==[4,5]; assert top_k([],1)==[]"),
]
for i, (sig, desc, test) in enumerate(CODE):
    tests = [t.strip() for t in re.split(r";\s*(?=assert\b)", test)]   # 断言字符串里可能有分号，只在 assert 前切
    out.append(dict(id=f"code-{i:02d}", kind="code", test=tests, prompt=(
        f"用 Python 写一个函数 {sig}：{desc}。只输出一个 ```python 代码块，不要解释，不要写测试。")))

Path("tasks.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
print(len(out), {k: sum(x["kind"] == k for x in out) for k in ("arith", "fact", "code")})
