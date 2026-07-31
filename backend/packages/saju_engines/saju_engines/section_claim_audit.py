"""섹션 금지 주장 감사 — 좁은 구조화 claim만 (2026-07-30 데굴님 확정).

P1 섹션 증거 라우팅에서 일부 섹션은 **근거가 보장하지 않는 주장**을 하면 안 된다.

    W-05   `windfall` 후보를 근거로 **상속 시기**를 말할 수 없다.
    RL-05  이동 위험을 근거로 **계약 하자·법적 분쟁 발생 시기**를 말할 수 없다.

두 주장만 배포 전 결정적으로 차단한다. 광범위한 단어 정규식은 만들지 않는다 —
'수입 증가로 단정하기 어렵다' 같은 안전 문장이 `수입` 때문에 오탐되기 때문이다.
판정 범위는 `relation_claim_audit.sentence_asserts` 와 **다르다.** 그쪽은 직후 12자
창을 보는데, 여기서 막아야 하는 문장은 "2028년 11월을 상속 시기로 단정할 수는
없습니다" 처럼 부정이 **문장 끝**에 온다(실측 오탐). 관계 감사의 좁은 창은 과다
억제를 막기 위한 것이고, 시기 단정 감사는 문장 잔여 전체에서 부정·유보를 봐야 한다.
그래서 문장 분리(`split_sentences`)는 공유하고 부정 판정만 이 모듈에서 정의한다.

이 모듈은 새 LLM 호출을 만들지 않는다. 위반 문장을 특정해 호출부의 기존
deterministic patch → safe fallback 경로가 처리하게 한다.
"""

from __future__ import annotations

import re
import threading as _threading
from dataclasses import dataclass

from .relation_claim_audit import split_sentences

# ── claim ID (승인 표 — `_timing` / `_occurrence` 를 이름에 명시) ──────────
CLAIM_INHERITANCE_TIMING = "inheritance_timing"
CLAIM_INHERITANCE_OCCURRENCE = "inheritance_occurrence"
CLAIM_CONTRACT_DEFECT_OCCURRENCE = "contract_defect_occurrence"
CLAIM_LEGAL_DISPUTE_TIMING = "legal_dispute_timing"
CLAIM_LEGAL_DISPUTE_OCCURRENCE = "legal_dispute_occurrence"
CLAIM_INCOME_INCREASE_TIMING = "income_increase_timing"
CLAIM_EXPENDITURE_INCREASE_TIMING = "expenditure_increase_timing"
CLAIM_ASSET_ACQUISITION_TIMING = "asset_acquisition_timing"
CLAIM_SETTLEMENT_TIMING = "settlement_timing"
CLAIM_DEBT_REPAYMENT_TIMING = "debt_repayment_timing"

# 대운 합화 배경 claim(2026-07-31) — 배경은 **이미 선택된** 사건의 체감 서술이다.
# 감사(DW-HWA)에서 발생·선정 관여 근거가 입증되지 않았으므로, 배경을 발생·순위·시점
# 선정·성사와 연결하는 서술은 근거 없는 인과 주장이 된다.
CLAIM_BG_OCCURRENCE_SUPPORT = "occurrence_support"
CLAIM_BG_OCCURRENCE_CAUSE = "occurrence_cause"
CLAIM_BG_RANKING_CAUSE = "ranking_cause"
CLAIM_BG_TIMING_SELECTION_CAUSE = "timing_selection_cause"
CLAIM_BG_EVENT_FAMILY_SUPPORT = "event_family_support"

#: 대운 배경 관련 금지 claim 묶음.
DAEWOON_HWA_FORBIDDEN_CLAIMS = frozenset({
    CLAIM_BG_OCCURRENCE_SUPPORT, CLAIM_BG_OCCURRENCE_CAUSE,
    CLAIM_BG_RANKING_CAUSE, CLAIM_BG_TIMING_SELECTION_CAUSE,
    CLAIM_BG_EVENT_FAMILY_SUPPORT,
})

