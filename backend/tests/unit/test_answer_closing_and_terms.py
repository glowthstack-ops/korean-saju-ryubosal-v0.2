"""답변 마무리 중복·신살 표기 훼손 회귀 (2026-08-06).

두 결함 다 실사용 답변에서 관측됐고, DB 이력으로 규모를 쟀다.

    마무리 중복   본문형 assistant 507건 중 40건(7.9%)이 말미 5문장에 물음표 문장 2개 이상
    표기 훼손     assistant 570건 중 '격격살' 1건 — 격각살(隔角殺)의 훼손, 존재하지 않는 말

마무리 중복의 원인은 모델이 아니라 **지시문 충돌**이었다. `[제안 방향]`·연도/월 되묻기가
각자 "답 말미에" 무언가를 요구하는데, 시스템 프롬프트도 무조건 "답변 끝에 핵심 정리 + 질문
1개"를 요구한다. 그래서 답이 두 번 끝났다. 여기서는 **말미 소유권이 한 곳뿐인지**를 고정한다.

원칙 1(개발 테스트에서 LLM 미사용)에 따라 실호출은 없다. 마무리 검사는 dry_run 이 돌려주는
프롬프트 문자열로, 표기 검사는 순수 함수로 판정한다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date, time

import pytest

from saju_api.services import chat_service, llm_client
from saju_shared_types.birth_input import BirthInput

_BIRTH = BirthInput(
    birth_date=date(1985, 11, 20),
    birth_time=time(14, 30),
    birth_place_name="서울",
    timezone="Asia/Seoul",
    gender="male",
    reference_date=date(2026, 8, 6),
)

#: "답을 여기서 맺어라"라고 지시하는 표현. 이 중 하나만 살아 있어야 한다.
_CLOSING_OWNER_RE = re.compile(
    r"답변 끝에 핵심을 한두 문장으로 정리|답 말미에|답변 끝에 '|끝에 특정 달의 상세"
)


def _prompt_of(question: str) -> str:
    """dry_run 프롬프트 + 실제 전송될 시스템 프롬프트 — LLM 을 부르지 않는다.

    `system_prompt` 은 추가 블록이 붙을 때만 채워진다. 비어 있으면 `generate_reading`
    이 기본 `_SYSTEM_PROMPT` 을 쓰므로(chat_service 의 예산 계산도 같은 규칙), 여기서도
    같은 폴백을 적용해야 실제 전송분과 어긋나지 않는다.
    """
    resp = chat_service.chat(
        _BIRTH, question, today=date(2026, 8, 6), dry_run=True
    )
    system = resp.system_prompt or llm_client._SYSTEM_PROMPT
    return (resp.prompt_preview or "") + "\n" + system


# ── 마무리 소유권 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    ["오늘의 운세를 알려줘", "내일 운세도 알려줘", "올해 어떤가요"],
)
def test_only_one_directive_owns_the_ending(question: str) -> None:
    """말미를 요구하는 지시는 정확히 하나다 — 답이 두 번 끝나던 원인.

    개정 전에는 '오늘의 운세를 알려줘' 한 질문에 시스템 8번 + `[제안 방향]`(답 말미에)
    + 특정일 행동지침이 동시에 붙었다.
    """
    owners = _CLOSING_OWNER_RE.findall(_prompt_of(question))
    assert len(owners) == 1, f"말미 지시 {len(owners)}개: {owners}"


def test_the_single_owner_is_the_system_prompt() -> None:
    """소유자는 시스템 프롬프트여야 한다 — 조건부 지시가 소유하면 질문 유형마다 흔들린다."""
    assert "답변 끝에 핵심을 한두 문장으로 정리" in llm_client._SYSTEM_PROMPT


def test_system_prompt_caps_the_question_count() -> None:
    """마무리 질문이 하나뿐임을 시스템 프롬프트가 못박는다."""
    text = llm_client._SYSTEM_PROMPT
    assert "마무리는 이 한 번뿐이다" in text
    assert "마지막 질문 하나뿐이어야 한다" in text


def test_suggestion_block_no_longer_claims_the_ending() -> None:
    """`[제안 방향]`은 본문에 녹이고 답을 맺지 않는다(대화·리포트 공용 문구)."""
    from saju_engines.direction_suggestion import DIRECTION_SUGGESTION_INSTRUCTION

    assert "답 말미에" not in DIRECTION_SUGGESTION_INSTRUCTION
    assert "본문 흐름 안에" in DIRECTION_SUGGESTION_INSTRUCTION


@pytest.mark.parametrize(
    "directive",
    ["_YEAR_DIGEST_DIRECTIVE", "_MONTH_PICK_DIRECTIVE"],
)
def test_followup_directives_supply_a_topic_not_another_question(
    directive: str,
) -> None:
    """되묻기 지시는 질문을 **추가**하지 않고 마무리 질문의 소재만 정한다."""
    text = getattr(chat_service, directive)
    assert "마무리 질문을 따로 더 만들지 말고" in text
    assert "자연스럽게 물어라" not in text


# ── 신살 표기 훼손 ───────────────────────────────────────────────────────


def test_nonexistent_sinsal_term_is_restored() -> None:
    """'격격살'은 존재하지 않는 말이다 — 엔진이 준 '격각살'로 되돌린다."""
    out = llm_client._sanitize_output("오늘은 격격살의 기운이 함께 들어와요.")
    assert "격각살" in out
    assert "격격살" not in out


@pytest.mark.parametrize("term", ["현침살", "백호살", "연살"])
def test_common_variants_are_left_alone(term: str) -> None:
    """통용 변형은 틀린 말이 아니다 — 사전 표기로 밀어붙이지 않는다(2026-08-06 확정).

    '연살'(年殺)은 두음법칙상 정당한 독음이고 '현침살'·'백호살'도 통용 표기다. 여기까지
    고치면 교정이 아니라 개입이 된다.
    """
    text = f"{term}의 기운이 있어요."
    assert llm_client._sanitize_output(text) == text


def test_canonical_names_are_never_rewritten() -> None:
    """사전에 있는 이름은 어떤 경우에도 건드리지 않는다."""
    from saju_engines.chart_interpretation import canonical_sinsal_names

    for name in sorted(canonical_sinsal_names()):
        text = f"{name}이(가) 들어와요."
        assert llm_client._sanitize_output(text) == text, name


@pytest.fixture()
def drift_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """`saju_api` 로거를 직접 잡는다 — caplog 만으로는 거짓 통과한다.

    `main.py` 가 앱 네임스페이스 로거에 `propagate = False` 를 건다(서드파티 INFO 소음
    차단). caplog 는 루트에 붙으므로, 이 모듈을 import 한 테스트가 하나라도 앞서 돌면
    **경고가 실제로 났는데도 `caplog.records` 가 빈다.** 그러면 긍정 검사는 깨지고 부정
    검사는 조용히 통과한다 — 뒤쪽이 더 위험하다(2026-08-06 전체 스위트에서 실측).
    """
    logger = logging.getLogger("saju_api.services.llm_client")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="saju_api.services.llm_client")
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def _drift_records(logs: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in logs.records if "sinsal_term_drift" in r.getMessage()]


def test_the_drift_logger_is_actually_captured(
    drift_logs: pytest.LogCaptureFixture,
) -> None:
    """포착 배선 자체를 먼저 고정한다 — 이게 깨지면 아래 부정 검사가 무의미해진다."""
    llm_client._logger.warning("sinsal_term_drift 포착 확인")
    assert _drift_records(drift_logs)


def test_unknown_drift_is_logged_not_silently_kept(
    drift_logs: pytest.LogCaptureFixture,
) -> None:
    """교정 목록에 없는 새 훼손은 경고로 드러난다 — 조용히 지나가면 다음에도 모른다.

    '화계살'은 사전의 '화개살'과 한 글자만 다르다 = 격격살과 같은 형태의 훼손이다.
    """
    llm_client._sanitize_output("화계살의 기운이 함께 들어와요.")
    assert _drift_records(drift_logs)


@pytest.mark.parametrize(
    "text",
    [
        "몸살 기운에 햇살까지 더해 살림살이가 고단해요.",   # 일반어
        "형살과 흉살, 관살의 작용이 함께 보여요.",          # 정상 명리어(2자)
        "식신제살과 상관제살의 구조가 보여요.",             # 정상 명리어(4자)
        "현침살과 백호살의 기운이 있어요.",                 # 통용 변형
    ],
)
def test_ordinary_and_valid_terms_do_not_trigger_drift_logs(
    text: str, drift_logs: pytest.LogCaptureFixture,
) -> None:
    """일반어·정상 용어·통용 변형으로 로그가 울리면 계측이 소음이 된다."""
    llm_client._sanitize_output(text)
    assert not _drift_records(drift_logs)


def test_drift_detector_matches_three_char_terms() -> None:
    """탐지 정규식이 '격격살'(3자)을 실제로 잡는가 — 초판이 이걸 놓쳤다."""
    found = llm_client._SINSAL_TOKEN_RE.findall("격격살과 천을귀인")
    assert "격격살" in found
    assert "천을귀인" in found


def test_swap_detector_boundary() -> None:
    """탐지 기준의 경계 — 같은 길이·한 글자 치환까지만 '가까운 이름'이다."""
    assert llm_client._is_one_char_swap("격격살", "격각살")
    assert not llm_client._is_one_char_swap("현침살", "현침")      # 길이 다름
    assert not llm_client._is_one_char_swap("천을귀인", "문창귀인")  # 두 글자 다름
