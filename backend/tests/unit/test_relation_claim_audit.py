"""P0 관계 주장 감사 불변식 — 2026-07-27 일운 역전 사고 회귀 고정.

사고: 엔진이 `寅亥合 → 합반(化 불성)·합거 · 壬/甲 흉 제거(유리)`로 판정했는데 답변이
"합을 하여 기신 木의 기운을 더 강하게 만든다"로 정반대 서술을 냈다(절대원칙 1 위반).
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from saju_engines.relation_claim_audit import (
    RelationViolationKind,
    audit_relation_claims,
    canonical_claim_lines,
    dedupe_canonical_claims,
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
    assert "붙잡" not in sem.canonical_claim
    # 보조 강화 — 쉬운 말 '조금 보태 주는 정도'(2026-10-13 개정, 구 '보조적으로 강화').
    assert "조금 보태 주는 정도" in sem.canonical_claim
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
    assert "합거" in patched.text  # 교체본 = 쉬운 말 확정 문장(원어는 괄호 한 번)
    assert audit_relation_claims(patched.text, semantics) == []


def test_canonical_claim_states_engine_verdict(semantics):
    """확정 문장은 엔진 판정(묶임·합거·흉 완화)을 쉬운 말로 그대로 말한다(2026-10-13 개정)."""
    claim = _by_label(semantics, "寅亥合").canonical_claim
    assert "서로 붙잡혀" in claim  # 묶임
    assert "바뀌지는 않고" in claim  # 化 불성
    assert "크게 약해집니다(합거)" in claim  # 합거 = 제거가 아니라 크게 약해짐
    assert "오히려 가벼워집니다" in claim  # 壬(구신)·甲(기신) 억제 = 유리


def test_prompt_uses_canonical_claim_not_only_prohibitions(semantics):
    """생성 전 입력에 확정 문장이 실린다 — 관계 사실은 자유 작문 대상이 아니다."""
    lines = canonical_claim_lines(semantics)
    assert any("관계 확정 문장" in ln for ln in lines)
    assert any("합거" in ln for ln in lines)


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


def test_multi_relation_sentence_is_replaced_with_all_canonical_claims(semantics):
    """한 문장이 여러 관계에 걸리면 임의로 하나를 고르지 않고 **전부의** canonical 문장으로 바꾼다.

    寅은 寅午반합·寅亥合·寅申충·寅巳해에 모두 참여하므로 한 문장이 둘 이상에 걸린다.
    예전엔 이를 모호로 보고 답 전체를 안전 템플릿으로 교체했다(2026-10-02·10-13 실답) —
    문장 하나 때문에 답 전체를 버리지 않도록 결정론 국소 교정으로 바꿨다(2026-10-13 승인).
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
    assert patched.patched_count == 2
    assert patched.ambiguous_sentences == []
    assert patched.multi_patched_sentences == [0]
    assert patched.fully_repaired
    assert patched.outcome is PatchOutcome.PATCHED_MULTI_RELATION
    expected = " ".join(
        s.canonical_claim for s in semantics if s.relation_label in {"寅亥合", "寅午반합"}
    )
    assert patched.text == expected  # semantics 순서로 전부, 임의 선택 없음


def test_sentence_with_unknown_relation_stays_ambiguous(semantics):
    """위반 라벨 중 canonical 문장이 없는 관계가 섞이면 교체본을 확정할 수 없어 모호로 남긴다."""
    from saju_engines.relation_claim_audit import PatchOutcome, RelationClaimViolation

    sentence = "해수(亥水)와 인목(寅木)이 얽혀 木이 강해집니다."
    violations = [
        RelationClaimViolation(
            relation_label=label,
            kind=RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT,
            sentence_index=0, sentence=sentence,
        )
        for label in ("寅亥合", "없는관계合")
    ]
    patched = patch_relation_claims(sentence, violations, semantics)
    assert patched.patched_count == 0
    assert patched.ambiguous_sentences == [0]
    assert patched.outcome is PatchOutcome.AMBIGUOUS_RELATION_FALLBACK
    assert patched.text == sentence


def test_split_sentences_preserves_offsets():
    """문장 분리는 오프셋을 보존해 원문 교체가 정확해야 한다."""
    text = "첫 문장이에요. 둘째 문장입니다.\n셋째 문장!"
    sentences = split_sentences(text)
    assert len(sentences) == 3
    for s in sentences:
        assert text[s.start : s.end] == s.text


