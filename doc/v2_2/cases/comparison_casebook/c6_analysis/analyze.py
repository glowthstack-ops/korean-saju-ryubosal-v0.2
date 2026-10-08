"""C6 오프라인 분석 — 세운/대운 luck_score 불일치 분류 + 대운 가중 블렌드 효과 추정 (코드 변경 없음)."""
import json, statistics, sys
from pathlib import Path
sys.path.insert(0, "backend/packages/shared_types")
from saju_shared_types.constants import BRANCH_CLASHES, SIX_COMBINATIONS, THREE_HARMONY, STEM_COMBINATIONS, STEM_ELEMENT, BRANCH_ELEMENT, hidden_stems_for
from saju_shared_types.enums import Branch, Stem

ROOT = Path("/home/degool/projects/saju_v2")
cases = [json.loads(l) for l in (ROOT/"backend/tests/fixtures/comparison_casebook/cases.jsonl").read_text().splitlines() if l.strip()]
subs = {}
for l in (ROOT/"var/casebook_replay/subjects.jsonl").read_text().splitlines():
    if l.strip():
        r = json.loads(l); subs[(r["case_id"], r["key"])] = r

def sign(x, eps=0.05): return "+" if x > eps else "-" if x < -eps else "0"
def age_year(sub, age): return int(sub["date_used"][:4]) + age - 1
def years_for(sub, when):
    if "year" in when: return [int(when["year"])], f"year={when['year']}"
    if "years" in when: return [int(y) for y in when["years"]], f"years={when['years']}"
    if "age" in when and "age_max" in when:
        return list(range(age_year(sub, when["age"]), age_year(sub, when["age_max"])+1)), f"age {when['age']}~{when['age_max']}"
    if "age" in when: return [age_year(sub, when["age"])], f"age={when['age']}"
    if "daewoon" in when:
        g = str(when["daewoon"]).split("/")[0]
        for d in sub.get("daewoon") or []:
            if d["ganji"] == g:
                y0 = int(d["start"][:4]); return list(range(y0, y0+10)), f"daewoon={g}"
        return [], "?"
    if "age_max" in when:
        return list(range(int(sub["date_used"][:4]), age_year(sub, when["age_max"])+1)), f"~age {when['age_max']}"
    return [], "?"

def dw_for_year(sub, y):
    for d in sub["daewoon"]:
        y0 = int(d["start"][:4])
        if y0 <= y < y0+10: return d
    return None

def transition_near(sub, y):
    """사건 연도가 어떤 대운 시작연도 ±1년 이내인가."""
    for d in sub["daewoon"]:
        y0 = int(d["start"][:4])
        if abs(y - y0) <= 1: return d["ganji"], y0
    return None

rows = []
for c in cases:
    for s in c["subjects"]:
        sub = subs.get((c["case_id"], s["key"]))
        for o in s["outcomes"]:
            when = o.get("when"); pol = o["polarity"]
            if pol not in "+-" or not when or not sub or not sub.get("daewoon"): continue
            years, label = years_for(sub, when)
            if not years: continue
            sew = sub["lifetime"]["sewoon"]
            per = []
            for y in years:
                sp = sew.get(str(y)); d = dw_for_year(sub, y)
                if sp is None: continue
                per.append({"y": y, "sg": sp["ganji"], "ss": sp["score"], "code": sp["code"], "rels": sp["rels"],
                            "dg": d["ganji"] if d else None, "ds": d["luck_score"] if d else None})
            if not per: continue
            sm = round(statistics.mean(p["ss"] for p in per), 2)
            dws = [d["luck_score"] for d in sub["daewoon"] if any(int(d["start"][:4]) <= y < int(d["start"][:4])+10 for y in years)]
            dm = round(statistics.mean(dws), 2) if dws else None
            roles = sub["roles"]["final"]
            rows.append({"case": c["case_id"], "key": s["key"], "domain": o["domain"], "text": o["text"], "pol": pol,
                         "when": label, "years": years, "per": per, "sm": sm, "dm": dm, "roles": roles,
                         "sew_agree": sign(sm) == pol, "dw_agree": dm is not None and sign(dm) == pol,
                         "trans": [transition_near(sub, y) for y in years if transition_near(sub, y)]})

