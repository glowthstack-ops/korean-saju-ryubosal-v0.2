"""GanjiCalendarEntry 생성기 + RelationHit 구조화 (v2.2 Phase 0 T0.4).

만세력 엔진은 운(대운/세운/월운/일운)과 원국의 합충형파해·공망 활성을 표시용 **문자열**
(`relations_to_chart`, `gongmang_activation`)로 내보낸다. 본 모듈은 그 문자열을 구조화된
`RelationHit`로 변환하고, 운 항목을 `GanjiCalendarEntry`로 묶는다.

설계 원칙: 어떤 관계가 성립하는지는 **엔진이 이미 판정**했다(인사신 일지 게이트, 자형 카운트
규칙 등). 본 변환기는 그 판정을 재계산하지 않고 파싱·보강만 한다(절대 원칙 1: 엔진 = 유일
진실 공급원). 원국 자리 해소(어느 기둥의 글자인지)와 삼합/방합 기여의 국(局) 구성 지지
보강만 공유 상수 테이블(`constants`)에서 조회한다.
"""

from __future__ import annotations

from saju_shared_types.constants import DIRECTIONAL_COMBINATIONS, THREE_HARMONY
from saju_shared_types.enums import Branch
from saju_shared_types.ganji_calendar import (
    GanjiCalendarEntry,
    GanjiLevel,
    GanjiRef,
    RelationHit,
    RelationType,
)
from saju_shared_types.luck import DaewoonItem, LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.pillars import FourPillarsResult, Pillar

# 엔진 한글 접두사 → 구조화 관계 종류. '-'로 운/원국 글자를 분리하는 형태와
# 단일 페이로드(기여 오행, 자형 지지) 형태가 섞여 있다.
_PREFIX_TO_TYPE: dict[str, RelationType] = {
    "충": RelationType.BRANCH_CLASH,
    "육합": RelationType.SIX_COMBINATION,
    "파": RelationType.BRANCH_BREAK,
    "해": RelationType.HARM,
    "무례지형": RelationType.PUNISHMENT_MUTUAL,
    "천간합": RelationType.STEM_COMBINATION,
    "삼합기여": RelationType.THREE_HARMONY_CONTRIB,
    "방합기여": RelationType.DIRECTIONAL_CONTRIB,
    "자형": RelationType.SELF_PUNISHMENT,
    "삼형": RelationType.PUNISHMENT_TRIPLE,
    "공망전실": RelationType.VOID_FILL,
    "공망발동(충)": RelationType.VOID_TRIGGER_CLASH,
    "공망해소(합)": RelationType.VOID_RELEASE_COMBINE,
}

_PERIOD_TYPE_TO_LEVEL: dict[str, GanjiLevel] = {
    "year": GanjiLevel.YEAR,
    "month": GanjiLevel.MONTH,
    "day": GanjiLevel.DAY,
}


def _natal_pillars(pillars: FourPillarsResult) -> list[tuple[str, Pillar]]:
    """원국 (자리이름, Pillar) 목록. 시주 미상이면 제외."""
    out = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        out.append(("hour", pillars.hour))
    return out


def _natal_positions_for_branch(pillars: FourPillarsResult, branch: str) -> list[str]:
    """해당 지지를 가진 원국 자리 이름 목록(복수 가능)."""
    return [pos for pos, p in _natal_pillars(pillars) if p.branch == branch]


def _natal_positions_for_stem(pillars: FourPillarsResult, stem: str) -> list[str]:
    """해당 천간을 가진 원국 자리 이름 목록(복수 가능)."""
    return [pos for pos, p in _natal_pillars(pillars) if p.stem == stem]


def _natal_refs_for_branch(pillars: FourPillarsResult, branch: str) -> list[GanjiRef]:
    """지지 한 글자에 대한 원국 측 GanjiRef 목록."""
    return [
        GanjiRef(side="natal", position=pos, branch=branch)
        for pos in _natal_positions_for_branch(pillars, branch)
    ]