#: 허용 claim — 차단 대상이 아니라 **대조군**이다. 판정기가 이쪽을 잡으면 오탐이다.
#: (체감 부담·완화·장기 배경 서술)
CLAIM_BG_EXPERIENCED_PRESSURE = "experienced_pressure"
CLAIM_BG_EXPERIENCED_MITIGATION = "experienced_mitigation"
CLAIM_BG_LONG_TERM_BACKGROUND = "long_term_background"
DAEWOON_HWA_ALLOWED_CLAIMS = frozenset({
    CLAIM_BG_EXPERIENCED_PRESSURE, CLAIM_BG_EXPERIENCED_MITIGATION,
    CLAIM_BG_LONG_TERM_BACKGROUND,
})

#: 이번 배포에서 **결정적으로** 차단하는 claim.
HARD_BLOCKED_CLAIMS = frozenset({
    CLAIM_INHERITANCE_TIMING, CLAIM_INHERITANCE_OCCURRENCE,
    CLAIM_CONTRACT_DEFECT_OCCURRENCE,
    CLAIM_LEGAL_DISPUTE_TIMING, CLAIM_LEGAL_DISPUTE_OCCURRENCE,
    *DAEWOON_HWA_FORBIDDEN_CLAIMS,
})
#: 탐지 정확도가 확보되지 않아 **프롬프트 지시만** 하는 claim. 억지 정규식을 만들어
#: 안전 문장을 오탐하는 것보다 낫다 — 상태를 숨기지 않고 분리해 둔다.
DIRECTIVE_ONLY_CLAIMS = frozenset({
    CLAIM_INCOME_INCREASE_TIMING, CLAIM_EXPENDITURE_INCREASE_TIMING,
    CLAIM_ASSET_ACQUISITION_TIMING, CLAIM_SETTLEMENT_TIMING,
    CLAIM_DEBT_REPAYMENT_TIMING,
})

#: 부정·유보 표지 — 주장 뒤 **문장 잔여**에 있으면 단정으로 보지 않는다. 오탐(안전
#: 문장 차단)이 미탐보다 해롭다는 판단에 따른 범위다.
_HEDGE = re.compile(r"않|아니|없|못|어렵|힘들|단정|말아|삼가|제한적|확정할 수")

#: 시기 표현이 함께 있어야 '시기 주장' 이다. 일반 설명은 차단 대상이 아니다.
_TIMING = re.compile(
    r"(20\d\d\s*년|20\d\d-\d\d|\d{1,2}\s*월|올해|내년|다음\s*달|이번\s*달"
    r"|상반기|하반기|분기)"
)

#: 사건 어휘.
_EVENT_INHERITANCE = re.compile(r"상속|유산|증여")
_EVENT_CONTRACT_DEFECT = re.compile(r"계약|하자")
_EVENT_LEGAL_DISPUTE = re.compile(r"분쟁|소송|고소|고발|법정")

#: **발생** 주장 동사. 사건 어휘만으로는 부족하다 — "상속 구조가 있습니다" 는 구조
#: 설명이고 발생 단정이 아니다.
_OCCURS = re.compile(
    r"발생|생기|생길|생깁|터지|터질|깨지|깨질|들어오|들어올|받게|이어지|이어질"
    r"|이루어|성립|벌어지|벌어질|문제가"
)

#: `_timing` claim — 사건 어휘 + **시기 표현**이 같은 문장에 있고 부정되지 않을 때.
_TIMING_CLAIMS: dict[str, re.Pattern[str]] = {
    CLAIM_INHERITANCE_TIMING: _EVENT_INHERITANCE,
    CLAIM_LEGAL_DISPUTE_TIMING: _EVENT_LEGAL_DISPUTE,
}

#: `_occurrence` claim — **시기 표현이 없어도** 발생 단정이면 차단한다. 이름과 판정을
#: 일치시킨 것이다(2026-07-30 데굴님 지적: occurrence 가 시기를 요구하면 불일치).
_OCCURRENCE_CLAIMS: dict[str, re.Pattern[str]] = {
    CLAIM_INHERITANCE_OCCURRENCE: _EVENT_INHERITANCE,
    CLAIM_CONTRACT_DEFECT_OCCURRENCE: _EVENT_CONTRACT_DEFECT,
    CLAIM_LEGAL_DISPUTE_OCCURRENCE: _EVENT_LEGAL_DISPUTE,
}
# ── 대운 배경 claim(2026-07-31) ─────────────────────────────────────────
#
# "대운이 좋다/나쁘다" 같은 일반 서술은 막지 않는다. 배경을 **발생·선정·성사와 연결하는
# 인과 술어**만 잡는다 — 넓게 잡으면 허용된 체감 서술("부담을 키우는 배경")까지 걸린다.
# 그래서 모든 패턴이 '배경 주어 + 인과/선정 술어' 두 조건을 함께 요구한다.