print("timed", len(rows), "sew_agree", sum(r["sew_agree"] for r in rows), "dw_agree", sum(r["dw_agree"] for r in rows))

# ── 분류 ──
def classify(r):
    tags = []
    s_sign, d_sign = sign(r["sm"]), (sign(r["dm"]) if r["dm"] is not None else "n/a")
    if not r["sew_agree"]:
        if d_sign == r["pol"]: tags.append("a")            # 세운≠대운, 대운 맞음
        elif d_sign == "0" or d_sign == "n/a": tags.append("c")  # 대운 중립/없음
        else: tags.append("b")                              # 둘 다 틀림
        if r["trans"]: tags.append("d")
        if len(r["per"]) > 1:
            signs = {sign(p["ss"]) for p in r["per"]}
            # 개별 연도 중 결과 극성과 같은 부호가 있는데 평균이 뒤집힘
            if r["pol"] in signs: tags.append("e")
    return tags

for r in rows: r["cls"] = classify(r)

# ── 특징: 세운-대운 지지 충/합, 천간 용신·지지 기신 등 ──
def rel_sew_dw(sg, dg):
    out = []
    sb, db = Branch(sg[1]), Branch(dg[1]); ss, ds = Stem(sg[0]), Stem(dg[0])
    k = frozenset({sb, db})
    if sb != db and k in BRANCH_CLASHES: out.append("지지충")
    if sb != db and k in SIX_COMBINATIONS: out.append("지지육합")
    for mem, el, royal in THREE_HARMONY:
        if sb in mem and db in mem and sb != db: out.append(f"삼합기여:{el}")
    if ss != ds and frozenset({ss, ds}) in STEM_COMBINATIONS: out.append("천간합")
    if sb == db: out.append("지지동")
    if ss == ds: out.append("천간동")
    return out

def stem_branch_dir(sg, roles):
    useful = {roles.get("yongsin"), roles.get("heesin")}; unfav = {roles.get("gisin"), roles.get("gusin")}
    se = str(STEM_ELEMENT[Stem(sg[0])])
    bs = sum(w*(1 if str(STEM_ELEMENT[h]) in useful else -1 if str(STEM_ELEMENT[h]) in unfav else 0) for h,_,w in hidden_stems_for(Branch(sg[1])))
    sd = "용" if se in useful else "기" if se in unfav else "한"
    bd = "용" if bs > 0.15 else "기" if bs < -0.15 else "한"
    return sd, bd

miss = [r for r in rows if not r["sew_agree"]]
hit = [r for r in rows if r["sew_agree"]]
print("miss", len(miss))
from collections import Counter
print("cls counter", Counter(t for r in miss for t in r["cls"]))
print("primary", Counter(r["cls"][0] for r in miss))

# ── 블렌드 ──
def blend_agree(rows, w):
    n = 0
    for r in rows:
        if r["dm"] is None: continue
        # 연도별 블렌드 후 평균(=평균의 블렌드와 동일, 선형)
        vals = [w*p["ss"] + (1-w)*(p["ds"] if p["ds"] is not None else 0.0) for p in r["per"]]
        if sign(statistics.mean(vals)) == r["pol"]: n += 1
    return n
def damp_agree(rows, thr=0.3, factor=0.5):
    """대운 부호가 강할 때(|dm|>=thr) 세운 부호가 반대면 세운 점수를 factor배 + 대운 점수 가산."""
    n = 0
    for r in rows:
        vals = []
        for p in r["per"]:
            ss, ds = p["ss"], p["ds"] or 0.0
            if abs(ds) >= thr and ss*ds < 0: v = ss*factor + ds*(1-factor)
            else: v = ss
            vals.append(v)
        if sign(statistics.mean(vals)) == r["pol"]: n += 1
    return n
