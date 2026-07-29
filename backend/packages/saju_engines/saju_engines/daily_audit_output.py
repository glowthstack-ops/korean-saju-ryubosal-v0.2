"""감사 결과 쓰기 — 동결 증거 파일을 실행 코드가 덮어쓰지 못하게 막는다.

실제로 5-anchor 진단 실행이 730-anchor 공식 증거(`oa10b_rolling_window.json`)를
밀어낸 적이 있다. 복구는 됐지만, 같은 일이 다시 가능하면 그 파일은 **동결된 것이
아니다.**

두 가지를 건다.

    · 증거 경로 쓰기는 canonical 조건을 전부 증명했을 때만 허용한다.
      `anchor_days == 730` 하나로는 부족하다 — anchor 수만 맞춘 비공식 데이터가
      증거를 덮을 수 있다.
    · 쓰기는 원자적이다. 직렬화·집계·쓰기 도중 실패해도 기존 파일이 부분 JSON 이나
      짧은 결과로 손상되지 않는다.
"""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: 이 경로들은 감사 증거다. canonical 실행만 덮어쓸 수 있다.
EVIDENCE_RELATIVE_PATHS = (
    "doc/v2_2/audits/oa10b_rolling_window.json",
)


#: "이 플랫폼·파일시스템은 디렉터리 fsync 를 지원하지 않는다" 에 해당하는 errno.
#: 그 밖의 오류(EIO 등)는 삼키지 않는다.
_UNSUPPORTED_ERRNOS = frozenset({
    errno.EINVAL, errno.EACCES, errno.EPERM, errno.EISDIR, errno.ENOSYS,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP), errno.EOPNOTSUPP,
})


class AuditEvidenceOverwriteError(RuntimeError):
    """비공식 실행이 동결 증거 경로에 쓰려 했다."""


class AuditDirectorySyncError(OSError):
    """파일 교체는 **완료됐고** 상위 디렉터리 내구성 동기화만 실패했다.

    일반 쓰기 실패로 오인해 재시도하면 안 된다 — 최종 파일은 이미 새 바이트다.
    """

    #: 이 예외가 던져진 시점에 `os.replace` 는 이미 커밋됐다.
    replace_committed = True


@dataclass(frozen=True)
class CanonicalWriteClaim:
    """증거 경로에 쓸 자격 — 전부 만족해야 한다.

    Attributes:
        contract_mode: `CANONICAL` 만 허용한다.
        anchor_days: 공식 anchor 수.
        first_anchor: 공식 첫 anchor(ISO).
        last_anchor: 공식 마지막 anchor(ISO).
        anchor_fingerprint: 산출된 anchor 지문.
        episode_fingerprint: 산출된 episode 지문.
        projection_verified: public-v1 투영 검증 통과 여부.
    """

    contract_mode: str
    anchor_days: int
    first_anchor: str
    last_anchor: str
    anchor_fingerprint: str
    episode_fingerprint: str
    projection_verified: bool
    #: 이 자격이 **어느 공개 payload** 에서 나왔는지. boolean 하나만 믿으면 claim
    #: 생성 뒤 결과를 바꿔치고 그대로 기록할 수 있다.
    public_schema_version: str = ""
    public_payload_sha256: str = ""


@dataclass(frozen=True)
class CanonicalExpectation:
    """동결 기준선이 기대하는 값."""

    anchor_days: int
    first_anchor: str
    last_anchor: str
    anchor_fingerprint: str
    episode_fingerprint: str


def fingerprint_public_payload(payload: Mapping[str, Any]) -> str:
    """공개 결과의 정규 지문 — 키 순서까지 포함한다.

    공개 계약은 키 **순서**도 포함하므로 `sort_keys` 를 쓰지 않는다. 순서가 바뀌면
    지문이 달라져야 한다.
    """
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def is_evidence_path(candidate: Path, repo_root: Path) -> bool:
    """정규화된 실제 경로로 판정한다.

    문자열 비교는 `./doc/...` · 절대 경로 · symlink 경유로 우회된다. 파일이 아직
    없을 수 있으므로 `strict=False` 로 푼다.
    """
    resolved = candidate.expanduser().resolve(strict=False)
    return any(
        resolved == (repo_root / rel).resolve(strict=False)
        for rel in EVIDENCE_RELATIVE_PATHS
    )


