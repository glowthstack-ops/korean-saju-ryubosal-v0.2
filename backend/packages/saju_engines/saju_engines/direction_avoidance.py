"""피할 방향 중첩 판정(STRONG_AVOID) — docs/19 §4 (2026-09-21 데굴님 승인).

원칙: 개인 12신살 층에는 절대흉방이 없다. 회피는 **목적 충돌(사전 caution)** 이 있을 때만 시작하고,
동일한 불리 주제가 **시간(세운·삼재)과 공간(방향 신살)** 에서 겹칠 때만 STRONG_AVOID 로 올린다.

조건 4개(전부 기존 엔진 산출값 — 새 명리 규칙 없음):
- ① 목적과 방향 신살의 성향이 강하게 반대 = 사전 grade == caution
- ② 기준 연도 세운 지지의 12신살 == 방향 신살 ⇔ 방향 지지 == 세운 지지(삼재 해면 들=역마/눌=육해/
  날=화개 테마 중첩이 자동으로 포함된다 — 자료 §4의 세 조합)
- ③ 악삼재(`SamjaeInfo.quality == ak`) 또는 비삼재 해의 기신운 세운(`LuckPillar.yongsin_alignment`)
- ④ 목적 도메인의 그 해 사건 흐름이 불리(`domain_grades_for_year` == caution)

판정: ① 참이고 ②③④ 중 2개 이상 → STRONG_AVOID. ①만 → CAUTION. ① 거짓이면 회피 없음.
반대(GOOD_MATCH): fit/support 방향에 ②가 참이고 복삼재(또는 용신운 세운)면 BEST_USE 에 '시간·공간
일치' 근거만 덧붙인다(등급을 새로 만들지 않는다 — 삼재 자체를 감점하지 않는 모델).

서술 전용(inert): 사건 점수·luck_score·날짜·간지 파이프라인 불변. 수치는 프롬프트에 싣지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.enums import Branch
from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.sinsal_direction import (
    DirectionPick,
    SinsalDirectionBlock,
    SinsalDirectionDict,
    SinsalDirectionProfile,
)
from saju_shared_types.twelve_sinsal import SamjaeInfo, SamjaeQuality, relative_twelve_sinsal

# samjae_quality → report_event_input → context_reducer 순환을 피하기 위해 엔진 헬퍼는 함수 안에서
# 지연 import 한다(sinsal_direction.format_samjae_lines 와 같은 방식).

#: STRONG_AVOID 에 필요한 중첩 조건 수(②③④ 중) — 자료 §7 "4조건 중 3개 이상"(①은 전제).
STRONG_AVOID_MIN_OVERLAPS = 2

_UNFAVORABLE_ALIGNMENTS = ("기신운",)
_FAVORABLE_ALIGNMENTS = ("용신운",)


@dataclass
class AvoidanceContext:
    """기준 연도의 시간 축 신호 묶음 — 목적별 판정이 공유한다."""

    year: int
    transit_branch: Branch
    transit_sinsal: str  # 출생 연지 기준 세운 지지의 12신살
    samjae: SamjaeInfo | None
    annual_alignment: str  # 용신운/기신운/혼합/평운/"" (세운 기둥 없으면 "")
    domain_grades: dict[str, str] = field(default_factory=dict)  # domain → favorable/mixed/caution

    @property
    def unfavorable(self) -> bool:
        """조건 ③ — 악삼재 또는 기신운 세운."""
        if self.samjae is not None and self.samjae.quality is not None:
            return self.samjae.quality is SamjaeQuality.AK
        return self.annual_alignment in _UNFAVORABLE_ALIGNMENTS

    @property
    def favorable(self) -> bool:
        """GOOD_MATCH 조건 — 복삼재 또는 용신운 세운."""
        if self.samjae is not None and self.samjae.quality is not None:
            return self.samjae.quality is SamjaeQuality.BOK
        return self.annual_alignment in _FAVORABLE_ALIGNMENTS

    def basis_line(self) -> str:
        """프롬프트 '중첩 판정 기준' 한 줄(수치 없음)."""
        head = f"{self.year}년 세운 {self.transit_branch}={self.transit_sinsal}"
        if self.samjae is not None:
            head += f"({self.samjae.label_ko}"
            if self.samjae.quality_label:
                head += f"·{self.samjae.quality_label}"
            head += ")"
        elif self.annual_alignment:
            head += f"({self.annual_alignment})"
        return head


def build_avoidance_context(
    result: ManseV2Result,
    year: int,
    candidates: list[EventCandidate] | None = None,
    *,
    dictionary: SinsalDirectionDict | None = None,
) -> AvoidanceContext | None:
    """기준 연도의 세운 신살·삼재·세운 극성·도메인 등급을 모은다(원국 없으면 None)."""
    if result.pillars is None:
        return None
    from .counterfactual_context import _year_pillar_map  # 순환 import 방지(지연)
    from .samjae_quality import domain_grades_for_year, evaluate_samjae
    from .sinsal_direction import load_sinsal_direction_dict

    dic = dictionary or load_sinsal_direction_dict()
    year_branch = Branch(result.pillars.year.branch)
    transit = year_ganzi(year)[1]
    pillar = _year_pillar_map(result).get(str(year))
    cands = [c for c in (candidates or []) if str(c.period)[:4] == str(year)]
    grades: dict[str, str] = {
        g.domain: str(g.grade) for g in domain_grades_for_year(cands, dic.samjae_quality)
    }
    return AvoidanceContext(
        year=year,
        transit_branch=transit,
        transit_sinsal=relative_twelve_sinsal(year_branch, transit),
        samjae=evaluate_samjae(result, year, candidates, dictionary=dic),
        annual_alignment=pillar.yongsin_alignment if pillar is not None else "",
        domain_grades=grades,
    )


def _overlap_evidence(ctx: AvoidanceContext, pick: DirectionPick, domain: str) -> list[str]:
    """②③④ 중 참인 조건의 한글 근거(순서 고정). 조건 ①은 호출자가 pick.grade 로 본다."""
    out: list[str] = []
    if pick.branch == str(ctx.transit_branch):
        line = f"{ctx.year}년 세운 {ctx.transit_branch}({ctx.transit_sinsal})가 이 방향 지지와 겹침"
        if ctx.samjae is not None:
            line += f" — 올해 {ctx.samjae.label_ko}({ctx.samjae.sinsal}) 테마와 동일"
        out.append(line)
    if ctx.unfavorable:
        out.append(
            f"올해 {ctx.samjae.quality_label} 성격 우세"
            if ctx.samjae is not None and ctx.samjae.quality_label
            else f"{ctx.year}년 세운이 {ctx.annual_alignment}"
        )
    if ctx.domain_grades.get(domain) == "caution":
        from .report_event_input import _DOMAIN_KO  # 라벨 단일 원천

        out.append(f"{_DOMAIN_KO.get(domain, domain)} 영역의 올해 사건 흐름이 불리 쪽")
    return out


def decide_verdict(grade: str, overlaps: int) -> str:
    """사전 등급 + 중첩 조건 수 → verdict. 절대흉방 없음(caution 이 아니면 회피로 올리지 않는다)."""
    if grade == "caution":
        return "STRONG_AVOID" if overlaps >= STRONG_AVOID_MIN_OVERLAPS else "CAUTION"
    return {"fit": "BEST_USE", "support": "GOOD_USE"}.get(grade, "NEUTRAL")


def annotate_avoidance(
    block: SinsalDirectionBlock,
    result: ManseV2Result,
    year: int,
    candidates: list[EventCandidate] | None = None,
    *,
    dictionary: SinsalDirectionDict | None = None,
) -> SinsalDirectionBlock:
    """블록의 추천(picks·cautions)에 verdict·근거를 채운다(제자리). 원국 없으면 그대로 반환."""
    from .sinsal_direction import load_sinsal_direction_dict  # 순환 import 방지(지연)

    dic = dictionary or load_sinsal_direction_dict()
    ctx = build_avoidance_context(result, year, candidates, dictionary=dic)
    if ctx is None:
        return block
    block.avoidance_basis = [ctx.basis_line()]
    if block.asked_sectors and block.recommendations:
        domain0 = dic.purpose(block.recommendations[0].purpose).domain
        for a in block.asked_sectors:
            ev = _overlap_evidence(ctx, a, domain0)
            a.verdict = decide_verdict(a.grade, len(ev))  # type: ignore[assignment]
            a.verdict_evidence = ev if a.verdict == "STRONG_AVOID" else []
    for rec in block.recommendations:
        domain = dic.purpose(rec.purpose).domain
        for c in rec.cautions:
            ev = _overlap_evidence(ctx, c, domain)
            c.verdict = decide_verdict(c.grade, len(ev))  # type: ignore[assignment]
            c.verdict_evidence = ev if c.verdict == "STRONG_AVOID" else []
        for p in rec.picks:
            p.verdict = decide_verdict(p.grade, 0)  # type: ignore[assignment]
            aligned = p.branch == str(ctx.transit_branch)
            if p.grade in ("fit", "support") and aligned and ctx.favorable:
                why = (
                    f"올해 {ctx.samjae.quality_label}"
                    if ctx.samjae is not None and ctx.samjae.quality_label
                    else f"{ctx.year}년 세운이 {ctx.annual_alignment}"
                )
                p.verdict_evidence = [
                    f"시간·공간 일치 — {ctx.year}년 세운 {ctx.transit_branch}({ctx.transit_sinsal})"
                    f"가 이 방향 지지와 겹치고 {why}"
                ]
    return block


def strong_avoid_lines(
    profile: SinsalDirectionProfile,
    result: ManseV2Result,
    year: int,
    candidates: list[EventCandidate] | None = None,
    *,
    dictionary: SinsalDirectionDict | None = None,
) -> list[str]:
    """목적 전체를 훑어 기준 연도의 STRONG_AVOID 만 한 줄씩(리포트 전용 섹션용). 없으면 빈 목록."""
    from .sinsal_direction import load_sinsal_direction_dict, recommend_for_purpose

    dic = dictionary or load_sinsal_direction_dict()
    ctx = build_avoidance_context(result, year, candidates, dictionary=dic)
    if ctx is None:
        return []
    lines: list[str] = []
    for entry in dic.purposes:
        rec = recommend_for_purpose(profile, entry.purpose, dic)
        for c in rec.cautions:
            ev = _overlap_evidence(ctx, c, entry.domain)
            if decide_verdict(c.grade, len(ev)) == "STRONG_AVOID":
                lines.append(
                    f"- {entry.name_ko}: {c.absolute_direction}쪽 {c.branch} {c.sinsal} — "
                    + " / ".join(ev)
                )
    if not lines:
        return []
    return [
        f"[강한 회피 — {year}년 기준(목적 충돌 + 시간·공간 중첩; 기준 {ctx.basis_line()})]",
        *lines,
    ]
