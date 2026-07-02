"""동반자 공동 풀이 모드 유사도 보강 (P3d — 보조 신호, shadow-first).

규칙(conversation._subject_mode)이 완곡·변형 표현을 놓쳐 mode를 확정 못 했을 때만 '보조'로
비교/경쟁/순위 의도 flavor(pairwise/compare_exclude_self/competition/ranking)를 제안한다
(rules-first). 실행 mode는 대상 구성(self 포함 여부·인원)과 결합해 호출 측이 결정하며, 이 분류는
점수·간지·판정에 일절 개입하지 않는다(절대원칙 1). intent_embedding과 동일한 ONNX 모델
(compiled/intent_onnx)을 재사용하고 시드만 다르다(time_embedding과 동일한 자립 복제 관례).

graceful: onnxruntime/tokenizers 미설치 또는 모델 부재면 비활성(available()=False) — 규칙만으로
동작하며 오류를 던지지 않는다. 결정론: 고정 ONNX + 고정 시드 → 동일 입력 동일 출력.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from saju_shared_types.intent import SubjectMode

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
_DEFAULT_CORPUS = _BACKEND / "dictionaries" / "companion_mode_seed_corpus.json"
_RELATION_CORPUS = _BACKEND / "dictionaries" / "companion_relation_seed_corpus.json"

# 실측 기반 보조 게이트(P3d — 2026-07-02). 기존 제안 0.78은 이 ONNX 분류기엔 과보수적이라
# 롱테일 참 양성을 놓쳤다(측정: 참=0.61~0.92, distractor=0.42~0.63). 1차 안전은 embedding이
# 아니라 '2명 이상 대상 해소 + 규칙 미확정 + companion_only 제외'라는 대상-구성 게이트다 —
# distractor(내 운·취업운 등)는 그 구성 자체가 안 되어 걸러진다. score/margin은 2차 정제.
_MODE_SIM_MIN_SCORE = 0.60
_MODE_SIM_MIN_MARGIN = 0.05

# 관계유형 보강(P3d-3) 게이트 — 실측상 mode보다 분리도가 좋다(참=0.67~0.88, distractor=0.39).
# 실행 경로를 바꾸지 않고 relationship_context.perspective_hints만 보강하므로 소폭 완화한다.
_RELATION_SIM_MIN_SCORE = 0.62
_RELATION_SIM_MIN_MARGIN = 0.03


@dataclass(frozen=True)
class CompanionModeSuggestion:
    """보조 분류 결과 — 규칙 폴백 시 참고할 비교/경쟁/순위 flavor + 신뢰 지표."""

    label: str  # 'pairwise' | 'compare_exclude_self' | 'competition' | 'ranking'
    score: float  # centroid 코사인(0~1)
    margin: float  # top1 - top2(모호도 — 클수록 확실)


class CompanionModeClassifier:
    """ONNX contextual 임베딩 최근접(mode centroid) 분류기 — 보조 신호 전용."""

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

    def classify(self, text: str) -> CompanionModeSuggestion | None:
        """질의를 mode centroid와 코사인 비교해 최상위 제안을 반환한다(비활성·공백이면 None).

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
        return CompanionModeSuggestion(
            label=self._labels[best],
            score=round(top1, 4),
            margin=round(top1 - top2, 4),
        )


_singleton: CompanionModeClassifier | None = None


def get_companion_mode_classifier() -> CompanionModeClassifier:
    """프로세스 1회 로드 싱글턴(기동 warm). 의존성·모델 없으면 available()=False로 반환."""
    global _singleton
    if _singleton is None:
        _singleton = CompanionModeClassifier()
    return _singleton


@dataclass(frozen=True)
class RelationSuggestion:
    """관계유형 보조 분류 결과 — relationship_context 관점 힌트 보강용."""

    relation_type: str  # spouse/romance/parent_child/family/friend/coworker/business_partner
    score: float
    margin: float


class CompanionRelationClassifier:
    """관계유형 centroid 분류기 — mode 분류기의 ONNX 세션을 재사용한다(모델 1회 로드)."""

    def __init__(self, corpus_path: Path = _RELATION_CORPUS) -> None:
        """관계유형 시드 centroid를 mode 분류기의 embed로 구성한다(세션 공유·비활성 시 무동작)."""
        self._enabled = False
        base = get_companion_mode_classifier()
        if not base.available():
            return
        self._base = base
        data = json.loads(Path(corpus_path).read_text("utf-8"))
        examples: list[str] = []
        labels: list[str] = []
        for entry in data["intents"]:
            for ex in entry["examples"]:
                examples.append(ex)
                labels.append(entry["label"])
        seed = base._embed(examples)
        groups: dict[str, list[int]] = defaultdict(list)
        for i, lab in enumerate(labels):
            groups[lab].append(i)
        self._labels = list(groups)
        centroid = np.vstack([seed[idx].mean(axis=0) for idx in groups.values()])
        self._centroid = centroid / (np.linalg.norm(centroid, axis=1, keepdims=True) + 1e-9)
        self._enabled = True

    def available(self) -> bool:
        return self._enabled

    def classify(self, text: str) -> RelationSuggestion | None:
        """질의를 관계유형 centroid와 코사인 비교해 최상위 제안을 반환(게이트는 호출 측)."""
        if not self._enabled or not text.strip():
            return None
        q = self._base._embed([text])[0]
        sims = self._centroid @ q
        order = np.argsort(-sims)
        best = int(order[0])
        top1 = float(sims[best])
        top2 = float(sims[int(order[1])]) if len(order) > 1 else 0.0
        return RelationSuggestion(
            relation_type=self._labels[best],
            score=round(top1, 4),
            margin=round(top1 - top2, 4),
        )


