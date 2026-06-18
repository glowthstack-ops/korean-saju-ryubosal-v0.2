"""ko-sroberta → ONNX export + 동적 양자화(빌드타임 1회, torch 사용).

런타임(eval_intent_onnx.py)은 onnxruntime+tokenizers만 쓴다(torch 불요, CPU, 무API).
산출물은 /tmp/intent_onnx (프로토타입 — 큰 모델이라 git 미추적). 운영화 시 compiled/로 버전 태깅.
"""

from __future__ import annotations

from pathlib import Path

_TEACHER = "jhgan/ko-sroberta-multitask"
_OUT = Path("/tmp/intent_onnx")


def main() -> None:
    from optimum.onnxruntime import ORTModelForFeatureExtraction, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from transformers import AutoTokenizer

    _OUT.mkdir(parents=True, exist_ok=True)
    print(f"export {_TEACHER} → ONNX ...")
    model = ORTModelForFeatureExtraction.from_pretrained(_TEACHER, export=True)
    model.save_pretrained(_OUT)
    AutoTokenizer.from_pretrained(_TEACHER).save_pretrained(_OUT)
    print("fp32 ONNX 저장 완료")

    print("동적 양자화(int8, avx2) ...")
    quantizer = ORTQuantizer.from_pretrained(_OUT)
    qconfig = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
    quantizer.quantize(save_dir=_OUT, quantization_config=qconfig)
    print("양자화 완료")

    for p in sorted(_OUT.glob("*.onnx")):
        print(f"  {p.name}: {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
