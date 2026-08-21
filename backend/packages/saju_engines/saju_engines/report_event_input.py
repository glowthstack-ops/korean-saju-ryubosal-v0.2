"""리포트 전용 이벤트 LLM 입력 (채팅과 분리 — 정밀·구조화).

채팅은 대화형 압축 입력이지만, 리포트는 섹션 서술의 정밀도가 중요하다. 후보를 **시점 클러스터**로
묶고 per-글자 십성(천간 辛=식신 / 지지 亥=정재)과 관계 분해(運亥↔원국巳 충 / 亥亥 자형)를 함께
명시한다. 엔진이 이미 계산한 값을 노출해 LLM이 '재성 지지 충' 류 임의 표현을 짓지 못하게 한다
(명리 계산 불변 — 입력 명시만). 같은 시점의 여러 사건은 한 블록으로 병합한다(반복 방지).
"""

from __future__ import annotations

from saju_shared_types.event_taxonomy_v2 import (
    EVENT_DOMAIN,
    direction_label,
    event_display_ko,
    result_direction,
)
from saju_shared_types.events import EventCandidate, confidence_ko
from saju_shared_types.ganji_calendar import GanjiLevel, RelationType
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.marriage_timing import derive_marriage_stage

from . import sinsal_modifier_config as _sinsal_cfg
from .candidate_semantics import candidate_semantics, review_month_from_signals
from .context_reducer import event_ko, polarity_ko
from .ganji_calendar import relation_hits
from .llm_event_serializer import score_band
from .sinsal_numeric_scoring import apply_sinsal_channel_shadow, channel_note_ko


def _dir(c: EventCandidate) -> str:
    """후보 방향(길흉)+타이밍 라벨 — 모호한 polarity 대신. 없으면 polarity 폴백."""
    return direction_label(c.quality, c.timing) or polarity_ko(str(c.polarity))


def _marriage_stage_note(c: EventCandidate) -> str:
    """관계 단계(MT) 접미사 — MT 신호가 있을 때만(비-MT·default 프로파일은 빈 문자열, 출력 불변).

    리포트(총운·년운·애정운)의 후보 라인에 결혼 '확정'이 아니라 '단계'로 표기한다(Step 2).
    """
    st = derive_marriage_stage(c.evidence_path)
    if not st.stage:
        return ""
    lim = f"; 상한 {st.stage_limit}" if st.stage_limit else ""
    return f" · 관계단계 {st.stage}(근거 {' / '.join(st.stage_reason)}{lim})"

# 도메인 코드 → 한글(12개월 흐름 표기용).
_DOMAIN_KO: dict[str, str] = {
    "career": "직업", "wealth": "재물", "relationship": "관계",
    "health": "건강", "relocation": "이동", "education": "학업",
}
_DOMAIN_BY_KEY: dict[str, str] = {str(k): v for k, v in EVENT_DOMAIN.items()}

# RelationType → 정확한 한글 관계명(엔진 계산값을 그대로 노출).
_REL_KO: dict[RelationType, str] = {
    RelationType.BRANCH_CLASH: "충",
    RelationType.SELF_PUNISHMENT: "자형",
    RelationType.PUNISHMENT_TRIPLE: "삼형",
    RelationType.PUNISHMENT_MUTUAL: "상형",
    RelationType.BRANCH_BREAK: "파",
    RelationType.HARM: "해",
    RelationType.SIX_COMBINATION: "육합",
    # 두 글자 결집은 완성 합국이 아니다(P0, 2026-07-22 데굴님 확정) — '삼합/방합'으로만
    # 표기하면 완성 국으로 오해된다. 미완성·부분 결집임을 라벨에 명시.
    RelationType.THREE_HARMONY_CONTRIB: "삼합 일부 결집(미완성·세력 보조)",
    RelationType.DIRECTIONAL_CONTRIB: "방합 일부 결집(미완성·세력 보조)",
    RelationType.STEM_COMBINATION: "천간합",
    RelationType.VOID_FILL: "공망",
    # 공망 충발 정의(2026-07-22 명문화): 엔진 효과 = 점수 -10 + 발현 지연(timing=delay),
    # 방향·사건 성립 불변 — 실패·무산 판정 신호가 아니다. 라벨에 보조 성격을 명시한다.
    RelationType.VOID_TRIGGER_CLASH: "공망 충발(지연·변동 보조)",
    RelationType.VOID_RELEASE_COMBINE: "공망 해소",
}
# 한 글자가 원국 같은 글자를 만나는 복음(伏吟)은 자형과 별개로 표기.
_DUPLICATE_NOTE = "복음(같은 글자 반복)"


