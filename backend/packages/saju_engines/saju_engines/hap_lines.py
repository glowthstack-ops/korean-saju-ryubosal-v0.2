"""천간합 작용 모드 → LLM 입력용 한 줄 텍스트 (Phase 2a — HAP_INTERACTION_SPEC §F-4).

manse_analysis의 `resolve_stem_hap`(판정)을 호출해, 합화/합반/합거/본신지합/쟁투를 **모드+영향+
신뢰도**가 담긴 사람용 한 줄로 직렬화한다. 단정 금지(절대원칙 3) — 신뢰도(확정/조건부/불성)로 표현.

원국 합(natal)은 캐시되는 고정 prefix(serialize_chart_prefix)에, 운 합(luck)은 기간 grounding에
주입한다. 점수 반영은 Phase 2b.
"""

from __future__ import annotations

from saju_manse_analysis.relations.hap_modes import (
    BranchHapResolution,
    StemHapResolution,
    resolve_branch_hap,
    resolve_stem_hap,
)

from saju_shared_types.constants import BRANCH_CLASHES, BRANCH_INDEX, STEM_INDEX, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

from . import period_v2_config
from .event_scoring import favorability_map

_TIER_KO = {"confirmed": "확정", "conditional": "조건부", "none": "불성"}
_EFFECT_KO = {"boon": "유리(흉 제거)", "harm": "불리(길 상실)", "neutral": ""}


def _affected_txt(a: object) -> str:
    """묶인 천간 1개 → '辛 정관=희신 불리(길 상실)' 형식."""
    stem = getattr(a, "stem", "")
    god = getattr(a, "ten_god", "")
    role = getattr(a, "role", "")
    eff = _EFFECT_KO.get(getattr(a, "effect", ""), "")
    s = f"{stem} {god}" + (f"={role}" if role else "")
    return f"{s} {eff}".rstrip()


_TEN_GOD_GROUP_KO = {
    "정관": "관성", "편관": "관성", "정재": "재성", "편재": "재성",
    "정인": "인성", "편인": "인성", "식신": "식상", "상관": "식상", "비견": "비겁", "겁재": "비겁",
}


def _contend_label(r: StemHapResolution, day_master: str | None) -> str:
    """쟁합·투합 표기 — RELATION_TERMS_V2면 다투는 글자의 십성군(관성/재성/인성 쟁합)을 병기.

    참고 기준(2026-09-18): 관성 쟁합=직위·선발·인정의 경쟁, 재성 쟁합=수익·거래·자원 배분의
    경쟁, 인성 쟁합=지원·문서·자격을 둘러싼 경쟁 — '몫 절반'·삼각관계 단정은 하지 않는다.
    """
    if not (period_v2_config.RELATION_TERMS_V2_ENABLED and r.contested_stem and day_master):
        return "쟁합·투합"
    try:
        god = str(ten_god(Stem(day_master), Stem(r.contested_stem)))
    except (KeyError, ValueError):
        return "쟁합·투합"
    group = _TEN_GOD_GROUP_KO.get(god)
    if r.contested_stem == day_master:
        return "쟁합·투합(일간을 두고 다툼 — 관계·선택의 경쟁)"
    return f"쟁합·투합({group} 쟁합 — {god} {r.contested_stem})" if group else "쟁합·투합"