# ── 공유 글자 오탐 회귀(2026-10-02 실답 사고) ────────────────────────────────
# 일진 己酉 · 대운 壬辰 · 세운 丙午 · 월운 丁酉 — 酉가 辰酉合·巳酉반합·申酉방합 3관계에
# 동시에 참여한다. "辰酉合은 … 합거입니다"라는 엔진 canonical 문장이 창(±2문장) 안의
# 巳·申 때문에 반합·방합에도 귀속되어 BINDING_ASSERTED_WHEN_NONE 으로, 반합의 '金 보조
# 강화' 문장이 辰酉合(化 불성)에 귀속되어 TRANSFORMATION_ASSERTED_WHEN_NOT 으로 잡혔고,
# 지시를 그대로 따른 답변이 AMBIGUOUS_RELATION_FALLBACK → 안전 템플릿으로 통째 교체됐다.
_SHARED_STEMS = ["己", "壬", "丙", "丁"]
_SHARED_BRANCHES = ["酉", "辰", "午", "酉"]


@pytest.fixture(scope="module")
def shared_semantics():
    """酉 공유 3관계가 동시에 성립하는 2026-10-02 스택의 관계 구조화 의미."""
    from saju_api.services.manse_service import calculate

    chart = calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 10, 2)}))
    sems = collect_luck_relation_semantics(chart, _SHARED_STEMS, _SHARED_BRANCHES)
    assert {s.relation_label for s in sems} >= {"辰酉合", "巳酉반합", "申酉방합"}
    return sems


def test_canonical_claims_verbatim_pass_audit(shared_semantics):
    """엔진이 '그대로 쓰라'고 준 canonical 문장 전체는 감사에 걸리면 안 된다."""
    text = "\n\n".join(s.canonical_claim for s in shared_semantics)
    assert audit_relation_claims(text, shared_semantics) == []


def test_explicitly_named_relation_is_not_attributed_to_shared_member_relations(
    shared_semantics,
):
    """관계를 이름으로 부른 문장은 그 관계에만 귀속한다 — 공유 글자 창 추정 금지."""
    text = (
        "오늘은 己酉(기유) 일진이 들어옵니다. "
        "辰酉合은 이번 판정에서 金으로 합화한 것이 아니라 서로 묶이는 합반이며, "
        "묶인 글자의 작용이 끌려가는 합거입니다. "
        "巳酉반합은 완전한 金국을 이루지는 않았지만 金(한신) 작용을 보조적으로 강화합니다. "
        "申酉방합은 완전한 金국을 이루지는 않았지만 金(한신) 작용을 보조적으로 강화합니다. "
        "그래서 오늘은 결정을 서두르기보다 정리에 집중하면 좋겠어요."
    )
    assert audit_relation_claims(text, shared_semantics) == []


def test_korean_alias_with_kind_suffix_counts_as_explicit_name(shared_semantics):
    """'사유반합'처럼 접미를 살린 한글 통칭도 직접 호칭으로 인정한다."""
    text = "진유합은 합거입니다. 사유반합은 金 작용을 보조적으로 강화합니다."
    assert audit_relation_claims(text, shared_semantics) == []


@pytest.mark.parametrize(
    ("text", "label", "kind"),
    [
        (
            "辰酉合으로 金이 강해져 식상의 기운이 살아납니다.",
            "辰酉合", RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT,
        ),
        (
            "巳酉반합으로 서로 묶여 작용이 둔해집니다.",
            "巳酉반합", RelationViolationKind.BINDING_ASSERTED_WHEN_NONE,
        ),
        (
            "오늘 유금(酉金)이 들어와 진토(辰土)와 합을 하여 금(金) 기운이 강해집니다.",
            "辰酉合", RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT,
        ),
    ],
)
def test_real_reversals_still_caught_after_explicit_name_rule(
    shared_semantics, text, label, kind
):
    """직접 호칭 역전 2건·호칭 없는 창 경로 역전 1건은 수정 후에도 검출된다."""
    violations = audit_relation_claims(text, shared_semantics)
    assert (label, kind) in {(v.relation_label, v.kind) for v in violations}
    assert {v.relation_label for v in violations} == {label}