#: 배경 주어 — 이 말이 없으면 배경에 대한 주장이 아니다.
_BG_SUBJECT = re.compile(r"대운|化神|화신|장기\s*배경|이\s*배경|배경\s*때문")

#: 인과 연결.
_CAUSAL = re.compile(r"때문|탓에|덕분|으로\s*인해|로\s*인해|영향으로|영향\s*때문")
#: 지지·뒷받침.
_SUPPORTS = re.compile(r"지지|뒷받침|받쳐\s*주|근거가\s*된|힘을\s*실")
#: 대표 선정·순위.
_SELECTION = re.compile(
    # '대표 시점으로 끌어올렸다' 처럼 사이에 말이 끼는 형태까지 — 다만 문장을 건너뛰지
    # 않도록 짧은 창으로 제한한다.
    r"대표[^.\n]{0,12}?(?:끌어\s*올|선정|선택|뽑|골라|꼽|올렸|올라)"
    r"|(?:달|시기|시점|월)이\s*(?:대표|선정|선택)"
    r"|순위를?\s*(?:끌어|올|높)"
    r"|우선순위"
)
#: 성사 가능성.
_LIKELIHOOD = re.compile(r"(?:가능성|확률)을?\s*(?:높|키우|올리|끌어)|성사\s*(?:가능성|확률)")
#: 사건 종류.
_EVENT_FAMILY = re.compile(r"사건\s*(?:종류|유형)|이런\s*(?:종류의\s*)?사건|이\s*유형의")

#: 배경 전용 발생 술어 — 기존 `_OCCURS`(상속·분쟁 claim 공용)는 건드리지 않는다.
#: 거기에 '나타나' 를 더하면 "상속 구조가 나타납니다" 같은 구조 설명까지 발생 단정이 된다.
_BG_OCCURS = re.compile(_OCCURS.pattern + r"|나타나|나타날|나타납|불러오|초래")


def _bg_claim(sentence: str, *others: re.Pattern[str]) -> bool:
    """배경 주어 + 나머지 조건이 **모두** 한 문장에 있고 부정되지 않았는가."""
    if not _BG_SUBJECT.search(sentence):
        return False
    return all(_asserted(p, sentence) for p in others)


def _detect_daewoon_hwa_claims(sentence: str) -> list[str]:
    """문장에서 금지 배경 claim 을 찾는다. 허용 서술은 걸리지 않아야 한다."""
    out: list[str] = []
    if _bg_claim(sentence, _SUPPORTS, _BG_OCCURS):
        out.append(CLAIM_BG_OCCURRENCE_SUPPORT)
    if _bg_claim(sentence, _CAUSAL, _BG_OCCURS):
        out.append(CLAIM_BG_OCCURRENCE_CAUSE)
    if _bg_claim(sentence, _SELECTION):
        # 순위·대표 선정 — 시점 표현이 함께면 시점 선정으로 본다.
        out.append(
            CLAIM_BG_TIMING_SELECTION_CAUSE if _TIMING.search(sentence)
            else CLAIM_BG_RANKING_CAUSE
        )
    if _bg_claim(sentence, _LIKELIHOOD):
        out.append(CLAIM_BG_OCCURRENCE_SUPPORT)
    if _bg_claim(sentence, _EVENT_FAMILY, _SUPPORTS):
        out.append(CLAIM_BG_EVENT_FAMILY_SUPPORT)
    return out


_CLAIM_PATTERNS: dict[str, re.Pattern[str]] = {**_TIMING_CLAIMS, **_OCCURRENCE_CLAIMS}


