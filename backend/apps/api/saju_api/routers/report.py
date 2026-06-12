"""풀이 상품(보고서) 엔드포인트 (v2.2.1 PR-E — Phase 9 운영 배선, docs/10)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.report import ReportResult, ReportSpec

from ..services import report_service

router = APIRouter(prefix="/api/v2/report", tags=["report"])


class ReportRequest(BaseModel):
    """보고서 생성 요청 — dry_run=True면 LLM 미호출(섹션 프롬프트 미리보기)."""

    birth: BirthInput
    spec: ReportSpec
    today: date | None = None
    dry_run: bool = False
    display_name: str = Field(default="회원", max_length=30)


class SectionPreview(BaseModel):
    """dry-run 섹션 미리보기 1건."""

    section_id: str
    prompt_chars: int
    allowed_ganji_count: int
    evidence_path_count: int
    body_prompt: str


class ReportDryRunResponse(BaseModel):
    """dry-run 응답 — 전 섹션 컨텍스트 요약."""

    status: str = "dry_run"
    section_count: int
    sections: list[SectionPreview]


@router.post("")
def generate(req: ReportRequest) -> ReportResult | ReportDryRunResponse:
    """보고서 생성(RPT_FULL 22섹션 / RPT_FOCUS 8섹션) 또는 dry-run 미리보기."""
    if req.dry_run:
        contexts = report_service.plan_report(req.birth, req.spec, req.today)
        return ReportDryRunResponse(
            section_count=len(contexts),
            sections=[
                SectionPreview(
                    section_id=c.section_id,
                    prompt_chars=len(c.body_prompt),
                    allowed_ganji_count=len(c.allowed_ganji),
                    evidence_path_count=len(c.evidence_paths),
                    body_prompt=c.body_prompt,
                )
                for c in contexts
            ],
        )
    try:
        return report_service.generate_report(
            req.birth, req.spec, req.today, display_name=req.display_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
