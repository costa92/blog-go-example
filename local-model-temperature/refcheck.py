import re
from collections import Counter, OrderedDict
from tasks import TASKS
from bench import run_tests
REF = {
"roman": '''
def roman_to_int(s):
    v={'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}; t=0
    for i,c in enumerate(s):
        t += -v[c] if i+1<len(s) and v[c]<v[s[i+1]] else v[c]
    return t''',
"intervals": '''
def merge_intervals(iv):
    out=[]
    for a,b in sorted(iv):
        if out and a<=out[-1][1]: out[-1][1]=max(out[-1][1],b)
        else: out.append([a,b])
    return out''',
"brackets": '''
def is_balanced(s):
    st=[]; p={')':'(',']':'[','}':'{'}
    for c in s:
        if c in '([{': st.append(c)
        elif c in p:
            if not st or st.pop()!=p[c]: return False
    return not st''',
"rle": '''
import re
def rle_decode(s):
    if not re.fullmatch(r'(?:\\d+\\D)*', s, re.S): raise ValueError(s)
    return ''.join(c*int(n) for n,c in re.findall(r'(\\d+)(\\D)', s))''',
"topk": '''
from collections import Counter
def top_k_words(w,k):
    c=Counter(w); return sorted(c,key=lambda x:(-c[x],x))[:k]''',
"lru": '''
from collections import OrderedDict
class LRUCache:
    def __init__(self,c): self.c=c; self.d=OrderedDict()
    def get(self,k):
        if k not in self.d: return -1
        self.d.move_to_end(k); return self.d[k]
    def put(self,k,v):
        self.d[k]=v; self.d.move_to_end(k)
        if len(self.d)>self.c: self.d.popitem(last=False)''',
"duration": '''
import re
def parse_duration(s):
    m=re.fullmatch(r'(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?', s)
    if not s or not m: raise ValueError(s)
    h,mi,se=(int(x or 0) for x in m.groups()); return h*3600+mi*60+se''',
"spiral": '''
def spiral_order(m):
    out=[]
    while m:
        out+=m.pop(0); m=[list(r) for r in zip(*m)][::-1]
    return out''',
"wrap": '''
def wrap(text,width):
    lines=[]; cur=''
    for w in text.split():
        if not cur: cur=w
        elif len(cur)+1+len(w)<=width: cur+=' '+w
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines''',
"semver": '''
def compare_versions(a,b):
    x=[int(p) for p in a.split('.')]; y=[int(p) for p in b.split('.')]
    n=max(len(x),len(y)); x+=[0]*(n-len(x)); y+=[0]*(n-len(y))
    return (x>y)-(x<y)''',
}
for t in TASKS:
    print(t["id"], run_tests(REF[t["id"]], t["tests"]))
