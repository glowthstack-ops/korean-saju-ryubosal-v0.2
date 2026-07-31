#!/usr/bin/env python3
"""폴백(OpenAI) 모델 호환성 smoke — 실제 계정·실제 요청 형태 (opt-in).

폴백은 메인(Gemini) 장애 시에만 탄다. 그래서 요청 파라미터가 호환되지 않아도 평소에는
드러나지 않다가 **정작 필요한 순간에 터진다**. 모델을 바꾼 뒤 이걸 닫아두려면 실제
호출이 유일한 근거다 — 모델 목록 조회는 계정이 그 모델을 쓸 수 있다는 것까지만 말하고,
특정 파라미터 조합의 성공은 보장하지 않는다.

요청은 문서 예시가 아니라 **production 어댑터(`_call_openai`)가 만드는 그대로**를 쓴다.
현재 어댑터는 Responses API 가 아니라 chat.completions 이고 `generation_extras` 를 body
최상위에 펼친다. 예시로 바꿔 시험하면 운영에서 실제로 나가는 요청을 검증하지 못한다.

세 단계다. 마지막 음성 대조가 없으면 결론이 뒤집힌다 — 엔드포인트가 모르는 필드를
그냥 무시하는 경우, 정상 호출 성공만으로는 "파라미터가 수용됐다" 를 말할 수 없다.

    A  모델 접근        GET /v1/models/{model}
    B  운영 요청 그대로  reasoning_effort 포함
    C  음성 대조        불가능한 effort 값 → **실패해야 한다**

CI·서버 시작 시 자동 실행 금지. `--confirm-live-call` 없이는 아무 호출도 하지 않는다.

이 smoke 실패를 운영 중 자동 retry 로 해결하면 안 된다. 파라미터 오류 후 reasoning 을
빼고 재호출하면 요청당 호출 횟수 제한과 실패 예측 가능성이 함께 깨진다. 비호환으로
판정되면 별건으로 model capability 설정을 두고 **호출 전에** 포함 여부를 정한다.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import httpx  # noqa: E402

from saju_api.services import llm_client  # noqa: E402

#: 불가능한 effort 값 — 서버가 파라미터를 실제로 해석한다면 반드시 거부해야 한다.
_IMPOSSIBLE_EFFORT = "definitely-not-a-valid-effort-value"

_SYSTEM = "You are a connectivity probe. Reply with exactly one word."
_PROMPT = "Reply with the single word: ok"
_MAX_TOKENS = 256   # reasoning 모델은 추론에도 출력 토큰을 쓴다 — 너무 줄이면 빈 응답
_TIMEOUT = 60.0


class _Recorder:
    """production 어댑터가 실제로 보낸 요청·받은 응답을 가로채 기록한다.

    `_call_openai` 는 텍스트·토큰만 돌려주고 응답의 `model` 필드를 버린다. 요청 형태는
    운영 그대로 두면서 반환 모델까지 확인하려면 전송 계층에서 봐야 한다.
    """

    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self.status: int | None = None
        self._orig = httpx.post

    def __enter__(self) -> _Recorder:
        def spy(url: str, **kw: Any) -> httpx.Response:
            self.request = copy.deepcopy(kw.get("json"))
            res = self._orig(url, **kw)
            self.status = res.status_code
            try:
                self.response = res.json()
            except ValueError:
                self.response = None
            return res

        httpx.post = spy  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: object) -> None:
        httpx.post = self._orig  # type: ignore[assignment]


def _classify_http_error(body: dict[str, Any] | None, status: int | None) -> str:
    """공급자 실패를 원인별로 나눈다. 뭉뚱그리면 대응이 달라지는데 구분이 안 된다."""
    if status in (401, 403):
        return "PROVIDER_AUTH_FAILURE"
    err = (body or {}).get("error") or {}
    param, code = err.get("param"), err.get("code")
    msg = str(err.get("message", ""))
    if status == 404 or code == "model_not_found":
        return "MODEL_NOT_AVAILABLE"
    if param == "reasoning_effort" or "reasoning_effort" in msg:
        if code == "unsupported_value" or "value" in str(code or ""):
            return "REASONING_VALUE_UNSUPPORTED"
        return "REASONING_PARAMETER_UNSUPPORTED"
    return "OTHER_PROVIDER_FAILURE"


def _model_access(profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A — 계정이 이 모델을 쓸 수 있는가. 요청 성공까지 보장하지는 않는다."""
    key = llm_client._api_key(profile)
    if not key:
        return "PROVIDER_AUTH_FAILURE", {"detail": f"{profile['api_key_env']} 미설정"}
    res = httpx.get(
        f"https://api.openai.com/v1/models/{profile['model']}",
        headers={"Authorization": f"Bearer {key}"},
        timeout=_TIMEOUT,
    )
    try:
        body = res.json()
    except ValueError:
        body = {}
    if res.status_code == 200:
        return "FALLBACK_MODEL_ACCESS_CONFIRMED", {"model": body.get("id")}
    return _classify_http_error(body, res.status_code), {
        "status": res.status_code, "body": body,
    }


