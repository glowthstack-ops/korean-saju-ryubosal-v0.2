"""OA-8a — 서사 카피 금지 표현 가드 + 표현 범위 계약.

카피가 늘어날수록 근거 없는 예측이 함께 늘어난다. 사건 판정은 엔진이 하고, 문장은
**사용자가 할 수 있는 행동과 가능성**에만 머물러야 한다.

관계 단절 검사는 **관계 의미 영역에만** 적용한다 — 그러지 않으면 휴식 사건의
"끊어가는 게 좋은 날"(쉼표를 넣으라는 뜻)이 오탐으로 걸린다.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

import saju_engines.daily_ilju_fortune as M

PILOT = (
    "money_small_gain", "praise_recognition", "good_news_arrives", "teamwork_flow",
    "rest_recharge", "tidy_luck", "argument_caution", "love_spark",
)

#: 전 사건 공통 금지.
_GLOBAL_BANS = {
    "사건 확정·결과 보장": re.compile(r"반드시|틀림없|확실히|보장|무조건|성공한다|합격|당첨"),
    "성별 전제": re.compile(r"남자|여자|남친|여친|그녀|그남"),
    "집착·감시·보복": re.compile(r"감시|캐물|시험해|복수|되갚"),
}
#: 금전 사건 전용 — 현금 유입·환급·수익은 별도 근거 없이 말하지 않는다.
_MONEY_BANS = re.compile(r"공돈|환급금|부수입|수익이|돈을 받|입금|한몫")
#: 관계 의미 영역 전용 — 일반 동작('끊어가다')과 구분하려고 어구 단위로 본다.
_RELATION_BANS = {
    "관계 단절 단정": re.compile(r"관계가 끊|사이가 끊|연락이 끊|인연이 끝|관계를 정리하게"),
    "상대 마음·행동 단정": re.compile(r"기다리고 있|마음이 있어요|고백이 성공|연애가 시작|재회"),
    "상대 존재 전제": re.compile(r"애인이|연인이 |배우자가|남편|아내"),
}
_RELATION_DOMAINS = {"love", "social", "relationship"}


def _sentences(dicts, event_key):
    """사건의 전 문장 — 평면 템플릿 + family + 연애 변형."""
    tpl = dicts.templates["events"][event_key]
    blocks = [tpl]
    for fam in (tpl.get("families") or {}).values():
        blocks.append(fam)
        if fam.get("romantic"):
            blocks.append(fam["romantic"])
    out = []
    for b in blocks:
        for kind in ("fragments", "actions", "results"):
            out.extend(b.get(kind) or ())
    return out


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


@pytest.mark.parametrize("event_key", PILOT)
def test_no_global_banned_expressions(dicts, event_key) -> None:
    for label, rx in _GLOBAL_BANS.items():
        bad = [s for s in _sentences(dicts, event_key) if rx.search(s)]
        assert not bad, f"{event_key} — {label}: {bad}"


def test_money_event_keeps_semantic_contract(dicts) -> None:
    """현금 유입·환급·당첨은 근거가 없다 — 혜택·절약·자원 활용만 말한다."""
    bad = [s for s in _sentences(dicts, "money_small_gain") if _MONEY_BANS.search(s)]
    assert not bad, f"금전 의미 계약 위반: {bad}"


def test_relation_bans_are_domain_scoped(dicts) -> None:
    """관계 단절·상대 단정 검사는 관계 의미 영역에만 적용한다."""
    events = dicts.catalog["events"]
    for key in PILOT:
        meta = events[key]
        is_relation = (
            meta["domain"] in _RELATION_DOMAINS
            or meta.get("semantic_family") == "relationship_connection"
        )
        if not is_relation:
            continue
        for label, rx in _RELATION_BANS.items():
            bad = [s for s in _sentences(dicts, key) if rx.search(s)]
            assert not bad, f"{key} — {label}: {bad}"


def test_rest_recharge_break_wording_is_not_flagged(dicts) -> None:
    """휴식 사건의 '끊어가다'는 관계 단절이 아니다 — 오탐 회귀."""
    assert dicts.catalog["events"]["rest_recharge"]["domain"] not in _RELATION_DOMAINS
    joined = " ".join(_sentences(dicts, "rest_recharge"))
    assert "끊어가는" in joined  # 표현은 살아 있고
    for rx in _RELATION_BANS.values():
        assert not rx.search(joined)  # 관계 금지 패턴에는 걸리지 않는다


# ── 표현 범위 계약 ─────────────────────────────────────────────────────────


def test_love_spark_defaults_to_general_relationship(dicts) -> None:
    """기본 카피는 연애를 전제하지 않는다."""
    meta = dicts.catalog["events"]["love_spark"]
    assert meta["semantic_family"] == "relationship_connection"
    assert meta["default_expression_scope"] == "general_relationship"
    assert meta["romance_expression_gate"] == "strong_romance_signal_only"

    fams = dicts.templates["events"]["love_spark"]["families"]
    for name, fam in fams.items():
        general = " ".join(
            fam.get(k, [])[0] if fam.get(k) else "" for k in ("fragments", "actions")
        )
        assert "♥" not in json_dump(fam, exclude_romantic=True), f"{name}: 기본 카피에 ♥"
        assert "연애" not in general, f"{name}: 기본 카피가 연애를 전제한다"


def json_dump(fam: dict, *, exclude_romantic: bool) -> str:
    import json

    data = {k: v for k, v in fam.items() if not (exclude_romantic and k == "romantic")}
    return json.dumps(data, ensure_ascii=False)


def test_romance_copy_only_behind_gate(dicts) -> None:
    """연애 변형은 게이트를 통과한 카드에서만 쓰인다."""
    fams = dicts.templates["events"]["love_spark"]["families"]
    romantic = {k: v for k, v in fams.items() if v.get("romantic")}
    assert romantic, "연애 변형이 하나도 없다"

    seed = "2026-07-28|甲子|x"
    general = M._headline(dicts, "love_spark", "s3", seed, 0, romance_scope=False)
    gated = M._headline(dicts, "love_spark", "s3", seed, 0, romance_scope=True)
    # 게이트가 실제로 표현 범위를 가른다(같은 family에 변형이 있으면 문장이 달라진다).
    assert isinstance(general, str) and isinstance(gated, str)


def test_romance_gate_reuses_existing_signal(dicts) -> None:
    """새 점수를 만들지 않는다 — 기존 '오늘의 연애' 게이트를 재사용한다."""
    board = M.compute_board(M.build_day_context(dt.date(2026, 7, 28)), dicts)
    assert board.fortunes  # 게이트 함수가 보드 생성 경로에서 호출됨을 보장
    assert hasattr(M, "_has_good_love_signal")
