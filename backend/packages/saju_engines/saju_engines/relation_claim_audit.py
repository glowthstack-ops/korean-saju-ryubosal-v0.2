"""관계 주장 감사 + 결정론적 교체 — P0 (2026-07-27 데굴님 확정).

엔진이 `化 불성·합거`로 판정한 관계를 LLM이 "합하여 木이 강해진다"로 뒤집어 서술한
사고(2026-07-27 일운 사례)를 차단한다. 감사는 **구조화 필드**(RelationSemantics)로
판정하고, 어휘 목록은 '주장이 있었는가'를 찾는 용도로만 쓴다.

정책(데굴님 확정):
  1. 위반 발견 → 교정 지시를 붙여 **1회만** 재생성.
  2. 재생성 후에도 위반이면 → **해당 문장만 엔진 문장으로 교체**(원문 유지 금지).
  3. 교체할 문장을 특정하지 못하면 → 호출부가 안전 응답으로 대체.
감사 자체는 사실 오류 안전장치이므로 비용 회로 차단은 '재생성'만 끄고 감사·교체는
항상 살려 둔다(플래그 분리).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    BRANCH_KO,
    ELEMENT_KO,
    STEM_ELEMENT,
    STEM_KO,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.relation_semantics import (
    BindingState,
    EffectFavorability,
    EffectKind,
    FormationState,
    RelationEffect,
    RelationSemantics,
    TransformationState,
)

# 한자 1자 → 한글 별칭. 한글 음 1음절만으로 찾으면 '기운을'의 '을'이 乙에, '환경의'의
# '경'이 庚에 걸려 무관한 문장을 위반으로 오판한다(실측). 따라서 한자 자체이거나
# '해수(亥水)'·'인목(寅木)'처럼 **음+오행** 2음절 형태일 때만 언급으로 인정한다.
_CHAR_ALIASES: dict[str, tuple[str, ...]] = {
    **{
        s.value: (s.value, f"{STEM_KO[s]}{ELEMENT_KO[Element(STEM_ELEMENT[s])]}")
        for s in Stem
    },
    **{
        b.value: (b.value, f"{BRANCH_KO[b]}{ELEMENT_KO[Element(BRANCH_ELEMENT[b])]}")
        for b in Branch
    },
}
_ELEMENT_KO_BY_HANJA: dict[str, str] = {e.value: ELEMENT_KO[e] for e in Element}
# 부정 표현 창 — '합화한 것이 아니라'처럼 주장을 부정하는 문맥은 위반이 아니다.
# (엔진 교체 문장이 스스로 감사에 걸리는 자기 재발동도 이 가드로 막는다.)
_NEGATION = re.compile(r"않|아니|없|못")
_NEGATION_WINDOW = 12

# 문장 분리 — 한국어 종결('~요.', '~다.') + 줄바꿈. 오프셋 보존을 위해 finditer를 쓴다.
_SENTENCE_END = re.compile(r"[.!?]+[\s\n]+|\n+")
# 관계 언급 여부 판정용 키워드(합/충/형/파/해/원진) — 호칭 없는 문장의 창(±2문장) 귀속 입구.
# 한글 1음절('합'·'충'·'형'·'파'·'해')을 그대로 쓰면 '집중합니다'·'종합해보면'·'뚜렷해지고'·
# '충분히'·'유형이'처럼 일상 어절에 걸려, 관계를 말하지 않은 문장이 공유 글자(未·己)만으로
# 午未合에 귀속돼 STRENGTHEN_ASSERTED_WHEN_SUPPRESSED 로 교체됐다(2026-10-12 실답). 한자는
# 그대로 인정하고, 한글은 관계 어휘로만 읽히는 활용·복합형에 한정한다(2026-10-12 데굴님 승인).
# '해' 단독은 인정하지 않는다(害·'해살'·'육해'로만) — 명식 서술에서 '해'는 거의 연(年)·행위다.
_RELATION_WORD = re.compile(
    r"合|沖|刑|破|害|원진|"
    r"(?<![종결조통적부복취집배혼화연])합(?:화|거|반|국|을|이|으로|하여|해서|하는|하면|한다|해|과|도)|"
    r"반합|방합|삼합|육합|암합|쟁합|"
    r"(?<![보])충(?:이|을|으로|하|해|돼|되|살|과|도|돌)|상충|"
    r"(?<![유모조변])형(?:살|이 |을|으로|하|과|도)|삼형|자형|형충|형파|"
    r"(?<![돌출전])파(?:살|가 |를|로|과)|파해|"
    r"해살|육해"
)
# 합화(化) 주장.
_TRANSFORM_CLAIM = re.compile(r"합화|化하|化 성립|으로 변하|로 바뀌|로 화하|化한다")
# 강화 주장 — 우회 표현까지 포함(단순 '강화·증폭'만 보면 뚫린다).
_STRENGTHEN_CLAIM = re.compile(
    r"강해|강화|강하게|증폭|커진|커지|불어나|살아난|살아나|보태|보탠|"
    r"더한다|더해|확대|세진|세져|힘을 얻|기운을 얻|짙어|짙게|북돋"
)
# 불리 방향 주장 / 유리 방향 주장.
_ADVERSE_CLAIM = re.compile(r"불리|악화|부담|소모|해롭|나빠|손실|위축|무거워")
_BENEFICIAL_CLAIM = re.compile(r"완화|유리|도움|해소|가벼워|풀린|덜어")
# 묶임 주장 / 제거(합거) 주장 — 묶임과 제거는 다른 판정이라 따로 본다.
_BINDING_CLAIM = re.compile(r"합거|묶이|묶여|묶인|묶고|붙잡")
_REMOVAL_CLAIM = re.compile(r"합거|제거되|없어지|사라지|소멸")


class RelationViolationKind(StrEnum):
    """관계 주장 위반 유형 — 각각 불변식 1개에 대응한다."""

    TRANSFORMATION_ASSERTED_WHEN_NOT = "TRANSFORMATION_ASSERTED_WHEN_NOT"
    WRONG_TRANSFORMED_ELEMENT = "WRONG_TRANSFORMED_ELEMENT"
    STRENGTHEN_ASSERTED_WHEN_SUPPRESSED = "STRENGTHEN_ASSERTED_WHEN_SUPPRESSED"
    BENEFICIAL_ASSERTED_AS_ADVERSE = "BENEFICIAL_ASSERTED_AS_ADVERSE"
    # 묶임·제거는 化와 별개 축이라 따로 감사한다. 합화 방향이 맞아도 '묶임'과 '제거'
    # 사이에서 사실이 다시 왜곡될 수 있다(2026-07-27 데굴님 지적).
    BINDING_ASSERTED_WHEN_NONE = "BINDING_ASSERTED_WHEN_NONE"
    REMOVAL_ASSERTED_WHEN_BOUND = "REMOVAL_ASSERTED_WHEN_BOUND"


class RelationClaimViolation(BaseModel):
    """감사 위반 1건 — 어느 문장이 어느 불변식을 깼는가."""

    relation_label: str
    kind: RelationViolationKind
    sentence_index: int
    sentence: str
    detail: str = ""


class _Sentence(BaseModel):
    """오프셋을 보존한 문장 1개(교체를 위해 원문 위치가 필요하다)."""

    index: int
    start: int
    end: int
    text: str


def split_sentences(text: str) -> list[_Sentence]:
    """한국어 답변을 문장 단위로 자른다(오프셋 보존).

    Args:
        text: 답변 원문.

    Returns:
        인덱스·시작·끝 오프셋·본문을 가진 문장 목록(공백만인 조각은 제외).
    """
    out: list[_Sentence] = []
    pos = 0
    idx = 0
    for m in _SENTENCE_END.finditer(text):
        end = m.start() + len(m.group().rstrip())
        chunk = text[pos:end]
        if chunk.strip():
            out.append(_Sentence(index=idx, start=pos, end=end, text=chunk))
            idx += 1
        pos = m.end()
    if text[pos:].strip():
        out.append(_Sentence(index=idx, start=pos, end=len(text), text=text[pos:]))
    return out


def sentence_asserts(pattern: re.Pattern[str], sentence: str) -> bool:
    """문장에 그 주장이 있는가 — 직후 부정 표현이 붙으면 주장으로 보지 않는다.

    '수입 증가로 단정할 수 **없다**' 처럼 부정하는 문장을 위반으로 잡지 않기 위한
    검증된 기계다. 다른 감사기가 같은 판정을 복제하지 않도록 공개한다
    (2026-07-30 — 섹션 claim 감사가 재사용).
    """
    for m in pattern.finditer(sentence):
        tail = sentence[m.end() : m.end() + _NEGATION_WINDOW]
        if not _NEGATION.search(tail):
            return True
    return False


#: 하위호환 별칭 — 모듈 내부 호출부가 그대로 쓰던 이름.
_claimed = sentence_asserts


def _mentions_char(window: str, char: str) -> bool:
    """창(window) 안에 그 글자가 한자 또는 '음+오행' 형태로 등장하는가."""
    return any(alias in window for alias in _CHAR_ALIASES.get(char, (char,)))


def _mentions_element(sentence: str, element: str) -> bool:
    """문장이 그 오행을 언급하는가 — 한자, 또는 '목(' · '목 기운' 형태의 한글."""
    if element in sentence:
        return True
    ko = _ELEMENT_KO_BY_HANJA.get(element)
    return bool(ko and re.search(rf"{ko}\s*(?:\(|기운|기)", sentence))


# 라벨 접미(한자/한글 혼용) → 한글 통칭 접미. relation_label은 '辰酉合'·'巳酉반합'·
# '申酉방합'·'寅午戌삼합' 형태라 구성 글자 뒤의 접미를 그대로 떼어 쓴다.
_LABEL_SUFFIX_KO: dict[str, str] = {"合": "합", "반합": "반합", "방합": "방합", "삼합": "삼합"}


def _relation_name_aliases(sem: RelationSemantics) -> tuple[str, ...]:
    """관계를 **직접 부르는** 표기 전부 — 한자 라벨과 한글 통칭.

    한자 라벨('辰酉合'·'巳酉반합')은 엔진 canonical claim 과 LLM 입력이 쓰는 표기라
    답변에 그대로 등장한다. 한글은 '진유합'·'유진합'(2자 관계는 양순) 과 라벨 접미를 살린
    '사유반합'·'신유방합' 형태를 인정한다.
    """
    names: list[str] = [sem.relation_label]
    ko = [
        STEM_KO.get(Stem(c)) if c in {s.value for s in Stem} else BRANCH_KO.get(Branch(c))
        for c in sem.members
    ]
    if any(k is None for k in ko):
        return tuple(names)
    joined = "".join(k for k in ko if k)
    suffix = sem.relation_label[len("".join(sem.members)):]
    suffix_ko = _LABEL_SUFFIX_KO.get(suffix, "합")
    hanja = "".join(sem.members)
    if len(sem.members) == 2:
        a, b = (k for k in ko if k)
        names += [f"{a}{b}합", f"{b}{a}합", f"{a}{b}{suffix_ko}", f"{b}{a}{suffix_ko}"]
        # 한자 글자 + 한글 접미('午未합'·'未午합') — 병기 정규화 뒤 남는 형태(2026-10-12).
        names += [f"{hanja}{suffix_ko}", f"{hanja[::-1]}{suffix_ko}", f"{hanja[::-1]}{suffix}"]
    else:
        names += [f"{joined}합", f"{joined}{suffix_ko}", f"{hanja}합", f"{hanja}{suffix_ko}"]
    return tuple(dict.fromkeys(names))


# 한글 병기 괄호 — '午未(오미) 합'·'巳午未(사오미) 방합'처럼 한자 뒤에 음을 괄호로 달면
# 직접 호칭이 끊긴다. 관계 호칭 판정에서만 괄호 병기와 접미 앞 공백을 걷어낸다.
_KO_ANNOTATION = re.compile(r"\(\s*[가-힣·\s]+\s*\)")
# 한자 병기 괄호 — '사신(巳申)합'처럼 한글 음 뒤에 한자를 괄호로 달아도 직접 호칭이 끊긴다
# (2026-10-13 실답: 巳申合 서술이 창 경로로 巳午방합·申戌방합에 귀속돼 안전 템플릿 교체).
_HANJA_ANNOTATION = re.compile(r"\(\s*[\u4e00-\u9fff·\s]+\s*\)")
_SUFFIX_GAP = re.compile(r"\s+(合|합|반합|방합|삼합)")


def _normalize_for_naming(text: str) -> str:
    """호칭 판정용 정규화 — 괄호 한글 병기 제거 + 관계 접미 앞 공백 제거.

    '午未(오미) 합으로 인해 … 묶이는'은 午未合을 직접 부른 문장인데 원문 그대로는
    '午未合'·'오미합' 어느 별칭에도 맞지 않아 공유 글자(未)로 巳午未방합에 귀속되어
    BINDING_ASSERTED_WHEN_NONE 으로 오판·교체됐다(2026-10-12 실답 3회 중 2회).
    글자 언급(_mentions_char)은 '해수(亥水)' 형태를 쓰므로 이 정규화를 거치지 않는다.

    Args:
        text: 문장 원문.

    Returns:
        호칭 매칭에만 쓰는 정규화 문자열.
    """
    out = _HANJA_ANNOTATION.sub("", _KO_ANNOTATION.sub("", text))
    return _SUFFIX_GAP.sub(r"\1", out)


def _named_relations(text: str, semantics: list[RelationSemantics]) -> set[str]:
    """문장이 이름으로 직접 부르는 관계 라벨 집합(없으면 빈 집합)."""
    norm = _normalize_for_naming(text)
    return {
        sem.relation_label
        for sem in semantics
        if any(alias in text or alias in norm for alias in _relation_name_aliases(sem))
    }


def _referenced(
    sentences: list[_Sentence],
    i: int,
    sem: RelationSemantics,
    named: set[str] | None = None,
) -> bool:
    """문장 i가 그 관계를 가리키는가.

    두 경로를 인정한다.
      ① 문장이 관계를 직접 부른다('辰酉合은 …'·'인해합이 …').
      ② 문장에 관계 어휘와 구성 글자가 **최소 1개** 있고, 나머지 구성 글자가 ±2 문장
         창 안에 있다. 실제 서술은 '인목(寅木)이 들어와 …'로 운 글자를 먼저 소개한 뒤
         두세 문장 뒤에서 '일지의 해수(亥水)와는 합을 하여 …'로 이어지기 때문이다.
    구성 글자 매칭은 한자 또는 '음+오행' 2음절만 인정한다(1음절 오탐 차단).

    **직접 호칭 배타 규칙(2026-10-02)**: 문장이 어떤 관계든 이름으로 부르면(`named`),
    그 문장은 호칭된 관계에만 귀속하고 경로 ②는 쓰지 않는다. 한 글자가 여러 관계에
    참여하는 날(일진 己酉 → 辰酉合·巳酉반합·申酉방합)에 "辰酉合은 … 합거입니다"라는
    엔진 canonical 문장이 창 안의 巳·申 때문에 반합·방합에도 귀속되어 위반으로 잡혔고,
    지시를 그대로 따른 답변이 안전 템플릿으로 통째 교체됐다(실답 2026-10-02 사고).

    Args:
        sentences: 분리된 문장 목록.
        i: 판정할 문장 인덱스.
        sem: 귀속 여부를 볼 관계.
        named: 문장 i 가 직접 부르는 관계 라벨 집합(None 이면 이 관계만 검사).
    """
    text = sentences[i].text
    if named is None:
        named = {sem.relation_label} if any(
            alias in text for alias in _relation_name_aliases(sem)
        ) else set()
    if named:
        return sem.relation_label in named
    if not _RELATION_WORD.search(text):
        return False
    if not any(_mentions_char(text, c) for c in sem.members):
        return False
    lo = max(0, i - 2)
    hi = min(len(sentences), i + 3)
    window = " ".join(s.text for s in sentences[lo:hi])
    return all(_mentions_char(window, c) for c in sem.members)


def audit_relation_claims(
    answer: str, semantics: list[RelationSemantics]
) -> list[RelationClaimViolation]:
    """답변이 엔진 관계 판정을 역전시켰는지 감사한다.

    Args:
        answer: LLM 답변 원문.
        semantics: 이번 턴 입력에 실린 관계 구조화 의미.

    Returns:
        위반 목록(없으면 빈 리스트).
    """
    sentences = split_sentences(answer)
    # 문장별 직접 호칭 관계 — 호칭이 있는 문장은 그 관계에만 귀속한다(공유 글자 오탐 차단).
    named = [_named_relations(s.text, semantics) for s in sentences]
    # 문장별 묶임 어휘의 정당한 지시 대상 유무 — 있으면 binding=NONE 관계에 ③을 걸지 않는다.
    binding_ok = [
        _has_binding_referent(s.text, named[i], semantics) for i, s in enumerate(sentences)
    ]
    out: list[RelationClaimViolation] = []
    for sem in semantics:
        if sem.formation_state is FormationState.NOT_FORMED and not sem.transform_element:
            continue
        for i, s in enumerate(sentences):
            if not _referenced(sentences, i, sem, named[i]):
                continue
            out += _audit_sentence(sem, s, binding_referent=binding_ok[i])
    return out


#: 억제 대상 글자와 십성명의 인접 허용 폭('丙 정인'·'정인 丙(병화)').
_EFFECT_TARGET_WINDOW = 8


def _mentions_effect_target(text: str, eff: RelationEffect) -> bool:
    """문장이 관계의 억제 대상 글자를 **십성명과 붙여** 부르는가('丙 정인'·'병화 정인').

    글자 단독 언급은 인정하지 않는다 — 세운 丙午처럼 간지 표기 속 丙이 걸리면 묶임 어휘의
    지시 대상이 있다고 오판해 진짜 역전('午戌반합으로 묶여')을 놓친다.
    """
    if not eff.ten_god:
        return False
    for alias in _CHAR_ALIASES.get(eff.target, (eff.target,)):
        for m in re.finditer(re.escape(alias), text):
            lo = max(0, m.start() - _EFFECT_TARGET_WINDOW)
            around = text[lo : m.end() + _EFFECT_TARGET_WINDOW]
            if eff.ten_god in around:
                return True
    return False


def _has_binding_referent(
    text: str, named: set[str], semantics: list[RelationSemantics]
) -> bool:
    """문장 안에 묶임·합거 어휘의 정당한 지시 대상이 있는가.

    한 문장이 묶임 판정이 **있는** 관계(합반·합거)의 결과를 결과어로 받으면서 묶임 판정이
    **없는** 반합·방합을 함께 부르는 서술은 정상이다 — 프롬프트가 '두 번째부터는 원어 대신
    결과어', '영역당 1~2문장'을 요구하니 "丙 정인이 묶여 있어 … 巳午방합·申戌방합이 보조하는
    …"처럼 한 문장에 합쳐 쓰게 된다. 직접 호칭 배타 규칙만 있으면 이 '묶여'가 호칭된
    방합들에 귀속돼 BINDING_ASSERTED_WHEN_NONE ×2 → 모호 → 답 전체가 안전 템플릿으로
    교체됐다(2026-10-13 실답·재현 3형). 다음 셋 중 하나면 지시 대상이 있다고 본다.
      ① binding≠NONE 관계를 이름으로 부른다(정규화 호칭 포함).
      ② 그 관계의 구성 글자가 **같은 문장 안에** 모두 있다(±2문장 창은 쓰지 않으며,
         호칭된 다른 관계의 라벨 글자는 세지 않는다).
      ③ 그 관계가 억제한 대상 글자가 십성명과 붙어 있다('丙 정인').
    한계: 같은 문장에서 묶임 있는 합과 함께 "午戌반합도 묶인다"처럼 둘 다 묶였다고 쓰면
    후자를 놓친다 — 확정 문장이 입력에 실리는 구조상 드문 형태로 보고 수용한다.

    Args:
        text: 문장 원문.
        named: 문장이 직접 부르는 관계 라벨 집합.
        semantics: 이번 턴 관계 구조화 의미 전체.
    """
    # ② 판정용 본문 — 호칭된 관계 라벨 자체는 걷어낸다. "巳午방합과 申戌방합이 서로 묶여"의
    # 巳·申은 방합 이름의 일부이지 巳申合 서술이 아니다(걷어내지 않으면 이 진짜 역전을 놓친다).
    bare = _normalize_for_naming(text)
    for sem in semantics:
        if sem.relation_label in named:
            for alias in _relation_name_aliases(sem):
                bare = bare.replace(alias, " ")
    for sem in semantics:
        if sem.binding_state is BindingState.NONE:
            continue
        if sem.relation_label in named:
            return True
        if all(_mentions_char(bare, c) for c in sem.members):
            return True
        if any(
            _mentions_effect_target(text, eff)
            for eff in sem.effects
            if eff.effect is EffectKind.SUPPRESSED
        ):
            return True
    return False


def _audit_sentence(
    sem: RelationSemantics, s: _Sentence, *, binding_referent: bool = False
) -> list[RelationClaimViolation]:
    """문장 1개 × 관계 1건 — 불변식 4종을 확인한다.

    Args:
        sem: 판정할 관계.
        s: 문장.
        binding_referent: 문장 안에 묶임 어휘의 정당한 지시 대상(묶임 판정이 있는 다른
            관계)이 있는가. True면 ③ BINDING_ASSERTED_WHEN_NONE 을 걸지 않는다.
    """
    out: list[RelationClaimViolation] = []
    el = sem.transform_element or ""
    transform_claimed = _claimed(_TRANSFORM_CLAIM, s.text)
    strengthen_claimed = _claimed(_STRENGTHEN_CLAIM, s.text)

    # ① 化 불성인데 합화했다고 서술. 방합(NOT_APPLICABLE)은 '강화'는 허용, '합화'만 금지.
    if sem.transformation_state is not TransformationState.TRANSFORMED:
        asserted = transform_claimed or (
            strengthen_claimed
            and el
            and _mentions_element(s.text, el)
            and sem.transformation_state is TransformationState.NO_TRANSFORMATION
        )
        if asserted:
            out.append(RelationClaimViolation(
                relation_label=sem.relation_label,
                kind=RelationViolationKind.TRANSFORMATION_ASSERTED_WHEN_NOT,
                sentence_index=s.index, sentence=s.text,
                detail=f"엔진 판정 {sem.transformation_state.value}"
                       + (f" · 후보 오행 {el}" if el else ""),
            ))

    # ② 化 확정인데 다른 오행으로 합화했다고 서술.
    if sem.transformation_state is TransformationState.TRANSFORMED and el:
        others = [
            e for e in _ELEMENT_KO_BY_HANJA
            if e != el and _mentions_element(s.text, e)
        ]
        if (transform_claimed or strengthen_claimed) and others and not _mentions_element(
            s.text, el
        ):
            out.append(RelationClaimViolation(
                relation_label=sem.relation_label,
                kind=RelationViolationKind.WRONG_TRANSFORMED_ELEMENT,
                sentence_index=s.index, sentence=s.text,
                detail=f"엔진 化神 {el} · 답변 언급 {''.join(others)}",
            ))

    # ③ 묶임 판정이 없는데 묶였다·합거됐다고 서술(반합을 합반으로 옮기는 오류의 대칭).
    if (
        sem.binding_state is BindingState.NONE
        and _claimed(_BINDING_CLAIM, s.text)
        and not binding_referent
    ):
        out.append(RelationClaimViolation(
            relation_label=sem.relation_label,
            kind=RelationViolationKind.BINDING_ASSERTED_WHEN_NONE,
            sentence_index=s.index, sentence=s.text,
            detail="엔진 판정 binding=NONE(묶임·합거 없음)",
        ))
    # ④ 묶임까지만 판정됐는데 제거·합거로 단정.
    if sem.binding_state is BindingState.BOUND and _claimed(_REMOVAL_CLAIM, s.text):
        out.append(RelationClaimViolation(
            relation_label=sem.relation_label,
            kind=RelationViolationKind.REMOVAL_ASSERTED_WHEN_BOUND,
            sentence_index=s.index, sentence=s.text,
            detail="엔진 판정 binding=BOUND(합거 아님)",
        ))

    # ⑤ 억제된 대상을 강화됐다고 서술.
    for eff in sem.effects:
        if eff.effect is not EffectKind.SUPPRESSED:
            continue
        if strengthen_claimed and _mentions_char(s.text, eff.target):
            out.append(RelationClaimViolation(
                relation_label=sem.relation_label,
                kind=RelationViolationKind.STRENGTHEN_ASSERTED_WHEN_SUPPRESSED,
                sentence_index=s.index, sentence=s.text,
                detail=f"{eff.target} 엔진 판정 SUPPRESSED",
            ))
        # ⑥ 유리한 억제(흉 제거)를 불리 요인으로 단정.
        if (
            eff.favorability is EffectFavorability.BENEFICIAL
            and _mentions_char(s.text, eff.target)
            and _ADVERSE_CLAIM.search(s.text)
            and not _BENEFICIAL_CLAIM.search(s.text)
        ):
            out.append(RelationClaimViolation(
                relation_label=sem.relation_label,
                kind=RelationViolationKind.BENEFICIAL_ASSERTED_AS_ADVERSE,
                sentence_index=s.index, sentence=s.text,
                detail=f"{eff.target} 억제는 엔진 판정 BENEFICIAL",
            ))
    return out


class RelationPatch(BaseModel):
    """교체 1건의 기록 — 어느 관계의 어느 문장을 무엇으로 바꿨는가."""

    relation_label: str
    sentence_index: int
    original: str
    replacement: str
    applied: bool


class PatchOutcome(StrEnum):
    """패치 결과 분류 — 계측에서 모호성과 불가능을 구분해야 마커 도입 필요성을 판단한다."""

    PATCHED_UNIQUE_RELATION = "PATCHED_UNIQUE_RELATION"
    # 한 문장이 여러 관계를 위반 → 그 문장을 위반 관계 전부의 canonical 문장으로 교체(2026-10-13).
    PATCHED_MULTI_RELATION = "PATCHED_MULTI_RELATION"
    AMBIGUOUS_RELATION_FALLBACK = "AMBIGUOUS_RELATION_FALLBACK"
    UNPATCHABLE_RELATION_FALLBACK = "UNPATCHABLE_RELATION_FALLBACK"


class PatchedAnswer(BaseModel):
    """패치 결과 — 계측(패치율·모호성률·미교정 오류율)에 그대로 쓰인다."""

    text: str
    patches: list[RelationPatch] = []
    unpatched: list[RelationClaimViolation] = []
    ambiguous_sentences: list[int] = []
    multi_patched_sentences: list[int] = []  # 여러 관계 canonical 문장으로 교체된 문장

    @property
    def patched_count(self) -> int:
        """실제 교체된 문장 수."""
        return sum(1 for p in self.patches if p.applied)

    @property
    def fully_repaired(self) -> bool:
        """미교정 위반이 남지 않았는가."""
        return not self.unpatched

    @property
    def outcome(self) -> PatchOutcome:
        """이번 패치의 대표 결과 — 로그 집계 키."""
        if self.fully_repaired:
            if self.multi_patched_sentences:
                return PatchOutcome.PATCHED_MULTI_RELATION
            return PatchOutcome.PATCHED_UNIQUE_RELATION
        if self.ambiguous_sentences:
            return PatchOutcome.AMBIGUOUS_RELATION_FALLBACK
        return PatchOutcome.UNPATCHABLE_RELATION_FALLBACK


def patch_relation_claims(
    answer: str,
    violations: list[RelationClaimViolation],
    semantics: list[RelationSemantics],
) -> PatchedAnswer:
    """위반 문장을 canonical claim으로 교체한다(추가 LLM 호출 없음).

    LLM 재생성은 쓰지 않는다 — 이 문제는 창작이 아니라 엔진 확정값 반영으로 풀리며,
    유료 Q&A에서 재호출을 기본값으로 두면 사용자 비용과 원가가 함께 늘어난다
    (2026-07-27 데굴님 확정).

    Args:
        answer: 답변 원문.
        violations: 감사 위반 목록.
        semantics: 관계 구조화 의미(라벨 → canonical claim).

    Returns:
        교체 결과와 미교정 위반을 담은 PatchedAnswer.
    """
    if not violations:
        return PatchedAnswer(text=answer)
    by_label = {s.relation_label: s for s in semantics}
    sentences = split_sentences(answer)
    # 문장 인덱스 → 그 문장에서 위반한 관계들. 한 글자가 여러 관계에 참여하므로
    # (예: 寅은 寅午반합·亥寅合·寅申충·寅巳해에 모두 참여) 한 문장이 둘 이상에 걸린다.
    # 어느 하나를 **임의로 고르지 않고**, 위반한 관계 전부의 canonical 문장(semantics 순)으로
    # 그 문장을 교체한다 — 결정론·재호출 없음. 예전처럼 문장 하나 때문에 답 전체를 안전
    # 템플릿으로 바꾸던 경로(2026-10-02·10-13 실답)는 canonical 문장이 없는 관계가 섞인
    # 경우에만 남는다(2026-10-13 데굴님 승인).
    by_sentence: dict[int, set[str]] = {}
    for v in violations:
        by_sentence.setdefault(v.sentence_index, set()).add(v.relation_label)

    out = answer
    patches: list[RelationPatch] = []
    patched_idx: set[int] = set()
    ambiguous: list[int] = []
    multi_patched: list[int] = []
    for idx in sorted(by_sentence, reverse=True):  # 뒤에서부터 잘라야 오프셋이 안 밀린다
        labels = by_sentence[idx]
        if idx >= len(sentences):
            continue
        sems = [
            by_label[s.relation_label] for s in semantics
            if s.relation_label in labels and s.canonical_claim
        ]
        if len(sems) != len(labels):
            # canonical 문장이 없는 관계가 섞여 있으면 교체본을 확정할 수 없다.
            if len(labels) > 1:
                ambiguous.append(idx)
            continue
        s = sentences[idx]
        replacement = " ".join(sem.canonical_claim for sem in sems)
        out = out[: s.start] + replacement + out[s.end :]
        for sem in sems:
            patches.append(RelationPatch(
                relation_label=sem.relation_label, sentence_index=idx,
                original=s.text, replacement=sem.canonical_claim, applied=True,
            ))
        patched_idx.add(idx)
        if len(sems) > 1:
            multi_patched.append(idx)

    unpatched = [v for v in violations if v.sentence_index not in patched_idx]
    return PatchedAnswer(
        text=out, patches=patches, unpatched=unpatched,
        ambiguous_sentences=sorted(ambiguous),
        multi_patched_sentences=sorted(multi_patched),
    )


def dedupe_canonical_claims(answer: str, semantics: list[RelationSemantics]) -> str:
    """같은 canonical claim이 두 번 이상 그대로 실렸으면 첫 출현만 남긴다(결정론·재호출 없음).

    프롬프트가 확정 문장을 '그대로 쓰거나 생략'하라고 지시하므로 LLM이 같은 문장을 영역별
    문단마다 복사하는 일이 생긴다(2026-10-12 실답: 午未合 문장이 2·3문단에 동일 반복).
    패치 경로에서도 위반 문장 둘이 같은 canonical claim으로 교체되면 같은 중복이 생긴다.
    두 경로 모두 이 함수로 정리한다. 확정 문장은 전문(全文) 일치만 중복으로 본다 — 결과어로
    바꿔 받은 문장은 건드리지 않는다.

    Args:
        answer: 답변 원문(감사·패치 이후 텍스트).
        semantics: 관계 구조화 의미(canonical claim 보유).

    Returns:
        각 canonical claim이 최대 한 번만 남은 답변. 중복이 없으면 원문 그대로.
    """
    out = answer
    for sem in semantics:
        claim = sem.canonical_claim
        if not claim:
            continue
        first = out.find(claim)
        if first < 0:
            continue
        cut = first + len(claim)
        head, tail = out[:cut], out[cut:]
        # 뒤따르는 공백 하나까지 함께 지워 '문장. 문장.' 간격을 유지한다.
        tail = re.sub(re.escape(claim) + r" ?", "", tail)
        out = head + tail
    if out != answer:
        out = re.sub(r" +\n", "\n", out)
    return out


def canonical_claim_lines(semantics: list[RelationSemantics]) -> list[str]:
    """생성 **전** LLM 입력용 — 관계별 확정 문장과 금지 주장.

    관계 사실을 자유 작문 영역에서 빼는 것이 최초 오류율을 낮추는 가장 큰 지렛대다.
    """
    if not semantics:
        return []
    lines = [
        "[관계 확정 문장 — 아래 문장의 의미를 바꾸지 말 것. 그대로 쓰거나 생략만 "
        "허용하며, 다른 뜻으로 바꿔 쓰면 안 된다(엔진 확정값). 각 문장은 답 전체에서 "
        "한 번만 인용하고, 같은 관계를 다른 영역에서 다시 다룰 때는 원문 반복 없이 "
        "결과어로만 받는다]"
    ]
    for sem in semantics:
        if not sem.canonical_claim:
            continue
        line = f"- {sem.canonical_claim}"
        if sem.forbidden_interpretations:
            line += " (금지: " + " / ".join(sem.forbidden_interpretations) + ")"
        lines.append(line)
    return lines if len(lines) > 1 else []
