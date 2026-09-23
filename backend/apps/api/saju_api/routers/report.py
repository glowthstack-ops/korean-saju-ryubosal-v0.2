"""풀이 상품(보고서) 엔드포인트 (v2.2.1 PR-E — Phase 9 운영 배선, docs/10).

동기 POST는 dry-run 미리보기 전용으로 유지하고, 실제 생성(RPT_FULL 22섹션은 수 분)은
비동기 잡(POST /jobs) + 폴링(GET /jobs/{id})으로 처리한다(v2.2 프론트 확장 Phase 6).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.report_job_store import ReportJobStore
from saju_engines.report_plan import build_section_plans, is_pair_relationship
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind
from saju_shared_types.report import ReportResult, ReportSpec

from ..deps import get_report_job_store, get_subject_store, require_owner
from ..services import error_logging, report_service
from ..services.partner_resolve import inline_to_birth

router = APIRouter(prefix="/api/v2/report", tags=["report"])


def _resolve_partner_birth(
    spec: ReportSpec, subjects: SubjectStore | None, owner_id: str | None,
) -> BirthInput | None:
    """관계운 궁합 모드 — 상대 subject를 BirthInput으로 해석.

    INLINE_TEMP(inline_birth)는 그 자리에서, COMPANION(companion_id)은 SubjectStore로 조회.
    상대를 해석하지 못하면 None(서비스는 단독 모드로 강등 — 빈 궁합 블록 안내).
    """
    if not is_pair_relationship(spec):
        return None
    partner = next((s for s in spec.subjects if s.kind != SubjectKind.SELF), None)
    if partner is None:
        return None
    if partner.inline_birth is not None:
        return inline_to_birth(partner.inline_birth)
    if subjects is not None and partner.companion_id:
        rec = subjects.get(partner.companion_id)
        if rec is not None and (owner_id is None or rec.owner_id == owner_id):
            return rec.birth
    return None

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
    partner_birth = _resolve_partner_birth(req.spec, None, None)
    if req.dry_run:
        contexts = report_service.plan_report(
            req.birth, req.spec, req.today, partner_birth=partner_birth,
        )
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
            partner_birth=partner_birth,
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
    #: 작성 시점(ISO) — PDF 저장 파일명 등 내용 식별용(2026-08-24).
    created_at: str | None = None


def _run_report_job(
    job_id: str, birth: BirthInput, spec: ReportSpec, today: date | None, display_name: str,
    owner_id: str, subject_id: str, partner_birth: BirthInput | None = None,
) -> None:
    """백그라운드 실행 — 생성 성공 시 complete, LLM 키 미설정 등 실패 시 fail."""
    store = ReportJobStore()
    store.mark_running(job_id)

    def _on_progress(done: int, total: int) -> None:
        # total = 분할 페이지 확장 후 실제 총 장 수 — 생성 시점의 확장 전 계획 수를 교체한다.
        try:
            store.update_progress(job_id, done, total)
        except Exception:  # noqa: BLE001 — 진행 갱신 실패가 생성을 막지 않도록
            pass

    try:
        result = report_service.generate_report(
            birth, spec, today, display_name=display_name,
            owner_id=owner_id, subject_id=subject_id, partner_birth=partner_birth,
            progress_fn=_on_progress,
        )
        store.complete(job_id, result.model_dump(mode="json"), len(result.sections))
    except RuntimeError as exc:
        store.fail(job_id, str(exc))
        _log_job_error(exc, job_id, owner_id, str(exc))
    except Exception as exc:  # noqa: BLE001 — 잡 실패는 사유 보존이 우선
        store.fail(job_id, f"생성 오류: {exc}")
        _log_job_error(exc, job_id, owner_id, f"생성 오류: {exc}")


def _log_job_error(exc: BaseException, job_id: str, owner_id: str, message: str) -> None:
    """리포트 잡 실패를 에러 모니터링에 적재 — 이미 기록된 예외(예: LLM 실패)는 중복 제외."""
    if error_logging.is_logged(exc):
        return
    with contextlib.suppress(Exception):
        error_logging.record_error(
            source="report_job", kind=type(exc).__name__, message=message,
            path="report.generate", owner_id=owner_id, ref_id=job_id, exc=exc,
        )


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
    # LLM 키가 없으면 잡을 만들지 않고 즉시 안내(분 단위 뒤 실패하는 doomed 잡 방지).
    if not report_service.llm_client.is_available():
        raise HTTPException(
            status_code=503, detail="LLM API 키 미설정 — 생성을 일시적으로 사용할 수 없습니다.",
        )
    partner_birth = _resolve_partner_birth(req.spec, subjects, owner_id)
    job_id = uuid.uuid4().hex
    total = len(build_section_plans(req.spec))
    jobs.create(job_id, owner_id, req.spec.model_dump(mode="json"), total)
    background.add_task(
        _run_report_job, job_id, record.birth, req.spec, req.today, record.label,
        owner_id, req.subject_id, partner_birth,
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
        created_at=rec.created_at.isoformat() if rec.created_at else None,
    )