def _pillar_lookup(result: ManseV2Result) -> dict[str, LuckPillar]:
    out: dict[str, LuckPillar] = {}
    lc = result.luck_cycles
    if lc is None:
        return out
    for p in [*lc.yearly_luck, *lc.monthly_luck, *lc.daily_luck]:
        out[p.label] = p
    for d in lc.daewoon_table:
        for p in d.sewoon or []:
            out.setdefault(p.label, p)
    return out


def _level(period: str) -> GanjiLevel:
    if len(period) == 4:
        return GanjiLevel.YEAR
    if len(period) == 7:
        return GanjiLevel.MONTH
    return GanjiLevel.DAY


def _relation_lines(pillar: LuckPillar, level: GanjiLevel, result: ManseV2Result) -> list[str]:
    """그 시점 운 글자가 원국과 맺는 관계를 글자 단위로 분해한다."""
    assert result.pillars is not None
    hits = relation_hits(
        level, pillar.stem, pillar.branch,
        pillar.relations_to_chart, pillar.gongmang_activation, result.pillars,
    )
    out: list[str] = []
    for h in hits:
        name = _REL_KO.get(h.type)
        if name is None:
            continue
        # endpoint 불변식(P0, 2026-07-22): 천간 관계는 천간끼리, 지지 관계는 지지끼리만
        # 표기한다 — '運 子↔원국 丁 천간합' 같은 혼합 표기 차단(원천은 ganji_calendar에서
        # 교정, 여기는 과거 데이터·타 생산자 대비 이중 방어).
        if h.type is RelationType.STEM_COMBINATION:
            luck_c = h.luck_ref.stem or ""
            natal_chars = [r.stem or "" for r in h.natal_refs if r.stem]
        else:
            luck_c = h.luck_ref.branch or ""
            natal_chars = [r.branch or "" for r in h.natal_refs if r.branch]
        natal = "·".join(dict.fromkeys(natal_chars))
        if not (luck_c and natal):
            continue
        line = f"運 {luck_c}↔원국 {natal} {name}"
        if luck_c in natal_chars:
            line += f"·{_DUPLICATE_NOTE}"
        out.append(line)
    return list(dict.fromkeys(out))


def _sinsal_channel_note(
    result: ManseV2Result, period: str, ganji: str, evs: list[EventCandidate],
) -> str:
    """그 기간 재활성 신살의 채널 색채 노트(B-2 운영 반영) — 숫자 없는 한글, 발생 가능성 불변.

    채널은 기간 단위(간지 기반)라 대표 1건만 계산해 부착한다. 게이트 off면 빈 문자열.
    """
    if not _sinsal_cfg.SINSAL_CHANNEL_APPLY_ENABLED or not evs:
        return ""
    rows = apply_sinsal_channel_shadow(result, evs[:1], {period: ganji}, domain="general")
    if not rows:
        return ""
    r = rows[0]
    return channel_note_ko(
        r["favorability_delta"], r["risk_delta"], r["mitigation_delta"],
        r.get("texture_tags", []),
    )


