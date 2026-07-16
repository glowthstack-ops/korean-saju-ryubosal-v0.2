"""모델 tokenizer adapter registry (감수 48차 §10-③ — EXPOSE 필수 조건).

계약: configured model alias → 실제 resolved provider model → matching
counter. **등록 여부만 검사하지 않는다** — counter는 provider에 실제 전달되는
전체 요청(system·user·context·risk instruction/guard·block·schema)을
계수해야 하며, 모델 fallback/라우팅 변경 시 새 resolved model로 counter를
재해소하고 전체 request를 재계수해야 한다(이전 모델 count 재사용 금지).

기본 registry는 **비어 있다** — adapter 미등록 모델은 EXPOSE에서
TOKENIZER_UNAVAILABLE(BYPASS)로 처리된다(heuristic 대체 금지). 실물
adapter(Gemini token-count API·GPT 계열 tokenizer)는 canary 개시 차수에서
감수와 함께 등록한다.
"""

from __future__ import annotations

import threading as _threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path

__all__ = ["ADAPTER_VALIDATION_POLICY", "ADAPTER_VALIDATION_STATES",
           "adapter_identity_hash", "suspension_state_ok",
           "adapter_validation_policy_hash", "record_count_observation",
           "resolve_expose_counter", "ProviderRequest",
           "TokenCounterAdapter", "register_adapter", "resolve_counter",
           "resolve_validated_counter", "set_validation_state"]

# adapter 검증 상태(감수 50차 §4): EXPOSE 주입 자격=VALIDATED만.
# UNREGISTERED→SHADOW_VALIDATING(등록 직후 — shadow에서 counted vs
# provider_reported 대조)→VALIDATED(감수)→SUSPENDED(오차 허용 초과 시).
# calibration 용어: counted_request_tokens / provider_reported_input_tokens
# / token_count_delta / token_count_relative_error.
ADAPTER_VALIDATION_STATES = ("UNREGISTERED", "SHADOW_VALIDATING",
                             "VALIDATED", "SUSPENDED")

# adapter 승격 기준(감수 51차 §6 — **실측 전 선행 고정**: 결과에 맞춘 기준
# 방지). 변경=expose 재감수 신호(hash가 manifest에 병기됨).
ADAPTER_VALIDATION_POLICY: dict = {
    "validation_key": ["provider_id", "resolved_model_id",
                       "counter_version", "provider_request_schema_version"],
    "key_change": "하나라도 변경 시 VALIDATED → SHADOW_VALIDATING 강등",
    "sample_shapes": ["한국어 장문", "한영 혼합", "JSON risk block",
                      "tool schema 포함", "output schema 포함",
                      "SUPPRESSED guard", "INJECTED instruction",
                      "FULL/P1/P0/P0_COMPACT 각 tier",
                      "runtime hard-max payload(질문 유형별 실제 상한"
                      " 2/3/4 episodes — 감수 57차 §6)",
                      "oversized stress payload(8/12/16 episodes —"
                      " synthetic 과대 요청, tokenizer 압박용)"],
    "rerouting_verification": "모델 fallback·rerouting 재계수는 30표본"
                              " **외** 별도 검증(감수 57차 §2) — 표본의"
                              " validation identity는 최초 설정 모델이"
                              " 아니라 **최종 resolved 모델** 기준으로"
                              " 집계하며, 감수되지 않은 fallback 모델"
                              " (validated counter 없음)은 canary에서"
                              " BYPASS를 유지한다",
    "sample_minimum": "카테고리 10형 × 각 3개 이상 = **validation"
                      " identity(7요소)별·최종 resolved 모델 native"
                      " 표본** 최소 30개(registry 전체 아님·rerouting"
                      " 표본 불포함 — 감수 56차 §9 + 57차 §2)",
    "runtime_drift": "canary 중 counted < provider_reported **1건**이라도"
                     " 발생 시 즉시 VALIDATED→SUSPENDED(이후 BYPASS)."
                     " overcount_ratio p50/p90/max 별도 관측(과대 계산은"
                     " 안전 문제 아님 — 과도하면 불필요 compact/suppressed)",
    "manifest_ssot": "registry 자체 선언으로 EXPOSE 자격 불가 — manifest"
                     " validatedTokenCounters 항목(reviewed=true·validation"
                     " key 4종·corpus/policy hash 일치)과 runtime adapter"
                     " key가 일치해야 주입(감수 52차 §2)",
    "provider_exact_pass": "undercount=0 · request shape 누락=0 · model"
                           " mismatch=0 · routing 후 recount 누락=0",
    "model_tokenizer_pass": "전 감수 표본에서 counted_request_tokens >="
                            " provider_reported_input_tokens(wrapper"
                            " reserve 포함) — 과소 계산 불허(과대는 허용)",
    "reported_basis": "비용 청구 수치가 아니라 실제 전체 prompt/input"
                      " token 수 기준(cached_input_tokens 별도 기록)",
    "corpus_hash_form": "validationCorpusHash 정본=**전체 SHA-256"
                        " digest(64 hex)**(감수 57차 §5 — gate·artifact"
                        " 무결성 기준). 16자 축약은 표시·로그·파일명"
                        " 전용(validationCorpusHashShort)",
    "corpus_canonical_rule": "표본을 sample ID로 정렬 후 canonical"
                             " 직렬화(sha256) — 포함: validation identity"
                             "(corpus 제외 6요소)·유형별 고정 sample ID·"
                             "정규화된 provider request digest·counted"
                             " tokens·provider-reported total input(cached"
                             "+non-cached)·cached input tokens·routing/"
                             "recount 결과·tier·합격 여부. 제외: 실행 시각·"
                             "원본 request ID·파일 경로·결과 배열 실행"
                             " 순서·임시 로그 ID(감수 56차 §1)",
    "shadow_promotion": "30표본 통과만으로 runtime 객체 자동 VALIDATED"
                        " 금지(감수 56차 §9) — 검증 통과 → validation"
                        " artifact 생성 → manifest 감수(reviewed entry"
                        " 배포) → 그 이후에만 VALIDATED 자격. 등록 직후는"
                        " SHADOW_VALIDATING 고정",
    "observability": ["counted_request_tokens",
                      "provider_reported_input_tokens", "delta",
                      "relative_error", "cached_input_tokens",
                      "routing_changed", "recount_performed"],
}