def _contrib_natal_refs(
    luck_branch: str, element: str, groups: list[tuple[frozenset[Branch], str]],
    pillars: FourPillarsResult,
) -> list[GanjiRef]:
    """삼합/방합 기여의 원국 구성 지지를 보강한다.

    엔진 문자열은 완성 오행만 담으므로, 해당 오행의 국(局) 중 운 지지를 포함하는 그룹을
    찾아 그 나머지 멤버가 원국에 있으면 원국 측 GanjiRef로 만든다.
    """
    refs: list[GanjiRef] = []
    for members, group_el in groups:
        if group_el != element:
            continue
        if Branch(luck_branch) not in members:
            continue
        for member in members:
            if str(member) == luck_branch:
                continue
            refs.extend(_natal_refs_for_branch(pillars, str(member)))
    return refs


def _relation_hit(
    raw: str, luck_level: GanjiLevel, luck_stem: str, luck_branch: str,
    pillars: FourPillarsResult,
) -> RelationHit | None:
    """엔진 관계/공망 문자열 한 건을 구조화 RelationHit로 변환한다.

    인식 불가한(미래 추가) 접두사는 None을 반환해 조용히 건너뛴다.
    """
    prefix, _, payload = raw.partition(":")
    rtype = _PREFIX_TO_TYPE.get(prefix)
    if rtype is None:
        return None

    luck_ref = GanjiRef(
        side="luck", position=str(luck_level), stem=luck_stem, branch=luck_branch
    )

    # 천간합: payload = '운천간-원국천간'.
    if rtype is RelationType.STEM_COMBINATION:
        _luck_s, _, natal_stem = payload.partition("-")
        natal_refs = [
            GanjiRef(side="natal", position=pos, stem=natal_stem)
            for pos in _natal_positions_for_stem(pillars, natal_stem)
        ]
        return RelationHit(
            relation_id=f"rel_{rtype}_{luck_stem}_{natal_stem}",
            type=rtype, luck_ref=luck_ref, natal_refs=natal_refs,
        )

    # 삼합/방합 기여: payload = 완성 오행. 원국 구성 지지를 보강.
    if rtype in (RelationType.THREE_HARMONY_CONTRIB, RelationType.DIRECTIONAL_CONTRIB):
        groups = (
            [(m, str(e)) for m, e, _royal in THREE_HARMONY]
            if rtype is RelationType.THREE_HARMONY_CONTRIB
            else [(m, str(e)) for m, e in DIRECTIONAL_COMBINATIONS]
        )
        natal_refs = _contrib_natal_refs(luck_branch, payload, groups, pillars)
        return RelationHit(
            relation_id=f"rel_{rtype}_{luck_branch}_{payload}",
            type=rtype, luck_ref=luck_ref, natal_refs=natal_refs, element=payload,
        )

    # 자형: payload = 지지(운·원국 동일 글자).
    if rtype is RelationType.SELF_PUNISHMENT:
        natal_refs = _natal_refs_for_branch(pillars, payload)
        return RelationHit(
            relation_id=f"rel_{rtype}_{payload}",
            type=rtype, luck_ref=luck_ref, natal_refs=natal_refs,
        )

    # 삼형: payload = '운지지-원국지지들'(연결 문자열).
    if rtype is RelationType.PUNISHMENT_TRIPLE:
        _luck_b, _, partners = payload.partition("-")
        natal_refs = [
            ref for ch in partners for ref in _natal_refs_for_branch(pillars, ch)
        ]
        return RelationHit(
            relation_id=f"rel_{rtype}_{luck_branch}_{partners}",
            type=rtype, luck_ref=luck_ref, natal_refs=natal_refs,
        )

    # 나머지(충·육합·파·해·무례지형·공망 3종): payload = '운지지-원국지지'.
    _luck_b, _, natal_branch = payload.partition("-")
    if not natal_branch:  # 공망전실은 payload가 단일 지지(원국 공망 자리).
        natal_branch = payload
    natal_refs = _natal_refs_for_branch(pillars, natal_branch)
    return RelationHit(
        relation_id=f"rel_{rtype}_{luck_branch}_{natal_branch}",
        type=rtype, luck_ref=luck_ref, natal_refs=natal_refs,
    )