def precise_candidate_clusters(
    result: ManseV2Result, candidates: list[EventCandidate],
    *,
    fav_map: dict[str, str] | None = None,
    rank_by_period: dict[str, tuple[int, bool, int]] | None = None,
) -> list[str]:
    """후보를 시점 클러스터로 묶어 운간지·per-글자 십성·관계 분해·점수를 정밀 출력한다.

    2026-08-21 채팅 패리티: fav_map을 주면 시점별 결실 뉘앙스 마커(⚠계약·결실 불리/
    ↗통관 순화/⚠길신 누설)와 후보별 검토월(공망 충발 한정)을 함께 표기하고,
    rank_by_period를 주면 '기간 내 상대 N/M위'(절대 강도와 분리)를 병기한다.
    판정·점수 불변 — 표기 전용.
    """
    if result.pillars is None:
        return []
    lookup = _pillar_lookup(result)
    by_period: dict[str, list[EventCandidate]] = {}
    for c in candidates:
        by_period.setdefault(c.period, []).append(c)

    lines: list[str] = []
    for period in sorted(by_period):
        evs = sorted(by_period[period], key=lambda c: -c.score)
        p = lookup.get(period)
        if p is None:  # 간지 미상 — 사건만 나열.
            for c in evs:
                lines.append(f"[{period}] {event_ko(c.event_key)}: {c.score}점")
            continue
        head = (
            f"[{period} {p.ganji}] 천간 {p.stem}={p.stem_ten_god or '?'}, "
            f"지지 {p.branch}={p.branch_ten_god or '?'}"
        )
        rels = _relation_lines(p, _level(period), result)
        if rels:
            head += " · 관계: " + ", ".join(rels)
        nuance_note = ""
        if fav_map:
            _cat, nuance_note, _rev = candidate_semantics(evs[0], p.ganji, fav_map)
        if rank_by_period and period in rank_by_period:
            _r, _tied, _n = rank_by_period[period]
            head += (
                f" · 기간 내 상대 {_r}/{_n}위{'(공동)' if _tied else ''}"
                "(절대 강도와 별개 — 표현이 같아도 상대 비중은 이 순위)"
            )
        lines.append(head)
        if nuance_note:
            lines.append(f"  ⚠유불리: {nuance_note}")
        note = _sinsal_channel_note(result, period, p.ganji, evs)
        if note:
            lines.append(f"  {note}")
        for c in evs:
            review = (
                " · 검토월(공망 충발 — 계약 유지력 낮음, 조사·조건 확인까지)"
                if fav_map and review_month_from_signals(list(c.signals)) else ""
            )
            lines.append(
                f"  - {event_display_ko(str(c.event_key), c.quality, c.timing)}: "
                f"신호 강도 {c.score} · "
                f"신뢰도 {confidence_ko(c.confidence)} · {_dir(c)}"
                f"{review}{_marriage_stage_note(c)}"
            )
    return lines


def _adjacent_period(a: str, b: str) -> bool:
    """두 기간 라벨이 같은 사건의 연속 신호로 볼 만큼 인접한가(같은 해 이웃 달·동일 기간)."""
    if a == b:
        return True
    if len(a) == 7 and len(b) == 7 and a[:4] == b[:4]:
        return abs(int(a[5:7]) - int(b[5:7])) <= 1
    return False


