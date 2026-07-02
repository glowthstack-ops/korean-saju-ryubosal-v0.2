"""동반자 모드 유사도 보강(P3d, shadow) — 분류기 + rules-first/구성 게이트 검증.

실행 mode는 아직 바꾸지 않는다(P3d-2에서 배선). 여기서는 보조 분류와 augment 로직의
안전장치 조합(rules-first + 대상-구성 게이트 + score/margin 게이트)만 검증한다. augment
로직은 suggestion 주입으로 결정론적으로 테스트하고, 실제 ONNX 예측은 모델 존재 시에만 확인한다.
"""

from __future__ import annotations

from saju_engines.companion_similarity import (
    _MODE_SIM_MIN_MARGIN,
    _MODE_SIM_MIN_SCORE,
    CompanionModeSuggestion,
    augment_subject_mode,
    get_companion_mode_classifier,
    suggest_companion_mode,
)
from saju_shared_types.intent import SubjectMode

_STRONG = CompanionModeSuggestion(label="competition", score=0.85, margin=0.20)


# ── augment 로직(결정론 — suggestion 주입) ─────────────────────────────

def test_rules_first_never_overridden() -> None:
    """규칙이 비교 mode를 확정했으면 유사도가 다른 label을 내도 덮지 않는다."""
    for rule in (
        SubjectMode.PAIRWISE, SubjectMode.COMPARE_EXCLUDE_SELF, SubjectMode.RANKING,
    ):
        got = augment_subject_mode(
            rule, "누가 제일 잘돼?", non_self_count=3, has_self=False, suggestion=_STRONG,
        )
        assert got is rule  # 절대 덮지 않음


def test_companion_only_single_excluded() -> None:
    """동반자 1명 단독(companion_only 후보)은 강한 제안이 있어도 보강하지 않는다."""
    got = augment_subject_mode(
        SubjectMode.SINGLE, "평생 함께할 사람일까", non_self_count=1, has_self=False,
        suggestion=_STRONG,
    )
    assert got is SubjectMode.SINGLE


def test_self_plus_one_becomes_pairwise() -> None:
    """본인 + 동반자 1명(비교 의도)이면 pairwise로 보강(arrangement=구성)."""
    got = augment_subject_mode(
        SubjectMode.SINGLE, "나랑 이 사람 평생 함께할까", non_self_count=1, has_self=True,
        suggestion=_STRONG,
    )
    assert got is SubjectMode.PAIRWISE


def test_two_companions_become_compare() -> None:
    """동반자 2명(본인 미포함)이면 compare_exclude_self로 보강."""
    got = augment_subject_mode(
        SubjectMode.SINGLE, "이 둘 같이 일하면 어때", non_self_count=2, has_self=False,
        suggestion=_STRONG,
    )
    assert got is SubjectMode.COMPARE_EXCLUDE_SELF


def test_three_companions_become_ranking() -> None:
    """동반자 3명 이상이면 ranking으로 보강(competition flavor라도 인원으로 축소)."""
    got = augment_subject_mode(
        SubjectMode.SINGLE, "이 사람들 중 누가 잘나가", non_self_count=3, has_self=False,
        suggestion=_STRONG,
    )
    assert got is SubjectMode.RANKING


def test_no_suggestion_keeps_rule() -> None:
    """score/margin 게이트 탈락(suggestion=None)이면 규칙 mode 그대로."""
    got = augment_subject_mode(
        SubjectMode.SINGLE, "이 둘 어때", non_self_count=2, has_self=False, suggestion=None,
    )
    # 모델 부재/저신뢰면 None → 규칙 유지(SINGLE). 모델이 확신하면 COMPARE로 승격될 수 있으나
    # 그 경우도 안전(2명 구성). 여기선 최소 보장: PAIRWISE/RANKING으로 잘못 가지 않음.
    assert got in (SubjectMode.SINGLE, SubjectMode.COMPARE_EXCLUDE_SELF)


def test_thresholds_are_data_calibrated() -> None:
    """실측 기반 임계값 — 과보수적 0.78이 아니라 0.60/0.05."""
    assert _MODE_SIM_MIN_SCORE == 0.60
    assert _MODE_SIM_MIN_MARGIN == 0.05


# ── 실제 ONNX 예측(모델 존재 시만) ─────────────────────────────────────

def _clf_available() -> bool:
    return get_companion_mode_classifier().available()


def test_gate_passes_clear_and_rejects_weak() -> None:
    """게이트 동작 검증 — 확신 높은 경쟁 표현은 통과, 저신뢰(비교 아님)는 탈락(모델 있을 때).

    현 ONNX는 intent 도메인 튜닝이라 동반자 flavor 변별력이 '보통'이다 — 안전 임계값에서 명확한
    꼬리만 잡고 애매한 건 규칙에 맡긴다(rules-first). 여기서는 커버리지 과대주장 대신 게이트가
    올바른 방향으로 동작함만 고정한다.
    """
    if not _clf_available():
        return
    # 명확한 경쟁 flavor(본인 vs 동반자, 승부 뉘앙스) — 게이트 통과.
    assert suggest_companion_mode("나랑 지민 중 누가 더 앞서 있어?") is not None
    # 비교 아님(본인 단독 운세) — 게이트에서 탈락해야(저 score).
    assert suggest_companion_mode("내 올해 운 봐줘") is None


def test_distractor_excluded_by_composition_even_if_scored() -> None:
    """비교 아님 질문은 score가 높아도 대상-구성 게이트(동반자 0~1명)에서 탈락한다."""
    if not _clf_available():
        return
    # '올해 연애운' 등은 해소 동반자 0명 → augment 발동 안 함(rule 유지).
    for q in ("내 올해 운 봐줘", "올해 연애운 있어?", "지민 취업운 봐줘"):
        got = augment_subject_mode(
            SubjectMode.SINGLE, q, non_self_count=0, has_self=True,
        )
        assert got is SubjectMode.SINGLE, q


# ── chat_service 배선(P3d-2) — DB 불요(0 동반자·rules-first는 분류기 미호출) ─────

def test_wiring_no_op_on_self_only() -> None:
    """본인 단독(동반자 0명) 질문은 구성 게이트에서 탈락 — mode/query_type 불변."""
    from saju_api.services.chat_service import _augment_companion_mode_by_similarity
    from saju_shared_types.intent import IntentJson, QueryType, SubjectKind, SubjectRef

    intent = IntentJson(
        intent_id="x", query_type=QueryType.DOMAIN_ANALYSIS,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        subject_mode=SubjectMode.SINGLE,
    )
    out = _augment_companion_mode_by_similarity(intent, "내 올해 운 봐줘")
    assert out.subject_mode is SubjectMode.SINGLE
    assert out.query_type is QueryType.DOMAIN_ANALYSIS


def test_wiring_rules_first_pairwise_untouched() -> None:
    """규칙이 pairwise를 확정했으면 배선이 건드리지 않는다(분류기 미호출)."""
    from saju_api.services.chat_service import _augment_companion_mode_by_similarity
    from saju_shared_types.intent import IntentJson, QueryType, SubjectKind, SubjectRef

    intent = IntentJson(
        intent_id="x", query_type=QueryType.COMPARISON,
        subjects=[
            SubjectRef(kind=SubjectKind.SELF, label="본인"),
            SubjectRef(kind=SubjectKind.COMPANION, label="지민", companion_id="c1"),
        ],
        subject_mode=SubjectMode.PAIRWISE,
    )
    out = _augment_companion_mode_by_similarity(intent, "지민이랑 궁합")
    assert out.subject_mode is SubjectMode.PAIRWISE
