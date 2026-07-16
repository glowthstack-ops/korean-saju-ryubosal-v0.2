"""외적 인상·매력 신호 판정·노출 단위 테스트 (v1, 2026-07-01).

SSOT: doc/v2_2/EXTERNAL_IMPRESSION_SIGNAL.md §6.1(최소 6개 케이스). '미인 판정'이 아니라 인상·
표현매력·관계적 끌림 보조 신호이며, 가중 스코어 + intent allowlist로 노출을 게이트한다. 원국 조건을
결정론적으로 만들기 위해 SimpleNamespace 스텁 result를 쓴다(기존 marriage_resource 테스트와 동일
관행). 실 chart 조회 경로(analyze_external_impression 필드 접근)와 동일한 속성만 사용한다.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from saju_engines.external_impression import analyze_external_impression
from saju_engines.structural_context import external_impression_lines
from saju_shared_types.intent import Domain, IntentJson, QueryType
from saju_shared_types.manse_result import ManseV2Result

# SSOT §4 금지어(생성 지시문에 문자열로 등장하면 실패 처리).
_BANNED = (
    "미인", "예쁘", "잘생", "못생", "방정맞", "섹시", "성적 매력",
    "남자에게 잘", "여자에게 잘",
)


def _pil(stem: str, branch: str, stem_tg: str = "", branch_tg: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        stem=stem, branch=branch, stem_ten_god=stem_tg, branch_main_ten_god=branch_tg
    )


def _result(
    year: SimpleNamespace, month: SimpleNamespace, day: SimpleNamespace, hour: SimpleNamespace,
    *, groups: dict | None = None, elem_env: dict | None = None,
    elem_sa: dict | None = None, strongest: str = "土", deficient: list | None = None,
    gender: str = "female",
) -> ManseV2Result:
    return cast("ManseV2Result", SimpleNamespace(
        input_summary={"gender": gender},
        pillars=SimpleNamespace(year=year, month=month, day=day, hour=hour),
        force_analysis=SimpleNamespace(
            ten_gods=SimpleNamespace(groups=groups or {}),
            five_elements=SimpleNamespace(
                distribution_environment=elem_env or {},
                season_adjusted_element_strength=elem_sa or {},
                strongest_element=strongest,
                deficient_elements=deficient or [],
            ),
        ),
    ))


def _intent(domain: Domain = Domain.RELATIONSHIP,
            qt: QueryType = QueryType.DOMAIN_ANALYSIS) -> IntentJson:
    return IntentJson(intent_id="x", query_type=qt, domain=domain)


def _codes(profile) -> dict:
    return {s.code: s for s in profile.signals}


# ── Case 1: 금수상관 + 관성 있음 → METAL_WATER_OFFICER primary 1.0 ──
def _metal_water_officer_result(gender: str = "female") -> ManseV2Result:
    # 庚(金) 일간 + 壬(水) 투간 + 월간 정관. 지지 未巳辰丑(도화·홍염·역마 아님).
    return _result(
        _pil("壬", "未", "상관", "정인"),
        _pil("丁", "巳", "정관", "편관"),
        _pil("庚", "辰", "일간", "편인"),
        _pil("己", "丑", "정인", "정인"),
        groups={"output": 5.0, "officer": 20.0},
        gender=gender,
    )


def test_case1_metal_water_with_officer() -> None:
    prof = analyze_external_impression(_metal_water_officer_result())
    sig = _codes(prof)
    assert "METAL_WATER_OFFICER" in sig
    assert sig["METAL_WATER_OFFICER"].weight == 1.0
    assert sig["METAL_WATER_OFFICER"].tier == "primary"
    assert "METAL_WATER_EXPRESSION" not in sig  # 배타 배점(이중 계상 금지)
    # 단일 카테고리(metal_water) → notable 미달(약신호), 단독 노출 안 됨.
    assert prof.is_notable is False
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) == []


# ── Case 2: 금수상관 + 관성 없음 → METAL_WATER_EXPRESSION secondary 0.5, 단독 노출 금지 ──
def test_case2_metal_water_without_officer() -> None:
    r = _result(
        _pil("壬", "未", "상관", "정인"),
        _pil("丁", "巳", "식신", "상관"),   # 관성 없음
        _pil("庚", "辰", "일간", "편인"),
        _pil("己", "丑", "정인", "정인"),
        groups={"output": 5.0, "officer": 0.0},
    )
    prof = analyze_external_impression(r)
    sig = _codes(prof)
    assert "METAL_WATER_EXPRESSION" in sig
    assert sig["METAL_WATER_EXPRESSION"].weight == 0.5
    assert sig["METAL_WATER_EXPRESSION"].tier == "secondary"
    assert "METAL_WATER_OFFICER" not in sig
    assert prof.band == "none" and prof.is_notable is False
    # 관계 질문이어도 단독 약신호는 표면화하지 않는다.
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) == []


# ── Case 3: 일지 도화 + 식상 적정(18~35%) → notable 노출 ──
def _day_peach_output_result(gender: str = "female") -> ManseV2Result:
    # 丙午 일주(일지 午=도화) + 식상 25%. 홍염(丙→寅) 미존재, 실제 도화 target 미존재.
    return _result(
        _pil("甲", "申", "편인", "편재"),
        _pil("乙", "未", "정인", "정인"),
        _pil("丙", "午", "일간", "겁재"),
        _pil("戊", "辰", "식신", "식신"),
        groups={"output": 25.0, "officer": 5.0},
        elem_env={"火": 10.0}, strongest="土",
        gender=gender,
    )


def test_case3_day_peach_plus_output_notable() -> None:
    prof = analyze_external_impression(_day_peach_output_result())
    sig = _codes(prof)
    assert "DAY_BRANCH_PEACH" in sig and sig["DAY_BRANCH_PEACH"].weight == 1.2
    assert "OUTPUT_EXPRESSION" in sig and sig["OUTPUT_EXPRESSION"].tier == "primary"
    assert "ACTUAL_DOHWA_OR_HONGYEOM" not in sig  # 실제 도화·홍염 아님(단순 일지 왕지)
    assert prof.category_count >= 2 and prof.primary_signal_count >= 2
    assert prof.band == "notable" and prof.is_notable is True
    lines = external_impression_lines(prof, _intent(Domain.RELATIONSHIP))
    assert lines and any("끌림" in ln or "표현" in ln for ln in lines)


# ── Case 4: 단순 子午卯酉만 존재(일지 아님) → 0.3, 단독 notable 금지 ──
def test_case4_non_day_peach_only() -> None:
    # 일지 辰(도화 아님) + 연지 卯(왕지, 일지 외). 실제 도화 target·홍염 미존재.
    r = _result(
        _pil("甲", "卯", "비견", "비견"),
        _pil("丁", "未", "상관", "편인"),
        _pil("乙", "辰", "일간", "정재"),   # 乙 홍염=午(미존재)
        _pil("己", "丑", "편재", "편재"),
        groups={"output": 5.0},
    )
    prof = analyze_external_impression(r)
    sig = _codes(prof)
    assert "NON_DAY_PEACH_BRANCH" in sig and sig["NON_DAY_PEACH_BRANCH"].weight == 0.3
    assert "DAY_BRANCH_PEACH" not in sig and "ACTUAL_DOHWA_OR_HONGYEOM" not in sig
    assert prof.is_notable is False
    # 단순 왕지 존재만으로는 어떤 intent에서도 노출되지 않는다.
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) == []


# ── Case 5: notable이지만 career intent → suppress(무언급) ──
def test_case5_notable_but_career_suppressed() -> None:
    prof = analyze_external_impression(_day_peach_output_result())
    assert prof.is_notable is True
    # 커리어 질문엔 매력 신호를 노출하지 않는다.
    assert external_impression_lines(prof, _intent(Domain.CAREER), "이직운 봐줘") == []
    # 관계 질문엔 노출된다(대조).
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) != []


# ── Case 6: 외모 직접 질문 → allowlist 예외로 suppress 도메인에서도 노출 ──
def test_case6_direct_appearance_question_exception() -> None:
    prof = analyze_external_impression(_day_peach_output_result())
    # career 도메인이라도 '외모' 직접 질문이면 노출.
    lines = external_impression_lines(prof, _intent(Domain.CAREER), "제 외모는 어떤가요?")
    assert lines


# ── 금지어 가드: 생성 지시문에 용모 우열·성적·성별 고정 어휘가 없어야 한다 ──
def test_no_banned_words_in_directive() -> None:
    prof = analyze_external_impression(_day_peach_output_result())
    text = " ".join(external_impression_lines(prof, _intent(Domain.RELATIONSHIP)))
    assert text
    for banned in _BANNED:
        assert banned not in text, f"금지어 '{banned}' 노출"


# ── 성별 미상(confidence=low): notable이라도 직접질문·strong일 때만 노출 ──
def test_gender_unknown_gated() -> None:
    prof = analyze_external_impression(_day_peach_output_result(gender="unknown"))
    assert prof.confidence == "low"
    # notable이지만 미상 → 일반 관계 질문에선 무언급.
    if prof.band == "notable":
        assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) == []
    # 직접 질문이면 노출.
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP), "외모 봐줘")


# ── 결측(pillars None) graceful ──
def test_missing_pillars_graceful() -> None:
    r = cast("ManseV2Result", SimpleNamespace(
        input_summary={"gender": "female"}, pillars=None, force_analysis=None))
    prof = analyze_external_impression(r)
    assert prof.band == "none" and prof.signals == []
    assert external_impression_lines(prof, _intent(Domain.RELATIONSHIP)) == []
