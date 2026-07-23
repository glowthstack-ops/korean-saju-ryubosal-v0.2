"""일주별 오늘의 운세 — LLM 배치 교정 검증 게이트 테스트 (LLM 목킹).

검증 항목: 구조 불일치·금지어·숫자 삽입·과장어·로또 유무 불변·잘린 JSONL 부분
채택·교정 후 중복 감사·polish 락 소유권·출력 토큰 예산 fixture.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_engines.daily_ilju_fortune import build_day_context, compute_board, load_daily_dicts
from saju_engines.llm_guard import CALL_LIMITS, estimate_tokens
from saju_shared_types.daily_fortune import CONTENT_VERSION

_D = date(2026, 7, 23)


@pytest.fixture(scope="module")
def board():
    return compute_board(build_day_context(_D), load_daily_dicts())


def _echo_response(board, transform=None) -> str:
    """원문을 그대로(또는 일부 변형해) 돌려주는 모의 LLM 응답."""
    lines = []
    for f in board.fortunes:
        rec = {
            "ilju": f.ilju,
            "headline": f.headline,
            "place_phrase": f.lucky_place.phrase,
            "lotto": f.lotto_phrase,
        }
        if transform:
            rec = transform(f, rec)
        lines.append(json.dumps(rec, ensure_ascii=False))
    return "\n".join(lines)


def test_full_success_marks_polished(board) -> None:
    # 원문 구조를 유지한 채 어미만 다듬은 응답(문장 수 불변) — 전건 채택되어야 한다
    def _t(f, rec):
        rec["headline"] = rec["headline"].replace("몰라요.", "몰라요!")
        return rec

    updated, audit = polish.validate_and_apply(board, _echo_response(board, _t))
    assert audit["accepted"] == 60 and audit["rejected"] == 0
    assert updated.polish_status == "POLISHED"
    assert all(f.polished for f in updated.fortunes)


def test_forbidden_terms_and_digits_rejected(board) -> None:
    bad_iljus = {board.fortunes[0].ilju, board.fortunes[1].ilju, board.fortunes[2].ilju}

    def _t(f, rec):
        if f.ilju == board.fortunes[0].ilju:
            rec["headline"] = "오늘은 편재의 기운이 강한 날이에요."  # 명리 용어
        elif f.ilju == board.fortunes[1].ilju:
            rec["headline"] = "오늘 100만원이 들어옵니다."  # 숫자·금액
        elif f.ilju == board.fortunes[2].ilju:
            rec["headline"] = "반드시 큰돈이 들어오는 날!"  # 확정+과장
        return rec

    updated, audit = polish.validate_and_apply(board, _echo_response(board, _t))
    assert audit["accepted"] == 57
    assert set(audit["reject_reasons"]) == bad_iljus
    for f in updated.fortunes:
        if f.ilju in bad_iljus:  # 원문 유지
            raw = next(x for x in board.fortunes if x.ilju == f.ilju)
            assert f.headline == raw.headline and not f.polished
    assert updated.polish_status == "PARTIAL"


def test_lotto_presence_immutable(board) -> None:
    no_lotto = next(f for f in board.fortunes if f.lotto_phrase is None)

    def _t(f, rec):
        if f.ilju == no_lotto.ilju:
            rec["lotto"] = "로또 한 장 어때요?"  # 없던 로또 추가 — 거부
        return rec

    _updated, audit = polish.validate_and_apply(board, _echo_response(board, _t))
    assert audit["reject_reasons"].get(no_lotto.ilju) == "lotto_presence_changed"


def test_place_name_must_remain(board) -> None:
    target = board.fortunes[5]

    def _t(f, rec):
        if f.ilju == target.ilju:
            rec["place_phrase"] = "오늘의 행운은 어딘가에 있어요."  # 장소명 삭제
        return rec

    _updated, audit = polish.validate_and_apply(board, _echo_response(board, _t))
    assert audit["reject_reasons"].get(target.ilju) == "place_name_missing"


def test_truncated_jsonl_partial_acceptance(board) -> None:
    full = _echo_response(board)
    lines = full.splitlines()
    truncated = "\n".join(lines[:40] + [lines[40][: len(lines[40]) // 2]])  # 41번째 줄 잘림
    updated, audit = polish.validate_and_apply(board, truncated)
    assert audit["accepted"] == 40
    assert audit["malformed_lines"] == 1
    assert len(audit["missing_iljus"]) == 20  # 잘린 41번째 줄 포함 미수신 20건
    assert updated.polish_status == "PARTIAL"


def test_duplicate_headline_after_polish_reverted(board) -> None:
    a, b = board.fortunes[0], board.fortunes[1]

    def _t(f, rec):
        if f.ilju in (a.ilju, b.ilju):
            rec["headline"] = "완전히 똑같은 문장이 되어버렸어요. 확인해 보세요."
        return rec

    updated, audit = polish.validate_and_apply(board, _echo_response(board, _t))
    assert audit["reject_reasons"].get(b.ilju) == "duplicate_after_polish"
    kept = next(f for f in updated.fortunes if f.ilju == a.ilju)
    reverted = next(f for f in updated.fortunes if f.ilju == b.ilju)
    assert kept.polished and not reverted.polished


def test_unknown_or_duplicate_ilju_lines(board) -> None:
    full = _echo_response(board)
    extra = json.dumps({"ilju": "없음", "headline": "x", "place_phrase": "y", "lotto": None})
    dup = full.splitlines()[0]
    _updated, audit = polish.validate_and_apply(board, full + "\n" + extra + "\n" + dup)
    assert audit["accepted"] == 60
    assert audit["malformed_lines"] == 1  # 알 수 없는 일주
    assert len(audit["duplicate_iljus"]) == 1


def test_polish_board_provider_failure_keeps_raw(board, monkeypatch) -> None:
    cache = InMemoryDailyFortuneCache()
    cache.save_board(_D, CONTENT_VERSION, board, 3600)

    def _boom(*args, **kwargs):
        raise RuntimeError("공급자 실패")

    monkeypatch.setattr(polish.llm_client, "generate_reading", _boom)
    result = polish.polish_board(cache, _D)
    assert result is not None and result["accepted"] == 0
    stored = cache.load_board(_D, CONTENT_VERSION)
    assert stored is not None and stored.polish_status == "FAILED"
    # FAILED 보드는 자동 재교정하지 않는다(날짜당 1회 원칙)
    assert polish.polish_board(cache, _D) is None


def test_polish_lock_single_owner(board, monkeypatch) -> None:
    cache = InMemoryDailyFortuneCache()
    cache.save_board(_D, CONTENT_VERSION, board, 3600)
    token = cache.acquire_lock("polish", _D, CONTENT_VERSION, 600)
    assert token is not None
    monkeypatch.setattr(
        polish.llm_client, "generate_reading", lambda *a, **k: _echo_response(board)
    )
    assert polish.polish_board(cache, _D) is None  # 락 미획득 — 소유권 없음


def test_output_budget_fixture(board) -> None:
    """60건 최대 길이 fixture 의 입력·예상 출력이 전용 한도 안에 드는지 검증."""
    limit = CALL_LIMITS["daily_fortune_polish"]
    payload = polish.build_polish_payload(board)
    assert estimate_tokens(payload + polish._SYSTEM) <= limit.max_input_tokens

    # 최악 출력: 모든 레코드가 상한 길이(한글) — 20% 헤드룸을 남기고 예산 내여야 한다
    worst_record = json.dumps({
        "ilju": "甲子",
        "headline": "가" * polish.MAX_HEADLINE_CHARS,
        "place_phrase": "나" * polish.MAX_PLACE_CHARS,
        "lotto": "다" * polish.MAX_LOTTO_CHARS,
    }, ensure_ascii=False)
    worst_output = "\n".join([worst_record] * 60)
    assert estimate_tokens(worst_output) <= limit.max_output_tokens * 0.8
