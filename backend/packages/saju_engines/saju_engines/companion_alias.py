"""등록 동반자 레지스트리 → 별칭 인덱스 (동반자 공동 풀이 P0).

사용자 발화 속 별명·관계어를 등록 동반자 subject_id로 해소하기 위한 인덱스를 만든다.
SSOT는 SubjectStore(subjects 테이블) — 하드코딩 관계어를 늘리지 않고 등록분에서만 생성한다.
한 별칭이 복수 대상에 매핑되면 자동 해소하지 않고(ambiguous) 확인 질문으로 넘긴다.

owner isolation은 호출 측(레지스트리 조회 시 owner 한정)이 보장한다 — records는 이미 owner 한정.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.subject import SubjectRecord

# 관계어 동의어 — relation_to_user 값을 사용자 표현으로 확장(배우자/부모/자녀/형제 중심).
RELATION_SYNONYMS: dict[str, list[str]] = {
    "spouse": ["배우자", "남편", "아내", "와이프", "신랑", "부인", "집사람"],
    "husband": ["남편", "신랑", "집사람"],
    "wife": ["아내", "와이프", "부인", "집사람"],
    "father": ["아빠", "아버지", "부친", "아버님"],
    "mother": ["엄마", "어머니", "모친", "어머님"],
    "parent": ["부모", "어버이"],
    "child": ["자녀", "아이", "아들", "딸"],
    "son": ["아들", "아드님"],
    "daughter": ["딸", "따님"],
    "sibling": ["형제", "자매", "오빠", "누나", "언니", "동생"],
    "brother": ["오빠", "남동생"],
    "sister": ["누나", "언니", "여동생"],
    "friend": ["친구"],
    "coworker": ["동료", "직장동료"],
    "business_partner": ["동업자", "파트너"],
}

# 명시적 대상 지칭 후보 토큰(등록 여부와 무관) — 미등록이면 임의 추정 대신 확인 질문에 쓴다.
REFERENCE_TOKENS: set[str] = {w for ws in RELATION_SYNONYMS.values() for w in ws} | {"신랑", "아가"}


@dataclass(frozen=True)
class AliasEntry:
    """별칭 하나가 가리키는 등록 동반자 + 매칭 출처(모호성 설명·P1 확장용)."""

    subject_id: str
    label: str
    relation_to_user: str | None
    source: str  # 'label' | 'alias' | 'relation_synonym' | 'legacy'


def normalize_token(token: str) -> str:
    """매칭용 정규화 — 공백 제거·소문자."""
    return token.replace(" ", "").strip().lower()


def merge_attached_partner(
    index: dict[str, list[AliasEntry]], partner_ref: dict | None,
) -> dict[str, list[AliasEntry]]:
    """FE 칩 첨부 동반자를 별칭 인덱스에 병합 — 명시 선택은 텍스트 해소보다 우선(원칙 7).

    첨부 라벨(정규화)을 첨부 대상 '단일 항목'으로 덮어쓴다: 사용자가 방금 UI에서 고른
    대상이 정답이므로, 동일 라벨의 다른 등록 대상과 모호(ambiguous) 처리하지 않는다.
    서버 미등록 첨부(inline)·게스트에서도 발화 속 첨부 라벨 지칭("남편 사주로 봐줘")이
    need_subject 확인 질문으로 빠지지 않게 한다. subject_id는 등록 첨부면 그 id,
    인라인 첨부면 'inline:partner'(다운스트림 birth 폴백 키와 일치).

    Args:
        index: 등록 레지스트리 기반 별칭 인덱스(원본은 변경하지 않음).
        partner_ref: 프론트 ChatPartner dict(mode/label/subjectId) 또는 None.

    Returns:
        병합된 새 인덱스(첨부 없음·라벨 1글자면 원본 그대로).
    """
    if not partner_ref or not partner_ref.get("label"):
        return index
    label = str(partner_ref["label"])
    key = normalize_token(label)
    if len(key) < 2:  # 1글자 라벨 과매칭 방지 — 자동 인덱스와 동일 기준
        return index
    sid = (
        str(partner_ref["subjectId"])
        if partner_ref.get("mode") == "registered" and partner_ref.get("subjectId")
        else "inline:partner"
    )
    out = dict(index)
    out[key] = [AliasEntry(sid, label, None, "attached")]
    return out


def build_companion_alias_index(
    records: list[SubjectRecord], base_subject_id: str | None = None
) -> dict[str, list[AliasEntry]]:
    """등록 대상 목록 → 정규화 별칭 → AliasEntry 목록.

    Args:
        records: owner 한정 등록 대상 목록(SubjectStore.list_all 결과).
        base_subject_id: 대화 기준(본인) 사주 — 인덱스에서 제외한다.

    Returns:
        정규화 별칭 → 그 별칭이 가리키는 동반자 목록(복수면 모호 — 자동 해소 금지).

    Note:
        - kind='self'와 base_subject_id는 제외.
        - 소스: label, aliases[], relation_to_user 동의어.
        - 1글자 별칭은 과매칭 위험이 커 자동 인덱스에서 제외한다.
    """
    index: dict[str, list[AliasEntry]] = {}

    def add(token: str, entry: AliasEntry) -> None:
        key = normalize_token(token)
        if len(key) < 2:  # 1글자 별칭 과매칭 방지(exact-only는 P1)
            return
        bucket = index.setdefault(key, [])
        if not any(e.subject_id == entry.subject_id and e.source == entry.source for e in bucket):
            bucket.append(entry)

    for r in records:
        if r.kind == "self" or (base_subject_id and r.subject_id == base_subject_id):
            continue
        rel = r.relation_to_user
        add(r.label, AliasEntry(r.subject_id, r.label, rel, "label"))
        for a in r.aliases:
            add(a, AliasEntry(r.subject_id, r.label, rel, "alias"))
        if rel:
            for syn in RELATION_SYNONYMS.get(rel, []):
                add(syn, AliasEntry(r.subject_id, r.label, rel, "relation_synonym"))
    return index
