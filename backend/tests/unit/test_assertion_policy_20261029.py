"""단정 금지 공통 정의(2026-10-29 데굴님 확정).

"단정은 '반드시 ~한다'뿐, '~할 수도 있다'는 단정이 아니다." 실측(완료 답변 948건): 추상 어구
출현 75% vs 구체 사건명 41%. 원인은 시스템 규칙 5 "사건 발생이 아니라 '변화 에너지의 활성화'로
표현"과 명확한 답 계약 ②의 '수 있' 2문장 상한이었다. 이 테스트는 그 두 문구가 되살아나지 않도록
잠그고, 리포트 금지 표현 검사가 가능성형을 하드 위반으로 잡지 않음을 반례로 고정한다.
"""

from __future__ import annotations

import re

from saju_api.services import llm_client
from saju_engines.context_reducer import _BASE_INSTRUCTION
from saju_engines.report_checks import _PROHIBITED_PATTERNS
from saju_engines.structural_context import (
    ANSWER_CLARITY_DIRECTIVE,
    ASSERTION_POLICY,
    AVOID_DATE_CERTAINTY_DIRECTIVE,
)


def test_assertion_policy_defines_assertion_as_certainty_only() -> None:
    """정의 = 확정 어미만 단정, 가능성형은 기본 서술, 추상어 대체 금지, 예외 3종."""
    for needle in ("결과를 확정하는", "단정이 아니며", "추상어로 바꿔", "수명·생사", "로또 번호"):
        assert needle in ASSERTION_POLICY, needle


def test_system_prompts_carry_policy_in_rule5_and_drop_energy_phrasing() -> None:
    """채팅·리포트 규칙 5는 공통 정의를 싣고, 옛 '변화 에너지의 활성화' 지시는 사라진다."""
    for sp in (llm_client._SYSTEM_PROMPT, llm_client._REPORT_SYSTEM_PROMPT):
        assert ASSERTION_POLICY in sp
        assert "5. 사건은 구체 사건명으로 부르되 가능성형으로 쓴다" in sp
        assert "사건 발생이 아니라 '변화 에너지의 활성화'로 표현" not in sp
        # 규칙 1~4·6~9 리터럴 앵커 불변.
        assert "3. 사건명은 동반 신호 매트릭스로 엔진이 확정한 값이다" in sp
        assert "6. 점수·숫자를 답변에 노출하지 않는다" in sp
    assert "답변 끝에 핵심을 한두 문장으로 정리" in llm_client._SYSTEM_PROMPT


def test_answer_clarity_allows_possibility_sentences_without_cap() -> None:
    """②: 판정 문장만 유보 금지, 사건 가능성 문장은 횟수 제한 없음 — '최대 두 문장' 상한 폐기."""
    assert "최대 두 문장" not in ANSWER_CLARITY_DIRECTIVE
    assert "횟수 제한이 없다" in ANSWER_CLARITY_DIRECTIVE
    assert "추상어로 바꿔 쓰지 마라" in ANSWER_CLARITY_DIRECTIVE
    # 기존 불변식 유지.
    assert "단정하라는 뜻이 아니다" in ANSWER_CLARITY_DIRECTIVE
    assert "조건문으로 번역" in ANSWER_CLARITY_DIRECTIVE


def test_date_certainty_directive_keeps_event_names() -> None:
    """시기 단정 지시는 사건명을 추상어('움직임이 강해지는 달')로 바꾸라고 하지 않는다."""
    assert "활성화 창으로 표현" not in AVOID_DATE_CERTAINTY_DIRECTIVE
    assert "면접·제안이 들어올 수 있다" in AVOID_DATE_CERTAINTY_DIRECTIVE
    assert "변화 에너지의 활성화" not in _BASE_INSTRUCTION


def _hits(text: str) -> list[str]:
    return [p for p in _PROHIBITED_PATTERNS if re.search(p, text)]


def test_report_prohibited_patterns_do_not_flag_possibility_forms() -> None:
    """반례 — 가능성형·일상 어휘는 하드 위반(재생성)이 아니다."""
    for text in (
        "작은 횡재가 당첨될 수도 있어요.",
        "이 달은 컨디션이 떨어진다 싶으면 쉬어 가세요.",
        "이직이 거론될 수 있는 해예요.",
        "수술을 하게 될 수도 있으니 검진을 권해요.",
        "이혼 이야기가 나올 수 있는 시기예요.",
        # 2026-10-30 점검: 가능성형 '것 같아요·것으로 보여요'·일상 어휘·조언형 '~할 것'
        "작은 횡재가 당첨될 것 같아요.",
        "당첨될 것으로 보여요.",
        "합격할 수 있어요.",
        "주가가 떨어진다 싶으면 분할 매수를 생각해 보세요.",
        "반드시 검진을 받을 것.",
    ):
        assert not _hits(text), (text, _hits(text))


def test_report_prohibited_patterns_still_flag_certainty_forms() -> None:
    """확정 어미·승부 확정·수명 단정은 그대로 잡는다."""
    for text in (
        "내년에는 반드시 이직한다.",
        "이번엔 당첨될 겁니다.",
        "시험에 떨어진다.",
        "면접에서 떨어진다.",
        "합격한다.",
        "올해 이혼하게 된다.",
        "부친과 사별하게 된다.",
        # 2026-10-30 점검: 확정 어미 '거야·거다·것입니다', 조사 생략·다른 명사, 합니다체, 불합격형
        "당첨될 거야.",
        "당첨될 것입니다.",
        "이번 시험은 떨어진다.",
        "경쟁에서 떨어진다.",
        "승진에서 떨어진다.",
        "반드시 합격합니다.",
        "불합격한다.",
        "합격할 거예요.",
    ):
        assert _hits(text), text