def _format(r: StemHapResolution, fav: dict[str, str], day_master: str | None = None) -> str:
    """StemHapResolution → 한 줄(모드+영향+신뢰도). 운 합은 '운 ' 접두."""
    # 표기 순서를 천간 표준순(甲→癸)으로 정규화 — 자리 순서에 따른 戊癸/癸戊 중복 방지.
    a, b = sorted(r.pair, key=lambda s: STEM_INDEX[Stem(s)])
    pair = f"{a}{b}合"
    prefix = "운 " if r.luck_origin else ""

    if r.blocked:
        body = f"불성립({r.block_reason})"
    elif r.hap_mode == "combine_self":
        if r.chart_transform:
            el = r.transform_element or ""
            body = f"본신지합 → 化氣格 후보(일간이 化神 {el}({fav.get(el, '역할 미상')})으로 化)"
        else:
            body = "본신지합(합거 아님)"
            if r.affected:
                body += f" · {_affected_txt(r.affected[0])} 유지"
    elif r.hap_mode == "transform":
        el = r.transform_element or ""
        body = f"합화 {el}({fav.get(el, '역할 미상')})"
    else:  # bind — 합반 + 합거 효과
        eff = " · ".join(_affected_txt(a) for a in r.affected)
        body = "합반(化 불성)" + (f" · {eff}" if eff else "")
        if r.direction == "away":
            body += " · 합거"

    tail = f" · 化 {_TIER_KO.get(r.transform_tier, '')}" if r.transform_element else ""
    flags = []
    if r.weakened:
        flags.append("隔位 약화")
    if r.contend:
        flags.append(_contend_label(r, day_master))
    if flags:
        tail += " · " + "·".join(flags)
    return f"{prefix}{pair} → {body}{tail}"


def _format_branch(r: BranchHapResolution) -> str:
    """BranchHapResolution(육합/삼합/방합) → 한 줄."""
    prefix = "운 " if r.luck_origin else ""
    mem = "".join(r.members)
    tier = _TIER_KO.get(r.transform_tier, "")
    if r.kind == "six":
        if r.hap_mode == "transform":
            body = f"{mem}合 → 합화 {r.transform_element}({r.role}) · 化 {tier}"
        else:
            eff = " · ".join(_affected_txt(a) for a in r.affected)
            body = f"{mem}合 → 합반(化 불성·묶임)" + (f" · {eff}" if eff else "")
            if r.direction == "away":
                body += " · 합거"
            body += f" · 化 {tier}"
    elif r.kind == "gonghap":
        body = (
            f"{mem} 공합(가합·왕지 없음) {r.transform_element}({r.role})에 부분 가세(미약) — "
            "반합·삼합 아님"
        )
    elif r.kind in ("three_harmony", "half"):
        kname = "삼합" if r.kind == "three_harmony" else "반합"
        royal = "(왕지)" if r.kind == "half" and r.royal_included else ""
        suffix = " 성립" if r.kind == "three_harmony" else ""
        body = f"{mem} {kname}{royal} {r.transform_element}국({r.role}){suffix} · {tier}"
    else:  # directional
        comp = "방합" if len(r.members) == 3 else "방합(부분)"
        body = f"{mem} {comp} {r.transform_element}({r.role}) 강화"
    if r.co_relations:
        body += " · 동시 " + "·".join(r.co_relations)
    return f"{prefix}{body}"


def _natal_pillars(p) -> list[tuple[str, str, str]]:
    """(자리, 천간, 지지) 목록 — 시주 없으면 3주."""
    out = [("year", p.year.stem, p.year.branch), ("month", p.month.stem, p.month.branch),
           ("day", p.day.stem, p.day.branch)]
    if p.hour is not None:
        out.append(("hour", p.hour.stem, p.hour.branch))
    return out


_PALACE_KO = {"year": "연주", "month": "월주", "day": "일주", "hour": "시주"}


