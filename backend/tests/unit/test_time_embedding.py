"""TimeBucket 임베딩 시점 분류기 + 버킷→날짜 결정론 변환 검증.

버킷→TimeRange(bucket_to_range)는 모델 없이 결정론으로 항상 검증한다. 임베딩 분류기(classify)는
ONNX 모델/의존성이 있을 때만(available) 동작 — 없으면 graceful 비활성(절대원칙 11).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.time_embedding import get_time_classifier
from saju_engines.time_parser import bucket_to_range
from saju_shared_types.intent import Granularity

_TODAY = date(2026, 6, 20)


# ── 버킷 → 날짜 결정론 변환(모델 불필요) ──────────────────────────


def test_bucket_rolling_week() -> None:
    tr, _ = bucket_to_range("rolling_week", _TODAY, "2026-06")
    assert tr.granularity is Granularity.DAY
    assert tr.start == "2026-06-20" and tr.end == "2026-06-26"


def test_bucket_this_and_next_month() -> None:
    tm, _ = bucket_to_range("this_month", _TODAY, "2026-06")
    assert tm.granularity is Granularity.MONTH and tm.start == tm.end == "2026-06"
    nm, _ = bucket_to_range("next_month", _TODAY, "2026-06")
    assert nm.start == nm.end == "2026-07"


def test_bucket_this_and_next_year() -> None:
    ty, _ = bucket_to_range("this_year", _TODAY, "2026-06")
    assert ty.granularity is Granularity.YEAR and ty.start == ty.end == "2026"
    ny, _ = bucket_to_range("next_year", _TODAY, "2026-06")
    assert ny.start == ny.end == "2027"


def test_non_synthesizing_buckets_return_none() -> None:
    # 막연 미래·과거 회고·구조·미등록은 합성하지 않는다(다운스트림 위임).
    for label in ("vague_future", "past_retro", "timeless", "unknown_bucket"):
        tr, _ = bucket_to_range(label, _TODAY, "2026-06")
        assert tr is None, label


# ── 임베딩 분류기(모델 있을 때만) ─────────────────────────────────


def _clf():
    clf = get_time_classifier()
    if not clf.available():
        pytest.skip("ONNX 시점 분류기 비활성(의존성/모델 부재) — graceful")
    return clf


def test_classifier_maps_concrete_phrases() -> None:
    clf = _clf()
    # 규칙이 놓치는 변형 표현이 의도한 버킷 군으로 분류된다.
    assert clf.classify("요 며칠 사이에").label == "rolling_week"
    assert clf.classify("가까운 시일에").label == "rolling_month"
    assert clf.classify("오는 해 운세").label == "next_year"


def test_classifier_non_time_to_anchor_buckets() -> None:
    clf = _clf()
    # 시점 없는 구조/막연 질문은 비합성 버킷으로 빠진다(오합성 방지 앵커).
    assert clf.classify("나는 어떤 기질이야").label in ("timeless", "vague_future")


def test_classifier_deterministic() -> None:
    clf = _clf()
    a = clf.classify("가까운 시일에 재물운")
    b = clf.classify("가까운 시일에 재물운")
    assert (a.label, a.score, a.margin) == (b.label, b.score, b.margin)
