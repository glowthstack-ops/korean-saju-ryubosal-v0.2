"""동반자 공동 풀이 P3c-1(competition) — 2명 경쟁 비교, 승부 단정 금지.

'누가 합격/이길까'류 경쟁 비교를 pairwise/compare 실행 경로를 재사용해 처리하되, 관계맥락을
competition으로 표시하고 승패·당락·확률·순위 산출을 금지하는 가드를 주입한다(절대원칙 8).
본인 포함 경쟁(self base)·동반자끼리 경쟁(A base) 모두 2명까지. thread 경로 필요(DB 미구성 시 skip).
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from saju_api.services import chat_service
from saju_engines.companion_alias import build_companion_alias_index
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.subject import SubjectRecord

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"),
    reason="competition은 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)

_TODAY = date(2026, 7, 2)
_SELF = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)  # 일주 己亥
_JIMIN = BirthInput(
    birth_date="1988-05-05", birth_time="10:00", birth_place_name="서울", gender="male",
)
_MINSU = BirthInput(
    birth_date="1990-09-09", birth_time="11:00", birth_place_name="서울", gender="male",
)


def _idx() -> dict:
    recs = [
        SubjectRecord(subject_id="self1", owner_id="u1", kind="self", label="데굴", birth=_SELF),
        SubjectRecord(
            subject_id="jimin", owner_id="u1", kind="companion", label="지민",
            relation_to_user="friend", birth=_JIMIN,
        ),
        SubjectRecord(
            subject_id="minsu", owner_id="u1", kind="companion", label="민수",
            relation_to_user="friend", birth=_MINSU,
        ),
    ]
    return build_companion_alias_index(recs, base_subject_id="self1")


def _dry(question: str) -> chat_service.ChatResponse:
    return chat_service.chat(
        _SELF, question, today=_TODAY, dry_run=True, thread_id=f"t-{uuid.uuid4().hex[:8]}",
        subject_id="self1", subject_label="데굴",
        companion_alias_index=_idx(),
        companion_births={"jimin": _JIMIN, "minsu": _MINSU},
    )


def test_self_vs_companion_competition_includes_self() -> None:
    """'나랑 지민 중 누가 합격' → 본인 포함(pairwise route) + 경쟁 가드."""
    r = _dry("나랑 지민 중 누가 합격 가능성이 더 있어?")
    txt = r.prompt_preview or ""
    assert r.status == "dry_run"
    assert "己亥" in txt.split("[기준 시점]")[0]  # 본인 명식이 base(포함)
    assert "함께 보기 — 대상별 명식" in txt
    assert "경쟁 비교 지침" in txt


def test_companion_vs_companion_competition_excludes_self() -> None:
    """'지민이랑 민수 누가 더 잘돼?' → 본인 미포함(compare route) + 경쟁 가드."""
    r = _dry("지민이랑 민수 누가 더 잘돼?")
    txt = r.prompt_preview or ""
    assert r.status == "dry_run"
    assert "己亥" not in txt.split("[기준 시점]")[0]  # 본인 명식 미사용
    assert "함께 보기 — 대상별 명식" in txt
    assert "경쟁 비교 지침" in txt


def test_competition_guards_no_verdict() -> None:
    """경쟁 가드가 승패·당락 확정·확률·순위 산출 금지 문구를 담는다."""
    txt = _dry("나랑 지민 중 누가 이길까?").prompt_preview or ""
    assert "승패·우승·합격·당락을 확정하지" in txt
    assert "승률·확률·점수·순위도" in txt


def test_non_competition_comparison_stays_relationship() -> None:
    """'지민이랑 궁합 봐줘'는 경쟁 아님 — 경쟁 가드 미주입(관계 관점 유지)."""
    r = chat_service.chat(
        _SELF, "지민이랑 궁합 어때?", today=_TODAY, dry_run=True,
        thread_id=f"t-{uuid.uuid4().hex[:8]}", subject_id="self1", subject_label="데굴",
        companion_alias_index=_idx(), companion_births={"jimin": _JIMIN},
    )
    txt = r.prompt_preview or ""
    assert "경쟁 비교 지침" not in txt
    assert "함께 보기 — 관계 관점" in txt
