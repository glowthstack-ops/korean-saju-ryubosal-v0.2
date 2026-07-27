"""P0 관계 주장 감사 불변식 — 2026-07-27 일운 역전 사고 회귀 고정.

사고: 엔진이 `寅亥合 → 합반(化 불성)·합거 · 壬/甲 흉 제거(유리)`로 판정했는데 답변이
"합을 하여 기신 木의 기운을 더 강하게 만든다"로 정반대 서술을 냈다(절대원칙 1 위반).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.relation_claim_audit import (
    RelationViolationKind,
    audit_relation_claims,
    canonical_claim_lines,
    patch_relation_claims,
    split_sentences,
)
from saju_engines.relation_semantics import collect_luck_relation_semantics
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.relation_semantics import (
    BindingState,
    EffectKind,
    FormationState,
    TransformationState,
)

# 회귀 대상 명식: 1980-11-22 09:40 서울 남 (庚申/丁亥/己亥/己巳, 己土 신약).
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00",
    birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
)
# 2026-07-27 기준 운 스택 — 대운 壬辰 · 세운 丙午 · 월운 乙未 · 일진 壬寅.
_LUCK_STEMS = ["壬", "丙", "乙", "壬"]
_LUCK_BRANCHES = ["辰", "午", "未", "寅"]
# 원국 8자 — 관계 참여가 허용되는 유일한 예외(운 participant는 요청 스택에 있어야 한다).
_BIRTH_PILLAR_CHARS = set("庚申丁亥己亥己巳")

# 실제 사고 답변(발췌) — 寅亥合을 '木 강화'로 역전 서술한 대목.
_BAD_ANSWER = (
    "특히 오늘 운에서 들어온 인목(寅木)이 데굴님의 타고난 명식 속 글자들과 복합적인 "
    "반응을 일으키고 있네요. 먼저 연주의 신금(申金)과 부딪히는 인신충이 발생하면서 "
    "예상치 못한 이동수나 환경의 변화가 생길 수 있어요. 동시에 일지의 해수(亥水)와는 "
    "합을 하여 기신인 목(木)의 기운을 더 강하게 만드니, 겉으로는 협력하는 듯 보여도 "
    "속으로는 본인의 에너지가 소모되는 상황이 생길 수 있어요."
)


@pytest.fixture(scope="module")
def semantics():
    """운 스택 전체를 넘겨 얻은 관계 구조화 의미."""
    from saju_api.services.manse_service import calculate

    chart = calculate(_BIRTH)
    return collect_luck_relation_semantics(chart, _LUCK_STEMS, _LUCK_BRANCHES)


def _by_label(semantics, label):
    return next(s for s in semantics if s.relation_label == label)


def test_hae_in_hap_is_bound_not_transformed(semantics):
    """寅亥合은 化 불성·합거 — 세 축이 각각 보존된다(단일 enum 축약 금지)."""
    sem = _by_label(semantics, "寅亥合")
    assert sem.formation_state is FormationState.FORMED
    assert sem.transformation_state is TransformationState.NO_TRANSFORMATION
    assert sem.binding_state is BindingState.REMOVED
    assert sem.transform_element == "木"  # 化 불성이어도 후보 오행은 보존


def test_directional_hap_is_not_transformation(semantics):
    """巳午未 방합은 기존 오행 강화이지 合化가 아니다 — 化 확정/조건부로 표기 금지."""
    sem = _by_label(semantics, "巳午未방합")
    assert sem.transformation_state is TransformationState.NOT_APPLICABLE
    assert sem.transform_element == "火"
    assert any("합화" in f for f in sem.forbidden_interpretations)
    assert any("강화" in a for a in sem.allowed_interpretations)


def test_half_hap_is_not_binding(semantics):
    """반합(半合)을 합반(合絆)으로 옮기지 않는다 — 엔진은 묶임을 주장한 적이 없다.

    실측: 午寅 kind=half · hap_mode=partial · direction=None · affected=[] →
    묶임도 합거도 없다. 이름이 비슷하다고 묶임으로 매핑하면 새 역전이 생긴다.
    """
    sem = _by_label(semantics, "寅午반합")
    assert sem.formation_state is FormationState.PARTIAL
    assert sem.binding_state is BindingState.NONE
    assert sem.transform_element == "火"
    assert "묶" not in sem.canonical_claim
    assert "합반" not in sem.canonical_claim
    assert "합거" not in sem.canonical_claim
    assert "보조적으로 강화" in sem.canonical_claim
    assert any(e.effect is EffectKind.PARTIALLY_STRENGTHENED for e in sem.effects)
    # 엔진은 반합에 'transform'을 반환하지 않는다 → 化 미결이 아니라 판정 대상 아님.
    assert sem.transformation_state is TransformationState.NOT_APPLICABLE
    assert "확정되지 않" not in sem.canonical_claim


def test_occurrences_preserve_position_after_label_normalization(semantics):
    """라벨은 정규화하되 참여 글자의 자리는 보존한다(월지 亥와 일지 亥 구분).

    정규화된 문자열에서 자리를 복원할 수 없으므로 occurrences로 따로 남긴다.
    """
    sem = _by_label(semantics, "寅亥合")
    assert sem.relation_label == "寅亥合"  # 입력 순서와 무관한 정규 라벨
    positions = {(o.char, o.position) for o in sem.occurrences}
    assert ("寅", "luck") in positions  # 일진에서 들어온 寅
    # 원국 亥는 월지·일지 두 곳에 있고, 각 관계는 자기 자리를 보존한다.
    assert any(c == "亥" and p in ("month", "day") for c, p in positions)


def test_removal_only_when_engine_says_away(semantics):
    """합거는 엔진 direction='away'일 때만 쓴다."""
    removed = _by_label(semantics, "寅亥合")  # dir=away · affected 2건
    assert removed.binding_state is BindingState.REMOVED
    assert "합거" in removed.canonical_claim

    partial = _by_label(semantics, "寅午반합")  # dir=None
    assert partial.binding_state is BindingState.NONE


def test_audit_catches_binding_asserted_when_none(semantics):
    """묶임 판정이 없는 관계를 '묶인다'고 서술하면 위반이다."""
    text = "인목(寅木)과 세운의 오화(午火)가 반합하여 서로 묶이면서 작용이 제거됩니다."
    kinds = {v.kind for v in audit_relation_claims(text, semantics)}
    assert RelationViolationKind.BINDING_ASSERTED_WHEN_NONE in kinds


def test_audit_catches_transformation_reversal(semantics):
    """사고 답변은 化 불성 역전으로 감사에 걸린다."""
    violations = audit_relation_claims(_BAD_ANSWER, semantics)
    kinds = {(v.relation_label, v.kind) for v in violations}
    assert ("寅亥合", RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT) in kinds


def test_audit_does_not_fire_on_unrelated_relations(semantics):
    """1음절 한글 음 오탐 차단 — 乙(을)·庚(경)이 '기운을'·'환경의'에 걸리지 않는다."""
    violations = audit_relation_claims(_BAD_ANSWER, semantics)
    assert {v.relation_label for v in violations} == {"寅亥合"}


def test_patch_fixes_and_survives_reaudit(semantics):
    """위반 문장을 canonical claim으로 교체하면 재감사가 깨끗해야 한다(자기 재발동 금지)."""
    violations = audit_relation_claims(_BAD_ANSWER, semantics)
    patched = patch_relation_claims(_BAD_ANSWER, violations, semantics)
    assert patched.patched_count == 1
    assert patched.fully_repaired
    assert "더 강하게 만드니" not in patched.text
    assert "합반" in patched.text
    assert audit_relation_claims(patched.text, semantics) == []


def test_canonical_claim_states_engine_verdict(semantics):
    """확정 문장은 엔진 판정(합반·합거·흉 제거)을 그대로 말한다."""
    claim = _by_label(semantics, "寅亥合").canonical_claim
    assert "합반" in claim
    assert "합거" in claim
    assert "완화" in claim  # 壬(구신)·甲(기신) 억제 = 유리


def test_prompt_uses_canonical_claim_not_only_prohibitions(semantics):
    """생성 전 입력에 확정 문장이 실린다 — 관계 사실은 자유 작문 대상이 아니다."""
    lines = canonical_claim_lines(semantics)
    assert any("관계 확정 문장" in ln for ln in lines)
    assert any("합반" in ln for ln in lines)


def test_patch_text_equals_prompt_claim(semantics):
    """프롬프트 문장과 복구 문장이 같은 SSOT여야 한다(교체가 예외 처리가 아님)."""
    sem = _by_label(semantics, "寅亥合")
    violations = audit_relation_claims(_BAD_ANSWER, semantics)
    patched = patch_relation_claims(_BAD_ANSWER, violations, semantics)
    assert patched.patches[0].replacement == sem.canonical_claim


def test_negated_claim_is_not_a_violation(semantics):
    """'합화하지 않는다'처럼 부정하는 서술은 위반이 아니다."""
    text = (
        "인목(寅木)이 들어옵니다. 해수(亥水)와 합을 이루지만 木으로 합화하지는 "
        "않고 서로 묶이는 합반에 그칩니다."
    )
    assert audit_relation_claims(text, semantics) == []


def test_forbidden_claims_are_rendered_for_prompt(semantics):
    """확정 문장 옆에 금지 주장이 함께 실린다."""
    lines = canonical_claim_lines(semantics)
    assert any("木으로 합화했다고 서술" in ln for ln in lines)


def test_period_relation_semantics_uses_only_target_stack(monkeypatch):
    """관계 수집 범위는 이번 기간의 운 스택뿐이다(질문과 무관한 연도 간지 혼입 금지).

    composite 목록 전체를 훑으면 2022~2031 세운의 parent_context까지 스택에 섞여
    `甲己合`·`丙辛合` 같은 허위 관계가 만들어졌다(2026-07-27 구현 중 발견).
    """
    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(_BIRTH, intent, date(2026, 7, 27), "daily")
    labels = {s.relation_label for s in pf.relation_semantics}

    # 전문가가 지적한 누락 신호 — 상위 운이 만드는 火(희신) 지원.
    assert "巳午未방합" in labels  # 원국 시지 巳 + 세운 午 + 월운 未
    assert "寅午반합" in labels  # 일진 寅 + 세운 午

    # 관계 수를 고정하지 않는다(정당한 변화까지 깨진다). 대신 구성 글자가 전부
    # **이번 요청 스택 또는 원국**에 속하는지를 본다.
    natal = _BIRTH_PILLAR_CHARS
    stack = set(_LUCK_STEMS) | set(_LUCK_BRANCHES)
    for sem in pf.relation_semantics:
        outside = [c for c in sem.members if c not in stack and c not in natal]
        assert not outside, f"{sem.relation_label}에 요청 스택 밖 글자 {outside}"


def test_ambiguous_sentence_is_not_patched_arbitrarily(semantics):
    """한 문장이 여러 관계에 걸리면 임의 교체하지 않고 폴백으로 넘긴다.

    寅은 寅午반합·寅亥合·寅申충·寅巳해에 모두 참여하므로, 어느 관계 문장으로
    바꿔야 하는지 확정할 수 없는 경우가 있다.
    """
    from saju_engines.relation_claim_audit import PatchOutcome, RelationClaimViolation

    sentence = "해수(亥水)와 인목(寅木)과 오화(午火)가 얽혀 木이 강해집니다."
    violations = [
        RelationClaimViolation(
            relation_label=label,
            kind=RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT,
            sentence_index=0, sentence=sentence,
        )
        for label in ("寅亥合", "寅午반합")
    ]
    patched = patch_relation_claims(sentence, violations, semantics)
    assert patched.patched_count == 0
    assert patched.ambiguous_sentences == [0]
    assert patched.outcome is PatchOutcome.AMBIGUOUS_RELATION_FALLBACK
    assert patched.text == sentence  # 임의 교체 금지


def test_split_sentences_preserves_offsets():
    """문장 분리는 오프셋을 보존해 원문 교체가 정확해야 한다."""
    text = "첫 문장이에요. 둘째 문장입니다.\n셋째 문장!"
    sentences = split_sentences(text)
    assert len(sentences) == 3
    for s in sentences:
        assert text[s.start : s.end] == s.text
