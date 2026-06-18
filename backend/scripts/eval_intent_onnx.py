"""ONNX 런타임(torch-free) contextual 임베딩 intent 정확도·레이턴시 측정.

런타임 의존성: onnxruntime + tokenizers + numpy (torch 미사용 — 본 스크립트에서 검증).
build_intent_onnx.py가 /tmp/intent_onnx 에 model.onnx·tokenizer.json·양자화 모델을 만든 뒤 실행.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

_BACKEND = Path(__file__).resolve().parents[1]
_CORPUS = _BACKEND / "dictionaries" / "intent_seed_corpus.json"
_EVAL = _BACKEND / "tests" / "fixtures" / "intent_eval.jsonl"
_OUT = Path("/tmp/intent_onnx")
_MAXLEN = 64


def _pick_model() -> Path:
    q = sorted(_OUT.glob("*quantized*.onnx"))
    return q[0] if q else next(iter(_OUT.glob("*.onnx")))


def _embed(sess: ort.InferenceSession, tok: Tokenizer, texts: list[str]) -> np.ndarray:
    want = {i.name for i in sess.get_inputs()}
    out: list[np.ndarray] = []
    for i in range(0, len(texts), 16):
        encs = tok.encode_batch(texts[i : i + 16])
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed: dict[str, np.ndarray] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in want:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in want}
        last = sess.run(None, feed)[0]  # (b, seq, hidden)
        m = mask[:, :, None].astype(np.float32)
        vec = (last * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        out.append(vec)
    v = np.vstack(out)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def main() -> None:
    model_path = _pick_model()
    tok = Tokenizer.from_file(str(_OUT / "tokenizer.json"))
    tok.enable_truncation(max_length=_MAXLEN)
    tok.enable_padding()
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    data = json.loads(_CORPUS.read_text("utf-8"))
    examples: list[str] = []
    ex_label: list[str] = []
    dom: dict[str, str] = {}
    for e in data["intents"]:
        dom[e["label"]] = e["domain"]
        for x in e["examples"]:
            examples.append(x)
            ex_label.append(e["label"])
    seed = _embed(sess, tok, examples)
    by: dict[str, list[int]] = defaultdict(list)
    for i, lab in enumerate(ex_label):
        by[lab].append(i)
    cl = list(by)
    cent = np.vstack([seed[ix].mean(0) for ix in by.values()])
    cent /= np.linalg.norm(cent, axis=1, keepdims=True) + 1e-9

    rows = [json.loads(x) for x in _EVAL.read_text("utf-8").splitlines() if x.strip()]
    t0 = time.perf_counter()
    qs = _embed(sess, tok, [r["q"] for r in rows])
    dt = (time.perf_counter() - t0) * 1000 / len(rows)
    gold = [r["domain"] for r in rows]
    n = len(rows)
    sims = qs @ seed.T
    cs = qs @ cent.T
    top1 = [dom[ex_label[int(np.argmax(sims[i]))]] for i in range(n)]
    ctr = [dom[cl[int(np.argmax(cs[i]))]] for i in range(n)]

    def acc(pred: list[str]) -> str:
        ok = sum(a == b for a, b in zip(pred, gold, strict=True))
        return f"{ok}/{n} = {ok / n:.1%}"

    print(f"모델: {model_path.name} ({model_path.stat().st_size / 1e6:.0f}MB)")
    print(f"런타임 torch 임포트됨? {'예' if 'torch' in sys.modules else '아니오(torch-free 확인)'}")
    print(f"  top1     : {acc(top1)}")
    print(f"  centroid : {acc(ctr)}")
    print(f"  추론 {dt:.1f}ms/문장 (onnxruntime CPU)")


if __name__ == "__main__":
    main()