def _live_call(profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """B — production 어댑터가 만드는 요청 그대로 한 번 호출한다."""
    with _Recorder() as rec:
        try:
            text, tin, tout, cached = llm_client._call_openai(
                profile, _SYSTEM, _PROMPT, _MAX_TOKENS, _TIMEOUT
            )
        except httpx.HTTPStatusError:
            return _classify_http_error(rec.response, rec.status), {
                "request": rec.request, "response": rec.response,
            }
        except Exception as exc:  # noqa: BLE001 - 원인 보존이 목적
            return "OTHER_PROVIDER_FAILURE", {"exception": repr(exc)}
    return "LIVE_CALL_OK", {
        "sent_reasoning_effort": (rec.request or {}).get("reasoning_effort"),
        "returned_model": (rec.response or {}).get("model"),
        "text": text.strip()[:80],
        "tokens": {"in": tin, "out": tout, "cached": cached},
    }


def _negative_control(profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """C — 불가능한 effort 값으로 호출한다. **성공하면 안 된다.**

    성공한다면 서버가 이 필드를 해석하지 않고 무시한다는 뜻이고, B 의 성공은
    "파라미터가 수용됐다" 의 근거가 되지 못한다.
    """
    probe = copy.deepcopy(profile)
    probe.setdefault("generation_extras", {})["reasoning_effort"] = _IMPOSSIBLE_EFFORT
    with _Recorder() as rec:
        try:
            llm_client._call_openai(probe, _SYSTEM, _PROMPT, _MAX_TOKENS, _TIMEOUT)
        except httpx.HTTPStatusError:
            return "NEGATIVE_CONTROL_REJECTED", {
                "status": rec.status,
                "error": ((rec.response or {}).get("error") or {}).get("message"),
            }
        except Exception as exc:  # noqa: BLE001
            return "NEGATIVE_CONTROL_INCONCLUSIVE", {"exception": repr(exc)}
    return "REASONING_PARAMETER_IGNORED", {"request": rec.request}


def main() -> int:
    """3단계 smoke 를 순서대로 실행하고 판정을 출력한다."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--confirm-live-call", action="store_true",
        help="실제 OpenAI 유료 호출 3건을 수행한다. 없으면 아무것도 호출하지 않는다.",
    )
    args = ap.parse_args()

    profile = copy.deepcopy(llm_client.load_config()["fallback"])
    print(f"모델: {profile['model']}  generation_extras: {profile.get('generation_extras')}")
    if not args.confirm_live_call:
        print("\n--confirm-live-call 미지정 — 외부 호출 없이 종료합니다(opt-in).")
        return 0

    results: dict[str, Any] = {}

    verdict, detail = _model_access(profile)
    results["A_model_access"] = {"verdict": verdict, **detail}
    print(f"\nA 모델 접근      {verdict}")
    if verdict != "FALLBACK_MODEL_ACCESS_CONFIRMED":
        print(json.dumps(detail, ensure_ascii=False, indent=2)[:800])
        print("\n최종: " + verdict)
        return 1

    verdict_b, detail_b = _live_call(profile)
    results["B_live_call"] = {"verdict": verdict_b, **detail_b}
    print(f"B 운영 요청      {verdict_b}")
    if verdict_b != "LIVE_CALL_OK":
        print(json.dumps(detail_b, ensure_ascii=False, indent=2)[:1200])
        print("\n최종: " + verdict_b)
        return 1
    print(f"   보낸 effort={detail_b['sent_reasoning_effort']!r}  "
          f"반환 model={detail_b['returned_model']!r}  "
          f"tokens={detail_b['tokens']}  text={detail_b['text']!r}")

    verdict_c, detail_c = _negative_control(profile)
    results["C_negative_control"] = {"verdict": verdict_c, **detail_c}
    print(f"C 음성 대조      {verdict_c}")
    print(f"   {json.dumps(detail_c, ensure_ascii=False)[:400]}")

    print()
    if verdict_c == "NEGATIVE_CONTROL_REJECTED":
        print("FALLBACK_MODEL_ACCESS_CONFIRMED")
        print("FALLBACK_REASONING_PARAMETER_CONFIRMED")
        return 0
    if verdict_c == "REASONING_PARAMETER_IGNORED":
        print("FALLBACK_MODEL_ACCESS_CONFIRMED")
        print("REASONING_PARAMETER_IGNORED — 호출은 성공하나 수용 근거가 되지 못한다.")
        return 1
    print("FALLBACK_MODEL_ACCESS_CONFIRMED")
    print(f"{verdict_c} — 음성 대조가 결론을 내지 못했다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
