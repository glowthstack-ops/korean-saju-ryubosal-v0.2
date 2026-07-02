"""동반자 공동 풀이 P2b(companion_only) — 본문 base를 동반자 birth로 교체.

'엄마 올해 건강운만' 같은 동반자 단독 질문은 동반자 명식(원국/대운/세운)을 primary로
산출한다. 본인 명식으로 대체하지 않으며, 동반자 birth가 없으면 self fallback 대신 확인
요청(need_subject)한다. self_only/pairwise 경로는 불변. 대상 해소는 thread 경로(대화 엔진 +
alias_index)에서 이뤄지므로 DB 필요 — 미구성 환경에서는 skip.
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
    reason="companion_only는 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)

_TODAY = date(2026, 7, 2)
_SELF = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)  # 일주 己亥
_MOM = BirthInput(
    birth_date="1955-06-10", birth_time="08:00", birth_place_name="서울", gender="female",
)  # 일주 壬寅


def _alias_index() -> dict:
    recs = [
        SubjectRecord(subject_id="self1", owner_id="u1", kind="self", label="데굴", birth=_SELF),
        SubjectRecord(
            subject_id="mom1", owner_id="u1", kind="companion", label="김여사",
            relation_to_user="mother", birth=_MOM,
        ),
    ]
    return build_companion_alias_index(recs, base_subject_id="self1")


def _dry(question: str, companion_births: dict | None = None) -> chat_service.ChatResponse:
    return chat_service.chat(
        _SELF, question, today=_TODAY, dry_run=True, thread_id=f"t-{uuid.uuid4().hex[:8]}",
        subject_id="self1", subject_label="데굴",
        companion_alias_index=_alias_index(),
        companion_births=companion_births if companion_births is not None else {"mom1": _MOM},
    )


def test_companion_only_swaps_base_to_companion() -> None:
    """'엄마 올해 건강운' → 엄마 명식(일주 壬寅)이 base + 분석대상 디렉티브(본인 대체 아님)."""
    r = _dry("엄마 올해 건강운 봐줘")
    txt = r.prompt_preview or ""
    assert r.status == "dry_run"
    # 원국·명식 구조 prefix의 일주가 엄마(壬寅)로 교체됨 — 본인(己亥)이 아님.
    assert "일주 壬寅" in txt or "壬寅" in txt.split("[기준 시점]")[0]
    assert "[분석 대상]" in txt and "김여사" in txt


def test_self_only_unchanged_in_thread() -> None:
    """'내 올해 건강운' → 본인(己亥) 그대로, companion_only 디렉티브 없음."""
    r = _dry("내 올해 건강운 봐줘")
    txt = r.prompt_preview or ""
    assert "己亥" in txt
    assert "[분석 대상]" not in txt


def test_companion_only_missing_birth_asks_clarification() -> None:
    """동반자 birth 없음 → 본인으로 대체하지 않고 need_subject(등록 정보 확인)."""
    r = _dry("엄마 올해 건강운 봐줘", companion_births={})
    assert r.status == "need_subject"
    assert "출생 정보" in (r.answer or "")


def test_pairwise_text_reads_both_not_companion_only() -> None:
    """'엄마랑 궁합'(텍스트 pairwise)은 companion_only로 오판되지 않는다 — 본인 base 유지 +
    동반자 명식 블록 주입. (base를 엄마로 교체하는 companion_only 디렉티브가 없어야 함.)"""
    r = chat_service.chat(
        _SELF, "엄마랑 궁합 어때?", today=_TODAY, dry_run=True,
        thread_id=f"t-{uuid.uuid4().hex[:8]}", subject_id="self1", subject_label="데굴",
        companion_alias_index=_alias_index(), companion_births={"mom1": _MOM},
    )
    txt = r.prompt_preview or ""
    assert "함께 보기 — 대상별 명식" in txt  # 동반자 블록 주입
    assert "[분석 대상]" not in txt  # companion_only 아님(본인 대체 아님)
    # 본인 일주(己亥)가 prefix 원국에 유지 — base가 엄마로 안 바뀜.
    assert "己亥" in txt.split("[기준 시점]")[0]