def cheonhap_jihap_lines(
    result: ManseV2Result, luck_ganji: str | None = None,
) -> list[str]:
    """천합지합(天合地合) 표기 — 두 기둥의 천간끼리 합이면서 지지끼리도 합일 때 1줄(서술 전용).

    2026-10-25 데굴님 승인(합 체계 대조 P1-2). 원국 기둥쌍(luck_ganji=None) 또는 운 기둥(간지 2자)
    대 원국 기둥. 성립 사실만 적고 길흉·점수는 없다 — 결속이 강한 쌍이라는 표지. 합화·묶임 판정은
    기존 천간합·지지합 줄이 담당한다.
    """
    if result.pillars is None:
        return []
    from saju_shared_types.constants import SIX_COMBINATIONS, STEM_COMBINATIONS
    natal = _natal_pillars(result.pillars)
    lines: list[str] = []
    if luck_ganji is None:
        for i in range(len(natal)):
            for j in range(i + 1, len(natal)):
                pa, sa, ba = natal[i]
                pb, sb, bb = natal[j]
                if (frozenset({Stem(sa), Stem(sb)}) in STEM_COMBINATIONS
                        and frozenset({Branch(ba), Branch(bb)}) in SIX_COMBINATIONS):
                    lines.append(
                        f"천합지합: {_PALACE_KO[pa]} {sa}{ba} ↔ {_PALACE_KO[pb]} {sb}{bb} — "
                        "천간합·지지합 동시 성립(결속 강한 쌍, 성립 표지일 뿐 길흉 아님)"
                    )
        return lines
    if len(luck_ganji) < 2:
        return []
    ls, lb = luck_ganji[0], luck_ganji[1]
    try:
        lstem, lbranch = Stem(ls), Branch(lb)
    except ValueError:
        return []
    for pa, sa, ba in natal:
        if (frozenset({lstem, Stem(sa)}) in STEM_COMBINATIONS
                and frozenset({lbranch, Branch(ba)}) in SIX_COMBINATIONS):
            lines.append(
                f"운 천합지합: 운 {luck_ganji} ↔ {_PALACE_KO[pa]} {sa}{ba} — 천간합·지지합 "
                "동시 성립(그 기둥과 결속이 강한 시기, 성립 표지일 뿐 길흉 아님)"
            )
    return lines


def natal_hap_change_lines(
    result: ManseV2Result,
    luck_stems: list[str] | None = None,
    luck_branches: list[str] | None = None,
) -> list[str]:
    """운 글자가 **원국 기존 합**에 주는 변화(서술 전용, 2026-10-25 P1-4).

    ① 운 천간이 원국 합의 제3자로 끼어 쟁합이 새로 생김 → '결속 약화'.
    ② 운 지지가 원국 육합·삼합·반합의 구성 지지를 충해 化 등급이 내려감 → '합·충 경쟁'.
    원국 줄은 운 없이 계산되므로 이 변화는 따로 내지 않으면 LLM 이 모른다.
    """
    if result.pillars is None or not (luck_stems or luck_branches):
        return []
    fav = favorability_map(result)
    p = result.pillars
    lines: list[str] = []
    if luck_stems:
        base = {
            (r.pair, r.positions): r for r in resolve_stem_hap(p, fav) if not r.luck_origin
        }
        for r in resolve_stem_hap(p, fav, luck_stems=luck_stems):
            if r.luck_origin:
                continue
            b = base.get((r.pair, r.positions))
            if b is None:
                continue
            if r.contend and not b.contend:
                a, c = sorted(r.pair, key=lambda s: STEM_INDEX[Stem(s)])
                lines.append(
                    f"운 영향: 원국 {a}{c}合에 운 천간이 제3자로 가세 — "
                    "쟁합(결속 약화·化 확정 불가)"
                )
    if luck_branches:
        base_b = {
            (r.kind, r.members): r for r in resolve_branch_hap(p, fav) if not r.luck_origin
        }
        for rb in resolve_branch_hap(p, fav, luck_branches=luck_branches):
            if rb.luck_origin:
                continue
            bb = base_b.get((rb.kind, rb.members))
            if bb is None:
                continue
            rank = {"confirmed": 2, "conditional": 1, "none": 0}
            if rank.get(rb.transform_tier, 0) < rank.get(bb.transform_tier, 0):
                clashes = [
                    f"충:{m}{lb}" for m in rb.members for lb in luck_branches
                    if frozenset({Branch(m), Branch(lb)}) in BRANCH_CLASHES
                ]
                why = f" — {'·'.join(dict.fromkeys(clashes))}" if clashes else ""
                members = "".join(sorted(rb.members, key=lambda x: BRANCH_INDEX[Branch(x)]))
                label = f"{members}合" if rb.kind == "six" else f"{members} 합"
                tier_from = _TIER_KO.get(bb.transform_tier, "")
                tier_to = _TIER_KO.get(rb.transform_tier, "")
                lines.append(
                    f"운 영향: 원국 {label}의 化 {tier_from}→{tier_to}{why} "
                    "(운 지지가 구성 지지를 충 — 합·충 경쟁, 합이 충을 무조건 해소하지 않음)"
                )
    return list(dict.fromkeys(lines))


