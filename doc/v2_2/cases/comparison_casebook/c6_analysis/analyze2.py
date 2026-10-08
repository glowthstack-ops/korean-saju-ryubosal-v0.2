import json, statistics
from collections import Counter
rows = json.load(open("/tmp/claude-1000/-home-degool-projects-saju-v2/feb89a75-96c0-469c-a6f2-5382e424af59/scratchpad/c6/rows.json"))
def sign(x, eps=0.05): return "+" if x > eps else "-" if x < -eps else "0"
def agree_with(fn, rows):
    out = []
    for r in rows:
        vals = [fn(p["ss"], p["ds"] if p["ds"] is not None else 0.0) for p in r["per"]]
        out.append(sign(statistics.mean(vals)) == r["pol"])
    return out
variants = {
  "세운 단독(w=1.0)": lambda s,d: s,
  "w=0.7": lambda s,d: 0.7*s+0.3*d,
  "w=0.6": lambda s,d: 0.6*s+0.4*d,
  "w=0.5": lambda s,d: 0.5*s+0.5*d,
  "w=0.4": lambda s,d: 0.4*s+0.6*d,
  "w=0.3": lambda s,d: 0.3*s+0.7*d,
  "대운 단독(w=0)": lambda s,d: d,
  "대운지배(|d|>=0.5면 d, 아니면 s)": lambda s,d: d if abs(d)>=0.5 else s,
  "대운지배(|d|>=0.3면 d, 아니면 s)": lambda s,d: d if abs(d)>=0.3 else s,
  "반대부호 완화(반대면 s*0.5+d*0.5, 같으면 s)": lambda s,d: (0.5*s+0.5*d) if s*d<0 else s,
  "반대부호 완화(반대면 s*0.3+d*0.7)": lambda s,d: (0.3*s+0.7*d) if s*d<0 else s,
  "곱셈 게이트 s*(1+d)": lambda s,d: s*(1+d) if s*d>0 else s+d,
}
base = agree_with(variants["세운 단독(w=1.0)"], rows)
print("| 변형 | 일치/43 | 신규 획득 | 기존 상실 |")
print("|---|---|---|---|")
for k, fn in variants.items():
    a = agree_with(fn, rows)
    gained = [f"{r['case'][5:]}/{r['key']}" for r, b, x in zip(rows, base, a) if x and not b]
    lost = [f"{r['case'][5:]}/{r['key']}" for r, b, x in zip(rows, base, a) if b and not x]
    print(f"| {k} | {sum(a)} | {len(gained)}: {' '.join(gained)} | {len(lost)}: {' '.join(lost)} |")

# 단일 연도 + 부정 결과에서 세운 지지 용신 비율
single = [r for r in rows if len(r["per"])==1]
print()
for grp, lab in ((single, "단일연도"),):
    m = [r for r in grp if not r["sew_agree"]]; h = [r for r in grp if r["sew_agree"]]
    print(lab, "miss", len(m), "hit", len(h))
    print(" miss: 세운·대운 부호 반대", sum(1 for r in m if r["per"][0]["ss"]*(r["per"][0]["ds"] or 0)<0),
          "/ 같은 부호", sum(1 for r in m if r["per"][0]["ss"]*(r["per"][0]["ds"] or 0)>0),
          "/ 어느쪽 0", sum(1 for r in m if r["per"][0]["ss"]*(r["per"][0]["ds"] or 0)==0))
    print(" miss |ss|<0.15(중립대 근접)", sum(1 for r in m if abs(r["per"][0]["ss"])<0.15))
    print(" miss 세운 code", Counter(r["per"][0]["code"] for r in m))
    print(" miss rels(원국)", Counter(x.split(':')[0] for r in m for x in r["per"][0]["rels"]))
    print(" hit  rels(원국)", Counter(x.split(':')[0] for r in h for x in r["per"][0]["rels"]))
# 다년 사건: 연도별 부호 분포
print()
for r in rows:
    if len(r["per"])>1 and not r["sew_agree"]:
        c = Counter(sign(p["ss"]) for p in r["per"])
        print(f"{r['case'][5:]}/{r['key']} {r['pol']} {r['when']} n={len(r['per'])} 세운부호분포 {dict(c)} 대운평균 {r['dm']}")