def relation_hits(
    level: GanjiLevel, stem: str, branch: str,
    relations_to_chart: list[str], gongmang_activation: list[str],
    pillars: FourPillarsResult,
) -> list[RelationHit]:
    """운 한 항목의 관계/공망 문자열 목록을 구조화 RelationHit 목록으로 변환한다.

    Args:
        level: 운 계층(대운/세운/월운/일운).
        stem, branch: 운 간지(한자).
        relations_to_chart: 엔진 산출 합충형파해 문자열.
        gongmang_activation: 엔진 산출 공망 활성 문자열.
        pillars: 원국(자리 해소·국 구성 보강에 사용).

    Returns:
        구조화된 관계 적중 목록(인식 불가 항목은 제외).
    """
    hits: list[RelationHit] = []
    for raw in [*relations_to_chart, *gongmang_activation]:
        hit = _relation_hit(raw, level, stem, branch, pillars)
        if hit is not None:
            hits.append(hit)
    return hits


def to_calendar_entry(
    level: GanjiLevel, period: str, stem: str, branch: str,
    relations_to_chart: list[str], gongmang_activation: list[str],
    pillars: FourPillarsResult,
) -> GanjiCalendarEntry:
    """운 한 항목을 구조화 관계를 포함한 GanjiCalendarEntry로 만든다."""
    return GanjiCalendarEntry(
        level=level,
        period=period,
        stem=stem,
        branch=branch,
        ganji=f"{stem}{branch}",
        relations_with_chart=relation_hits(
            level, stem, branch, relations_to_chart, gongmang_activation, pillars
        ),
    )


def _daewoon_entry(item: DaewoonItem, pillars: FourPillarsResult) -> GanjiCalendarEntry:
    """대운 항목 → GanjiCalendarEntry. period는 '시작연도~종료연도'."""
    period = f"{item.approx_start_date.year}~{item.approx_end_date.year}"
    return to_calendar_entry(
        GanjiLevel.DAEWOON, period, item.stem, item.branch,
        item.relations_to_chart, item.gongmang_activation, pillars,
    )


def _luck_entry(pillar: LuckPillar, pillars: FourPillarsResult) -> GanjiCalendarEntry:
    """세운/월운/일운 항목 → GanjiCalendarEntry. period=label, level=period_type 매핑."""
    level = _PERIOD_TYPE_TO_LEVEL.get(pillar.period_type, GanjiLevel.YEAR)
    return to_calendar_entry(
        level, pillar.label, pillar.stem, pillar.branch,
        pillar.relations_to_chart, pillar.gongmang_activation, pillars,
    )


def calendar_entries_from_result(
    result: ManseV2Result, levels: set[GanjiLevel] | None = None
) -> list[GanjiCalendarEntry]:
    """만세 결과에 이미 계산된 운 항목들을 GanjiCalendarEntry 목록으로 변환한다.

    result.luck_cycles의 대운표와 (reference_date가 주어졌을 때 채워지는) 세운/월운/일운을
    구조화한다. 임의 기간의 추가 운은 서비스 계층(luck_months/luck_days)이 반환하는
    LuckPillar를 to_calendar_entry로 직접 변환해 얻는다.

    Args:
        result: 만세력 엔진 결과(pillars·luck_cycles 필요).
        levels: 포함할 계층 집합. None이면 전부.

    Returns:
        구조화된 간지달력 엔트리 목록(계층 순: 대운→세운→월운→일운).
    """
    if result.pillars is None or result.luck_cycles is None:
        return []
    wanted = levels or set(GanjiLevel)
    pillars = result.pillars
    lc = result.luck_cycles

    entries: list[GanjiCalendarEntry] = []
    if GanjiLevel.DAEWOON in wanted:
        entries.extend(_daewoon_entry(d, pillars) for d in lc.daewoon_table)
    if GanjiLevel.YEAR in wanted:
        entries.extend(_luck_entry(p, pillars) for p in lc.yearly_luck)
    if GanjiLevel.MONTH in wanted:
        entries.extend(_luck_entry(p, pillars) for p in lc.monthly_luck)
    if GanjiLevel.DAY in wanted:
        entries.extend(_luck_entry(p, pillars) for p in lc.daily_luck)
    return entries
