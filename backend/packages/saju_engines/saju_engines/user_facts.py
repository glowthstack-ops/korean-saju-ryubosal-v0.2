"""사용자 제공 사실 원장 — 추출·병합·만료 (2026-07-22 P0, GPT 검토안 승인).

배경: 이전 질문 원문을 상속하지 않는 구조에서 사용자가 밝힌 사실("이미 계약 끝냈고",
"잔금만 남았어", "그날이 손없는 날이래")이 매 턴 증발해 답변이 모순·되묻기로 흐르던
결함(2026-07-22 테스터 스레드). 원문 전체를 다시 붙이는 대신, 사용자 명시 사실만
슬롯 단위로 축적해 LLM 입력에 compact 블록으로 주입한다.

쓰기 정책(불변식): 저장 대상은 **사용자 명시 발화**뿐이다 — 엔진 결과·LLM 해석·추론
기록 금지. 추출은 rules-first(정규식)이며 LLM을 쓰지 않는다(절대원칙 1·9).
"""

from __future__ import annotations

import re

from saju_shared_types.conversation import ConversationState, UserFact

# 슬롯별 추출 패턴 — 매칭된 '문장 절'을 인용(quote)으로 보존한다(정규화 값보다 오해석이
# 적다). singleton=True인 키는 스레드에 1건만 유지하고 재진술 시 supersede(정정 이력).
# 2026-07-22 커버리지 확대: 테스터 실문장 4종("이사가 결정되었어"·"계약서는 이미 다 썼고"·
# "8월 신청·9월 공사"·"주택을 사기 위한 대출")이 전부 미추출(원장 빈 채 유지 → '다시
# 백지에서 시작' 재현)이던 결함 — 실대화 동사·계획 진술·용도 진술 슬롯 보강.
_FACT_RULES: list[tuple[str, re.Pattern[str], bool]] = [
    # 완료 진술 — "이미 계약도 끝냈고", "계약서는 이미 다 썼고", "보증금은 냈어" (누적)
    (
        "completed",
        re.compile(
            r"(?:이미|벌써|다)\s*[^.!?\n]{0,24}?(?:했|썼|냈|됐|받았|맺었|끝났|끝냈|완료|마쳤)"
            r"|[^.!?\n]{1,30}?(?:끝냈|완료했|마무리했|마쳤)"
        ),
        False,
    ),
    # 잔여 절차 — "잔금만 남았", "대출, 인테리어 등이 남아있는데" (누적)
    ("remaining", re.compile(r"[^.!?\n]{1,45}?(?:만\s*남|남아\s*있|남았)"), False),
    # 확정 일정 — "9월 30일에 이사가 예정/결정되었어", "10월로 확정" (단수 — 재진술 시 정정)
    (
        "fixed_schedule",
        re.compile(
            r"(?:\d{4}년\s*)?\d{1,2}월(?:\s*\d{1,2}일)?[^.!?\n]{0,16}?"
            r"(?:예정|확정|결정|하기로|정해[졌져]|가기로|잡[혔았]|계약[했함])"
        ),
        True,
    ),
    # 일정 계획 진술 — "8월에는 대출 신청·업체 선정", "공사는 9월에 진행" (누적)
    (
        "planned_task",
        re.compile(
            r"\d{1,2}월[^.!?\n]{0,20}?(?:신청|선정|진행|공사|입주|잔금|계약|이사|시작|마무리)"
            r"|(?:공사|잔금|입주|계약|대출|인테리어)[^.!?\n]{0,12}?\d{1,2}월"
        ),
        False,
    ),
    # 당일 계획 — "그 날은 짐만 옮기는 날이야" (단수)
    (
        "day_plan",
        re.compile(r"그\s*날은[^.!?\n]{1,30}?(?:날이야|날이에요|날임)|짐만\s*옮기"),
        True,
    ),
    # 명시 용도 — "주택을 사기 위한 대출" (단수)
    ("stated_purpose", re.compile(r"[^.!?\n]{1,24}?위한\s*(?:대출|자금|계약|돈|투자)"), True),
    # 변경 불가 진술 — "어쩔 수 없어", "날짜 못 바꿔" (단수)
    ("unchangeable", re.compile(r"어쩔\s*수\s*없|못\s*바꾸|바꿀\s*수\s*없|무를\s*수\s*없"), True),
    # 속설 조건 — "손없는 날이래" (단수)
    ("folk_condition", re.compile(r"손\s*없는\s*날"), True),
]

_SENT_SPLIT_RE = re.compile(r"[.!?\n]+")
_MAX_QUOTE = 80
_MAX_FACTS = 12  # 주입 캡과 별개의 저장 캡 — 오래된 누적 사실부터 밀어낸다.


