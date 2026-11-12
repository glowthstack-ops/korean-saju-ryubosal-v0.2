"""docs/17 §32 — 오늘의 운세 상해 채널의 백호를 일주 기준으로 (2026-11-13 데굴님 지시).

"오늘의 운세 백호채널을 추가 개선해."

원국·운 신살은 2026-11-12 부터 '백호는 일주가 백호 간지일 때만 성립'으로 본다. 오늘의 운세는 그날
일진이 백호 간지면 일주와 무관하게 60일주 전부에 상해 채널 .6 을 붙이고 있었다. 날짜 경계
(BAEKHO_DAY_BASIS_EFFECTIVE_FROM, 11/14)부터 일주도 백호 간지일 때만 붙이고, 과거 날짜는 그날
계약(model.v2.3)으로 재생된다.
"""

from __future__ import annotations

import datetime as dt

from saju_manse_analysis.sinsal import sinsal_catalog as sc

from saju_engines import daily_ilju_fortune as M
from saju_engines.daily_fortune_v2 import content_version_v2_for, day_channels, sinsal_channels
from saju_shared_types.daily_fortune import (
    BAEKHO_DAY_BASIS_EFFECTIVE_FROM,
    active_dict_version,
    baekho_needs_day_pillar,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    MODEL_V2_VERSION_BEFORE_BAEKHO_DAY_BASIS,
    active_model_v2_version,
)
from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S

_FROM = BAEKHO_DAY_BASIS_EFFECTIVE_FROM  # 2026-11-14
_BEFORE = _FROM - dt.timedelta(days=1)
_BAEKHO_DAY = dt.date(2026, 11, 17)  # 일진 乙未 — 백호 간지


def test_boundary_selects_model_version_and_keeps_dict_version() -> None:
    assert not baekho_needs_day_pillar(_BEFORE) and baekho_needs_day_pillar(_FROM)
    assert active_model_v2_version(_BEFORE) == MODEL_V2_VERSION_BEFORE_BAEKHO_DAY_BASIS
    assert MODEL_V2_VERSION_BEFORE_BAEKHO_DAY_BASIS == "model.v2.3"
    assert active_model_v2_version(_FROM) == MODEL_V2_VERSION == "model.v2.4"
    # 사전 문구는 그대로다 — dict 버전은 경계 앞뒤가 같고, 캐시 키는 model 버전으로 갈린다.
    assert active_dict_version(_BEFORE) == active_dict_version(_FROM)
    assert content_version_v2_for(_BEFORE) != content_version_v2_for(_FROM)


def test_baekho_channel_needs_both_today_and_day_pillar() -> None:
    month = B.HAE
    # 오늘 일진 乙未(백호) × 일주 甲辰(백호) → .6
    both = sinsal_channels(S.GAP, B.JIN, S.EUL, B.MI, month)
    assert both["sinsal_hazard"] == 0.6
    # 반례 ①: 일주 丙寅(백호 아님) — 오늘이 백호 일진이어도 붙지 않는다.
    not_mine = sinsal_channels(S.BYEONG, B.IN, S.EUL, B.MI, month)
    assert not_mine["sinsal_hazard"] == 0.0
    # 반례 ②: 일주가 백호여도 오늘 일진이 백호가 아니면 붙지 않는다(丙寅일 — 현침도 아님).
    not_today = sinsal_channels(S.GAP, B.JIN, S.BYEONG, B.IN, month)
    assert not_today["sinsal_hazard"] == 0.0
    # 종전 규칙 재생: baekho_day_basis=False 면 일주와 무관하게 .6
    legacy = sinsal_channels(S.BYEONG, B.IN, S.EUL, B.MI, month, baekho_day_basis=False)
    assert legacy["sinsal_hazard"] == 0.6


def test_other_hazard_sources_are_untouched() -> None:
    month = B.HAE
    # 양인(甲 일간 × 오늘 卯)은 그대로 1.0, 현침(오늘 글자 甲·辛·卯·午·申)은 그대로 .4.
    assert sinsal_channels(S.GAP, B.JA, S.JEONG, B.MYO, month)["sinsal_hazard"] == 1.0
    assert sinsal_channels(S.BYEONG, B.IN, S.GAP, B.JA, month)["sinsal_hazard"] == 0.4
    # 백호 일진이면서 현침 글자가 없는 날(乙未) — 백호 아닌 일주는 0, 현침 글자가 있는 백호 일진
    # (甲辰)은 현침 몫 .4 가 남는다.
    assert sinsal_channels(S.BYEONG, B.IN, S.GAP, B.JIN, month)["sinsal_hazard"] == 0.4


def test_day_channels_follow_the_date_boundary() -> None:
    """같은 백호 일진이라도 경계 뒤 날짜에서만 일주를 본다 — 과거 날짜는 그날 계약으로 재생."""
    assert (S.EUL, B.MI) in sc.BAEKHO
    ctx = M.build_day_context(_BAEKHO_DAY)
    assert (ctx.day_stem, ctx.day_branch) == ("乙", "未") or (
        str(ctx.day_stem), str(ctx.day_branch)
    ) == ("乙", "未")
    assert day_channels(S.GAP, B.JIN, ctx)["sinsal_hazard"] == 0.6      # 甲辰 일주(백호)
    assert day_channels(S.BYEONG, B.IN, ctx)["sinsal_hazard"] == 0.0    # 丙寅 일주
    # 경계 이전의 백호 일진(2026-11-08 丙戌)은 종전 규칙 — 백호 아닌 일주에도 .6.
    past = M.build_day_context(dt.date(2026, 11, 8))
    assert (S(str(past.day_stem)), B(str(past.day_branch))) in sc.BAEKHO
    assert day_channels(S.BYEONG, B.IN, past)["sinsal_hazard"] >= 0.6
