"""풀이 상품(보고서) 엔드포인트 (v2.2.1 PR-E — Phase 9 운영 배선, docs/10).

동기 POST는 dry-run 미리보기 전용으로 유지하고, 실제 생성(RPT_FULL 22섹션은 수 분)은
비동기 잡(POST /jobs) + 폴링(GET /jobs/{id})으로 처리한다(v2.2 프론트 확장 Phase 6).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.report_job_store import ReportJobStore
from saju_engines.report_plan import build_section_plans
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.report import ReportResult, ReportSpec

from ..deps import get_report_job_store, get_subject_store, require_owner
from ..services import report_service

router = APIRouter(prefix="/api/v2/report", tags=["report"])

OwnerId = Annotated[str, Depends(require_owner)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]
Jobs = Annotated[ReportJobStore, Depends(get_report_job_store)]


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


# ── 비동기 잡(테마사주 실생성) ──────────────────────────────────


class ReportJobRequest(BaseModel):
    """잡 생성 요청 — 대상은 subject_id로 지정(서버가 출생정보·소유 검증)."""

    subject_id: str
    spec: ReportSpec
    today: date | None = None


class ReportJobCreated(BaseModel):
    """잡 생성 응답."""

    job_id: str


class ReportJobStatus(BaseModel):
    """잡 상태/진행 — 폴링 응답."""

    job_id: str
    status: str
    sections_done: int
    sections_total: int
    result: dict | None = None
    error: str | None = None


def _run_report_job(
    job_id: str, birth: BirthInput, spec: ReportSpec, today: date | None, display_name: str,
    owner_id: str, subject_id: str,
) -> None:
    """백그라운드 실행 — 생성 성공 시 complete, LLM 키 미설정 등 실패 시 fail."""
    store = ReportJobStore()
    store.mark_running(job_id)
    try:
        result = report_service.generate_report(
            birth, spec, today, display_name=display_name,
            owner_id=owner_id, subject_id=subject_id,
        )
        store.complete(job_id, result.model_dump(mode="json"), len(result.sections))
    except RuntimeError as exc:
        store.fail(job_id, str(exc))
    except Exception as exc:  # noqa: BLE001 — 잡 실패는 사유 보존이 우선
        store.fail(job_id, f"생성 오류: {exc}")


@router.post("/jobs", response_model=ReportJobCreated, status_code=202)
def create_job(
    req: ReportJobRequest,
    background: BackgroundTasks,
    owner_id: OwnerId,
    subjects: Subjects,
    jobs: Jobs,
) -> ReportJobCreated:
    """리포트 생성 잡 등록 → 백그라운드 실행. 대상 출생정보는 subject에서 가져온다."""
    record = subjects.get(req.subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="사주를 찾을 수 없습니다.")
    job_id = uuid.uuid4().hex
    total = len(build_section_plans(req.spec))
    jobs.create(job_id, owner_id, req.spec.model_dump(mode="json"), total)
    background.add_task(
        _run_report_job, job_id, record.birth, req.spec, req.today, record.label,
        owner_id, req.subject_id,
    )
    return ReportJobCreated(job_id=job_id)


class ReportJobSummary(BaseModel):
    """내 풀이 내역 1건 — 목록 표시용(본문 제외)."""

    job_id: str
    status: str
    product_code: str
    topic: str | None = None
    subject_labels: list[str] = Field(default_factory=list)
    sections_done: int
    sections_total: int
    created_at: str | None = None


@router.get("/jobs", response_model=list[ReportJobSummary])
def list_jobs(owner_id: OwnerId, jobs: Jobs) -> list[ReportJobSummary]:
    """내 풀이(리포트) 내역 — 최신순. 본문은 상세 조회(GET /jobs/{id})로."""
    out: list[ReportJobSummary] = []
    for j in jobs.list_by_owner(owner_id):
        spec = j.get("spec") or {}
        subjects = spec.get("subjects") or []
        out.append(
            ReportJobSummary(
                job_id=j["job_id"],
                status=j["status"],
                product_code=spec.get("product_code", ""),
                topic=spec.get("topic"),
                subject_labels=[s.get("label", "") for s in subjects if isinstance(s, dict)],
                sections_done=j["sections_done"],
                sections_total=j["sections_total"],
                created_at=j["created_at"],
            )
        )
    return out


@router.get("/jobs/{job_id}", response_model=ReportJobStatus)
def get_job(job_id: str, owner_id: OwnerId, jobs: Jobs) -> ReportJobStatus:
    """잡 상태/진행/결과 조회(소유자 한정)."""
    rec = jobs.get(job_id)
    if rec is None or rec.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return ReportJobStatus(
        job_id=rec.job_id,
        status=rec.status,
        sections_done=rec.sections_done,
        sections_total=rec.sections_total,
        result=rec.result,
        error=rec.error,
    )
