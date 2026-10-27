"""구조 패턴 감지기(Step ②) — 사전 무결성 + 어댑터 감지 + inert 불변식.

설계: doc/v2_2/docs/13_STRUCTURE_PATTERNS.md
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.context_reducer import serialize_chart_prefix
from saju_engines.structure_patterns import (
    _FAILURE_TO_PID,
    _MANSE_DISPLAY_EXCLUDED_IDS,
    _MANSE_DISPLAY_FAMILIES,
    _MAX_LLM_PATTERNS,
    detect_structure_patterns,
    load_structure_patterns,
    select_llm_patterns,
    select_manse_display_patterns,
)
from saju_shared_types.birth_input import BirthInput

# EventKeyV2(21종) — domain_hints 정렬 검증용.
_EVENT_KEYS = {
    "career_change", "job_gain", "promotion", "business_start", "business_expansion",
    "wealth_change", "windfall", "contract_document", "education_admission",
    "education_completion", "relationship_change", "new_relationship", "marriage_signal",
    "childbirth", "relocation", "legal_conflict", "health_attention", "social_conflict",
    "preparation_delay", "creative_output", "public_exposure",
}
_POLARITY_MODES = {"favorable", "unfavorable", "depends_on_yonggi_and_control", "context_only"}
_SCOPES = {"natal", "luck", "natal_luck"}


@pytest.fixture(scope="module")
def result():
    return calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))


# ── 사전 무결성 ─────────────────────────────────────────────────────────

def test_dictionary_loads_and_no_dup() -> None:
    dic = load_structure_patterns()
    ids = [p.pattern_id for p in dic.patterns]
    assert len(ids) == len(set(ids)), "중복 pattern_id"
    assert len(ids) == 156, (
        "P0 35 + F3 25 + F4 7 + 잡기재관격(F5) 1 + 사고수 확장 23(2026-07-23) "
        "+ 용어 감사 F6 63(2026-09-17) + 조토불생금·습토회화 2(2026-10-27)"
    )


def test_dictionary_fields_valid() -> None:
    dic = load_structure_patterns()
    for p in dic.patterns:
        assert p.polarity_mode in _POLARITY_MODES
        assert set(p.domain_hints) <= _EVENT_KEYS, f"{p.pattern_id} domain_hints 미정렬"
        assert len(p.llm_tag) <= 120, f"{p.pattern_id} llm_tag 초과"
        assert p.llm_usage == "explanation_tag_only"


# ── 감지 결과 불변식 ────────────────────────────────────────────────────

def test_detected_patterns_wellformed(result) -> None:
    dic = load_structure_patterns()
    valid_ids = {p.pattern_id for p in dic.patterns}
    detected = detect_structure_patterns(result)
    assert detected, "실제 명식에서 구조 패턴이 하나도 감지되지 않음"
    seen = set()
    for d in detected:
        assert d.pattern_id in valid_ids, f"사전에 없는 pattern_id: {d.pattern_id}"
        assert d.pattern_id not in seen, f"중복 감지: {d.pattern_id}"
        seen.add(d.pattern_id)
        assert 0.0 <= d.strength <= 1.0
        assert d.scope in _SCOPES
        assert d.polarity_mode in _POLARITY_MODES
        assert set(d.domain_hints) <= _EVENT_KEYS
        assert d.favorability is None, "P0: 길흉 미확정(favorability None)"


def test_sorted_by_strength_desc(result) -> None:
    detected = detect_structure_patterns(result)
    strengths = [d.strength for d in detected]
    assert strengths == sorted(strengths, reverse=True)


def test_deterministic(result) -> None:
    a = detect_structure_patterns(result)
    b = detect_structure_patterns(result)
    assert [d.pattern_id for d in a] == [d.pattern_id for d in b]


# ── 어댑터 정합성: 활성 파격 → 대응 pattern_id 감지 ──────────────────────

def test_active_failures_map_to_patterns(result) -> None:
    assert result.geokguk is not None and result.geokguk.evaluation is not None
    detected_ids = {d.pattern_id for d in detect_structure_patterns(result)}
    for f in result.geokguk.evaluation.failures:
        if f.get("active") and f.get("type") in _FAILURE_TO_PID:
            assert _FAILURE_TO_PID[f["type"]] in detected_ids, (
                f"활성 파격 {f['type']} → {_FAILURE_TO_PID[f['type']]} 미감지"
            )


def test_geguk_main_structure_detected(result) -> None:
    """주격이 P0 사전에 있으면 해당 격국 패턴이 감지된다."""
    assert result.geokguk is not None
    detected_ids = {d.pattern_id for d in detect_structure_patterns(result)}
    from saju_engines.structure_patterns import _GEOK_NAME_TO_PID

    pid = _GEOK_NAME_TO_PID.get(result.geokguk.main_structure or "")
    if pid is not None:
        assert pid in detected_ids


# ── Step ④/F1: LLM 입력 배선(질문 가변 suffix, 도메인 필터, 상한, inert) ────

def test_select_llm_patterns_capped_and_ranked(result) -> None:
    detected = detect_structure_patterns(result)
    top = select_llm_patterns(detected)
    assert len(top) <= _MAX_LLM_PATTERNS
    assert [d.pattern_id for d in top] == [d.pattern_id for d in detected[:_MAX_LLM_PATTERNS]]


def test_select_llm_patterns_domain_priority() -> None:
    """domains 지정 시 domain_hints 매칭이 앞으로(soft filter). 미지정은 strength desc."""
    from saju_shared_types.structure_patterns import DetectedPattern

    def mk(pid: str, strength: float, hints: list[str]) -> DetectedPattern:
        return DetectedPattern(
            pattern_id=pid, name_ko=pid, strength=strength,
            polarity_mode="context_only", domain_hints=hints,
        )

    pats = [mk("A", 0.9, ["wealth_change"]), mk("B", 0.8, ["career_change"])]
    # domains=None: strength desc
    assert [d.pattern_id for d in select_llm_patterns(pats)] == ["A", "B"]
    # domains={career_change,...}: B(매칭) 우선 — strength 낮아도 앞으로
    ordered = select_llm_patterns(pats, domains={"career_change", "job_gain"})
    assert ordered[0].pattern_id == "B"


def test_domain_event_keys_include_contract_document() -> None:
    """career 도메인 집합에 contract_document 포함 — taxonomy(CONTRACT_DOCUMENT→career)와 정합.

    누락 시 계약·문서 질문에서 관인상생 등의 contract_document domain_hint가
    절대 매칭되지 않는다(2026-08-10 감사 결함 1).
    """
    from saju_engines.context_reducer import _DOMAIN_EVENT_KEYS

    assert "contract_document" in _DOMAIN_EVENT_KEYS["career"]


def test_pattern_domain_keys_merges_singular_domain() -> None:
    """domains(복수)가 비고 domain(단수)만 채워져도 도메인 우선 선별이 동작한다.

    능동 제안 경로에는 있던 단수 병합 방어가 구조 패턴 경로에 없던 결함
    (2026-08-10 감사 결함 2)의 회귀 가드.
    """
    from saju_engines.context_reducer import _DOMAIN_EVENT_KEYS, _pattern_domain_keys
    from saju_shared_types.intent import Domain, IntentJson, QueryType

    single = IntentJson(
        intent_id="t1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
    )
    assert _pattern_domain_keys(single) == _DOMAIN_EVENT_KEYS["career"]

    both = IntentJson(
        intent_id="t2", query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER, domains=[Domain.WEALTH],
    )
    assert _pattern_domain_keys(both) == (
        _DOMAIN_EVENT_KEYS["career"] | _DOMAIN_EVENT_KEYS["wealth"]
    )

    empty = IntentJson(intent_id="t3", query_type=QueryType.DOMAIN_ANALYSIS)
    assert _pattern_domain_keys(empty) == set()


def test_prefix_no_longer_carries_patterns(result) -> None:
    """구조 패턴은 캐시 프리픽스에서 제거됨(질문 가변 suffix로 이전). 프리픽스는 결정적."""
    from saju_engines.context_reducer import build_birth_summary

    ci = build_chart_interpretation(result)
    assert ci is not None and not hasattr(ci, "detected_patterns")
    summary = build_birth_summary(result)
    a = serialize_chart_prefix(summary, ci)
    assert a == serialize_chart_prefix(summary, ci), "프리픽스는 결정적(캐시)"
    assert not any("구조 패턴" in line for line in a), "구조 패턴은 프리픽스에 없어야 함"


def test_domain_filter_active_in_full_input() -> None:
    """도메인 필터 실동작 — 재물 질문과 직업 질문에서 구조 패턴 노출/순서가 달라진다."""
    from datetime import date

    import saju_api.services.chat_service as chat_service

    birth = BirthInput(
        calendar_type="solar", birth_date="1990-03-15", birth_time="14:30",
        birth_place_name="서울", gender="female", reference_date="2026-06-11",
    )
    today = date(2026, 6, 11)

    def _pattern_block(question: str) -> list[str]:
        res = chat_service.chat(birth, question, today, dry_run=True)
        assert res.prompt_preview is not None
        text = res.prompt_preview
        # 구조 패턴 블록은 [기준 시점] 이후(질문 가변 suffix)에 있어야 한다.
        assert "[기준 시점]" in text
        suffix = text.split("[기준 시점]", 1)[1]
        if "[구조 패턴" not in suffix:
            return []
        after = suffix.split("[구조 패턴", 1)[1]
        return [ln for ln in after.splitlines()[1:] if ln and not ln.startswith("[")]

    career = _pattern_block("올해 이직운 어때?")
    wealth = _pattern_block("올해 재물운은 어떤가요?")
    # 최소 한쪽에 패턴이 노출되고, 도메인에 따라 순서/구성이 달라진다(필터 동작 증거).
    assert career or wealth
    assert career != wealth


# ── F2: 묘고(입묘/충개/개고) 어댑터 감지 ─────────────────────────────────

def test_tomb_patterns_natal_detection(result) -> None:
    """묘고 구조는 natal 신호(입묘 지지/충 지지쌍/병존)로 감지된다(운 activation 별개)."""
    from saju_engines.health_vulnerability import analyze_health_vulnerability
    from saju_engines.wealth_capacity import analyze_wealth_capacity

    detected = {d.pattern_id for d in detect_structure_patterns(result)}
    pillars = result.pillars
    assert pillars is not None
    natal_branches = {
        p.branch for pos in ("year", "month", "day", "hour")
        if (p := getattr(pillars, pos)) is not None
    }
    hv = analyze_health_vulnerability(result)
    tomb_present = (
        hv.day_master_tomb_branch in natal_branches
        or hv.food_god_tomb_branch in natal_branches
    )
    assert ("IPMYO" in detected) == tomb_present
    clash_present = any(
        a in natal_branches and b in natal_branches for a, b in (("辰", "戌"), ("丑", "未"))
    )
    assert ("CHUNGGAE" in detected) == clash_present
    assert ("GAEGO" in detected) == analyze_wealth_capacity(result).storage_repeat


# ── 만세력 화면 노출 선별(2026-10-17) ───────────────────────────────────────


def _display_result(**kw):
    base = dict(birth_date="1985-03-12", birth_time="14:30", birth_place_name="서울", gender="male")
    base.update(kw)
    return calculate(BirthInput(**base))


def test_detected_patterns_carry_hanja(result) -> None:
    # 화면 한글·한자 병기용 — 사전 전 항목에 한자명이 있으므로 감지 결과도 비어 있으면 안 된다.
    detected = detect_structure_patterns(result)
    assert detected
    assert all(d.name_hanja for d in detected)


def test_manse_display_excludes_internal_and_other_sections() -> None:
    # 1985-03-12 14:30 남: 재다신약·토다금매(노출)와 용신 무력·오행 과다·삼형 완성·충동(제외)이
    # 함께 감지되는 명식. (2026-10-17 성립 조건 SSOT 이후 상관생재(상관 10% 미만)·재극인(재 37% <
    # 인 40%)은 미성립.)
    r = _display_result()
    detected = detect_structure_patterns(r)
    ids = {d.pattern_id for d in detected}
    assert {"JAEDA_SINYAK", "TODA_GEUMMAE", "YONGSIN_MURYEOK",
            "ELEMENT_EXCESS_ACTIVE", "THREE_PUNISHMENT_COMPLETE", "CHUNGDONG"} <= ids
    assert "JAE_GEUGIN" not in ids  # 반례: 재가 인보다 약하면 재극인 미성립
    shown = select_manse_display_patterns(detected)
    shown_ids = [d.pattern_id for d in shown]
    assert "JAEDA_SINYAK" in shown_ids and "TODA_GEUMMAE" in shown_ids
    # 내부 신호·삼형·격국/합충 전용 family 는 빠진다.
    assert not (set(shown_ids) & _MANSE_DISPLAY_EXCLUDED_IDS)
    assert "CHUNGDONG" not in shown_ids
    assert all(set(d.family) & _MANSE_DISPLAY_FAMILIES for d in shown)
    # 상한 없음·입력 순서(strength desc) 보존.
    assert [d.strength for d in shown] == sorted((d.strength for d in shown), reverse=True)
    assert len(shown_ids) == len(set(shown_ids))


def test_manse_display_keeps_jaeda_sinyak_when_detected() -> None:
    # 재다신약은 geokguk 파격 어댑터 경로 — overload family 라 노출 대상이어야 한다.
    dic = load_structure_patterns()
    entry = next(e for e in dic.patterns if e.pattern_id == "JAEDA_SINYAK")
    assert set(entry.family) & _MANSE_DISPLAY_FAMILIES
    assert "JAEDA_SINYAK" not in _MANSE_DISPLAY_EXCLUDED_IDS


def test_calculate_exposes_display_patterns() -> None:
    # calculate 응답에 선별본이 실리고, 감지 전체에 대한 선별 결과와 ID 가 일치한다(시간 미상 포함).
    r = _display_result()
    assert r.structure_patterns is not None
    shown = select_manse_display_patterns(detect_structure_patterns(r))
    assert [d.pattern_id for d in r.structure_patterns] == [d.pattern_id for d in shown]
    assert all(d.scope == "natal" for d in r.structure_patterns)


def test_hour_unknown_keeps_only_patterns_agreed_by_all_candidates() -> None:
    # 시주 미상: 3기둥 감지를 확정으로 쓰지 않는다 — 후보 시진 전부에서 성립하는 패턴만 남는다.
    r = _display_result(birth_time=None, birth_time_unknown=True)
    hu = r.hour_unknown
    assert hu is not None and hu.candidates and hu.structure_patterns is not None
    agreed = set.intersection(*(set(c.structure_pattern_ids) for c in hu.candidates))
    union = set.union(*(set(c.structure_pattern_ids) for c in hu.candidates))
    assert agreed < union  # 반례 보장: 이 명식은 후보에 따라 갈리는 패턴이 실제로 있다
    assert hu.structure_patterns.status == "differ"
    assert "structure_patterns" in hu.unconfirmed
    assert hu.structure_patterns.values  # 갈리는 배합 이름
    # LLM 경로(detect)와 화면 경로(structure_patterns) 모두 확정 집합 안에서만 나온다.
    assert {d.pattern_id for d in detect_structure_patterns(r)} <= agreed
    assert r.structure_patterns is not None
    assert {d.pattern_id for d in r.structure_patterns} <= agreed
    # 3기둥만으로 감지하면 나오지만 후보 일부에서 사라지는 패턴은 노출되지 않는다.
    base_ids = {d.pattern_id for d in detect_structure_patterns(r, apply_hour_unknown_policy=False)}
    assert base_ids - agreed, "반례 없음: 3기둥 감지가 전부 후보 일치라면 이 테스트는 무의미"
    assert not ((base_ids - agreed) & {d.pattern_id for d in r.structure_patterns})


# ── P0 원국 세력 보정 2중 판정(2026-10-17) ──────────────────────────────────


def _p0_result(d: str, t: str):
    return calculate(BirthInput(birth_date=d, birth_time=t, birth_place_name="서울", gender="male"))


def _by_id(r, pid):
    return {x.pattern_id: x for x in detect_structure_patterns(r)}.get(pid)


def test_p0_both_criteria_gives_strong_tier() -> None:
    # 1970-07-24 04:30: 표면 재성 43%·보정 세력 43%·신약 → 개수·세력 둘 다 성립.
    d = _by_id(_p0_result("1970-07-24", "04:30"), "JAEDA_SINYAK")
    assert d is not None and d.strength == 0.8
    assert "뚜렷한 성립" in d.basis_note
    assert "표면 " in d.basis_note and "보정 세력 " in d.basis_note
    assert d.basis_note in d.llm_line


def test_p0_effective_only_emits_weak_tier() -> None:
    # 1970-07-24 13:30: 표면 재성 29%(개수 기준 미달)·보정 세력 31.8%·태신약
    # → 세력 기준만 성립 → 신규 발동 0.5.
    r = _p0_result("1970-07-24", "13:30")
    d = _by_id(r, "JAEDA_SINYAK")
    assert d is not None and d.strength == 0.5 and "보정 세력만" in d.basis_note


def test_p0_count_only_downgrades_to_weak_tier() -> None:
    # 1971-05-26 04:30: 표면 식상 43%(개수 성립)·보정 세력 31.2%(<35) → 개수 기준만 → 0.5.
    d = _by_id(_p0_result("1971-05-26", "04:30"), "SEOLGI_TAEGWA")
    assert d is not None and d.strength == 0.5 and "표면 개수만" in d.basis_note


def test_p0_neither_criteria_no_pattern() -> None:
    # 1970-01-01 04:30: 재성 표면 14%·보정 7.9% → 재다신약 없음, 근거 줄도 없음.
    r = _p0_result("1970-01-01", "04:30")
    assert _by_id(r, "JAEDA_SINYAK") is None


def test_p0_skipped_when_hour_unknown() -> None:
    # 시주 미상: 세력 비율 판정 자체를 하지 않는다 — 어떤 패턴에도 basis_note 가 없다.
    r = calculate(BirthInput(birth_date="1970-07-24", birth_time=None, birth_time_unknown=True,
                             birth_place_name="서울", gender="male"))
    detected = detect_structure_patterns(r, apply_hour_unknown_policy=False)
    assert all(not d.basis_note for d in detected)


def test_p0_basis_note_only_on_six_overload_patterns() -> None:
    r = _p0_result("1970-07-24", "04:30")
    six = {"JAEDA_SINYAK", "GWANDA_SINYAK", "INDA_SINYAK", "SEOLGI_TAEGWA",
           "GUNGEOP_JAENGJAE", "BIGEOP_TALJAE"}
    assert all((d.pattern_id in six) or not d.basis_note for d in detect_structure_patterns(r))
