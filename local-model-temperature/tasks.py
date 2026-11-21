TASKS = [
    {
        "id": "roman",
        "prompt": "Write a Python function `roman_to_int(s: str) -> int` that converts a Roman numeral (I, V, X, L, C, D, M, with subtractive forms like IV, IX, XL, XC, CD, CM) to an integer.",
        "tests": """
assert roman_to_int('III') == 3
assert roman_to_int('IV') == 4
assert roman_to_int('IX') == 9
assert roman_to_int('LVIII') == 58
assert roman_to_int('MCMXCIV') == 1994
assert roman_to_int('MMMCMXCIX') == 3999
""",
    },
    {
        "id": "intervals",
        "prompt": "Write a Python function `merge_intervals(intervals: list[list[int]]) -> list[list[int]]` that merges overlapping closed intervals. Intervals that only touch (e.g. [1,2] and [2,3]) count as overlapping. The input may be unsorted; return the merged intervals sorted by start. Do not modify the input list.",
        "tests": """
assert merge_intervals([]) == []
assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]
assert merge_intervals([[1,2],[2,3]]) == [[1,3]]
assert merge_intervals([[5,7],[1,2]]) == [[1,2],[5,7]]
assert merge_intervals([[1,10],[2,3],[4,5]]) == [[1,10]]
x = [[3,4],[1,2]]
merge_intervals(x)
assert x == [[3,4],[1,2]]
""",
    },
    {
        "id": "brackets",
        "prompt": "Write a Python function `is_balanced(s: str) -> bool` that returns True if every bracket among (), [] and {} in the string is correctly matched and nested. All other characters must be ignored.",
        "tests": """
assert is_balanced('') is True
assert is_balanced('a(b)c[d]{e}') is True
assert is_balanced('([{}])') is True
assert is_balanced('([)]') is False
assert is_balanced('(((') is False
assert is_balanced('}') is False
assert is_balanced('print(x[0] + {1: 2}[1])') is True
""",
    },
    {
        "id": "rle",
        "prompt": "Write a Python function `rle_decode(s: str) -> str` that decodes a run-length encoded string where each run is a count followed by one character, e.g. '3a2b1c' -> 'aaabbc'. Counts can have multiple digits ('12x' -> 12 x's). If the string is malformed (e.g. ends with digits, or a character has no count), raise ValueError.",
        "tests": """
assert rle_decode('') == ''
assert rle_decode('3a2b1c') == 'aaabbc'
assert rle_decode('12x') == 'x' * 12
assert rle_decode('1 2!') == ' !!'
for bad in ['3', 'a', '3ab', '2a3']:
    try:
        rle_decode(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
""",
    },
    {
        "id": "topk",
        "prompt": "Write a Python function `top_k_words(words: list[str], k: int) -> list[str]` that returns the k most frequent words, ordered by frequency descending; words with the same frequency are ordered alphabetically ascending. If k exceeds the number of distinct words, return all of them.",
        "tests": """
assert top_k_words(['i','love','leetcode','i','love','coding'], 2) == ['i','love']
assert top_k_words(['the','day','is','sunny','the','the','the','sunny','is','is'], 4) == ['the','is','sunny','day']
assert top_k_words(['b','a','c'], 2) == ['a','b']
assert top_k_words(['x'], 5) == ['x']
""",
    },
    {
        "id": "lru",
        "prompt": "Write a Python class `LRUCache` with `__init__(self, capacity: int)`, `get(self, key) -> int` returning the value or -1 if absent, and `put(self, key, value) -> None`. When inserting beyond capacity, evict the least recently used key. Both get and put of an existing key count as a use.",
        "tests": """
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(4, 4)
assert c.get(1) == -1
assert c.get(3) == 3
assert c.get(4) == 4
d = LRUCache(2)
d.put(1, 1); d.put(2, 2); d.put(1, 10); d.put(3, 3)
assert d.get(1) == 10
assert d.get(2) == -1
""",
    },
    {
        "id": "duration",
        "prompt": "Write a Python function `parse_duration(s: str) -> int` that parses strings like '1h30m15s', '45m', '2h', '10s', '1h5s' into a number of seconds. Units must appear in the order h, m, s, each at most once, each with a non-negative integer. Raise ValueError for an empty string, unknown units, wrong order, repeated units or missing numbers.",
        "tests": """
assert parse_duration('1h30m15s') == 5415
assert parse_duration('45m') == 2700
assert parse_duration('2h') == 7200
assert parse_duration('1h5s') == 3605
assert parse_duration('0s') == 0
for bad in ['', '5', 'h', '1d', '1m1h', '1h1h', '1x', 'm5']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
""",
    },
    {
        "id": "spiral",
        "prompt": "Write a Python function `spiral_order(matrix: list[list[int]]) -> list[int]` that returns the elements of an m x n matrix in clockwise spiral order starting from the top-left. An empty matrix returns [].",
        "tests": """
assert spiral_order([]) == []
assert spiral_order([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]
assert spiral_order([[1,2,3,4],[5,6,7,8],[9,10,11,12]]) == [1,2,3,4,8,12,11,10,9,5,6,7]
assert spiral_order([[1],[2],[3]]) == [1,2,3]
assert spiral_order([[1,2,3]]) == [1,2,3]
""",
    },
    {
        "id": "wrap",
        "prompt": "Write a Python function `wrap(text: str, width: int) -> list[str]` that greedily word-wraps text into lines of at most `width` characters. Words are separated by any whitespace; lines join words with single spaces and have no leading or trailing spaces. A word longer than width goes alone on its own line, unsplit. Empty or whitespace-only text returns [].",
        "tests": """
assert wrap('', 10) == []
assert wrap('   ', 10) == []
assert wrap('the quick brown fox', 10) == ['the quick', 'brown fox']
assert wrap('a b c d', 3) == ['a b', 'c d']
assert wrap('hello   world', 11) == ['hello world']
assert wrap('tiny supercalifragilistic ok', 5) == ['tiny', 'supercalifragilistic', 'ok']
assert wrap('one\\ntwo three', 7) == ['one two', 'three']
""",
    },
    {
        "id": "semver",
        "prompt": "Write a Python function `compare_versions(a: str, b: str) -> int` comparing dotted version strings like '1.2.10' and '1.2.9' numerically part by part. Missing parts count as 0 (so '1.0' equals '1'). Return -1 if a < b, 0 if equal, 1 if a > b.",
        "tests": """
assert compare_versions('1.2.10', '1.2.9') == 1
assert compare_versions('1.0', '1') == 0
assert compare_versions('1.0.0.0', '1') == 0
assert compare_versions('0.9', '1.0') == -1
assert compare_versions('2.01', '2.1') == 0
assert compare_versions('10.0', '9.99') == 1
""",
    },
]

SYSTEM = "You are a Python coding assistant."
SUFFIX = "\n\nReply with only the code in a single ```python block: no explanation, no example usage, no tests."
