"""2026-10-27 외부 자료 대조 반영분 — 서술층·궁합 신호·조토/습토 규칙 회귀.

대조 기록: doc/v2_2/EXTERNAL_TEXT_GAP_TAESAN.md. 각 규칙은 성립 사례와 반례를 함께 고정한다
(반례 없는 테스트는 게이트를 통과해 버린다 — 2026-10-14 검수 교훈).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import (
    _relation_text_by_id,
    build_chart_interpretation,
    first_arrival_note,
)
from saju_engines.compatibility_engine import (
    _ATTRACTION_WEIGHT,
    _output_yongsin_signals,
    _weak_resource_signals,
)
from saju_engines.context_reducer import (
    SCORE_FLOOR,
    family_extra_candidates,
    period_other_signal_lines,
    reduce_candidates,
)
from saju_engines.dictionaries import (
    RelationsTextFile,
    _lint_relations_text,
    validate_dictionaries,
)
from saju_engines.love_period_notes import love_period_notes
from saju_engines.love_type import LoveTypeResult, excess_groups, love_type_lines
from saju_engines.structural_context import (
    excess_remedy_lines,
    load_remedy_action_map,
    remedy_action_lines,
)
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind
from saju_shared_types.constants import BRANCH_CLASHES
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.llm_input import UsefulGods

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(birth_date: str, birth_time: str, gender: str = "female"):
    return calculate(BirthInput(
        birth_date=birth_date, birth_time=birth_time, birth_place_name="서울", gender=gender,
    ))


def test_dictionaries_validate_clean() -> None:
    assert validate_dictionaries(_DICTS) == []


# ── 조토불생금·습토회화(조토/습토 규칙 확정) ─────────────────────────────


def _ids(result) -> set[str]:
    return {p.pattern_id for p in detect_structure_patterns(result)}


def test_joto_fires_with_dry_earth_metal_and_weak_water() -> None:
    r = _chart("1975-02-07", "21:30")  # 卯寅申戌 — 戌 조토, 辰丑 없음, 金 있음, 水 약
    assert "JOTO_BULSAENGGEUM" in _ids(r)


def test_joto_counter_wet_earth_present() -> None:
    # 反例: 戌(조토)와 丑(습토)이 함께 있으면 습토가 생금하므로 성립하지 않는다.
    r = _chart("1975-01-24", "21:30")  # 寅丑午戌
    branches = {getattr(r.pillars, p).branch for p in ("year", "month", "day", "hour")}
    assert {"戌", "丑"} <= branches
    assert "JOTO_BULSAENGGEUM" not in _ids(r)


def test_joto_excludes_togeum_yuksu() -> None:
    # 戊 일간·신강·金 존재 — 조토불생금이 서면 토금육수(土生金 배합)는 성립하지 않는다.
    r = _chart("1969-02-12", "15:30", "male")
    ids = _ids(r)
    assert r.pillars.day_master == "戊"
    assert "JOTO_BULSAENGGEUM" in ids
    assert "TOGEUM_YUKSU" not in ids


def test_seupto_fires_with_two_wet_earth_and_weak_fire() -> None:
    r = _chart("1975-04-11", "09:30")  # 卯辰亥辰 — 辰 2개, 火 약
    assert "SEUPTO_HOEHWA" in _ids(r)


def test_seupto_counter_single_wet_earth() -> None:
    # 反例: 습토가 하나뿐이면(丑 1) 습토회화가 아니다.
    r = _chart("1975-01-24", "21:30")  # 寅丑午戌
    assert "SEUPTO_HOEHWA" not in _ids(r)


# ── 십성다자 양면 성향(원국 해석 발췌) ───────────────────────────────────


def test_group_trait_excerpt_matches_excess_groups() -> None:
    r = _chart("1975-01-03", "21:30")  # 관성 3글자
    ci = build_chart_interpretation(r)
    assert ci is not None
    got = [e for e in ci.excerpts if e.kind == "ten_god_group"]
    assert [e.key.split(" ")[0] for e in got] == [g for g, _ in excess_groups(r)]
    text = got[0].text
    assert "책임감이 강해" in text and "서열을 나누고" in text  # 두 갈래 모두
    assert "단정하지 말 것" in text


def test_group_trait_excerpt_absent_without_excess() -> None:
    r = _chart("1980-11-22", "09:08", "male")
    ci = build_chart_interpretation(r)
    assert ci is not None
    got = [e for e in ci.excerpts if e.kind == "ten_god_group"]
    assert len(got) == len(excess_groups(r))


# ── 연애 유형: 사랑에 빠졌을 때·미련(빈 칸은 생략) ──────────────────────────


def test_love_type_lines_in_love_and_lingering() -> None:
    lines = "\n".join(love_type_lines(LoveTypeResult(primary="비겁", basis="테스트")))
    assert "사랑에 빠졌을 때" in lines and "이별 뒤 미련" in lines


def test_love_type_lines_all_groups_filled() -> None:
    # 2026-10-27 2차: 관성 연애 행동·재성/관성 미련을 보완 해석으로 채워 5군 모두 두 줄이 있다.
    for g in ("비겁", "식상", "재성", "관성", "인성"):
        lines = "\n".join(love_type_lines(LoveTypeResult(primary=g, basis="테스트")))
        assert "사랑에 빠졌을 때" in lines and "이별 뒤 미련" in lines, g


def test_love_type_lines_skip_empty_field(monkeypatch: pytest.MonkeyPatch) -> None:
    # 反例: 사전 칸이 비면 줄을 지어내지 않고 생략한다.
    import saju_engines.love_type as lt

    items = lt.load_love_types()
    items["관성"] = {**items["관성"], "inLove": "", "lingering": ""}
    monkeypatch.setattr(lt, "load_love_types", lambda: items)
    lines = "\n".join(lt.love_type_lines(LoveTypeResult(primary="관성", basis="테스트")))
    assert "사랑에 빠졌을 때" not in lines and "이별 뒤 미련" not in lines


# ── 충 성향(질환어는 참고용 표기) ─────────────────────────────────────────


def test_clash_trait_has_reference_note() -> None:
    texts = _relation_text_by_id()
    for rid in ("rel_寅申沖", "rel_巳亥沖", "rel_卯酉沖", "rel_子午沖", "rel_甲庚沖"):
        assert "의학적 판단 아님" in texts[rid]["natalTrait"], rid


def test_clash_trait_lint_counter_example() -> None:
    raw = json.loads((_DICTS / "interpretations" / "relations_text.json").read_text("utf-8"))
    for item in raw["items"]:
        if item["id"] == "rel_甲庚沖":
            item["natalTrait"] = "두통이 잦을 수 있다."
    errors = _lint_relations_text(_DICTS, RelationsTextFile.model_validate(raw))
    assert any("rel_甲庚沖" in e for e in errors)


# ── 용신·기신 운의 다른 얼굴 ───────────────────────────────────────────────


def test_favorability_face_excerpts() -> None:
    r = _chart("1980-11-22", "09:08", "male")
    ci = build_chart_interpretation(r)
    assert ci is not None
    faces = [e for e in ci.excerpts if e.kind == "favorability_face"]
    assert any("용신 운의 다른 얼굴" in e.key for e in faces)
    yong = next(e for e in faces if "용신" in e.key)
    assert "미리 단정하지 않는다" in yong.text  # 사건 미화 차단


# ── 처음 들어오는 용·희신 기운 ────────────────────────────────────────────


def _with_visible(result, vis: dict[str, float]):
    fa = result.force_analysis
    fe = fa.five_elements.model_copy(update={"visible_percent": vis})
    return result.model_copy(update={"force_analysis": fa.model_copy(update={"five_elements": fe})})


def test_first_arrival_fires_for_absent_yongsin_in_year_luck() -> None:
    r = _with_visible(_chart("1980-11-22", "09:08", "male"),
                      {"木": 30.0, "火": 0.0, "土": 30.0, "金": 20.0, "水": 20.0})
    note = first_arrival_note(r, "丙午", "year", {"火": "용신"})
    assert "火(용신)" in note and "낯섦" in note


def test_first_arrival_counter_examples() -> None:
    r = _with_visible(_chart("1980-11-22", "09:08", "male"),
                      {"木": 30.0, "火": 0.0, "土": 30.0, "金": 20.0, "水": 20.0})
    assert first_arrival_note(r, "丙午", "month", {"火": "용신"}) == ""  # 월운 제외
    assert first_arrival_note(r, "丙午", "year", {"火": "기신"}) == ""  # 기신은 대상 아님
    present = _with_visible(r, {"木": 20.0, "火": 10.0, "土": 30.0, "金": 20.0, "水": 20.0})
    assert first_arrival_note(present, "丙午", "year", {"火": "용신"}) == ""  # 원국에 있음


# ── 연애 운 결(관계 사건 후보) ─────────────────────────────────────────────


def test_love_period_notes_clash_and_ten_god() -> None:
    r = _chart("1975-01-03", "09:30")  # 己 일간
    day_branch = Branch(r.pillars.day.branch)
    clash = next(
        b for pair in BRANCH_CLASHES if day_branch in pair for b in pair if b != day_branch
    )
    notes = love_period_notes(r, f"甲{clash.value}", "new_relationship", {})
    assert any("일지(배우자 자리)를 충하는 운" in n for n in notes)
    assert any("관성 운" in n for n in notes)  # 己 기준 甲=정관


def test_love_period_notes_counter_examples() -> None:
    r = _chart("1975-01-03", "09:30")
    day_branch = Branch(r.pillars.day.branch)
    clash_partners = {b for pair in BRANCH_CLASHES if day_branch in pair for b in pair}
    calm = next(b for b in Branch if b not in clash_partners)
    notes = love_period_notes(r, f"丙{calm.value}", "new_relationship", {})
    assert not any("충하는 운" in n for n in notes)
    assert not any("관성 운" in n or "식상 운" in n for n in notes)  # 己 기준 丙=정인(정의 없음)
    # 관계 사건이 아니면 아무 구절도 붙지 않는다.
    assert love_period_notes(r, f"甲{calm.value}", "career_change", {}) == []


def test_love_period_notes_role_split() -> None:
    r = _chart("1975-01-03", "09:30")
    hard = love_period_notes(r, "甲寅", "new_relationship", {"木": "기신"})
    good = love_period_notes(r, "甲寅", "new_relationship", {"木": "용신"})
    mixed = love_period_notes(r, "甲申", "new_relationship", {"木": "기신", "金": "용신"})
    assert any("오래 기억될 수 있다" in n for n in hard)
    assert any("긴가민가할 수 있다" in n for n in good)
    assert not any("오래 기억" in n or "긴가민가" in n for n in mixed)  # 엇갈리면 생략


# ── 궁합 신호 2종(끌림 점수 포함) ─────────────────────────────────────────


def test_weak_resource_partner_signal() -> None:
    weak = _chart("1975-01-03", "09:30")  # 己 신약
    resource = _chart("1976-03-06", "12:00", "male")  # 丁 — 己의 편인
    assert weak.force_analysis.strength.band in ("신약", "태신약")
    sigs = _weak_resource_signals(weak, resource, self_label="본인", partner_label="상대")
    assert [s.kind for s in sigs] == [CompatSignalKind.WEAK_RESOURCE_PARTNER]
    assert sigs[0].direction is CompatDirection.HARMONY
    assert _ATTRACTION_WEIGHT[CompatSignalKind.WEAK_RESOURCE_PARTNER] == 1


def test_weak_resource_counter_strong_taker() -> None:
    # 反例: 신강 庚에게 己(정인)는 신호가 아니고, 신약 己에게 庚(상관)도 인성이 아니다.
    strong = _chart("1975-01-24", "09:30")  # 庚 신강
    weak = _chart("1975-01-03", "09:30")  # 己 신약
    assert _weak_resource_signals(strong, weak, self_label="본인", partner_label="상대") == []


def test_output_yongsin_signal_and_counter() -> None:
    me = UsefulGods(yongsin=["火"])
    other = UsefulGods()
    hit = _output_yongsin_signals(Stem("庚"), Stem("甲"), me, other,
                                  self_label="본인", partner_label="상대")
    assert [s.kind for s in hit] == [CompatSignalKind.OUTPUT_YONGSIN_SUPPORT]  # 甲의 식상=火
    miss = _output_yongsin_signals(Stem("庚"), Stem("壬"), me, other,
                                   self_label="본인", partner_label="상대")
    assert miss == []  # 壬의 식상=木
    assert _ATTRACTION_WEIGHT[CompatSignalKind.OUTPUT_YONGSIN_SUPPORT] == 1


# ── 오행 과다 개운 ─────────────────────────────────────────────────────────


def test_excess_remedy_lines() -> None:
    m = load_remedy_action_map(_DICTS)
    lines = excess_remedy_lines(["木", "金"], m)
    assert lines[0].startswith("木 과다 개운") and "끝까지 마무리" in lines[0]
    assert lines[1].startswith("金 과다 개운") and "빠르게 고친" in lines[1]


def test_excess_remedy_counter_examples() -> None:
    m = load_remedy_action_map(_DICTS)
    assert excess_remedy_lines([], m) == []
    assert remedy_action_lines([], m, excess_elements=[]) == []  # 블록 미부착
    block = remedy_action_lines([], m, excess_elements=["水"])
    assert block[0].startswith("[개운 행동") and "水 과다 개운" in block[1]


@pytest.mark.parametrize("word", ["태산", "태산명리"])
def test_no_source_attribution_in_dictionaries(word: str) -> None:
    # 데굴님 결정(2026-10-27): 출처는 사전 근거 칸에도 적지 않는다.
    for rel in (
        "interpretations/ten_god_group_traits.json", "interpretations/love_types.json",
        "interpretations/relations_text.json", "interpretations/favorability_text.json",
        "interpretations/sinsal_text.json", "interpretations/ten_gods_text.json",
        "interpretations/remedy_action_map.json", "structure_patterns.json",
    ):
        assert word not in (_DICTS / rel).read_text("utf-8"), rel


# ── 같은 영역 다른 사건 후보 · 같은 기간 다른 영역 신호(2026-10-27 2차) ──────────────


def _cand(key: str, score: int, period: str = "2027-02") -> SimpleNamespace:
    return SimpleNamespace(
        event_key=EventKeyV2(key), score=score, period=period,
        life_fit=0.0, personal_match=0.0, raw_total=float(score),
    )


def test_family_extra_picks_same_domain_strong_events() -> None:
    cands = [
        _cand("new_relationship", 25), _cand("marriage_signal", 96),
        _cand("relationship_change", 92), _cand("childbirth", 69), _cand("job_gain", 95),
        _cand("marriage_signal", 99, "2028-02"),
    ]
    scope = [EventKeyV2.NEW_RELATIONSHIP]
    assert reduce_candidates(cands, scope, 5, SCORE_FLOOR, "2027-02", "2027-02") == []  # 기존 0건
    extra = family_extra_candidates(cands, scope, "2027-02", "2027-02")
    # 같은 영역 70점 이상만(출산 69·다른 영역 취업·기간 밖 2028 제외), 질문 키 자체는 제외.
    assert [str(c.event_key) for c in extra] == ["marriage_signal", "relationship_change"]


def test_family_extra_counter_examples() -> None:
    cands = [_cand("public_exposure", 30), _cand("social_conflict", 90)]
    # 계열이 없는 질문 키 — 확장 대상 없음.
    assert family_extra_candidates(cands, [EventKeyV2.PUBLIC_EXPOSURE], "2027-02", "2027-02") == []
    # 질문 키가 없으면(총운 등) 아무것도 고르지 않는다.
    assert family_extra_candidates([_cand("marriage_signal", 96)], [], "2027-02", "2027-02") == []


def test_period_other_signal_lines_threshold_and_family() -> None:
    cands = [
        _cand("job_gain", 95), _cand("job_gain", 80, "2027-03"), _cand("wealth_change", 69),
        _cand("marriage_signal", 96), _cand("career_change", 70, "2028-01"),
    ]
    lines = period_other_signal_lines(
        cands, [EventKeyV2.NEW_RELATIONSHIP], "2027-01", "2027-12", {"2027-02": "壬寅"},
    )
    # 키별 1건만, 69점·기간 밖·같은 영역(결혼 신호)은 제외.
    assert lines == ["취업·합격 @ 2027-02(壬寅) — 신호가 매우 강합니다"]


def _love_prompt(question: str) -> str:
    from saju_api.services import chat_service

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(birth, question, date(2026, 10, 27), dry_run=True)
    assert res.prompt_preview is not None
    return res.prompt_preview


def test_love_question_shows_family_candidates_and_month_labels() -> None:
    p = _love_prompt("2027년 2월에 새로운 인연이 생길까?")
    fam = p[p.index("[같은 영역 다른 사건 후보 — "):p.index("[같은 기간 다른 영역 신호 — ")]
    assert "혼인 구체화 @ 2027-02" in fam  # 결혼 신호(방향 라벨) — 같은 영역 강신호
    # '후보 없음'은 질문 사건에 한정.
    assert "질문하신 사건 자체의 후보는 이 기간에 약하거나 없다" in p
    assert "'해당 기간에는 뚜렷한 신호가 없습니다'로 정직하게" not in p
    assert "- 취업·합격 @ 2027-02(壬寅)" in p  # 다른 영역은 별도 줄로만
    assert "연애 운의 결(그럴 수 있다는 경향" in p
    yearly = _love_prompt("내년에 연애운 어때? 언제쯤 인연이 생길까?")
    assert "└ 연애 운의 결:" in yearly
    assert "(연애 운의 결 — 관계 신호가 있는 달에만" in yearly


def test_love_question_family_scope_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # 反例: 플래그를 끄면 기존 단일 키 선별로 돌아간다(롤백 경로).
    from saju_engines import period_v2_config

    monkeypatch.setattr(period_v2_config, "DOMAIN_FAMILY_SCOPE_ENABLED", False)
    p = _love_prompt("2027년 2월에 새로운 인연이 생길까?")
    assert "[같은 영역 다른 사건 후보" not in p
    assert "질문 기간 내 해당 도메인 후보 없음" in p


def test_month_love_labels_absent_for_career_question() -> None:
    # 反例: 관계 도메인 질문이 아니면 월별 표에 연애 운의 결을 달지 않는다.
    p = _love_prompt("내년에 이직운 어때?")
    assert "└ 연애 운의 결:" not in p


def test_entry_slot_question_keeps_asked_candidates() -> None:
    # 反例(설계 회귀): 같은 영역 사건을 질문 후보 목록에 섞으면 취업 질문의 진입 시기 판정이
    # 계약·승진 후보로 바뀐다. 별도 블록이므로 event_candidates 는 질문 사건 키만 담는다.
    from saju_api.services import chat_service

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(birth, "2027년 2월에 새로운 인연이 생길까?", date(2026, 10, 27), True)
    assert res.postprocess is not None
    keys = {str(c.event_key) for c in res.postprocess.payload.event_candidates}
    assert keys <= {"new_relationship"}
    assert res.postprocess.payload.family_candidates


# ── 3차(재검토, 2026-10-27): 중복 제거·동점 처리·리포트 연애 운의 결 ──────────────────


def test_family_extra_dedupes_same_key_and_period() -> None:
    cands = [_cand("marriage_signal", 96), _cand("marriage_signal", 90), _cand("childbirth", 80)]
    extra = family_extra_candidates(cands, [EventKeyV2.NEW_RELATIONSHIP], "2027-02", "2027-02")
    assert [(str(c.event_key), c.score) for c in extra] == [
        ("marriage_signal", 96), ("childbirth", 80),
    ]


def test_period_other_signal_prefers_month_on_tie() -> None:
    cands = [_cand("job_gain", 90, "2027"), _cand("job_gain", 90, "2027-02")]
    lines = period_other_signal_lines(
        cands, [EventKeyV2.NEW_RELATIONSHIP], "2027-01", "2027-12", {},
    )
    assert lines == ["취업·합격 @ 2027-02 — 신호가 매우 강합니다"]


def _report_contexts(topic: str):
    from saju_api.services import report_service
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    spec = ReportSpec(
        product_code="RPT_FOCUS", topic=topic,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2027-01-01", end="2027-12-31"),
    )
    return report_service.plan_report(birth, spec, date(2026, 10, 27))


def test_report_relationship_month_pages_carry_love_notes() -> None:
    by_id = {c.section_id: c.body_prompt for c in _report_contexts("relationship")}
    page = by_id["R-05-Y2027"]
    block = page[page.index("[연애 운의 결(후보 기간)"):]
    assert "2027-02 壬寅: " in block
    assert "  · 좋은 운의 인연: " in block  # 범례 1회
    assert block.count("  · 좋은 운의 인연: ") == 1


def test_report_non_relationship_theme_has_no_love_notes() -> None:
    # 反例: 재물 테마에는 연애 운의 결을 싣지 않는다.
    assert all("[연애 운의 결" not in c.body_prompt for c in _report_contexts("wealth"))


# ── 4차(독립 리뷰 지적 반영, 2026-10-27) ─────────────────────────────────────────


def test_granularity_blocks_coarse_periods() -> None:
    cands = [_cand("job_gain", 95, "2027"), _cand("job_gain", 90, "2027-02")]
    scope = [EventKeyV2.NEW_RELATIONSHIP]
    # 월 질문 — 연 단위 후보는 '같은 기간'이 아니다.
    assert period_other_signal_lines(cands, scope, "2027-02", "2027-02", {}) == [
        "취업·합격 @ 2027-02 — 신호가 매우 강합니다",
    ]
    # 일 질문 — 보조 블록 자체를 싣지 않는다.
    assert period_other_signal_lines(cands, scope, "2027-02-11", "2027-02-11", {}) == []
    fam = [_cand("marriage_signal", 96, "2027")]
    assert family_extra_candidates(fam, scope, "2027-02", "2027-02") == []
    # 反例: 연 질문은 연·월 후보 모두 허용.
    assert len(period_other_signal_lines(cands, scope, "2027", "2027", {})) == 1


def test_same_event_domain_is_not_other_domain() -> None:
    # 직업 질문의 법적 갈등(EVENT_DOMAIN=career)은 '다른 영역' 줄에 올리지 않는다.
    cands = [_cand("legal_conflict", 95, "2027-01"), _cand("marriage_signal", 90, "2027-01")]
    lines = period_other_signal_lines(cands, [EventKeyV2.CAREER_CHANGE], "2027", "2027", {})
    assert len(lines) == 1 and "@ 2027-01" in lines[0]  # 결혼 신호만(관계 영역)
    assert all("법적" not in ln for ln in lines)


def test_family_only_turn_keeps_reading_rules() -> None:
    p = _love_prompt("2027년 2월에 새로운 인연이 생길까?")
    assert "사건명은 동반 신호 매트릭스" in p  # 질문 사건 후보 0 + 같은 영역 후보만 있어도
    assert "'새 인연' 자체 신호의 강도" in p and "이 영역의 강한 신호를 함께 밝힐 것" in p
    assert "질문 사건의 확정으로 바꿔 말하지 말 것" in p


def test_remedy_question_has_no_secondary_blocks() -> None:
    p = _love_prompt("연애운 높이는 개운법 알려줘")
    assert "[같은 영역 다른 사건 후보 — " not in p
    assert "[같은 기간 다른 영역 신호 — " not in p


def test_token_guard_drops_secondary_blocks_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from saju_api.services import chat_service
    from saju_engines import context_reducer as cr
    from saju_engines.llm_guard import TokenBudgetExceeded

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(birth, "2027년 2월에 새로운 인연이 생길까?", date(2026, 10, 27), True)
    assert res.postprocess is not None
    payload = res.postprocess.payload
    assert payload.period_other_signals and len(payload.family_candidates) >= 2
    calls = {"n": 0}

    class _Guard:
        def __init__(self, _call_type: str) -> None: ...

        def check_input(self, text: str, reserve_tokens: int = 0) -> int:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TokenBudgetExceeded("over")
            return 1

    monkeypatch.setattr(cr, "LLMCallGuard", _Guard)
    text, _ = cr.serialize_with_guard(payload, "chat_single")
    assert "[같은 기간 다른 영역 신호 — " not in text
    fam = text[text.index("[같은 영역 다른 사건 후보 — "):]
    assert fam.count(" @ 2027-02(") == 1  # 같은 영역 후보는 1건만 남는다
    assert "[이벤트 후보" in text  # 질문 사건 블록은 유지


def test_love_notes_not_repeated_across_candidates() -> None:
    p = _love_prompt("2027년 2월에 새로운 인연이 생길까?")
    fam = p[p.index("[같은 영역 다른 사건 후보 — "):p.index("[같은 기간 다른 영역 신호 — ")]
    note = "이때 만난 인연은 처음부터 확신이 서지 않고"
    assert fam.count(note) == 1  # 같은 달 두 후보(결혼 신호·관계 변화)에 한 번만
    assert "연애 운의 결: 앞 후보와 같음" in fam


def test_month_labels_absent_for_date_selection() -> None:
    p = _love_prompt("내년에 결혼하기 좋은 날 언제야?")
    assert "└ 연애 운의 결:" not in p


def test_weak_resource_skips_unconfirmed_strength_band() -> None:
    weak_unknown = calculate(BirthInput(
        birth_date="1981-08-03", birth_time_unknown=True, birth_place_name="서울", gender="female",
    ))
    hu = weak_unknown.hour_unknown
    assert hu is not None and hu.is_unconfirmed("strength_band")
    partner = _chart("1976-03-06", "12:00", "male")
    sigs = _weak_resource_signals(weak_unknown, partner, self_label="본인", partner_label="상대")
    assert all("본인(" not in s.detail for s in sigs)  # 미확정 밴드로 신약 전제를 쓰지 않음


def test_first_arrival_excludes_daewoon() -> None:
    r = _with_visible(_chart("1980-11-22", "09:08", "male"),
                      {"木": 30.0, "火": 0.0, "土": 30.0, "金": 20.0, "水": 20.0})
    assert first_arrival_note(r, "丙午", "daewoon", {"火": "용신"}) == ""
    assert first_arrival_note(r, "丙午", "year", {"火": "용신"}) != ""


def test_report_non_romantic_pair_has_no_love_notes() -> None:
    from saju_api.services.report_service import (
        _expand_report_plans,
        _ReportData,
        build_section_context,
    )
    from saju_engines.report_plan import build_section_plans
    from saju_shared_types.intent import InlineBirth, SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    me = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    mother = BirthInput(
        birth_date="1965-03-08", birth_time="10:00", birth_place_name="서울", gender="female",
    )

    def prompts(relation: str | None) -> list[str]:
        spec = ReportSpec(
            product_code="RPT_FOCUS", topic="relationship",
            subjects=[
                SubjectRef(kind=SubjectKind.SELF, label="본인"),
                SubjectRef(
                    kind=SubjectKind.INLINE_TEMP, label="상대",
                    inline_birth=InlineBirth(date="1965-03-08", time="10:00", gender="F"),
                    relation_type=relation,
                ),
            ],
            period=ReportPeriod(start="2026-07", end="2028-12"),
        )
        data = _ReportData(me, spec, date(2026, 10, 27), owner_id=None, subject_id=None,
                           partner_birth=mother)
        plans = _expand_report_plans(build_section_plans(spec), data)  # 연도별 상세 페이지 포함
        return [build_section_context(p, spec, data).body_prompt
                for p in plans if p.section_id.startswith("RP-06")]

    assert all("[연애 운의 결" not in b for b in prompts("mother"))
    assert any("[연애 운의 결" in b for b in prompts(None))  # 反例: 연애 상대면 붙는다


def test_report_month_slice_labels_only_strong_months() -> None:
    by_id = {c.section_id: c.body_prompt for c in _report_contexts("relationship")}
    block = by_id["R-05-Y2027"].split("[연애 운의 결(후보 기간)", 1)[1]
    rows = [ln for ln in block.splitlines() if ln.startswith("2027-")]
    assert 0 < len(rows) < 12



# ── 5차(권장안: 같은 영역 관계 후보 해석 틀, 2026-10-27) ─────────────────────────────


def _love_prompt_status(question: str, status: str | None) -> str:
    from saju_api.services import chat_service

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(
        birth, question, date(2026, 10, 27), dry_run=True, relationship_status=status,
    )
    assert res.prompt_preview is not None
    return res.prompt_preview


@pytest.mark.parametrize(
    ("status", "needle"),
    [
        ("dating", "교제 중으로 입력됨 — 이 영역의 강한 신호는 지금 관계의 진전·공식화로"),
        ("single", "교제 상대 없음으로 입력됨 — 새 만남 자체 신호가 약하다는 점과 함께"),
        ("married", "기혼으로 입력됨 — 이 영역의 강한 신호는 새 인연이 아니라"),
        (None, "교제 상태 미입력 — 두 경우를 한 문장씩 나눠 쓸 것"),
    ],
)
def test_relationship_family_frame_by_status(status: str | None, needle: str) -> None:
    p = _love_prompt_status("2027년 2월에 새로운 인연이 생길까?", status)
    assert "(관계 영역 해석 틀) " + needle in p
    assert p.count("(관계 영역 해석 틀)") == 1


def test_relationship_family_frame_absent_for_career_question() -> None:
    # 反例: 직업 질문의 같은 영역 블록에는 관계 해석 틀을 싣지 않는다.
    from saju_api.services import chat_service

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    p = chat_service.chat(birth, "2027년 2월에 취업할 수 있을까?", date(2026, 10, 27), True)
    assert p.prompt_preview is not None
    assert "(관계 영역 해석 틀)" not in p.prompt_preview


def _love_payload():
    from saju_api.services import chat_service

    birth = BirthInput(
        birth_date="1992-07-21", birth_time="08:00", birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(birth, "2027년 2월에 새로운 인연이 생길까?", date(2026, 10, 27), True)
    assert res.postprocess is not None
    return res.postprocess.payload


def test_family_verdict_directive_states_both_strengths() -> None:
    from saju_engines.context_reducer import family_verdict_directive

    payload = _love_payload()
    line = family_verdict_directive(payload)
    head = "[첫 판정 재료 — 엔진 확정] 질문하신 '새 인연' 자체: 뚜렷한 신호는 없습니다"
    assert line.startswith(head)
    assert "혼인 구체화 신호가 매우 강합니다" in line
    assert "만나는 분이 있다면" in line  # 교제 상태 미입력 — 두 경우 예시
    single = family_verdict_directive(payload.model_copy(update={"relationship_status": "single"}))
    assert "새로운 만남 자체의 신호는 약한 편이지만" in single


def test_family_verdict_directive_counter_examples() -> None:
    from saju_engines.context_reducer import family_verdict_directive

    payload = _love_payload()
    # 反例 1: 같은 영역 후보가 없으면 지시 없음.
    assert family_verdict_directive(payload.model_copy(update={"family_candidates": []})) == ""
    # 反例 2: 질문 사건도 강하면(70+) 충돌이 없어 지시 없음.
    strong = payload.family_candidates[0].model_copy(
        update={"event_key": EventKeyV2.NEW_RELATIONSHIP, "score": 80},
    )
    assert family_verdict_directive(payload.model_copy(update={"event_candidates": [strong]})) == ""