def adapter_validation_policy_hash() -> str:
    """승격 기준 해시 — manifest 병기(변경=expose 재감수 신호).

    정본=**전체 SHA-256 digest**(감수 58차 §6 — EXPOSE 자격을 결정하는
    값이므로 corpus hash와 동일하게 full digest, 16자 축약은 표시 전용).
    """
    import hashlib
    import json
    return hashlib.sha256(json.dumps(
        ADAPTER_VALIDATION_POLICY, sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()


@dataclass(frozen=True)
class ProviderRequest:
    """provider에 실제 전송되는 요청 전체(감수 49차 §4 — 계수 대상 SSOT).

    문자열 하나가 아니라 요청 전체를 계수한다: 모든 message(system/user)·
    risk instruction 또는 suppressed guard·risk block·output/tool schema·
    provider wrapper·모델 특수 토큰(어댑터 구현이 반영).
    """

    system_messages: tuple[str, ...] = field(default_factory=tuple)
    user_messages: tuple[str, ...] = field(default_factory=tuple)
    output_schema: str | None = None
    tool_schema: str | None = None
    generation_config: str | None = None


@dataclass(frozen=True)
class TokenCounterAdapter:
    """모델별 token counter — model_id는 alias 해소 후의 resolved ID.

    count_request가 정본(요청 전체 계수 — 감수 49차 §4). counter(문자열
    단건)는 block 단위 예비 계수 용도로만 유지한다.
    """

    model_id: str
    mode: str  # PROVIDER_EXACT | MODEL_TOKENIZER
    counter: Callable[[str], int]
    provider_id: str = ""
    counter_version: str = ""
    # validation key 4번째 축(감수 53차 §2): ProviderRequest 구조 버전 —
    # 요청 구조가 바뀌면 감수 무효(manifest 대조 대상).
    request_schema_version: str = "1"
    # 감수 corpus canonical hash(감수 55차 §1 — identity 구성 요소): corpus
    # 재감수=새 identity(기존 suspension 미적용·새 manifest 감수 전 BYPASS).
    validation_corpus_hash: str = ""

    def count_request(self, request: ProviderRequest) -> int:
        """provider request 전체 계수 — 기본 구현은 전 구성요소 합산 +
        wrapper 여유(어댑터가 provider 정밀 계수로 재정의 가능)."""
        parts = [*request.system_messages, *request.user_messages]
        for extra in (request.output_schema, request.tool_schema,
                      request.generation_config):
            if extra:
                parts.append(extra)
        return sum(self.counter(p) for p in parts) + 4 * len(parts)


_REGISTRY: dict[str, TokenCounterAdapter] = {}
_VALIDATION: dict[str, str] = {}  # model_id → 검증 상태(기본 SHADOW_VALIDATING)


def register_adapter(adapter: TokenCounterAdapter) -> None:
    """adapter 등록 — mode는 EXPOSE 허용 2종만(heuristic 등록 금지)."""
    if adapter.mode not in ("PROVIDER_EXACT", "MODEL_TOKENIZER"):
        raise ValueError(f"EXPOSE 불가 token mode: {adapter.mode}")
    _REGISTRY[adapter.model_id] = adapter
    # 등록≠검증(감수 50차 §4 — 등록과 canary 활성화 분리): shadow 대조 후
    # 감수를 거쳐야 VALIDATED가 된다.
    _VALIDATION.setdefault(adapter.model_id, "SHADOW_VALIDATING")


def set_validation_state(model_id: str, state: str) -> None:
    """adapter 검증 상태 전환(감수 절차 전용) — 미등록 상태값 거부."""
    if state not in ADAPTER_VALIDATION_STATES:
        raise ValueError(f"미지원 검증 상태: {state}")
    _VALIDATION[model_id] = state


def resolve_validated_counter(
        resolved_model_id: str) -> TokenCounterAdapter | None:
    """EXPOSE 주입용 해소(감수 50차 §4) — **VALIDATED 상태만** 반환.

    SHADOW_VALIDATING/SUSPENDED/미등록은 None(게이트 BYPASS). shadow
    측정에는 resolve_counter(상태 무관)를 쓴다.
    """
    if _VALIDATION.get(resolved_model_id) != "VALIDATED":
        return None
    return _REGISTRY.get(resolved_model_id)


# 전역 suspension 공유 저장소(감수 53차 §3 + 54차 §2 — 다중 worker).
# **배포 불변식(감수 54차)**: 파일 backend는 single host + shared writable
# runtime state에서만 전역이다 — 다중 호스트/컨테이너는 공유 저장소(Redis·
# DB)로 교체 후 canary. 경로=빌드 산출물(compiled/) 아님·runtime state.
# 자동 복구 금지 — suspension은 **validation identity hash** 기준 기록.
# tombstone 계약(감수 56차 §5): 옛 identity는 suspension tombstone
# (append-only ledger)을 삭제하지 않으며, 복구는 record 삭제가 아니라
# 새 validation identity(counterVersion/corpus 변경)의 재감수·새 manifest
# entry로만 수행한다. 운영 정리는 [기존 identity manifest 제거 + 새
# identity 배포 완료 + 감사 ledger 보존] 전부 충족 시에만.
_STATE_DIR = Path(__file__).resolve().parents[4] / "var" / "risk_state"
_SUSPENSION_FILE = _STATE_DIR / "adapter_suspensions.json"
# 전용 lock 파일(감수 55차 §2): 데이터 파일은 atomic replace로 inode가
# 바뀌므로 lock 대상은 교체되지 않는 별도 파일이어야 한다.
_SUSPENSION_LOCK_FILE = _STATE_DIR / "adapter_suspensions.lock"
# append-only suspension ledger(감수 56차 §5 — tombstone): state 파일이
# 삭제·재생성돼도 ledger에 남은 identity는 계속 차단된다(단일 파일 삭제로
# 부활 불가). ledger 손상=저장소 불가용(BYPASS).
_SUSPENSION_LEDGER = _STATE_DIR / "adapter_suspensions_ledger.jsonl"
# persistence 쓰기 실패 전역 차단 marker(감수 55차 §4): under-count 기록에
# 실패하면 로컬 SUSPENDED만으로는 전역 보장이 없다 — marker가 존재하면
# 모든 worker의 suspension_state_ok()=False(전부 BYPASS). marker 기록조차
# 실패하면 프로세스 로컬 flag로 최소 현 worker 차단 + supervisor 재시작
# 계약(canary 전 공유 저장소 전환 권장 — 배포 불변식).
_EXPOSURE_DISABLED_MARKER = _STATE_DIR / "exposure_disabled.marker"
_LOCAL_PERSISTENCE_FAILED = False
_IN_PROCESS_LOCK = _threading.Lock()  # 동일 프로세스 thread/async 동기화


def adapter_identity_hash(adapter: TokenCounterAdapter) -> str:
    """validation identity hash(감수 54차 §1) — suspension·감수 결속 키.

    identity가 바뀌면(counterVersion·schema version·**corpus**·count mode
    등) 기존 VALIDATED·SUSPENDED 상태를 재사용하지 않는다 — 감수 55차 §1:
    corpus 재감수=새 identity 복구 계약과 정합(감수 identity와 완전 동일
    구성: provider|model|counterVersion|schemaVersion|countMode|policyHash
    |corpusHash).
    """
    import hashlib
    parts = "|".join([adapter.provider_id, adapter.model_id,
                      adapter.counter_version,
                      adapter.request_schema_version,
                      adapter.mode,
                      adapter_validation_policy_hash(),
                      adapter.validation_corpus_hash])
    return hashlib.sha256(parts.encode()).hexdigest()[:16]


def _shared_suspensions() -> tuple[dict, bool]:
    """(기록, 상태 정상 여부) — 손상·권한 오류는 '없음'이 아니라 불가용
    (감수 54차 §2: 저장소 오류=BYPASS)."""
    import json as _json
    try:
        if not _SUSPENSION_FILE.exists():
            return {}, True  # 최초 상태 — 기록 없음은 정상
        data = _json.loads(_SUSPENSION_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}, False
        return data, True
    except (OSError, ValueError):
        return {}, False


def _ledger_suspensions() -> tuple[set[str], bool]:
    """(ledger의 suspended identity 집합, 상태 정상 여부).

    tombstone 저장소(감수 56차 §5) — 손상 line·읽기 실패는 '기록 없음'이
    아니라 불가용(fail-closed). 파일 부재는 최초 상태로 정상.
    """
    import json as _json
    identities: set[str] = set()
    try:
        if not _SUSPENSION_LEDGER.exists():
            return identities, True
        for line in _SUSPENSION_LEDGER.read_text(
                encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = _json.loads(line)
            if not isinstance(rec, dict) or "identity" not in rec:
                return identities, False
            identities.add(str(rec["identity"]))
        return identities, True
    except (OSError, ValueError):
        return identities, False


def suspension_state_ok() -> bool:
    """suspension 저장소 가용성 — False면 EXPOSE 해소 전부 BYPASS.

    persistence 쓰기 실패 marker(전 worker)·로컬 실패 flag(현 worker)도
    불가용으로 판정한다(감수 55차 §4).
    """
    if _LOCAL_PERSISTENCE_FAILED or _EXPOSURE_DISABLED_MARKER.exists():
        return False
    from saju_engines import risk_engine_config as _cfg
    combo = (_cfg.RISK_SUSPENSION_BACKEND, _cfg.RISK_DEPLOYMENT_TOPOLOGY)
    if combo not in _cfg._SUPPORTED_SUSPENSION_COMBOS:
        return False  # 미지원 배포 조합=전역 suspension 미보장(감수 55차 §6)
    return _suspension_snapshot()[2]


def _suspension_snapshot() -> tuple[dict, set[str], bool]:
    """(state 기록, ledger identity, 정상 여부) — **동일 lock 스냅샷**.

    감수 57차 §7: ledger와 state 파일은 같은 공유 lock(LOCK_SH) 안에서
    읽는다 — writer의 RMW(EX lock)와 배타적이므로 두 파일이 서로 다른
    시점의 상태로 읽히지 않는다. lock 획득 실패=저장소 불가용(BYPASS).
    """
    import fcntl
    try:
        _SUSPENSION_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SUSPENSION_LOCK_FILE, "a+") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_SH)
            try:
                records, ok = _shared_suspensions()
                ledger_ids, ledger_ok = _ledger_suspensions()
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
        return records, ledger_ids, ok and ledger_ok
    except OSError:
        return {}, set(), False


def _is_globally_suspended(identity_hash: str) -> tuple[bool, bool]:
    """(suspended 여부, 상태 정상 여부) — state 파일 ∪ append-only ledger.

    tombstone 계약(감수 56차 §5): state 파일의 항목·파일 삭제만으로는
    identity가 부활하지 않는다 — ledger에 남은 identity도 차단 대상.
    """
    records, ledger_ids, ok = _suspension_snapshot()
    return identity_hash in records or identity_hash in ledger_ids, ok


def resolve_expose_counter(
    resolved_model_id: str,
    manifest_counters: list[dict],
) -> TokenCounterAdapter | None:
    """manifest SSOT 대조 해소(감수 52차 §2 + 53차 §2) — canary 정본 경로.

    registry의 VALIDATED 선언만으로는 부족: manifest validatedTokenCounters
    항목(reviewed=true)과 **validation key 4종 전부**(provider·model·
    counter version·request schema version) + 감수 artifact 해시
    (validationPolicyHash — 현행 정책과 일치, validationCorpusHash — 존재)
    가 맞아야 반환. 전역 suspension 기록 존재=무조건 None(BYPASS).
    """
    adapter = resolve_validated_counter(resolved_model_id)
    if adapter is None:
        return None
    suspended, state_ok = _is_globally_suspended(
        adapter_identity_hash(adapter))
    if suspended or not state_ok:
        # 저장소 불가용(손상·권한)도 BYPASS(감수 54차 §2) — 'suspension
        # 없음'으로 처리하지 않는다.
        return None
    for entry in manifest_counters:
        if (entry.get("reviewed") is True
                and entry.get("resolvedModelId") == adapter.model_id
                and entry.get("providerId") == adapter.provider_id
                and entry.get("counterVersion") == adapter.counter_version
                and entry.get("providerRequestSchemaVersion")
                == adapter.request_schema_version
                and entry.get("validationPolicyHash")
                == adapter_validation_policy_hash()
                and entry.get("countMode") == adapter.mode
                and bool(adapter.validation_corpus_hash)
                and entry.get("validationCorpusHash")
                == adapter.validation_corpus_hash):
            return adapter
    return None


def record_count_observation(model_id: str, counted: int, reported: int,
                             request_id_hash: str = "") -> None:
    """canary 계수 관측(감수 52차 §2 + 53차 §3 — 전역 drift suspend).

    counted < reported(과소 계산) 1건이라도 관측되면: ①현 프로세스
    registry 즉시 SUSPENDED ②공유 suspension 파일에 원자적 기록(모든
    worker의 다음 요청부터 BYPASS) ③관측 필드(undercount 수·최초 요청
    hash·시각) 보존. VALIDATED→SUSPENDED 단방향 — 자동 복구 금지.
    """
    if counted >= reported:
        return
    _VALIDATION[model_id] = "SUSPENDED"
    adapter = _REGISTRY.get(model_id)
    identity = (adapter_identity_hash(adapter) if adapter is not None
                else f"unregistered:{model_id}")
    import fcntl
    import hashlib
    import hmac as _hmac
    import json as _json
    import os
    import tempfile
    from datetime import datetime

    from saju_engines import risk_engine_config
    # request id도 HMAC(감수 54차 §9 — 순차·예측 가능 원문 비노출).
    rid_hash = _hmac.new(risk_engine_config.RISK_AUDIT_HMAC_KEY,
                         request_id_hash.encode(),
                         hashlib.sha256).hexdigest()[:16]
    _SUSPENSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    # process-safe RMW(감수 54차 §2 + 55차 §2): flock 대상은 **교체되지
    # 않는 전용 lock 파일**(데이터 파일은 replace로 inode 변경) + 동일
    # 프로세스 thread용 mutex 병행. temp는 같은 디렉터리(atomic 보장).
    with _IN_PROCESS_LOCK, open(_SUSPENSION_LOCK_FILE, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            # tombstone 선기록(감수 56차 §5 — append-only·삭제 금지):
            # state 파일과 독립적으로 identity 차단 사실을 영속화한다.
            with open(_SUSPENSION_LEDGER, "a", encoding="utf-8") as lf:
                lf.write(_json.dumps({
                    "identity": identity, "model_id": model_id,
                    "event": "SUSPENDED", "request_id_hash": rid_hash,
                    "at": datetime.now(UTC).isoformat(),
                }, ensure_ascii=False, sort_keys=True) + "\n")
                lf.flush()
                os.fsync(lf.fileno())
            records, _ok = _shared_suspensions()
            entry = records.get(identity) or {
                "model_id": model_id,
                "undercount_detected_count": 0,
                "first_undercount_request_id_hash": rid_hash,
                "adapter_suspended_at": datetime.now(UTC).isoformat(),
            }
            entry["undercount_detected_count"] += 1
            records[identity] = entry
            fd, tmp = tempfile.mkstemp(dir=str(_SUSPENSION_FILE.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(records, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, _SUSPENSION_FILE)
            dir_fd = os.open(str(_SUSPENSION_FILE.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # persistence 실패(감수 55차 §4) — 로컬 SUSPENDED만으로는 전역
            # 보장이 없다: 전역 marker 기록(실패 시 로컬 flag) → 모든
            # 해소가 BYPASS로 강등.
            global _LOCAL_PERSISTENCE_FAILED
            try:
                _EXPOSURE_DISABLED_MARKER.write_text(
                    "suspension_persistence_failed", encoding="utf-8")
            except OSError:
                _LOCAL_PERSISTENCE_FAILED = True
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def resolve_counter(resolved_model_id: str) -> TokenCounterAdapter | None:
    """resolved model ID → adapter(없으면 None — 게이트가 BYPASS 처리).

    호출부 계약: 모델 fallback 발생 시 새 resolved ID로 다시 호출하고
    최종 request 전체를 재계수한다.
    """
    return _REGISTRY.get(resolved_model_id)
