"""완료형 이직 보고 판정 — '이직을 했는데', '회사 옮겼어', '아니 난 이직을 했다니까'.

2026-10-28 데굴님 승인.

실로그(web-mvrpyw6m·web-mvrq8ocg): "이직을 했는데 업무의 양이 많아"의 '이직'이 **앞으로 일어날**
이직 사건(`career_change`)으로 잡혀 2027년 진입 창 서술로 흘렀고, "아니 난 이직을 했다니까!"도 같은
사건으로 다시 전망했다. 사건 보고형(`query_parser.detect_reported_event`)은 '앞으로 어떻게' 표지가
있거나 해고·퇴사 계열일 때만 보고로 보고, 사실 원장(`user_facts`)의 `job_separation` 슬롯도 이직
완료를 덮지 않았다.

이 모듈 하나를 파서(보고 절 제거 후 사건 감지), 사실 원장(`job_changed` 슬롯), 대화 계층(되물음-답
링크의 도메인 판정), 답변 지시(이직은 이미 일어난 사건)가 함께 쓴다 — `job_separation`과 같은
SSOT 원칙. 규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).

판정: 한 절(쉼표·마침표·접속 어미 경계) 안에 **이직 어휘 + 완료형 어미**가 있고, 그 절이
가정형('이직하면 어떨까')·소원형('했으면')·부정형('안 했')·제3자('남편이 이직했')가 아닐 때.
"""

from __future__ import annotations

import re

#: 이직 어휘 — '이직'·'전직'·'입사', '회사/직장(을) 옮기-', '새 회사/직장(에/로) 들어가-/입사'.
#: 동사 어간('옮'·'들어')은 소비하지 않고(lookahead) 완료형 어미 쪽에서 통째로 맞춘다.
_JOB_CHANGE_WORD = (
    r"(?:이직|전직|입사|(?:회사|직장)(?:를|을|도)?\s*(?=옮)"
    r"|새\s*(?:회사|직장|곳)(?:에|로|으로)?\s*(?=들어|입사|옮|갔|왔))"
)
#: 완료형 — 어휘 뒤 6자 안(조사 포함). '해서/하고 나서'는 완료 연결형("이직을 해서 환경이
#: 바뀌었어").
_DONE = (
    r"(?:했|한\s*지|해서|하고\s*나서|옮겼|들어갔|들어왔|갔|왔|됐|되었)"
    r"(?:다니까요?|라니까요?|다고요?|는데요?|습니다|어요|거든요?|잖아요?|잖니|지만|니까|고|서|어|다|음|지|죠)?"
)
JOB_CHANGE_REPORT_RE = re.compile(rf"{_JOB_CHANGE_WORD}[^.!?\n,]{{0,6}}?{_DONE}")

#: 가정·소원형 — 완료형 바로 뒤에 붙으면 보고가 아니다('이직했으면', '이직했다면', '이직했을까').
_HYPOTHETICAL_TAIL_RE = re.compile(r"^\s*(?:으면|다면|을까|더라면|더라도)")
#: 부정형 — 완료형 앞의 '안/못'('이직 안 했어'), '아직 이직'.
_NEGATED_RE = re.compile(r"(?:안|못)\s*(?:했|옮|들어|갔|왔)|아직\s*(?:이직|옮|입사)")
#: 제3자 주어 — 본인 보고만 사실로 남긴다(`user_facts._JOB_THIRD_PARTY_RE`와 같은 원칙).
_THIRD_PARTY_RE = re.compile(
    r"(?:남편|아내|와이프|신랑|친구|동생|언니|누나|형|오빠|엄마|아빠|어머니|아버지|부모님|동료"
    r"|지인|딸|아들|직원|부하|팀원|후배|선배)(?:이|가|은|는|도)\s*[^.!?\n,]{0,10}?"
    rf"{_JOB_CHANGE_WORD}"
)
#: 절 경계 — 문장 부호·쉼표.
_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n,]+")

#: 새 이직을 묻는 표지 — 보고가 있어도 '또/다시 이직'을 물으면 이직 사건 전망이 맞다.
_NEW_JOB_CHANGE_ASK_RE = re.compile(
    r"(?:또|다시|한\s*번\s*더|새로|다른\s*(?:회사|직장|곳)(?:으로|로)?)\s*[^.!?\n]{0,8}?"
    r"(?:이직|옮기|옮길|들어갈|구직|취업)"
    r"|이직\s*(?:운|시기|언제|제안|할까|하고\s*싶|하려|할지|해야|하면)"
)


def _clause_spans(text: str) -> list[tuple[int, int]]:
    """절 단위 (start, end) 구간 — 경계 부호는 포함하지 않는다."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def job_change_report_spans(text: str) -> list[tuple[int, int]]:
    """완료형 이직 보고 구간 (start, end) 목록 — 절 시작부터 완료형 어미(연결 어미 포함)까지.

    '이직을 했는데 업무의 양이 많아' → '이직을 했는데'. 가정·부정·제3자 절은 제외.
    """
    out: list[tuple[int, int]] = []
    for s, e in _clause_spans(text or ""):
        clause = text[s:e]
        m = JOB_CHANGE_REPORT_RE.search(clause)
        if m is None:
            continue
        head = clause[: m.end()]
        if _HYPOTHETICAL_TAIL_RE.search(clause[m.end():]):
            continue
        if _NEGATED_RE.search(head) or _THIRD_PARTY_RE.search(head):
            continue
        out.append((s, s + m.end()))
    return out


def job_change_report_clauses(text: str) -> list[str]:
    """완료형 이직 보고 구간의 원문 조각 목록(앞뒤 공백 제거). 없으면 빈 목록."""
    return [text[s:e].strip() for s, e in job_change_report_spans(text) if text[s:e].strip()]


def is_job_change_report(text: str) -> bool:
    """발화에 본인의 완료형 이직 보고가 있는가."""
    return bool(job_change_report_spans(text))


def strip_job_change_report(text: str) -> str:
    """보고 구간을 뺀 나머지 — 사건·도메인 감지는 이 잔여 텍스트로 한다.

    '이직을 했는데 업무의 양이 많아' → ' 업무의 양이 많아'. 보고가 없으면 원문 그대로.
    """
    text = text or ""
    spans = job_change_report_spans(text)
    if not spans:
        return text
    out: list[str] = []
    pos = 0
    for s, e in spans:
        out.append(text[pos:s])
        out.append(" ")
        pos = e
    out.append(text[pos:])
    return "".join(out)


def asks_new_job_change(text: str) -> bool:
    """보고와 별개로 **새** 이직을 묻는가('또 이직할까', '다시 옮길 시기').

    이때는 이직 사건 전망이 맞다.
    """
    return bool(_NEW_JOB_CHANGE_ASK_RE.search(text or ""))