def assert_may_write_evidence(
    claim: CanonicalWriteClaim, expected: CanonicalExpectation
) -> None:
    """증거 경로 쓰기 자격을 증명한다.

    Raises:
        AuditEvidenceOverwriteError: 하나라도 어긋나면.
    """
    problems: list[str] = []
    if claim.contract_mode != "CANONICAL":
        problems.append(f"contract_mode={claim.contract_mode}")
    if claim.anchor_days != expected.anchor_days:
        problems.append(f"anchor_days={claim.anchor_days} != {expected.anchor_days}")
    if claim.first_anchor != expected.first_anchor:
        problems.append(f"first_anchor={claim.first_anchor}")
    if claim.last_anchor != expected.last_anchor:
        problems.append(f"last_anchor={claim.last_anchor}")
    if claim.anchor_fingerprint != expected.anchor_fingerprint:
        problems.append(f"anchor_fp={claim.anchor_fingerprint[:16]}…")
    if claim.episode_fingerprint != expected.episode_fingerprint:
        problems.append(f"episode_fp={claim.episode_fingerprint[:16]}…")
    if not claim.projection_verified:
        problems.append("projection_verified=False")
    if len(claim.public_payload_sha256) != 64:
        problems.append("public_payload_sha256 미설정")
    if problems:
        raise AuditEvidenceOverwriteError(
            "동결 증거 경로에 쓸 수 없다 — " + " · ".join(problems)
        )


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """같은 디렉터리 임시 파일에 쓰고 교체한다.

    임시 파일은 **최종 파일과 같은 디렉터리**여야 `os.replace` 의 원자성이 보장된다
    (다른 파일시스템이면 교체가 아니라 복사가 된다).

    parent directory `fsync` 는 내구성 보강이다. 디렉터리 fd 열기를 지원하지 않는
    플랫폼이 있으므로, 그 실패로 **이미 성공한 교체**를 실패 처리하지 않는다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    # 여기부터는 교체가 끝났다 — 아래 실패로 롤백하지 않는다.
    _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    """디렉터리 항목까지 내려쓴다 — **내구성 보강**이다.

    이미 `os.replace` 가 끝난 뒤라 여기서 실패해도 롤백하지 않는다. 다만
    `except OSError: pass` 로 뭉뚱그리면 EIO 같은 실제 I/O 오류까지 숨는다.
    플랫폼·파일시스템이 지원하지 않는 경우만 조용히 넘기고, 그 밖의 오류는
    전파한다.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_ERRNOS:
            return                  # Windows 등 — 디렉터리 fd 열기 미지원
        raise
    try:
        os.fsync(dir_fd)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_ERRNOS:
            # 교체는 이미 끝났다 — 일반 쓰기 실패로 오인해 재시도하지 않도록
            # 상태가 드러나는 예외로 감싼다.
            raise AuditDirectorySyncError(
                exc.errno,
                "파일 교체는 완료됐으나 상위 디렉터리 내구성 동기화에 실패했다: "
                f"{exc.strerror}",
            ) from exc
    finally:
        os.close(dir_fd)


def write_audit_output(
    path: Path,
    payload: Mapping[str, Any],
    *,
    repo_root: Path,
    claim: CanonicalWriteClaim | None = None,
    expected: CanonicalExpectation | None = None,
    public_payload: Mapping[str, Any] | None = None,
) -> None:
    """감사 결과를 쓴다. 증거 경로라면 자격을 먼저 증명한다.

    Args:
        path: 출력 경로.
        payload: 직렬화할 결과.
        repo_root: 증거 경로 판정 기준.
        claim: canonical 자격 주장(증거 경로일 때 필수).
        expected: 동결 기준선 기대값(증거 경로일 때 필수).

    Raises:
        AuditEvidenceOverwriteError: 증거 경로인데 자격이 없을 때.
    """
    if is_evidence_path(path, repo_root):
        if claim is None or expected is None or public_payload is None:
            raise AuditEvidenceOverwriteError(
                f"{path} 는 동결 증거다 — canonical 자격 없이 쓸 수 없다"
            )
        assert_may_write_evidence(claim, expected)
        # 자격은 "이 계산이 canonical 이었다" 가 아니라 "**이 정확한 payload** 가
        # 그 계산에서 나왔다" 를 증명해야 한다. 쓰기 직전에 다시 검증한다.
        actual = fingerprint_public_payload(public_payload)
        if not hmac.compare_digest(actual, claim.public_payload_sha256):
            raise AuditEvidenceOverwriteError(
                "공개 payload 가 자격 발급 이후 달라졌다 — "
                f"claim={claim.public_payload_sha256[:16]}… "
                f"actual={actual[:16]}…"
            )
    atomic_write_json(path, payload)