def test_prompt_header_limits_claim_to_single_citation(semantics):
    """확정 문장 헤더는 '한 번만 인용'을 명시한다(2026-10-12 — 영역별 문단 복사 반복 차단)."""
    header = canonical_claim_lines(semantics)[0]
    assert "한 번만 인용" in header


def test_dedupe_keeps_first_canonical_claim_only(semantics):
    """같은 canonical claim이 두 번 그대로 실리면 첫 출현만 남고 문장 간격은 유지된다."""
    claim = _by_label(semantics, "寅亥合").canonical_claim
    text = f"오늘은 유리한 날이에요. {claim} 일에서는 막힌 것이 풀려요. {claim} 돈은 점검이 맞아요."
    out = dedupe_canonical_claims(text, semantics)
    assert out.count(claim) == 1
    assert out == f"오늘은 유리한 날이에요. {claim} 일에서는 막힌 것이 풀려요. 돈은 점검이 맞아요."
    # 중복이 없으면 원문 byte 그대로.
    assert dedupe_canonical_claims(out, semantics) == out


def test_dedupe_ignores_rephrased_claims(semantics):
    """결과어로 바꿔 받은 문장은 전문 일치가 아니므로 건드리지 않는다."""
    claim = _by_label(semantics, "寅亥合").canonical_claim
    text = f"{claim} 그래서 묶인 글자의 작용이 끌려가는 흐름이 이어져요."
    assert dedupe_canonical_claims(text, semantics) == text


# ── 한글 병기 호칭 정규화(2026-10-12 실답 오귀속) ───────────────────────────────
# '午未(오미) 합'·'巳午未(사오미) 방합'처럼 한자 뒤 괄호 음 병기 + 공백이 끼면 직접 호칭
# 인식이 실패해 공유 글자 관계로 귀속됐다. 2026-10-02 스택(酉 공유 3관계)으로 재현한다.
@pytest.mark.parametrize(
    "text",
    [
        "辰酉(진유) 합은 이번 판정에서 서로 묶이는 합반이며 합거입니다.",
        "巳酉(사유) 반합이 형성되며 金(금)의 기운이 보조적으로 강화됩니다.",
        "申酉(신유)방합으로 金 기운이 강화됩니다.",
    ],
)
def test_annotated_relation_name_counts_as_explicit_name(shared_semantics, text):
    """괄호 병기·공백이 끼어도 호칭된 관계에만 귀속되어 공유 글자 관계 위반이 나지 않는다."""
    assert audit_relation_claims(text, shared_semantics) == []


def test_annotated_name_still_catches_real_reversal(shared_semantics):
    """정규화는 귀속만 바로잡는다 — 호칭된 관계 자체의 역전은 그대로 검출된다."""
    text = "辰酉(진유) 합으로 金이 강해져 식상의 기운이 살아납니다."
    violations = audit_relation_claims(text, shared_semantics)
    assert {(v.relation_label, v.kind) for v in violations} == {
        ("辰酉合", RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT)
    }


# ── 호칭 없는 문장의 창 귀속 좁히기(2026-10-12 데굴님 승인) ────────────────────────
# 2026-10-12 스택 — 대운 壬辰 · 세운 丙午 · 월운 戊戌 · 일진 己未. 午未合이 己 비견·丁 편인을
# 억제(SUPPRESSED)한다. 관계를 말하지 않은 문장('뚜렷해지고'·'집중합니다'·'종합해보면')이
# 한글 1음절 관계 어휘에 걸려 未·己 공유로 午未合에 귀속, STRENGTHEN 위반으로 교체되던 오탐.
_OCT12_STEMS = ["壬", "丙", "戊", "己"]
_OCT12_BRANCHES = ["辰", "午", "戌", "未"]


@pytest.fixture(scope="module")
def oct12_semantics():
    """午未合(합반·합거, 己·丁 억제)이 성립하는 2026-10-12 스택의 관계 구조화 의미."""
    from saju_api.services.manse_service import calculate

    chart = calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 10, 12)}))
    sems = collect_luck_relation_semantics(chart, _OCT12_STEMS, _OCT12_BRANCHES)
    sem = _by_label(sems, "午未合")
    assert any(e.effect is EffectKind.SUPPRESSED and e.target == "己" for e in sem.effects)
    return sems


