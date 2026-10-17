"""풀이 상품(보고서) 엔드포인트 (v2.2.1 PR-E — Phase 9 운영 배선, docs/10).

동기 POST는 dry-run 미리보기 전용으로 유지하고, 실제 생성(RPT_FULL 22섹션은 수 분)은
비동기 잡(POST /jobs) + 폴링(GET /jobs/{id})으로 처리한다(v2.2 프론트 확장 Phase 6).
잡 실행기·상대 해석은 `services/report_job_runner.py`(관리자 재개 경로와 공유, 2026-10-06).
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
from saju_shared_types.subject import RELATION_TO_USER_KO

from ..deps import get_report_job_store, get_subject_store, require_owner
from ..services import llm_service_state, report_service
from ..services.report_job_runner import resolve_partner_birth, run_report_job

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
    partner_birth = resolve_partner_birth(req.spec, None, None)
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
    # 비용 소진 일시 중단 — 신규 잡은 받지 않는다(큐 적재 시 재개 때 비용이 한꺼번에 나간다,
    # 데굴님 결정 2026-10-06). 진행 중이던 잡만 보류→재개 대상이다.
    if report_service.llm_client.is_suspended():
        raise HTTPException(status_code=503, detail=llm_service_state.SUSPENDED_REPORT_DETAIL)
    partner_birth = resolve_partner_birth(req.spec, subjects, owner_id)
    job_id = uuid.uuid4().hex
    total = len(build_section_plans(req.spec))
    jobs.create(job_id, owner_id, req.spec.model_dump(mode="json"), total)
    background.add_task(
        run_report_job, job_id, record.birth, req.spec, req.today, record.label,
        owner_id, req.subject_id, partner_birth,
    )
    return ReportJobCreated(job_id=job_id)


class ReportJobSubject(BaseModel):
    """목록용 대상 1명 — 라벨 + 관계(본인/동반자 관계유형 한글)."""

    label: str
    kind: str
    relation_type: str | None = None
    relation_label: str  # '본인' | RELATION_KO | '동반자'


class ReportJobSummary(BaseModel):
    """내 풀이 내역 1건 — 목록 표시용(본문 제외).

    2026-10-08 데굴님 지시: 연도(기간)·대상·관계가 없으면 내역에서 구분이 안 된다 → 선택값을
    함께 싣는다.
    """

    job_id: str
    status: str
    product_code: str
    topic: str | None = None
    subject_labels: list[str] = Field(default_factory=list)
    subjects: list[ReportJobSubject] = Field(default_factory=list)
    period_start: str | None = None  # 'YYYY-MM' — 한해풀이는 연도만 표시
    period_end: str | None = None
    sections_done: int
    sections_total: int
    created_at: str | None = None


def _self_relation_label(relation_to_user: object) -> str:
    """주 대상(kind=self)의 목록 라벨 — 등록 관계 키로만 정한다(2026-10-15 데굴님 승인).

    spec 의 kind=self 는 '이 잡의 주 대상'이지 '계정 본인'이 아니다(SubjectGateway 는 아무 명식이나
    주 대상으로 고른다 — 어머니 총운이 "박여사(본인)"으로 떴다). 채팅 모달(2026-10-14)과 같은 규칙:
    kind 로 '본인'을 추정하지 않고 relation_to_user 한글만 쓴다. 키가 아예 없는 레거시 잡은 종전대로
    '본인', ""(미설정)은 '관계 미설정'.
    """
    if relation_to_user is None:
        return "본인"
    key = str(relation_to_user)
    if not key:
        return "관계 미설정"
    return RELATION_TO_USER_KO.get(key, key)


def job_summary(j: dict) -> ReportJobSummary:
    """report_jobs 행(spec JSON 포함) → 목록 요약. 관계 라벨은 relationship_hints.RELATION_KO."""
    from saju_engines.relationship_hints import RELATION_KO, normalize_relation_type

    spec = j.get("spec") or {}
    subjects = [s for s in (spec.get("subjects") or []) if isinstance(s, dict)]
    subs: list[ReportJobSubject] = []
    for s in subjects:
        kind = str(s.get("kind", ""))
        rel = s.get("relation_type")
        if kind == "self":
            rel_label = _self_relation_label(s.get("relation_to_user"))
        elif rel:
            # 상대 관계는 테마 14종 또는 등록 키 17종 — 등록 키는 테마 어휘로 번역해 라벨링하고,
            # 번역이 없으면(other 등) 등록 한글, 그것도 없으면 '동반자'(영문 키 노출 금지,
            # 2026-10-15 실측: "mother" 그대로 떴다).
            _norm = normalize_relation_type(str(rel))
            rel_label = (
                RELATION_KO[_norm] if _norm else RELATION_TO_USER_KO.get(str(rel), "동반자")
            )
        else:
            rel_label = "동반자"
        subs.append(ReportJobSubject(label=str(s.get("label", "")), kind=kind,
                                     relation_type=rel, relation_label=rel_label))
    period = spec.get("period") or {}
    return ReportJobSummary(
        job_id=j["job_id"],
        status=j["status"],
        product_code=spec.get("product_code", ""),
        topic=spec.get("topic"),
        subject_labels=[s.label for s in subs],
        subjects=subs,
        period_start=period.get("start"),
        period_end=period.get("end"),
        sections_done=j["sections_done"],
        sections_total=j["sections_total"],
        created_at=_iso(j.get("created_at")),
    )


def _iso(value: object) -> str | None:
    """저장소가 datetime 또는 ISO 문자열을 줄 수 있어 둘 다 받는다."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@router.get("/jobs", response_model=list[ReportJobSummary])
def list_jobs(owner_id: OwnerId, jobs: Jobs) -> list[ReportJobSummary]:
    """내 풀이(리포트) 내역 — 최신순. 본문은 상세 조회(GET /jobs/{id})로."""
    return [job_summary(j) for j in jobs.list_by_owner(owner_id)]


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
