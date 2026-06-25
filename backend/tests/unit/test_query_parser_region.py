"""이사 지명 추출(목적지·현재지) 회귀 — 실로그: '이사할집은 서울 중구야'.

버그: 지명이 '이사' 뒤에 오는 진술형('이사할집은 서울 중구야')·'현재는 X에 있는데' 어순을
추출 정규식이 못 잡아 target_region/location_base=None → 지역 오행 적합(region_fit)이 누락됨.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.query_parser import parse_message

_TODAY = date(2026, 6, 25)


def _con(text: str):
    return parse_message(text, _TODAY, birth_year=1980).intents[0].constraints


@pytest.mark.parametrize("text,target,base", [
    ("현재는 고양시 일산동구에 있는데 이사할집은 서울 중구야.", "서울 중구", "고양시 일산동구"),
    ("이사할집은 서울 중구야", "서울 중구", None),
    ("이사 갈 곳은 대전 서구예요", "대전 서구", None),
    ("서울 중구로 이사하려고 해", "서울 중구", None),  # 기존 어순 유지
    ("수원시로 가려고", "수원시", None),
    ("지금 사는 곳은 부산 해운대구인데 대전 서구로 이사", "대전 서구", "부산 해운대구"),
    ("부산 해운대구에 사는데 어때?", None, "부산 해운대구"),
])
def test_region_extraction(text: str, target: str | None, base: str | None) -> None:
    c = _con(text)
    assert c.target_region == target
    assert c.location_base == base


def test_non_relocation_text_no_region() -> None:
    c = _con("올해 이직운 어때?")
    assert c.target_region is None and c.location_base is None
