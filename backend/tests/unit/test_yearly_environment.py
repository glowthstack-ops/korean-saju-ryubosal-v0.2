"""월주 상대 관점(세운 환경 블록) 회귀 — 2026-10-25 데굴님 승인(별의당 「운명의 병오년」 번역층).

검증 축:
  ① 계산 재현 — 강의 사례(壬寅 월주 × 丙午년): 월간 壬 기준 丙=편재·午=정재·胎 / 세운 丙 기준
     壬=편관·寅=편인·長生 / 寅午 반합 / 丙壬충 / 통근 丙(寅○午○)·壬(寅×午×).
  ② 세운 전용 — 월운·일운 pillar 는 None(대운·월운 미적용 결정).
  ③ 채팅 '해당 연 총운' 프롬프트에 블록이 [세운:] 줄 뒤에 붙고, 월 총운에는 없다.
  ④ 리포트 F-11·Y-04 에 [해당 연 세운 grounding] + 환경 블록이 붙는다(패리티).
  ⑤ 시대 기운 연도 — '내년/2027년' 질문은 丁未, 올해 질문은 丙午(2026-10-25 실측 결함 교정).
  ⑥ 계층 블록 천간 참여자 라벨 — 丙壬沖의 壬은 '원국 월간 壬'(종전 '월지' 오표기 교정).
  ⑦ 사전 lint — 십성 10·운성 12·관계/통근 키·단정 어휘.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
from saju_api.services.chat_service import calculate
from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.conversation_store import ConversationStore
from saju_engines.dictionaries import (
    YearlyEnvironmentFile,
    _lint_yearly_environment,
    validate_dictionaries,
)
from saju_engines.luck_hierarchy_render import _who
from saju_engines.report_plan import build_section_plans
from saju_engines.yearly_environment import (
    YearlyEnvironment,
    build_yearly_environment,
    render_yearly_environment,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Granularity, SubjectKind, SubjectRef
from saju_shared_types.luck import LuckPillar
from saju_shared_types.luck_hierarchy import (
    HierarchyInteraction,
    HierarchyParticipant,
    ParticipantLayer,
    participant_label,
)
from saju_shared_types.report import ReportPeriod, ReportSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 10, 25)
# 강의 사례와 같은 壬寅 월주 + 甲 일간(안세영 사례와 같은 일간) — 1982-02-20 09:00 서울 여.
_BIRTH_IMIN = BirthInput(
    calendar_type="solar", birth_date="1982-02-20", birth_time="09:00", birth_place_name="서울",
    gender="female", reference_date="2026-10-25",
)
_BIRTH_DG = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울",
    gender="male", reference_date="2026-10-25",
)


@pytest.fixture(scope="module")
def imin_result():
    r = calculate(_BIRTH_IMIN)
    assert r.pillars is not None and r.pillars.month.ganji == "壬寅"
    return r


def _yearly(result, label: str) -> LuckPillar:
    return next(p for p in result.luck_cycles.yearly_luck if p.label == label)


# ── ① 계산 재현 ────────────────────────────────────────────────────────────


def test_lecture_case_imin_month_x_byeongo_year(imin_result) -> None:
    env = build_yearly_environment(imin_result, _yearly(imin_result, "2026"))
    assert isinstance(env, YearlyEnvironment)
    assert (env.month_ganji, env.luck_ganji) == ("壬寅", "丙午")
    # 월간 壬 기준: 丙=편재, 午(본기 丁)=정재, 午는 壬의 태지
    fwd = (env.forward_stem_tg, env.forward_branch_tg, env.forward_branch_main)
    assert fwd == ("편재", "정재", "丁")
    assert env.forward_stage == "태"
    # 세운 丙 기준: 壬=편관, 寅(본기 甲)=편인, 寅은 丙의 장생지
    rev = (env.reverse_stem_tg, env.reverse_branch_tg, env.reverse_branch_main)
    assert rev == ("편관", "편인", "甲")
    assert env.reverse_stage == "장생"
    # 寅午 반합(火) · 丙壬충 · 통근 丙 寅○午○ / 壬 寅×午×
    assert [k for k, _ in env.branch_relations] == ["branch_half_harmony"]
    assert env.stem_relation == "stem_clash"
    assert env.luck_roots == ["寅", "午"] and env.month_roots == []
    assert env.rooting_key == "luck_only"


def test_render_uses_dictionary_vocabulary_only(imin_result) -> None:
    env = build_yearly_environment(imin_result, _yearly(imin_result, "2026"))
    lines = render_yearly_environment(env)
    text = "\n".join(lines)
    assert lines[0].startswith("[월주 상대 관점 — 시절이 만드는 환경")
    assert "월주와 세운의 상대 기운으로 보면" in lines[0]
    assert "천간 丙=편재 · 지지 午=정재(본기 丁) · 午=壬의 태(胎)지" in text
    assert "천간 壬=편관 · 지지 寅=편인(본기 甲) · 寅=丙의 장생(長生)지" in text
    assert "午寅반합(火)" in text and "丙壬충" in text
    assert "세운 천간 丙 → 寅(○)·午(○) / 월간 壬 → 寅(×)·午(×)" in text
    assert "큰 무대·활동 영역·새로운 기회" in text  # 편재 forward 어휘(강의 6:41)
    assert "관문" in text  # 편관 reverse·천간충 어휘
    assert lines[-1].startswith("- 서술 규칙:")
    for bad in ("반드시", "확실히", "틀림없이"):
        assert bad not in text


def test_no_relation_case_renders_none_line(imin_result) -> None:
    """지지·천간 관계가 모두 없는 해 — 2029 己酉 × 壬寅(酉↔寅 무관계, 己↔壬 합·충 없음)."""
    env = build_yearly_environment(imin_result, _yearly(imin_result, "2029"))
    assert env is not None and env.luck_ganji == "己酉"
    assert env.branch_relations == [] and env.stem_relation is None
    text = "\n".join(render_yearly_environment(env))
    assert "지지 관계(세운 酉 ↔ 월지 寅): 없음" in text
    assert "천간 관계(세운 己 ↔ 월간 壬): 합·충 없음" in text


# ── ② 세운 전용 ────────────────────────────────────────────────────────────


def test_only_year_pillars_produce_environment(imin_result) -> None:
    month = imin_result.luck_cycles.monthly_luck[0]
    assert month.period_type == "month"
    assert build_yearly_environment(imin_result, month) is None
    assert render_yearly_environment(None) == []


# ── ③ 채팅 경로(dry-run) ───────────────────────────────────────────────────


def _dry(birth: BirthInput, question: str) -> str:
    r = cs.chat(birth, question, _TODAY, dry_run=True, store=ConversationStore(), owner_id="t")
    assert r.status == "dry_run", r.answer
    return r.prompt_preview or ""


def test_chat_yearly_prompt_carries_environment_block_after_sewoon_line() -> None:
    text = _dry(_BIRTH_IMIN, "올해 운세 어때?")
    assert "[해당 연 총운 — 2026 丙午" in text
    i_sewoon = text.index("\n세운: ")
    i_env = text.index("[월주 상대 관점 — 시절이 만드는 환경")
    assert i_sewoon < i_env
    assert "午=壬의 태(胎)지" in text and "丙壬충" in text
    # 합성 지시(환경 → 태도 → 주제)
    assert "'시절이 만드는 환경' 한 문장" in text


def test_chat_monthly_prompt_has_no_environment_block() -> None:
    text = _dry(_BIRTH_IMIN, "이번달 운세 어때?")
    assert "[해당 월 총운" in text
    assert "[월주 상대 관점" not in text


# ── ⑤ 시대 기운 연도 ───────────────────────────────────────────────────────


def test_era_energy_follows_target_year_not_today() -> None:
    nxt = _dry(_BIRTH_DG, "내년 운세 어때?")
    assert "[해당 연 총운 — 2027 丁未" in nxt
    assert "[2027년 丁未年 시대 기운" in nxt
    assert "丙午年 시대 기운" not in nxt
    this = _dry(_BIRTH_DG, "올해 운세 어때?")
    assert "[2026년 丙午年 시대 기운" in this


def test_era_year_helper_single_year_only() -> None:
    from saju_shared_types.intent import IntentJson, TimeRange

    def _intent(tr: TimeRange | None) -> IntentJson:
        return IntentJson.model_construct(time_range=tr)

    y = TimeRange(type="absolute", granularity=Granularity.YEAR, start="2027", end="2027")
    assert cs._era_year(_intent(y), _TODAY) == 2027
    span = TimeRange(type="absolute", granularity=Granularity.YEAR, start="2027", end="2029")
    assert cs._era_year(_intent(span), _TODAY) == 2026  # 복수 연 범위는 올해 유지
    assert cs._era_year(_intent(None), _TODAY) == 2026


# ── ④ 리포트 패리티 ────────────────────────────────────────────────────────


def _year_spec(year: str) -> ReportSpec:
    return ReportSpec(
        product_code="RPT_YEAR", topic="general",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start=year, end=year),
    )


def test_report_y04_carries_sewoon_grounding_and_environment() -> None:
    spec = _year_spec("2027")
    data = _ReportData(_BIRTH_IMIN, spec, _TODAY, owner_id=None, subject_id=None)
    plan = next(p for p in build_section_plans(spec) if p.section_id == "Y-04")
    body = build_section_context(plan, spec, data).body_prompt
    assert "[해당 연 세운 grounding — 2027 丁未" in body
    assert "\n세운: 丁未 유입 = 천간 丁" in body
    assert "[월주 상대 관점 — 시절이 만드는 환경" in body
    assert "× 세운 2027 丁未" in body
    assert "서술 순서: [월주 상대 관점]" in body


def test_report_f11_uses_today_year() -> None:
    spec = ReportSpec(
        product_code="RPT_FULL", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    data = _ReportData(_BIRTH_IMIN, spec, _TODAY, owner_id=None, subject_id=None)
    plan = next(p for p in build_section_plans(spec) if p.section_id == "F-11")
    body = build_section_context(plan, spec, data).body_prompt
    assert "[해당 연 세운 grounding — 2026 丙午" in body
    assert "午=壬의 태(胎)지" in body
    # 다른 운 섹션(F-10 현재 대운)에는 붙지 않는다.
    plan10 = next(p for p in build_section_plans(spec) if p.section_id == "F-10")
    assert "[해당 연 세운 grounding" not in build_section_context(plan10, spec, data).body_prompt


# ── ⑥ 계층 블록 천간 참여자 라벨 ───────────────────────────────────────────


def test_hierarchy_participant_label_distinguishes_stem_and_branch() -> None:
    assert participant_label(ParticipantLayer.NATAL_MONTH, "壬") == "원국 월간"
    assert participant_label(ParticipantLayer.NATAL_MONTH, "寅") == "원국 월지"
    assert participant_label(ParticipantLayer.NATAL_DAY, "甲") == "원국 일간"
    assert participant_label(ParticipantLayer.ANNUAL, "丙") == "세운"
    inter = HierarchyInteraction(
        interaction_id="rel_丙壬沖", relation_label="丙壬沖", kind="stem_clash",
        participants=[
            HierarchyParticipant(char="丙", layer=ParticipantLayer.ANNUAL),
            HierarchyParticipant(char="壬", layer=ParticipantLayer.NATAL_MONTH),
        ],
    )
    assert _who(inter) == "세운 丙 + 원국 월간 壬"


def test_chat_hierarchy_block_labels_stem_clash_with_wolgan() -> None:
    """壬寅 월주 × 丙午년 — 계층 블록 ON 이면 丙壬沖 참여자가 '원국 월간 壬'으로 나간다."""
    from saju_engines import period_v2_config as c

    if not c.PERIOD_HIERARCHY_ENABLED:
        pytest.skip("계층 블록 OFF 환경")
    text = _dry(_BIRTH_IMIN, "올해 운세 어때?")
    assert "원국 월지 壬" not in text
    assert "원국 월간 壬" in text


# ── ⑦ 사전 lint ───────────────────────────────────────────────────────────


def test_dictionary_validates_and_lints() -> None:
    errs = [e for e in validate_dictionaries(_DICTS) if "yearly_environment" in e]
    assert errs == []


def test_lint_catches_coverage_and_assertive_words() -> None:
    import json

    path = _DICTS / "interpretations/yearly_environment.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["stageEnv"][0]["text"] = "반드시 새로 돋아나는 기운"
    raw["relationEnv"].pop("none")
    f = YearlyEnvironmentFile.model_validate(raw)
    errs = _lint_yearly_environment(f)
    assert any("단정 어휘 '반드시'" in e for e in errs)
    assert any("relationEnv 키 집합 불일치" in e for e in errs)
