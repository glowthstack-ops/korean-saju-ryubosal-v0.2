"""반사실(counterfactual) 컨텍스트 resolver — 서술 전용 inert 레이어 (2026-07-21 데굴님 확정).

"왜 늦게 결혼할 운이야 / 2021년에 이직했으면 어땠을까" 류 질문에서, 그때 실행됐다면
함께 활성화됐을 부담·지원·회복 신호를 **기존 계산값만 재배치**해 산출한다(도메인 범용).

fail-closed 원칙(GPT 검토안·사용자 승인):
- 기간·대상 미확정 → INSUFFICIENT: 과거 전체에서 불리한 해만 골라 '안 하길 잘했다'
  서사를 만들지 못하게 제한 지시만 내보낸다(체리피킹 차단).
- 부담 성립 = 도메인 구조 신호(원국) AND 기간 내 활성화(운 충·형·공망 발동) 동시 필요 —
  '기신운이었다'만으로 유지 실패를 연결하지 않는다.
- 보호 해석(ELIGIBLE_PROTECTIVE)은 기간 이후 완화·회복이 데이터로 확인될 때만 연다.
- health 도메인·대상 불명 질문은 NOT_APPLICABLE(정서 가드).

읽기만 하는 기존 신호: result.structure_analysis.interactions(궁위 라벨 내장),
세운 LuckPillar(relations_to_chart·luck_label_code·gongmang_activation — 대운 sewoon이
생애 전체 커버), LifeEventRow(실제 시도·확정 기간). 신규 명리 계산 금지(절대원칙 1·9).
"""

from __future__ import annotations

import re
from datetime import date

