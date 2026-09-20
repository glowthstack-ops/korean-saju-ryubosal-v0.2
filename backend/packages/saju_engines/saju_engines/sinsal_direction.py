"""12신살 방위 활용 엔진 + 삼재 맥락 — docs/18 (2026-09-20 데굴님 승인).

파이프라인: `연지 → 삼합 → 지지별 신살 → 절대 방위 → (기준점·랜드마크) → 사용 목적 → 활용 전략`.

- 계산은 전부 여기서 끝난다(절대원칙 1). LLM은 사전 문구를 '활용 방향으로 해석' 톤으로
  재서술만 한다.
- 점수·판정·날짜·간지 파이프라인에 관여하지 않는 서술 전용(inert) 계층이다.
- 기존 `direction_suggestion`(E8 삶의 방향 능동 제안)과 다른 계층이며 이름을 섞지 않는다.
- 용신 오행 방위(`date_selection`/`region_direction`)와 합산 금지 — 답변에서는 "오행 보완
  방향"과 "이동·변화 활용 방향"으로 질문을 분리해 병기한다(지시문에 고정).

삼재는 같은 12신살 표의 시간 축 파생값이다(역마=들·육해=눌·화개=날). 세운 지지 기준이며
세운 경계는 만세력 세운과 같은 입춘 기준이다. 사건 점수에 넣지 않고 맥락 신호로만 쓴다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_shared_types.enums import Branch
from saju_shared_types.intent import Domain, IntentJson, QueryType
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.sinsal_direction import (
    FIT_GRADE_KO,
    Anchor,
    Cardinal4,
    Direction8Code,
    DirectionPick,
    DirectionPurpose,
    DirectionQuadrant,
    DirectionSector,
    LandmarkNote,
    PurposeEntry,
    SinsalDirectionBlock,
    SinsalDirectionDict,
    SinsalDirectionProfile,
    SinsalDirectionRecommendation,
    UsageMode,
)
from saju_shared_types.twelve_sinsal import (
    BASE_MAPS,
    BRANCH_ORDER,
    SAMJAE_LABEL_KO,
    TWELVE_SINSAL_ALIAS,
    TWELVE_SINSAL_HANJA,
    SamjaeInfo,
    SamjaeQuality,
    SamjaeStage,
    samjae_branches,
    trine_group_label,
)

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
SINSAL_DIRECTION_VERSION = "1.1.0"

#: 12지지 고정 방위 — 寅卯辰=동 / 巳午未=남 / 申酉戌=서 / 亥子丑=북. 각도 경계는 두지 않는다.
BRANCH_CARDINAL: dict[Branch, Cardinal4] = {
    Branch.IN: "동", Branch.MYO: "동", Branch.JIN: "동",
    Branch.SA: "남", Branch.O: "남", Branch.MI: "남",
    Branch.SIN: "서", Branch.YU: "서", Branch.SUL: "서",
    Branch.HAE: "북", Branch.JA: "북", Branch.CHUK: "북",
}
CARDINAL_ORDER: tuple[Cardinal4, ...] = ("북", "동", "남", "서")

#: 8방위 코드 → (한글, 후보 지지). 간방은 두 지지 경계에 걸쳐 후보 2개(모호 표시).
DIRECTION8_BRANCHES: dict[str, tuple[str, tuple[Branch, ...]]] = {
    "N": ("북", (Branch.JA,)),
    "NE": ("북동", (Branch.CHUK, Branch.IN)),
    "E": ("동", (Branch.MYO,)),
    "SE": ("남동", (Branch.JIN, Branch.SA)),
    "S": ("남", (Branch.O,)),
    "SW": ("남서", (Branch.MI, Branch.SIN)),
    "W": ("서", (Branch.YU,)),
    "NW": ("북서", (Branch.SUL, Branch.HAE)),
}
_OPPOSITE8: dict[str, str] = {
    "N": "S", "S": "N", "E": "W", "W": "E", "NE": "SW", "SW": "NE", "SE": "NW", "NW": "SE",
}

USAGE_MODE_KO: dict[UsageMode, str] = {
    UsageMode.POSITION: "공간 내 위치(방 중심 기준 그 물건이 놓이는 쪽)",
    UsageMode.FACE: "바라보는 방향(앉아서 시선이 향하는 쪽)",
    UsageMode.HEAD: "잠잘 때 머리 방향",
    UsageMode.MOVE: "이동 목적지 방향(현 위치 기준)",
    UsageMode.ENTRANCE: "출입구·문 방향",
}

ANCHOR_KO: dict[Anchor, str] = {
    Anchor.HOME_CENTER: "집 전체 중심",
    Anchor.ROOM_CENTER: "방 중심",
    Anchor.USER_POSITION: "지금 있는 자리(책상·침대 등 본인 위치)",
}

#: 능동 제안 — 채팅 질문 유형 → 목적(도메인과 별개 트리거). 감정지원은 상담·명상 방향.
_QUERY_TYPE_PURPOSES: dict[QueryType, tuple[DirectionPurpose, ...]] = {
    QueryType.EMOTIONAL_SUPPORT: (DirectionPurpose.COUNSELING,),
}
#: 능동 제안 미노출 질문 유형(용어교육·피드백·범위외 — 방향 제안이 소음이 되는 유형).
# 택일(Q4)은 이미 용신 오행 방위 블록을 싣는다 — 역마 방향을 능동으로 덧붙이면 같은 답에 서로
# 다른 방위 결론이 두 개가 되므로 제외(리뷰 수정 2026-09-20). 수동 방향 질문은 영향 없음.
_NO_PROACTIVE_QUERY_TYPES = frozenset({
    QueryType.TERMINOLOGY_EDUCATION, QueryType.FEEDBACK_CORRECTION, QueryType.OUT_OF_SCOPE,
    QueryType.COMPARISON, QueryType.DATE_RECOMMENDATION,
})
MAX_PROACTIVE_PURPOSES = 2


@lru_cache(maxsize=8)
def load_sinsal_direction_dict(
    dictionaries_dir: Path = _DICTS_DEFAULT, compiled_dir: Path = _COMPILED_DEFAULT
) -> SinsalDirectionDict:
    """방위 활용 사전 로드 — 컴파일 스냅샷 우선, 원본 폴백(원칙 5)."""
    snapshot = compiled_dir / f"sinsal_direction_v{SINSAL_DIRECTION_VERSION}.json"
    if snapshot.exists():
        return SinsalDirectionDict.model_validate(json.loads(snapshot.read_text("utf-8")))
    raw = json.loads((dictionaries_dir / "sinsal_direction.json").read_text("utf-8"))
    return SinsalDirectionDict.model_validate(raw)


# ── 프로필 ────────────────────────────────────────────────────────────────────


def sinsal_label(name: str) -> str:
    """사용자 노출 표기 — '년살(年殺·도화살)' 처럼 한자·별칭 병기."""
    hanja = TWELVE_SINSAL_HANJA.get(name, "")
    alias = TWELVE_SINSAL_ALIAS.get(name)
    inner = "·".join(x for x in (hanja, alias) if x)
    return f"{name}({inner})" if inner else name


def build_direction_profile(
    year_branch: Branch, dictionary: SinsalDirectionDict | None = None
) -> SinsalDirectionProfile:
    """출생 연지 → 12방위 신살 프로필. 연지는 만세력 年支(입춘 기준)를 그대로 받는다."""
    dic = dictionary or load_sinsal_direction_dict()
    table = BASE_MAPS[year_branch]
    sectors: list[DirectionSector] = []
    for b in BRANCH_ORDER:
        name = table[b]
        entry = dic.sinsal(name)
        sectors.append(DirectionSector(
            branch=str(b), absolute_direction=BRANCH_CARDINAL[b],
            relative_sinsal=name, group=entry.group, sequence_index=entry.sequence_index,
        ))
    quadrants: list[DirectionQuadrant] = []
    for card in CARDINAL_ORDER:
        # 구간 순서(1→2→3 상태 전이)로 정렬 — 북은 子丑亥가 아니라 亥子丑 순으로 읽힌다.
        secs = sorted(
            (s for s in sectors if s.absolute_direction == card), key=lambda s: s.sequence_index
        )
        group = dic.group(secs[0].group)
        quadrants.append(DirectionQuadrant(
            absolute_direction=card,
            branches=[s.branch for s in secs],
            sinsals=[s.relative_sinsal for s in secs],
            group=group.key, theme=group.quadrant_theme, service_use=group.service_use,
        ))
    return SinsalDirectionProfile(
        year_branch=str(year_branch), trine_group=trine_group_label(year_branch),
        sectors=sectors, quadrants=quadrants,
        samjae_branches=[str(b) for b in samjae_branches(year_branch)],
    )


def profile_from_result(
    result: ManseV2Result, dictionary: SinsalDirectionDict | None = None
) -> SinsalDirectionProfile | None:
    """ManseV2Result 어댑터 — 원국이 없으면 None."""
    if result.pillars is None:
        return None
    return build_direction_profile(Branch(result.pillars.year.branch), dictionary)


# ── 목적 추천 ─────────────────────────────────────────────────────────────────


def _fill_action(entry: PurposeEntry, sector: DirectionSector) -> str:
    """목적 행동 템플릿에 방향·지지·신살(한자·별칭 병기)을 채운다."""
    return entry.action_template.format(
        direction=sector.absolute_direction, branch=sector.branch,
        sinsal=sinsal_label(sector.relative_sinsal),
    )


def recommend_for_purpose(
    profile: SinsalDirectionProfile,
    purpose: DirectionPurpose,
    dictionary: SinsalDirectionDict | None = None,
) -> SinsalDirectionRecommendation:
    """목적 1종 → 적합·보조 방향(우선순위순)과 같은 4방 안의 주의 신살.

    등급은 사전 매트릭스(목적 × 개별 신살)를 그대로 읽는다 — 구간 단위 점수로 뭉개지 않는다
    (년살 fit / 월살 caution 처럼 같은 구간 안에서도 갈린다).
    """
    dic = dictionary or load_sinsal_direction_dict()
    entry = dic.purpose(purpose)
    picks: list[DirectionPick] = []
    for name in entry.primary_sinsals:
        sec = profile.sector_of(name)
        picks.append(DirectionPick(
            sinsal=name, branch=sec.branch, absolute_direction=sec.absolute_direction,
            grade=entry.grades[name], action=_fill_action(entry, sec),
        ))
    for sec in profile.sectors:  # primary 외 적합·보조는 후순위로 보충
        g = entry.grades[sec.relative_sinsal]
        if g in ("fit", "support") and all(p.sinsal != sec.relative_sinsal for p in picks):
            picks.append(DirectionPick(
                sinsal=sec.relative_sinsal, branch=sec.branch,
                absolute_direction=sec.absolute_direction, grade=g,
                action=_fill_action(entry, sec),
            ))
    pick_cards = {p.absolute_direction for p in picks if p.grade == "fit"}
    cautions = [
        DirectionPick(
            sinsal=sec.relative_sinsal, branch=sec.branch,
            absolute_direction=sec.absolute_direction, grade="caution",
            action=dic.sinsal(sec.relative_sinsal).cautions[0]
            if dic.sinsal(sec.relative_sinsal).cautions else "",
        )
        for sec in profile.sectors
        if entry.grades[sec.relative_sinsal] == "caution" and sec.absolute_direction in pick_cards
    ]
    return SinsalDirectionRecommendation(
        purpose=purpose, purpose_ko=entry.name_ko, usage_mode=entry.usage_mode,
        picks=picks, cautions=cautions,
        strategy=dic.sinsal(entry.primary_sinsals[0]).strategy,
    )


def detect_purposes_for_intent(
    intent: IntentJson, dictionary: SinsalDirectionDict | None = None
) -> list[DirectionPurpose]:
    """능동 제안 — 질문의 도메인·유형에서 목적을 도출한다(질문이 방향을 묻지 않아도).

    사전 `trigger_domains` 순서대로, 도메인 우선순위(intent.domain → domains)로 최대 2개.
    """
    if intent.query_type in _NO_PROACTIVE_QUERY_TYPES:
        return []
    dic = dictionary or load_sinsal_direction_dict()
    ordered_domains: list[str] = []
    for d in [intent.domain, *intent.domains]:
        if d is not Domain.GENERAL and str(d) not in ordered_domains:
            ordered_domains.append(str(d))
    out: list[DirectionPurpose] = []
    for p in _QUERY_TYPE_PURPOSES.get(intent.query_type, ()):
        out.append(p)
    for dom in ordered_domains:
        for entry in dic.purposes:
            if dom in entry.trigger_domains and entry.purpose not in out:
                out.append(entry.purpose)
    return out[:MAX_PROACTIVE_PURPOSES]


# ── 랜드마크(프로필 거실 주 창 방향) ─────────────────────────────────────────


def landmark_from_facing(
    profile: SinsalDirectionProfile, facing: Direction8Code | str | None
) -> LandmarkNote | None:
    """거실 주 창 8방위 → '창 쪽 / 창을 등진 쪽' 상대 랜드마크 번역(P2 보완안).

    이익: 절대 방위를 사용자가 아는 물체(창)로 바꿔 행동으로 옮기기 쉽다. 문제: ①간방은
    지지 2개 경계라 모호 → 후보 2개 병기 + 나침반 확인 권고 ②거실 창이지 침실·서재 창이
    아님 → 고지 ③8방위 입력값의 정확도 → 확인 문구. 방향 계산 자체(절대 방위)는 바꾸지 않는다.
    """
    if not facing or facing == "unknown" or facing not in DIRECTION8_BRANCHES:
        return None
    ko, branches = DIRECTION8_BRANCHES[facing]
    _oko, opp = DIRECTION8_BRANCHES[_OPPOSITE8[facing]]

    table = BASE_MAPS[Branch(profile.year_branch)]

    def _side(bs: tuple[Branch, ...]) -> list[str]:
        """후보 지지들을 '지지 신살' 표기로."""
        return [f"{b} {table[b]}" for b in bs]

    return LandmarkNote(
        facing_code=facing, facing_ko=ko,
        window_side=_side(branches), opposite_side=_side(opp), ambiguous=len(branches) > 1,
    )


# ── 블록 조립·직렬화 ──────────────────────────────────────────────────────────


def build_sinsal_direction_block(
    result: ManseV2Result,
    purposes: list[DirectionPurpose],
    *,
    living_room_facing: str | None = None,
    proactive: bool = True,
    dictionary: SinsalDirectionDict | None = None,
    profile: SinsalDirectionProfile | None = None,
) -> SinsalDirectionBlock | None:
    """LLM 입력 블록 — 원국 없음 또는 목적 없음(능동 모드)이면 None.

    profile을 주면(리포트가 1회 계산해 둔 값) 프로필을 다시 만들지 않는다.
    """
    if proactive and not purposes:  # 대부분의 턴 — 프로필을 만들기 전에 끝낸다
        return None
    dic = dictionary or load_sinsal_direction_dict()
    profile = profile or profile_from_result(result, dic)
    if profile is None:
        return None
    recs = [recommend_for_purpose(profile, p, dic) for p in purposes]
    return SinsalDirectionBlock(
        profile=profile, recommendations=recs,
        landmark=landmark_from_facing(profile, living_room_facing),
        anchor=Anchor.USER_POSITION, proactive=proactive,
    )


def format_profile_lines(profile: SinsalDirectionProfile) -> list[str]:
    """4방 방향판(목적별 방향판 — '좋은 방향 1개' 아님)."""
    lines = [
        f"연지 {profile.year_branch}({profile.trine_group} 삼합) 기준 12신살 방위 — "
        "방향 자체의 길흉이 아니라 '그 방향의 신살 × 무엇을 하려는가'로 활용도를 본다.",
    ]
    for q in profile.quadrants:
        pairs = " · ".join(f"{b} {s}" for b, s in zip(q.branches, q.sinsals, strict=True))
        lines.append(f"- {q.absolute_direction}쪽 — {q.theme}: {pairs} → {q.service_use}")
    return lines


def format_sinsal_direction_lines(block: SinsalDirectionBlock | None) -> list[str]:
    """질문 가변 suffix용 [방위 활용] 블록. 비었으면 무헤더."""
    if block is None:
        return []
    lines = ["", "[방위 활용 — 12신살 기준(서술 전용, 점수·판정 무관)]"]
    lines += format_profile_lines(block.profile)
    for rec in block.recommendations:
        lines.append(
            f"◆ 목적 '{rec.purpose_ko}' — 사용 방식: {USAGE_MODE_KO[rec.usage_mode]}"
        )
        for i, p in enumerate(rec.picks):
            head = (
                f"  · [{FIT_GRADE_KO[p.grade]}] {p.absolute_direction}쪽 {p.branch} "
                f"{sinsal_label(p.sinsal)}"
            )
            # 1순위만 행동 문장을 붙이고 나머지는 후보로만 나열(토큰 절약·반복 차단).
            lines.append(f"{head} — {p.action}" if i == 0 else head)
        for c in rec.cautions:
            lines.append(
                f"  · [주의] 같은 {c.absolute_direction}쪽 안의 {c.branch} {c.sinsal} — {c.action}"
            )
    lines.append(
        f"기준점: {ANCHOR_KO[block.anchor]} — 사용자가 기준점을 말하지 않았으면 "
        "이 기준임을 한 줄로 밝힐 것."
    )
    if block.landmark is not None:
        lines.append(format_landmark_line(block.landmark))
    return lines


def format_landmark_line(lm: LandmarkNote) -> str:
    """랜드마크(거실 주 창) 프롬프트 줄 — 채팅·리포트 공용(문구 단일 원천)."""
    return (
        f"랜드마크(프로필 거실 주 창={lm.facing_ko}): 창 쪽={', '.join(lm.window_side)} / "
        f"창을 등진 쪽={', '.join(lm.opposite_side)}"
        + (" — 간방이라 두 지지에 걸치므로 나침반 앱으로 확인을 권할 것." if lm.ambiguous else "")
        + " 거실 창 기준이므로 침실·서재는 방 창 방향을 따로 확인하라고 안내할 것."
    )


def format_purpose_table_lines(
    profile: SinsalDirectionProfile, dictionary: SinsalDirectionDict | None = None
) -> list[str]:
    """목적 13종 전체를 한 줄씩 — 리포트 전용 섹션(F-20b·Y-11b)용 목적별 방향판."""
    dic = dictionary or load_sinsal_direction_dict()
    lines = ["[목적별 활용 방향 — 목적 13종 전체(우선 신살 → 방향, 같은 4방 안 주의 신살)]"]
    for entry in dic.purposes:
        rec = recommend_for_purpose(profile, entry.purpose, dic)
        first = rec.picks[0]
        rest = " · ".join(f"{p.branch} {p.sinsal}" for p in rec.picks[1:3])
        caution = " / ".join(f"{c.branch} {c.sinsal}" for c in rec.cautions)
        mode = USAGE_MODE_KO[rec.usage_mode].split("(")[0]
        line = (
            f"- {entry.name_ko}({mode}): {first.absolute_direction}쪽 {first.branch} "
            f"{sinsal_label(first.sinsal)}"
        )
        if rest:
            line += f" [보조: {rest}]"
        if caution:
            line += f" [주의: {caution}]"
        lines.append(line)
    return lines


SINSAL_DIRECTION_INSTRUCTION = (
    "[방위 활용 지침] 위 [방위 활용] 블록은 연지 삼합 기준 12신살을 방위에 배치한 '활용 해석'이다. "
    "①방향에 절대 길흉을 부여하지 말 것('북쪽은 나쁜 방향' 금지) — '북쪽은 겁살·재살·천살 "
    "구간이라 집중·연구·계획처럼 머무르는 활동과 연결해 해석한다'처럼 목적형으로 쓸 것. "
    "②사용 방식(위치/바라보는 방향/머리 방향/이동/출입구)을 섞지 말고 목적에 맞는 한 가지로 "
    "안내할 것. ③같은 4방 안에서도 신살마다 쓰임이 다르니 지지 단위까지 짚을 것(예: 서쪽 중 "
    "酉가 년살). ④용신 오행 방위(색·방향 개운)와 합산하지 말고, 둘 다 있으면 '오행 보완 방향'과 "
    "'활용 방향'으로 질문을 분리해 병기할 것. ⑤'활용해 볼 수 있다'·'연결해 해석한다' 톤 — "
    "'이 방향이면 합격/성공/결혼' 류 단정 금지. ⑥각도·도수를 지어내지 말 것. 나침반 확인은 "
    "권고로만. ⑦기준점(방 중심/본인 자리)을 한 줄로 밝히고, 랜드마크(창 쪽)가 있으면 그것으로 "
    "행동을 구체화할 것."
)


# ── 삼재(시간 축) ─────────────────────────────────────────────────────────────


def samjae_for_year(result: ManseV2Result, year: int) -> SamjaeInfo | None:
    """달력연도의 삼재 정보 — 저장된 세운 기둥(luck_cycles)의 stage에 quality를 얹은 값."""
    from .samjae_quality import evaluate_samjae  # 순환 import 방지(지연)

    return evaluate_samjae(result, year)


def format_samjae_lines(
    result: ManseV2Result,
    years: list[int],
    *,
    dictionary: SinsalDirectionDict | None = None,
    current_year: int | None = None,
    candidates: list | None = None,
) -> list[str]:
    """[삼재 흐름] 블록 — 창 안에 삼재 해가 없으면 빈 목록(무소음).

    각 삼재 해에 stage(들/눌/날) + quality(복/평/악, `samjae_quality.evaluate_samjae`)·강도·
    겹삼재·근거·도메인 등급·단계×품질 표현을 싣는다. 수치·내부 신호명·후보 유무는 싣지 않는다
    (LLM이 그대로 옮기는 것을 막기 위해 — 2026-09-20 데굴님 지시).
    """
    from .samjae_quality import evaluate_samjae  # 순환 import 방지(지연)

    if result.pillars is None:
        return []
    dic = dictionary or load_sinsal_direction_dict()
    hits = [
        (y, info) for y in years
        if (info := evaluate_samjae(result, y, candidates, dictionary=dic)) is not None
    ]
    if not hits:
        return []
    yb = Branch(result.pillars.year.branch)
    enter, stay, leave = samjae_branches(yb)
    lines = [
        "",
        "[삼재 흐름 — 연지 삼합 기준 역마→육해→화개 3년"
        "(단계=맥락, 복/평/악=원국·대운·세운 작용 판정 · 입춘 기준 세운)]",
        f"연지 {yb}({trine_group_label(yb)}) → 삼재 해 지지: "
        f"{enter}(들) → {stay}(눌) → {leave}(날)",
    ]
    for y, info in hits:
        stage_entry = next(s for s in dic.samjae_stages if s.stage == info.stage.value)
        mark = " ◀ 올해" if current_year is not None and y == current_year else ""
        head = f"- {y}년 {info.label_ko}({info.sinsal}, {info.sequence_index}/3){mark}"
        if info.quality_label:
            head += (
                f" · {info.quality_label}(뚜렷한 방향 없음, 강도 {info.strength_label})"
                if info.quality is SamjaeQuality.NORMAL
                else f" · {info.quality_label} 성격 우세(강도 {info.strength_label})"
            )
        if info.overlap_label:
            head += f" · {info.overlap_label}"
        lines.append(head + f": {stage_entry.core_signal}")
        if info.stage_quality_phrase:
            lines.append(f"  단계×성격: {info.stage_quality_phrase}")
        if info.evidence:
            marks = {"positive": "+", "negative": "−", "neutral": "·"}
            lines.append(
                "  근거: " + " / ".join(f"{e.note}({marks[e.effect]})" for e in info.evidence)
            )
        if info.domains:
            grade_ko = {"favorable": "유리", "mixed": "혼합", "caution": "주의"}
            lines.append(
                "  영역: " + " · ".join(f"{d.domain_ko} {grade_ko[d.grade]}" for d in info.domains)
            )
        for kind in dic.samjae_quality.overlap_kinds:
            if kind.kind in info.overlap:
                lines.append(f"  {kind.label_ko}: {kind.phrase}")
        lines.append(f"  사건 후보 예: {', '.join(stage_entry.event_candidates[:5])}")
    return lines


SAMJAE_INSTRUCTION = (
    "[삼재 지침] 삼재는 '나쁜 해'가 아니라 이동(들)→마찰·적응(눌)→정리(날) 3단계 변화 과정이며, "
    "복/평/악은 그 변화가 명식에 유리·중립·불리하게 작용할 조건을 원국·대운·세운으로 따로 판정한 "
    "결과다. ①'올해는 들삼재이지만 복삼재 성격이 우세하다'처럼 단계와 성격을 함께 쓰고, 단계×성격 "
    "표현과 근거를 문장으로 풀 것 — 근거 라벨·기호를 그대로 나열하지 말 것. ②복삼재≠대길, 악삼재≠"
    "사고 확정, 평삼재=방향성 없음(변화는 있으나 어느 쪽으로도 강하게 기울지 않음). ③영역 등급이 "
    "있으면 '전체 성격'과 '영역별 차이'를 나눠 쓸 것. ④겹삼재는 방향이 아니라 강도의 문제로만. "
    "⑤'삼재라서 큰일'·'삼재니까 조심만' 류 공포 조장 금지, 삼재 해가 아닌 해에 삼재 언급 금지. "
    "⑥점수·수치·내부 신호명·데이터/후보의 유무나 부족을 절대 언급하지 말 것 — 있는 근거만으로 "
    "서술한다. 경계는 사주 세운과 같은 입춘 기준임을 필요 시 한 문장으로만."
)


def samjae_stage_label(stage: SamjaeStage) -> str:
    """내부 enum → 사용자 노출 라벨."""
    return SAMJAE_LABEL_KO[stage]
