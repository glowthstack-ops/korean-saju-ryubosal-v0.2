"""OA-6d1 — 선택 seed 계약과 콘텐츠 버전의 분리.

예전에는 선택 seed에 `CONTENT_VERSION`(= `DICT_VERSION` 포함)이 들어 있어서 **문구
오타 하나만 고쳐도 사용자 3.7%의 오늘 사건이 바뀌었다**(실측). 표현을 개선할수록
사건이 흔들리는 구조라, 서사 축을 넓히는 작업과 정면으로 충돌한다.

    선택 seed   어떤 동점 후보를 고르는가   ← 선택 계약이 바뀔 때만
    캐시 키     현재 사전으로 만든 결과인가  ← DICT_VERSION 유지
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M

_START = dt.date(2026, 7, 1)
_DAYS = 7


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


def _boards(dicts, days: int = _DAYS):
    return [
        M.compute_board(M.build_day_context(_START + dt.timedelta(days=i)), dicts)
        for i in range(days)
    ]


def _selection(board):
    return [
        (f.ilju, str(f.headline_event_key), f.lucky_place.place_key,
         tuple(sorted((e.slot, e.event_key, e.probability) for e in f.events)))
        for f in board.fortunes
    ]


# ── 콘텐츠 버전은 선택에 영향을 주지 않는다 ─────────────────────────────────


def test_content_version_is_not_in_selection_seed(dicts, monkeypatch) -> None:
    """콘텐츠 버전이 바뀌어도 사건 선택이 그대로여야 한다.

    엔진은 이제 `CONTENT_VERSION` 을 import 조차 하지 않는다 — 보드에 찍는 값은
    `content_version_for(날짜)` 이며 선택 seed 와 무관하다.
    """
    import saju_shared_types.daily_fortune as V

    before = [_selection(b) for b in _boards(dicts, 3)]

    monkeypatch.setattr(
        M, "content_version_for", lambda _d: "engine.v9|dict.v9.9|polish.v9"
    )
    after = [_selection(b) for b in _boards(dicts, 3)]

    assert before == after, "콘텐츠 버전이 아직 선택 seed에 남아 있다"
    assert "CONTENT_VERSION" not in M.EVENT_SELECTION_COMPAT_SALT
    assert V.DICT_VERSION not in M.EVENT_SELECTION_COMPAT_SALT


def test_selection_contract_constants_exist() -> None:
    """계약 네임스페이스가 역할별로 분리돼 있다."""
    assert M.EVENT_SELECTION_CONTRACT == "event-selection.v1-legacy-frozen"
    assert M.BOARD_REBALANCE_VERSION
    assert M.NARRATIVE_SEED_VERSION
    # 호환 salt 는 과거 콘텐츠 버전 문자열을 **동결**한 값이다(앞으로 바뀌지 않는다).
    assert "dict.v1.9" in M.EVENT_SELECTION_COMPAT_SALT


# ── 문구·사전 변경이 선택을 흔들지 않는다 ───────────────────────────────────


def test_copy_change_does_not_move_events(dicts) -> None:
    """문장만 바꾸면 사건 선택과 서사 family 선택이 모두 그대로다."""
    patched = M.DailyFortuneDicts(
        catalog=dicts.catalog,
        templates=copy.deepcopy(dicts.templates),
        places=dicts.places,
    )
    fam = patched.templates["events"]["tidy_luck"]["families"]["desk_clear"]
    fam["fragments"] = ["(오타 수정) " + s for s in fam["fragments"]]

    base = [_selection(b) for b in _boards(dicts, 3)]
    after = [
        _selection(M.compute_board(M.build_day_context(_START + dt.timedelta(days=i)), patched))
        for i in range(3)
    ]

    assert base == after


def test_adding_family_does_not_move_events(dicts) -> None:
    """서사 family 추가는 event_key를 0건도 바꾸지 않는다."""
    patched = M.DailyFortuneDicts(
        catalog=copy.deepcopy(dicts.catalog),
        templates=copy.deepcopy(dicts.templates),
        places=dicts.places,
    )
    modes = patched.catalog["events"]["tidy_luck"]["narrative_modes"]
    modes[0]["template_families"].append("zzz_new_family")
    patched.templates["events"]["tidy_luck"]["families"]["zzz_new_family"] = {
        "fragments": ["새 장면입니다."], "actions": ["새 행동입니다."],
        "results": ["새 결과입니다."],
    }

    base_keys = [
        [str(f.headline_event_key) for f in b.fortunes] for b in _boards(dicts, 3)
    ]
    after_keys = [
        [
            str(f.headline_event_key)
            for f in M.compute_board(
                M.build_day_context(_START + dt.timedelta(days=i)), patched
            ).fortunes
        ]
        for i in range(3)
    ]

    assert base_keys == after_keys


# ── 후보별 안정 해시 — 배열 순서에 흔들리지 않는다 ──────────────────────────


def test_narrative_selection_is_order_independent(dicts) -> None:
    """모드·family 배열 순서를 뒤집어도 같은 서사가 선택된다.

    인덱스 기반(`seed % len`)이면 JSON 정렬만 바뀌어도 전 배정이 재편된다.
    """
    shuffled = M.DailyFortuneDicts(
        catalog=copy.deepcopy(dicts.catalog),
        templates=dicts.templates,
        places=dicts.places,
    )
    for key in ("money_small_gain", "love_spark", "rest_recharge"):
        modes = shuffled.catalog["events"][key]["narrative_modes"]
        modes.reverse()
        for m in modes:
            m["template_families"] = list(reversed(m["template_families"]))

    seed = f"2026-07-28|甲子|{M.EVENT_SELECTION_COMPAT_SALT}"
    for key in ("money_small_gain", "love_spark", "rest_recharge"):
        assert M.resolve_narrative(dicts, key, seed) == M.resolve_narrative(
            shuffled, key, seed
        )


def test_narrative_is_deterministic(dicts) -> None:
    seed = f"2026-07-28|乙丑|{M.EVENT_SELECTION_COMPAT_SALT}"
    assert M.resolve_narrative(dicts, "love_spark", seed) == M.resolve_narrative(
        dicts, "love_spark", seed
    )


def test_narrative_varies_across_ilju(dicts) -> None:
    """일주가 다르면 서사도 갈린다 — 축이 실제로 작동하는지."""
    seen = {
        M.resolve_narrative(
            dicts, "money_small_gain", f"2026-07-28|{i}|{M.EVENT_SELECTION_COMPAT_SALT}"
        )
        for i in range(60)
    }
    assert len(seen) > 3


# ── 처리 순서·재생성 ───────────────────────────────────────────────────────


def test_board_is_reproducible_across_calls(dicts) -> None:
    a = M.compute_board(M.build_day_context(_START), dicts)
    b = M.compute_board(M.build_day_context(_START), dicts)

    assert _selection(a) == _selection(b)
    assert [f.headline for f in a.fortunes] == [f.headline for f in b.fortunes]


def test_event_catalog_order_does_not_change_selection(dicts) -> None:
    """사전 사건 배열 순서를 바꿔도 선택 결과가 같다."""
    reordered = M.DailyFortuneDicts(
        catalog=copy.deepcopy(dicts.catalog),
        templates=dicts.templates,
        places=dicts.places,
    )
    events = reordered.catalog["events"]
    reordered.catalog["events"] = dict(reversed(list(events.items())))

    base = _selection(M.compute_board(M.build_day_context(_START), dicts))
    after = _selection(M.compute_board(M.build_day_context(_START), reordered))

    assert base == after
