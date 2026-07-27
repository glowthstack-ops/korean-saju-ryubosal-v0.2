"""명시적 진행 사실 추출기 (P2-PROC-2) — rules-first, LLM 미사용.

설계: `doc/v2_2/REVIEW_PROCESS_FACT_PATTERNS.md` §8~9

**축소 개방이다.** 실로그 조사 판정이 INSUFFICIENT라 자료가 있는 도메인만 연다.

    career    Episode hard-fact 어댑터 — 정규식 불필요(구조가 이미 있다)
    move      결정·확정 고정밀 positive 패턴만
    contract  terminal 패턴만 — 닫는 용도
    loan · relationship · selection   패턴 없음(coverage=UNSUPPORTED)

자료 없는 도메인에 추측 패턴을 쓰지 않는다. `user_facts.py`가 2026-07-22에 겪은 실패
(추측 패턴 → 테스터 실문장 4종 전부 미추출)와 같은 조건이기 때문이다.

정밀도 우선 원칙: 애매하면 만들지 않는다. 놓친 사실은 게이트 BYPASS로 기존 동작이
유지되지만, 잘못 만든 사실은 게이트를 부당하게 열어 사건을 과대 서술한다.
"""

from __future__ import annotations

import re

from saju_shared_types.process_fact import (
    EvidenceOrigin,
    ExtractedProcessFact,
    IntentLevel,
    ProcessFact,
    ProcessFamily,
    ProcessStage,
    ProcessStatus,
    SubjectResolution,
)

#: 욕구·계획 표지 — 이 표현이 절에 있으면 진행 사실로 만들지 않는다.
#: "이사를 완료하고 싶어"(C9)·"준비하고 있어"(A11)·"진행해야되는데"(테스터 회귀)가
#: 전부 여기서 걸린다.
_NOT_YET_RE = re.compile(
    r"싶|하려|할까|볼까|생각\s*(?:중|이|해)|고민|예정이|계획|"
    r"준비\s*(?:중|하고)|알아보|해야\s*(?:되|하)|려고"
)

#: 제3자 주어 — 주체가 본인이 아니면 만들지 않는다(fail closed).
_THIRD_PARTY_RE = re.compile(
    r"(?:남편|아내|와이프|아들|딸|엄마|아빠|어머니|아버지|친구|동생|형|누나|언니|오빠)"
    r"(?:이|가|은|는)"
)

#: 과거 시점 표지 — 현재 진행이 아니다.
_PAST_RE = re.compile(r"작년|재작년|예전에|\d+년\s*전")

# ── 도메인별 고정밀 패턴 ─────────────────────────────────────────
# (rule_id, family, stage, status, 패턴)
_RULES: list[tuple[str, ProcessFamily, ProcessStage, ProcessStatus, re.Pattern[str]]] = [
    # move — 날짜가 확정된 경우만 SCHEDULED. 그 외 '결정'은 IN_PROGRESS다.
    # "9월 30일에 이사가 결정되었어"는 날짜가 이삿날인지 결정일인지 모호하므로
    # SCHEDULED로 올리지 않는다(설계 §8-3).
    (
        "MOVE_DATE_FIXED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.SCHEDULED,
        ProcessStatus.ACTIVE,
        re.compile(r"(?:이사\s*날짜|이삿날|입주(?:일|\s*일정))[^.!?\n]{0,12}?(?:확정|잡[혔았])"),
    ),
    (
        "MOVE_DECISION_CONFIRMED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.IN_PROGRESS,
        ProcessStatus.ACTIVE,
        re.compile(r"이사[^.!?\n]{0,10}?(?:결정|확정)(?:되었|됐|했|돼)"),
    ),
    (
        "MOVE_VENDOR_BOOKED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.SCHEDULED,
        ProcessStatus.ACTIVE,
        re.compile(r"이사(?:업체|짐센터)[^.!?\n]{0,10}?(?:예약|계약)(?:했|완료|됐)"),
    ),
    # move terminal — SINGLE_ACTIVE_FAMILY라 키 없이도 기존 진행을 닫는다.
    (
        "MOVE_CANCELLED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.CANCELLED,
        ProcessStatus.TERMINAL,
        re.compile(r"(?:이사|입주)[^.!?\n]{0,12}?(?:취소|무산|엎어)(?:했|됐|되었|짐)"),
    ),
    (
        "MOVE_ABANDONED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.ABANDONED,
        ProcessStatus.TERMINAL,
        re.compile(r"이사(?:\s*계획)?[^.!?\n]{0,10}?(?:접었|포기했|안\s*하기로\s*했)"),
    ),
    (
        "MOVE_COMPLETED",
        ProcessFamily.MOVE_PROCESS,
        ProcessStage.COMPLETED,
        ProcessStatus.TERMINAL,
        re.compile(r"이사[^.!?\n]{0,8}?(?:마쳤|끝냈|완료했)"),
    ),
    # contract — terminal만. 열지 않고 닫는다.
    (
        "CONTRACT_SIGNED",
        ProcessFamily.CONTRACT_PROCESS,
        ProcessStage.COMPLETED,
        ProcessStatus.TERMINAL,
        re.compile(r"계약(?:서)?[^.!?\n]{0,12}?(?:다\s*썼|체결|완료|끝냈|맺었)"),
    ),
    (
        "CONTRACT_CANCELLED",
        ProcessFamily.CONTRACT_PROCESS,
        ProcessStage.CANCELLED,
        ProcessStatus.TERMINAL,
        re.compile(r"계약[^.!?\n]{0,12}?(?:취소|무산|파기|해지)(?:됐|되었|했)"),
    ),
    (
        "CONTRACT_ABANDONED",
        ProcessFamily.CONTRACT_PROCESS,
        ProcessStage.ABANDONED,
        ProcessStatus.TERMINAL,
        re.compile(r"계약[^.!?\n]{0,12}?(?:포기|안\s*하기로)(?:했|함)"),
    ),
]