def select_table_candidates(
    pool: list[EventCandidate], cap: int = 12
) -> list[EventCandidate]:
    """부록 점수표 후보 계층 선별(P3, 2026-07-22 데굴님 확정) — 점수순 Top-N 편향 교정.

    순서: ①동일 event_key의 인접 기간 중복 제거(강한 신호 유지 — 같은 사건 반복 차단)
    ②결과 방향(긍정/부정/지연/중립)별 대표 후보를 존재하는 방향만 우선 확보 — 고정 긍정
    쿼터 금지(억지 낙관 편향 차단, 실제 후보가 있을 때만 노출) ③잔여는 점수순 충원.
    판정·점수 불변 — 표에 실을 후보의 '선별'만 바꾼다.
    """
    ranked = sorted(pool, key=lambda c: -c.score)
    deduped: list[EventCandidate] = []
    for c in ranked:
        if any(
            d.event_key == c.event_key and _adjacent_period(str(d.period), str(c.period))
            for d in deduped
        ):
            continue
        deduped.append(c)
    # 방향별 대표(존재하는 방향만) → 잔여 점수순.
    picked: list[EventCandidate] = []
    seen_dir: set[str] = set()
    for c in deduped:
        d = result_direction(c.quality, c.timing)
        if d not in seen_dir:
            seen_dir.add(d)
            picked.append(c)
    for c in deduped:
        if len(picked) >= cap:
            break
        if c not in picked:
            picked.append(c)
    return sorted(picked[:cap], key=lambda c: (str(c.period), -c.score))