@pytest.mark.parametrize(
    "text",
    [
        # 실답 오탐 문장 그대로 — '뚜렷해지고'의 '해'가 관계 어휘로 읽혔다.
        "세운 丙午(병오)가 배경에 있습니다. 오늘 유입된 己未(기미) 기운은 당신에게 꼭 필요한 "
        "土(토) 용신의 힘으로, 본인의 주관이 뚜렷해지고 결정권이 강화되는 흐름을 만듭니다.",
        # '집중합니다'·'종합해보면'·'충분히' — 일상 어절.
        "丙午(병오) 세운 속 己未(기미) 일진은 己(기) 비견을 강하게 합니다. 종합해보면 충분히 "
        "좋은 날이니 정리에 집중합니다.",
    ],
)
def test_sentence_without_relation_word_is_not_window_attributed(oct12_semantics, text):
    """관계 어휘가 없는 문장은 공유 글자가 창 안에 있어도 어느 관계에도 귀속되지 않는다."""
    assert audit_relation_claims(text, oct12_semantics) == []


def test_window_path_still_catches_strengthen_of_suppressed_target(oct12_semantics):
    """진짜 관계 어휘('합을 하여')가 있으면 창 경로 귀속과 억제 대상 강화 검출은 유지된다."""
    text = (
        "세운의 午(오화)가 들어옵니다. 일진 未(미토)가 그와 합을 하여 己(기) 비견이 더 "
        "강해지니 주도권이 커집니다."
    )
    violations = audit_relation_claims(text, oct12_semantics)
    assert ("午未合", RelationViolationKind.STRENGTHEN_ASSERTED_WHEN_SUPPRESSED) in {
        (v.relation_label, v.kind) for v in violations
    }


# ── 묶임 어휘의 정당한 지시 대상(2026-10-13 데굴님 승인) ──────────────────────────
# 2026-10-13 스택 — 대운 壬辰 · 세운 丙午 · 월운 戊戌 · 일진 庚申. 巳申合=합거(丙 정인 억제),
# 午戌반합·巳午방합·申戌방합=보조 강화(묶임 없음). 실답: "묶여"가 호칭된 두 방합에 귀속돼
# BINDING_ASSERTED_WHEN_NONE ×2 → 모호 → 답 전체가 안전 템플릿으로 교체.
_OCT13_STEMS = ["壬", "丙", "戊", "庚"]
_OCT13_BRANCHES = ["辰", "午", "戌", "申"]


@pytest.fixture(scope="module")
def oct13_semantics():
    """巳申合(합거·丙 억제)과 巳午방합·申戌방합이 함께 서는 2026-10-13 스택."""
    from saju_api.services.manse_service import calculate

    chart = calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 10, 13)}))
    sems = collect_luck_relation_semantics(chart, _OCT13_STEMS, _OCT13_BRANCHES)
    assert {s.relation_label for s in sems} >= {"巳申合", "巳午방합", "申戌방합"}
    sem = _by_label(sems, "巳申合")
    assert sem.binding_state is BindingState.REMOVED
    assert any(e.effect is EffectKind.SUPPRESSED and e.target == "丙" for e in sem.effects)
    assert _by_label(sems, "巳午방합").binding_state is BindingState.NONE
    return sems


@pytest.mark.parametrize(
    "text",
    [
        # 결과어 '묶여'(巳申合의 丙 억제) + 방합 두 라벨 호칭을 한 문장에 — 실답 오탐 형태.
        "직장에서는 丙 정인이 묶여 있어 서류 확인이 느슨해질 수 있고, 巳午방합·申戌방합이 "
        "보조하는 火·金 기운으로 체력은 받쳐 줘요.",
        "巳午방합과 申戌방합은 火·金 기운을 보조적으로 강화하지만, 丙 정인은 묶여 있어 문서 "
        "운은 기대를 낮추세요.",
        # 한글 음 뒤 한자 병기 — '사신(巳申)합'은 巳申合 직접 호칭이다.
        "사신(巳申)합으로 申과 巳가 묶여 丙 정인의 이로운 작용이 끌려가요. 巳午방합과 "
        "申戌방합은 火·金 기운을 보조해요.",
        # 호칭 없이 구성 글자만으로 巳申合을 받은 결과어 서술.
        "일진 庚申의 申이 시지 巳와 만나 서로 묶이면서 丙 정인의 이로운 작용이 끌려가요. "
        "그래도 午戌·巳午의 火 기운과 申戌의 金 기운이 보조적으로 받쳐 줘요.",
    ],
)
def test_binding_word_with_legit_referent_is_not_attributed_to_unbound_relations(
    oct13_semantics, text
):
    """묶임 판정이 있는 관계(巳申合)의 결과를 받은 '묶여'는 함께 불린 방합의 위반이 아니다."""
    assert audit_relation_claims(text, oct13_semantics) == []


