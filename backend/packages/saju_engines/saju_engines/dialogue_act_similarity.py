"""대화 행위 유사도 폴백 — 결론 요구형 변형 표현 (2026-07-14 후속②, 보조 신호).

룰(conversation._CONCLUSION_SEEK_RE)이 놓친 완곡·변형 결론 요구("한마디로 돼 안 돼?",
"요점만 말해줘")를 임베딩 최근접으로 보강한다(rules-first — 룰이 이미 dialogue_act를
확정했으면 호출 측이 스킵). conclusion_summary만 배선하며, 점수·간지·판정에는 일절
개입하지 않는다(절대원칙 1·9). intent_embedding과 동일한 ONNX 모델(compiled/intent_onnx)
을 재사용하고 시드만 다르다(time_embedding·companion_similarity와 동일한 자립 복제 관례).

graceful: onnxruntime/tokenizers 미설치 또는 모델 부재면 비활성(available()=False) —
룰만으로 동작하며 오류를 던지지 않는다. 결정론: 고정 ONNX + 고정 시드 → 동일 입력 동일 출력.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:  # 선택적 런타임 의존성(pip install .[intent]) — 없으면 비활성.
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
_DEFAULT_CORPUS = _BACKEND / "dictionaries" / "dialogue_act_seed_corpus.json"

# 보조 게이트 — 1차 안전은 embedding이 아니라 '후속 턴 + 같은 도메인 + 룰 미확정'이라는
# 대화 구성 게이트다(새 질문·도메인 전환은 그 구성 자체가 안 돼 걸러진다). score/margin은
# 2차 정제(companion_similarity mode 게이트와 동일 수준에서 출발, 실측 후 조정).
DIALOGUE_ACT_MIN_SCORE = 0.60
DIALOGUE_ACT_MIN_MARGIN = 0.05


@dataclass(frozen=True)
class DialogueActSuggestion:
    """보조 분류 결과 — 대화 행위 라벨 + 신뢰 지표."""

    label: str  # 'conclusion_summary' | 'evidence_request' | 'reanalysis' | 'new_analysis'
    score: float  # centroid 코사인(0~1)
    margin: float  # top1 - top2(모호도 — 클수록 확실)


class DialogueActClassifier:
    """ONNX contextual 임베딩 최근접(대화 행위 centroid) 분류기 — 보조 신호 전용."""

    def __init__(
        self,
        model_dir: Path = _DEFAULT_MODEL_DIR,
        corpus_path: Path = _DEFAULT_CORPUS,
    ) -> None:
        """ONNX 세션·토크나이저·시드 centroid를 1회 로드한다(의존성/모델 없으면 비활성)."""
        self._enabled = False
        model_path = model_dir / "model_quantized.onnx"
        tok_path = model_dir / "tokenizer.json"
        if not (_AVAILABLE and model_path.exists() and tok_path.exists()
                and Path(corpus_path).exists()):
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
        for entry in data["intents"]:
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
        """분류기 사용 가능 여부(의존성·모델·코퍼스 로드 성공)."""
        return self._enabled

    def _embed(self, texts: list[str]) -> np.ndarray:
        """문장 목록 → mean-pooling contextual 임베딩(L2 정규화). torch 미사용."""
        out: list[np.ndarray] = []
        for i in range(0, len(texts), 16):
            encs = self._tok.encode_batch(texts[i: i + 16])
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

    def classify(self, text: str) -> DialogueActSuggestion | None:
        """질의를 행위 centroid와 코사인 비교해 최상위 제안을 반환한다(비활성·공백이면 None).

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
        return DialogueActSuggestion(
            label=self._labels[best],
            score=round(top1, 4),
            margin=round(top1 - top2, 4),
        )


_singleton: DialogueActClassifier | None = None


def get_dialogue_act_classifier() -> DialogueActClassifier:
    """프로세스 1회 로드 싱글턴(기동 warm). 의존성·모델 없으면 available()=False로 반환."""
    global _singleton
    if _singleton is None:
        _singleton = DialogueActClassifier()
    return _singleton
