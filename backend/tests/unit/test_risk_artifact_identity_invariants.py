"""validation artifact identity 불변식(2026-08-04 데굴님 승인 §2).

역할 분리를 회귀로 고정한다.

  validationCorpusHash   결정적 검증 **입력** identity — manifest/runtime
                         일치 판정에 사용
  validationPolicyHash   결정적 검증 **계약** identity — 동일
  validationArtifactHash 특정 실측 실행의 provenance — reviewed artifact
                         추적·변조 탐지용이며 **주기적 lease 갱신 identity
                         비교에는 쓰지 않는다**

report에는 provider가 보고한 실행 시점 값(캐시 적중 등)이 들어가므로
artifactHash는 동등한 검증 실행 사이에서도 달라질 수 있다. 이를 runtime
identity 비교에 넣으면 2026-08-04에 제거한 비결정성이 재발한다.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from saju_api.services import risk_exposure_service as svc
from saju_api.services.token_counter_registry import (
    TokenCounterAdapter,
    _manifest_entry_matches,
    adapter_validation_policy_hash,
)

_MODEL = "m-artifact-test"
_CORPUS = "c" * 64


def _identity() -> dict:
    return {"countMode": "PROVIDER_EXACT", "counterVersion": "v-test",
            "providerId": "gemini", "providerRequestSchemaVersion": "1",
            "resolvedModelId": _MODEL,
            "validationPolicyHash": adapter_validation_policy_hash()}


def _artifact(*, corpus_hash: str = _CORPUS,
              report_extra: dict | None = None) -> dict:
    """identityCorpus 기반 artifact(현행 schema) — 자기정합 해시 포함."""
    identity_corpus = {
        "identity": _identity(),
        "samples": [{"sample_id": "S01-a", "category": "S01_korean_long",
                     "tier": "FULL", "resolved_model_id": _MODEL,
                     "attempt_kind": "INITIAL",
                     "request_digest": "d" * 16,
                     "request_shape_digest": "s" * 16}],
    }
    body = {
        "nativeValidationCorpus": {
            "identity": _identity(),
            # 실행 관측값 — identity 미참여, 증거로만 보존
            "samples": [{"sample_id": "S01-a", "counted": 100,
                         "reported_total_input": 100, "cached_input": 0}],
        },
        "identityCorpus": identity_corpus,
        "validationCorpusHash": corpus_hash,
        "report": {"pass": True, **(report_extra or {})},
        "volatile": {"generated_at": "2026-08-04T00:00:00+00:00"},
    }
    body["validationArtifactHash"] = hashlib.sha256(json.dumps(
        {k: v for k, v in body.items() if k != "volatile"},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return body


def _corpus_hash_of(artifact: dict) -> str:
    return hashlib.sha256(json.dumps(
        artifact["identityCorpus"], ensure_ascii=False,
        sort_keys=True).encode()).hexdigest()


@pytest.fixture()
def artifact_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_ARTIFACT_DIR", tmp_path)
    return tmp_path


def _write(artifact_dir, artifact: dict, name: str = "a.json") -> None:
    (artifact_dir / name).write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")


# ── ① artifactHash 변경만으로는 identity 불일치가 되지 않는다 ────────────


def test_artifact_hash_differs_but_identity_matches(artifact_dir) -> None:
    """동일 corpus·policy에서 report(실측)만 다른 두 실행은 corpusHash가
    같고 manifest 일치 판정도 그대로다 — artifactHash만 달라진다."""
    run_a = _artifact(report_extra={"cacheValidationStatus": "NOT_OBSERVED",
                                    "cacheHitSamplesObserved": 0})
    run_b = _artifact(report_extra={"cacheValidationStatus": "VALIDATED",
                                    "cacheHitSamplesObserved": 3})
    assert run_a["validationArtifactHash"] != run_b["validationArtifactHash"]
    assert _corpus_hash_of(run_a) == _corpus_hash_of(run_b)

    adapter = TokenCounterAdapter(
        model_id=_MODEL, mode="PROVIDER_EXACT", counter=len,
        provider_id="gemini", counter_version="v-test",
        validation_corpus_hash=_corpus_hash_of(run_b))
    # manifest 항목에 artifactHash가 없어도(또는 달라도) 일치 판정은 성립
    entry = {**_identity(), "reviewed": True,
             "validationCorpusHash": adapter.validation_corpus_hash,
             "validationArtifactHash": run_a["validationArtifactHash"]}
    assert _manifest_entry_matches(adapter, entry)

    corpus_hash = _corpus_hash_of(run_b)
    _write(artifact_dir, {**run_b, "validationCorpusHash": corpus_hash,
                          "validationArtifactHash": hashlib.sha256(
                              json.dumps({k: v for k, v in {
                                  **run_b,
                                  "validationCorpusHash": corpus_hash,
                              }.items() if k not in (
                                  "volatile", "validationArtifactHash")},
                                  ensure_ascii=False,
                                  sort_keys=True).encode()).hexdigest()})
    assert svc._artifact_corpus_ok(_MODEL, corpus_hash)


# ── ② corpusHash·policyHash 변경은 재감수를 요구한다 ─────────────────────


def test_corpus_hash_change_breaks_manifest_match() -> None:
    adapter = TokenCounterAdapter(
        model_id=_MODEL, mode="PROVIDER_EXACT", counter=len,
        provider_id="gemini", counter_version="v-test",
        validation_corpus_hash="new" + "c" * 61)
    entry = {**_identity(), "reviewed": True,
             "validationCorpusHash": _CORPUS}
    assert not _manifest_entry_matches(adapter, entry)


def test_policy_hash_change_breaks_manifest_match() -> None:
    adapter = TokenCounterAdapter(
        model_id=_MODEL, mode="PROVIDER_EXACT", counter=len,
        provider_id="gemini", counter_version="v-test",
        validation_corpus_hash=_CORPUS)
    entry = {**_identity(), "reviewed": True,
             "validationCorpusHash": _CORPUS,
             "validationPolicyHash": "stale-policy-hash"}
    assert not _manifest_entry_matches(adapter, entry)


# ── ③ artifact 내용과 artifactHash 불일치 = fail-closed ──────────────────


def test_tampered_artifact_fails_closed(artifact_dir) -> None:
    """provenance 해시가 내용과 어긋나면 신뢰하지 않는다(변조 탐지)."""
    art = _artifact()
    corpus_hash = _corpus_hash_of(art)
    art["validationCorpusHash"] = corpus_hash
    art["validationArtifactHash"] = "0" * 64  # 내용과 불일치
    _write(artifact_dir, art)
    assert not svc._artifact_corpus_ok(_MODEL, corpus_hash)


def test_tampered_identity_corpus_fails_closed(artifact_dir) -> None:
    """identityCorpus를 고치면 corpusHash 재해시가 어긋난다."""
    art = _artifact()
    corpus_hash = _corpus_hash_of(art)
    art["validationCorpusHash"] = corpus_hash
    art["identityCorpus"]["samples"][0]["request_digest"] = "e" * 16
    _write(artifact_dir, art)
    assert not svc._artifact_corpus_ok(_MODEL, corpus_hash)


# ── 구 schema 폴백(운영 artifact 교체 전까지 유효) ───────────────────────


def test_legacy_artifact_without_identity_corpus_still_verifies(
        artifact_dir) -> None:
    """identityCorpus가 없는 구 artifact는 nativeValidationCorpus 전체
    재해시로 검증한다 — 교체 전 운영 artifact가 무효화되면 안 된다."""
    native = {"identity": _identity(),
              "samples": [{"sample_id": "S01-a", "counted": 100}]}
    legacy = {"nativeValidationCorpus": native,
              "validationCorpusHash": hashlib.sha256(json.dumps(
                  native, ensure_ascii=False,
                  sort_keys=True).encode()).hexdigest(),
              "report": {"pass": True},
              "volatile": {"generated_at": "2026-07-23T00:00:00+00:00"}}
    legacy["validationArtifactHash"] = hashlib.sha256(json.dumps(
        {k: v for k, v in legacy.items() if k != "volatile"},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    _write(artifact_dir, legacy)
    assert svc._artifact_corpus_ok(_MODEL, legacy["validationCorpusHash"])
