"""관계 이벤트 어휘 SSOT 로더·검증 — P0-B1 (RELATIONSHIP_EVENT_SYSTEM 부록 C-5).

`dictionaries/relationship_event_vocab.json`이 canonical 21키 + legacy alias의 기계 검증
기준이다. 이후 3층 타입·상태 해소기·REL shadow 배선이 이 어휘를 참조한다.

lint 계층 분담:
- 본 모듈 `validate_vocab`: 파일 자체로 닫히는 규칙(중복·순환·충돌·owner·daily·tombstone).
- 교차 참조 lint(TopicBuilder·structure pattern·Event Graph·EVENT_DOMAIN 일치):
  `tests/unit/test_relationship_event_vocab.py` — 참조 대상 모듈을 임포트해 검증한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
VOCAB_FILENAME = "relationship_event_vocab.json"


class VocabEntry(BaseModel):
    """어휘 항목 — 부록 C-5 필수 필드."""

    canonical_key: str
    legacy_aliases: list[str] = Field(default_factory=list)
    family: str
    owner: str  # 소유 시스템(빈 값 금지 — lint)
    personalized_allowed: bool = True
    daily_allowed: bool = False
    deprecated: bool = False
    replacement: str | None = None  # deprecated=True면 필수(또는 tombstone)
    tombstone: str | None = None    # 폐기 사유 기록(replacement 부재 시 필수)


class VocabFile(BaseModel):
    """어휘 파일 전체."""

    schema_name: str = Field(alias="schema")
    version: str
    notes: list[str] = Field(default_factory=list)
    items: list[VocabEntry]

    def canonical_keys(self) -> set[str]:
        return {e.canonical_key for e in self.items}

    def alias_map(self) -> dict[str, str]:
        """legacy alias → canonical key (검증 전 호출 시 중복은 마지막 항목 우선)."""
        return {
            alias: e.canonical_key for e in self.items for alias in e.legacy_aliases
        }


@lru_cache(maxsize=2)
def load_relationship_event_vocab(dictionaries_dir: str | None = None) -> VocabFile:
    """어휘 파일 로드(캐시). 유효성은 `validate_vocab`로 별도 검사한다."""
    base = Path(dictionaries_dir) if dictionaries_dir else _DICTS_DEFAULT
    return VocabFile.model_validate(
        json.loads((base / VOCAB_FILENAME).read_text(encoding="utf-8"))
    )


def validate_vocab(vocab: VocabFile) -> list[str]:
    """파일 자체로 닫히는 lint(부록 C-5). 위반 목록 반환(빈 목록=통과).

    규칙: canonical 중복 금지 / alias 중복 금지 / alias-canonical 충돌 금지 /
    alias 순환(자기 자신 alias) 금지 / owner 없는 키 금지 / 폐기 키는
    replacement 또는 tombstone 필수 / replacement는 등록된 canonical이어야 함.
    """
    errors: list[str] = []
    canon = [e.canonical_key for e in vocab.items]
    canon_set = set(canon)
    if len(canon) != len(canon_set):
        dup = sorted({k for k in canon if canon.count(k) > 1})
        errors.append(f"canonical 중복: {dup}")

    seen_alias: dict[str, str] = {}
    for e in vocab.items:
        if not e.owner.strip():
            errors.append(f"owner 없는 키: {e.canonical_key}")
        for alias in e.legacy_aliases:
            if alias == e.canonical_key:
                errors.append(f"alias 순환(자기 자신): {alias}")
            if alias in canon_set:
                errors.append(f"alias-canonical 충돌: {alias}")
            if alias in seen_alias:
                errors.append(
                    f"alias 중복: {alias} ({seen_alias[alias]} vs {e.canonical_key})"
                )
            seen_alias[alias] = e.canonical_key
        if e.deprecated and e.replacement is None and e.tombstone is None:
            errors.append(f"폐기 키에 replacement/tombstone 없음: {e.canonical_key}")
        if e.replacement is not None and e.replacement not in canon_set:
            errors.append(
                f"replacement 미등록 canonical: {e.canonical_key} -> {e.replacement}"
            )
    return errors
