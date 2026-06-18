"""Intent 임베딩 분류기 (운영, 보조 신호) — ONNX contextual 임베딩, torch-free CPU.

규칙 파서(query_parser)가 domain=GENERAL/저신뢰일 때만 '보조'로 domain·event·query_type을
제안한다(rules-first). 런타임은 onnxruntime + tokenizers + numpy만 — torch 불요, LLM/API 비용 0
(절대원칙 9의 'LLM·추론 모드' 규정과 무관한 결정론적 임베딩). 점수·간지·합충·길흉 판정에는
일절 개입하지 않는다(절대원칙 1) — intent 라우팅 전용.

배경(2026-06-18 측정): char n-gram(12.5%)·정적 임베딩(70%)은 한국어 합성 의미를 못 잡았고,
contextual ko-sroberta를 ONNX int8(110MB, 6ms/CPU, torch-free)로 돌리면 평가셋에서 큰 폭 우위.
모델 스냅샷은 compiled/intent_onnx (scripts/build_intent_onnx.py로 생성, .sha256 무결성).

graceful: onnxruntime/tokenizers 미설치 또는 모델 부재면 분류기 비활성(available()=False) —
규칙 파서만으로 동작하며 오류를 던지지 않는다(절대원칙 11 — 보조 기능 부재가 차단 금지).
결정론: 고정 ONNX 스냅샷 + 고정 시드 코퍼스 → 동일 입력 동일 출력(캐시·회귀 테스트 가능).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:  # 선택적 런타임 의존성(pip install .[intent]) — 없으면 분류기 비활성.
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    _AVAILABLE = True
except ImportError:  # pragma: no cover - 의존성 미설치 환경
    np = None  # type: ignore[assignment]
    ort = None
    Tokenizer = None
    _AVAILABLE = False

_MAXLEN = 64
_BACKEND = Path(__file__).resolve().parents[3]
_DEFAULT_MODEL_DIR = _BACKEND / "compiled" / "intent_onnx"
_DEFAULT_CORPUS = _BACKEND / "dictionaries" / "intent_seed_corpus.json"


@dataclass(frozen=True)
class IntentSuggestion:
    """보조 분류 결과 — 규칙 폴백 시 채울 domain/event/query_type + 신뢰 지표."""

    domain: str
    event: str | None
    query_type: str | None
    label: str
    score: float  # centroid 코사인(0~1)
    margin: float  # top1 - top2 라벨 점수 차(모호도 — 클수록 확실)


class IntentEmbeddingClassifier:
    """ONNX contextual 임베딩 최근접(intent centroid) 분류기 — 보조 신호 전용."""

    def __init__(
        self,
        model_dir: Path = _DEFAULT_MODEL_DIR,
        corpus_path: Path = _DEFAULT_CORPUS,
    ) -> None:
        """ONNX 세션·토크나이저·시드 centroid를 1회 로드한다(의존성/모델 없으면 비활성)."""
        self._enabled = False
        model_path = model_dir / "model_quantized.onnx"
        tok_path = model_dir / "tokenizer.json"
        if not (_AVAILABLE and model_path.exists() and tok_path.exists()):
            return
        self._tok = Tokenizer.from_file(str(tok_path))
        self._tok.enable_truncation(max_length=_MAXLEN)
        self._tok.enable_padding()
        self._sess = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._sess.get_inputs()}

        data = json.loads(Path(corpus_path).read_text("utf-8"))
        examples: list[str] = []
        labels: list[str] = []
        self._meta: dict[str, dict] = {}
        for entry in data["intents"]:
            self._meta[entry["label"]] = entry
            for ex in entry["examples"]:
                examples.append(ex)
                labels.append(entry["label"])
        seed = self._embed(examples)
        groups: dict[str, list[int]] = defaultdict(list)
        for i, lab in enumerate(labels):
            groups[lab].append(i)
        self._labels = list(groups)
        centroid = np.vstack([seed[idx].mean(axis=0) for idx in groups.values()])
        self._centroid = centroid / (np.linalg.norm(centroid, axis=1, keepdims=True) + 1e-9)
        self._enabled = True

    def available(self) -> bool:
        """분류기 사용 가능 여부(의존성·모델 로드 성공)."""
        return self._enabled

    def _embed(self, texts: list[str]) -> np.ndarray:
        """문장 목록 → mean-pooling contextual 임베딩(L2 정규화). torch 미사용."""
        out: list[np.ndarray] = []
        for i in range(0, len(texts), 16):
            encs = self._tok.encode_batch(texts[i : i + 16])
            ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            feed = {k: v for k, v in feed.items() if k in self._inputs}
            last = self._sess.run(None, feed)[0]  # (b, seq, hidden)
            m = mask[:, :, None].astype(np.float32)
            vec = (last * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            out.append(vec)
        v = np.vstack(out)
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

    def classify(self, text: str) -> IntentSuggestion | None:
        """질의를 intent centroid와 코사인 비교해 최상위 제안을 반환한다(비활성·공백이면 None).

        게이트(임계·마진)는 호출 측이 결정한다 — 여기서는 점수·마진을 함께 실어 보고만 한다.
        """
        if not self._enabled or not text.strip():
            return None
        q = self._embed([text])[0]
        sims = self._centroid @ q
        order = np.argsort(-sims)
        best = int(order[0])
        top1 = float(sims[best])
        top2 = float(sims[int(order[1])]) if len(order) > 1 else 0.0
        entry = self._meta[self._labels[best]]
        return IntentSuggestion(
            domain=entry["domain"],
            event=entry.get("event"),
            query_type=entry.get("query_type"),
            label=entry["label"],
            score=round(top1, 4),
            margin=round(top1 - top2, 4),
        )


_singleton: IntentEmbeddingClassifier | None = None


def get_intent_classifier() -> IntentEmbeddingClassifier:
    """프로세스 1회 로드 싱글턴(기동 warm). 의존성·모델 없으면 available()=False로 반환."""
    global _singleton
    if _singleton is None:
        _singleton = IntentEmbeddingClassifier()
    return _singleton
