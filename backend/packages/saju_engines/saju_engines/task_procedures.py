"""현실 과업 절차 레이어 (2026-07-22 데굴님 승인 — GPT 검토안 P1·P2·P3 축소판).

사주 신호를 현실 과업으로 번역하기 위한 도메인 절차 지식. 3단계 경계(승인 문서 §8):
- L1 절차 구조(단계·의존관계)와 L2 실무 체크(시점 불변 일반 지식)만 코드 상수로 보유한다.
- L3(최신 금융규제·법률 효력·세금·기관별 요강)는 절대 자체 단정하지 않고 확인 안내로
  분리한다 — 각 팩의 expert_note가 그 경계 고지문이다.

라우트(승인 문서 §4 축소): CAPABILITY_PROBE('너 집 계약 절차 알아?')와 PROCEDURE_QUERY
('집 계약 순서가 어떻게 돼?')는 명식·이벤트 엔진과 LLM을 호출하지 않는 즉답 경로다 —
QueryType enum은 확장하지 않고(docs/03 taxonomy 불변) 서비스 계층 선행 라우트로 처리한다.
MIXED_TASK(과업 점검)는 기존 분석 경로에 [과업 절차 참고] 블록을 가산 주입해 처리한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskPack:
    """생활 사건 1종의 절차 지식팩 (L1 단계 + L2 실무 체크, L3 제외)."""

    key: str
    name: str  # 사용자 노출명('주택 계약·이사')
    trigger_words: tuple[str, ...]  # 질문에서 이 팩을 고르는 신호 어휘
    stages: tuple[str, ...]  # L1 — 진행 단계(순서 의존)
    dependencies: tuple[str, ...]  # L1 — 단계 간 의존관계
    common_failures: tuple[str, ...]  # L2 — 흔한 실패 형태
    irreversible_points: tuple[str, ...]  # L2 — 되돌리기 어려운 시점
    expert_note: str = ""  # L3 경계 고지 — 자체 단정 금지 영역 안내
    checkpoints: tuple[str, ...] = field(default=())  # L2 — 단계별 확인 행동


# 범용 절차 온톨로지(§3) — 팩이 없는 도메인의 폴백 골격.
GENERIC_STAGES: tuple[str, ...] = (
    "준비", "신청·접수", "심사·협의", "선정·승인", "계약·확정", "실행·배치", "정산·유지",
)

TASK_PACKS: dict[str, TaskPack] = {
    "housing": TaskPack(
        key="housing",
        name="주택 계약·대출·이사",
        trigger_words=("집 계약", "주택", "매매", "전세", "월세", "이사", "대출", "잔금",
                       "인테리어", "입주", "등기", "부동산"),
        stages=(
            "자금계획", "대출 사전확인", "물건·권리관계 확인", "계약·특약", "대출 승인",
            "잔금·등기", "인테리어·공사", "입주·하자처리",
        ),
        dependencies=(
            "대출 승인이 나야 잔금이 가능하다",
            "계약 범위가 확정되어야 인테리어 견적이 확정된다",
            "대출 '승인'과 실제 '실행(입금)'은 별개 단계다",
        ),
        common_failures=(
            "심사 지연·추가서류 요청으로 잔금일과 승인일이 어긋남",
            "견적에 없던 철거·전기·보수 항목의 추가 비용",
            "특약·해제조건 누락(대출 불승인 시 처리 조항 부재)",
            "잔금·착공·입주 일정이 한 시기에 몰려 지연 시 대체 일정 부재",
        ),
        irreversible_points=("계약금 지급", "잔금일 확정", "대출 실행", "공사 착공"),
        checkpoints=(
            "계약 전: 필요서류 목록·잔금일 변경 가능 여부·특약(대출 불승인 시 해제 조건)",
            "공사 전: 견적 제외 항목·추가비 산정 방식을 계약서에 명기",
            "잔금 전: 대출 실행일과 잔금일 간격·등기 서류 준비",
        ),
        expert_note=(
            "현재 대출 규제·금리·실제 승인 가능 금액과 계약 조항의 법적 효력은 "
            "금융기관·계약 전문가의 최신 기준 확인이 필요하다"
        ),
    ),
    "employment": TaskPack(
        key="employment",
        name="취업·이직",
        trigger_words=("취업", "이직", "입사", "면접", "지원서", "채용", "퇴사"),
        stages=("지원", "서류심사", "면접", "합격", "처우협의", "계약", "입사", "적응"),
        dependencies=(
            "합격 후에도 처우협의·입사일 조율·온보딩이 남는다",
            "퇴사 통보는 다음 자리가 확정된 뒤가 안전하다",
        ),
        common_failures=(
            "합격 이후 처우협의 결렬·입사일 충돌",
            "재직 중 이직 시 인수인계·통보 시점 관리 실패",
        ),
        irreversible_points=("퇴사 통보", "입사 계약 서명"),
        checkpoints=("합격 전: 지원 범위 확대·면접 준비 / 합격 후: 처우 조건 문서화",),
        expert_note="연봉·계약 조건의 법적 판단은 계약서 검토 전문가 확인이 필요하다",
    ),
    "selection": TaskPack(
        key="selection",
        name="추첨·선발·배치",
        trigger_words=("추첨", "청약", "선발", "배치", "입영", "입대", "군대", "당첨"),
        stages=(
            "지원조건 확인", "신청", "추첨·선발", "자격 재확인", "희망조건 매칭",
            "배치 확정", "실제 이동·적응",
        ),
        dependencies=("추첨 당첨 후에도 자격심사와 배치 단계가 남는다",),
        common_failures=("당첨 후 자격 요건 미비로 취소", "희망 조건과 배치 결과 불일치"),
        irreversible_points=("입영·배치 확정",),
        checkpoints=("신청 전: 자격 요건·제출 서류 / 당첨 후: 후속 심사 일정",),
        expert_note="기관별 최신 모집요강·자격조건은 해당 기관 공고 확인이 필요하다",
    ),
    "marriage": TaskPack(
        key="marriage",
        name="결혼 준비",
        trigger_words=("결혼 준비", "상견례", "예식", "혼인신고", "신혼집"),
        stages=(
            "관계 형성", "결혼 의사 확인", "가족 협의", "재정·주거 계획", "날짜·계약",
            "혼인", "공동생활 적응",
        ),
        dependencies=("양가 협의와 재정 계획이 서야 날짜·계약이 확정된다",),
        common_failures=("예식·주거 계약 일정 충돌", "예산 초과", "양가 협의 지연"),
        irreversible_points=("예식장·주거 계약금 지급", "혼인신고"),
        checkpoints=("계약 전: 위약 조건 / 협의 단계: 예산 상한 합의",),
        expert_note="혼인신고·재산 관련 법적 효력은 전문가 확인이 필요하다",
    ),
}


def detect_task_pack(text: str) -> TaskPack | None:
    """본문에서 가장 먼저 신호가 잡히는 지식팩(없으면 None)."""
    best: tuple[int, TaskPack] | None = None
    for pack in TASK_PACKS.values():
        positions = [text.find(w) for w in pack.trigger_words if w in text]
        if positions and (best is None or min(positions) < best[0]):
            best = (min(positions), pack)
    return best[1] if best else None


# 능력 탐문(§1·§4 CAPABILITY_PROBE) — 서비스가 그 과업을 이해하는지 묻는 질문.
# '너/네가' 주어 + 알아/알고 있어, 또는 '볼 줄 알아/상담 가능해/할 수 있어' 탐문형.
_PROBE_RE = re.compile(
    r"(?:너|네가|니가)[^.!?\n]{0,30}?(?:알고\s*있|알아|아니\?)"
    r"|볼\s*줄\s*알|상담\s*(?:가능|돼|되)|(?:이런\s*것|이것)도\s*(?:알|봐|할\s*수)"
)
# 절차 질문(§4 PROCEDURE_QUERY) — 운세가 아니라 일반 절차 자체를 묻는 질문.
_PROCEDURE_RE = re.compile(
    r"(?:절차|순서|과정|방식)[^.!?\n]{0,12}?(?:어떻게|알려|뭐야|어떻게\s*돼|궁금)"
    r"|어떻게\s*진행\s*(?:돼|되는지|되나)"
)
# 운세 신호 — 시기·길흉을 물으면 탐문이 아니라 분석 경로다(과잉 라우팅 방지).
_FORTUNE_SIGNAL_RE = re.compile(r"운세|운이|길일|언제|몇\s*월|시기|괜찮|좋을까|해도\s*될")


def build_capability_answer(question: str) -> str | None:
    """능력 탐문·절차 질문의 즉답(LLM·엔진 미호출). 해당 없으면 None.

    아는 범위(절차 단계)와 한계(L3 전문가 영역)를 함께 보여주고, 과업별 시기·주의점
    상담(MIXED_TASK)으로 자연스럽게 이어지게 안내한다(승인 문서 §1 권장 형식).
    """
    if _FORTUNE_SIGNAL_RE.search(question):
        return None  # 시기·길흉 질문은 분석 경로
    is_probe = bool(_PROBE_RE.search(question))
    is_procedure = bool(_PROCEDURE_RE.search(question))
    if not (is_probe or is_procedure):
        return None
    pack = detect_task_pack(question)
    if pack is None:
        if not is_probe:
            return None  # 팩 없는 순수 절차 질문은 일반 경로에 맡긴다(오탐 방지)
        return (
            "네, 생활 사건은 준비→신청→심사→승인→계약→실행→정산의 단계로 나눠 이해하고 "
            "있어요. 사주 풀이에서는 이 과정을 한 번에 뭉뚱그리지 않고 과업별로 나눠 "
            "시기와 주의점을 설명해 드려요. 다만 법률·금융·의료 같은 전문 판단과 최신 "
            "제도는 해당 전문가·기관 확인이 필요해요. 어떤 과업의 시기·주의점이 궁금하신가요?"
        )
    stages = " → ".join(pack.stages)
    deps = " / ".join(pack.dependencies[:2])
    return (
        f"네. {pack.name} 과정은 보통 {stages} 순서로 진행돼요. "
        f"단계 사이에는 의존관계가 있어요 — {deps}. "
        "사주 풀이에서는 이 과정을 하나의 운으로 뭉뚱그리지 않고, 과업별로 나눠 시기와 "
        f"주의점을 설명해 드려요. 다만 {pack.expert_note}. "
        "어떤 과업의 시기·주의점부터 볼까요?"
    )


def procedure_reference_block(pack: TaskPack) -> str:
    """분석 경로(MIXED_TASK) 가산용 [과업 절차 참고] 블록 — 일반 절차 지식(운 신호 아님).

    LLM이 과업 점검을 실제 단계·의존관계·실패 형태에 연결하게 하되, 이 지식을 운세
    판정처럼 서술하거나 L3(최신 규정)를 단정하지 않도록 경계를 함께 고지한다.
    """
    lines = [
        f"[과업 절차 참고 — {pack.name} 일반 절차 지식. 운 신호가 아니라 현실 절차다. "
        "과업별 점검 시 단계·의존관계·되돌리기 어려운 시점을 반영하되, 이 내용을 사주에서 "
        "읽은 것처럼 서술하지 말 것]",
        f"- 단계: {' → '.join(pack.stages)}",
    ]
    lines += [f"- 의존관계: {d}" for d in pack.dependencies]
    lines += [f"- 흔한 문제: {f}" for f in pack.common_failures]
    if pack.irreversible_points:
        lines.append(f"- 되돌리기 어려운 시점: {', '.join(pack.irreversible_points)}")
    lines += [f"- 확인 행동: {c}" for c in pack.checkpoints]
    if pack.expert_note:
        lines.append(f"- 전문가 확인 영역(단정 금지): {pack.expert_note}")
    return "\n".join(lines)
