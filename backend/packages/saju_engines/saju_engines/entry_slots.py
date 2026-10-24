"""진입 시기 두 칸의 엔진 배정 — 성사 가능 달과 움직이는(국면) 달 후보를 결정론으로 나눈다.

채팅·리포트 공용. EMPLOYMENT_HISTORY_CALIBRATION.md §4-6·§4-7(2026-10-24).

배경(실답 thread web-mvm8zqyr): 같은 사건 키(job_gain)의 후보가 결과 방향에 따라 '취업 성사
가능성'(기회·유입)과 '구직·채용 국면'(압박·부담)으로 갈리는데, 두 칸 지시가 "사건 후보가 있는 달을
성사 달로" 라고만 해서 '최대한 빨리' 질문에서 가장 이른 국면 달(2027-02)이 성사 달로 올라갔다. 엔진
점수는 두 턴에서 같았으므로, 배정을 LLM에 맡기지 않고 여기서 확정해 지시문으로 내린다.

두 모드(`SAJU_ENTRY_SLOT_MODE`, §4-7 — 기본값은 정밀도 측정으로 정한다):
- ``trigger``: 성사 가능 달 = 월 단위 진입 후보 중 사건 신호 점수가 `ENTRY_DONE_MIN_SCORE` 이상인
  달. 용기신 방향은 성사 여부가 아니라 **조건 등급**(순조/완화/조건 불리)으로 병기하고, 공망 충발의
  지연은 제외가 아니라 '시점 이연 가능' 주석이다. 움직이는 달 = `ENTRY_MOVE_MIN_SCORE` 이상·하한
  미만. 현대 통설(관성·인성 유입이 '자리가 생기는 때', 용기신은 '결과의 질')과 리포 원칙 "길흉=
  용신·기신, 사건 종류=십성"에 맞춘 모드.
- ``direction``: 성사 달 = 결과 방향 긍정(`result_direction` == positive)·지연 아님·검토월 아님. 그
  밖은 움직이는 달. 2026-10-24 오전 1차 구현(측정 전) — 비교·회귀용으로 보존.

적중률의 정의(데굴님 2026-10-24): **성사 가능하다고 한 달 가운데 실제 성사된 달의 비율(정밀도)**.
모드·임계값은 `scripts/measure_entry_slot_modes.py` 로 실이력에 대고 정밀도로 고른다.

규칙은 순수 함수이며 점수·판정은 바꾸지 않는다(지시문 전용).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from saju_shared_types.event_taxonomy_v2 import result_direction

from .entry_channel import ENTRY_CHANNEL_KEYS

#: 지시문 머리 — 테스트·감사가 이 문자열로 블록 존재를 판정한다.
ENTRY_SLOT_HEADER = "[진입 시기 두 칸 — 엔진 배정]"

#: 배정 모드 — 환경 변수 SAJU_ENTRY_SLOT_MODE(trigger|direction).
ENTRY_SLOT_MODES: tuple[str, ...] = ("trigger", "direction")
_MODE_ENV = "SAJU_ENTRY_SLOT_MODE"
#: 기본 모드·임계값(§4-7 정밀도 측정 2026-10-24: 4명·456달·입사 17건 — 95점 이상 정밀도 6.4%
#: (기저율 3.7%, ×1.72, 재현율 41%) > 85점 4.1%(×1.10) > direction 1.8%(×0.48). 데굴님 기준
#: "성사 가능하다고 한 달 중 실제 성사된 달의 비율"로 95 채택. 표본이 작아 이력이 쌓이면
#: `scripts/measure_entry_slot_modes.py`로 재측정한다).
DEFAULT_ENTRY_SLOT_MODE = "trigger"
#: trigger 모드 — 성사 가능 달 점수 하한(환경 변수 SAJU_ENTRY_DONE_MIN_SCORE 로 재지정 가능).
_DONE_MIN_ENV = "SAJU_ENTRY_DONE_MIN_SCORE"
ENTRY_DONE_MIN_SCORE = 95
#: 움직이는 달 하한(tone_for_score '흐름이 나타날 수 있습니다').
ENTRY_MOVE_MIN_SCORE = 55

#: '가장 빠른 성사' 질문 표지 — 성사 달 후보 중 가장 이른 달로 답하게 한다.
_EARLIEST_RE = re.compile(
    r"최대한\s*빨리|최대한\s*빠[르른를]|가장\s*빠[르른를]|가장\s*빨리|제일\s*빠[르른를]|제일\s*빨리|빨리"
)

#: 지연 타이밍 라벨(direction 표시 문자열에 병기됨).
_DELAY_LABEL = "지연"

#: 조건 등급 문구(trigger 모드) — 용기신 방향의 번역. 성사 여부가 아니라 성사의 질이다.
COND_SMOOTH = "순조"
COND_SOFTENED = "완화(흉신 묶임 — 부담 완화)"
COND_ADVERSE = "조건 불리(처우·강도 주의)"
NOTE_DELAY = "시점 이연 가능(공망 충발 — 달 후반·다음 달로 걸칠 수 있음)"
NOTE_REVIEW = "검토월(계약 유지력 낮음)"
_GRADE_ORDER = {COND_SMOOTH: 0, COND_SOFTENED: 1, COND_ADVERSE: 2}


def resolve_mode(mode: str | None = None) -> str:
    """배정 모드 — 인자 > 환경 변수 > 기본값. 모르는 값은 기본값."""
    m = (mode or os.environ.get(_MODE_ENV) or DEFAULT_ENTRY_SLOT_MODE).strip().lower()
    return m if m in ENTRY_SLOT_MODES else DEFAULT_ENTRY_SLOT_MODE


def resolve_done_min(done_min: int | None = None) -> int:
    """성사 가능 달 점수 하한 — 인자 > 환경 변수 > 기본값."""
    if done_min is not None:
        return int(done_min)
    raw = os.environ.get(_DONE_MIN_ENV, "").strip()
    try:
        return int(raw) if raw else ENTRY_DONE_MIN_SCORE
    except ValueError:
        return ENTRY_DONE_MIN_SCORE


@dataclass(frozen=True)
class EntrySlotAssignment:
    """두 칸 배정 결과 — 기간 라벨은 'YYYY-MM', 시점순."""

    done_periods: list[str] = field(default_factory=list)
    move_periods: list[str] = field(default_factory=list)
    #: 성사 가능 달별 조건 등급·주석(trigger 모드) — 기간 → '순조 · 시점 이연 가능' 등.
    conditions: dict[str, str] = field(default_factory=dict)
    mode: str = DEFAULT_ENTRY_SLOT_MODE
    done_min: int = ENTRY_DONE_MIN_SCORE

    @property
    def earliest_done(self) -> str | None:
        """가장 이른 성사 달 후보(없으면 None)."""
        return self.done_periods[0] if self.done_periods else None

    @property
    def earliest_smooth(self) -> str | None:
        """가장 이른 '순조' 성사 달(trigger 모드; 조건 정보 없으면 None)."""
        for p in self.done_periods:
            if self.conditions.get(p, "").startswith(COND_SMOOTH):
                return p
        return None

    def move_before(self, done: str) -> str | None:
        """성사 달 `done` 앞의 가장 가까운 움직이는 달 후보(없으면 None)."""
        before = [p for p in self.move_periods if p < done]
        return before[-1] if before else None

    def to_state_slots(self) -> dict[str, str]:
        """승계 저장용 두 칸 — {'done': …, 'move': …}(없는 칸 생략)."""
        out: dict[str, str] = {}
        done = self.earliest_done
        if done is None:
            return out
        out["done"] = done
        move = self.move_before(done)
        if move is not None:
            out["move"] = move
        return out


def _is_entry_month(c: object) -> bool:
    key = getattr(c, "event_key", "")
    key_s = getattr(key, "value", None) or str(key)
    return key_s in ENTRY_CHANNEL_KEYS and len(str(getattr(c, "period", ""))) == 7


def _is_delayed(c: object) -> bool:
    timing = getattr(c, "timing", "") or ""
    if (getattr(timing, "value", None) or str(timing)) == "delay":
        return True
    return _DELAY_LABEL in str(getattr(c, "direction", "") or "")


def _quality(c: object) -> str | None:
    q = getattr(c, "quality", None)
    return (getattr(q, "value", None) or str(q)) if q else None


def is_done_candidate(c: object) -> bool:
    """direction 모드의 성사 달 후보 — 결과 방향 긍정 + 지연 아님 + 검토월 아님.

    `quality`(원값)가 있으면 그것으로, 없으면 `direction` 표시 라벨의 '지연' 병기만 본다.
    """
    if getattr(c, "review_month", False):
        return False
    if _is_delayed(c):
        return False
    return result_direction(_quality(c), "active") == "positive"


def is_positive_candidate(c: object) -> bool:
    """결과 방향 긍정(지연·검토월 무관) — 측정 스크립트의 결합 변형용."""
    return result_direction(_quality(c), "active") == "positive"


def condition_grade(c: object) -> str:
    """trigger 모드 조건 등급 — 용기신 방향의 번역 + 지연·검토월 주석."""
    q = _quality(c)
    direction = result_direction(q, "active")
    if direction == "positive":
        grade = COND_SMOOTH
    elif q == "mixed":
        grade = COND_SOFTENED
    elif direction in ("negative", "activation"):
        grade = COND_ADVERSE
    else:
        grade = COND_SMOOTH if not q else COND_SOFTENED
    notes = [grade]
    if _is_delayed(c):
        notes.append(NOTE_DELAY)
    if getattr(c, "review_month", False):
        notes.append(NOTE_REVIEW)
    return " · ".join(notes)


def _merge_condition(prev: str | None, new: str) -> str:
    """같은 달 후보가 여럿이면 등급은 더 나은 쪽(순조>완화>불리), 주석은 합집합."""
    if prev is None:
        return new
    p_parts, n_parts = prev.split(" · "), new.split(" · ")
    grade = min((p_parts[0], n_parts[0]), key=lambda g: _GRADE_ORDER.get(g, 9))
    return " · ".join([grade, *sorted({*p_parts[1:], *n_parts[1:]})])


def assign_entry_slots(
    candidates: Iterable[object], mode: str | None = None, done_min: int | None = None,
) -> EntrySlotAssignment | None:
    """월 단위 진입 후보를 성사 달·움직이는 달 후보로 나눈다. 월 진입 후보가 없으면 None.

    Args:
        candidates: LlmEventCandidate 또는 EventCandidate(V2) — event_key·period·score·quality 를
            읽는다.
        mode: 'trigger' | 'direction'(미지정 시 환경 변수·기본값).
        done_min: trigger 모드 성사 가능 달 점수 하한(미지정 시 환경 변수·기본값).
    """
    m = resolve_mode(mode)
    th = resolve_done_min(done_min)
    done: set[str] = set()
    move: set[str] = set()
    conds: dict[str, str] = {}
    for c in candidates:
        if not _is_entry_month(c):
            continue
        period = str(getattr(c, "period", ""))
        if m == "direction":
            (done if is_done_candidate(c) else move).add(period)
            continue
        score = int(getattr(c, "score", 0))
        if score >= th:
            done.add(period)
            conds[period] = _merge_condition(conds.get(period), condition_grade(c))
        elif score >= ENTRY_MOVE_MIN_SCORE:
            move.add(period)
    if not done and not move:
        return None
    # 같은 달에 성사·국면 후보가 함께 있으면 성사 달로 본다(국면은 그 달의 과정 서술).
    move -= done
    return EntrySlotAssignment(
        done_periods=sorted(done), move_periods=sorted(move),
        conditions={p: conds[p] for p in sorted(conds)}, mode=m, done_min=th,
    )


def is_earliest_question(text: str) -> bool:
    """'최대한 빨리·가장 빠른' 류 질문인가."""
    return bool(text) and _EARLIEST_RE.search(text) is not None


def _fmt(periods: Iterable[str], ganji_by_period: dict[str, str] | None) -> str:
    parts = []
    for p in periods:
        g = (ganji_by_period or {}).get(p, "")
        parts.append(f"{p}({g})" if g else p)
    return "·".join(parts)


def _fmt_done_with_conditions(
    assignment: EntrySlotAssignment, ganji_by_period: dict[str, str] | None,
) -> str:
    parts = []
    for p in assignment.done_periods:
        g = (ganji_by_period or {}).get(p, "")
        cond = assignment.conditions.get(p, "")
        inner = " · ".join(x for x in (g, cond) if x)
        parts.append(f"{p}({inner})" if inner else p)
    return "·".join(parts)


def _directive_direction(
    assignment: EntrySlotAssignment, *, event_ko: str,
    ganji_by_period: dict[str, str] | None, earliest_asked: bool,
) -> str:
    done = assignment.done_periods
    move = assignment.move_periods
    if not done:
        return (
            f"{ENTRY_SLOT_HEADER} 성사 달 후보 없음 — 질문 창 안의 '{event_ko}' 후보는 전부 "
            f"국면·압박·지연 쪽({_fmt(move, ganji_by_period)})이다. 첫 문단에서 '이 창 안에는 "
            "성사 달 후보가 없고 이 달들은 제안·접수·면접이 오가는 움직이는(국면) 달'임을 먼저 "
            "말하고, 성사 달을 지어내지 말 것."
        )
    parts = [
        f"{ENTRY_SLOT_HEADER} 성사 달 후보(결과 방향 긍정): {_fmt(done, ganji_by_period)}",
    ]
    if move:
        parts.append(
            f"/ 움직이는 달 후보(구직·채용 국면·압박·지연·검토월): {_fmt(move, ganji_by_period)}. "
            "국면 후보 달은 제안·접수·면접이 오가는 움직이는 달이지 성사 달이 아니다 — 국면 달을 "
            "성사 달로 세우지 말 것."
        )
    else:
        parts.append("/ 움직이는 달 후보 없음(성사 달 한두 달 앞으로 잡을 것).")
    parts.append("성사 달은 위 성사 달 후보 안에서만 고른다.")
    earliest = assignment.earliest_done
    if earliest_asked and earliest is not None:
        parts.append(
            "'가장 빠른·최대한 빨리' 질문이므로 성사 달은 그중 가장 이른 "
            f"{_fmt([earliest], ganji_by_period)}로 두고, 그보다 이른 국면 달은 움직이는 달로 "
            "서술할 것."
        )
    parts.append(
        "성사 달 후보는 답에서 각각 한 번씩 달 이름을 들어 다룰 것(건너뛰지 말 것). 성사 달 "
        "후보라도 성사를 단정하지 말고 조건·유불리를 함께 말할 것."
    )
    return " ".join(parts)


def _directive_trigger(
    assignment: EntrySlotAssignment, *, event_ko: str,
    ganji_by_period: dict[str, str] | None, earliest_asked: bool,
) -> str:
    done = assignment.done_periods
    move = assignment.move_periods
    if not done:
        return (
            f"{ENTRY_SLOT_HEADER} 성사 가능 달 없음 — 질문 창 안의 '{event_ko}' 사건 신호가 성사 "
            f"기준에 못 미친다(움직이는 달 후보: {_fmt(move, ganji_by_period) or '없음'}). "
            "첫 문단에서 '이 창 안에는 성사 가능 달이 없고 제안·접수·면접이 오가는 움직이는 달만 "
            "있다'고 먼저 말하고, 성사 달을 지어내지 말 것."
        )
    parts = [
        f"{ENTRY_SLOT_HEADER} 성사 가능 달(사건 신호 매우 강함 · 괄호 안은 조건 등급): "
        f"{_fmt_done_with_conditions(assignment, ganji_by_period)}",
    ]
    if move:
        parts.append(
            "/ 움직이는 달(사건 신호는 있으나 성사 기준 미달 — 제안·접수·면접 과정): "
            f"{_fmt(move, ganji_by_period)}."
        )
    else:
        parts.append("/ 움직이는 달 후보 없음(성사 가능 달 한두 달 앞으로 잡을 것).")
    parts.append(
        "성사 달은 위 성사 가능 달 안에서만 고르고, 조건 등급을 반드시 함께 말할 것 — '순조'는 "
        "성사와 조건이 함께 열리는 달, '조건 불리'는 자리는 생기나 처우·강도·실속이 아쉬울 수 있는 "
        "달('성사 가능하나 조건 불리'로 쓰고 불성사·국면으로 격하하지 말 것), '완화'는 흉신이 "
        "합으로 묶여 부담이 줄어든 달. '시점 이연 가능'은 성사가 달 후반이나 다음 달로 걸칠 수 "
        "있다는 뜻이지 안 된다는 뜻이 아니다."
    )
    earliest = assignment.earliest_done
    smooth = assignment.earliest_smooth
    if earliest_asked and earliest is not None:
        line = (
            "'가장 빠른·최대한 빨리' 질문이므로 가장 이른 성사 가능 달은 "
            f"{_fmt([earliest], ganji_by_period)}({assignment.conditions.get(earliest, '')})이다"
        )
        if smooth is not None and smooth != earliest:
            line += (
                f" — 조건까지 순조한 가장 이른 달은 {_fmt([smooth], ganji_by_period)}이니 두 달을 "
                "'가장 빠른 달'과 '조건이 좋은 달'로 나눠 함께 말할 것"
            )
        parts.append(line + ".")
    parts.append(
        "성사 가능 달은 답에서 각각 한 번씩 달 이름을 들어 다룰 것(건너뛰지 말 것). 성사 가능 "
        "달이라도 성사를 단정하지 말 것."
    )
    return " ".join(parts)


def entry_slot_directive(
    assignment: EntrySlotAssignment,
    *,
    event_ko: str,
    ganji_by_period: dict[str, str] | None = None,
    earliest_asked: bool = False,
) -> str:
    """두 칸 배정 지시문 — 모드별 문안(assignment.mode).

    Args:
        assignment: `assign_entry_slots` 결과.
        event_ko: 사건 한글 이름('취업·합격' 등).
        ganji_by_period: 기간 라벨 → 간지(있으면 병기).
        earliest_asked: '최대한 빨리' 질문이면 가장 이른 성사 달 후보를 성사 달로 못박는다.
    """
    fn = _directive_direction if assignment.mode == "direction" else _directive_trigger
    return fn(
        assignment, event_ko=event_ko, ganji_by_period=ganji_by_period,
        earliest_asked=earliest_asked,
    )
