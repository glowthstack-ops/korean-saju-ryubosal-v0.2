"""관계질 라벨 사전(P4) 단위 테스트 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §2. P4는 해석 문구 표준화 레이어 — 점수·confidence·후보를
변경하지 않고(inert), 합충형파해원진공망을 좋다/나쁘다로 단정하지 않으며 중립 표현만 제공한다.
"""

from __future__ import annotations

from saju_engines.compatibility_engine import compatibility_lines
from saju_engines.relationship_relation_labels import (
    RELATIONSHIP_RELATION_LABELS,
    get_relationship_relation_label,
    relation_summary_ko,
)
from saju_shared_types.compatibility import (
    CompatDirection,
    CompatibilityReport,
    CompatSignal,
    CompatSignalKind,
)

_ALL_KEYS = ["hap", "chung", "hyeong", "pa", "hae", "wonjin", "gongmang"]


# 1. 모든 relation_type이 라벨을 반환한다(키·한글명 양쪽).
def test_all_relation_types_return_label() -> None:
    for key in _ALL_KEYS:
        label = get_relationship_relation_label(key)
        assert label is not None and label["summary"]
    # 한글명·엔진 산출명도 매핑(육합→합, 귀문→원진).
    for ko in ["합", "육합", "충", "형", "파", "해", "원진", "귀문", "공망"]:
        assert get_relationship_relation_label(ko) is not None


# 2. 없는 relation_type은 None.
def test_unknown_relation_returns_none() -> None:
    assert get_relationship_relation_label("nope") is None
    assert get_relationship_relation_label("") is None
    assert relation_summary_ko("nope") == ""


# 3. 원진 라벨에 금지어가 포함되지 않는다(요약·주의·safe에는 없고, avoid에만 명시).
def test_wonjin_no_banned_words_in_visible_text() -> None:
    w = RELATIONSHIP_RELATION_LABELS["wonjin"]
    banned = ["악연", "속궁합", "절대 못 헤어짐", "징글징글"]
    visible = w["summary"] + " " + w["caution"] + " " + " ".join(w["safe_phrases"])
    for b in banned:
        assert b not in visible
        assert b in w["avoid_phrases"]  # 금지어 목록엔 명시돼 있어야 한다


# 4. 합이 '무조건 좋음'으로 표현되지 않는다.
def test_hap_not_unconditionally_good() -> None:
    h = RELATIONSHIP_RELATION_LABELS["hap"]
    assert "무조건 좋음" not in h["summary"] and "무조건 좋음" in h["avoid_phrases"]
    assert "천생연분 확정" not in h["summary"]


# 5. 충이 '무조건 이별'로 표현되지 않는다.
def test_chung_not_unconditional_breakup() -> None:
    c = RELATIONSHIP_RELATION_LABELS["chung"]
    assert "무조건 이별" not in c["summary"] and "무조건 이별" in c["avoid_phrases"]
    assert "파국" not in c["summary"]


def _report_with_clash() -> CompatibilityReport:
    return CompatibilityReport(
        self_label="본인", partner_label="상대", self_day="己亥", partner_day="乙巳",
        signals=[
            CompatSignal(
                kind=CompatSignalKind.DAY_BRANCH_CLASH, label="일지 충",
                detail="본인 일지 亥 ↔ 상대 일지 巳 충(沖)", direction=CompatDirection.FRICTION,
            ),
            CompatSignal(
                kind=CompatSignalKind.SINSAL_FRICTION, label="원진·귀문",
                detail="일지 亥·巳 원진 — 가까울수록 예민", direction=CompatDirection.FRICTION,
                auxiliary=True,
            ),
        ],
        harmony_count=0, friction_count=1, summary="마찰 요소가 더 두드러지는 조합",
        attraction_score=2, attraction_band="중",
    )


# 6. P4는 inert — compatibility_lines가 리포트 점수/카운트를 변경하지 않고, 설명 태그만 붙는다.
def test_compatibility_lines_is_inert_and_annotates() -> None:
    report = _report_with_clash()
    before = (report.harmony_count, report.friction_count, report.attraction_score,
              len(report.signals))
    lines = compatibility_lines(report)
    after = (report.harmony_count, report.friction_count, report.attraction_score,
             len(report.signals))
    assert before == after  # 점수·후보 불변(explanation-only)
    text = "\n".join(lines)
    # 충·원진의 중립 요약이 설명 태그로 붙는다.
    assert relation_summary_ko("chung") in text
    assert relation_summary_ko("wonjin") in text
    # 금지어는 출력에 등장하지 않는다.
    for b in ["악연", "속궁합", "파국", "무조건 이별"]:
        assert b not in text