def score_table_lines(
    result: ManseV2Result, candidates: list[EventCandidate]
) -> list[str]:
    """부록 점수표 — 실제 마크다운 표(시점·운간지·사건·신호 강도·신뢰도·방향·정밀 근거).

    2026-07-22 데굴님 확정(P2): '점수'는 길흉이 아니라 발동 강도이므로 '신호 강도'로
    표기하고, 사건명은 결과 방향 인지 라벨(event_display_ko — '횡재+손실' 모순 차단)로
    치환한다. 판정·점수 값 자체는 불변(표기 전용).

    이 표 블록은 순수 데이터 행만 담는다(2026-08-14 누출 수정) — 부록 섹션이 표를
    verbatim 복사하도록 지시받으므로, 표에 끼운 평문 캡션·지시문은 사용자 본문에
    그대로 노출되고 마크다운 표 렌더링도 깨뜨린다. '신호 강도=발동 강도' 안내는
    섹션 가이드(_SCORE_TABLE_GUIDE)가 LLM 자기 문장 서술로 맡는다.
    """
    if result.pillars is None:
        return []
    lookup = _pillar_lookup(result)
    out = [
        "| 시점 | 운간지 | 사건 | 신호 강도 | 신뢰도 | 예상 방향 | 십성·관계 근거 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in sorted(candidates, key=lambda x: (x.period, -x.score)):
        p = lookup.get(c.period)
        ganji = p.ganji if p else "—"
        if p is not None:
            tengods = (
                f"{p.stem}={p.stem_ten_god or '?'}/{p.branch}={p.branch_ten_god or '?'}"
            )
            rels = ", ".join(_relation_lines(p, _level(c.period), result))
            # 기여 일치(P0 감사, 2026-07-22): 그 시기의 관계 적중은 기간 공통 데이터라,
            # 이 후보 점수에 관계 신호가 실제 기여('관계 발동')했을 때만 점수 근거로
            # 제시한다. 아니면 '시기 참고'로 구분 — 무관 관계가 점수 근거처럼 보이는
            # 착시 차단(관계별 delta 구조화는 후속 과제). 이 마커는 표 셀에 실려
            # 사용자에게 그대로 보이므로 대괄호 없는 읽기용 표현을 쓴다(2026-08-14).
            rel_contributed = any(
                s.name == "관계 발동" or s.type in ("relation", "hap", "clash")
                for s in c.signals
            )
            if rels and not rel_contributed:
                rels = f"(시기 참고 — 점수의 직접 근거 아님) {rels}"
            evidence = tengods + (" · " + rels if rels else "")
        else:
            evidence = "—"
        out.append(
            f"| {c.period} | {ganji} | {event_display_ko(str(c.event_key), c.quality, c.timing)}"
            f" | {c.score} | {confidence_ko(c.confidence)} | {_dir(c)} | {evidence} |"
        )
    return out


def month_overview_lines(
    result: ManseV2Result, scored: list[EventCandidate], domain: str | None = None,
    *, notable_only: bool = False, months_filter: set[str] | None = None,
) -> list[str]:
    """이 해 12개월 전체를 한 줄씩 — 월 간지·운 품질 등급·우세 도메인·강도밴드·길흉·대표 신호.

    한해풀이에서 한두 강신호가 전 섹션에 반복되는 문제(2026-06-16)를 막기 위해, 월별 흐름
    섹션이 12개월을 빠짐없이 고르게 다루도록 모든 달을 데이터로 제공한다. 점수는 절대값 대신
    강/중/약 밴드로 노출한다(표시용 격하). 신호 없는 달도 누락하지 않는다(빠짐없이 12줄).

    각 달에 운 품질 등급(luck_label '강한 용신운' 등)을 〈…〉로 함께 노출한다 — 좋은 달/주의할
    달은 사건 밀도가 아니라 이 운 품질이 1차 기준이다(길흉=용신/기신). 신약 사주에 천간·지지가
    모두 용신인 '강한 용신운' 달은 사건이 적어도 기반이 가장 좋은 달이라, ★주목에도 포함한다.

    notable_only=True(Context Reduction 축소 단계 — report 경로에서 섹션이 토큰 상한 초과 시에만
    호출): 다년 예측 창에서 모든 달을 나열하면 토큰이 폭증하므로, 연도 헤더는 유지하되 각 해의
    ★주목 달(연내 top3 + 강한 용신운/기신운)만 남긴다. 단년(12개월)은 원래도 작아 전체 유지한다.
    """
    lc = result.luck_cycles
    if lc is None or not lc.monthly_luck:
        return []
    # months_filter(YYYY-MM 라벨 집합) — 분할 페이지(한해 상·하반기, 테마 연도별 상세,
    # 2026-08-13)가 자기 구간의 달만 받도록 한다. None=전체(기존 동작 불변).
    pool_months = (
        lc.monthly_luck
        if months_filter is None
        else [p for p in lc.monthly_luck if p.label in months_filter]
    )
    if not pool_months:
        return []
    by_period: dict[str, list[EventCandidate]] = {}
    for c in scored:
        if domain is not None and _DOMAIN_BY_KEY.get(str(c.event_key)) != domain:
            continue  # 테마 섹션 — 대표 사건을 주제 도메인으로 한정(운 품질 등급은 항상 표기).
        by_period.setdefault(c.period, []).append(c)
    # 연도별로 묶어 각 해의 12개월을 빠짐없이 출력한다(다년 예측 — ★주목은 연도 내 상대 기준).
    years = sorted({p.label[:4] for p in pool_months})
    multi = len(years) > 1
    lines: list[str] = []
    for yr in years:
        months = [p for p in pool_months if p.label[:4] == yr]
        rep: dict[str, EventCandidate | None] = {}
        month_score: dict[str, int] = {}
        for p in months:
            cs = sorted(by_period.get(p.label, []), key=lambda c: -c.score)
            top = cs[0] if cs else None
            rep[p.label] = top
            month_score[p.label] = top.score if top is not None else 0
        # 주목할 달 Top3 — 그 해 안에서 대표 후보 점수 기준(신호 없는 달은 0점 취급).
        ranked = sorted((p.label for p in months), key=lambda lb: -month_score[lb])
        top3 = {lb for lb in ranked[:3] if rep[lb] is not None}
        # 운 품질이 뚜렷한 달(천간·지지 모두 용신/기신)도 주목 — 사건이 적어도 길흉 변별의 핵심.
        strong_quality = {
            p.label for p in months if p.luck_label in ("강한 용신운", "강한 기신운")
        }
        notable = top3 | strong_quality
        if multi:
            lines.append(f"〈{yr}년〉")
        # 축소 단계 — 다년 창에서 ★주목 달만 남긴다(단년이면 12개월 전체 유지: 원래도 작음).
        shown = [p for p in months if not (notable_only and multi and p.label not in notable)]
        for p in shown:
            cand = rep[p.label]
            tg = f"천간 {p.stem_ten_god or '?'}·지지 {p.branch_ten_god or '?'}"
            grade = f" 〈{p.luck_label}〉" if p.luck_label else ""  # 운 품질 등급 — 길흉 1차 기준
            star = " ★주목" if p.label in notable else ""
            if cand is None:
                lines.append(f"{p.label} {p.ganji}({tg}){grade}: 두드러진 신호 약함{star}")
            else:
                dom = _DOMAIN_KO.get(_DOMAIN_BY_KEY.get(str(cand.event_key), ""), "일반")
                lines.append(
                    f"{p.label} {p.ganji}({tg}){grade}: {dom} {score_band(cand.score)} · "
                    f"{_dir(cand)} · {event_ko(cand.event_key)}{star}"
                )
    return lines


def year_spectrum_lines(
    result: ManseV2Result, scored: list[EventCandidate], years: list[int],
    domain: str | None = None, *, notable_only: bool = False,
) -> list[str]:
    """지정 연도들의 세운을 빠짐없이 한 줄씩 — 연 간지·운 품질 등급·우세 도메인·강도밴드·길흉·★주목.

    '향후 5년 종합' 류 섹션이 상위 몇 건만 반복하지 않고 전 연도를 고르게(좋은·주의·평범 해 모두)
    다루도록 모든 해를 데이터로 제공한다. month_overview_lines의 연(年) 버전 — 좋은 해/주의할 해의
    1차 기준은 사건 밀도가 아니라 세운 운 품질 등급〈…〉(길흉=용신/기신)이다.

    notable_only=True(Context Reduction 2단계): 토큰 상한을 1단계(월별 흐름 축소)로도 못 맞춘
    긴 예측 창에서만, ★주목 해(top3 + 강한 용신운/기신운)로 좁힌다(연 단위라 원래도 작아 후순위).
    """
    lc = result.luck_cycles
    if lc is None or not lc.yearly_luck:
        return []
    by_label = {p.label: p for p in lc.yearly_luck}
    by_period: dict[str, list[EventCandidate]] = {}
    for c in scored:
        if len(c.period) != 4:
            continue
        if domain is not None and _DOMAIN_BY_KEY.get(str(c.event_key)) != domain:
            continue  # 테마 섹션 — 대표 사건을 주제 도메인으로 한정(운 품질 등급은 항상 표기).
        by_period.setdefault(c.period, []).append(c)
    yr_strs = [str(y) for y in years if str(y) in by_label]
    rep: dict[str, EventCandidate | None] = {}
    yscore: dict[str, int] = {}
    for y in yr_strs:
        cs = sorted(by_period.get(y, []), key=lambda c: -c.score)
        rep[y] = cs[0] if cs else None
        yscore[y] = cs[0].score if cs else 0
    ranked = sorted(yr_strs, key=lambda y: -yscore[y])
    top3 = {y for y in ranked[:3] if rep[y] is not None}
    strong = {
        y for y in yr_strs
        if by_label[y].luck_label in ("강한 용신운", "강한 기신운")
    }
    notable = top3 | strong
    lines: list[str] = []
    shown_years = [y for y in yr_strs if not (notable_only and y not in notable)]
    for y in shown_years:
        p = by_label[y]
        tg = f"천간 {p.stem_ten_god or '?'}·지지 {p.branch_ten_god or '?'}"
        grade = f" 〈{p.luck_label}〉" if p.luck_label else ""
        star = " ★주목" if y in notable else ""
        cand = rep[y]
        if cand is None:
            lines.append(f"{y}년 {p.ganji}({tg}){grade}: 두드러진 신호 약함{star}")
        else:
            dom = _DOMAIN_KO.get(_DOMAIN_BY_KEY.get(str(cand.event_key), ""), "일반")
            lines.append(
                f"{y}년 {p.ganji}({tg}){grade}: {dom} {score_band(cand.score)} · "
                f"{_dir(cand)} · {event_ko(cand.event_key)}{star}"
            )
    return lines