def test_hanja_annotated_korean_name_counts_as_explicit_name(oct13_semantics):
    """'사신(巳申)합'은 巳申合 직접 호칭 — 합거 서술이 다른 관계로 새지 않는다."""
    from saju_engines.relation_claim_audit import _named_relations

    assert _named_relations("사신(巳申)합으로 묶여요.", oct13_semantics) == {"巳申合"}
    assert _named_relations("사신(巳申) 합이 합거예요.", oct13_semantics) == {"巳申合"}


def test_real_binding_reversal_of_unbound_relation_still_caught(oct13_semantics):
    """지시 대상 없이 반합을 묶였다고 쓰면 여전히 위반이다(세운 丙午의 丙 단독 언급은 면책 아님)."""
    text = "세운 丙午의 午와 월운 戌이 午戌반합으로 서로 묶여 火 작용이 둔해집니다."
    violations = audit_relation_claims(text, oct13_semantics)
    assert {(v.relation_label, v.kind) for v in violations} == {
        ("午戌반합", RelationViolationKind.BINDING_ASSERTED_WHEN_NONE)
    }


def test_two_unbound_relations_bound_in_one_sentence_are_both_replaced(oct13_semantics):
    """방합 둘을 한 문장에서 묶였다고 쓰면 두 canonical 문장으로 **그 문장만** 교체된다.

    답 전체를 안전 템플릿으로 바꾸던 예전 경로가 아니다.
    """
    from saju_engines.relation_claim_audit import PatchOutcome

    bad = "巳午방합과 申戌방합이 서로 묶여 작용이 둔해집니다."
    text = f"오늘은 평운이에요. {bad} 서류는 한 번 더 확인하세요."
    violations = audit_relation_claims(text, oct13_semantics)
    assert {v.relation_label for v in violations} == {"巳午방합", "申戌방합"}
    patched = patch_relation_claims(text, violations, oct13_semantics)
    assert patched.outcome is PatchOutcome.PATCHED_MULTI_RELATION
    assert patched.text.startswith("오늘은 평운이에요. ")
    assert patched.text.endswith(" 서류는 한 번 더 확인하세요.")
    assert bad not in patched.text
    for label in ("巳午방합", "申戌방합"):
        assert _by_label(oct13_semantics, label).canonical_claim in patched.text
    assert audit_relation_claims(patched.text, oct13_semantics) == []


# ── 확정 문장 쉬운 말 개정(2026-10-13 데굴님 승인) ────────────────────────────────
# 용어를 모르는 사용자가 읽는 문장 — 판정을 쉬운 말로 먼저, 원어는 괄호로 한 번만.
# 실측 스택 4개(07-27·10-02·10-12·10-13)의 관계 22건 전부에 대해 불변식을 고정한다.
_STACK_FIXTURES = ("semantics", "shared_semantics", "oct12_semantics", "oct13_semantics")
_BAD_JOSA = re.compile(r"[水火土]으로|[木金]로(?![^\s])")


@pytest.mark.parametrize("fixture_name", _STACK_FIXTURES)
def test_plain_canonical_claims_pass_audit_as_a_whole(request, fixture_name):
    """스택의 확정 문장 전부를 한 답에 실어도 감사 위반이 없다(자기 재발동·상호 오귀속 없음)."""
    sems = request.getfixturevalue(fixture_name)
    text = "\n\n".join(s.canonical_claim for s in sems)
    assert audit_relation_claims(text, sems) == []
    # 한 문단에 이어 붙여도(창 경로 ±2문장) 위반이 없다.
    assert audit_relation_claims(" ".join(s.canonical_claim for s in sems), sems) == []


