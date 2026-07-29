"""OA-10b aggregate·episode 기준선 — 대표값과 지문을 고정한다.

C2 에서는 legacy 의미를 **개선하지 않고 그대로 복제**한다. 이름과 실제 축이
어긋나는 부분(episode 최저값이 key 축, bottom 일주가 key 축, episode ID 접두사가
'family-coverage')도 보존 대상이다. 의미 개선은 parity 종료 후 별도 버전이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ARTIFACT = (
    Path(__file__).resolve().parents[2] / "compiled" / "oa10b_anchor_aggregates.json"
)

ANCHOR_AGGREGATE_FINGERPRINT = (
    "64499efdf51913b906bbb7cfd1846b61865c59240ee0bd4b930dc9eb83231050"
)
EPISODE_FINGERPRINT = (
    "c94c5a278de12c09ad51cc6c7774be4b193debf7f85d0b82877eced3d2ff4c04"
)
ARTIFACT_SHA256 = (
    "889f0eeeb178fe1fba679f100a407b3b7f8310bb14e559f3c364a9b2e2aa5a47"
)


@pytest.fixture(scope="module")
def artifact() -> dict:
    if not _ARTIFACT.exists():
        pytest.skip(
            "`python3 scripts/legacy_oa10b_aggregate.py` 로 생성한다(gitignore 대상)"
        )
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def test_fingerprints_are_pinned_in_full(artifact) -> None:
    """축약형이 아니라 64자리 전체를 고정한다."""
    assert artifact["anchor_aggregate_fingerprint"] == ANCHOR_AGGREGATE_FINGERPRINT
    assert artifact["episode_fingerprint"] == EPISODE_FINGERPRINT
    assert artifact["artifact_sha256"] == ARTIFACT_SHA256


def test_headline_counts(artifact) -> None:
    s = artifact["summary"]
    assert (s["anchors"], s["passing"], s["episodes"]) == (730, 262, 30)
    assert s["anchors_in_2025"] == 0
    assert s["duplicate_anchors"] == 0


def test_worst_values(artifact) -> None:
    a = artifact["anchors"]
    assert min(x["key_p10"] for x in a) == 14
    assert min(x["family_p10"] for x in a) == 14
    assert min(x["domain_p10"] for x in a) == 6


def test_transition_date_counts(artifact) -> None:
    t = artifact["transitions"]
    assert len(t["key"]["to_15_dates"]) == 29
    assert len(t["key"]["to_14_dates"]) == 28
    assert len(t["family"]["to_15_dates"]) == 30
    assert len(t["family"]["to_14_dates"]) == 29


def test_longest_episode(artifact) -> None:
    longest = max(artifact["episodes"], key=lambda e: e["duration_days"])
    assert longest["episode_id"] == "family-coverage:2027-06-01:2027-10-09"
    assert longest["duration_days"] == 131


def test_legacy_semantics_are_recorded_not_corrected(artifact) -> None:
    """이름과 축이 어긋난 부분을 그대로 보존했는지."""
    sem = artifact["semantics"]
    assert sem["domain_gate_applied"] is False
    assert sem["episode_minimum_axis"] == "KEY"
    assert sem["bottom_ilju_axis"] == "KEY"
    assert sem["affected_ilju_order"] == "sorted_unique"
    assert sem["episode_id_prefix_semantics"] == "LEGACY_LABEL_NOT_AUTHORITATIVE"
    assert sem["episode_trigger_semantics"] == "COMBINED_KEY_AND_FAMILY_GATE_FAILURE"
    # 개선판에서만 쓸 필드가 기준선에 섞이면 안 된다.
    for forbidden in ("minimum_family_p10", "pass_domain_gate"):
        assert all(forbidden not in e for e in artifact["episodes"])


def test_evidence_chain_is_recorded(artifact) -> None:
    """어느 바이트에서 나왔는지 저장소 안에서 다시 증명할 수 있어야 한다."""
    for key in ("source_builder_sha256", "source_rows_artifact_sha256",
                "legacy_oa10b_output_sha256"):
        assert len(artifact[key]) == 64


def test_episode_fingerprint_is_independent_of_anchors(artifact) -> None:
    """episode 가 불변인데 anchor 변화로 지문이 움직이면 진단성이 없다."""
    import hashlib

    recomputed = hashlib.sha256(
        json.dumps(
            {"schema": artifact["episode_schema_version"],
             "episodes": artifact["episodes"]},
            ensure_ascii=False, sort_keys=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert recomputed == artifact["episode_fingerprint"]
