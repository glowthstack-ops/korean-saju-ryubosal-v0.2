"""동결 증거를 실행 코드가 덮어쓰지 못하게 한다.

실제로 5-anchor 진단 실행이 730-anchor 공식 증거를 밀어낸 적이 있다. 복구는 됐지만
같은 일이 다시 가능하면 그 파일은 동결된 것이 아니다.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from saju_engines.daily_audit_output import (
    EVIDENCE_RELATIVE_PATHS,
    AuditDirectorySyncError,
    AuditEvidenceOverwriteError,
    CanonicalExpectation,
    CanonicalWriteClaim,
    assert_may_write_evidence,
    atomic_write_json,
    fingerprint_public_payload,
    is_evidence_path,
    write_audit_output,
)
from saju_engines.daily_rolling_audit_aggregate import (
    CONTRACT_MODE_CANONICAL,
    CONTRACT_MODE_DIAGNOSTIC,
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    RollingAuditAggregateContract,
    contract_mode,
    derive_diagnostic_contract,
)

_REPO = Path(__file__).resolve().parents[3]
_EXPECTED = CanonicalExpectation(
    anchor_days=730,
    first_anchor="2026-01-01",
    last_anchor="2027-12-31",
    anchor_fingerprint="a" * 64,
    episode_fingerprint="b" * 64,
)


def _payload() -> dict:
    """공개 결과 모사 — 키 순서도 계약의 일부다."""
    return {
        "summary": {"total_anchors": 730},
        "daily": [{"anchor_date": "2026-01-01", "key_p10": 15, "passes": True}],
        "episodes": [{"episode_start": "2026-06-01", "duration_days": 131}],
        "repeatedly_below_iljus": {"戊辰": 309, "庚戌": 268},
    }


_PAYLOAD = _payload()


def _claim(**over) -> CanonicalWriteClaim:
    base = {
        "contract_mode": CONTRACT_MODE_CANONICAL,
        "anchor_days": 730,
        "first_anchor": "2026-01-01",
        "last_anchor": "2027-12-31",
        "anchor_fingerprint": "a" * 64,
        "episode_fingerprint": "b" * 64,
        "projection_verified": True,
        "public_schema_version": "oa10b-public.v1",
        "public_payload_sha256": fingerprint_public_payload(_PAYLOAD),
    }
    base.update(over)
    return CanonicalWriteClaim(**base)


# ── 경로 판정은 정규화된 실제 경로로 ──────────────────────────────────────


def test_evidence_path_is_matched_after_resolution() -> None:
    """문자열 비교는 상대·절대·`./` 우회로 뚫린다."""
    rel = EVIDENCE_RELATIVE_PATHS[0]
    # `.` · `..` 를 섞은 경로도 정규화 후 같은 파일이면 증거로 판정돼야 한다.
    candidates = (
        _REPO / rel,
        _REPO / "doc" / ".." / rel,
        _REPO / "." / rel,
        Path(str(_REPO / rel).replace("/doc/", "/./doc/")),
    )
    for candidate in candidates:
        assert is_evidence_path(candidate, _REPO), candidate


def test_symlink_to_evidence_is_still_evidence(tmp_path: Path) -> None:
    link = tmp_path / "sneaky.json"
    link.symlink_to(_REPO / EVIDENCE_RELATIVE_PATHS[0])
    assert is_evidence_path(link, _REPO)


def test_ordinary_paths_are_not_evidence(tmp_path: Path) -> None:
    assert not is_evidence_path(tmp_path / "out.json", _REPO)


def test_missing_file_can_still_be_judged(tmp_path: Path) -> None:
    """파일이 아직 없어도 판정돼야 한다(strict=False)."""
    assert not is_evidence_path(tmp_path / "nope" / "out.json", _REPO)


# ── 자격 증명은 anchor 수 하나로 끝나지 않는다 ────────────────────────────


def test_full_canonical_claim_passes() -> None:
    assert_may_write_evidence(_claim(), _EXPECTED)


@pytest.mark.parametrize(
    "override",
    [
        {"contract_mode": CONTRACT_MODE_DIAGNOSTIC},
        {"anchor_days": 5},
        {"first_anchor": "2025-10-03"},
        {"last_anchor": "2027-12-30"},
        {"anchor_fingerprint": "c" * 64},
        {"episode_fingerprint": "c" * 64},
        {"projection_verified": False},
    ],
)
def test_any_single_failure_blocks_the_write(override: dict) -> None:
    """anchor 수만 730 으로 맞춘 비공식 데이터가 증거를 덮으면 안 된다."""
    with pytest.raises(AuditEvidenceOverwriteError):
        assert_may_write_evidence(_claim(**override), _EXPECTED)


def test_evidence_write_without_a_claim_is_blocked(tmp_path: Path) -> None:
    target = _REPO / EVIDENCE_RELATIVE_PATHS[0]
    before = target.read_bytes()
    with pytest.raises(AuditEvidenceOverwriteError):
        write_audit_output(target, {"x": 1}, repo_root=_REPO)
    assert target.read_bytes() == before


# ── 원자적 쓰기 ───────────────────────────────────────────────────────────


def test_atomic_write_replaces_the_file(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1})
    atomic_write_json(target, {"a": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}


def test_serialization_failure_leaves_the_old_file_intact(tmp_path: Path) -> None:
    """직렬화 중 실패해도 기존 파일이 부분 JSON 으로 손상되면 안 된다."""
    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1})
    before = hashlib.sha256(target.read_bytes()).hexdigest()

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": Unserializable()})
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_no_temp_files_are_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "out.json"

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": Unserializable()})
    assert list(tmp_path.iterdir()) == []


def test_temp_file_is_created_beside_the_target(tmp_path: Path) -> None:
    """다른 파일시스템의 임시 파일이면 os.replace 가 원자적이지 않다."""
    nested = tmp_path / "deep" / "out.json"
    atomic_write_json(nested, {"a": 1})
    assert nested.exists()
    assert list(nested.parent.iterdir()) == [nested]


# ── 진단 계약 ─────────────────────────────────────────────────────────────


def test_diagnostic_contract_changes_only_the_anchor_count() -> None:
    """호출부의 무제한 replace() 를 대체한다 — cap·의미 축은 못 바꾼다."""
    base = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1
    derived = derive_diagnostic_contract(anchor_days=5)
    assert derived.anchor_days == 5
    for field in (
        "board_size", "pass_axes", "pass_threshold", "domain_gate_applied",
        "p10_index", "window_days", "warmup_days", "first_anchor",
        "bottom_ilju_axis", "bottom_ilju_limit", "episode_minimum_axis",
        "episode_affected_axis", "episode_id_prefix",
    ):
        assert getattr(derived, field) == getattr(base, field)


def test_diagnostic_contract_is_not_canonical() -> None:
    assert contract_mode(ROLLING_AUDIT_AGGREGATE_CONTRACT_V1) == (
        CONTRACT_MODE_CANONICAL
    )
    assert contract_mode(derive_diagnostic_contract(anchor_days=5)) == (
        CONTRACT_MODE_DIAGNOSTIC
    )
    # cap 을 바꾼 계약도 canonical 이 아니다.
    tweaked = RollingAuditAggregateContract(pass_threshold=14)
    assert contract_mode(tweaked) == CONTRACT_MODE_DIAGNOSTIC


def test_diagnostic_contract_rejects_nonpositive_anchor_days() -> None:
    with pytest.raises(ValueError):
        derive_diagnostic_contract(anchor_days=0)


# ── directory fsync 예외 범위 ─────────────────────────────────────────────
#
# `except OSError: pass` 로 뭉뚱그리면 EIO 같은 실제 I/O 오류가 숨는다.


def test_unsupported_directory_fsync_is_tolerated(tmp_path, monkeypatch) -> None:
    """Windows 등 디렉터리 fd 열기 미지원 — 이미 끝난 교체를 실패로 만들지 않는다."""
    import errno as _errno
    import os as _os

    from saju_engines import daily_audit_output as mod

    real_open = _os.open

    def fake_open(path, flags, *a, **kw):
        if flags == _os.O_RDONLY and Path(path).is_dir():
            raise OSError(_errno.EACCES, "not supported")
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(mod.os, "open", fake_open)
    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def _fail_directory_fsync_only(monkeypatch, errno_code: int) -> None:
    """**디렉터리** fsync 만 실패시킨다.

    파일 fsync 까지 막으면 `os.replace` 전에 터져 다른 경로를 검사하게 된다 —
    실제로 그렇게 잘못된 이유로 통과한 적이 있다.
    """
    import os as _os
    import stat as _stat

    from saju_engines import daily_audit_output as mod

    real = _os.fsync

    def selective(fd):
        if _stat.S_ISDIR(_os.fstat(fd).st_mode):
            raise OSError(errno_code, "disk failure")
        return real(fd)

    monkeypatch.setattr(mod.os, "fsync", selective)


def test_real_io_error_on_directory_fsync_propagates(tmp_path, monkeypatch) -> None:
    """EIO 는 숨기지 않는다."""
    import errno as _errno

    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1})
    _fail_directory_fsync_only(monkeypatch, _errno.EIO)
    with pytest.raises(OSError) as exc:
        atomic_write_json(target, {"a": 2})
    assert exc.value.errno == _errno.EIO


# ── claim 은 payload 에 결박된다 ──────────────────────────────────────────
#
# `projection_verified=True` boolean 하나만 믿으면, 자격을 받은 뒤 결과를 바꿔치고
# 그대로 증거 경로에 기록할 수 있다. 쓰기 직전에 실제 payload 를 다시 지문낸다.


def _write(payload: dict, claim=None):
    target = _REPO / EVIDENCE_RELATIVE_PATHS[0]
    return write_audit_output(
        target, {"result": payload}, repo_root=_REPO,
        claim=claim or _claim(), expected=_EXPECTED, public_payload=payload,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p["daily"][0].__setitem__("passes", False),
                     id="daily 값"),
        pytest.param(lambda p: p["episodes"][0].__setitem__("duration_days", 1),
                     id="episode 값"),
        pytest.param(lambda p: p["repeatedly_below_iljus"].__setitem__("戊辰", 1),
                     id="repeatedly_below 값"),
        pytest.param(lambda p: p.__setitem__("extra", 1), id="최상위 키 추가"),
        pytest.param(lambda p: p.pop("episodes"), id="최상위 키 삭제"),
    ],
)
def test_payload_changed_after_the_claim_is_blocked(mutate) -> None:
    target = _REPO / EVIDENCE_RELATIVE_PATHS[0]
    before = target.read_bytes()
    payload = _payload()
    claim = _claim()                       # 원본 payload 로 발급된 자격
    mutate(payload)
    with pytest.raises(AuditEvidenceOverwriteError, match="달라졌다"):
        _write(payload, claim)
    assert target.read_bytes() == before


def test_top_level_key_order_change_is_blocked() -> None:
    """키 순서도 공개 계약이다."""
    target = _REPO / EVIDENCE_RELATIVE_PATHS[0]
    before = target.read_bytes()
    original = _payload()
    reordered = {k: original[k] for k in reversed(list(original))}
    with pytest.raises(AuditEvidenceOverwriteError, match="달라졌다"):
        _write(reordered, _claim())
    assert target.read_bytes() == before


def test_claim_from_another_run_is_rejected() -> None:
    """다른 실행에서 얻은 자격을 재사용할 수 없다."""
    other = _payload()
    other["summary"]["total_anchors"] = 729
    foreign = _claim(public_payload_sha256=fingerprint_public_payload(other))
    with pytest.raises(AuditEvidenceOverwriteError, match="달라졌다"):
        _write(_payload(), foreign)


def test_claim_without_a_payload_digest_is_rejected() -> None:
    with pytest.raises(AuditEvidenceOverwriteError, match="public_payload_sha256"):
        assert_may_write_evidence(_claim(public_payload_sha256=""), _EXPECTED)


def test_unchanged_payload_passes_the_binding_check() -> None:
    """결박이 정상 경로를 막지는 않는다."""
    payload = _payload()
    claim = _claim()
    assert_may_write_evidence(claim, _EXPECTED)
    assert fingerprint_public_payload(payload) == claim.public_payload_sha256


def test_claim_is_frozen() -> None:
    claim = _claim()
    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.anchor_days = 5           # type: ignore[misc]


# ── 디렉터리 sync 실패는 상태가 드러나야 한다 ────────────────────────────


def test_directory_sync_failure_reports_that_replace_committed(
    tmp_path, monkeypatch
) -> None:
    """일반 쓰기 실패로 오인해 재시도하면 안 된다 — 파일은 이미 새 바이트다."""
    import errno as _errno

    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1})
    _fail_directory_fsync_only(monkeypatch, _errno.EIO)
    with pytest.raises(AuditDirectorySyncError) as exc:
        atomic_write_json(target, {"a": 2})
    assert exc.value.replace_committed is True
    assert "교체는 완료" in str(exc.value)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert list(tmp_path.iterdir()) == [target]
