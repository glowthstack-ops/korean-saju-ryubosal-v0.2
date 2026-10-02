"""문서·계약 주의점/대비 블록(2026-08-10 P2·P3) — 조건부 생성 + chat 배선.

structural_context의 document_caution_block(인성 과다=묶는 문서 / 약세=동요·지연)·
document_contrast_block(용신·희신+적정 세력=기회·결실 대비)이 조건 성립 명식에서만
생성되고(미성립=None → 프롬프트 byte 불변), 원시 퍼센트·위치 고정 문구를 노출하지
않으며, 문서·계약 도메인 질문의 chat 프롬프트까지 배선됨을 고정한다(서술 전용 inert).
"""

from __future__ import annotations


def _chart(birth_date: str):
    from saju_api.services.manse_service import calculate
    from saju_shared_types.birth_input import BirthInput

    return calculate(BirthInput(
        calendar_type="solar", birth_date=birth_date, birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date="2026-08-10",
    ))


def test_document_caution_excess() -> None:
    """인성군 세력 과다(>=30%) — '묶는 문서' 주의점 생성, 원시 퍼센트 미노출."""
    from saju_engines.structural_context import document_caution_block

    block = document_caution_block(_chart("1988-01-10"))  # resource 30%
    assert block is not None
    assert "묶는" in block
    assert "%" not in block  # 원시 수치 누출 금지(모듈 계약)
    assert "말미" not in block  # 마무리 계약 — 위치 고정 문구 금지


def test_document_caution_weak() -> None:
    """인성군 세력 약세(<12%) — 동요·지연 주의점 생성."""
    from saju_engines.structural_context import document_caution_block

    block = document_caution_block(_chart("1990-01-01"))  # resource 9%
    assert block is not None
    assert "지연" in block


def test_document_caution_absent_when_moderate() -> None:
    """중간 세력(12~30%) — 조건 미성립이면 None(기존 프롬프트 byte 불변)."""
    from saju_engines.structural_context import document_caution_block

    assert document_caution_block(_chart("1988-03-10")) is None  # resource 18%


def test_document_caution_wired_into_chat_prompt() -> None:
    """chat 배선 — 직업 도메인 질문 + 조건 성립 명식에서 프롬프트에 블록 포함."""
    from datetime import date

    import saju_api.services.chat_service as chat_service
    from saju_shared_types.birth_input import BirthInput

    birth = BirthInput(
        calendar_type="solar", birth_date="1988-01-10", birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date="2026-08-10",
    )
    res = chat_service.chat(
        birth, "올해 계약운 어때? 이직 계약서 써도 될까?", date(2026, 8, 10), dry_run=True,
    )
    assert res.prompt_preview is not None
    assert "[문서·계약 주의점" in res.prompt_preview


def test_document_contrast_favorable_moderate() -> None:
    """인성 용신+적정 세력 — 대비 관점 블록 생성(P3), 주의점 조건과 상호 배타."""
    from saju_engines.structural_context import (
        document_caution_block,
        document_contrast_block,
    )

    chart = _chart("1985-02-03")  # 인성 오행=용신, resource 23%
    assert document_caution_block(chart) is None
    block = document_contrast_block(chart)
    assert block is not None
    assert "기회·결실" in block
    assert "%" not in block


def test_document_contrast_absent_for_hansin() -> None:
    """인성이 한신(용/희 아님) — 대비 블록 미생성(과장 서술 방지)."""
    from saju_engines.structural_context import document_contrast_block

    assert document_contrast_block(_chart("1988-03-10")) is None  # 한신·18%


def test_document_blocks_mutually_exclusive_on_excess() -> None:
    """과다 명식 — 주의점만 생성되고 대비 블록은 None(세력 조건에서 배제)."""
    from saju_engines.structural_context import (
        document_caution_block,
        document_contrast_block,
    )

    chart = _chart("1988-01-10")  # resource 30%
    assert document_caution_block(chart) is not None
    assert document_contrast_block(chart) is None