def _asserted(pattern: re.Pattern[str], sentence: str) -> bool:
    """문장이 그 주장을 **단정**하는가.

    주장 어휘 뒤 문장 잔여에 부정·유보 표지가 있으면 단정으로 보지 않는다. 고정 길이
    창을 쓰지 않는 이유는 한국어 부정이 문장 끝에 오기 때문이다.
    """
    for m in pattern.finditer(sentence):
        if not _HEDGE.search(sentence[m.end():]):
            return True
    return False


@dataclass(frozen=True)
class SectionClaimPolicy:
    """섹션이 할 수 있는/할 수 없는 주장. 사건 판정 규칙이 아니다."""

    section_id: str
    allowed_claims: frozenset[str] = frozenset()
    forbidden_claims: frozenset[str] = frozenset()

    def hard_blocked(self) -> frozenset[str]:
        """이 정책에서 **결정적으로** 차단되는 claim(탐지기가 있는 것만).

        directive-only claim 을 차단됐다고 계상하지 않는다 — 상태 과대 보고 방지.
        """
        return frozenset(self.forbidden_claims) & HARD_BLOCKED_CLAIMS

    def directive_only(self) -> frozenset[str]:
        """지시로만 막는 claim — 감사가 잡지 못한다는 사실을 드러낸다."""
        return frozenset(self.forbidden_claims) & DIRECTIVE_ONLY_CLAIMS


@dataclass(frozen=True)
class ClaimViolation:
    """위반 1건 — 문장을 특정해 호출부가 교체·폴백할 수 있게 한다."""

    claim_id: str
    sentence_index: int
    start: int
    end: int
    sentence: str


def audit_section_claims(
    text: str, policy: SectionClaimPolicy
) -> tuple[ClaimViolation, ...]:
    """금지 주장이 **시기와 함께** 단정됐는지 문장 단위로 감사한다.

    Args:
        text: 생성된 섹션 본문.
        policy: 섹션 claim 정책.

    Returns:
        위반 목록(문장 오프셋 포함). 위반이 없으면 빈 튜플.

    Note:
        시기 표현이 없는 일반 서술("상속 구조가 있는 사주입니다")은 위반이 아니다 —
        차단 대상은 근거 없는 **시기 단정**이다.
    """
    blocked = policy.hard_blocked()
    if not blocked or not text.strip():
        return ()
    out: list[ClaimViolation] = []
    bg_blocked = blocked & DAEWOON_HWA_FORBIDDEN_CLAIMS
    for sent in split_sentences(text):
        has_timing = bool(_TIMING.search(sent.text))
        # 대운 배경 claim 은 사건 어휘가 아니라 '배경 주어 + 인과/선정 술어' 조합으로
        # 판정하므로 `_CLAIM_PATTERNS` 단일 정규식 경로에 들어가지 않는다.
        if bg_blocked:
            for claim_id in sorted(set(_detect_daewoon_hwa_claims(sent.text)) & bg_blocked):
                out.append(ClaimViolation(
                    claim_id=claim_id, sentence_index=sent.index,
                    start=sent.start, end=sent.end, sentence=sent.text.strip(),
                ))
        for claim_id in sorted(blocked - DAEWOON_HWA_FORBIDDEN_CLAIMS):
            pattern = _CLAIM_PATTERNS[claim_id]
            if claim_id in _TIMING_CLAIMS:
                # 시기 단정 — 사건 어휘와 시기 표현이 **같은 문장**에 있어야 한다.
                hit = has_timing and _asserted(pattern, sent.text)
            else:
                # 발생 단정 — 시기 표현은 필요하지 않다. 발생 동사가 있어야 한다.
                hit = _asserted(pattern, sent.text) and bool(
                    _OCCURS.search(sent.text)
                )
            if hit:
                out.append(ClaimViolation(
                    claim_id=claim_id, sentence_index=sent.index,
                    start=sent.start, end=sent.end, sentence=sent.text.strip(),
                ))
    return tuple(out)


#: 섹션 claim 정책 — evidence 정책과 **분리**한다(무엇을 쓰는가 ↔ 무엇을 말할 수 있는가).
#: 키는 정책 ID다 — evidence 정책이 claim 문자열을 직접 갖지 않게 하려는 것이다.
CLAIM_POLICY_WEALTH_BROAD = "wealth_broad_change"
CLAIM_POLICY_WINDFALL_ONLY = "windfall_only"
CLAIM_POLICY_RELOCATION_CHECK = "relocation_contract_check"

