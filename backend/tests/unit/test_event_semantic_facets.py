"""채널 중립 이벤트 의미 facet 계약 (2026-07-30 데굴님 확정 — 가′).

facet 은 섹션 라우팅용 **메타데이터**다. 점수·극성·confidence·성사 판정에 관여하지
않는다. 여기서 고정하는 것은 세 가지다.

  ① fail-closed 를 **축 단위**로 한다 — `wealth_change` 는 family 는 알지만 subtype 과
     process_role 은 모른다. 키 전체를 버리지 않는다.
  ② `stage_tags` 는 기존 SSOT 가 부여한 값만 쓴다 — 관계 3키를 로드맵 6단계에 강제
     배분하지 않는다(현재 확정 매핑이 없어 비어 있는 것이 계약이다).
  ③ 미등록 키는 family 까지 UNKNOWN 이므로 세부 라우팅에서 자동 제외된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (_BACKEND / "packages" / "shared_types",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_shared_types.event_taxonomy_v2 import (  # noqa: E402
    EVENT_DOMAIN,
    EVENT_FAMILY,
    EVENT_PROCESS_ROLE,
    EVENT_STAGE_TAGS,
    FACET_UNKNOWN,
    event_facets,
)

# ── ① 축 단위 fail-closed ────────────────────────────────────────────────


def test_wealth_change_keeps_family_but_closes_unknown_axes() -> None:
    """umbrella 키를 통째로 버리면 W-04 라우팅까지 잃는다."""
    f = event_facets("wealth_change")
    assert f["event_family"] == "wealth_change"      # 아는 축은 살린다
    assert f["process_role"] == FACET_UNKNOWN        # 수입·지출·정산 미분화
    assert f["subtype"] == FACET_UNKNOWN


def test_windfall_has_a_confirmed_process_role() -> None:
    """의미가 명확한 키는 role 까지 확정한다 — W-05 DIRECT 의 근거."""
    f = event_facets("windfall")
    assert (f["event_family"], f["process_role"]) == ("windfall", "unexpected_gain")


def test_marriage_signal_role_is_not_inferred_from_the_name() -> None:
    """이름만 보고 `formalization` 으로 추론하지 않는다 — 확정 매핑이 없다."""
    assert event_facets("marriage_signal")["process_role"] == FACET_UNKNOWN


# ── ② stage_tags 는 비어 있는 것이 계약 ──────────────────────────────────


def test_stage_tags_are_empty_until_the_ssot_assigns_them() -> None:
    """관계 3키를 6단계에 강제 배분하면 없는 근거를 만들어 낸다."""
    assert EVENT_STAGE_TAGS == {}
    for key in ("new_relationship", "relationship_change", "marriage_signal"):
        assert event_facets(key)["stage_tags"] == ()


# ── ③ 미등록 키 ──────────────────────────────────────────────────────────


def test_unregistered_key_is_unknown_on_every_axis() -> None:
    """모르는 키가 넓은 사건군에 임의 편입되면 세부 섹션이 오염된다."""
    f = event_facets("no_such_event_key")
    assert f["event_family"] == FACET_UNKNOWN
    assert f["process_role"] == FACET_UNKNOWN
    assert f["stage_tags"] == ()


# ── 커버리지·정합성 ──────────────────────────────────────────────────────


#: 다섯 테마 후보 풀에서 실측된 고유 event_key(2026-07-30 인벤토리 17종). 승인된
#: facet 매핑의 범위와 같다.
THEME_POOL_KEYS = (
    "business_expansion", "business_start", "career_change", "contract_document",
    "creative_output", "job_gain", "legal_conflict", "marriage_signal",
    "new_relationship", "preparation_delay", "promotion", "public_exposure",
    "relationship_change", "relocation", "social_conflict", "wealth_change",
    "windfall",
)

#: 도메인에는 있으나 facet 이 아직 승인되지 않은 키. fail-closed 로 DIRECT 세부
#: 라우팅에서 제외된다 — 잊히지 않게 여기 고정한다(임의 편입 금지).
UNMAPPED_BY_DESIGN = ("childbirth",)


@pytest.mark.parametrize("event_key", THEME_POOL_KEYS)
def test_theme_pool_keys_have_a_confirmed_family(event_key: str) -> None:
    """테마 후보 풀에 실제로 등장하는 키는 family 가 확정돼 있어야 한다.

    비어 있으면 그 키는 DIRECT 라우팅에서 조용히 빠진다.
    """
    assert event_facets(event_key)["event_family"] != FACET_UNKNOWN


@pytest.mark.parametrize("event_key", UNMAPPED_BY_DESIGN)
def test_unapproved_keys_stay_unmapped_and_are_excluded(event_key: str) -> None:
    """승인되지 않은 키에 facet 을 임의로 붙이지 않는다.

    `childbirth` 는 relationship 도메인이지만 승인 표(17종)에 없다. 지금 넓은 사건군에
    편입하면 R-04 같은 세부 섹션이 근거 없이 오염된다 — fail-closed 가 맞다. facet 이
    필요해지면 별건으로 승인받는다.
    """
    assert event_key in {str(k) for k in EVENT_DOMAIN}
    assert event_facets(event_key)["event_family"] == FACET_UNKNOWN


def test_approved_facet_scope_matches_the_inventory() -> None:
    """facet 테이블이 승인 범위(17종)에서 벗어나면 드러난다."""
    assert set(EVENT_FAMILY) == {  # type: ignore[comparison-overlap]
        k for k in EVENT_DOMAIN if str(k) in THEME_POOL_KEYS
    }


def test_family_and_role_tables_cover_the_same_keys() -> None:
    """한쪽만 등록되면 조회 결과가 축마다 어긋난다."""
    assert set(EVENT_FAMILY) == set(EVENT_PROCESS_ROLE)


def test_facets_never_expose_score_or_polarity_fields() -> None:
    """facet 은 라우팅 메타데이터다 — 판정 필드가 섞이면 계약이 무너진다."""
    keys = set(event_facets("wealth_change"))
    assert keys == {"event_family", "process_role", "stage_tags", "subtype"}
    assert not keys & {"score", "polarity", "confidence", "favorability"}