from saju_shared_types.constants import BRANCH_ELEMENT, CONTROLS, STEM_ELEMENT
from saju_shared_types.counterfactual import (
    CounterfactualContext,
    CounterfactualMode,
    CounterfactualSignal,
    EventStage,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, EVENT_KO
from saju_shared_types.intent import Domain, IntentJson
from saju_shared_types.life_event import LifeEventRow
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

# ── 모드 감지(rules-first 후보 → intent 슬롯으로 최종 확정) ──────────────────
# 과거 가정형: 종성 ㅆ 음절('했/갔/왔/됐/였…', '있'·'겠' 제외) + 다면/더라면/으면.
_HYP_TAILS = ("다면", "더라면", "으면")
# 결과 질의 표지 — "…했으면 어땠을까/괜찮았을까/이혼했겠지".
_OUTCOME_RE = re.compile(r"어땠|어떻게\s*됐|나았|좋았|괜찮|어찌\s*됐|겠지|었을까|았을까|였을까")
# 지나간 결과의 원인(과거형): "왜 취업이 안 됐지 / 왜 계약이 늦었지".
_RETRO_CAUSAL_RE = re.compile(
    r"왜.{0,12}(안\s*됐|못\s*했|늦었|실패했|떨어졌|안\s*풀렸|틀어졌|엎어졌)"
)
# 현재 미발생 상태: "왜 나는 결혼이 늦어 / 아직도 안 돼" — 과거 반사실 자동 생성 금지 모드.
_CURRENT_NON_RE = re.compile(
    r"왜.{0,12}(늦|안\s*(?:되|돼|풀리)|못\s*(?:하|해)|않)|(?:아직|여태).{0,8}(?:안|못)"
)

# ── 도메인 근거 테이블 ──────────────────────────────────────────────────────
# 원국 구조 신호: 궁위 라벨(structure_analysis._PALACE 산출값) 또는 관련 십성 매칭.
_DOMAIN_PALACES: dict[str, set[str]] = {
    "relationship": {"배우자궁"},
    "career": {"직업·환경궁"},
    "education": {"직업·환경궁"},
    "relocation": {"직업·환경궁", "배우자궁"},
    "wealth": set(),  # 재물은 궁위 대신 재성 십성·재성 지지 기준
}
_DOMAIN_GODS: dict[str, set[str]] = {
    "wealth": {"정재", "편재"},
    "career": {"정관", "편관"},
    "relationship": set(),
    "education": set(),
    "relocation": set(),
}
# 부담성 원국 관계(StructuralInteraction.relation_type) → 사건 단계.
_DISRUPTIVE_STAGE: dict[str, EventStage] = {
    "clash": "stabilization",  # 충 — 변동·조율
    "punishment": "maintenance",  # 형 — 조정·소모
    "self_punishment": "maintenance",
    "break": "maintenance",  # 파
    "harm": "maintenance",  # 해
}
_RELATION_KO = {
    "clash": "충", "punishment": "형", "self_punishment": "자형", "break": "파", "harm": "해",
}
_STAGE_KO: dict[str, str] = {
    "initiation": "시작·성사", "stabilization": "적응·조율", "maintenance": "유지·관리",
    "fruition": "결실·실체화", "recovery": "회복",
}
# 궁위 라벨 → 원국 기둥 코드(기간 활성화 대조용) — structure_analysis._PALACE 역방향.
_PALACE_POS = {
    "뿌리·가족궁": "year", "직업·환경궁": "month", "배우자궁": "day", "자녀·결과궁": "hour",
}

# EventKeyV2 enum 키를 str 키로 변환(외부 EventKey와 문자열 값으로 대조 — 타입 경계).
_EVENT_DOMAIN_BY_STR = {str(k): v for k, v in EVENT_DOMAIN.items()}
_EVENT_KO_BY_STR = {str(k): v for k, v in EVENT_KO.items()}

_GISIN_CODES = {"pure_gisin_luck", "partial_gisin", "mixed_gisin_surface"}
_YONGSIN_CODES = {"pure_yongsin_luck", "partial_yongsin", "mixed_yongsin_surface"}
_MAX_PERIOD_YEARS = 6  # 반사실 기간 상한(과대 창 방지)
_AFTER_WINDOW_MIN = 2  # 회복 판정에 필요한 기간 이후 최소 연수


def _has_past_hypothetical(question: str) -> bool:
    """종성 ㅆ 과거 축약('했/됐/갔…', '있'·'겠' 제외) 뒤에 가정 어미가 오면 과거 가정형."""
    for i, ch in enumerate(question):
        if ch in "있겠":
            continue
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172 and code % 28 == 20:  # 종성 ㅆ
            if question[i + 1 : i + 4].startswith(_HYP_TAILS):
                return True
    return False


def detect_counterfactual_mode(question: str) -> CounterfactualMode:
    """질문 문구에서 반사실 모드 후보를 감지한다(도메인·기간 확정은 별도 단계).

    우선순위: 명시 가정형 > 과거 결과 원인(implicit 포함) > 현재 미발생. 미래 가정
    ('한다면/간다면')은 종성 ㅆ 조건에 걸리지 않아 자동 배제된다(기존 conditional 유지).
    """
    if _has_past_hypothetical(question) and _OUTCOME_RE.search(question):
        return "counterfactual_explicit"
    m = _RETRO_CAUSAL_RE.search(question)
    if m:
        return "counterfactual_implicit" if "늦었" in m.group(0) else "retrospective_causal"
    if _CURRENT_NON_RE.search(question):
        return "current_non_occurrence"
    return ""


def _resolve_domain(intent: IntentJson) -> str:
    """intent 도메인/이벤트 키 → 반사실 대상 도메인('' = 불명, health = 제외)."""
    if intent.event_key is not None:
        dom = _EVENT_DOMAIN_BY_STR.get(str(intent.event_key), "")
        if dom:
            return "" if dom == "health" else dom
    if intent.domain in (Domain.GENERAL, Domain.HEALTH):
        return ""
    return str(intent.domain)


def _resolve_period(
    intent: IntentJson,
    today: date,
    prior_time_scope: str | None,
    life_events: list[LifeEventRow] | None,
    domain: str,
) -> tuple[str, str, str]:
    """반사실 기간 확정 — 우선순위: 질문 명시 > 직전 대화 확정 > 실제 시도 기록.

    Returns:
        (from_year, to_year, source) — 미확정이면 ("", "", "")(과거 체리피킹 금지).
    """
    tr = intent.time_range
    if tr is not None and tr.start and not tr.end_offset_days:
        end = tr.end or tr.start
        end_y, start_y = end[:4], tr.start[:4]
        cur_month = f"{today.year}-{today.month:02d}"
        all_past = end_y.isdigit() and (
            int(end_y) < today.year
            or (int(end_y) == today.year and len(end) >= 7 and end[:7] < cur_month)
        )
        if all_past:
            return (start_y, end_y, "user_stated")
    scope_y = (prior_time_scope or "")[:4]
    if scope_y.isdigit() and int(scope_y) < today.year:
        return (scope_y, scope_y, "thread_inherited")
    if life_events:
        past = sorted(
            r.period[:4]
            for r in life_events
            if r.outcome in ("confirmed", "planned")
            and _EVENT_DOMAIN_BY_STR.get(r.event_key, "") == domain
            and r.period[:4].isdigit() and int(r.period[:4]) < today.year
        )
        if past:
            return (past[-1], past[-1], "life_event")
    return ("", "", "")


def _natal_burden_signals(result: ManseV2Result, domain: str) -> list[CounterfactualSignal]:
    """도메인 관련 원국 구조 부담 신호 — StructuralInteraction(궁위 라벨 내장)만 조회."""
    sa = result.structure_analysis
    if sa is None:
        return []
    palaces = _DOMAIN_PALACES.get(domain, set())
    gods = _DOMAIN_GODS.get(domain, set())
    out: list[CounterfactualSignal] = []
    for rel in [*sa.interactions, *getattr(sa, "amplifiers", [])]:
        stage = _DISRUPTIVE_STAGE.get(rel.relation_type)
        if stage is None:
            continue
        hit_palaces = [p for p in rel.palaces if p in palaces]
        hit_gods = [g for g in rel.affected_ten_gods if g in gods]
        if not hit_palaces and not hit_gods:
            continue
        where = "·".join(hit_palaces) or ("관련 십성 " + "·".join(hit_gods))
        out.append(CounterfactualSignal(
            signal_id=f"NATAL_{rel.relation_type.upper()}_{'.'.join(rel.positions)}",
            stage=stage, scope="natal",
            detail=f"{_RELATION_KO.get(rel.relation_type, rel.relation_type)}"
                   f"({'·'.join(rel.members)}) — {where}",
            confidence="high" if rel.severity == "high" else "medium",
        ))
    return out


def _year_pillar_map(result: ManseV2Result) -> dict[str, LuckPillar]:
    """연도 라벨 → 세운 LuckPillar. 대운 sewoon(생애 전체)을 깔고 기본 창(yearly_luck) 우선."""
    lc = result.luck_cycles
    if lc is None:
        return {}
    out: dict[str, LuckPillar] = {}
    for d in lc.daewoon_table:
        for pl in d.sewoon:
            out.setdefault(pl.label, pl)
    for pl in lc.yearly_luck:
        out[pl.label] = pl
    return out


def _domain_branches(result: ManseV2Result, domain: str) -> set[str]:
    """기간 활성화 대조용 원국 지지 집합 — 도메인 궁위 지지(+재물은 재성 오행 지지)."""
    p = result.pillars
    if p is None:
        return set()
    out = {
        getattr(p, pos).branch
        for label, pos in _PALACE_POS.items()
        if label in _DOMAIN_PALACES.get(domain, set()) and getattr(p, pos, None) is not None
    }
    if domain == "wealth":
        wealth_el = CONTROLS[STEM_ELEMENT[Stem(p.day.stem)]]
        out |= {
            pil.branch
            for pil in (p.year, p.month, p.day, p.hour)
            if pil is not None and BRANCH_ELEMENT[Branch(pil.branch)] is wealth_el
        }
    return out


def _period_signals(
    years: list[str], pillar_map: dict[str, LuckPillar], targets: set[str],
) -> tuple[list[CounterfactualSignal], list[CounterfactualSignal], int, int]:
    """기간 세운의 활성 부담·지원 신호 + (활성충 건수, 용신운 연수) 집계."""
    burdens: list[CounterfactualSignal] = []
    supports: list[CounterfactualSignal] = []
    clash_hits = 0
    support_years = 0
    seen_rel: set[str] = set()  # 같은 글자쌍 충이 복수 궁위에 걸려도 라인 1회(중복 서술 방지)
    for y in years:
        pl = pillar_map.get(y)
        if pl is None:
            continue
        for rel in pl.relations_to_chart:
            head, _, pair = rel.partition(":")
            if head not in ("충", "무례지형", "자형"):
                continue
            parts = pair.split("-")
            partner = parts[1] if len(parts) == 2 and parts[0] == pl.branch else parts[0]
            if partner in targets:
                clash_hits += 1
                key = f"{y}:{head}:{pair}"
                if key in seen_rel:
                    continue
                seen_rel.add(key)
                burdens.append(CounterfactualSignal(
                    signal_id=f"YEAR_{head}_ACTIVATED_{y}", stage="stabilization",
                    scope="period", period=y, confidence="high",
                    detail=f"{y} {pl.ganji} — 운 {head}({pair})이 대상 궁위·글자를 직접 자극",
                ))
        for g in pl.gongmang_activation:
            if g.startswith(("공망발동", "공망전실")):
                burdens.append(CounterfactualSignal(
                    signal_id=f"YEAR_VOID_{y}", stage="fruition", scope="period",
                    period=y, confidence="medium",
                    detail=f"{y} {pl.ganji} — {g}(실체화·지속 활용의 불안정)",
                ))
        if pl.luck_label_code in _GISIN_CODES:
            burdens.append(CounterfactualSignal(
                signal_id=f"YEAR_PRESSURE_{y}", stage="maintenance", scope="period",
                period=y, confidence="low",
                detail=f"{y} {pl.ganji} — {pl.luck_label}(전반 부담 배경, 단독 근거 금지)",
            ))
        elif pl.luck_label_code in _YONGSIN_CODES:
            support_years += 1
            supports.append(CounterfactualSignal(
                signal_id=f"SUPPORT_YEAR_{y}", stage="initiation", scope="period",
                period=y, confidence="medium",
                detail=f"{y} {pl.ganji} — {pl.luck_label}(같은 기간의 지원·완충 신호)",
            ))
    return burdens, supports, clash_hits, support_years


def _recovery_signals(
    period_to: str, today: date, pillar_map: dict[str, LuckPillar], targets: set[str],
    period_clash: int, period_years: int, period_support: int,
) -> list[CounterfactualSignal]:
    """기간 이후~현재 창의 완화·회복 — 활성충 빈도 감소 AND 지원 비율 증가일 때만."""
    after_years = [str(y) for y in range(int(period_to) + 1, today.year + 1)]
    if len(after_years) < _AFTER_WINDOW_MIN:
        return []
    _, after_supports, after_clash, after_support_n = _period_signals(
        after_years, pillar_map, targets,
    )
    n_after, n_period = len(after_years), max(period_years, 1)
    eased = (after_clash / n_after) < (period_clash / n_period)
    supported = (after_support_n / n_after) > (period_support / n_period)
    if not (eased and supported):
        return []
    return [CounterfactualSignal(
        signal_id="RECOVERY_PRESSURE_EASED", stage="recovery", scope="after",
        period=f"{after_years[0]}~{after_years[-1]}", confidence="medium",
        detail=(
            f"{after_years[0]}~{after_years[-1]} — 같은 자극 신호의 빈도가 낮아지고 "
            "지원(용신) 연도 비율이 높아짐(엔진 비교값)"
        ),
    )]


def build_counterfactual_context(
    question: str,
    intent: IntentJson,
    result: ManseV2Result,
    today: date,
    *,
    prior_time_scope: str | None = None,
    life_events: list[LifeEventRow] | None = None,
) -> CounterfactualContext:
    """반사실 컨텍스트 산출 — fail-closed 상태 기계(점수·판정 불변).

    상태 규칙: 모드 미감지/도메인 불명/health → NOT_APPLICABLE. 현재 미발생 모드 또는
    기간 미확정 → INSUFFICIENT(정적 구조까지만·체리피킹 금지). 기간 확정 시 '구조 신호
    AND 기간 활성화' 동시 성립해야 ELIGIBLE — 아니면 BLOCKED(반사실 단정 금지). 회복
    비교가 확인될 때만 ELIGIBLE_PROTECTIVE.
    """
    mode = detect_counterfactual_mode(question)
    if not mode:
        return CounterfactualContext()
    domain = _resolve_domain(intent)
    if not domain:
        return CounterfactualContext(mode=mode)
    target = _EVENT_KO_BY_STR.get(str(intent.event_key), "") if intent.event_key else ""
    natal = _natal_burden_signals(result, domain)

    if mode == "current_non_occurrence":
        return CounterfactualContext(
            status="INSUFFICIENT", mode=mode, domain=domain, target=target,
            burden_signals=natal, allowed_claim_level="structure_only",
        )
    period_from, period_to, source = _resolve_period(
        intent, today, prior_time_scope, life_events, domain,
    )
    if not period_from:
        return CounterfactualContext(
            status="INSUFFICIENT", mode=mode, domain=domain, target=target,
            burden_signals=natal, allowed_claim_level="structure_only",
        )
    years = [str(y) for y in range(int(period_from), int(period_to) + 1)][-_MAX_PERIOD_YEARS:]
    pillar_map = _year_pillar_map(result)
    targets = _domain_branches(result, domain)
    period_burdens, supports, clash_hits, support_years = _period_signals(
        years, pillar_map, targets,
    )
    activated = clash_hits > 0 or any(s.signal_id.startswith("YEAR_VOID") for s in period_burdens)
    if not (natal and activated):
        # 구조 신호와 시기 활성화가 함께 성립하지 않으면 반사실 단정 근거가 없다.
        return CounterfactualContext(
            status="BLOCKED", mode=mode, domain=domain, target=target,
            period_from=period_from, period_to=period_to, period_source=source,
            burden_signals=natal, allowed_claim_level="none",
        )
    recovery = _recovery_signals(
        period_to, today, pillar_map, targets, clash_hits, len(years), support_years,
    )
    return CounterfactualContext(
        status="ELIGIBLE_PROTECTIVE" if recovery else "ELIGIBLE_BURDEN_ONLY",
        mode=mode, domain=domain, target=target,
        period_from=period_from, period_to=period_to, period_source=source,
        burden_signals=[*natal, *period_burdens],
        support_signals=supports,
        recovery_signals=recovery,
        allowed_claim_level="burden_plus_recovery" if recovery else "burden_only",
    )


# ── LLM 라인 렌더(서술 전용 — 금지 가드 내장) ───────────────────────────────

_FORBIDDEN_LINE = (
    "금지: ①이혼·파산·해고·질병 등 구체 파국 사건 생성 ②'그때 했다면 반드시 실패'류 확정 "
    "③미발생 사건의 과거형 서술 ④'운이 막아서 못 했다'·'늦어진 덕분에 피했다' 자동 결론 "
    "⑤사용자가 망설였다·검토가 부족했다 등 행동 추정 ⑥과거 선택을 잘못으로 평가."
)


def counterfactual_lines(ctx: CounterfactualContext) -> list[str]:
    """[반사실 맥락] — 상태별 서술 재료+제한 규칙(무해당이면 빈 목록, fail-closed)."""
    if ctx.status == "NOT_APPLICABLE" or not ctx.mode:
        return []
    if ctx.status == "INSUFFICIENT":
        out = [
            "[반사실 서술 한계 — 필수 준수] 이 질문은 '했다면/왜 안 됐나' 결이지만 대상 시기가 "
            "확정되지 않았다. 과거 전체에서 불리한 해만 골라 '안 하길 잘했다'는 보호 서사를 "
            "만들지 말 것 — 특정 시기에 했으면 더 어려웠다고 단정할 근거는 제공되지 않았다.",
        ]
        if ctx.burden_signals:
            structural = " / ".join(
                f"{s.detail}(부담 단계: {_STAGE_KO[s.stage]})" for s in ctx.burden_signals[:4]
            )
            out.append(f"허용 범위: 아래 원국 구조 경향(시기 효과 아님)까지만 — {structural}")
        out.append(_FORBIDDEN_LINE)
        return out
    if ctx.status == "BLOCKED":
        return [
            f"[반사실 서술 한계 — 필수 준수] {ctx.period_from}~{ctx.period_to} 기간에 대해 "
            "질문 대상과 맞물린 부담 활성화 근거가 제공되지 않았다 — '그때 했으면 어려웠다/"
            "나았다' 양쪽 모두 단정하지 말고, 일반 회고 수준으로만 답할 것. " + _FORBIDDEN_LINE,
        ]
    header = (
        f"[반사실 맥락 — 서술 전용(점수·판정 불변) · 대상 {ctx.target or ctx.domain} · "
        f"기간 {ctx.period_from}~{ctx.period_to}] 아래는 '그 시기에 실행됐다면 함께 "
        "활성화됐을' 엔진 신호다. '부담이 더 컸을 가능성'까지만 말하고 실패 단정 금지. "
        "신호의 단계(시작/조율/유지/결실)에 맞춰 서술할 것 — 모든 신호를 '유지 어려움'으로 "
        "뭉뚱그리지 말 것."
    )
    out = [header]
    for s in ctx.burden_signals:
        out.append(f"부담({_STAGE_KO[s.stage]}): {s.detail}")
    for s in ctx.support_signals:
        out.append(f"지원: {s.detail} — 부담과 함께 양면으로 반영할 것(불리 단독 서술 금지)")
    if ctx.status == "ELIGIBLE_PROTECTIVE":
        for s in ctx.recovery_signals:
            out.append(f"이후 완화: {s.detail}")
        out.append(
            "보호 해석 허용(제한): 위 '이후 완화'가 확인되므로 '시간을 둔 것이 결과적으로 "
            "부담을 줄이는 방향과 겹쳤다' 수준까지 허용 — 운명적 보호로 신성화하거나 "
            "'덕분에 위험을 피했다'로 단정하지 말 것."
        )
    else:
        out.append(
            "보호 해석 금지: 이후 완화·개선 근거가 제공되지 않았다 — '늦어진 것이 다행/"
            "보호였다'·'지금이 그때보다 낫다'는 결론을 만들지 말 것(부담 설명까지만)."
        )
    out.append(_FORBIDDEN_LINE)
    return out
