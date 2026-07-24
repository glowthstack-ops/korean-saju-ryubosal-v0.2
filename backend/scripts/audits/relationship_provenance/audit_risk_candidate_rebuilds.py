"""RiskCandidate 재구성 provenance 감사 — P1-6 (RELATIONSHIP_EVENT_SYSTEM 부록 D §5).

하드 게이트 1차 방어선(live_relationship_context_derived 단조 보존)이 우회되지
않도록, RiskCandidate를 필드 승계로 재구성하는 모든 지점이 rebuild_risk_candidate
helper를 거치는지 정적으로 강제한다.

원리:
- RiskCandidate만이 live provenance 필드(live_relationship_context_derived·
  relationship_target_id)를 갖는다 — 이 타입의 **필드 보존 재구성**(model_copy·
  model_construct·dataclasses.replace·copy.copy/deepcopy)에서 flag가 유실되면
  namespace fail-safe만 남아 방어선이 하나로 준다.
- 따라서 RiskCandidate를 다루는 소스 파일에서 위 재구성 동사가 나타나면
  **sanction**을 요구한다:
    · `rebuild_risk_candidate(` 호출        → 승인(helper 경유)
    · `RiskCandidate(` 생성자               → 승인(origin — flag 명시 설정)
    · `# provenance-audit: helper` 마커      → helper 본체의 유일한 원본 copy
    · `# provenance-audit: not-risk <이유>`  → RiskCandidate 아닌 타입 재구성
  그 외 raw 재구성은 감사 실패(신규 우회 site 유입 차단).

manifest는 스캔 대상 = **RiskCandidate를 import하는 non-test 소스 전부**(하드코딩
목록이 아니라 자동 발견 — 신규 파일도 자동 편입). 스크립트를 직접 실행하면 결과를
출력하고, 테스트가 audit_risk_candidate_rebuilds()를 호출해 clean을 강제한다.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# 필드 보존 재구성 메서드(원본 인스턴스 필드를 승계 — provenance 유실 위험).
_METHOD_VERBS = frozenset({"model_copy", "model_construct"})
# 마커: 재구성 라인 또는 바로 윗줄 주석에 있어야 승인.
_SANCTION_MARKERS = ("# provenance-audit: helper", "# provenance-audit: not-risk")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def scan_files() -> list[Path]:
    """RiskCandidate를 import·언급하는 non-test 소스 자동 발견(하드코딩 없음)."""
    root = _backend_root()
    out: list[Path] = []
    for base in ("packages", "apps"):
        for p in sorted((root / base).rglob("*.py")):
            if "test" in p.parts or "__pycache__" in p.parts:
                continue
            text = p.read_text(encoding="utf-8")
            if "RiskCandidate" in text:
                out.append(p)
    return out


@dataclass(frozen=True)
class Finding:
    """감사 위반 1건 — 미승인 재구성 site."""

    path: str
    line_no: int
    line: str


def _reconstruction_lines(tree: ast.AST) -> list[int]:
    """AST에서 필드 보존 재구성 호출의 라인 번호(문자열·주석·docstring 무시)."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        # x.model_copy(...) / x.model_construct(...)
        if attr in _METHOD_VERBS:
            lines.append(node.func.lineno)
            continue
        # dataclasses.replace(...) / copy.copy(...) / copy.deepcopy(...)
        val = node.func.value
        if isinstance(val, ast.Name):
            if val.id == "dataclasses" and attr == "replace":
                lines.append(node.func.lineno)
            elif val.id == "copy" and attr in ("copy", "deepcopy"):
                lines.append(node.func.lineno)
    return lines


def _sanctioned(src_lines: list[str], line_no: int) -> bool:
    """재구성 라인 또는 바로 윗줄에 승인 마커가 있는지."""
    line = src_lines[line_no - 1] if 0 < line_no <= len(src_lines) else ""
    prev = src_lines[line_no - 2] if line_no >= 2 else ""
    return any(m in line or m in prev for m in _SANCTION_MARKERS)


def audit_file(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    src_lines = text.splitlines()
    tree = ast.parse(text, filename=str(path))
    findings: list[Finding] = []
    for line_no in sorted(set(_reconstruction_lines(tree))):
        if _sanctioned(src_lines, line_no):
            continue
        rel = str(path.relative_to(_backend_root()))
        findings.append(Finding(
            path=rel, line_no=line_no,
            line=(src_lines[line_no - 1].strip() if line_no <= len(src_lines) else "")))
    return findings


def audit_risk_candidate_rebuilds() -> list[Finding]:
    """전체 감사 — 위반 목록 반환(빈 목록 = clean)."""
    findings: list[Finding] = []
    for p in scan_files():
        findings += audit_file(p)
    return findings


def main() -> int:
    findings = audit_risk_candidate_rebuilds()
    scanned = scan_files()
    print(f"scanned {len(scanned)} RiskCandidate-handling source files")
    if not findings:
        print("PROVENANCE AUDIT CLEAN — 모든 RiskCandidate 재구성이 helper 경유·승인됨")
        return 0
    print(f"PROVENANCE AUDIT FAILED — 미승인 재구성 {len(findings)}건:")
    for f in findings:
        print(f"  {f.path}:{f.line_no}: {f.line}")
    print("\n조치: rebuild_risk_candidate(...) 경유로 바꾸거나, RiskCandidate가 "
          "아니면 '# provenance-audit: not-risk <이유>' 마커를 다세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