@pytest.mark.parametrize("fixture_name", _STACK_FIXTURES)
def test_plain_canonical_claim_wording_invariants(request, fixture_name):
    """쉬운 말 문장 형태 — 엔진 말투 제거·조사 오류 없음·한글 병기·원어는 괄호 한 번."""
    for sem in request.getfixturevalue(fixture_name):
        claim = sem.canonical_claim
        assert "이번 판정에서" not in claim
        assert not _BAD_JOSA.search(claim), claim
        assert claim.startswith(f"{sem.relation_label}(")  # 라벨 + 한글 음 병기
        for term in ("합거", "합반", "합화"):
            assert claim.count(term) <= 1, claim
        assert "국을 이루" not in claim and "보조적으로 강화" not in claim
        if sem.binding_state is BindingState.NONE:
            assert "붙잡" not in claim and "묶" not in claim, claim
        if sem.transformation_state is not TransformationState.TRANSFORMED:
            assert "바뀝니다" not in claim, claim


def test_plain_claims_for_oct13_incident(oct13_semantics):
    """2026-10-13 사고일 문장 고정 — 합거는 '제거'가 아니라 '크게 약해짐', 역할은 쉬운 말+괄호."""
    claims = {s.relation_label: s.canonical_claim for s in oct13_semantics}
    assert claims["巳申合"] == (
        "巳申合(사신합)은 이번 운에서 두 글자가 서로 붙잡혀, 새로운 水(수) 기운으로 바뀌지는 "
        "않고 붙잡힌 글자의 작용이 크게 약해집니다(합거). 그 대신 丙(병) 정인의 좋은 작용도 "
        "이번에는 힘을 덜 씁니다."
    )
    assert claims["丁壬合"] == (
        "丁壬合(정임합)은 이번 운에서 두 글자가 손을 잡고 木(목) 기운으로 바뀝니다(합화). "
        "이 木 기운은 이 사주에서 부담스러운 기운(기신)입니다."
    )
    assert claims["午戌반합"].startswith(
        "午戌반합(오술반합)은 이번 운에서 세 글자가 모여야 완성되는 조합 중 두 글자만 모여, "
        "火(화) 기운을 조금 보태 주는 정도입니다."
    )
    assert claims["巳午방합"].startswith(
        "巳午방합(사오방합)은 이번 운에서 같은 계절의 글자끼리 모였지만 세 글자가 다 모이지는 않아"
    )
    assert "제거" not in claims["巳申合"]


def test_forbidden_phrases_use_correct_particle(oct13_semantics):
    """금지 해석 문구의 조사 — '水로·火로'(받침 없음), '木으로·金으로'(받침)."""
    joined = " ".join(f for s in oct13_semantics for f in s.forbidden_interpretations)
    assert "水으로" not in joined and "火으로" not in joined
    assert "水로 합화했다고 서술" in joined
    assert "火로 합화했다고 서술" in joined


def test_boon_tail_uses_plain_words(semantics):
    """흉이 눌리는 합거(寅亥合)는 '부담스러운 작용이 오히려 가벼워진다'로 쓴다."""
    claim = _by_label(semantics, "寅亥合").canonical_claim
    assert "그 덕분에 壬(임) 정재·甲(갑) 정관의 부담스러운 작용은 오히려 가벼워집니다." in claim


@pytest.mark.parametrize(
    "text",
    [
        "午戌반합으로 丙 정인이 묶여 火 작용이 둔해집니다.",
        "巳午방합으로 丙 정인이 묶여 있어요.",
        "세운 丙午의 정인 기운은 午戌반합으로 묶여 힘을 잃어요.",
    ],
)
def test_binding_attributed_to_unbound_relation_is_violation_even_with_effect_target(
    oct13_semantics, text
):
    """'丙 정인'을 덧붙여도 묶임을 반합·방합의 작용(…으로 묶여)으로 돌리면 ③ 위반이다.

    2026-10-14 검수 반례.
    """
    kinds = {(v.relation_label, v.kind) for v in audit_relation_claims(text, oct13_semantics)}
    assert kinds, text
    assert all(k is RelationViolationKind.BINDING_ASSERTED_WHEN_NONE for _l, k in kinds)
