"""汇总 llama-perplexity 的结果：python3 kld.py  读 logs/kld/*.log"""
import re
from pathlib import Path
ROWS = [("q8_0", "q8_0"), ("q4_K_M", "q4_K_M"), ("self-Q4_K_M", "自己量化 Q4_K_M"), ("imat-Q4_K_M", "imatrix Q4_K_M"),
        ("q3_K_L", "q3_K_L"), ("q3_K_M", "q3_K_M"), ("self-Q3_K_M", "自己量化 Q3_K_M"), ("imat-Q3_K_M", "imatrix Q3_K_M"),
        ("q2_K", "q2_K"), ("self-Q2_K", "自己量化 Q2_K"), ("imat-Q2_K", "imatrix Q2_K")]
def get(name):
    s = Path(f"logs/kld/{name}.log").read_text()
    f = lambda k: float(re.search(k + r"\s*:\s*([\d.]+)", s).group(1))
    return f(r"Mean PPL\(Q\)"), f(r"Mean    KLD"), f(r"Same top p")
def table():
    base = float(re.search(r"Final estimate: PPL = ([\d.]+)", Path("logs/kld/fp16.log").read_text()).group(1))
    return base, [(lab, *get(n)) for n, lab in ROWS]
if __name__ == "__main__":
    base, rows = table()
    print(f"{'版本':18s} {'PPL':>9s} {'KLD':>7s} {'首选 token 同 fp16':>8s}")
    print(f"{'fp16（基准）':16s} {base:9.2f} {'0':>7s} {'100%':>8s}")
    for lab, ppl, kld, same in rows:
        print(f"{lab:16s} {ppl:9.2f} {kld:7.3f} {same:7.1f}%")
