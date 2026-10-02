"""기회·호전 경량 엔진 — 위험 사전(risks/)의 긍정 대칭 층 (P1, 2026-09-18 데굴님 승인).

설계 원칙:
- **판정 공유, 점수 불변.** 위험 엔진과 같은 재료(용기신 극성·관계 발동·공망 상태·12운성)에 합
  완화(hap_mitigation)·구조 배경(luck_structure_flags)을 더해 판정하지만, 이벤트 점수·순위·
  favorability는 건드리지 않는다. 출력은 후보 서술의 '호전·기회 신호' 줄과 근거뿐이다.
- **별도 경량 엔진.** 위험 엔진의 감수 매니페스트·노출 게이트·shape 검증은 위험 전제라 재사용하지
  않는다(데굴님 결정). 대신 사전 규칙 문법만 같은 형태로 유지해 감수·비교가 쉽게 한다.
- **성사 확정 금지.** manifestations는 '가능한 발현 형태'이고 prohibitedClaims를 프롬프트에 함께
  싣는다(결혼·합격·당첨·치료 확정 금지 — 기존 가드와 중첩 적용).

규칙 문법(dictionaries/opportunities/<domain>.json, 룰 안 조건은 전부 AND):
  polarityRoleIn / tenGod / tenGodGroup / tenGodGroup2(두 번째 십성군 동시 존재) / rooted(운 천간이
  원국 지지 본기에 통근) / relation(YUKHAP·SAMHAP·BANGHAP·CHUNG·HYEONG·PA·HAE·STEM_HAP) /
  relationPalace(year·month·day·hour — 관계 상대 원국 자리) / relationTargetTenGodGroup(관계 상대
  원국 지지 본기 십성군) / voidState(active·release·fill·trigger) / hapMitigation(mitigated·
  officer·harmed·bound) / structure(chunggeun_clear·rescue_ok·tonggwan_present) / twelveStageIn /
  luckGradeIn / yeokma(운 지지가 기준 삼합국 상대 역마) / reasonPrefix(후보 근거 코드 접두).
점수 = baseValue + Σ 트리거 strength(기본 0.3) + Σ 증폭 − Σ 감쇠, [0, 1] 클램프.
minimumTriggers 이상 + OPPORTUNITY_MIN_SCORE 이상일 때만 신호.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.relations.hap_mitigation import resolve_hap_mitigation
from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
from saju_manse_analysis.structure.luck_geok_break import geok_break
from saju_manse_analysis.structure.luck_structure_flags import resolve_luck_structure_flags

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT, main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.pillars import Pillar

from . import period_v2_config
from .dictionaries import OpportunityMappingFile
from .relationship_relative_sinsal import get_relative_sinsal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_DOMAINS = (
    "career", "finance", "contract_legal", "relationship", "relocation", "selection",
    "health_safety",
)
_GROUP_OF = {
    "비견": "peer", "겁재": "peer", "식신": "output", "상관": "output",
    "편재": "wealth", "정재": "wealth", "편관": "officer", "정관": "officer",
    "편인": "resource", "정인": "resource",
}
_RELATION_PREFIX = {
    "YUKHAP": ("육합:",), "SAMHAP": ("삼합완성:", "반합성립:"), "BANGHAP": ("방합완성:",),
    "CHUNG": ("충:",), "HYEONG": ("삼형:", "무례지형:", "자형:"), "PA": ("파:",),
    "HAE": ("해:",), "STEM_HAP": ("천간합:",),
}
_DEFAULT_STRENGTH = 0.3
#: 후보 사건 키 → 함께 보일 기회 도메인(질문과 무관한 도메인 신호가 후보 줄에 섞이지 않게).
EVENT_DOMAINS: dict[str, tuple[str, ...]] = {
    "career_change": ("career", "selection"), "job_gain": ("career", "selection"),
    "promotion": ("career",), "business_start": ("finance", "career"),
    "business_expansion": ("finance", "career"), "wealth_change": ("finance",),
    "windfall": ("finance",), "contract_document": ("contract_legal", "finance"),
    "education_admission": ("selection",), "education_completion": ("selection",),
    "relationship_change": ("relationship",), "new_relationship": ("relationship",),
    "marriage_signal": ("relationship",), "childbirth": ("relationship", "health_safety"),
    "relocation": ("relocation", "contract_legal"), "legal_conflict": ("contract_legal",),
    "health_attention": ("health_safety",), "social_conflict": ("relationship",),
    "preparation_delay": ("contract_legal", "selection"), "creative_output": ("career", "finance"),
    "public_exposure": ("career", "relationship"),
}


@dataclass(frozen=True)
class OpportunitySignal:
    """한 시점의 기회·호전 신호 1건(서술 참고 전용)."""

    opportunity_id: str
    domain: str
    kind: str  # opportunity | achievement | maintenance | relief
    family: str  # event_process_types 긍정 유형 id
    score: float
    manifestations: tuple[str, ...]
    evidence: tuple[str, ...]
    allowed_claim_scope: tuple[str, ...]
    prohibited_claims: tuple[str, ...]


@dataclass
class _PeriodFacts:
    """운 기둥 1건에서 규칙 대조에 필요한 사실만 뽑은 것."""

    stem_role: str
    branch_role: str
    polarity_role: str
    ten_gods: set[str]
    groups: set[str]
    rooted: bool
    relations: list[str]
    relation_palaces: dict[str, set[str]]  # relation 코드 → 상대 원국 자리 집합
    relation_target_groups: dict[str, set[str]]  # relation 코드 → 상대 본기 십성군 집합
    void_states: set[str]
    hap_flags: set[str]
    structure_flags: set[str]
    twelve_stage: str
    luck_grade: str
    yeokma: bool
    reason_codes: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)


@lru_cache(maxsize=4)
def load_opportunities(dictionaries_dir: Path = _DICTS_DEFAULT) -> list[OpportunityMappingFile]:
    """도메인별 기회 사전(검증 스키마로 로드, 프로세스당 1회)."""
    out: list[OpportunityMappingFile] = []
    for dom in _DOMAINS:
        path = dictionaries_dir / "opportunities" / f"{dom}.json"
        if path.exists():
            out.append(OpportunityMappingFile.model_validate(json.loads(path.read_text("utf-8"))))
    return out


def _polarity(stem_role: str, branch_role: str) -> str:
    bad = {"기신", "구신"}
    if stem_role == "용신" and branch_role == "용신":
        return "YONG_STRONG"
    if stem_role in bad and branch_role in bad:
        return "GI_STRONG"
    for r in (stem_role, branch_role):
        if r == "용신":
            return "YONG"
        if r == "희신":
            return "HEE"
        if r in bad:
            return "GI"
    return "NEUTRAL"


def _period_facts(
    result: ManseV2Result, pillar: LuckPillar, fav_map: dict[str, str],
    reason_codes: Iterable[str] = (),
) -> _PeriodFacts | None:
    p = result.pillars
    if p is None or not pillar.stem or not pillar.branch:
        return None
    try:
        ls, lb = Stem(pillar.stem), Branch(pillar.branch)
    except ValueError:
        return None
    dm = Stem(p.day_master)
    stem_el, branch_el = str(STEM_ELEMENT[ls]), str(BRANCH_ELEMENT[lb])
    stem_role, branch_role = fav_map.get(stem_el, ""), fav_map.get(branch_el, "")
    raw_natal = [("year", p.year), ("month", p.month), ("day", p.day), ("hour", p.hour)]
    natal: list[tuple[str, Pillar]] = [(pos, x) for pos, x in raw_natal if x is not None]
    branch_of = {x.branch: pos for pos, x in natal}
    tgs = {pillar.stem_ten_god, pillar.branch_ten_god} - {""}
    rooted = any(
        STEM_ELEMENT[main_hidden_stem(Branch(x.branch))] == STEM_ELEMENT[ls] for _, x in natal
    )
    rel_pal: dict[str, set[str]] = {}
    rel_tg: dict[str, set[str]] = {}
    for rel in pillar.relations_to_chart:
        for code, prefixes in _RELATION_PREFIX.items():
            if not rel.startswith(prefixes):
                continue
            payload = rel.split(":", 1)[1]
            others = [
                ch for ch in payload.replace("-", "") if ch != pillar.branch and ch != pillar.stem
            ]
            for ch in others:
                if ch in branch_of:
                    rel_pal.setdefault(code, set()).add(branch_of[ch])
                    tg = str(ten_god(dm, main_hidden_stem(Branch(ch))))
                    rel_tg.setdefault(code, set()).add(_GROUP_OF.get(tg, ""))
                else:
                    try:
                        tg = str(ten_god(dm, Stem(ch)))
                        rel_tg.setdefault(code, set()).add(_GROUP_OF.get(tg, ""))
                        for pos, x in natal:
                            if x.stem == ch:
                                rel_pal.setdefault(code, set()).add(pos)
                    except ValueError:
                        pass
            rel_pal.setdefault(code, set())
    void: set[str] = set()
    if pillar.branch in set(p.gongmang_branches):
        void.add("active")
    for g in pillar.gongmang_activation:
        if g.startswith("공망해소"):
            void.add("release")
        elif g.startswith("공망전실"):
            void.add("fill")
        elif g.startswith("공망발동"):
            void.add("trigger")
    hap: set[str] = set()
    try:
        # 육합이 합화가 아니라 합거(묶임)면 '연결 성사'가 아니라 '얽힘'이다(참고 기준 합반·합거).
        for r in resolve_branch_hap(p, fav_map, luck_branches=[pillar.branch]):
            if r.luck_origin and r.kind == "six" and r.hap_mode == "bind" and r.direction == "away":
                hap.add("bound")
        m = resolve_hap_mitigation(p, fav_map, luck_stem=pillar.stem, luck_branch=pillar.branch)
        if m.stem_mitigated or m.branch_mitigated:
            hap.add("mitigated")
        if m.officer_elements:
            hap.add("officer")
        if m.stem_harmed or m.branch_harmed:
            hap.add("harmed")
    except (KeyError, ValueError):
        pass
    struct: set[str] = set()
    try:
        geok = result.geokguk.main_structure if result.geokguk is not None else None
        fl = resolve_luck_structure_flags(
            p, fav_map, luck_stem=pillar.stem, luck_branch=pillar.branch,
            geok_name=geok, luck_ten_gods=(pillar.stem_ten_god, pillar.branch_ten_god),
        )
        if fl.chunggeun_unfavorable:
            struct.add("chunggeun_clear")
        if not fl.tonggwan_absent:
            struct.add("tonggwan_present")
        breaks = geok_break(
            geok, [pillar.stem_ten_god, pillar.branch_ten_god],
            [str(ten_god(dm, Stem(x.stem))) for pos, x in natal if pos != "day"]
            + [str(ten_god(dm, main_hidden_stem(Branch(x.branch)))) for _, x in natal],
        )
        if breaks and all(b.rescued for b in breaks) and not fl.rescue_damaged:
            struct.add("rescue_ok")
    except (KeyError, ValueError):
        pass
    yeokma = False
    try:
        # 역마는 글자살이 아니라 연지·일지 삼합국 기준 상대 12신살로만 판정한다(2026-07-23 정정).
        for base in (p.year.branch, p.day.branch):
            res = get_relative_sinsal(Branch(base), lb)
            if "역마" in str(getattr(res, "name", "") or getattr(res, "sinsal", "")):
                yeokma = True
    except Exception:  # noqa: BLE001 — 상대 신살 계산 실패는 판정 생략(보수적)
        yeokma = False
    return _PeriodFacts(
        stem_role=stem_role, branch_role=branch_role,
        polarity_role=_polarity(stem_role, branch_role),
        ten_gods=tgs, groups={_GROUP_OF.get(t, "") for t in tgs} - {""},
        rooted=rooted, relations=list(pillar.relations_to_chart),
        relation_palaces=rel_pal, relation_target_groups=rel_tg,
        void_states=void, hap_flags=hap, structure_flags=struct,
        twelve_stage=pillar.twelve_unseong or "", luck_grade=pillar.luck_label or "",
        yeokma=yeokma, reason_codes=tuple(reason_codes),
    )


def _rule_matches(rule: dict, f: _PeriodFacts) -> str | None:
    """룰 조건 전부 AND. 통과하면 근거 문자열, 아니면 None."""
    ev: list[str] = []
    if (v := rule.get("polarityRoleIn")) and f.polarity_role not in v:
        return None
    if v:
        ev.append(f"극성 {f.polarity_role}")
    if (v := rule.get("tenGod")) and v not in f.ten_gods:
        return None
    if v:
        ev.append(f"십성 {v}")
    for key in ("tenGodGroup", "tenGodGroup2"):
        if (v := rule.get(key)) and v not in f.groups:
            return None
        if v:
            ev.append(f"십성군 {v}")
    if rule.get("rooted") and not f.rooted:
        return None
    if rule.get("rooted"):
        ev.append("운 천간 통근")
    if (v := rule.get("relation")):
        if v not in f.relation_palaces:
            return None
        pal = rule.get("relationPalace")
        if pal and pal not in f.relation_palaces.get(v, set()):
            return None
        tg = rule.get("relationTargetTenGodGroup")
        if tg and tg not in f.relation_target_groups.get(v, set()):
            return None
        ev.append(f"관계 {v}" + (f"@{pal}" if pal else "") + (f"→{tg}" if tg else ""))
    elif (pal := rule.get("relationPalace")):
        if not any(pal in s for s in f.relation_palaces.values()):
            return None
        ev.append(f"자리 {pal} 발동")
    if (v := rule.get("voidState")) and v not in f.void_states:
        return None
    if v:
        ev.append(f"공망 {v}")
    if (v := rule.get("hapMitigation")) and v not in f.hap_flags:
        return None
    if v:
        ev.append(f"합 {v}")
    if (v := rule.get("structure")) and v not in f.structure_flags:
        return None
    if v:
        ev.append(f"구조 {v}")
    if (v := rule.get("twelveStageIn")) and f.twelve_stage not in v:
        return None
    if v:
        ev.append(f"12운성 {f.twelve_stage}")
    if (v := rule.get("luckGradeIn")) and f.luck_grade not in v:
        return None
    if v:
        ev.append(f"운 등급 {f.luck_grade}")
    if rule.get("yeokma") and not f.yeokma:
        return None
    if rule.get("yeokma"):
        ev.append("역마 유입")
    if (v := rule.get("reasonPrefix")) and not any(c.startswith(v) for c in f.reason_codes):
        return None
    if v:
        ev.append(f"근거 {v}")
    return " · ".join(ev) if ev else None


def detect_opportunities(
    result: ManseV2Result,
    pillar: LuckPillar,
    fav_map: dict[str, str],
    *,
    reason_codes: Iterable[str] = (),
    dictionaries_dir: Path = _DICTS_DEFAULT,
    domains: Iterable[str] | None = None,
) -> list[OpportunitySignal]:
    """운 기둥 1건의 기회·호전 신호(점수 내림차순). 플래그·문턱은 호출자가 아니라 여기서 본다."""
    facts = _period_facts(result, pillar, fav_map, reason_codes)
    if facts is None:
        return []
    wanted = set(domains) if domains else None
    out: list[OpportunitySignal] = []
    for file in load_opportunities(dictionaries_dir):
        if wanted and file.domain not in wanted:
            continue
        for item in file.items:
            spec = item.model_dump(by_alias=True)
            hits: list[str] = []
            score = float(spec["baseValue"])
            for rule in spec["triggerRules"]:
                e = _rule_matches(rule, facts)
                if e:
                    hits.append(f"{rule['id']}: {e}")
                    score += float(rule.get("strength") or _DEFAULT_STRENGTH)
            if len(hits) < int(spec.get("minimumTriggers", 1)):
                continue
            for rule in spec.get("amplifierRules", []):
                if _rule_matches(rule, facts):
                    score += float(rule.get("strength") or 0.2)
            for rule in spec.get("dampenerRules", []):
                if _rule_matches(rule, facts):
                    score -= float(rule.get("strength") or 0.3)
                    hits.append(f"{rule['id']}(감쇠)")
            score = max(0.0, min(1.0, round(score, 3)))
            if score < period_v2_config.OPPORTUNITY_MIN_SCORE:
                continue
            out.append(OpportunitySignal(
                opportunity_id=spec["opportunityId"], domain=file.domain, kind=spec["kind"],
                family=spec["family"], score=score,
                manifestations=tuple(m["ko"] for m in spec.get("manifestations", [])),
                evidence=tuple(hits),
                allowed_claim_scope=tuple(spec.get("allowedClaimScope", [])),
                prohibited_claims=tuple(spec.get("prohibitedClaims", [])),
            ))
    out.sort(key=lambda s: -s.score)
    return out


_FAMILY_KO = {
    "opportunity_inflow": "기회 유입", "connection": "연결·협력 성사",
    "selection_pass": "선발·통과·승인",
    "acquisition": "획득·수령", "completion": "완수·실현", "recognition": "인정·보상",
    "expansion": "확대·성장", "stabilization": "유지·정착", "recovery": "회복·복구",
    "settlement": "해결·해소", "protection": "보호·지원", "relief": "부담 경감",
    "autonomy": "선택권·자율성 확대", "loss_prevention": "손실 방지·피해 축소",
}
_KIND_KO = {
    "opportunity": "기회 발생", "achievement": "실제 성취",
    "maintenance": "유지·후속", "relief": "해소·경감",
}


def format_opportunity_notes(signals: list[OpportunitySignal], limit: int = 2) -> list[str]:
    """후보 서술용 줄 — 상위 limit개. '단계·유형: 발현 형태 (근거) — 금지 표현'."""
    out: list[str] = []
    for s in signals[:limit]:
        forms = " / ".join(s.manifestations[:2])
        parts = [h.split(": ", 1)[1] if ": " in h else h for h in s.evidence[:2]]
        basis = "; ".join(parts)
        out.append(
            f"{_KIND_KO.get(s.kind, s.kind)} · {_FAMILY_KO.get(s.family, s.family)}: {forms} "
            f"(근거 {basis}) — 확정 금지: {'·'.join(s.prohibited_claims[:2])}"
        )
    return out
