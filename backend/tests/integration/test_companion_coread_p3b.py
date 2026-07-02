"""동반자 공동 풀이 P3b(compare_exclude_self) — 동반자 A vs B, 본인 제외.

'엄마랑 아빠 궁합/잘 맞아?' 같은 동반자끼리 비교는 본인 명식을 쓰지 않고 두 동반자만
분석한다(A=base, B=블록). 비교 대상 중 birth가 없으면 self fallback 대신 확인 요청.
thread 경로(대화 엔진 + alias_index) 필요 — DB 미구성 시 skip.
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
    reason="compare_exclude_self는 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)

_TODAY = date(2026, 7, 2)
_SELF = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)  # 일주 己亥
_MOM = BirthInput(
    birth_date="1955-06-10", birth_time="08:00", birth_place_name="서울", gender="female",
)  # 일주 壬寅
_DAD = BirthInput(
    birth_date="1952-03-20", birth_time="06:00", birth_place_name="서울", gender="male",
)


def _idx() -> dict:
    recs = [
        SubjectRecord(subject_id="self1", owner_id="u1", kind="self", label="데굴", birth=_SELF),
        SubjectRecord(
            subject_id="mom1", owner_id="u1", kind="companion", label="김여사",
            relation_to_user="mother", birth=_MOM,
        ),
        SubjectRecord(
            subject_id="dad1", owner_id="u1", kind="companion", label="박선생",
            relation_to_user="father", birth=_DAD,
        ),
    ]
    return build_companion_alias_index(recs, base_subject_id="self1")


def _dry(question: str, births: dict) -> chat_service.ChatResponse:
    return chat_service.chat(
        _SELF, question, today=_TODAY, dry_run=True, thread_id=f"t-{uuid.uuid4().hex[:8]}",
        subject_id="self1", subject_label="데굴",
        companion_alias_index=_idx(), companion_births=births,
    )


def test_compare_excludes_self_reads_both_companions() -> None:
    """'엄마랑 아빠 궁합' → 본인(己亥) 미사용, 두 동반자 블록 + 비교 디렉티브."""
    r = _dry("엄마랑 아빠 궁합 봐줘", {"mom1": _MOM, "dad1": _DAD})
    txt = r.prompt_preview or ""
    assert r.status == "dry_run"
    assert "己亥" not in txt.split("[기준 시점]")[0]  # 본인이 base가 아님
    assert "함께 보기 — 대상별 명식" in txt
    assert "김여사" in txt and "박선생" in txt
    assert "두 동반자의 관계 비교" in txt


def test_compare_via_jal_majda_phrasing() -> None:
    """'잘 맞아?'(도메인 키워드)도 관계 비교로 통과 — too_broad에 빠지지 않음."""
    r = _dry("엄마랑 아빠는 잘 맞아?", {"mom1": _MOM, "dad1": _DAD})
    assert r.status == "dry_run"
    assert "함께 보기 — 대상별 명식" in (r.prompt_preview or "")


def test_compare_missing_one_birth_asks_clarification() -> None:
    """비교 대상 중 한 명 birth 없음 → self fallback 금지, need_subject."""
    r = _dry("엄마랑 아빠 궁합 봐줘", {"mom1": _MOM})
    assert r.status == "need_subject"


def test_compare_does_not_flip_per_subject_incorrectly() -> None:
    """compare는 본인 미포함 — 본인 명식 서술 디렉티브가 아니라 비교 디렉티브가 실린다."""
    r = _dry("엄마랑 아빠 궁합 봐줘", {"mom1": _MOM, "dad1": _DAD})
    txt = r.prompt_preview or ""
    # companion_only 단일 대상 디렉티브가 아니라 비교 디렉티브여야 한다.
    assert "한 사람입니다" not in txt
    assert "두 동반자의 관계 비교" in txt
