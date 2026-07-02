"""동반자 공동 풀이 P3c-2(ranking) — 동반자 3~4명 다자 비교, 순위 단정 금지.

'지민 민수 영희 중 누가 제일 잘돼?'류 다자 비교를 self 제외·A=base·나머지 블록으로 처리하고,
절대 순위·점수·확률 산출을 금지하는 다자 비교 지침을 주입한다. 4명 초과는 cap=4 + 초과 명시.
thread 경로 필요 — DB 미구성 시 skip.
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
    reason="ranking은 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)

_TODAY = date(2026, 7, 2)
_SELF = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)  # 일주 己亥


def _c(d: str) -> BirthInput:
    return BirthInput(birth_date=d, birth_time="10:00", birth_place_name="서울", gender="male")


_PEOPLE = {
    "jimin": ("지민", _c("1988-05-05")),
    "minsu": ("민수", _c("1990-09-09")),
    "younghee": ("영희", _c("1992-01-01")),
    "taeho": ("태호", _c("1985-03-03")),
    "sujin": ("수진", _c("1993-07-07")),
}


def _idx() -> dict:
    recs = [SubjectRecord(
        subject_id="self1", owner_id="u1", kind="self", label="데굴", birth=_SELF,
    )]
    for sid, (label, birth) in _PEOPLE.items():
        recs.append(SubjectRecord(
            subject_id=sid, owner_id="u1", kind="companion", label=label,
            relation_to_user="friend", birth=birth,
        ))
    return build_companion_alias_index(recs, base_subject_id="self1")


def _births() -> dict:
    return {sid: birth for sid, (_label, birth) in _PEOPLE.items()}


def _dry(question: str) -> chat_service.ChatResponse:
    return chat_service.chat(
        _SELF, question, today=_TODAY, dry_run=True, thread_id=f"t-{uuid.uuid4().hex[:8]}",
        subject_id="self1", subject_label="데굴",
        companion_alias_index=_idx(), companion_births=_births(),
    )


def _blocks(txt: str) -> list[str]:
    return [ln for ln in txt.splitlines() if ln.startswith("· ")]


def test_ranking_three_companions_excludes_self() -> None:
    """3명 다자 → 본인(己亥) 미사용, 3개 대상 블록 + 다자 비교 지침."""
    r = _dry("지민 민수 영희 중 누가 제일 잘돼?")
    txt = r.prompt_preview or ""
    assert r.status == "dry_run"
    assert "己亥" not in txt.split("[기준 시점]")[0]  # 본인 명식 미사용
    assert "다자 비교 지침" in txt
    assert len(_blocks(txt)) == 3


def test_ranking_forbids_rank_verdict() -> None:
    """다자 지침이 순위 확정·점수화·확률화 금지를 담는다."""
    txt = _dry("지민 민수 영희 비교해줘").prompt_preview or ""
    assert "절대 순위를" in txt
    assert "점수화" in txt


def test_ranking_caps_at_four() -> None:
    """5명 요청 → 앞 4명만 반영 + '최대 4명' 초과 명시."""
    r = _dry("지민 민수 영희 태호 수진 중 누가 제일 나아?")
    txt = r.prompt_preview or ""
    assert len(_blocks(txt)) == 4
    assert "최대 4명" in txt


def test_two_companions_stays_compare_not_ranking() -> None:
    """2명은 ranking이 아니라 기존 compare/competition 경로 유지(다자 지침 없음)."""
    txt = _dry("지민이랑 민수 누가 더 잘돼?").prompt_preview or ""
    assert "다자 비교 지침" not in txt
    assert len(_blocks(txt)) == 2