SECTION_CLAIM_POLICIES: dict[str, SectionClaimPolicy] = {
    CLAIM_POLICY_WEALTH_BROAD: SectionClaimPolicy(
        section_id="W-04",
        allowed_claims=frozenset({
            "wealth_change_timing", "wealth_variability",
            "financial_decision_attention",
        }),
        forbidden_claims=frozenset(DIRECTIVE_ONLY_CLAIMS),
    ),
    CLAIM_POLICY_WINDFALL_ONLY: SectionClaimPolicy(
        section_id="W-05",
        allowed_claims=frozenset({
            "windfall_signal_present", "windfall_signal_limited", "windfall_timing",
        }),
        forbidden_claims=frozenset({
            CLAIM_INHERITANCE_TIMING, CLAIM_INHERITANCE_OCCURRENCE,
        }),
    ),
    CLAIM_POLICY_RELOCATION_CHECK: SectionClaimPolicy(
        section_id="RL-05",
        allowed_claims=frozenset({
            "relocation_volatility", "relocation_burden",
            "contract_terms_check", "cost_schedule_exit_check",
        }),
        forbidden_claims=frozenset({
            CLAIM_CONTRACT_DEFECT_OCCURRENCE,
            CLAIM_LEGAL_DISPUTE_TIMING, CLAIM_LEGAL_DISPUTE_OCCURRENCE,
        }),
    ),
}


def claim_directive(policy: SectionClaimPolicy) -> str:
    """프롬프트에 넣을 허용·금지 주장 지시. 감사와 같은 정책에서 생성한다."""
    if not policy.forbidden_claims:
        return ""
    parts = [
        "[주장 범위 — 이 섹션의 근거가 보장하는 범위]",
    ]
    if policy.allowed_claims:
        parts.append("허용: " + ", ".join(sorted(policy.allowed_claims)))
    parts.append(
        "금지: " + ", ".join(sorted(policy.forbidden_claims))
        + " — 해당 사건 근거가 없으므로 그 내용을 시기와 함께 단정하지 말 것. "
        "대응·점검 조언은 가능하나 사건 발생 예측은 금지."
    )
    return "\n".join(parts)


#: 위반 문장을 대체하는 안전 문장. 새 사건 판정을 만들지 않고 근거 한계만 말한다.
#: 대운 배경 위반의 대체 문장 — **배경이 실제로 제공된 섹션에서만** 쓴다. 배경 자체는
#: 유효한 구조 입력이라 통째로 삭제하면 서술이 근거를 잃는다. 바꾸는 것은 '발생·선정을
#: 설명한다'는 인과 주장뿐이다.
_BG_SAFE_WITH_BACKGROUND = (
    "장기 대운 배경은 이미 선택된 흐름의 체감을 설명하는 참고일 뿐, 사건의 발생이나 "
    "이 시기가 선택된 이유를 뜻하지는 않습니다."
)
#: 배경이 **제공되지 않은** 섹션용. 위 문장을 쓰면 주지도 않은 배경을 새로 만들어 낸다 —
#: 전 섹션을 감사하므로 배경 블록 없는 섹션에서도 금지 문장이 나올 수 있다.
_BG_SAFE_WITHOUT_BACKGROUND = (
    "이 시기가 선택된 이유나 사건의 발생 여부를 여기서 단정할 근거는 없습니다."
)
_BG_SAFE = _BG_SAFE_WITH_BACKGROUND