def _clause_of(text: str, span_start: int) -> str:
    """매칭 위치가 속한 문장 절(quote) — 앞뒤 문장 경계로 자르고 길이 캡."""
    start = 0
    for m in _SENT_SPLIT_RE.finditer(text):
        if m.start() >= span_start:
            return text[start:m.start()].strip()[:_MAX_QUOTE]
        start = m.end()
    return text[start:].strip()[:_MAX_QUOTE]


def extract_user_facts(text: str, turn: int) -> list[UserFact]:
    """이번 턴 발화에서 사용자 명시 사실을 추출한다(rules-first, LLM 미사용).

    Args:
        text: 사용자 발화 원문.
        turn: 이번 턴 번호(source_turn 기록).

    Returns:
        추출된 UserFact 목록 — 같은 절에서 같은 key가 중복 매칭되면 1건만.
    """
    out: list[UserFact] = []
    seen: set[tuple[str, str]] = set()
    for key, pat, _singleton in _FACT_RULES:
        for m in pat.finditer(text):
            quote = _clause_of(text, m.start())
            if not quote or (key, quote) in seen:
                continue
            seen.add((key, quote))
            out.append(UserFact(key=key, quote=quote, source_turn=turn))
    # 같은 절이 fixed_schedule과 planned_task에 겹치면 구체적인 쪽(fixed)만 남긴다.
    fixed_quotes = {f.quote for f in out if f.key == "fixed_schedule"}
    return [f for f in out if not (f.key == "planned_task" and f.quote in fixed_quotes)]


def merge_user_facts(
    state: ConversationState,
    new_facts: list[UserFact],
    topic_reset: bool,
) -> list[UserFact]:
    """상태의 사실 원장에 이번 턴 추출분을 병합한다.

    규칙: ①주제 전환(topic_reset)이면 scope='topic' 기존 사실 만료 ②단수 키(확정
    일정 등)는 새 진술이 오면 기존 건을 corrected로 대체하고 이전 인용을 이력으로 보존
    ③누적 키는 동일 인용 중복만 제거 ④저장 캡 초과 시 오래된 것부터 제거(정정 이력
    우선 보존).
    """
    singleton_keys = {k for k, _p, s in _FACT_RULES if s}
    kept = [
        f for f in state.user_facts
        if not (topic_reset and f.scope == "topic")
    ]
    for nf in new_facts:
        if nf.key in singleton_keys:
            prev = next(
                (f for f in kept if f.key == nf.key and f.status == "confirmed"), None
            )
            if prev is not None:
                if prev.quote == nf.quote:
                    continue  # 동일 재진술 — 갱신 불요
                kept = [f for f in kept if f is not prev]
                nf = nf.model_copy(
                    update={"status": "confirmed", "superseded_quote": prev.quote}
                )
        elif any(f.key == nf.key and f.quote == nf.quote for f in kept):
            continue
        kept.append(nf)
    if len(kept) > _MAX_FACTS:
        kept = kept[-_MAX_FACTS:]
    return kept


_KEY_KO = {
    "completed": "완료됨",
    "remaining": "남은 절차",
    "fixed_schedule": "확정 일정",
    "planned_task": "일정 계획",
    "day_plan": "당일 계획",
    "stated_purpose": "명시 용도",
    "unchangeable": "변경 불가",
    "folk_condition": "속설 조건",
}


def user_facts_block(facts: list[UserFact], cap: int = 10) -> str | None:
    """LLM 입력용 [사용자 제공 정보] 블록 — 최근 cap건, 없으면 None.

    사실과 모순되는 서술·이미 밝힌 내용 되묻기를 차단하는 근거 블록이다. 인용 원문을
    그대로 노출하며, 정정된 단수 슬롯은 이전 진술을 함께 표기해 혼동을 막는다.
    """
    if not facts:
        return None
    lines = [
        "[사용자 제공 정보 — 대화에서 사용자가 직접 밝힌 사실. 아래 내용과 모순되게 "
        "서술하지 말고, 이미 밝힌 사실을 다시 묻지 말 것. 이 사실들은 사용자가 알려준 "
        "정보이지 사주에서 읽어낸 것이 아니다 — '~로 보여요/읽혀요'처럼 점친 듯 되풀이하지 "
        "말고, 사실은 사실로 받아 그 위에서 풀이할 것]"
    ]
    for f in facts[-cap:]:
        label = _KEY_KO.get(f.key, f.key)
        line = f"- ({label}) “{f.quote}”"
        if f.superseded_quote:
            line += f" (이전 진술 “{f.superseded_quote}”에서 정정됨)"
        lines.append(line)
    return "\n".join(lines)
