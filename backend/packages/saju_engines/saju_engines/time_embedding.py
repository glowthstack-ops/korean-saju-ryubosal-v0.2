"""TimeBucket 임베딩 분류기 (운영, 보조 신호) — ONNX contextual 임베딩, torch-free CPU.

규칙 파서(time_parser)가 시점을 못 잡았을 때만 '보조'로 시점 버킷을 제안한다(rules-first).
intent_embedding과 동일한 ONNX 모델(compiled/intent_onnx)을 재사용하며, 시드는 시점 표현
코퍼스(time_seed_corpus.json)다. 버킷→날짜 변환은 결정론 코드(time_parser.bucket_to_range)가
today 기준으로 수행 — 분류기는 '버킷'만 고른다(절대원칙 1·9 무관, 결정론적 임베딩).

graceful: onnxruntime/tokenizers 미설치 또는 모델 부재면 비활성(available()=False) — 규칙 파서만
으로 동작하며 오류를 던지지 않는다(절대원칙 11). 결정론: 고정 ONNX + 고정 시드 → 동일 입력 동일
출력(회귀 테스트 가능). 임베딩 로더는 intent_embedding과 동일 구조를 자립 복제했다(워킹 중인
intent 분류기 무수정 — 회귀 위험 차단).
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
_DEFAULT_CORPUS = _BACKEND / "dictionaries" / "time_seed_corpus.json"


@dataclass
class TimeBucketSuggestion:
    """시점 버킷 제안(보조 신호) — 게이트(임계·마진)는 호출 측이 결정한다."""

    label: str
    score: float
    margin: float


class TimeBucketClassifier:
    """ONNX contextual 임베딩 최근접(버킷 centroid) 분류기 — 보조 신호 전용."""

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
        for entry in data["buckets"]:
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

    def classify(self, text: str) -> TimeBucketSuggestion | None:
        """질의를 버킷 centroid와 코사인 비교해 최상위 제안을 반환한다(비활성·공백이면 None)."""
        if not self._enabled or not text.strip():
            return None
        q = self._embed([text])[0]
        sims = self._centroid @ q
        order = np.argsort(-sims)
        best = int(order[0])
        top1 = float(sims[best])
        top2 = float(sims[int(order[1])]) if len(order) > 1 else 0.0
        return TimeBucketSuggestion(
            label=self._labels[best],
            score=round(top1, 4),
            margin=round(top1 - top2, 4),
        )


_singleton: TimeBucketClassifier | None = None


def get_time_classifier() -> TimeBucketClassifier:
    """프로세스 1회 로드 싱글턴(기동 warm). 의존성·모델 없으면 available()=False로 반환."""
    global _singleton
    if _singleton is None:
        _singleton = TimeBucketClassifier()
    return _singleton