_SAFE_SENTENCE: dict[str, str] = {
    CLAIM_BG_OCCURRENCE_SUPPORT: _BG_SAFE,
    CLAIM_BG_OCCURRENCE_CAUSE: _BG_SAFE,
    CLAIM_BG_RANKING_CAUSE: _BG_SAFE,
    CLAIM_BG_TIMING_SELECTION_CAUSE: _BG_SAFE,
    CLAIM_BG_EVENT_FAMILY_SUPPORT: _BG_SAFE,
    CLAIM_INHERITANCE_TIMING: (
        "이 항목에서는 횡재성 신호의 강약까지만 참고할 수 있고, 상속의 시기를 "
        "판단할 근거로는 쓰지 않습니다."
    ),
    CLAIM_INHERITANCE_OCCURRENCE: (
        "이 항목에서는 횡재성 신호의 강약까지만 참고할 수 있고, 상속의 발생 여부를 "
        "판단할 근거로는 쓰지 않습니다."
    ),
    CLAIM_CONTRACT_DEFECT_OCCURRENCE: (
        "계약 문제가 생긴다고 볼 근거는 없고, 이동 부담이 큰 구간이라 비용·일정·해지 "
        "조건을 미리 확인하는 편이 좋습니다."
    ),
    CLAIM_LEGAL_DISPUTE_TIMING: (
        "법적 분쟁의 시기를 판단할 근거는 없습니다."
    ),
    CLAIM_LEGAL_DISPUTE_OCCURRENCE: (
        "법적 분쟁이 생긴다고 볼 근거는 없습니다."
    ),
}

#: patch 로도 해결되지 않을 때 섹션 전체를 대체하는 문구. **해당 섹션만** 바꾼다 —
#: 테마 리포트 전체를 안전 템플릿으로 바꾸는 것은 과도하다.
SECTION_FALLBACK: dict[str, str] = {
    CLAIM_POLICY_WINDFALL_ONLY: (
        "이 항목에서는 횡재성 신호의 강약까지만 참고할 수 있으며, 상속의 발생 여부나 "
        "구체적인 시기를 판단할 근거로 사용하지 않습니다."
    ),
    CLAIM_POLICY_RELOCATION_CHECK: (
        "특정 위험 시점이 두드러지지는 않지만, 계약 전 비용·해지·입주일 조건은 별도로 "
        "확인해 두는 편이 좋습니다."
    ),
}


def patch_section_claims(
    text: str, violations: tuple[ClaimViolation, ...]
) -> str:
    """위반 문장을 안전 문장으로 **결정적으로** 교체한다(새 LLM 호출 없음).

    뒤쪽 문장부터 교체해 앞선 오프셋이 밀리지 않게 한다. 같은 문장에 여러 claim 이
    걸리면 첫 claim 의 안전 문장 하나로 대체한다(문장 중복 삽입 방지).
    """
    if not violations:
        return text
    by_sentence: dict[int, ClaimViolation] = {}
    for v in violations:
        by_sentence.setdefault(v.sentence_index, v)
    out = text
    for v in sorted(by_sentence.values(), key=lambda x: -x.start):
        safe = _SAFE_SENTENCE.get(v.claim_id)
        if safe is None:
            continue
        out = out[: v.start] + safe + out[v.end :]
    return out


@dataclass(frozen=True)
class SectionAuditOutcome:
    """섹션 1개의 감사 결과 — orchestration 전용(새 판정 엔진이 아니다)."""

    text: str
    violations: tuple[ClaimViolation, ...]
    remaining: tuple[ClaimViolation, ...]
    patched: bool
    fell_back: bool


def audit_and_patch_generated_section(
    text: str, policy: SectionClaimPolicy, *, policy_id: str | None = None
) -> SectionAuditOutcome:
    """섹션 생성 직후 감사 → 결정적 patch → 재감사 → 섹션 단위 fallback.

    기존 감사기와 patch 를 잇는 orchestration 이며 새 판정 규칙을 만들지 않는다.
    fallback 은 **이 섹션만** 대체한다.
    """
    found = audit_section_claims(text, policy)
    if not found:
        return SectionAuditOutcome(text, (), (), False, False)
    patched_text = patch_section_claims(text, found)
    remaining = audit_section_claims(patched_text, policy)
    if not remaining:
        return SectionAuditOutcome(patched_text, found, (), True, False)
    fb = SECTION_FALLBACK.get(policy_id or "")
    if fb is None:
        return SectionAuditOutcome(patched_text, found, remaining, True, False)
    return SectionAuditOutcome(fb, found, remaining, True, True)


# ── 대운 배경 감사 orchestration (2026-07-31) ────────────────────────────
#
# 기존 `audit_and_patch_generated_section` 은 섹션별 evidence 정책이 있을 때만 돈다.
# 배경 claim 은 **전 섹션** 대상이라 별도 경로가 필요하다. 다만 enforcement 는
# post_selection 모드에서만 — current 모드는 탐지·계수만 하고 출력을 건드리지 않는다.

