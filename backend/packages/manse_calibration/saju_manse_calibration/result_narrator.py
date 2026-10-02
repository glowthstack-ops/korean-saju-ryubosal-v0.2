"""검증 결과 사용자용 설명(CAL-P3, 2026-09-21 데굴님 승인) — 템플릿 문장만 조립한다.

`CalibrationResult.explanation`(내부 진단: 모델 type·gap 수치)은 그대로 두고, 사용자에게는
①판정 근거 한 줄(일치 n/m) ②용희기구 역할의 의미 ③애매할 때 다음 행동 세 문장만 보여준다.
즉석 작문·명리 규칙 추가 없음 — 역할 의미는 용희기구한 정의(canonical)의 일반 문구다.
"""

from __future__ import annotations

from saju_shared_types.calibration import CalibrationQuestion, FeedbackAnswer
from saju_shared_types.yongsin import YongsinCandidateModel

_ROLE_MEANING = (
    "용신 {y}=나를 안정시키고 채워 주는 기운 · 희신 {h}=용신을 돕는 기운 · "
    "기신 {g}=부담을 주는 기운 · 구신 {gu}=그 부담을 키우는 기운"
)


def _answered_base(questions: list[CalibrationQuestion], answers: dict[str, FeedbackAnswer],
                   probe_types: frozenset[str]) -> tuple[int, int]:
    """기본(판별) 문항 수와 그중 유효 응답이 있는 문항 수."""
    base = [q for q in questions if q.question_type not in probe_types]
    answered = 0
    for q in base:
        a = answers.get(q.id)
        if a is None:
            continue
        has_event = any(
            v not in ("unknown", "na", "not_occurred") for v in a.event_ratings.values()
        )
        has_domain = any(
            v not in ("unknown", "no_domain_activity") for v in a.domain_ratings.values()
        )
        if has_event or has_domain or a.overall_rating != "unknown":
            answered += 1
    return len(base), answered


def narrate(
    status: str,
    model: YongsinCandidateModel | None,
    hits: int,
    totals: int,
    questions: list[CalibrationQuestion],
    answers: dict[str, FeedbackAnswer],
    probe_types: frozenset[str],
    *,
    close_gap: bool = False,
) -> list[str]:
    """상태별 사용자 문장 — 확정/유력/불확실."""
    n_base, n_answered = _answered_base(questions, answers, probe_types)
    out: list[str] = []
    if model is None or totals == 0:
        out.append(
            "유효한 답이 없어 용신을 확정하지 못했어요. 각 해의 '실제 사건 · 결과'를 골라 주세요."
        )
        if n_base:
            out.append(f"판별 문항 {n_base}개 중 {n_answered}개만 답하셨어요.")
        return out
    y = model.yongsin or "-"
    if status == "calibrated":
        out.append(
            f"답하신 {totals}개 중 {hits}개가 '{y} 기운이 도움이 된다'는 해석과 맞았어요 → "
            f"용신 {y}(으)로 확정했어요."
        )
    elif status == "probable":
        out.append(
            f"답하신 {totals}개 중 {hits}개가 '{y} 기운이 도움이 된다'는 해석과 맞았어요. "
            + ("다른 후보와 차이가 크지 않아 " if close_gap else "근거가 조금 부족해 ")
            + f"'유력'으로 두었어요 — 용신 {y}."
        )
    else:
        out.append(
            f"답과 후보 해석이 엇갈려요(일치 {hits}/{totals}). 지금 후보로는 확정하지 못했고, "
            "다른 후보가 맞을 수 있어요."
        )
    if status != "uncertain":
        out.append(_ROLE_MEANING.format(
            y=y, h=model.heesin or "-", g=model.gisin or "-", gu=model.gusin or "-",
        ))
    if status != "calibrated":
        if n_answered < n_base:
            out.append(
                f"판별 문항 {n_base}개 중 {n_answered}개만 답하셨어요 — 남은 문항의 "
                "'실제 사건 · 결과'를 고르면 확정에 가까워져요."
            )
        else:
            out.append(
                "문항을 다 답하셨어요. 기억이 더 또렷한 해가 있다면 '검증 다시 진행'으로 답을 고쳐 "
                "보세요."
            )
    return out
