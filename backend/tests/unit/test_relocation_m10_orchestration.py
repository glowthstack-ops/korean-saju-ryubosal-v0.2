"""M10 그룹 리졸버 오케스트레이션 — 채팅(다인 택일) + 리포트(방위·월별 흐름) 연결.

본인+첨부 상대 2인 이사 택일은 M10 그룹 집계(함께 무난한 날)로, 이사 테마 리포트는
방위 적합(RL-04)·월별 이동운 흐름(RL-06)을 surface한다. 점수는 코드가 계산(절대원칙 1).
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_api.services.report_service import _DICTS, plan_report
from saju_engines.precompute import CompositeBuilder
from saju_engines.query_parser import parse_message
from saju_engines.relocation import RelocationResolver
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportSpec

_SELF = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male",
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date=date(1992, 7, 20), birth_time="14:00",
    birth_place_name="서울", gender="female",
)


# ── 채팅: 다인 그룹 택일 ──────────────────────────────────────────


def test_relocation_intent_gate() -> None:
    """이사 도메인/이벤트 질문만 그룹 M10으로 분기한다."""
    reloc = parse_message(
        "배우자랑 같이 이사 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    other = parse_message(
        "올해 재물운 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    assert chat_service._is_relocation_intent(reloc) is True
    assert chat_service._is_relocation_intent(other) is False


def test_group_block_aggregates_two_subjects() -> None:
    """본인+상대 이사 택일 → 그룹 집계 블록(랭킹·방위·그룹 라벨)."""
    intent = parse_message(
        "배우자랑 같이 이사 좋은 날 언제야?", date(2026, 6, 11), birth_year=1990
    ).intents[0]
    block = chat_service._relocation_group_block(
        _SELF, _PARTNER, intent, date(2026, 6, 11), "본인", "배우자",
    )
    assert block is not None
    assert "그룹" in block.purpose_ko and "본인" in block.purpose_ko
    assert block.rows  # 함께 무난한 이사일 랭킹
    assert all(0 <= r.score <= 100 for r in block.rows)
    assert block.directions  # 방위 적합 동반


def test_group_block_falls_back_when_not_relocation() -> None:
    """이사가 아닌 질문은 그룹 경로를 타지 않는다(게이트)."""
    intent = parse_message("재물운 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    assert chat_service._is_relocation_intent(intent) is False


# ── 리포트: 방위·월별 흐름 surface ───────────────────────────────


def _reloc_spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS", topic="relocation",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period={"start": "2026", "end": "2031"},
    )


def test_report_surfaces_direction_and_flow() -> None:
    """이사 테마 리포트 RL-04(방위)·RL-06(월별 이동운 흐름)에 M10 결과가 실린다."""
    secs = {s.section_id: s for s in plan_report(_SELF, _reloc_spec(), date(2026, 6, 11))}
    assert "방위 적합" in secs["RL-04"].body_prompt
    assert "월별 이동운 흐름" in secs["RL-06"].body_prompt
    assert "유리한 방위" in secs["RL-04"].body_prompt


# ── 십성 이유분류: 대운 축 + 채팅/연간 surface ──────────────────────


def _build_composites(birth: BirthInput, ref: date):
    """대상의 전 레벨 LuckComposite — classify_reasons 입력."""
    chart = calculate(birth.model_copy(update={"reference_date": ref}))
    return CompositeBuilder(_DICTS).build(
        chart, "본인", "1.0.0", f"{ref.isoformat()}T00:00:00+00:00")


def test_classify_reasons_adds_daewoon_axis() -> None:
    """month_key 없으면 세운+대운 천간으로 분류 — 대운(장기 배경) 축이 surface된다."""
    comps = _build_composites(_SELF, date(2026, 6, 18))
    profs = RelocationResolver(_DICTS).classify_reasons(comps, "2026", None)
    sources = {p.source for p in profs}
    # 월 축이 없으므로 월운은 없고, 대운(장기 배경)이 천간 배경 축으로 들어온다.
    assert any(s.startswith("대운 천간") for s in sources)
    assert not any(s.startswith("월운") for s in sources)


def test_chat_group_block_surfaces_reasons() -> None:
    """그룹 이사 택일 블록에 십성 이유분류 라벨이 동반된다(채팅 surface)."""
    intent = parse_message(
        "배우자랑 같이 이사 좋은 날 언제야?", date(2026, 6, 11), birth_year=1990
    ).intents[0]
    block = chat_service._relocation_group_block(
        _SELF, _PARTNER, intent, date(2026, 6, 11), "본인", "배우자",
    )
    assert block is not None
    assert block.relocation_reasons  # 십성 이유분류 동반
    assert any("→" in r for r in block.relocation_reasons)


def test_eval_question_surfaces_reason_context() -> None:
    """'이사하면 어때?'(택일 아님·domain_analysis) 질문도 십성 이유분류를 구조 블록에 싣는다."""
    intent = parse_message(
        "6월에 이사하면 어때?", date(2026, 6, 18), birth_year=1990).intents[0]
    # 택일이 아니라 도메인 분석 질문이어야 한다(date_block 미생성 경로).
    assert intent.query_type.value == "domain_analysis"
    lines = chat_service._relocation_reason_context(_SELF, intent, date(2026, 6, 18))
    assert lines and "이사 이유·집 성격 — 십성 분류" in lines[0]
    assert any("→" in line for line in lines[1:])
    assert any(line.startswith("- 세운 천간") for line in lines)


def test_relocation_directive_injected_in_prompt() -> None:
    """이사 질문이면 십성(유형)/용신·기신(길흉) 분리 지시가 프롬프트에 주입된다(dry_run)."""
    b = BirthInput(
        calendar_type="solar", birth_date=date(1988, 3, 5), birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    prompt = chat_service.chat(
        b, "6월에 이사하면 어때?", today=date(2026, 6, 18), dry_run=True).prompt_preview or ""
    # 십성 이유분류 블록 + 십성/길흉 분리 지시가 함께 실린다.
    assert "이사 이유·집 성격 — 십성 분류" in prompt
    assert "이사 해석 규칙" in prompt and "둘을 섞어" in prompt


def test_non_relocation_no_directive() -> None:
    """이사가 아닌 질문엔 이사 지시·이유분류가 실리지 않는다(회귀 방지)."""
    b = BirthInput(
        calendar_type="solar", birth_date=date(1988, 3, 5), birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    prompt = chat_service.chat(
        b, "올해 재물운 어때?", today=date(2026, 6, 18), dry_run=True).prompt_preview or ""
    assert "이사 해석 규칙" not in prompt


def test_target_region_extracted_and_normalized() -> None:
    """'서울 중구로 이사' 목적지 추출 + 등재 키 정규화(모호 지명은 None)."""
    from saju_api.services.chat_service import _DICTS, _normalize_region
    from saju_engines.relocation import RelocationResolver

    it = parse_message("서울 중구로 이사가려 해. 나랑 잘 맞을까?", date(2026, 6, 18)).intents[0]
    assert it.constraints.target_region == "서울 중구"
    known = RelocationResolver(_DICTS).known_regions()
    assert _normalize_region("서울 중구", known) == "서울 중구"  # 완전일치
    assert _normalize_region("수원시", known) == "경기도 수원시"  # 접미 유일
    assert _normalize_region("중구", known) is None  # 여러 시도 — 모호


def test_region_fit_context_surfaces_for_registered_region() -> None:
    """등재 목적지면 지역 오행×용신 적합이 구조 블록에 실린다. 모호·미지정이면 빈 줄."""
    b = BirthInput(
        calendar_type="solar", birth_date=date(1988, 3, 5), birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    it = parse_message("서울 중구로 이사가려 해. 나랑 잘 맞을까?", date(2026, 6, 18)).intents[0]
    lines = chat_service._relocation_region_context(b, it, date(2026, 6, 18))
    assert lines and "지역 오행 적합" in lines[0]
    assert "서울 중구" in lines[1] and "적합도" in lines[1]
    # 목적지 미지정이면 빈 줄.
    it2 = parse_message("이사하면 어때?", date(2026, 6, 18)).intents[0]
    assert chat_service._relocation_region_context(b, it2, date(2026, 6, 18)) == []


def test_region_recommendation_context_open_and_specific() -> None:
    """P4-A 배선: 미지정/시도 범위는 시군구 후보 추천, 특정 시군구는 제외(단건 경로 담당)."""
    from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

    b = BirthInput(
        calendar_type="solar", birth_date=date(1988, 3, 5), birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 26))

    def _intent(**c: object) -> IntentJson:
        return IntentJson(
            intent_id="t", query_type=QueryType.DECISION_SUPPORT, domain=Domain.RELOCATION,
            constraints=Constraints(**c),
        )

    # 개방형(목적지 미지정) → 전국 시군구 후보 랭킹.
    open_lines = chat_service._region_recommendation_context(
        b, _intent(location_base="서울특별시 강남구"), date(2026, 6, 26))
    assert open_lines and "지역 오행 추천" in open_lines[0]
    assert any("적합" in ln for ln in open_lines[1:])
    # 시도 범위(제주) → 제주 시군구만.
    jeju = chat_service._region_recommendation_context(
        b, _intent(target_region="제주"), date(2026, 6, 26))
    assert jeju and all("제주" in ln for ln in jeju[1:] if ln[0].isdigit())
    # 특정 시군구 → 단건 궁합 경로가 담당하므로 여기선 빈 줄.
    assert chat_service._region_recommendation_context(
        b, _intent(target_region="서울 중구"), date(2026, 6, 26)) == []


def test_year_report_surfaces_relocation_type() -> None:
    """연간 총운(RPT_YEAR) Y-04에 세운·대운 천간 이사 유형이 간결 surface된다."""
    spec = ReportSpec(
        product_code="RPT_YEAR", topic="general",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period={"start": "2026", "end": "2026"},
    )
    secs = {s.section_id: s for s in plan_report(_SELF, spec, date(2026, 6, 18))}
    body = secs["Y-04"].body_prompt
    assert "올해 이사·이동의 성격" in body
    assert "세운 천간" in body and "→" in body


def test_chat_topic_module_context_wired() -> None:
    """옵션1: 토픽 질문(재물)은 해당 Topic Builder 모듈을 실행해 확정 신호+정책 톤을 싣는다."""
    from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

    b = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    wealth = IntentJson(
        intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.WEALTH,
        constraints=Constraints())
    lines = chat_service._topic_module_context(b, wealth, date(2026, 6, 18))
    assert lines and "M09" in lines[0]
    assert any("번호·종목 픽 금지" in ln for ln in lines)  # 절대원칙 8 정책 톤
    # 비토픽(general)은 빈 줄.
    general = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        constraints=Constraints())
    assert chat_service._topic_module_context(b, general, date(2026, 6, 18)) == []


def test_report_region_block_with_residence(monkeypatch) -> None:
    """옵션1: 거주지 정보가 있으면 리포트가 현 지역 평가 + 살면 좋은 지역 추천을 싣는다."""
    from saju_api.services import report_service
    from saju_shared_types.report import ReportPeriod

    monkeypatch.setattr(report_service, "_residence_region", lambda _o: "서울특별시 강남구")
    b = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"))
    data = report_service._ReportData(b, spec, date(2026, 6, 18))
    block = report_service._region_report_block(data, spec)
    # compiled 스냅샷이 있으면 평가+추천이 나온다(없으면 graceful 빈 줄 — skip).
    if not block:
        import pytest
        pytest.skip("지역 compiled 스냅샷 미빌드")
    assert "거주 지역 평가·추천" in block[0]
    assert any("현 거주지 서울특별시 강남구" in ln for ln in block)
    assert any("살면 좋은 지역" in ln for ln in block)


# ── 2026-06-26 데굴님 지적: 공간(지역 추천) 질문의 시점·이사의도 과잉 승계 + 스코프·이중병기 ──


def test_place_seeking_followup_drops_prior_date_and_scopes_region() -> None:
    """'7/4 이사' 뒤 '서울 살 곳 추천'은 7/4 일운/질문기간을 승계하지 않고 서울 스코프로 잡힌다."""
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState

    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    today = date(2026, 6, 26)
    p1, state, _r1, _l1 = eng.process_turn(
        state, "7월 4일에 서울 중구로 이사가게 되었어", today)
    assert p1.intents[0].time_range is not None
    assert p1.intents[0].time_range.start == "2026-07-04"  # 1턴은 날짜 보유
    p2, state, _r2, _l2 = eng.process_turn(
        state, "서울 내에 내가 살면 좋은 지역을 추천해줘", today)
    it2 = p2.intents[0]
    # 7/4 미승계 + relocation 도메인 + 서울 스코프.
    assert not (it2.time_range and it2.time_range.start == "2026-07-04")
    assert it2.domain.value == "relocation"
    assert it2.constraints.target_region == "서울"


def test_sido_scope_extracted_only_in_residence_context() -> None:
    """시도 스코프는 거주·추천 맥락에서만 채택('서울에 재물운'은 스코프 아님)."""
    from saju_engines.query_parser import parse_message

    a = parse_message("서울 내에 내가 살면 좋은 지역을 추천해줘", date(2026, 6, 26)).intents[0]
    assert a.constraints.target_region == "서울"
    b = parse_message("경기도에서 살 곳 추천해줘", date(2026, 6, 26)).intents[0]
    assert b.constraints.target_region == "경기"
    c = parse_message("서울에 재물운 어때?", date(2026, 6, 26)).intents[0]
    assert c.constraints.target_region is None  # 타 도메인 오염 방지
    d = parse_message("서울 중구로 이사가려 해", date(2026, 6, 26)).intents[0]
    assert d.constraints.target_region == "서울 중구"  # 시군구 경로 회귀


def test_ganji_gloss_double_annotation_collapsed() -> None:
    """간지 이중 병기(LLM 과글로싱)를 한 번으로 정규화하되 올바른 단일 병기는 보존한다."""
    from saju_api.services.chat_service import _normalize_ganji_gloss as g

    assert g("이날은 기묘(己卯(기묘))일로") == "이날은 기묘(己卯)일로"
    assert g("7월은 갑오(甲午(갑오))월로") == "7월은 갑오(甲午)월로"
    assert g("己卯(기묘)(기묘)일") == "己卯(기묘)일"
    assert g("정상: 갑오(甲午)월 / 己卯일") == "정상: 갑오(甲午)월 / 己卯일"  # 보존


def test_region_element_fact_direct_answer() -> None:
    """'창원 성산구의 오행은?' 사실 질문은 too_broad가 아니라 지역 엔진 프로파일로 직접 답한다."""
    b = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    r = chat_service.chat(b, "창원 성산구의 오행은 뭐야?", today=date(2026, 6, 18), dry_run=True)
    if r.status != "answered":  # compiled 미빌드 환경
        import pytest
        pytest.skip("지역 compiled 스냅샷 미빌드")
    assert "지역 오행" in (r.answer or "") and "창원시 성산구" in (r.answer or "")
    assert any(e in (r.answer or "") for e in ("목(木)", "화(火)", "토(土)", "금(金)", "수(水)"))
    # '내 사주 오행'은 지역 사실 라우트로 빠지지 않는다(개인 사주 분석 경로 유지).
    r2 = chat_service.chat(b, "내 사주 오행 분포 어때?", today=date(2026, 6, 18), dry_run=True)
    assert "지역 오행은" not in (r2.answer or "")