_SENT_SPLIT_RE = re.compile(r"[.!?\n]+")
_MAX_QUOTE = 80


def _clause(text: str) -> str:
    return text.strip()[:_MAX_QUOTE]


def extract_process_facts(
    text: str, *, turn: int | None = None, subject_id: str | None = "self"
) -> list[ExtractedProcessFact]:
    """발화에서 구조화된 진행 사실을 뽑는다(정밀도 우선).

    Args:
        text: 사용자 발화 원문.
        turn: 발화 턴 번호(supersede 우선순위에 쓰인다).
        subject_id: 화자 본인의 subject id. 제3자 주어가 감지되면 무시하고
            `SubjectResolution.UNKNOWN`으로 남긴다.

    Returns:
        절 단위 추출 결과. 사실을 만들지 않은 경우에도 사유(`skipped_reason`)를
        남겨 오분류를 사후 검증할 수 있게 한다.
    """
    out: list[ExtractedProcessFact] = []
    for order, raw in enumerate(_SENT_SPLIT_RE.split(text)):
        clause = _clause(raw)
        if not clause:
            continue
        for rule_id, family, stage, status, pattern in _RULES:
            if not pattern.search(clause):
                continue
            # terminal 사실은 욕구·계획 표지와 무관하게 유효하다 — "계약 취소하고
            # 싶어"는 걸러야 하지만 "계약 취소됐어"는 완료형이라 위 정규식이 이미
            # 완료 어미를 요구한다. 반면 active는 표지가 하나라도 있으면 만들지 않는다.
            if status is ProcessStatus.ACTIVE and _NOT_YET_RE.search(clause):
                out.append(ExtractedProcessFact(
                    original_text=clause, source_slot="current_turn", rule_id=rule_id,
                    skipped_reason=IntentLevel.PLANNED_OR_INTENDED,
                ))
                continue
            # 과거 사실은 "만들지 않음"이 아니라 "current=False인 사실"이다 —
            # 모델에 이미 축이 있으므로 사유를 뭉개지 않고 그대로 남긴다.
            is_current = not _PAST_RE.search(clause)
            third_party = bool(_THIRD_PARTY_RE.search(clause))
            out.append(ExtractedProcessFact(
                original_text=clause,
                source_slot="current_turn",
                rule_id=rule_id,
                normalized_fact=ProcessFact(
                    fact_id=f"{rule_id}:{turn or 0}:{len(out)}",
                    subject_id=None if third_party else subject_id,
                    subject_resolution=(
                        SubjectResolution.UNKNOWN if third_party
                        else SubjectResolution.RESOLVED
                    ),
                    process_family=family,
                    stage=stage,
                    status=status,
                    evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
                    original_text=clause,
                    rule_id=rule_id,
                    source_turn=turn,
                    source_order=order,
                    current=is_current,
                ),
            ))
            break  # 한 절에서 규칙 하나만 — 중복 사실 생성 방지
    return out