def natal_hap_mode_lines(result: ManseV2Result) -> list[str]:
    """원국 천간합·지지합의 작용 모드 줄(운 무관 — 캐시 고정 prefix용)."""
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    p = result.pillars
    # 쟁합(동일 글자 다자)으로 같은 줄이 중복될 수 있어 순서 보존 dedup.
    lines = [_format(r, fav, p.day_master) for r in resolve_stem_hap(p, fav)]
    lines += [_format_branch(r) for r in resolve_branch_hap(p, fav) if not r.luck_origin]
    lines += cheonhap_jihap_lines(result)  # 천합지합(2026-10-25, 성립 표지)
    return list(dict.fromkeys(lines))


def luck_hap_mode_lines(
    result: ManseV2Result,
    luck_stems: list[str] | None = None,
    luck_branches: list[str] | None = None,
) -> list[str]:
    """운(運) 천간·지지가 원국과 맺는 합의 작용 모드 줄(기간 grounding용).

    원국 합은 natal_hap_mode_lines에서 다루므로, 운 관여(luck_origin) 합만 반환한다.
    """
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    p = result.pillars
    lines: list[str] = []
    if luck_stems:
        lines += [
            _format(r, fav, p.day_master)
            for r in resolve_stem_hap(p, fav, luck_stems=luck_stems)
            if r.luck_origin
        ]
    if luck_branches:
        natal_branches = [
            Branch(x.branch) for x in (p.year, p.month, p.day, p.hour) if x is not None
        ]
        for r in resolve_branch_hap(p, fav, luck_branches=luck_branches):
            if not r.luck_origin:
                continue
            line = _format_branch(r)
            if period_v2_config.RELATION_TERMS_V2_ENABLED and r.kind == "six":
                line += _hapcheo_bongchung_suffix(r, natal_branches)
            lines.append(line)
    # 운 기둥 천합지합(간지 쌍이 하나씩 넘어온 경우) + 운이 원국 기존 합에 주는 변화(2026-10-25).
    if luck_stems and luck_branches and len(luck_stems) == len(luck_branches):
        for ls, lb in zip(luck_stems, luck_branches, strict=True):
            lines += cheonhap_jihap_lines(result, f"{ls}{lb}")
    lines += natal_hap_change_lines(result, luck_stems, luck_branches)
    return list(dict.fromkeys(lines))


def _hapcheo_bongchung_suffix(r: BranchHapResolution, natal_branches: list[Branch]) -> str:
    """합처봉충(合處逢沖) 표기 — 합으로 연결된 두 글자 중 하나를 원국 다른 지지가 충하면 병기.

    참고 기준(2026-09-18): 계약·협업·관계의 재편, 유지하던 연결의 흔들림. 표기 전용이며
    충 자체의 점수·변동성은 관계 판정이 이미 반영한다(중복 계산 없음).
    """
    hits: list[str] = []
    for m in r.members:
        mb = Branch(m)
        for nb in natal_branches:
            if nb != mb and frozenset({mb, nb}) in BRANCH_CLASHES:
                tag = f"{nb}충{mb}"
                if tag not in hits:
                    hits.append(tag)
    if not hits:
        return ""
    return " · 합처봉충(" + "·".join(hits) + " — 합 자리에 충 개입: 연결의 재편·흔들림)"
