"""검증 사례(cases.jsonl) 적재/조회 (v2.2 Phase 6 T6.2, docs/05).

Past Validation 피드백과 예측 실패 신고(B10/Q12)를 누적해 회귀 테스트·가중치 보정
자료로 쓴다. 행 스키마(docs/05): caseId, signals[], predictedEvent, actualEvent,
time, matched, notes. 사례가 충분히 쌓이기 전까지 점수 절대값 신뢰 금지(docs/07
리스크 1) — 이 파일이 그 누적 원천이다.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "cases.jsonl"
)


class CaseRow(BaseModel):
    """cases.jsonl 한 행 (docs/05 스키마 — camelCase 키)."""

    case_id: str = Field(alias="caseId")
    signals: list[str] = Field(default_factory=list)
    predicted_event: str = Field(alias="predictedEvent")
    actual_event: str | None = Field(default=None, alias="actualEvent")
    time: str = ""  # '2026-06' / '2009'
    matched: bool = False
    notes: str | None = None

    model_config = {"populate_by_name": True}


class CasesStore:
    """JSONL append 전용 스토어 — UTF-8, 행 단위(쓰기 멱등 아님: 호출 측이 중복 관리)."""

    def __init__(self, path: Path | None = None) -> None:
        """기본 경로는 tests/fixtures/cases.jsonl(docs/05 레이아웃)."""
        self._path = path or _DEFAULT_PATH

    @property
    def path(self) -> Path:
        """저장 파일 경로."""
        return self._path

    def append(self, row: CaseRow) -> None:
        """사례 1건 추가(파일·디렉토리 자동 생성)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row.model_dump(by_alias=True), ensure_ascii=False) + "\n")

    def load(self) -> list[CaseRow]:
        """전체 사례 로드(없으면 빈 목록)."""
        if not self._path.exists():
            return []
        rows: list[CaseRow] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(CaseRow.model_validate(json.loads(line)))
        return rows

    def next_case_id(self) -> str:
        """다음 caseId('case_NNN') — 기존 행 수 기반."""
        return f"case_{len(self.load()) + 1:03d}"