_relation_singleton: CompanionRelationClassifier | None = None


def get_companion_relation_classifier() -> CompanionRelationClassifier:
    """프로세스 1회 로드 싱글턴(mode 분류기 세션 재사용)."""
    global _relation_singleton
    if _relation_singleton is None:
        _relation_singleton = CompanionRelationClassifier()
    return _relation_singleton


def augment_relation_type(
    rule_relation: str, rule_basis: str, text: str, has_companion: bool,
) -> tuple[str, str]:
    """infer_relation_type이 unknown일 때만 관계유형을 유사도로 보강한다(rules-first, 힌트 전용).

    실행 mode/subject_blocks/base는 바꾸지 않는다 — relationship_context 관점 힌트만. 규칙/키워드/
    relation_to_user로 확정된 관계유형(rule_basis != 'unknown')은 절대 덮지 않는다.

    Returns:
        (relation_type, relation_basis). 보강 시 basis='similarity', 아니면 입력 그대로.
    """
    if rule_relation != "unknown" or rule_basis != "unknown" or not has_companion:
        return rule_relation, rule_basis
    sug = get_companion_relation_classifier().classify(text)
    if sug is None or sug.score < _RELATION_SIM_MIN_SCORE or sug.margin < _RELATION_SIM_MIN_MARGIN:
        return rule_relation, rule_basis
    return sug.relation_type, "similarity"


def suggest_companion_mode(text: str) -> CompanionModeSuggestion | None:
    """score/margin 2차 게이트를 통과한 보조 제안만 반환(그 외 None). 분류기 비활성 시 None.

    1차 안전(대상-구성·rules-first)은 augment_subject_mode/호출 측이 담당한다.
    """
    sug = get_companion_mode_classifier().classify(text)
    if sug is None:
        return None
    if sug.score < _MODE_SIM_MIN_SCORE or sug.margin < _MODE_SIM_MIN_MARGIN:
        return None
    return sug


def augment_subject_mode(
    rule_mode: SubjectMode,
    text: str,
    non_self_count: int,
    has_self: bool,
    suggestion: CompanionModeSuggestion | None = None,
) -> SubjectMode:
    """규칙이 비교 mode를 못 잡은 경우에만 유사도로 보강한다(rules-first, shadow 설계).

    안전장치 조합: ①rules-first(규칙이 pairwise/compare/ranking 확정이면 그대로) ②대상-구성
    게이트(총 2명 이상 + companion_only 1명 단독 제외) ③score/margin 게이트. embedding은
    'comparison 여부 + competition/ranking flavor'에만 쓰고, pairwise↔compare 구분과 최종
    arrangement는 대상 구성(self 포함·인원)이 결정한다(실측: 텍스트만으론 구분 불가).

    Args:
        rule_mode: 규칙(_subject_mode) 결과.
        text: 사용자 발화.
        non_self_count: 해소된 비-본인 대상 수(동반자+인라인).
        has_self: 본인 대상 포함 여부.
        suggestion: 주입된 제안(테스트/캐시). None이면 suggest_companion_mode(text) 사용.

    Returns:
        보강된 SubjectMode(보강 없으면 rule_mode 그대로).
    """
    # ① rules-first — 규칙이 비교/경쟁/순위를 확정했으면 절대 덮지 않는다.
    if rule_mode in (
        SubjectMode.PAIRWISE, SubjectMode.COMPARE_EXCLUDE_SELF, SubjectMode.RANKING,
    ):
        return rule_mode
    # ② 대상-구성 게이트 — 총 2명 이상 + companion_only(동반자 1명 단독)는 제외.
    total = non_self_count + (1 if has_self else 0)
    if total < 2 or (non_self_count == 1 and not has_self):
        return rule_mode
    # ③ score/margin 게이트.
    sug = suggestion if suggestion is not None else suggest_companion_mode(text)
    if sug is None:
        return rule_mode
    # arrangement는 구성으로 — competition/ranking flavor는 인원으로 축소.
    if non_self_count >= 3:
        return SubjectMode.RANKING
    if has_self and non_self_count == 1:
        return SubjectMode.PAIRWISE
    return SubjectMode.COMPARE_EXCLUDE_SELF
