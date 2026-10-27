"""층위 라벨 정합 — 관계 확정 문장 참여 글자 라벨 + 생성 후 층위 라벨 감사(2026-10-25 데굴님 승인).

실답('올해 운세', 1980-11-22 명식, 대운 壬辰·세운 丙午): LLM 이 丁壬合을 "대운의 壬와 세운의 丁"으로
썼다 — 세운에 丁은 없고 실제는 원국 월간 丁 × 대운 壬. 생성 전 `[관계 확정 문장]`에 참여 글자 층위를
붙이고(`layer_labels.participants_label`), 생성 후 잘못 붙은 층위어를 실제 자리로 바로잡는다
(`layer_label_audit.audit_layer_labels`).
"""

from __future__ import annotations

from datetime import date

import saju_api.services.chat_service as cs
from saju_engines.conversation_store import ConversationStore
from saju_engines.layer_label_audit import audit_layer_labels
from saju_engines.layer_labels import (
    luck_layers_of,
    natal_label,
    natal_positions_of,
    participants_label,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.relation_semantics import RelationOccurrence

_TODAY = date(2026, 10, 25)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울",
    gender="male", reference_date="2026-10-25",
)
_STACK = {"대운": "壬辰", "세운": "丙午"}
_NATAL = {"year": "庚申", "month": "丁亥", "day": "己亥", "hour": "己巳"}


# ── 라벨 SSOT ──────────────────────────────────────────────────────────────


def test_natal_label_distinguishes_stem_and_branch() -> None:
    assert natal_label("month", "丁") == "원국 월간"
    assert natal_label("month", "亥") == "원국 월지"
    assert natal_label("hour", "巳") == "원국 시지"
    assert natal_label("unknown", "丁") == "원국"


def test_luck_layers_and_natal_positions_respect_stem_branch_slot() -> None:
    assert luck_layers_of("壬", _STACK) == ["대운"]
    assert luck_layers_of("午", _STACK) == ["세운"]
    assert luck_layers_of("丁", _STACK) == []
    # 己는 일간·시간 두 자리 — 모호
    assert natal_positions_of("己", _NATAL) == ["day", "hour"]
    assert natal_positions_of("亥", _NATAL) == ["month", "day"]
    assert natal_positions_of("丁", _NATAL) == ["month"]


def test_participants_label_from_occurrences() -> None:
    occ = [
        RelationOccurrence(char="丁", position="month"),
        RelationOccurrence(char="壬", position="luck"),
    ]
    assert participants_label(occ, _STACK) == "원국 월간 丁 + 대운 壬"
    assert participants_label(occ, None) == "원국 월간 丁 + 운 壬"  # 스택 없으면 '운'
    assert participants_label([], _STACK) == ""


# ── 생성 전: 관계 확정 문장 ────────────────────────────────────────────────


def test_canonical_claim_lines_carry_layer_labels_from_stack() -> None:
    """플래그 무관 — 운 스택(대운 壬辰·세운 丙午) 관계 의미에 참여 글자 층위 라벨이 붙는다."""
    from saju_api.services.chat_service import calculate
    from saju_engines.relation_claim_audit import canonical_claim_lines
    from saju_engines.relation_semantics import collect_luck_relation_semantics

    chart = calculate(_BIRTH)
    sems = collect_luck_relation_semantics(chart, ["壬", "丙"], ["辰", "午"])
    lines = canonical_claim_lines(sems, stack_ganji=_STACK)
    head = "- 丁壬合 [원국 월간 丁 + 대운 壬]: 丁壬合(정임합)은"
    assert any(ln.startswith(head) for ln in lines), lines
    assert "원국 월간 丁을 '세운의 丁'이라 쓰지 말 것" in lines[0]
    # 스택 없이 호출하면 운 글자는 '운 壬'
    assert any("[원국 월간 丁 + 운 壬]" in ln for ln in canonical_claim_lines(sems))


def test_yearly_prompt_canonical_claims_carry_layer_labels() -> None:
    """실답 경로(dry-run) — 관계 의미 패치·계층 플래그 중 하나가 켜진 환경에서만 확정 문장이
    실린다."""
    import pytest

    from saju_engines import period_v2_config as c

    if not (c.RELATION_SEMANTIC_PATCH_ENABLED or c.PERIOD_HIERARCHY_ENABLED):
        pytest.skip("관계 의미 패치·계층 블록 OFF 환경(pytest 기준선)")
    r = cs.chat(
        _BIRTH, "올해 운세를 알려줘", _TODAY, dry_run=True, store=ConversationStore(), owner_id="t",
    )
    assert r.status == "dry_run", r.answer
    p = r.prompt_preview or ""
    assert "- 丁壬合 [원국 월간 丁 + 대운 壬]: 丁壬合(정임합)은" in p
    assert "- 巳午방합 [원국 시지 巳 + 세운 午]:" in p
    assert "원국 월간 丁을 '세운의 丁'이라 쓰지 말 것" in p


# ── 생성 후: 층위 라벨 감사 ────────────────────────────────────────────────


def test_mislabelled_layer_is_rewritten_to_true_position() -> None:
    ans = (
        "대운의 壬(임수)와 세운의 丁(정화)가 합을 하여 木의 기운을 만듭니다. "
        "특히 대운 壬(임수)와 세운 丙(병화)의 충돌은 자극제가 됩니다."
    )
    out = audit_layer_labels(ans, _STACK, _NATAL)
    assert out.fixes == ["세운의 丁→원국 월간 丁(정화)"]
    assert "원국 월간 丁(정화)가 합을" in out.text
    assert "대운의 壬(임수)" in out.text and "세운 丙(병화)" in out.text  # 맞는 표기는 불변


def test_ambiguous_char_drops_layer_word_only() -> None:
    out = audit_layer_labels("세운의 己(기토)가 흔들립니다.", _STACK, _NATAL)  # 己는 일간·시간
    assert out.text == "己(기토)가 흔들립니다."
    assert out.fixes == ["세운의 己→己(기토)"]
    out2 = audit_layer_labels("월운 亥가 들어옵니다.", {**_STACK, "월운": "己亥"}, _NATAL)
    assert out2.fixes == []  # 월운 己亥의 亥 — 맞는 표기


def test_unknown_char_and_full_ganji_are_left_alone() -> None:
    s = "세운의 甲은 보이지 않고, 세운 丙午 자체는 뜨겁습니다. 대운 壬辰(임진)도 그렇습니다."
    out = audit_layer_labels(s, _STACK, _NATAL)
    assert out.text == s and out.fixes == []
    assert audit_layer_labels("아무 층위어 없음", {}, _NATAL).fixes == []


def test_ilun_word_maps_to_iljin_layer() -> None:
    out = audit_layer_labels("일운의 丁이 움직입니다.", {**_STACK, "일진": "丁卯"}, _NATAL)
    assert out.fixes == []  # 일진 丁卯의 丁 — 맞음
    out2 = audit_layer_labels("일운의 丁이 움직입니다.", _STACK, _NATAL)
    assert out2.text == "원국 월간 丁이 움직입니다."