_BG_ALL_POLICY = SectionClaimPolicy(
    section_id="*", forbidden_claims=frozenset(DAEWOON_HWA_FORBIDDEN_CLAIMS),
)

#: 요청 로컬 shadow 관측 — 싱글턴에 남기면 요청 간 계수가 섞여 승격 판단이 왜곡된다.
#: background store 와 같은 take-and-reset 계약이다.
_bg_audit_tls = _threading.local()


@dataclass(frozen=True)
class DaewoonHwaAuditOutcome:
    """배경 claim 감사 1건 — 모드와 무관하게 관측치는 남긴다."""

    text: str
    violations: tuple[ClaimViolation, ...]
    remaining: tuple[ClaimViolation, ...]
    patched: bool
    fell_back: bool
    background_present: bool
    enforced: bool


def audit_daewoon_hwa_claims(
    section_id: str,
    text: str,
    *,
    enforce: bool,
    background_present: bool,
    fallback_text: str | None = None,
) -> DaewoonHwaAuditOutcome:
    """전 섹션 배경 claim 감사. **모드 분기는 patch 호출 이전**에 있다.

    `enforce=False`(current) 면 탐지·계수만 하고 원문을 그대로 돌려준다 — patch 도
    fallback 도 실행하지 않는다. fallback 만 모드로 나누고 patch 를 공통 실행하면
    current 모드 출력이 조용히 달라진다.

    Args:
        section_id: 관측 기록용.
        text: 생성된 섹션 본문.
        enforce: post_selection 모드인가.
        background_present: 이 섹션에 배경 evidence 가 실제로 주입됐는가.
        fallback_text: 재감사 잔존 시 이 섹션을 대체할 문구. None 이면 폴백하지 않는다.

    Returns:
        감사 결과. `text` 는 enforce=False 면 항상 원문과 동일하다.
    """
    violations = audit_section_claims(text, _BG_ALL_POLICY)
    outcome_text, patched, fell_back = text, False, False
    remaining: tuple[ClaimViolation, ...] = violations
    if enforce and violations:
        safe = (
            _BG_SAFE_WITH_BACKGROUND if background_present
            else _BG_SAFE_WITHOUT_BACKGROUND
        )
        outcome_text = _patch_with(text, violations, safe)
        patched = True
        remaining = audit_section_claims(outcome_text, _BG_ALL_POLICY)
        if remaining and fallback_text is not None:
            outcome_text, fell_back = fallback_text, True
            remaining = audit_section_claims(outcome_text, _BG_ALL_POLICY)
    out = DaewoonHwaAuditOutcome(
        text=outcome_text, violations=violations, remaining=remaining,
        patched=patched, fell_back=fell_back,
        background_present=background_present, enforced=enforce,
    )
    sink = getattr(_bg_audit_tls, "sink", None)
    if sink is not None:
        sink.append((section_id, out))
    return out


def _patch_with(
    text: str, violations: tuple[ClaimViolation, ...], safe: str
) -> str:
    """위반 문장을 주어진 안전 문장으로 교체(뒤에서부터 — 오프셋 보존)."""
    by_sentence: dict[int, ClaimViolation] = {}
    for v in violations:
        by_sentence.setdefault(v.sentence_index, v)
    out = text
    for v in sorted(by_sentence.values(), key=lambda x: -x.start):
        out = out[: v.start] + safe + out[v.end :]
    return out


def start_daewoon_hwa_audit_collection() -> None:
    """요청 시작 시 관측 sink 를 연다."""
    _bg_audit_tls.sink = []


def take_daewoon_hwa_audit() -> tuple[tuple[str, DaewoonHwaAuditOutcome], ...]:
    """이번 요청의 배경 감사 관측 — **소비하면 비운다.**

    생성이 생략된 다음 요청이 직전 요청의 계수를 보면 승격 판단이 왜곡된다.
    """
    out = tuple(getattr(_bg_audit_tls, "sink", None) or ())
    _bg_audit_tls.sink = None
    return out