print("blend:", {w: blend_agree(rows, w) for w in (1.0, 0.7, 0.6, 0.5, 0.4, 0.3, 0.0)})
print("damp:", {(t,f): damp_agree(rows, t, f) for t in (0.2, 0.3, 0.5) for f in (0.5, 0.3)})
# 단일 연도 사건만
single = [r for r in rows if len(r["per"]) == 1]
print("single-year n", len(single), "sew", sum(r["sew_agree"] for r in single), "dw", sum(r["dw_agree"] for r in single),
      "blend", {w: blend_agree(single, w) for w in (0.7, 0.6, 0.5)})
# 중립 밴드 민감도
for eps in (0.0, 0.05, 0.1):
    print("eps", eps, "sew", sum(1 for r in rows if (("+" if r["sm"]>eps else "-" if r["sm"]<-eps else "0")==r["pol"])),
          "dw", sum(1 for r in rows if r["dm"] is not None and (("+" if r["dm"]>eps else "-" if r["dm"]<-eps else "0")==r["pol"])))

json.dump(rows, open("/tmp/claude-1000/-home-degool-projects-saju-v2/feb89a75-96c0-469c-a6f2-5382e424af59/scratchpad/c6/rows.json","w"), ensure_ascii=False, indent=1, default=str)

# ── 표 출력 ──
print("\n### 불일치 29건 표")
print("| # | 사례/키 | 사건 | 극성 | 시점 | 세운 간지(점수) | 대운 간지(점수) | 세운평균 | 대운평균 | 분류 | 세운-대운 관계 | 천간/지지 방향 |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for i, r in enumerate(miss, 1):
    per = r["per"]
    sg = ", ".join(f"{p['sg']}({p['ss']:+.2f})" for p in per[:4]) + (" …" if len(per) > 4 else "")
    dg = ", ".join(sorted({f"{p['dg']}({p['ds']:+.2f})" for p in per}))
    rel = "; ".join(sorted({"/".join(rel_sew_dw(p["sg"], p["dg"])) or "-" for p in per if p["dg"]}))
    dirs = "; ".join(sorted({"".join(stem_branch_dir(p["sg"], r["roles"])) for p in per}))
    print(f"| {i} | {r['case'][5:]}/{r['key']} | {r['text']} | {r['pol']} | {r['when']} | {sg} | {dg} | {r['sm']:+.2f} | {r['dm']} | {''.join(r['cls'])} | {rel} | {dirs} |")

print("\n### 일치 15건")
for r in hit:
    print(f"- {r['case'][5:]}/{r['key']} {r['text']} {r['pol']} {r['when']} 세운 {r['sm']:+.2f} 대운 {r['dm']} 연도 {len(r['per'])}")

# 단일 연도 불일치에서 세운-대운 관계·방향 통계
single_miss = [r for r in miss if len(r["per"]) == 1]
print("\nsingle-year miss", len(single_miss))
print("rel counter", Counter(x for r in single_miss for x in rel_sew_dw(r["per"][0]["sg"], r["per"][0]["dg"])))
print("dir counter", Counter(stem_branch_dir(r["per"][0]["sg"], r["roles"]) for r in single_miss))
single_hit = [r for r in hit if len(r["per"]) == 1]
print("single-year hit", len(single_hit))
print("rel counter hit", Counter(x for r in single_hit for x in rel_sew_dw(r["per"][0]["sg"], r["per"][0]["dg"])))
print("dir counter hit", Counter(stem_branch_dir(r["per"][0]["sg"], r["roles"]) for r in single_hit))
print("codes miss", Counter(r["per"][0]["code"] for r in single_miss))
print("codes hit", Counter(r["per"][0]["code"] for r in single_hit))
