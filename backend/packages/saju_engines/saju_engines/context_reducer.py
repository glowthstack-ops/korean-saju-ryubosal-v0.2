"""Context Reduction Engine + LLM 입력 직렬화기 (v2.2 Phase 3 T3.4·T3.5).

LLM 입력 직전 최종 필터(docs/03 B5 — 규칙 전체):
1. **간지 계층 압축**: 대운 전체 / 선택된 세운만 / 선택 세운 내 월운만 / 택일 시에만 일운
2. 그래프 노드: intent graphScope의 evidence path만
3. 사전: dictionaryScope 외 로드 금지(Planner가 결정 — 본 모듈은 사전을 싣지 않음)
4. 이벤트 후보: Top N(기본 5) + score 임계값(40 미만 = 언급 생략 구간, docs/06 톤 표)
5. 모든 후보에 해당 간지와 대운 맥락 필수 — LLM은 간지를 계산할 수 없다

직렬화(T3.5)는 docs/06 "좋은 입력 예" 형태의 한국어 사실 문장으로 만들고,
llm_guard로 입력 토큰을 호출 전 검증한다(초과 시 후보 수를 줄여 재축소).
"""

from __future__ import annotations

import logging
import re
from datetime import date as date_cls
from datetime import timedelta

from saju_manse_analysis.yongsin.operational_role_config import (
    is_favorable_role,
    is_unfavorable_role,
)

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    CONTROLS,
    GENERATES,
    STEM_ELEMENT,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.event_engine import LayerEvidenceScope
from saju_shared_types.event_taxonomy_v2 import (
    EVENT_DOMAIN,
    direction_label,
    event_display_ko,
)
from saju_shared_types.event_taxonomy_v2 import EVENT_KO as _EVENT_KO_V2
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.graph import EvidenceBundle
from saju_shared_types.intent import IntentJson, QueryType
from saju_shared_types.llm_input import (
    BirthChartSummary,
    ChartInterpretation,
    DaewoonEntry,
    DateSelectionBlock,
    LlmBudget,
    LlmCalendarContext,
    LlmEventCandidate,
    LlmEvidence,
    LlmInput,
    LlmLayerGrounding,
    LlmStyleRules,
    MonthOverviewRow,
    PeriodFortune,
    ReferenceFrame,
    RelationshipContext,
    SelectedDay,
    SelectedMonth,
    SelectedYear,
    SubjectBlock,
    UsefulGods,
    YongsinOperationalSummary,
)
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.marriage_timing import derive_marriage_stage
from saju_shared_types.sinsal import LlmSinsalModifier
from saju_shared_types.structure_patterns import DetectedPattern

from . import marriage_timing_profile as _mtp
from . import sinsal_modifier_config as _sinsal_cfg
from .amhap_luck import detect_luck_amhap
from .chart_interpretation import build_chart_interpretation, incoming_ten_god_note
from .direction_suggestion import (
    DIRECTION_SUGGESTION_INSTRUCTION,
    detect_direction_suggestions,
    format_direction_suggestion_lines,
    select_direction_suggestions,
)
from .event_engine_v2 import EventEngineV2
from .event_scoring import favorability_map
from .layer_evidence_scope import classify_layer_evidence_scope, normalize_layers
from .llm_guard import CALL_LIMITS, LLMCallGuard, TokenBudgetExceeded, estimate_tokens
from .manifestation_branch import branch_summary
from .marriage_output_guard import (
    compute_marriage_output_guard,
    has_stability_risk,
    marriage_guard_directive,
)
from .marriage_telemetry import build_marriage_telemetry, emit_marriage_telemetry
from .relation_claim_audit import canonical_claim_lines
from .sinsal_modifier import derive_natal_sinsal_modifiers, select_llm_sinsal_modifiers
from .sinsal_numeric_scoring import apply_sinsal_channel_shadow, channel_note_ko
from .structure_patterns import detect_structure_patterns, select_llm_patterns

TOP_N_CANDIDATES = 5  # 기본 Top N (docs/03 B5 — 3~5)
SCORE_FLOOR = 40  # docs/06 톤 표: <40은 언급 생략 구간 → LLM 미전달
MAX_PATHS_PER_EVENT = 3  # 근거 경로 상한(토큰 절약, 초안)
# 도메인 → 대표 이벤트(다중 도메인 질문에서 secondary 도메인 후보를 포함시키기 위함).
_DOMAIN_PRIMARY_EVENT: dict[str, EventKey] = {
    "career": EventKey.CAREER_CHANGE,
    "relocation": EventKey.RELOCATION,
    "wealth": EventKey.WEALTH_CHANGE,
    "relationship": EventKey.MARRIAGE_SIGNAL,
    "health": EventKey.HEALTH_ATTENTION,
    "education": EventKey.EDUCATION_ADMISSION,
}

# 질문 도메인(intent.domains) → 구조 패턴 domain_hints(EventKeyV2 값) 집합. 도메인 우선 선별용.
# general/미지원 도메인은 매핑 없음 → domains=None(strength desc)로 폴백.
_DOMAIN_EVENT_KEYS: dict[str, set[str]] = {
    "career": {"career_change", "job_gain", "promotion", "business_start", "business_expansion"},
    "wealth": {"wealth_change", "windfall"},
    "relationship": {"relationship_change", "new_relationship", "marriage_signal", "childbirth"},
    "education": {"education_admission", "education_completion"},
    "health": {"health_attention"},
    "relocation": {"relocation"},
}

# 능동 제안(docs/15) 미노출 질문 유형 — 방향 제안이 소음·부적절이 되는 유형.
_NO_SUGGESTION_QUERY_TYPES = (
    QueryType.TERMINOLOGY_EDUCATION,
    QueryType.FEEDBACK_CORRECTION,
    QueryType.EMOTIONAL_SUPPORT,
    QueryType.OUT_OF_SCOPE,
)

# docs/06 점수→표현 강도 매핑(toneGuide 기본).
_TONE_GUIDE = (
    "85+: '~신호가 매우 강합니다' / 70~84: '~가능성이 높습니다' / "
    "55~69: '~흐름이 나타날 수 있습니다' / 40~54: '~조짐이 약하게 있습니다' / "
    "40 미만: 언급 생략 또는 '뚜렷한 신호는 없습니다'"
)
_BASE_PROHIBITED = ["반드시 이직한다", "무조건 헤어진다", "확정적으로 발생한다"]
_BASE_INSTRUCTION = (
    "사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, 촉발→진행→결과의 인과 흐름으로 "
    "설명하되 '촉발/진행/결과'를 단계 표제·소제목으로 달지 말고 자연스러운 문장으로 녹일 것. "
    "제공된 간지·점수·근거 외의 명리 계산을 시도하지 말 것 — 데이터에 없으면 지어내지 말고 "
    "해당 대목을 조용히 생략하고, '제공되지 않았다'·'재계산은 제공되지 않았다' 같은 안내·메타 "
    "문구는 답변에 쓰지 말 것."
)
# 기간 총운(E9) framing — 같은 위계·사건화 철학, 출력은 해당 기간 단위로 한정.
# 하루 운세(E9 daily) — 하루 안에 가능한 범위로 한정(사용자 확정 2026-06-12).
_DAILY_INSTRUCTION = (
    " 이 질문은 '하루 운세'다 — 하루 안에 실제로 일어날 수 있는 범위로만 풀 것: "
    "주요 사건의 '조짐/신호'(실행·확정 단정 금지), 소소한 금전·횡재, 직장에서의 가벼운 "
    "변화나 기분, 애정 관련 만남·연락, 작은 다툼·신경전, 이동·건강·컨디션 정도다. "
    "이직·이사 같은 인생 사건을 '오늘 일어난다'고 단정하지 말고, 그날 일진이 그런 흐름의 "
    "'조짐을 비춘다'는 수준으로만 언급한다. [오늘의 운세] 블록의 일진·생활 슬롯 점수 "
    "범위 안에서 핵심기운→분야별(일·돈·관계·건강)→주의·활용 순으로 간결히 서술할 것."
)
# 월간 총운 — 그 달의 큰 흐름. 대운·세운이 형성한 기운이 이 달에 작동하는 양상 중심.
_MONTHLY_INSTRUCTION = (
    " 이 질문은 '특정 한 달의 총운'이다 — 그 달의 큰 흐름을 잡되, 대운·세운이 형성한 "
    "기운이 이 달에 어떻게 작동하는지를 중심으로 풀 것. [이번 달 총운] 블록의 분야별"
    "(일·직업/재물/관계·연애/건강) 점수와, 그 달 안에서 상대적으로 주의할 시기·기회 "
    "시기(주·일)를 함께 짚는다. 한 달 안에 가능한 사건의 '활성화·가능성'으로 표현하고 "
    "특정 사건의 실행·확정은 단정하지 말 것."
)
# 연간 총운 — 한 해 핵심 주제. 대운이 형성한 배경 위에서 세운으로 푼다.
_YEARLY_INSTRUCTION = (
    " 이 질문은 '한 해(특정 연)의 총운'이다 — 한 해의 핵심 주제를, 대운이 형성한 큰 "
    "배경 위에서 세운으로 풀 것. [올해 총운] 블록의 상·하반기 흐름과 분야별(직업/재물/"
    "관계/건강) 기운, 주의 시기·기회 시기(월)를 짚는다. 연 단위라 사건의 방향·가능성·"
    "시기 흐름으로 서술하고 특정 사건을 단정하지 말 것."
)
# 계층형 grounding 공통 규칙(P2, 2026-07-27) — 일·월·연·M15가 **같은 SSOT**를 쓴다.
# 일운 전용 지시문에만 넣으면 월운·연운에서 평면 합산이 다시 나타난다(데굴님 지적).
_PERIOD_HIERARCHY_INSTRUCTION = (
    " [계층 규칙] 대상 기간만으로 전체 흐름을 단정하지 말 것. 상위 배경(대운·세운·월운)과 "
    "대상 기간을 분리해 서술하고, 천간과 지지의 방향이 반대인 층위는 '혼합' 상태를 그대로 "
    "유지할 것(한쪽으로 축약 금지). 좋은 층위와 나쁜 층위를 평균 내 '중립'·'평범'으로 "
    "합산하지 말 것 — 배경이 우호적이어도 대상 기간의 마찰은 마찰대로, 배경이 부담이어도 "
    "대상 기간의 완화는 완화대로 말한다. 분류 코드는 검사용이니 코드명을 그대로 쓰지 말고 "
    "층별 근거로 서술할 것."
)
_PERIOD_FORTUNE_INSTRUCTION = {
    "daily": _DAILY_INSTRUCTION,
    "monthly": _MONTHLY_INSTRUCTION,
    "yearly": _YEARLY_INSTRUCTION,
}
# 운에서 오는 신살(2026-06-12 사용자 확정) — 원국 보유와 작용 방식이 다르다.
_LUCK_SINSAL_INSTRUCTION = (
    " 운(運)에서 들어온 신살은 타고난 체질이 아니라 그 시기에 '사건·자극'으로 터지는 "
    "신호다 — 블록의 운 신살 '유입 레벨'을 따를 것: 대운 신살은 향후 10년의 무대·환경이 "
    "그 색으로 바뀌는 것, 세운 신살은 그해 실제 일어나는 사건이다. 운 신살은 단독이 "
    "아니라 원국 글자를 합·충·형으로 건드려 발동하므로, [형충회합]에 표기된 그 운 글자가 "
    "원국의 어느 자리를 건드리는지(월지=직업·사회, 일지=배우자·가정)와 연결해 발현 영역을 "
    "정한다. 길흉은 ①희기 결합(나에게 희신인 글자에 실린 흉살은 통제된 권력·성취로, 기신인 "
    "글자에 실린 길신은 생색뿐 실속이 약함) ②궁성 충돌 자리 ③공망이 충으로 풀려 묶였던 "
    "기운이 해방되는지로 판가름하되, 신살은 끝까지 보조 자료다."
)
# fortune_type → (블록 헤더, 간지 줄 라벨).
_PERIOD_FORTUNE_HEADER = {
    "daily": ("오늘의 운세", "일진"),
    "monthly": ("이번 달 총운", "월운"),
    "yearly": ("올해 총운", "세운"),
}
# v2.2.1 — 계산 금지/의미 서술 허용 분리(docs/06 표현 원칙 4 개정).
_MEANING_INSTRUCTION = (
    "[명식 해석 자료]와 후보별 '해석' 줄을 적극 엮어, '이 글자가 일간에게 무엇이고 "
    "지금 들어온 글자와 어떤 관계를 맺어 이런 신호가 되는가'의 이야기로 풍부하게 서술할 "
    "것 — 점수와 간지를 낭독만 하지 말 것. 단, 간지·점수·합충 성립 판정의 재계산·변경은 "
    "여전히 금지."
)
# regression_2025_08 — 단일 합·십성으로 사건명 재해석 금지(동반 신호 매트릭스가 결정).
_MATRIX_INSTRUCTION = (
    "사건명은 동반 신호 매트릭스(신호 구성·개수)로 엔진이 확정한 값이다 — 단일 합이나 "
    "십성 하나만 근거로 다른 사건으로 재해석하지 말 것(예: 합+정관이라도 역마·식상 "
    "동반이면 이동·이사 신호가 우세할 수 있음). 각 후보의 '동반 신호' 구성을 근거로 "
    "인용할 것."
)
_AUXILIARY_INSTRUCTION = (
    "신살·암합은 보조 참고 자료다 — '이런 점은 이런 신살의 영향일 수도 있다' 정도로만 "
    "가볍게 곁들이고, 성향·길흉의 핵심 근거로 부각하거나 그것만으로 사건을 단정하지 "
    "말 것. 운 암합은 '물밑·비공식'의 뉘앙스(숨은 계약·은밀한 인연·비공식 협력)로만, "
    "암합이 건드린 궁성(연-대외/월-직장·사회/일-사생활·배우자/시-취미·투자)과 십성을 "
    "참고해 가능성으로만 언급한다. 풀이의 중심은 일간·십성·합충형파해와 운의 관계다."
)
# 신살 궁성론(2026-06-12 사용자 확정) — 위치·충형공망·용기신에 따른 발현 차이.
_SINSAL_POSITION_INSTRUCTION = (
    "신살은 원국 위치(궁성)에 따라 시기·대상·발현이 달라진다 — 년·월은 사회·대외"
    "(조상/부모·직장, 초중년), 일·시는 개인·가정(나·배우자/자녀·내면, 중말년)으로 "
    "작용한다. 발췌의 '위치'·'위치별' 표기를 따라 해석하고 신살 이름만으로 뭉뚱그리지 "
    "말 것. 또한 그 신살 자리가 충·형·공망을 맞으면 길신은 작용이 정지·반감되고 흉성은 "
    "부작용이 커지거나(공망이면) 무력화되며, 일간 기준 용·희신이면 길작용이 강해지고 "
    "기·구신이면 길신도 힘이 줄거나 흉신이 카리스마·전문성으로 승화될 수 있다 — 이 보정을 "
    "[원국 관계]·공망·용희기구한 정보와 연결하되 여전히 보조 자료로만 쓴다."
)
# 신살 보조 태그(SINSAL_MODIFIER_SPEC Phase A-1) — 구조화 태그 우선 해석.
_SINSAL_MODIFIER_INSTRUCTION = (
    "후보의 '신살 보조' 태그가 있으면 단독 사건 근거로 쓰지 말고, 강도(약함/보조/강함/"
    "매우 강함)·일치 여부·효과 태그에 따라 기존 사건 후보의 질감·리스크·완충·이동성 보조 "
    "신호로만 해석한다 — 길성은 완충·도움·회복, 흉살은 리스크·긴장·주의로 표현하고 단정은 금지."
)
# 답변 길이 — 사용자 확정(2026-06-12): 최대 1,500자.
_LENGTH_INSTRUCTION = (
    "답변은 공백 포함 1,500자 이내로 핵심만 간결하게 쓸 것. 길어지면 가장 중요한 "
    "흐름부터 추리고 나머지는 생략한다."
)
# 마크다운 미지원 출력 — 기호가 그대로 노출되므로 평문으로(항목 4).
_FORMAT_INSTRUCTION = (
    "출력은 마크다운을 쓰지 말 것 — '#', '*', '**', '###', '|' 표 등 마크다운 기호 "
    "없이 자연스러운 평문 문단으로 서술한다. 강조가 필요하면 따옴표나 줄바꿈을 쓴다."
)
# 이벤트 신호의 위상 — 추측값일 뿐 기간 전체를 대표하지 않음(항목 10).
_SCOPE_INSTRUCTION = (
    "[이벤트 후보]는 그 기간에 '가능성이 상대적으로 높은 사건'에 대한 추측 신호일 "
    "뿐, 그 기간 전체를 대표하지 않는다. 이벤트 신호만으로 기간 전부를 규정하지 말고, "
    "원국 구조와 대운·세운의 전반적 기운을 바탕으로 그 시기의 큰 흐름을 먼저 설명한 "
    "뒤 이벤트 신호를 그 안의 한 가능성으로 배치할 것."
)
# 운의 위계 — 대운>세운>월운>일운, 상위 운이 하위 운을 지배(항목 6).
_HIERARCHY_INSTRUCTION = (
    "운은 위계가 있다: 대운(10년·환경/배경) > 세운(1년·사건의 발생) > 월운(달·"
    "타이밍과 심리) > 일운(하루·체감). 상위 운이 하위 운을 지배하므로, 대운으로 큰 "
    "흐름을 먼저 잡고 세운으로 올해의 사건을, 월운·일운으로 시점과 디테일을 조율하는 "
    "순서로 설명할 것. 대운·세운이 받쳐주지 않으면 월운·일운만으로 큰 변화를 단정하지 "
    "말 것."
)
# 원국 보유 요소 vs 운에서 들어온 요소를 반드시 구분(항목 16).
_ORIGIN_INSTRUCTION = (
    "원국(타고난 명식)에 본래 있는 요소와, 운에서 새로 들어와 작용하는 요소를 반드시 "
    "구분해 서술할 것 — 예: 원국에 없던 신살·십성이 운에서 들어온 경우 '원래 가진 것'이 "
    "아니라 '이 시기에 들어온 기운'으로 설명한다. [원국·명식 구조]에 있는 것은 원국 "
    "보유, [이벤트 후보]·[근거 경로]의 유입 글자는 운에서 온 것이다."
)
# 격국·용희기구한·궁성 활용(항목 8·9·14).
_STRUCTURE_INSTRUCTION = (
    "[원국·명식 구조]의 격국·용희기구한(용신/희신/기신/구신/한신)·궁성(자리별 가족 "
    "역할)을 풀이에 활용할 것 — 용신/기신만이 아니라 희신·구신·한신의 작용도, 관계·"
    "가족 풀이에서는 궁성 자리(연-조상, 월-부모, 일-나·배우자, 시-자녀)도 함께 본다. "
    "이 정보가 있으므로 '모른다'고 답하지 말 것."
)
# 작동 역할 우선 참고 — 정적 용희기구한과 실제 작동성이 다를 수 있다(Phase 5a, 원국 기준).
_OPERATIONAL_INSTRUCTION = (
    "[작동 역할]은 원국(타고난 명식) 기준 실제 작동성·조건부 해석 자료다. canonical(용희기구한)은 "
    "전통적 정적 역할로 설명하고, 원국의 실제 작동성·조건부 해석은 [작동 역할]을 우선 참고한다. "
    "단 점수·이벤트 판정은 엔진 산출값을 그대로 따른다(바꾸지 말 것). '조건부 희신/병'은 단순 "
    "희신으로 해석하지 말고(생용신이나 과다·병 동반), '조후보조신'은 주용신은 아니나 실제 "
    "보조약으로 설명하며, 용신 작동성(operability)이 낮으면 '용신은 맞으나 작동성이 약하다'로 "
    "설명한다. 운에서 들어오는 오행도 정적 희신/기신만으로 단정하지 말고 원국 [작동 역할]을 "
    "함께 본다(점수·판정은 엔진값 그대로)."
)
# 길흉 반전 — 구신·기신도 조건부로 돕는다(사용자 확정 2026-06-12).
_REVERSAL_INSTRUCTION = (
    "용희기구한의 길흉은 고정이 아니다 — 흉신(기신·구신)도 구조·운에 따라 사주를 "
    "돕는 반전이 있다. 구신은 ①희신이 태과할 때 그 과한 기운을 눌러 중화하거나 "
    "②기신과 합해 기신을 묶거나(탐합망극) ③운에서 통관 글자가 들어와 징검다리가 되거나 "
    "④제화되어 권력·전문 기술로 치환될 때 오히려 복이 된다. '구신이라 무조건 나쁘다'고 "
    "단정하지 말고, [명식 해석 자료]의 반전 조건을 살펴 해당 시 그 가능성을 함께 풀이할 것."
)
# 합의 작용을 끝까지 설명(항목 17·18).
_HARMONY_INSTRUCTION = (
    "합·충·형·파·해의 작용은 결과까지 끝맺을 것 — '합이 되어 좋게 작용합니다'로 끝내지 "
    "말고, '무엇과 합하여(예: 갑기합), 무엇으로 변하거나 작용하고(예: 합화 토 → 용신), "
    "그래서 어떤 결과로 나타나는지'까지 인과를 완결한다. 합화 결과 오행이 용신/기신 중 "
    "무엇인지가 길흉의 방향을 정한다 — 근거 경로의 합화·용기신 표시를 활용할 것."
)
# 방합 준방합 규칙(항목 3) — 두 글자를 방합 성립으로 단정 금지.
_BANGHAP_INSTRUCTION = (
    "방합(인묘진/사오미/신유술/해자축)은 같은 계절 세 글자가 모두 모여야 성립한다. "
    "두 글자(예: 巳午)만 있으면 '사오미 방합이 형성됐다'고 단정하지 말 것 — 그 오행 "
    "기운이 매우 강해진 '준방합' 상태로만 설명하고, 운에서 마지막 글자(예: 未)가 채워질 "
    "때 비로소 방합이 촉발돼 사건이 크게 현실화된다고 풀이한다."
)
# 물상(2단계 프로필) 사실 맥락 — 상황 구체화용. 점수·판정·간지 불변, 사실 확대해석 금지.
_PROFILE_FACTS_INSTRUCTION = (
    "[사용자 정보]는 사용자가 입력한 사실 맥락(직업·혼인·거주 등)이다. 풀이를 그 상황에 맞게 "
    "구체화하되(예: 직업 형태에 맞는 사건 표현), 점수·간지·판정은 바꾸지 말고 입력된 사실을 "
    "단정적으로 확대 해석하거나 없는 정보를 지어내지 말 것."
)
# 구조 패턴 태그 — 구조 라벨일 뿐 사건·길흉 확정 아님(원칙 3·4, 설계 §14).
_STRUCTURE_PATTERN_INSTRUCTION = (
    "[구조 패턴]은 십성 관계 구조를 압축한 설명 라벨이다 — 사건이나 길흉의 확정이 아니다. "
    "'관인상생이라 취업 확정' 같은 단정 금지. 각 태그의 도메인은 후보(가능성)일 뿐이며, "
    "길흉 방향은 용희기구한·작동 역할로, 사건 여부·시점은 이벤트 후보·근거 경로로 판단한다. "
    "구조 패턴은 그 판단을 자연스럽게 설명하는 어휘로만 활용할 것."
)
# v1 [오늘 날짜]·자체 검증 체크리스트 계승 — LLM은 어떤 계산도 할 수 없다는 전제.
_REFERENCE_INSTRUCTION = (
    "[기준 시점]의 오늘 날짜를 기준으로 과거·현재·미래를 판단할 것 — 임의로 다른 "
    "날짜를 기준으로 삼지 말 것. 질문의 시점 표현(올해/내년/다음 달 등)은 [기준 시점]에 "
    "해석되어 있다. 후보·근거의 기간이 오늘보다 과거(연·월이 기준 시점 이전)면 '이미 지난 "
    "일'로 과거형으로 서술하고 앞으로 다가올 일처럼 예측하지 말 것. 시점을 명시하지 않은 "
    "질문은 올해(현재 연도)와 가까운 미래를 답의 중심에 두고, 지난 흐름은 배경으로만 짧게 "
    "짚되 올해를 건너뛰지 말 것."
)
_LABEL_INSTRUCTION = (
    "이벤트는 반드시 한글 라벨로 부를 것(예: '이직·직업 변화') — career_change 같은 "
    "영문 내부 키를 답변에 노출하지 말 것."
)
_SELF_CHECK_INSTRUCTION = (
    "답변 작성 후 자체 검증: 답변에 등장한 모든 연도·월·날짜·간지·점수가 위 입력에 "
    "실제로 존재하는지 확인하고, 입력에 없는 항목은 삭제하거나 '해당 정보는 제공되지 "
    "않았다'로 바꿀 것. 특히 일주(日柱)·일간·용신 표기는 [원국·명식 구조]의 값과 글자까지 "
    "일치하는지 반드시 대조할 것(다른 간지로 적었으면 그 값으로 정정). 신살·십성의 주(柱) "
    "위치도 [위치:] 표기와 대조해 없는 주로 옮겨 적었으면 정정할 것('년·월에 있으면' 류 "
    "위치별 일반론을 실제 위치로 오인 금지)."
)
# 후속 턴 절제(항목 19) — 멀티턴에서 인사·앞 내용 재설명 반복 금지. 단 원국 사실(일주 등)은
# 글자 그대로 유지(후속 턴 일주 오답 방지 — 2026-06-23 데굴님 지적: '일주를 재인용 말라'가
# 일주를 기억으로 대충 생성→환각시키던 원인).
_FOLLOWUP_INSTRUCTION = (
    "이번은 대화의 후속 답변이다 — '안녕하세요/반갑습니다' 류 인사나 자기소개를 다시 "
    "하지 말고, 격국·용신·성향 등 배경을 길게 재설명하지 말 것(바로 이번 질문의 새 내용으로 "
    "답하되 필요한 최소 맥락만 한 문장 이내). 단, 일주·일간·용신·격국 등 원국 사실을 언급할 "
    "때는 반드시 [원국·명식 구조]에 적힌 값을 글자 그대로 쓰고, 기억으로 새로 지어내거나 다른 "
    "간지로 바꾸지 말 것(일주는 [원국·명식 구조]의 일주 간지 그대로)."
)
_OUT_OF_RANGE_INSTRUCTION = (
    "[참고 — 질문 기간 외 흐름]은 배경 맥락으로만 짧게 인용하고 메인 서술로 삼지 말 것. "
    "답변의 중심은 질문 기간 내 데이터다."
)
_DATE_TABLE_INSTRUCTION = (
    "[택일 결과] 표가 제공되었으므로 '날짜 정보가 없다' 류의 회피성 답변을 절대 하지 말 "
    "것. 표의 날짜·간지·사유를 그대로 인용해 1~3개 날짜를 명확히 추천할 것. 표 밖의 "
    "날짜를 임의로 만들지 말 것."
)

# 이벤트 한글 라벨(21키 taxonomy_v2) — 내부 키 노출 방지(Phase 7).
_EVENT_KO: dict[str, str] = {str(k): v for k, v in _EVENT_KO_V2.items()}
# 근거 경로 내부 노트 제거(예: "(docs/05 회귀 기준 케이스)").
_INTERNAL_NOTE_RE = re.compile(r"\s*\((?:docs?/|내부|회귀)[^)]*\)")
# 저작 메타 괄호 — LLM 지시·금기·표현 제한 안내 등(예: "(windfall은 표현 제한 — 당첨 단정
# 금지, 변동성·과몰입 경고)", "(표현 제한)"). 근거 경로 등 사용자 노출 출력에서 제거한다.
# '(재성국 완성)'처럼 의미 있는 괄호는 키워드 미포함이라 보존된다(2026-06-16 챗 누출 정리).
_AUTHORING_PAREN_RE = re.compile(
    r"\s*\([^)]*(?:표현\s*제한|당첨|단정|번호\s*거부|로또|과몰입|투자\s*조언|고지|경계 동반)[^)]*\)"
)


def _clean_evidence_text(text: str) -> str:
    """근거 경로/보조 근거에서 내부·저작 메타 괄호를 제거한다(사용자 노출 정리)."""
    return _AUTHORING_PAREN_RE.sub("", _INTERNAL_NOTE_RE.sub("", text)).strip()


_FIRST_SENT_END_RE = re.compile(r"[다요죠]\.")


def first_sentence(text: str, limit: int = 120) -> str:
    """서술 텍스트의 첫 문장(종결어미 '다./요./죠.' 기준, 상한 길이 보호).

    리포트 섹션·채팅 답변의 '서두 반복 금지' 블록 재료(2026-07-06) — 직전 출력의 실제
    첫 문장을 다음 프롬프트에 제시해 같은 패턴 서두를 막는다. 해요체(…예요.) 답변도
    첫 문장에서 끊기도록 종결어미를 폭넓게 본다. 종결어미가 없으면 첫 줄.
    """
    stripped = text.strip()
    m = _FIRST_SENT_END_RE.search(stripped)
    snippet = stripped[: m.end()] if m else stripped.split("\n", 1)[0]
    return snippet[:limit].strip()


_POLARITY_KO = {
    "positive": "우호적",
    "negative_or_forced": "부담·비자발 계열",
    "conditional": "조건부",
    "neutral": "중립",
}


def polarity_ko(value: str) -> str:
    """극성 → 한글(내부 어휘 노출 방지)."""
    return _POLARITY_KO.get(value, value)


# 택일 추천 등급 → 한글 라벨(내부 enum 노출 방지 — LLM이 'recommended'를 그대로 인용하던 결함
# 차단, 2026-07-01 데굴님 지적). recommended|acceptable|avoid.
_RECOMMENDATION_KO = {"recommended": "추천", "acceptable": "무난", "avoid": "회피"}


def recommendation_ko(value: str) -> str:
    """택일 추천 등급 → 한글(내부 어휘 노출 방지)."""
    return _RECOMMENDATION_KO.get(value, value)


#: LLM에 전달할 억제 사유 allowlist — 원시 reason_codes를 통째로 넘기지 않는다.
#: 내부 계산 사유·shadow 코드·설명 불필요 enum이 프롬프트에 새는 것을 막는다.
_GROUNDING_CODE_ALLOWLIST: dict[str, str] = {
    "SUPPRESS_minor_layer_only": "MINOR_LAYER_ONLY",
}
#: 층위 한글 라벨(표시 전용) — 상위/하위 구분은 layer_evidence_scope가 단독으로 판정한다.
_LAYER_KO: dict[str, str] = {
    "daewoon": "대운", "sewoon": "세운", "wolwoon": "월운", "ilwoon": "일운",
}


def _layer_grounding(c) -> LlmLayerGrounding | None:
    """후보의 기간 근거를 LLM용으로 정규화한다(점수·등급·순위 불변).

    판정은 `classify_layer_evidence_scope` 한 곳에서만 한다 — 여기서 따로 재계산하면
    P2 랭킹 게이트와 어긋난다. 입력은 `candidate_source_layers`(후보별 기여)이며
    `stack_layers`(평가 스택 구성)는 읽지 않는다.

    근거 코드는 legacy DTO의 실제 운반 필드인 `evidence_path`에서 읽는다.
    `reason_codes` 폴백은 V2 후보를 직접 넘기는 호출자를 위한 것이며, 운영 주 경로는
    `evidence_path`다(to_legacy_candidate가 여기에 옮긴다).

    Returns:
        후보별 기여 층위가 확인된 경우에만 grounding. 현재 엔진은 이를 수집하지 않으므로
        운영 경로에서는 항상 None이다 — 층위를 지어내는 대신 기존 동작(층위 언급 없음)을
        유지한다. 실제 수집은 P2-PROV 이후.
    """
    layers = list(getattr(c, "candidate_source_layers", []) or [])
    scope = classify_layer_evidence_scope(layers)
    if scope is LayerEvidenceScope.UNKNOWN:
        return None
    raw_codes = list(getattr(c, "evidence_path", []) or []) or list(
        getattr(c, "reason_codes", []) or []
    )
    codes = [_GROUNDING_CODE_ALLOWLIST[r] for r in raw_codes if r in _GROUNDING_CODE_ALLOWLIST]
    return LlmLayerGrounding(
        source_layers=normalize_layers(layers),
        has_upper_layer_support=scope is LayerEvidenceScope.UPPER_SUPPORTED,
        minor_layer_only=scope is LayerEvidenceScope.MINOR_ONLY,
        confidence_adjusted=bool(codes),
        grounding_codes=codes,
    )


def _direction_for(c: EventCandidate) -> str:
    """후보의 방향(길흉)+타이밍 라벨 — '조건부' 4값 축소 대신 또렷한 방향. 없으면 polarity 폴백."""
    lbl = direction_label(c.quality, c.timing)
    return lbl or polarity_ko(str(c.polarity))


# 결과 유불리(favorability) 밴드 — 발생 가능성(score)과 분리된 길흉 채널. 중립대(±0.2)는 빈
# 문자열(노출 안 함). 시험 합·불·특수직군·퇴직 리스크·이직 압박/기회가 합산된 net 유불리.
_FAVORABILITY_BAND_TH = 0.2


def _favorability_ko(favorability: float) -> str:
    """favorability(−1~1) → 유불리 밴드 라벨(중립은 빈 문자열)."""
    if favorability >= _FAVORABILITY_BAND_TH:
        return "유리(결과 우호)"
    if favorability <= -_FAVORABILITY_BAND_TH:
        return "불리(결과 주의)"
    return ""


# 기반 최고 달 지목용 — 운 품질 등급 우선순위(길 방향만). 그 기간에 이 등급의 달이 있으면
# 질문 사건과 무관하게 '가장 도움되는 시기'로 명시 노출(intent 질문에서 누락 방지).
_BEST_GRADE_PRIORITY = ("강한 용신운", "용신운(부분)")


def _best_quality_months(rows: list[MonthOverviewRow]) -> str:
    """그 기간 운 품질 최고 달(강한 용신운 우선, 없으면 용신운 부분) — 'YYYY-MM(등급)' 목록.

    길 방향 등급만 대상(기신·혼합은 '좋은 달'로 지목하지 않는다). 너무 길지 않게 최대 3개.
    """
    for grade in _BEST_GRADE_PRIORITY:
        hits = [r.period for r in rows if r.luck_grade == grade]
        if hits:
            return ", ".join(f"{p}({grade})" for p in hits[:3])
    return ""


def event_ko(key: EventKey | str) -> str:
    """EventKey → 한글 라벨(미등록 시 키 그대로)."""
    return _EVENT_KO.get(str(key), str(key))


def _period_bounds(
    period: str, month_bounds: dict[str, tuple[str, str]] | None = None
) -> tuple[str, str]:
    """후보 기간 라벨('2026'/'2026-05'/'2026-05-03') → ISO 구간.

    월 라벨은 절기 월이라 캘린더 월 경계로 잡으면 절입 직전 날을 다음 달로 오인한다
    (2026-07-04는 절기상 甲午인데 캘린더 2026-07로 잡힘). month_bounds가 주어지면 그
    절기 양력 경계를 우선 사용한다(월운 절기 경계 맵 — _month_seolgi_bounds).
    """
    if len(period) == 4:
        return f"{period}-01-01", f"{period}-12-31"
    if len(period) == 7:
        if month_bounds and period in month_bounds:
            return month_bounds[period]
        return f"{period}-01", f"{period}-31"
    return period, period


def in_question_range(
    period: str,
    start: str | None,
    end: str | None,
    month_bounds: dict[str, tuple[str, str]] | None = None,
) -> bool:
    """후보 기간이 질문 기간과 겹치는가(ISO 문자열 비교, 월은 절기 경계 우선)."""
    if not start and not end:
        return True
    p_start, p_end = _period_bounds(period, month_bounds)
    q_start, _ = _period_bounds(start, month_bounds) if start else ("0000-01-01", "")
    _, q_end = _period_bounds(end or start or "9999", month_bounds)
    return p_start <= q_end and p_end >= q_start


def _month_seolgi_bounds(result: ManseV2Result) -> dict[str, tuple[str, str]]:
    """월운 라벨(YYYY-MM) → 절기 월 양력 경계(절입~다음 절입 전일) ISO 매핑.

    월 후보 기간 비교를 절기 기준으로 맞춘다 — 캘린더 월 경계는 절입 직전 초순일을 다음
    절기월로 오인하기 때문(질문일이 속한 절기월이 '지난 달'로 밀려나던 결함 보정).
    """
    lc = result.luck_cycles
    if lc is None:
        return {}
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from saju_manse_core.calendar.solar_terms import get_table

    tz_name = result.time_correction.timezone if result.time_correction else "Asia/Seoul"
    try:
        tz = ZoneInfo(tz_name)
        table = get_table()
    except Exception:  # noqa: BLE001 — 절기 테이블 부재 시 캘린더 경계로 폴백
        return {}
    out: dict[str, tuple[str, str]] = {}
    for p in lc.monthly_luck:
        try:
            y, m = int(p.label[:4]), int(p.label[5:7])
            mid = datetime(y, m, 15, 12, 0, tzinfo=tz)
            prev_jeol, next_jeol = table.bounding_month_terms(mid)
            out[p.label] = (
                prev_jeol.astimezone(tz).date().isoformat(),
                (next_jeol.astimezone(tz).date() - timedelta(days=1)).isoformat(),
            )
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def tone_for_score(score: int) -> str:
    """점수 → 표현 강도(docs/06 매핑표)."""
    if score >= 85:
        return "신호가 매우 강합니다"
    if score >= 70:
        return "가능성이 높습니다"
    if score >= 55:
        return "흐름이 나타날 수 있습니다"
    if score >= 40:
        return "조짐이 약하게 있습니다"
    return "뚜렷한 신호는 없습니다"


def reduce_candidates(
    candidates: list[EventCandidate],
    graph_scope: list[EventKey],
    top_n: int = TOP_N_CANDIDATES,
    score_floor: int = SCORE_FLOOR,
    period_start: str | None = None,
    period_end: str | None = None,
    month_bounds: dict[str, tuple[str, str]] | None = None,
) -> list[EventCandidate]:
    """이벤트 후보 축소 — graphScope + 임계값 + **질문 기간 필터** + Top N.

    기간 필터(P2): '올해' 질문에 과거 100점 후보가 메인이 되는 문제 차단.
    기간 외 상위 후보는 reduce_with_context()로 별도 분리 제공.
    """
    scoped = [
        c
        for c in candidates
        if (not graph_scope or c.event_key in graph_scope)
        and c.score >= score_floor
        and in_question_range(c.period, period_start, period_end, month_bounds)
    ]
    # LEI 정렬축(현실적합>과거유사) 우선 → 점수 포화 시 raw 가중 합 → 시점·키. 개인 시그니처
    # 미배선 시 life_fit·personal_match=0이라 기존 (-score, -raw_total) 정렬과 동치.
    return sorted(
        scoped,
        key=lambda c: (
            -getattr(c, "life_fit", 0.0),
            -getattr(c, "personal_match", 0.0),
            -c.score,
            -getattr(c, "raw_total", 0.0),
            c.period,
            str(c.event_key),
        ),
    )[:top_n]


# ── 총운형 다변화 선별 (2026-07-14 데굴님 설계 확정) ─────────────────────
#
# 실측 결함: "앞으로 1년 주요 이벤트" 같은 총운 질문에 단일 도메인 질문과 동일한 순수
# 점수순 Top-N을 적용 → 강한 십성 유입 해에 한 사건이 기간만 바꿔 5슬롯을 독점(재물
# 변화 ×5), 답변이 한 도메인으로 쏠림. 해법은 균등 배분(라운드로빈)이 아니라 **중복을
# 압축한 뒤 유효 신호 범위 안에서 조망성 확보**:
#   ①의미 클러스터링(event_key+길흉 방향+지배 신호 계열 — 반대 방향·원인 다른 독립
#     피크는 분리, 기간 반복은 대표+supporting_periods로 집계)
#   ②품질 게이트 다양화(전체 최고 1개 → 미포함 도메인 후보는 절대·상대·life_fit 게이트
#     통과 시에만 추가 → 남는 슬롯 점수순, 동일 도메인은 다른 유효 도메인이 있는 동안
#     최대 2개 — 약한 후보를 억지로 끌어올리지 않고, 압도 도메인은 집중 보존)
#   ③life_fit 계층 불변(다양화는 정렬 계층 안에서만) ④Top 3~5는 목표 범위(강제 충원 금지).
# 특정 도메인 질문은 reduce_candidates 기존 로직 그대로(회귀 0).

_overview_log = logging.getLogger(__name__)

# 커버리지 품질 게이트 — 절대 최소점수 / 전체 최고점 대비 허용 격차 / life_fit 허용 격차.
OVERVIEW_COVERAGE_MIN_SCORE = 55
OVERVIEW_RELATIVE_WINDOW = 30
OVERVIEW_LIFE_FIT_WINDOW = 0.15
# 동일 도메인 상한(조건부 — 미포함 유효 도메인 클러스터가 남아 있을 때만 적용).
OVERVIEW_DOMAIN_CAP = 2
# 근-최고점(co-top) 창(2026-07-14 실사용 2차 결함) — 최고점과 이 격차 이내의 클러스터는
# '주요 이벤트' 그 자체이므로 커버리지보다 먼저 선정한다. 실측: 커버리지 패스가 슬롯을
# 전부 소모해 결혼 신호 98점이 이동 82·건강 75점에 밀려 탈락(총운이 최상위 사건을 누락).
OVERVIEW_CO_TOP_WINDOW = 10
# 선정 제외 강신호 메타의 포함 기준(2026-07-14 3차 평가 — 데굴님 확정): co-top 창(−10)
# 만으로는 85점급 '강' 신호가 여전히 침묵 가능(최고점 100 기준 창 밖) → 상대 창은
# 커버리지 게이트와 동일(−30), 절대 하한은 '가능성이 높습니다' 등급(70). 나열 폭주
# 방지 캡 3건(정렬순 상위).
OVERVIEW_DROPPED_META_MIN = 70
OVERVIEW_DROPPED_META_CAP = 3

_QUALITY_POS = frozenset({"opportunity", "achievement", "resolution"})
_QUALITY_NEG = frozenset({"loss", "pressure", "conflict"})


def _overview_direction(c: EventCandidate) -> str:
    """길흉 방향 축 — quality 길·흉군 우선, 없으면 favorability 부호(반대 방향 병합 금지)."""
    if c.quality in _QUALITY_POS:
        return "pos"
    if c.quality in _QUALITY_NEG:
        return "neg"
    if c.favorability > 0.15:
        return "pos"
    if c.favorability < -0.15:
        return "neg"
    return "mixed"


def _dominant_trigger(c: EventCandidate) -> str:
    """지배 신호 계열(|weight| 최대 신호의 type) — 원인이 다른 독립 피크의 분리 축."""
    if not c.signals:
        return ""
    return max(c.signals, key=lambda s: abs(s.weight)).type


def _life_fit_sort_key(c: EventCandidate) -> tuple:
    """reduce_candidates와 동일한 정렬 계층(life_fit>personal_match>score>raw) — 불변."""
    return (
        -getattr(c, "life_fit", 0.0),
        -getattr(c, "personal_match", 0.0),
        -c.score,
        -getattr(c, "raw_total", 0.0),
        c.period,
        str(c.event_key),
    )


def reduce_overview_candidates(
    candidates: list[EventCandidate],
    period_start: str | None,
    period_end: str | None,
    month_bounds: dict[str, tuple[str, str]] | None = None,
    top_n: int = TOP_N_CANDIDATES,
    score_floor: int = SCORE_FLOOR,
) -> tuple[list[EventCandidate], dict[int, str], list[str]]:
    """총운형 후보 선별 — 의미 클러스터링 + 품질 게이트 다양화.

    Returns:
        (선별 후보, {선별 인덱스: 반복 신호 노트}, 선정 제외 강신호 메타 줄들).
        유효 클러스터가 top_n보다 적으면 그 수만 반환한다(약한 후보 강제 충원 금지 —
        Top 3~5는 목표 범위). 제외 메타는 근-최고점 미선정 클러스터 한정.
    """
    pool = sorted(
        (
            c for c in candidates
            if c.score >= score_floor
            and in_question_range(c.period, period_start, period_end, month_bounds)
        ),
        key=_life_fit_sort_key,
    )
    if not pool:
        return [], {}, []

    # ① 의미 클러스터링 — 대표(정렬 최상위) + 보조 기간 집계.
    clusters: dict[tuple, dict] = {}
    order: list[tuple] = []
    for c in pool:
        key = (str(c.event_key), _overview_direction(c), _dominant_trigger(c))
        if key not in clusters:
            clusters[key] = {"rep": c, "periods": [c.period], "count": 1}
            order.append(key)
        else:
            clusters[key]["periods"].append(c.period)
            clusters[key]["count"] += 1
    ranked = [clusters[k] for k in order]  # pool 정렬 순서 = 대표 정렬 순서

    # ② 품질 게이트 다양화 — 전체 최고 1개 → 미포함 도메인 → 점수순 충원.
    top = ranked[0]
    top_score = top["rep"].score
    top_fit = getattr(top["rep"], "life_fit", 0.0)

    def _domain_of(cl: dict) -> str:
        return EVENT_DOMAIN.get(cl["rep"].event_key, "general")

    def _passes_gate(cl: dict) -> bool:
        rep = cl["rep"]
        return (
            rep.score >= OVERVIEW_COVERAGE_MIN_SCORE
            and rep.score >= top_score - OVERVIEW_RELATIVE_WINDOW
            and getattr(rep, "life_fit", 0.0) >= top_fit - OVERVIEW_LIFE_FIT_WINDOW
        )

    selected: list[dict] = [top]
    covered = {_domain_of(top)}
    remaining = [cl for cl in ranked[1:]]

    def _domain_count(d: str) -> int:
        return sum(1 for s in selected if _domain_of(s) == d)

    def _uncovered_valid_exists(exclude: dict) -> bool:
        return any(
            _domain_of(o) not in covered and _passes_gate(o)
            for o in remaining if o is not exclude and o not in selected
        )

    # co-top 패스 — 최고점 근접 클러스터는 도메인 커버리지보다 먼저(그 자체가 '주요
    # 이벤트'). 게이트·조건부 도메인 캡은 동일 적용(단일 도메인 90점대 나열로의 회귀 방지).
    for cl in remaining:
        if len(selected) >= top_n:
            break
        if cl["rep"].score < top_score - OVERVIEW_CO_TOP_WINDOW:
            continue  # 정렬은 life_fit 우선이라 점수 비단조 — 창 밖만 건너뛴다
        if not _passes_gate(cl):
            continue
        d = _domain_of(cl)
        if _uncovered_valid_exists(cl) and _domain_count(d) >= OVERVIEW_DOMAIN_CAP:
            continue
        selected.append(cl)
        covered.add(d)

    # 커버리지 패스 — 미포함 도메인의 최상위 클러스터를 게이트 통과 시에만 1개씩.
    for cl in remaining:
        if len(selected) >= top_n:
            break
        d = _domain_of(cl)
        if cl in selected or d in covered or not _passes_gate(cl):
            continue
        selected.append(cl)
        covered.add(d)
    # 충원 패스 — 남는 슬롯은 정렬순, 단 품질 게이트 통과 클러스터만(유효 신호 범위
    # 안에서 조망 — 약한 후보로 3~5개를 강제 충원하지 않는다). 동일 도메인 상한은
    # '미포함 유효 도메인이 남아 있을 때만' 적용(조건부) — 압도 도메인 집중은 보존.
    for cl in remaining:
        if len(selected) >= top_n:
            break
        if cl in selected or not _passes_gate(cl):
            continue
        d = _domain_of(cl)
        uncovered_valid = any(
            _domain_of(o) not in covered and _passes_gate(o)
            for o in remaining if o is not cl and o not in selected
        )
        if (
            uncovered_valid
            and sum(1 for s in selected if _domain_of(s) == d) >= OVERVIEW_DOMAIN_CAP
        ):
            continue
        selected.append(cl)
        covered.add(d)

    out: list[EventCandidate] = []
    notes: dict[int, str] = {}
    for idx, cl in enumerate(selected):
        out.append(cl["rep"])
        if cl["count"] > 1:
            others = sorted(p for p in cl["periods"] if p != cl["rep"].period)
            notes[idx] = (
                f"반복 신호: 같은 계열 신호가 {', '.join(others)}에도 나타남"
                f"(총 {cl['count']}회 — 대표 시기 {cl['rep'].period})"
            )

    # 선정 제외 강신호 메타(2026-07-14 not_selected_due_to_limit — 감수 확정 방식):
    # 근-최고점(co-top 창)인데 개인화 가중·슬롯 제한으로 밀린 클러스터는 '신호 없음'이
    # 아니다 — 제한 언급용 메타로 노출한다. 실측: 데굴님 총운에서 결혼 신호 98점이
    # 완전 침묵해 후속 질문("애정운은 없어?")에서야 드러난 결함.
    dropped: list[str] = []
    for cl in ranked:
        if len(dropped) >= OVERVIEW_DROPPED_META_CAP:
            break
        if cl in selected:
            continue
        rep = cl["rep"]
        # '강' 등급(≥70) + 커버리지 상대 창(−30) 이내만 — 85점급 침묵 방지(3차 확대),
        # 그 아래는 노이즈로 보고 메타에서도 생략.
        if (
            rep.score < OVERVIEW_DROPPED_META_MIN
            or rep.score < top_score - OVERVIEW_RELATIVE_WINDOW
        ):
            continue
        if getattr(rep, "life_fit", 0.0) < top_fit - OVERVIEW_LIFE_FIT_WINDOW:
            reason = "현재 생활 맥락 가중(개인화 적합도)에서 후순위"
        else:
            reason = "조망 슬롯 제한"
        label = _EVENT_KO_V2.get(rep.event_key, str(rep.event_key))
        dropped.append(
            f"{label} @ {rep.period} — 신호가 강하게 잡혀 있으나 {reason}로 "
            "이번 조망 선정에서 제외됨"
        )
    return out, notes, dropped


def reduce_with_context(
    candidates: list[EventCandidate],
    graph_scope: list[EventKey],
    period_start: str | None,
    period_end: str | None,
    top_n: int = TOP_N_CANDIDATES,
    score_floor: int = SCORE_FLOOR,
    out_of_range_n: int = 2,
    month_bounds: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[EventCandidate], list[EventCandidate]]:
    """(질문 기간 내 선별, 기간 외 참고 상위) — 참고는 배경 맥락 전용."""
    selected = reduce_candidates(
        candidates,
        graph_scope,
        top_n,
        score_floor,
        period_start,
        period_end,
        month_bounds,
    )
    out_scoped = [
        c
        for c in candidates
        if (not graph_scope or c.event_key in graph_scope)
        and c.score >= score_floor
        and not in_question_range(c.period, period_start, period_end, month_bounds)
    ]
    out_top = sorted(
        out_scoped,
        key=lambda c: (
            -getattr(c, "life_fit", 0.0),
            -getattr(c, "personal_match", 0.0),
            -c.score,
            c.period,
        ),
    )[:out_of_range_n]
    return selected, out_top


def _daewoon_lookup(result: ManseV2Result) -> dict[int, str]:
    """연도 → 대운 간지(대운 맥락 필수 동반용)."""
    lookup: dict[int, str] = {}
    if result.luck_cycles is None:
        return lookup
    for d in result.luck_cycles.daewoon_table:
        for y in range(d.approx_start_date.year, d.approx_end_date.year):
            lookup[y] = d.ganji
    return lookup


def _ganji_lookup(result: ManseV2Result) -> dict[str, str]:
    """기간 라벨 → 간지(세운/월운/일운)."""
    out: dict[str, str] = {}
    if result.luck_cycles is None:
        return out
    lc = result.luck_cycles
    for p in [*lc.yearly_luck, *lc.monthly_luck, *lc.daily_luck]:
        out[p.label] = p.ganji
    return out


def _exact_jiao_dates(result: ManseV2Result) -> list[date_cls]:
    """만세력 엔진이 산출한 정확한 교운일 목록(trace.exact_jiao_un_dates)."""
    if result.luck_cycles is None:
        return []
    out: list[date_cls] = []
    for x in result.luck_cycles.trace.get("exact_jiao_un_dates", []):
        try:
            out.append(date_cls.fromisoformat(x) if isinstance(x, str) else x)
        except (ValueError, TypeError):
            continue
    return out


def _nearest_jiao(approx: date_cls, exact: list[date_cls], max_gap_days: int = 400) -> str:
    """approx_start_date에 가장 가까운 정확 교운일(없거나 너무 멀면 approx)."""
    if not exact:
        return approx.isoformat()
    nearest = min(exact, key=lambda d: abs((d - approx).days))
    if abs((nearest - approx).days) > max_gap_days:
        return approx.isoformat()
    return nearest.isoformat()


def build_calendar_context(
    result: ManseV2Result,
    selected: list[EventCandidate],
    intent: IntentJson,
) -> LlmCalendarContext:
    """간지 계층 압축(docs/03 B5 규칙 1).

    대운: 장기 질문(fortune_overview/대운 단위)이면 전체, 아니면 선택 후보가 속한
    대운만. 세운: 선택 후보 연도만. 월운: 선택 세운 안에서만. 일운: 택일에서만.
    """
    if result.luck_cycles is None:
        return LlmCalendarContext()
    lc = result.luck_cycles
    dw_by_year = _daewoon_lookup(result)
    ganji = _ganji_lookup(result)

    selected_years_set: set[str] = set()
    months: list[SelectedMonth] = []
    seen_months: set[str] = set()
    days: list[SelectedDay] = []
    for c in selected:
        year_label = c.period[:4]
        selected_years_set.add(year_label)
        if len(c.period) == 7 and c.period not in seen_months:  # 월운 — 중복 제거
            seen_months.add(c.period)
            months.append(
                SelectedMonth(
                    period=c.period,
                    ganji=ganji.get(c.period, ""),
                    year=year_label,
                )
            )
        elif len(c.period) == 10:  # 일운 — 택일 질의에서만
            if intent.query_type is QueryType.DATE_RECOMMENDATION:
                days.append(SelectedDay(date=c.period, ganji=ganji.get(c.period, "")))

    years = [
        SelectedYear(
            year=int(y),
            ganji=ganji.get(y, ""),
            daewoon=dw_by_year.get(int(y), ""),
            reason_selected=_selection_reason(y, selected),
        )
        for y in sorted(selected_years_set)
        if y.isdigit()
    ]

    # 대운 전체는 장기 질문에서만 — 시점이 연 단위 이하로 좁혀졌으면 선택 대운만.
    has_bounded_period = intent.time_range is not None and intent.time_range.start is not None
    long_term = intent.time_scope.value in ("long_term", "life_stage", "daewoon_unit") or (
        intent.query_type is QueryType.FORTUNE_OVERVIEW and not has_bounded_period
    )
    wanted_dw = {dw_by_year.get(int(y), "") for y in selected_years_set if y.isdigit()}
    # 정확한 교운일은 만세력 엔진 trace에 있다(approx_start_date는 대략값) — 가장 가까운
    # 정확 교운일을 매칭해 프롬프트에 제공한다(사용자 지적 2026-06-12).
    exact_jiao = _exact_jiao_dates(result)
    daewoon = [
        DaewoonEntry(
            period=f"{d.approx_start_date.year}~{d.approx_end_date.year}",
            ganji=d.ganji,
            age_range=f"{d.start_age}~{d.start_age + 9}세",
            jiao_date=_nearest_jiao(d.approx_start_date, exact_jiao),
        )
        for d in lc.daewoon_table
        if long_term or d.ganji in wanted_dw
    ]
    return LlmCalendarContext(
        daewoon=daewoon,
        selected_years=years,
        selected_months=months,
        selected_days=days,
    )


def _selection_reason(year_label: str, selected: list[EventCandidate]) -> str:
    """세운 선별 사유 — 그 해 최고 후보(한글 라벨 + 강도 표현).

    2026-07-14 데굴님 실사용 발견: 종전 f"{event_key} {score}점"이 영문 내부 키와
    원점수를 LLM에 그대로 노출 — 답변에 '98점'이 인용되는 원칙 위반(점수 비노출·
    내부 키 비노출)의 소스였다. 강도는 tone 표현으로만 전달한다.
    """
    in_year = [c for c in selected if c.period[:4] == year_label]
    if not in_year:
        return ""
    top = max(in_year, key=lambda c: c.score)
    return f"{event_ko(top.event_key)} — {tone_for_score(top.score)}"


def build_birth_summary(result: ManseV2Result) -> BirthChartSummary:
    """원국 요약(확정값만 — LLM 재판정 금지). 대화·보고서 공용."""
    assert result.pillars is not None
    p = result.pillars
    pillars = {"year": p.year.ganji, "month": p.month.ganji, "day": p.day.ganji}
    if p.hour is not None:
        pillars["hour"] = p.hour.ganji
    strength = ""
    if result.force_analysis is not None:
        strength = result.force_analysis.strength.band
    fav = favorability_map(result)
    roles = lambda name: [el for el, role in fav.items() if role == name]  # noqa: E731
    geokguk = ""
    g = result.geokguk
    if g is not None and g.main_structure:
        parts = [g.main_structure, g.formation_level]
        if g.evaluation is not None:
            parts.append(g.evaluation.success_failure_label)
        geokguk = " · ".join(part for part in parts if part)
    # 표면 부재 오행의 지장간 잠복(2026-07-03 데굴님 확정) — '완전 부재'≠'숨은 존재'.
    # 출처 포맷 '亥중甲' = [지지][단계(정/중/여)][천간]. 십성은 일간 기준 엔진 계산.
    hidden_latents: list[str] = []
    flow_note = ""
    if result.force_analysis is not None:
        fe = result.force_analysis.five_elements
        _stage_ko = {"정": "정기", "중": "중기", "여": "여기"}
        dm_stem = Stem(p.day.stem)
        for el in ("木", "火", "土", "金", "水"):
            sources = fe.hidden_support.get(el) or []
            if fe.raw_visible.get(el, 0.0) > 0 or not sources:
                continue
            latent_parts: list[str] = []
            for src_token in dict.fromkeys(sources):  # dedupe(순서 유지)
                if len(src_token) != 3:
                    continue
                b_ch, stage_ch, s_ch = src_token[0], src_token[1], src_token[2]
                tg = str(ten_god(dm_stem, Stem(s_ch)))
                latent_parts.append(f"{b_ch} {_stage_ko.get(stage_ch, stage_ch)} {s_ch}({tg})")
            if latent_parts:
                hidden_latents.append(f"{el}: 표면에 없음 — {' · '.join(latent_parts)} 잠복")
    ya = result.yongsin_analysis
    if (
        ya is not None
        and ya.flow_circulation
        and ya.flow_circulation.get("smooth")
        and "신약" in strength
    ):
        links = ya.flow_circulation.get("sheng_links", 0)
        flow_note = f"유통 양호(상생 고리 {links}/5)"
    return BirthChartSummary(
        day_master=p.day_master,
        pillars=pillars,
        void_branches=list(p.gongmang_branches),
        strength=strength,
        useful_gods=UsefulGods(
            yongsin=roles("용신"),
            heesin=roles("희신"),
            gisin=roles("기신"),
            gusin=roles("구신"),
            hansin=roles("한신"),
        ),
        geokguk=geokguk,
        hidden_latents=hidden_latents,
        flow_note=flow_note,
    )


_MAX_SIGNALS_KO = 4  # 후보별 동반 신호 표기 상한


def _ganji_result_nuance(
    stem_el: str, branch_el: str, stem_role: str, fav_map: dict[str, str]
) -> tuple[str, str, str]:
    """그 달 천간 역할 × 지지와의 생극으로 본 '결실(계약·실속)' 유불리 뉘앙스.

    천간만 보는 단순 휴리스틱의 비대칭(흉=⚠불리만, 길=무경고)을 보정한다. 천간 흉신이라도
    지지 용·희신을 생하면 통관(관인상생)으로 순화되고, 천간 길신이라도 지지로 누설·피극되면
    실속이 약화된다 — 어느 쪽도 단정하지 않게 표시.

    Returns:
        (마커, 설명, 카테고리). 카테고리 ∈ {'unfavorable','tonggwan','leak',''}.
    """
    try:
        s_el, b_el = Element(stem_el), Element(branch_el)
    except ValueError:
        return "", "", ""
    branch_role = fav_map.get(branch_el, "")
    stem_gen_branch = GENERATES.get(s_el) == b_el  # 천간 → 지지 생
    branch_ctrl_stem = CONTROLS.get(b_el) == s_el  # 지지 → 천간 극
    if is_unfavorable_role(stem_role):
        if stem_gen_branch and is_favorable_role(branch_role):
            return (
                "↗통관 순화",
                "천간이 흉신이나 그 달 지지(용·희신)를 생하는 통관(관인상생)으로 순화 — "
                "흉이 일간을 돕는 쪽으로 흐른다(다만 천간 흉신이라 과한 낙관은 금물).",
                "tonggwan",
            )
        return (
            "⚠계약·결실 불리",
            "천간 흉신 — 사건이 일어나도 계약·결실·실속에 불리한 시기(우호 단정 금지).",
            "unfavorable",
        )
    if is_favorable_role(stem_role):
        if (stem_gen_branch and is_unfavorable_role(branch_role)) or branch_ctrl_stem:
            return (
                "⚠천간 길신 누설",
                "천간은 길신이나 그 달 지지로 누설·피극되어 결실·실속이 약화 — "
                "'좋은 달'로 과하게 단정하지 말 것.",
                "leak",
            )
    return "", "", ""


def _to_llm_candidate(
    c: EventCandidate,
    ganji: dict[str, str],
    dw_by_year: dict[int, str],
    day_master: str = "",
    fav_map: dict[str, str] | None = None,
    result: ManseV2Result | None = None,
    sinsal_modifiers: list[LlmSinsalModifier] | None = None,
    sinsal_channel_note: str = "",
) -> LlmEventCandidate:
    period_ganji = ganji.get(c.period, "")
    # 관계 단계(Step 2) — MT reason_codes(evidence_path)에서 도출. 비-MT 후보는 빈값(무영향).
    _stage = derive_marriage_stage(c.evidence_path)
    # 동반 신호 매트릭스(v2.2.1) — 사건명을 결정한 신호 구성을 LLM에 명시.
    signals_ko: list[str] = []
    for sig in c.signals:
        label = _INTERNAL_NOTE_RE.sub("", sig.effect or sig.name).strip()
        if label and label not in signals_ko:
            signals_ko.append(label)
        if len(signals_ko) >= _MAX_SIGNALS_KO:
            break
    note = ""
    if day_master and period_ganji:
        # 후보별 note 는 operational guard 미적용(후보 다수 → 토큰 과증, Phase 5b-1 조건 5/7).
        # 운세 해석 operational guard 는 단일 기간 build_luck_grounding 에서만 붙인다.
        note = incoming_ten_god_note(day_master, period_ganji, fav_map or {})
    # 운 암합(보조) — 점수 미반영, 물밑·비공식 뉘앙스 참고(2026-06-12 자료).
    amhap_notes: list[str] = []
    if result is not None and result.pillars is not None and len(period_ganji) == 2:
        amhaps = detect_luck_amhap(period_ganji[0], period_ganji[1], result.pillars)
        amhap_notes = [a.describe() for a in amhaps[:2]]
    # 유불리 주의(후보별 사실 데이터) — 천간 역할 × 지지 생극(통관/누설)으로 결실 유불리를
    # 본다. 천간 흉신이라도 지지 용·희신을 생하면 순화, 천간 길신이라도 누설·피극되면 약화
    # (천간만 보는 단순 단정의 비대칭 보정, 2026-06-12 → 2026-06-15).
    caution = ""
    if fav_map and len(period_ganji) == 2:
        try:
            stem_el = str(STEM_ELEMENT[Stem(period_ganji[0])])
            branch_el = str(BRANCH_ELEMENT[Branch(period_ganji[1])])
        except ValueError:
            stem_el = branch_el = ""
        if stem_el and branch_el:
            _m, nuance_note, _cat = _ganji_result_nuance(
                stem_el, branch_el, fav_map.get(stem_el, ""), fav_map
            )
            caution = nuance_note
    # 검토월 판정(G3 — 계사월 케이스 일반화): 불안정 신호(중복 충·공망·대운 공망)가
    # 동반되면 이동·변동 신호가 강해도 계약 유지력이 낮다 — 실행이 아니라 검토의 시기.
    unstable = any(
        ("중복 충" in (s.effect or "")) or ("공망" in (s.effect or "")) for s in c.signals
    )
    if unstable:
        review_note = (
            "이동·변동 신호는 강하나 공망·중복 충으로 계약 유지력이 낮은 시기 — "
            "'실행월'이 아니라 '검토월'(조사·조건 확인까지)로 안내할 것."
        )
        caution = f"{caution} {review_note}".strip()
    # 방향 인지 표시 라벨(2026-07-22 P2) — '횡재+손실' 모순 차단. 방향 함의 키는 결과
    # 방향에 맞는 라벨로, 그 외·비V2 키는 기존 라벨 유지(판정·점수 불변).
    _disp = event_display_ko(str(c.event_key), c.quality, c.timing)
    return LlmEventCandidate(
        event_key=c.event_key,
        event_ko=_disp if _disp != str(c.event_key) else event_ko(c.event_key),
        period=c.period,
        ganji=period_ganji,
        daewoon_context=dw_by_year.get(int(c.period[:4]), "") if c.period[:4].isdigit() else "",
        score=c.score,
        signal_count=len(c.signals),
        confidence=str(c.confidence),
        polarity=str(c.polarity),
        direction=_direction_for(c),
        signals_ko=signals_ko,
        incoming_note=note,
        amhap_notes=amhap_notes,
        caution_note=caution,
        favorability_ko=_favorability_ko(c.favorability),
        sinsal_modifiers=list(sinsal_modifiers or []),
        sinsal_channel_note=sinsal_channel_note,
        layer_grounding=_layer_grounding(c),
        marriage_stage=_stage.stage,
        marriage_base_stage=_stage.base_stage,
        marriage_stage_reason=_stage.stage_reason,
        marriage_stage_limit=_stage.stage_limit,
        # B2 — stage_reason(MT 전용)에 없는 REL_CHUNG_* 등 배우자궁 충·형·파·해를
        # full evidence_path로 판정해 출력 가드에 전달(방향 누수 차단, 점수 불변).
        marriage_stability_risk=has_stability_risk(list(c.evidence_path)),
    )


def _sinsal_modifier_str(s: LlmSinsalModifier) -> str:
    """신살 보조 태그 1건 직렬화(숫자 없는 한글, 강도어·궁성·효과 태그)."""
    palace = _sinsal_cfg.PALACE_SHORT_LABEL.get(s.position, s.position)
    match = "·일치" if s.domain_match else ""
    effect = ", ".join(s.effect_tags)
    return f"{s.star}({palace}·{s.llm_strength}{match}): {effect}"


_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _prev_month(month: str) -> str:
    """'YYYY-MM' 직전 달 라벨."""
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def build_reference_frame(
    today: date_cls,
    intent: IntentJson,
    result: ManseV2Result,
    current_month_label: str | None = None,
    current_month_detail: str | None = None,
) -> ReferenceFrame:
    """기준 시점(P1) — v1 [오늘 날짜] 원칙: LLM은 오늘이 언제인지 모른다.

    current_month_label: 오늘이 속한 절기 월운 라벨(YYYY-MM). 시제(지남/남은 구간) 판정의
        기준 달로 쓴다. 미주입 시 양력 ``today`` 폴백(절기 경계 직전 한 달 어긋남 감수).
    current_month_detail: 현재 절기월의 사람이 읽는 상세(간지·양력 절기 span·진행 상태). LLM이
        라벨(YYYY-MM)을 캘린더월로 오인하지 않도록 [기준 시점]에 병기(호출 측이 절기표로 산출).
    """
    ganji = _ganji_lookup(result)
    start = intent.time_range.start if intent.time_range else None
    end = intent.time_range.end if intent.time_range else None
    # 'N개월 안에' 류 상대 창은 end 대신 end_offset_days로 표현된다 —
    # end가 비면 offset으로 실제 끝 날짜를 계산해 기간으로 표기한다
    # (2026-07-17 데굴님 지적: '12개월안에'가 [질문 기간: 오늘 하루]로
    # 축소돼 일운 중심 답변이 되던 결함).
    if (
        start and not end
        and intent.time_range is not None
        and intent.time_range.end_offset_days
        and len(start) == 10
    ):
        try:
            end = (
                date_cls.fromisoformat(start)
                + timedelta(days=int(intent.time_range.end_offset_days))
            ).isoformat()
        except ValueError:
            end = None
    period = f"{start} ~ {end}" if start and end and start != end else (start or "")
    note = (
        f"질문의 시점 표현은 {period} 구간으로 해석되었다."
        if period
        else "질문에 시점이 명시되지 않았다 — 오늘 기준 흐름으로 안내."
    )
    # P3(2026-06-14): 의도(event)·기간 유형을 명시해 LLM이 기간/사건을 재해석하지 않게 한다.
    tr = intent.time_range
    if intent.event_key is not None:
        note += f" 의도 사건: '{event_ko(intent.event_key)}'."
    if tr is not None and tr.granularity is not None:
        gv = tr.granularity.value
        if tr.type == "absolute" and gv == "year":
            note += " 기간 유형: 달력연도(해당 연도 1~12월 전체)."
        elif tr.type == "relative" and gv == "month" and start and end and start[:4] != end[:4]:
            note += " 기간 유형: 현재 달부터 미래 롤링 구간."
        elif gv == "year":
            note += " 기간 유형: 달력연도."
    if period:
        note += " 제공된 후보 기간만 바탕으로 풀이하고 이 기간을 임의로 재해석하지 말 것."
    # P6(2026-06-12): 질문 창이 과거~미래에 걸치면(예: '올해') 이미 지난 구간과 남은
    # 구간을 데이터로 명시 — 지난 달(4월 등)을 다가올 트리거처럼 서술하는 오류 차단.
    cur = current_month_label or f"{today.year}-{today.month:02d}"
    if start and end:
        start_m = start[:7] if len(start) >= 7 else f"{start}-01"
        end_m = end[:7] if len(end) >= 7 else f"{end}-12"
        if start_m < cur <= end_m:
            note += (
                f" 이 중 {start_m}~{_prev_month(cur)}는 이미 지났다(과거형으로만, "
                f"앞으로의 권고·트리거로 쓰지 말 것) — 남은 구간은 {cur}~{end_m}이다."
            )
        elif end_m < cur:
            # 창 전체가 과거(회고 질문) — 걸침 케이스만 표시하던 P6의 사각지대. 과거 창이
            # 미래 예측처럼 서술되던 결함 교정(2026-07-21 데굴님 실로그: '2025년 몇월에
            # 취직에 성공했을까'가 전면 미래 시제로 답변됨).
            note += (
                " 이 기간은 전부 이미 지났다(회고 질문) — 전체를 과거형·추정형으로만 "
                "서술하고 앞으로의 예측·권고·트리거로 쓰지 말 것."
            )
    return ReferenceFrame(
        today=f"{today.isoformat()} ({_WEEKDAY_KO[today.weekday()]})",
        this_year=str(today.year),
        this_year_ganji=ganji.get(str(today.year), ""),
        this_luck_month=cur,
        this_luck_month_detail=current_month_detail or "",
        question_period=period,
        question_period_note=note,
    )


def build_monthly_overview(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    year: int | None = None,
    months: list[str] | None = None,
) -> list[MonthOverviewRow]:
    """12개월 요약(P4 — v1 monthSummaryText 계승). 신호 없는 달도 표기.

    year: 달력상 한 해(1~12월) 요약. months: 명시적 'YYYY-MM' 목록(오늘 기준
    롤링 창 등 달력 연도와 무관한 구간). 둘 중 하나는 제공해야 한다.
    """
    if months is None:
        if year is None:
            raise ValueError("build_monthly_overview: year 또는 months 필요")
        months = [f"{year}-{m:02d}" for m in range(1, 13)]
    ganji = _ganji_lookup(result)
    # 교운(대운 교체) 근접 라벨 — 월운 점수가 cap에 포화돼도 교운일 중심 가중 차이가
    # 표에서 변별되게(2026-06-12 지적). 엔진의 교운 가중 모델과 같은 거리 기준.
    jiao_dates = _exact_jiao_dates(result)
    fav_map = favorability_map(result)
    # 그 달/해의 운 품질 등급(luck_label) — 엔진이 이미 계산한 권위 라벨. 길흉(좋은 달/부담 달)은
    # 사건 밀도가 아니라 이 운 품질이 1차 기준이므로 LLM에 함께 전달한다(길흉=용신/기신 우선).
    luck_grade_by_period: dict[str, str] = {}
    if result.luck_cycles is not None:
        for pl in (*result.luck_cycles.monthly_luck, *result.luck_cycles.yearly_luck):
            if pl.luck_label:
                luck_grade_by_period[pl.label] = pl.luck_label

    def _roles_for(period: str) -> str:
        """그 달 천간·지지의 용기신 역할 '癸水 구신·巳火 희신' — 유불리 변별용."""
        gj = ganji.get(period, "")
        if len(gj) < 2:
            return ""
        try:
            stem_el = str(STEM_ELEMENT[Stem(gj[0])])
            branch_el = str(BRANCH_ELEMENT[Branch(gj[1])])
        except ValueError:
            return ""
        parts = []
        if fav_map.get(stem_el):
            parts.append(f"{gj[0]}{stem_el} {fav_map[stem_el]}")
        if fav_map.get(branch_el):
            parts.append(f"{gj[1]}{branch_el} {fav_map[branch_el]}")
        roles = "·".join(parts)
        # 천간 역할 × 지지 생극(통관/누설)을 본 결실 유불리 마커 — 행에 직접 부착(각주만으론
        # 묻힘). 흉천간 통관이면 순화(↗), 길천간 누설이면 과낙관 경계(⚠)로 대칭 표시.
        marker, _note, _cat = _ganji_result_nuance(
            stem_el, branch_el, fav_map.get(stem_el, ""), fav_map
        )
        if marker:
            roles += f" {marker}"
        return roles

    def _transition_for(period: str) -> str:
        if not jiao_dates:
            return ""
        try:
            mid = (
                date_cls(int(period[:4]), 7, 1)
                if len(period) == 4
                else date_cls(int(period[:4]), int(period[5:7]), 15)
            )
        except ValueError:
            return ""
        d = min(abs((mid - jd).days) for jd in jiao_dates)
        if d <= 45:
            return "대운 교체 정점"
        if d <= 180:
            return "대운 교체기"
        if d <= 365:
            return "대운 교체 영향권"
        return ""

    period_set = set(months)
    # 월당 후보를 모아 상위 2개를 표기 — 한 달에 직업·이사처럼 성격이 다른 신호가 함께
    # 강할 때 1개만 보여주면 다른 신호가 누락된다(2026-06-12: 2025-08 이사 누락 지적).
    by_month: dict[str, list[EventCandidate]] = {}
    for c in candidates:
        if c.period in period_set:  # 월('YYYY-MM') 또는 연('YYYY') 라벨 — 창이 결정
            by_month.setdefault(c.period, []).append(c)
    rows: list[MonthOverviewRow] = []
    month_raw: dict[str, float] = {}  # 달별 최강 후보의 raw — 창 내 상대 순위용
    for period in months:
        # 동점 시 동반 신호 수 우선(이벤트 후보 정렬과 일관).
        cs = sorted(
            by_month.get(period, []),
            key=lambda x: (-x.score, -getattr(x, "raw_total", 0.0), -len(x.signals)),
        )[:2]
        if cs:
            # 사건명은 발생 가능성 순(앞이 우세) — '>'로 우열을 명시(나열 오해 방지).
            label = " > ".join(event_ko(c.event_key) for c in cs)
            month_raw[period] = getattr(cs[0], "raw_total", 0.0)
            # 발현 분기 — 절단 전 그 달 후보 전체에서, 표시되는 상위 사건들(cs)의 계열을
            # 모두 훑어 형제를 도출(1위 단일 초점이면 동점 흔들림에 이직↔이사가 누락됨).
            branch = branch_summary([c.event_key for c in cs], by_month.get(period, []))
            rows.append(
                MonthOverviewRow(
                    period=period,
                    ganji=ganji.get(period, ""),
                    top_event_ko=label,
                    score=cs[0].score,
                    polarity=str(cs[0].polarity),
                    direction=_direction_for(cs[0]),
                    transition=_transition_for(period),
                    luck_roles=_roles_for(period),
                    luck_grade=luck_grade_by_period.get(period, ""),
                    branch_ko=branch or "",
                )
            )
        else:
            rows.append(
                MonthOverviewRow(
                    period=period,
                    ganji=ganji.get(period, ""),
                    top_event_ko="",
                    score=None,
                    polarity="",
                    transition=_transition_for(period),
                    luck_roles=_roles_for(period),
                    luck_grade=luck_grade_by_period.get(period, ""),
                )
            )
    # 창 내 상대 강도 순위(클램프 전 raw 기준, 상위 3위까지) — 톤(점수 cap 포화)이
    # 같아 보여도 '진짜 중요한 달'이 변별되게(절대값보다 상대 순위 신뢰 — docs/07).
    ranked = sorted(month_raw.items(), key=lambda kv: (-kv[1], kv[0]))
    rank_of = {p: i + 1 for i, (p, _v) in enumerate(ranked[:3])}
    for row in rows:
        row.strength_rank = rank_of.get(row.period)
    return rows


def build_llm_input(
    user_question: str,
    intent: IntentJson,
    result: ManseV2Result,
    candidates: list[EventCandidate],
    bundles: list[EvidenceBundle],
    scorer: EventEngineV2,
    call_type: str = "chat_single",
    today: date_cls | None = None,
    monthly_overview: list[MonthOverviewRow] | None = None,
    date_selection: DateSelectionBlock | None = None,
    is_followup_turn: bool = False,
    period_fortune: PeriodFortune | None = None,
    default_period: tuple[str, str] | None = None,
    prior_claims: list[str] | None = None,
    current_month_label: str | None = None,
    current_month_detail: str | None = None,
    structural_context: list[str] | None = None,
    profile_facts: list[str] | None = None,
    subject_blocks: list[SubjectBlock] | None = None,
    relationship_context: RelationshipContext | None = None,
    reserved_tokens: int | None = None,
    overview_mode: bool = False,
) -> LlmInput:
    """축소 → 계약 조립 (T3.4+T3.5). 모든 수치는 입력 시점에 확정 완료.

    P1: today 제공 시 [기준 시점] 동반(LLM은 오늘을 모른다).
    P2: 질문 기간 내 후보 우선 — 기간 외 상위는 참고 블록으로 분리.
    P5·P6(2026-06-12): default_period = 후보 축소용 **유효 창**(호출부가 '오늘이 속한
    달'로 시작을 클램프해 전달) — 질문 창보다 우선한다. 이미 지난 달 후보가 메인에 올라
    미래처럼 서술되는 시점 오류 차단(지난 기간은 out_of_range 배경 + '지남' 마커).
    기준 시점 표시(P1)는 원래 질문 창을 그대로 쓴다.

    current_month_label: 오늘이 속한 절기 월운 라벨(YYYY-MM) — 기준 시점(P6)의 '당월'을
        절기 기준으로 잡도록 build_reference_frame에 전달(미주입 시 양력 폴백).
    """
    graph_scope = [k for k in [intent.event_key, *intent.event_keys] if k is not None]
    # 다중 도메인 질문(예: '이직, 이사')은 secondary 도메인의 대표 이벤트도 후보 범위에 포함한다
    # — event_key 하나만 잡혀 다른 도메인(이사=relocation) 후보가 빠지던 비대칭 차단(2026-06-16).
    for _d in intent.domains:
        _ev = _DOMAIN_PRIMARY_EVENT.get(str(_d))
        if _ev is not None and _ev not in graph_scope:
            graph_scope.append(_ev)
    period_start: str | None
    period_end: str | None
    if default_period is not None:
        period_start, period_end = default_period
    elif intent.time_range is not None:
        period_start = intent.time_range.start
        period_end = intent.time_range.end
    else:
        period_start = period_end = None
    # 월 후보 기간 비교를 절기 경계로 — 질문일이 속한 절기월이 '지난 달'로 밀려나는 결함 보정.
    month_bounds = _month_seolgi_bounds(result)
    recurrence_notes: dict[int, str] = {}
    overview_dropped: list[str] = []
    if overview_mode:
        # 총운형(2026-07-14) — 의미 클러스터링 + 품질 게이트 다양화(위 주석 참조).
        # graph_scope 미적용(멀티도메인 조망), 기간 외 참고 상위는 기존 로직 재사용.
        selected, recurrence_notes, overview_dropped = reduce_overview_candidates(
            candidates, period_start, period_end, month_bounds=month_bounds,
        )
        # 표시 순서 = 강도(점수) 내림차순(2026-07-14 5차) — 선정·life_fit 계층은 불변,
        # 직렬화 순서만 조정. 선정 정렬(fit 우선)을 그대로 두면 최약 후보가 목록
        # 맨 앞에 놓여 LLM 서술 리드를 잡는 문제(조망 지침의 '최강 후보 앞부분
        # 비중' 요구를 구조로 보장).
        _disp = sorted(
            range(len(selected)),
            key=lambda i: (-selected[i].score, selected[i].period),
        )
        selected = [selected[i] for i in _disp]
        recurrence_notes = {
            new_i: recurrence_notes[old_i]
            for new_i, old_i in enumerate(_disp)
            if old_i in recurrence_notes
        }
        _, out_of_range = reduce_with_context(
            candidates, [], period_start, period_end, month_bounds=month_bounds,
        )
        # 선별 결정 trace(관측용) — 라이브 재질문 시 서버 로그에서 원인 확인 가능.
        _overview_log.info(
            "overview_selection selected=%s dropped=%s",
            [
                (str(c.event_key), c.period, c.score,
                 round(getattr(c, "life_fit", 0.0), 3))
                for c in selected
            ],
            overview_dropped,
        )
    else:
        selected, out_of_range = reduce_with_context(
            candidates,
            graph_scope or [b.event_key for b in bundles],
            period_start,
            period_end,
            month_bounds=month_bounds,
        )
    dw_by_year = _daewoon_lookup(result)
    ganji = _ganji_lookup(result)
    day_master = result.pillars.day_master if result.pillars else ""
    fav_map = favorability_map(result)

    # Scoring 1c-β near-tie demotion — 게이트 충족 시 LLM 노출 순서만 제한적 재배열.
    # sub-flag(near_tie_demotion) 기본 off → None → byte-identical. 이후의 인덱스 기반
    # 후처리(신살 채널·rank guard)가 재배열된 selected 와 1:1 정렬되도록 여기서 적용한다.
    from .scoring_operational import near_tie_demotion_order

    _nt_order = near_tie_demotion_order(result, selected, ganji, domain=str(intent.domain.value))
    if _nt_order is not None:
        selected = [selected[i] for i in _nt_order]
        # 반복 신호 노트는 selected 인덱스와 1:1 — 재배열을 따라간다.
        recurrence_notes = {
            new_i: recurrence_notes[old_i]
            for new_i, old_i in enumerate(_nt_order)
            if old_i in recurrence_notes
        }

    # 신살 보조 태그(Phase A-1) — 질문 도메인 기준으로 1회 derive·prune(후보당 ≤3).
    # 점수·랭킹·favorability 불변(순수 enrichment). domain 은 파서 확정 도메인의 대표값.
    # 궁성 정렬이 의미 있는 도메인·이벤트 질문에만 부착한다 — 광역 총운(FORTUNE_OVERVIEW)은
    # 12달 요약으로 이미 토큰이 빽빽해 per-후보 신살이 토큰만 늘리고 변별력은 낮다(토큰 가드).
    _sinsal_eligible = intent.query_type in (
        QueryType.DOMAIN_ANALYSIS,
        QueryType.EVENT_EXPLANATION,
        QueryType.TIMING_SEARCH,
        QueryType.DECISION_SUPPORT,
    )
    sinsal_mods: list[LlmSinsalModifier] = []
    # 신살 기간 채널 색채(Phase B-2, §10-2) — 후보 period 별 한글 노트(발생 가능성 미반영).
    # 토큰 초과 시 serialize_with_guard Tier0 가 캐시 prefix보다 먼저 제거(보조 우선 트림).
    _channel_notes: dict[int, str] = {}
    if _sinsal_eligible:
        _domain = str(intent.domains[0]) if intent.domains else "general"
        _natal_mods = derive_natal_sinsal_modifiers(result, _domain, reference_date=today)
        sinsal_mods = select_llm_sinsal_modifiers(_natal_mods)
        if _sinsal_cfg.SINSAL_CHANNEL_APPLY_ENABLED:
            _rows = apply_sinsal_channel_shadow(result, selected, ganji, domain=_domain)
            for idx, r in enumerate(_rows):
                _note = channel_note_ko(
                    r["favorability_delta"],
                    r["risk_delta"],
                    r["mitigation_delta"],
                    r.get("texture_tags", []),
                )
                if _note:
                    _channel_notes[idx] = _note
    # natal 신살은 도메인 레벨(후보 무관 동일) → 상위 N개 후보에만 부착해 토큰 중복을 막는다.
    _max_cand = _sinsal_cfg.SINSAL_PAYLOAD_MAX_CANDIDATES

    llm_candidates = [
        _to_llm_candidate(
            c,
            ganji,
            dw_by_year,
            day_master,
            fav_map,
            result,
            sinsal_mods if i < _max_cand else None,
            _channel_notes.get(i, "") if i < _max_cand else "",
        )
        for i, c in enumerate(selected)
    ]
    # 총운형 반복 신호 노트(2026-07-14) — 클러스터 대표에 보조 기간·반복 횟수 병기.
    for _ri, _rnote in recurrence_notes.items():
        if 0 <= _ri < len(llm_candidates):
            llm_candidates[_ri].recurrence_note = _rnote
    # Scoring 1c-α rank guard 는 payload 조립 후(_apply_rank_guards)에서 토큰 헤드룸 가드와 함께
    # 적용한다 — 본문을 절단하지 않도록(spec §14-9). 여기서는 본문만 만든다.
    out_candidates = [
        _to_llm_candidate(c, ganji, dw_by_year, day_master, fav_map, result) for c in out_of_range
    ]
    selected_keys = {c.event_key for c in [*selected, *out_of_range]}
    # 근거 경로(v2.2.1) — 이 사용자·이 시점의 **인스턴스 경로**(스코어러 산출)를 우선하고,
    # 정적 그래프 경로는 인스턴스 경로가 없는 이벤트의 폴백으로만 쓴다.
    instance_paths: dict[EventKey, list[list[str]]] = {}
    for c in selected:
        path = scorer.readable_path(c)
        if path and path not in instance_paths.setdefault(c.event_key, []):
            instance_paths[c.event_key].append(path)
    evidence = []
    for b in bundles:
        if b.event_key not in selected_keys:
            continue
        paths = instance_paths.get(b.event_key) or [
            p.readable for p in b.paths[:MAX_PATHS_PER_EVENT]
        ]
        evidence.append(
            LlmEvidence(
                event_key=b.event_key,
                readable_paths=paths[:MAX_PATHS_PER_EVENT],
                contradicts=b.contradicts,
                supports=b.supports,
                interpretation_hints=b.interpretation_hints,
            )
        )
    prohibited = list(_BASE_PROHIBITED)
    for b in bundles:
        if b.event_key in selected_keys:
            prohibited += [p for p in b.prohibitions if p not in prohibited]

    limit = CALL_LIMITS[call_type]
    # 구조 패턴(질문 가변 suffix) — 전체 감지 후 질문 도메인 우선 상위 N 선별(내부/노출 분리).
    _domain_keys: set[str] = set()
    for _d in intent.domains:
        _domain_keys |= _DOMAIN_EVENT_KEYS.get(str(_d), set())
    selected_patterns = select_llm_patterns(
        detect_structure_patterns(result), domains=_domain_keys or None
    )
    # 능동 제안(docs/15 Phase C) — 실질 풀이 질문에서만 도메인 우선 top-2 노출.
    # 용어교육·피드백·감정지원·범위외에는 미노출(제안이 소음이 되는 유형).
    # domains(복수)가 비고 domain(단수)만 채워지는 파서 경로가 있어 둘을 합친다.
    _suggestion_domains = sorted({str(d) for d in intent.domains} | {str(intent.domain)})
    selected_suggestions = (
        select_direction_suggestions(
            detect_direction_suggestions(result), domains=_suggestion_domains
        )
        if intent.query_type not in _NO_SUGGESTION_QUERY_TYPES
        else []
    )

    payload = LlmInput(
        user_question=user_question,
        resolved_intent=intent,
        birth_chart_summary=build_birth_summary(result),
        chart_interpretation=build_chart_interpretation(result),
        calendar_context=build_calendar_context(result, selected, intent),
        event_candidates=llm_candidates,
        out_of_range_candidates=out_candidates,
        overview_dropped_notables=overview_dropped,
        overview_mode=overview_mode,
        # 택일(DATE_RECOMMENDATION)·날짜표가 있는 답에는 '신호 없음' 면책을 넣지 않는다 —
        # 택일 표가 곧 답이라 "뚜렷한 신호가 없습니다"와 날짜 추천이 한 답에서 모순되던 결함
        # 수정(2026-06-16). 사건 점수 공집합은 택일 질의에 무관(길흉이 아니라 실행일을 묻는다).
        no_candidates_in_period=(
            bool(period_start or period_end)
            and not llm_candidates
            and date_selection is None
            and intent.query_type is not QueryType.DATE_RECOMMENDATION
        ),
        reference=(
            build_reference_frame(today, intent, result, current_month_label, current_month_detail)
            if today
            else None
        ),
        structural_context=structural_context or [],
        profile_facts=profile_facts or [],
        subject_blocks=subject_blocks or [],
        relationship_context=relationship_context,
        detected_patterns=selected_patterns,
        direction_suggestions=selected_suggestions,
        is_followup_turn=is_followup_turn,
        prior_claims=prior_claims or [],
        monthly_overview=monthly_overview or [],
        period_fortune=period_fortune,
        date_selection=date_selection,
        evidence=evidence,
        style_rules=LlmStyleRules(
            prohibited=prohibited,
            tone_guide=_TONE_GUIDE,
            llm_instruction=(
                _BASE_INSTRUCTION
                + _PERIOD_FORTUNE_INSTRUCTION.get(period_fortune.fortune_type, "")
                # 계층형 grounding이 실렸을 때만 공통 계층 규칙을 덧붙인다
                # (일·월·연·M15 공용 SSOT — 대상 표현만 블록에서 치환된다).
                + (_PERIOD_HIERARCHY_INSTRUCTION
                   if period_fortune.hierarchy_lines else "")
                + (_LUCK_SINSAL_INSTRUCTION if period_fortune.sinsal_lines else "")
                if period_fortune is not None
                else _BASE_INSTRUCTION
            ),
        ),
        budget=LlmBudget(
            max_input_tokens=limit.max_input_tokens,
            max_output_chars=limit.max_output_chars or limit.max_output_tokens,
        ),
    )
    _apply_rank_guards(payload, result, selected, ganji, intent, call_type, reserved_tokens)
    return payload


def _apply_rank_guards(
    payload: LlmInput,
    result: ManseV2Result,
    selected: list[EventCandidate],
    ganji: dict[str, str],
    intent: IntentJson,
    call_type: str,
    reserved_tokens: int | None,
) -> None:
    """Scoring 1c-α rank guard 태그 — **본문 우선·토큰 헤드룸 가드**(spec §14-9).

    payload 조립 후 적용. 태그가 토큰예산을 넘겨 본문(event_candidates/evidence/excerpts) 재축소를
    유발하지 않도록, 본문 토큰을 측정해 헤드룸 내에서 phrase 실토큰을 순차 차감하며 부착한다
    (부족 시 미부착·max_guards 동적 3→1→0). **순위·.score·reduce 불변·career 한정·APPLY off →
    무동작(byte-identical).**
    """
    import saju_manse_analysis.yongsin.operational_role_config as _sc

    from .scoring_operational import guard_caution_phrase, operational_rank_guards

    guards = operational_rank_guards(result, selected, ganji, domain=str(intent.domain.value))
    if not guards:
        return
    reserve = (
        reserved_tokens if reserved_tokens is not None else _sc.SCORING_OPERATIONAL_HEADROOM_RESERVE
    )
    base = estimate_tokens(serialize_llm_input(payload))  # 태그 없는 본문 토큰
    remaining = CALL_LIMITS[call_type].max_input_tokens - base - reserve
    max_guards = _sc.SCORING_OPERATIONAL_APPLY_COEF["max_guards"]
    attached = 0
    for idx, reason_key in guards:  # 감점 큰 순(정렬됨)
        if attached >= max_guards:
            break
        cn = payload.event_candidates[idx].caution_note
        phrase = guard_caution_phrase(reason_key, cn)
        cost = estimate_tokens(phrase) + 2  # 구분 공백 여유
        if remaining >= cost:  # 본문 우선 — 헤드룸 부족 시 skip(미부착)
            payload.event_candidates[idx].caution_note = f"{cn} {phrase}".strip() if cn else phrase
            remaining -= cost
            attached += 1


def serialize_chart_prefix(summary: BirthChartSummary, ci: ChartInterpretation | None) -> list[str]:
    """고정 prefix([원국·명식 구조]+[명식 해석 자료]) 직렬화 — 대화·보고서 공용.

    사용자별로 바이트 단위 동일해야 한다(provider 캐시 조건) — 가변 값 삽입 금지.
    """
    ug = summary.useful_gods
    lines: list[str] = [
        "[원국·명식 구조 — 엔진 확정값]",
        f"일간 {summary.day_master} · 명식 "
        + " ".join(f"{k}:{v}" for k, v in summary.pillars.items())
        + f" · 공망 {''.join(summary.void_branches) or '없음'} · 강약 {summary.strength}",
        # 용희기구한 5역할 전부(항목 8) — 희신/구신/한신 질문에도 답할 수 있게.
        f"용신 {','.join(ug.yongsin) or '미정'} · 희신 {','.join(ug.heesin) or '없음'} · "
        f"기신 {','.join(ug.gisin) or '미정'} · 구신 {','.join(ug.gusin) or '없음'} · "
        f"한신 {','.join(ug.hansin) or '없음'}",
    ]
    if summary.geokguk:
        lines.append(f"격국: {summary.geokguk}")  # 항목 9
    # 표면 부족 오행의 지장간 잠복 — '존재'와 '작동'을 구분해 잠재·조건부로만 서술
    # (2026-07-03 데굴님 확정 원리: 천간 투출=실제 작동선 / 지장간=숨은 연결선).
    if summary.hidden_latents:
        lines.append(
            "[표면 부족 오행의 잠재 신호 — 지장간] "
            + " / ".join(summary.hidden_latents)
            + " — '완전 부재'가 아니라 숨은 형태로 존재한다. 지장간에만 있는 오행은 "
            "'존재'와 '작동'이 다르다: 천간에 드러난 오행과 동급으로 서술하지 말고 "
            "잠재·조건부로만 다루며, 운에서 같은 오행·천간이 오거나 그 지지가 합·충으로 "
            "자극될 때 살아나는 결로 설명할 것(충 자극 활성은 안정보다 사건화·변동 동반)."
        )
    if summary.flow_note:
        lines.append(
            f"[오행 유통] {summary.flow_note} — 표면에 부족한 오행이 있어도 지장간 통로로 "
            "상생 순환이 이어져 완전히 끊긴 구조는 아니다. 신강약 판정은 그대로 두고"
            "(신강으로 뒤집지 말 것), 스스로 강하게 밀어붙이는 결이라기보다 운·환경 자극을 "
            "받으면 숨은 오행이 작동해 적응력·회복력이 살아나는 구조로 풀 것."
        )
    if ci is not None:
        for pd in ci.pillar_details:
            line = (
                f"{pd.palace_ko} {pd.ganji} · 천간 {pd.stem_ten_god} · "
                f"지지 {pd.branch_ten_god} · 운성 {pd.twelve_stage}"
            )
            if pd.palace_role:
                line += f" · 궁성: {pd.palace_role}"
            if pd.sinsal:
                line += f" · 신살(보조): {','.join(pd.sinsal)}"
            lines.append(line)
        if ci.natal_relations:
            lines.append("원국 관계: " + " / ".join(ci.natal_relations))
        if ci.hap_modes:
            # 합 작용 모드·신뢰도는 엔진 판정 — 단정 말고 신뢰도(확정/조건부/불성)대로 서술하고,
            # 합거된 십성은 그 기간 기능이 약화/전환됨을 반영(HAP_INTERACTION_SPEC).
            lines.append("합 작용(원국): " + " / ".join(ci.hap_modes))
        if ci.ilju_text or ci.excerpts:
            lines += ["", "[명식 해석 자료 — 의미 서술의 근거(점수·판정 변경 금지)]"]
            if ci.ilju_text:
                lines.append(ci.ilju_text)
            for ex in ci.excerpts:
                lines.append(f"{ex.key}: {ex.text}")
        _append_operational_summary(lines, ci.yongsin_operational_summary)
    return lines


def _append_structure_patterns(lines: list[str], patterns: list[DetectedPattern]) -> None:
    """구조 패턴 설명 태그 블록(질문 가변 suffix = 토큰 가드 후순위 절삭 대상).

    질문 도메인 우선 선별(select_llm_patterns(domains=...))된 상위 N. llm_tag 는 구조 라벨
    설명일 뿐 사건·길흉 확정이 아니다(domain_hints 는 후보). 빈 목록이면 생략.
    """
    if not patterns:
        return
    lines += ["", "[구조 패턴 — 의미 설명 태그(구조 라벨일 뿐, 사건·길흉 확정 아님·도메인은 후보)]"]
    for p in patterns:
        lines.append(p.llm_tag)


def _append_operational_summary(lines: list[str], s: YongsinOperationalSummary | None) -> None:
    """작동 역할 요약 compact 블록(원국 기준). None/구형이면 생략 — 깨지지 않음(Phase 5a)."""
    if s is None:
        return
    lines += ["", "[작동 역할 — 원국 기준, 정적 역할과 다를 수 있음(점수·판정 변경 금지)]"]
    yong = f"용신 {s.primary_yongsin}"
    if s.operability is not None:
        # 프리픽스에는 내부 key(no_transmit 등)가 아니라 한국어 압축 표현을 노출(토큰·가독성).
        why = "·".join(s.operability_factors_ko)
        yong += f" (작동성 {s.operability_level} {s.operability}{': ' + why if why else ''})"
    lines.append(yong)
    if s.main_support:
        lines.append("조후보조: " + " · ".join(s.main_support))
    if s.conditional:
        lines.append("조건부: " + " · ".join(s.conditional))
    if s.warnings:
        lines.append("주의: " + " / ".join(s.warnings))


def serialize_llm_input(payload: LlmInput) -> str:
    """계약 → LLM 프롬프트 본문(한국어 사실 서술 — docs/06 '좋은 입력 예' 형태).

    v2.2.1 2층 구조(docs/06): 고정 prefix([원국·명식 구조]+[명식 해석 자료] — 사용자별
    멀티턴 동일, provider 캐시 대상) → 동적 suffix([기준 시점] 이하 — 질문마다 변경).
    고정 prefix에는 날짜 등 가변 값을 넣지 않는다(캐시 무효화 방지).
    지시는 명령형으로, 데이터와 분리한다(표현 원칙 5).
    """
    lines: list[str] = serialize_chart_prefix(
        payload.birth_chart_summary,
        payload.chart_interpretation,
    )
    # MT 결혼 답변 콘텐츠(단계 라인·출력 가드)는 관계 도메인 질문에만 렌더(일반 질문 토큰 절약·
    # 의미 정합 — 일반 월간운에 결혼 가드 불필요). 점수·텔레메트리는 도메인 무관 그대로 동작.
    _intent = payload.resolved_intent
    _rel_focus = _intent.domain.value == "relationship" or "relationship" in {
        str(d) for d in _intent.domains
    }
    lines.append("")
    # ── 동적 suffix (질문마다 변경) ──────────────────────────────
    if payload.reference is not None:
        r = payload.reference
        lines += [
            "[기준 시점]",
            f"오늘: {r.today} · 올해: {r.this_year}년"
            + (f"({r.this_year_ganji})" if r.this_year_ganji else ""),
        ]
        if r.this_luck_month_detail:
            lines += [
                f"현재 절기월(진행 중): {r.this_luck_month_detail}",
                "※ 월운·후보의 'YYYY-MM'은 절기월 라벨(절입 시작 캘린더월 기준)이라 오늘 "
                "캘린더월과 다를 수 있다. 위 '현재 절기월'이 지금 진행 중인 달이며, 라벨 "
                "숫자만으로 과거/미래를 판단하지 말 것 — 진행 중인 달을 '다가오는' 미래로 "
                "서술하지 말 것.",
            ]
        lines += [
            (
                f"질문 기간: {r.question_period} — {r.question_period_note}"
                if r.question_period
                else r.question_period_note
            ),
            "",
        ]
    # 함께 보기(P2a pairwise) — 본인+동반자 대상별 명식을 분리 노출. 상대 명식을 본인과 섞지
    # 않도록 각 대상을 명시한다. 궁합 신호는 아래 [궁합 분석] 보조로 유지.
    if payload.subject_blocks:
        rc = payload.relationship_context
        lines.append("[함께 보기 — 대상별 명식(엔진 확정값)]")
        if rc is not None:
            rel = f" · 관계 {rc.relation_type}" if rc.relation_type else ""
            lines.append(f"조합: {rc.mode}{rel}")
        for sb in payload.subject_blocks:
            _rel = "본인" if sb.role == "self" else (sb.relation_to_user or "동반자")
            who = f"{sb.label}({_rel})"
            # primary(=본문 base)는 원국을 위 [원국·명식 구조]에서 이미 노출 → 참조로만.
            if sb.is_primary:
                cp = f" · 현재 {sb.current_period}" if sb.current_period else ""
                lines.append(f"· {who}: 위 [원국·명식 구조] 참조{cp}")
                continue
            cs = sb.chart
            pil = "/".join(
                cs.pillars[k] for k in ("year", "month", "day", "hour") if cs.pillars.get(k)
            )
            ug = cs.useful_gods
            roles = [
                f"{name} {''.join(vals)}"
                for name, vals in (("용신", ug.yongsin), ("희신", ug.heesin), ("기신", ug.gisin))
                if vals
            ]
            seg = [f"일간 {cs.day_master}", f"원국 {pil}"]
            if cs.strength:
                seg.append(f"신강약 {cs.strength}")
            if roles:
                seg.append(" · ".join(roles))
            if cs.geokguk:
                seg.append(f"격국 {cs.geokguk}")
            if sb.current_period:
                seg.append(f"현재 {sb.current_period}")
            lines.append(f"· {who}: " + " · ".join(seg))
        lines.append(
            "※ 두 사람 각각의 명식으로 함께 풀되, 상대의 간지·용신을 본인 것과 섞지 말 것. "
            "궁합 신호는 아래 [궁합 분석](있으면) 보조로만 참조."
        )
        # P3a — 관계 관점(관계유형별 볼 영역 힌트 + 안전 가드). 점수·우열 아님(관점 제어 전용).
        if rc is not None and (rc.perspective_hints or rc.safety_guards):
            lines.append("[함께 보기 — 관계 관점]")
            if rc.relation_type:
                lines.append(f"관계 유형: {rc.relation_type}(추론 근거 {rc.relation_basis})")
            if rc.perspective_hints:
                lines.append(
                    "주로 살필 영역(관점 힌트 — 점수 아님): " + " · ".join(rc.perspective_hints)
                )
            for g in rc.safety_guards:
                lines.append(f"※ {g}")
        lines.append("")
    # 현재 달(기준 시점) — 절기 기준 당월(this_luck_month) 우선(양력 today[:7]은 절기 경계
    # 직전 한 달 어긋남). 진행 중 절기월 표시(#3)와 '지남' 마커(P6)에 공용으로 쓴다.
    cur_month = (
        (payload.reference.this_luck_month or payload.reference.today[:7])
        if payload.reference
        else ""
    )
    _cur_tag = " ← 현재 진행 중인 절기월(오늘 포함)"
    lines += [
        "[간지달력(압축)]",
    ]
    for d in payload.calendar_context.daewoon:
        period = d.period.replace("~", "-")
        ages = d.age_range.replace("~", "-")
        jiao = f", 교운일 {d.jiao_date}" if d.jiao_date else ""
        lines.append(f"대운 {d.ganji} ({period}, {ages}{jiao})")
    for y in payload.calendar_context.selected_years:
        lines.append(f"세운 {y.year} {y.ganji} (대운 {y.daewoon} 내) — 선별: {y.reason_selected}")
    for m in payload.calendar_context.selected_months:
        _mtag = _cur_tag if cur_month and m.period == cur_month else ""
        lines.append(f"월운 {m.period} {m.ganji}{_mtag}")
    for day in payload.calendar_context.selected_days:
        lines.append(f"일운 {day.date} {day.ganji}")

    def candidate_line(c: LlmEventCandidate) -> str:
        # 점수 숫자·신호 건수는 내부 변수라 노출하지 않는다(항목 5) — 강도는 치환
        # 문장(tone_for_score)으로만 전달해 '100점=확정' 오인을 막는다.
        label = c.event_ko or event_ko(c.event_key)
        # 후보 기간이 현재 진행 중인 절기월이면 표시(#3) — 라벨(YYYY-MM)이 캘린더월과 어긋나
        # 진행 중인 달을 '다가오는' 미래로 오인하지 않게 한다.
        cur_tag = _cur_tag if cur_month and c.period == cur_month else ""
        return (
            f"{label} @ {c.period}({c.ganji}, 대운 {c.daewoon_context}){cur_tag} "
            f"— {tone_for_score(c.score)} · {c.direction or polarity_ko(c.polarity)}"
        )

    def candidate_block(c: LlmEventCandidate, with_notes: bool = True) -> list[str]:
        block = [candidate_line(c)]
        if with_notes and c.favorability_ko:
            # 결과 유불리 — 발생 가능성(강도)과 분리된 길흉('강한 달=좋은 달'이 아님).
            block.append(f"  결과 유불리: {c.favorability_ko}(발생 가능성과 별개)")
        if with_notes and c.signals_ko:
            block.append("  동반 신호: " + " / ".join(c.signals_ko))
        if with_notes and _rel_focus and c.marriage_stage:
            # 관계 단계(MT) — 결혼 확정이 아니라 단계로 표현. 관계 도메인 질문에만(토큰 절약).
            block.append(f"  관계 단계: {c.marriage_stage}(결혼 확정 아님)")
        if with_notes and c.recurrence_note:
            # 총운형 집계 — 같은 계열 신호의 보조 기간·반복 횟수(대표만 남긴 것이 아님).
            block.append(f"  {c.recurrence_note}")
        if with_notes and c.incoming_note:
            block.append(f"  해석: {c.incoming_note}")
        if with_notes and c.amhap_notes:
            # 운 암합 — 보조(물밑·비공식), 단독 결론 금지.
            block.append("  운 암합(보조·물밑): " + " / ".join(c.amhap_notes))
        if with_notes and c.caution_note:
            # 유불리 주의 — 천간 흉신 시기는 발생해도 결실 불리(우호 단정 방지).
            block.append(f"  ⚠유불리: {c.caution_note}")
        if with_notes and c.sinsal_modifiers:
            # 신살 보조 태그(Phase A-1) — 숫자 없는 한글 강도어·효과 태그만. 단독 근거 금지.
            tags = " / ".join(_sinsal_modifier_str(s) for s in c.sinsal_modifiers)
            block.append(f"  신살 보조: {tags}")
        if with_notes and c.layer_grounding is not None and c.layer_grounding.minor_layer_only:
            # D1-B — 후보별 기간 근거. 자격 판정이 아니라 **설명 범위 힌트**다.
            # 상위 지지 쪽 문장은 두지 않는다: 평가 스택에 대운·세운이 있다는 사실을
            # "이 후보를 대운·세운이 지지했다"로 확대하는 오독을 만들기 때문이다.
            # 후보별 provenance(P2-PROV)가 확보되기 전까지 minor-only 쪽만 서술한다.
            layers = " · ".join(
                _LAYER_KO.get(x, x) for x in c.layer_grounding.source_layers
            )
            block.append(
                f"  기간 근거: {layers}에서만 포착 · 대운·세운의 독립 근거 없음 "
                "→ 장기 변화·사건 성사로 단정하지 말고 단기 접촉·조정·마찰·확인 "
                "가능성으로 서술"
            )
        if with_notes and c.sinsal_channel_note:
            # 신살 기간 채널 색채(Phase B-2) — 발생 가능성 아님, 완충/리스크/질감 보조.
            block.append(f"  {c.sinsal_channel_note}")
        return block

    if payload.prior_claims:
        lines.append("")
        lines.append(
            "[이전 답변에서 이미 제시한 엔진 결과 — 아래 사실과 모순 금지: 같은 기간을 "
            "다른 사건·성격으로 뒤집지 말 것. 새 질문의 관점에서 재해석은 가능하나, "
            "이미 말한 시기 판정과 어긋나면 그 차이를 명시적으로 설명할 것]"
        )
        for cl in payload.prior_claims:
            lines.append(f"- {cl}")
    # 총운 모드(2026-07-14 6차 — 데굴님 확정: 재생성 대신 무비용 입력 구조로 유도) —
    # 이벤트 후보·제외 강신호 블록을 월별 요약·유력 달 종합 '뒤'(최종 지시문 인접)로
    # 미룬다. 마지막 데이터 블록이 서술을 지배하는 경향을 역이용해, 월별 표(직업 신호
    # 밀집)가 후보 조망을 덮는 쏠림을 줄인다. 비총운 질문은 기존 위치 그대로.
    _cand_out: list[str] = [] if payload.overview_mode else lines
    # 이벤트 후보 섹션 — 내용이 있을 때만 출력(구조 질문 등 후보 미산출 시 빈 헤더 노출 방지).
    if payload.event_candidates or payload.no_candidates_in_period:
        _cand_out.append("")
        _cand_out.append(
            "[이벤트 후보 — 그 기간에 가능성이 상대적으로 높은 사건의 추측 신호. "
            "기간 전체를 대표하지 않음, 강도는 표현 그대로 인용. 점수·백분율 등 "
            "숫자 수치는 제공되지 않았다 — '98점'류 수치를 지어내 말하지 말 것]"
        )
        if payload.no_candidates_in_period:
            _cand_out.append(
                "질문 기간 내 해당 도메인 후보 없음 — '해당 기간에는 뚜렷한 신호가 "
                "없습니다'로 정직하게 안내할 것(추측 금지)."
            )
        _n_cands = len(payload.event_candidates)
        for _ci, c in enumerate(payload.event_candidates, 1):
            _blk = candidate_block(c)
            if payload.overview_mode and _blk:
                # 순번 체크리스트화 — 누락 인지 강화(총운 한정).
                _blk[0] = f"후보 {_ci}/{_n_cands} · {_blk[0]}"
            _cand_out += _blk
        if payload.overview_mode and _n_cands:
            _cand_out.append(
                f"(총운 서술 체크리스트: 위 {_n_cands}개 후보 각각을 그 시기와 함께 "
                "최소 한 문장씩 답변에 포함할 것. 후보의 성격(갈등·마찰/손실·지출/압박·"
                "부담)과 결과 유불리 '불리'는 완곡하게 뒤집거나 생략하지 말 것 — ⚠ 표시가 "
                "있는 시기를 '긍정적'으로 요약하는 것은 금지)"
            )
        # 결혼 출력 가드(Step 3·4) — 관계 도메인 질문 + MT 단계가 있을 때만 코드 결정 지시문 주입.
        # risk 코드(충·쟁합·기신)면 관계 변화·갈등 가능성 병기 강제(Step 4 분기).
        _mt_cands = [c for c in payload.event_candidates if c.marriage_stage]
        if _mt_cands:
            # 텔레메트리(debug-only·PII 없음·토큰 무관)는 도메인 무관 집계(오픈 후 calibration용).
            emit_marriage_telemetry(
                build_marriage_telemetry(
                    profile=_mtp.ACTIVE_MARRIAGE_PROFILE,
                    enabled_features=_mtp.active_mt_features(),
                    candidates=payload.event_candidates,
                )
            )
            if _rel_focus:
                _stages = {c.marriage_stage for c in _mt_cands}
                _top = "relationship" if "relationship" in _stages else "awareness"
                # B2 — stage_reason(MT 전용) 판정 + 빌드 시 full evidence_path로 계산한
                # marriage_stability_risk(REL_CHUNG_* 등) 병합. 충 기반 marriage_signal이
                # 리스크 병기 없이 서술되던 방향 누수 차단(P0-A 실측).
                _risk = any(
                    c.marriage_stability_risk or has_stability_risk(c.marriage_stage_reason)
                    for c in _mt_cands
                )
                _cand_out.append(
                    marriage_guard_directive(
                        compute_marriage_output_guard(_top, stability_risk=_risk)
                    )
                )
    # 총운 선정 제외 강신호(2026-07-14 not_selected_due_to_limit) — 침묵 금지·승격 금지.
    if payload.overview_dropped_notables:
        _cand_out.append("")
        _cand_out.append(
            "[선정 제외 강신호 — '신호 없음'이 아니다] 아래는 신호 강도가 최상위권이나 "
            "조망 선정에서 밀린 항목이다. 각 항목의 존재를 답변에서 **한 문장으로 짧게** "
            "언급하라('~신호도 강하게 잡혀 있으니 따로 물어보면 자세히 볼 수 있다' 수준). "
            "주요 서사로 승격하거나 상세 풀이하지 말고, 반대로 이 영역을 '신호 없음·"
            "조용함'으로 단정하지도 마라."
        )
        for _dn in payload.overview_dropped_notables:
            _cand_out.append(f"- {_dn}")
    # cur_month(현재 절기월)는 위에서 1회 산출 — 지난 기간 행·후보에 '지남' 마커(P6)에 재사용.
    if payload.out_of_range_candidates:
        lines.append("")
        lines.append("[참고 — 질문 기간 외 흐름(메인 서술 금지, 배경 맥락 전용)]")
        for c in payload.out_of_range_candidates:
            lines += candidate_block(c, with_notes=False)
            c_end = c.period[:7] if len(c.period) >= 7 else f"{c.period}-12"
            if cur_month and c_end < cur_month:
                lines.append("  ※ 위 기간은 이미 지났다 — 과거형으로만, 앞으로의 권고 금지.")
    if payload.monthly_overview:
        lines.append("")
        _ov = payload.monthly_overview
        _span = f"{_ov[0].period}~{_ov[-1].period}" if _ov else ""
        _is_yearly = bool(_ov) and len(_ov[0].period) == 4
        _n_months = sum(1 for r in _ov if len(r.period) == 7)
        _n_years = sum(1 for r in _ov if len(r.period) == 4)
        _is_mixed = bool(_n_months and _n_years)  # 지평 결합 표(앞 N개월 + 연 단위)
        # 기간 단위어 — 연 단위 블록은 '해', 월 단위 블록은 '달'(년월 혼동 방지).
        # 조사: '해'(모음)=는/를, '달'(ㄹ받침)=은/을. '로'·'의'는 양쪽 공통.
        _unit = "해" if _is_yearly else "달"
        _n = "는" if _is_yearly else "은"  # 주격/보조사
        _l = "를" if _is_yearly else "을"  # 목적격
        if _is_mixed:
            lines.append(
                f"[운 흐름 요약 — 앞 {_n_months}개월은 월 단위, 이후 {_n_years}개년은 "
                "연(세운) 단위(값 그대로 사용, 추측 금지)]"
            )
        elif _is_yearly:
            lines.append(
                f"[연도별 흐름 — {_span} {len(_ov)}년(값 그대로 사용, 추측 금지; "
                "점수 낮은 해 = 그 사건의 신호가 거의 없던 해)]"
            )
        else:
            lines.append(f"[월별 요약 — {_span} {len(_ov)}개월(값 그대로 사용, 추측 금지)]")
        # 기반 최고 시기를 이름 박아 별도 지목 — intent 질문(이직 등)에서 그 시기에 해당 사건이
        # 없으면 표 범례 지시가 묻혀 누락되던 문제(2026-06-16). 사건과 무관하게 반드시 한 번 짚게.
        _best = _best_quality_months(_ov)
        if _best:
            lines.append(
                f"※ [기반 최고 {_unit}] {_best} — 질문하신 사건이 이 {_unit}에 약하거나 없더라도, "
                "'기반(전반 운)이 가장 좋은·가장 도움되는 시기'로 반드시 한 번 짚을 것."
            )
        has_transition = False
        has_rank = False
        has_branch = False
        has_grade = False
        for row in payload.monthly_overview:
            row_cmp = cur_month[: len(row.period)] if cur_month else ""
            past_mark = " · 지남(과거형으로만)" if row_cmp and row.period < row_cmp else ""
            # 현재 진행 중인 절기월 표시(#3) — 월 단위 행에서 라벨이 오늘과 같은 절기월이면.
            if cur_month and len(row.period) == 7 and row.period == cur_month:
                past_mark += _cur_tag
            tr_mark = f" · {row.transition}" if row.transition else ""
            has_transition = has_transition or bool(row.transition)
            rank_mark = ""
            if row.strength_rank is not None:
                has_rank = True
                rank_mark = (
                    " · ★기간 내 강도 1위"
                    if row.strength_rank == 1
                    else f" · 기간 내 강도 {row.strength_rank}위"
                )
            roles_mark = f" [{row.luck_roles}]" if row.luck_roles else ""
            # 운 품질 등급 — 길흉(좋은 달/부담 달)의 1차 기준. 사건명 앞에 둬서 묻히지 않게.
            grade_mark = f" 〈{row.luck_grade}〉" if row.luck_grade else ""
            has_grade = has_grade or bool(row.luck_grade)
            # 발현 분기 — 같은 계열에서 함께 점수화됐으나 표(top-2)에서 잘린 형제(예: 이사)를
            # 모든 달에서 노출(top-3 종합에만 의존하지 않게). 압축형, 안내는 표 하단에 1회.
            branch_mark = f" · 분기 {row.branch_ko}" if row.branch_ko else ""
            has_branch = has_branch or bool(row.branch_ko)
            if row.score is not None:
                # 분기(형제 사건)를 사건명 바로 뒤로 — 줄 끝에 묻혀 무시되는 것 방지(이직↔이사).
                lines.append(
                    f"{row.period} {row.ganji}{grade_mark}{roles_mark}: {row.top_event_ko}"
                    f"{branch_mark} · {row.direction or polarity_ko(row.polarity)} "
                    f"→ {tone_for_score(row.score)}"
                    f"{rank_mark}{tr_mark}{past_mark}"
                )
            elif not row.ganji:
                lines.append(f"{row.period}: 입춘 전 — 전년 세운 구간(월운 정보 없음)")
            else:
                lines.append(
                    f"{row.period} {row.ganji}{grade_mark}{roles_mark}: 특이 신호 없음"
                    f"{tr_mark}{past_mark}"
                )
        lines.append(
            f"(표 읽는 법: 사건명은 그 {_unit} 발생 가능성 순 — '>' 앞이 우세. [간지 역할]은 "
            f"유불리 — 천간이 구신·기신인 {_unit}{_n} 사건이 발생해도 계약·결실·실속에 불리할 수 "
            f"있으니 '좋은 {_unit}'로 단정하지 말 것(발생 강도와 유불리를 구분). 단 마커가 "
            "'↗통관 순화'면 흉천간이 지지 용·희신을 생해 순화된 것(검토 시기 아님, 과낙관만 경계), "
            f"'⚠천간 길신 누설'이면 길천간이 지지로 누설·피극돼 실속이 약화된 것"
            f"(좋은 {_unit} 단정 금지)."
            + (
                f" 〈…〉는 그 {_unit}의 운 품질 등급으로 길흉(좋은 {_unit}/부담스러운 {_unit})의 "
                f"1차 기준이다 — 좋은 {_unit}{_n} 사건 밀도가 아니라 이 등급('강한 용신운'>"
                "'용신운(부분)'>'혼합'>'기신운')으로 판단하고, 사건(이직·이사 등)은 그 위에 "
                f"십성으로 얹어 '무슨 일'을 설명한다. '강한 용신운' {_unit}{_n} 두드러진 사건이 "
                f"없어도 기반이 가장 좋은(가장 도움되는) {_unit}로 짚을 것."
                if has_grade
                else ""
            )
            + (
                " 표현 강도가 같아 보여도 '기간 내 강도 N위'가 실제 상대 순위 — "
                f"가장 유력한 {_unit}{_n} 1위부터 지목하되 유불리를 함께 밝힐 것."
                if has_rank
                else ""
            )
            + (
                " 교운 표기는 '정점'에 가까울수록 대운 교체의 갑작스러운·비자발적 "
                f"전환 에너지가 강함 — 동급이면 교운 근접 {_unit}{_l} 우선."
                if has_transition
                else ""
            )
            + (
                " '분기'는 같은 계열(이동·재물·학업 등)에서 같은 에너지가 갈릴 수 있는 형제 "
                "사건이다 — 무작정 둘 다 나열하지 말고, 사용자의 상황·질문 맥락에서 성립 불가능한 "
                "형제는 배제해 가능한 쪽으로 좁혀 해석하라. 예: 현재 직장이 없으면 '이직'은 성립할 "
                f"수 없어 같은 이동 에너지는 '이사'가 된다. 질문이 특정 사건(재취업 등)을 묻는데 "
                f"그 {_unit}의 우세 신호가 다른 형제(이사)라면, 그 {_unit}{_l} 질문 사건의 답으로 "
                "단정하지 말고 맥락상 실제 발현됐을 형제 사건으로 풀이하라."
                if has_branch
                else ""
            )
            + ")"
        )
        # 유력 달 종합 판정(2026-06-12) — 순위·우세 사건·유불리·교운이 표·후보에
        # 흩어져 LLM이 일부를 누락하는 문제를 엔진 사전 종합으로 차단. 답의 골자.
        ranked_rows = sorted(
            (r for r in payload.monthly_overview if r.strength_rank is not None),
            key=lambda r: r.strength_rank or 9,
        )
        if ranked_rows:
            asked_ko = (
                event_ko(payload.resolved_intent.event_key)
                if payload.resolved_intent.event_key is not None
                else ""
            )
            # 총운 조망에선 이벤트 후보가 서술 골격 — 유력 달 순위가 조망 지침을
            # 눌러 직업 등 특정 영역 쏠림을 만들던 지시문 충돌 해소(2026-07-14 5차).
            lines.append(
                "[유력 달 종합 — 이 순위는 '시기 짚기' 참고 자료다. 총운·조망 답변의 "
                "서술 골격은 [이벤트 후보] 목록이며 이 달 순위가 서술 비중 기준이 "
                "아니다. 아래 달을 서술할 때는 우세 사건·유불리·주의를 그대로 함께 "
                "밝힐 것]"
                if payload.overview_mode
                else "[유력 달 종합 — 엔진 확정 골자. 각 달을 서술할 때 아래의 우세 "
                "사건·유불리·주의를 반드시 그대로 함께 밝힐 것(누락 금지)]"
            )
            for mr in ranked_rows:
                events = mr.top_event_ko.split(" > ")
                dominant = events[0] if events else ""
                second = f"(2순위 {events[1]})" if len(events) > 1 else ""
                bits = [
                    f"우세 사건 '{dominant}'{second}",
                    f"성격 {mr.direction or polarity_ko(mr.polarity)}",
                ]
                if mr.luck_grade:  # 운 품질 등급 — 길흉 1차 기준(사건 강도와 별개)
                    bits.append(f"운 품질 {mr.luck_grade}")
                # 질문 사건과 그 달 우세 사건이 다르면 명시 — 사건명 단정 오류 방지
                # (regression_2025_08: 甲申월은 이사 우세, 이직은 동반 2순위).
                if asked_ko and dominant and dominant != asked_ko:
                    bits.append(
                        f"※ 이 달의 주된 신호는 '{dominant}' — "
                        f"질문하신 '{asked_ko}'은(는) 동반 신호로만 서술할 것"
                    )
                if mr.branch_ko:
                    # 골자는 '누락 금지'라 형제 판별 지시를 여기에 직접 — 표 하단 범례만으론
                    # 우세 사건명에 고정돼 형제(이사 등)가 무시되는 실로그 결함(regression_2025_08).
                    bits.append(
                        f"발현 분기: {mr.branch_ko} — 우세 사건명에 고정하지 말 것, 같은 계열 "
                        "형제(이직↔이사 등)가 실제 발현일 수 있으니 사용자 맥락(직업·거주 "
                        "변화)으로 판별해 단정하지 말 것"
                    )
                if mr.luck_roles:
                    bits.append(f"간지 역할 {mr.luck_roles}")
                if mr.transition:
                    bits.append(mr.transition)
                line = f"{mr.strength_rank}위 {mr.period} {mr.ganji}: " + " · ".join(bits)
                roles_txt = mr.luck_roles or ""
                if "계약·결실 불리" in roles_txt:
                    line += (
                        " — 발생 신호는 강하나 결실·실속이 불리한 '검토월' 성격"
                        "(이 달을 우호적으로만 서술 금지)"
                    )
                elif "통관 순화" in roles_txt:
                    line += (
                        " — 천간이 흉신이나 지지 용·희신을 생하는 통관(관인상생)으로 순화 — "
                        "우호적이나 천간 흉신이라 과한 낙관은 금물"
                    )
                elif "누설" in roles_txt:
                    line += (
                        " — 천간은 길신이나 지지로 누설·피극되어 실속이 약화 — "
                        "'좋은 달'로 단정하지 말 것"
                    )
                lines.append(line)
    # 총운 모드 — 미뤄둔 이벤트 후보·제외 강신호 블록을 여기(월별·유력 달 뒤,
    # 최종 지시문 인접)에 삽입한다. 월별 표가 비어도 반드시 방출된다.
    if payload.overview_mode and _cand_out is not lines and _cand_out:
        lines += _cand_out
    if payload.period_fortune is not None:
        pf = payload.period_fortune
        header, pillar_label = _PERIOD_FORTUNE_HEADER.get(pf.fortune_type, ("기간 총운", "운"))
        lines.append("")
        lines.append(
            f"[{header} — {pf.period_label} {pf.ganji} · {pillar_label}·슬롯(엔진 확정값)]"
        )
        if pf.solar_month_note:
            lines.append(f"절기월 안내: {pf.solar_month_note}")
        lines.append(f"{pillar_label}: {pf.pillar_line}")
        if pf.luck_label or pf.luck_summary:
            lines.append(f"운 요약: {pf.luck_label} — {pf.luck_summary}")
        if pf.hierarchy_lines:
            # P1 계층형 grounding ON — 관계는 이쪽 하나만 쓴다(기존 형충회합 줄과
            # 동시 노출 금지: 같은 관계가 두 표현으로 들어가면 사실이 갈라진다).
            lines += pf.hierarchy_lines
        else:
            for rl in pf.relation_lines:
                lines.append(f"형충회합: {rl}")
        for sl in pf.sinsal_lines:
            lines.append(sl)
        if pf.gongmang:
            lines.append("공망: " + ", ".join(pf.gongmang))
        for slot in pf.slots:
            lines.append(f"· {slot.name}({tone_for_score(slot.score)}): {slot.summary}")
        # P0(2026-07-27) — 관계 사실을 자유 작문에서 빼고 엔진 확정 문장으로 제공한다.
        # 금지 문구만 나열하면 LLM이 '寅亥合은 원래 木'이라는 자체 지식으로 엔진의
        # 化 불성 판정을 덮는다. 확정 문장을 주는 쪽이 최초 오류율을 더 크게 낮춘다.
        lines += canonical_claim_lines(pf.relation_semantics)
        lines += pf.hierarchy_appendix
    if payload.date_selection is not None:
        ds = payload.date_selection
        lines.append("")
        lines.append(f"[택일 결과 — {ds.purpose_ko} · {ds.period} · 엔진 확정값]")
        for drow in ds.rows:
            notes = " · ".join(drow.notes) if drow.notes else ""
            # 택일 점수·내부 enum은 노출 금지 — 추천 등급을 한글 라벨로만 노출(항목 5).
            lines.append(
                f"{drow.date}({drow.weekday}) {drow.ganji} "
                f"[{recommendation_ko(drow.recommendation)}]" + (f" — {notes}" if notes else "")
            )
        for avoid in ds.avoid[:5]:
            lines.append(f"회피일 {avoid.get('date')} — {avoid.get('reason')}")
        if ds.directions:
            top = [d for d in ds.directions if d.get("fit", 0) >= 0.7] or ds.directions[:2]
            label = ", ".join(
                f"{d.get('direction')}({d.get('note') or d.get('element')})" for d in top
            )
            lines.append(f"방위: {label}")
        if ds.hour_fits:
            best = [h for h in ds.hour_fits if h.get("fit", 0) >= 0.8]
            if best:
                slots = ", ".join(f"{h.get('branch')}시({h.get('time_range')})" for h in best)
                lines.append(f"시간대: {slots}")
        for warning in ds.group_warnings:  # 그룹(다인) 이사 — 구성원 충돌·경고
            lines.append(f"구성원 주의: {warning}")
        if ds.relocation_reasons:  # 이사 십성 이유분류(유형 라벨 — 실제 발생 단정 금지)
            lines.append(
                "[이사 이유·집 성격 — 십성 분류. 천간=명분(이유)/지지=현장(집·지역), "
                "대운=장기 배경·세운=올해 대표·월운=그 달 발동. 유형 분류일 뿐 실제 이사 "
                "발생 여부는 별개이며 단정 표현 금지]"
            )
            for reason in ds.relocation_reasons:
                lines.append(f"- {reason}")
        for caution in ds.cautions:
            lines.append(f"주의: {caution}")
    if payload.structural_context:
        # 구조 해석 블록(질문 도메인 맞춤 — 이미 누출 안전 한글). 개인 풀이의 구조 근거로 활용.
        lines.append("")
        lines += payload.structural_context
    if payload.profile_facts:
        # 물상 사실 맥락(직업·혼인·거주 등) — 상황 구체화 근거. 점수·판정 불변.
        lines += ["", "[사용자 정보 — 입력한 사실 맥락(상황 구체화용, 판정 불변)]"]
        lines += payload.profile_facts
    _append_structure_patterns(lines, payload.detected_patterns)
    # 능동 제안 — 세운 의존이라 동적 suffix 전용(프리픽스 캐시 불변). 비었으면 무헤더.
    lines += format_direction_suggestion_lines(payload.direction_suggestions)
    if payload.evidence:  # 근거 경로 — 후보·증거 있을 때만(구조 질문 등 빈 헤더 방지).
        lines.append("")
        lines.append("[근거 경로]")
    for e in payload.evidence:
        label = _clean_evidence_text(event_ko(e.event_key))
        for path in e.readable_paths:
            steps = [s for step in path if (s := _clean_evidence_text(step))]
            # 경로 끝 단계가 이벤트 라벨과 같으면 'label:' 표기와 중복이라 제거.
            if steps and steps[-1] == label:
                steps = steps[:-1]
            if steps:
                lines.append(f"{label}: " + " → ".join(steps))
        if e.supports:
            cleaned_sup = [s for x in e.supports if (s := _clean_evidence_text(x))]
            if cleaned_sup:
                lines.append(f"{label} 보조 근거: {', '.join(cleaned_sup)}")
        if e.contradicts:
            cleaned_contra = [s for x in e.contradicts if (s := _clean_evidence_text(x))]
            if cleaned_contra:
                lines.append(f"{label} 반대 근거: {', '.join(cleaned_contra)}")
        if e.interpretation_hints:
            cleaned_hints = [s for x in e.interpretation_hints if (s := _clean_evidence_text(x))]
            if cleaned_hints:
                lines.append(f"{label} 해석 힌트: {', '.join(cleaned_hints)}")
    lines.append("")
    lines.append("[지시]")
    lines.append(payload.style_rules.llm_instruction)
    if payload.chart_interpretation is not None:
        lines.append(_MEANING_INSTRUCTION)
        lines.append(_AUXILIARY_INSTRUCTION)
        lines.append(_SINSAL_POSITION_INSTRUCTION)
        lines.append(_ORIGIN_INSTRUCTION)
        lines.append(_STRUCTURE_INSTRUCTION)
        if payload.chart_interpretation.yongsin_operational_summary is not None:
            lines.append(_OPERATIONAL_INSTRUCTION)
        lines.append(_REVERSAL_INSTRUCTION)
        lines.append(_HARMONY_INSTRUCTION)
        lines.append(_BANGHAP_INSTRUCTION)
    if payload.detected_patterns:
        lines.append(_STRUCTURE_PATTERN_INSTRUCTION)
    if payload.direction_suggestions:
        lines.append(DIRECTION_SUGGESTION_INSTRUCTION)
    if payload.profile_facts:
        lines.append(_PROFILE_FACTS_INSTRUCTION)
    if payload.event_candidates:
        lines.append(_MATRIX_INSTRUCTION)
        lines.append(_SCOPE_INSTRUCTION)
        lines.append(_HIERARCHY_INSTRUCTION)
        if any(c.sinsal_modifiers for c in payload.event_candidates):
            lines.append(_SINSAL_MODIFIER_INSTRUCTION)
    if payload.reference is not None:
        lines.append(_REFERENCE_INSTRUCTION)
    lines.append(_LABEL_INSTRUCTION)
    if payload.out_of_range_candidates:
        lines.append(_OUT_OF_RANGE_INSTRUCTION)
    if payload.date_selection is not None:
        lines.append(_DATE_TABLE_INSTRUCTION)
    lines.append(_SELF_CHECK_INSTRUCTION)
    if payload.is_followup_turn:
        lines.append(_FOLLOWUP_INSTRUCTION)
    lines.append(_FORMAT_INSTRUCTION)
    lines.append(_LENGTH_INSTRUCTION)
    lines.append("금기 표현: " + ", ".join(payload.style_rules.prohibited))
    if payload.persona.prompt_block:
        lines.append(payload.persona.prompt_block)
    lines.append(f"[질문] {payload.user_question}")
    return "\n".join(lines)


def _drop_sinsal_aux(payload: LlmInput) -> LlmInput:
    """신살 보조 텍스트(modifier·채널 색채)를 후보에서 제거한 payload 사본(트림 Tier0).

    신살이 없으면 동일 객체를 그대로 반환(불필요한 복사 회피 → 캐시·byte-identical 보존).
    """
    if not any(c.sinsal_modifiers or c.sinsal_channel_note for c in payload.event_candidates):
        return payload
    return payload.model_copy(
        update={
            "event_candidates": [
                c.model_copy(update={"sinsal_modifiers": [], "sinsal_channel_note": ""})
                for c in payload.event_candidates
            ],
        }
    )


def serialize_with_guard(
    payload: LlmInput, call_type: str = "chat_single", reserve_tokens: int = 0
) -> tuple[str, int]:
    """직렬화 + 토큰 가드(docs/09 8장) — 초과 시 후보·근거를 줄여 1회 재축소.

    Args:
        payload: 직렬화 대상 입력.
        call_type: 한도표 키.
        reserve_tokens: 직렬화 본문 뒤에 호출부가 덧붙이는 고정 오버헤드(시스템 프롬프트·
            후행 지시문)를 위한 예약분. payload+예약분이 상한을 넘으면 재축소가 발동하므로,
            후행 텍스트까지 더한 실제 총 입력이 한도에 맞게 줄어든다.

    Returns:
        (프롬프트 본문, 측정 토큰). 재축소 후에도 초과면 TokenBudgetExceeded 전파.
    """
    guard = LLMCallGuard(call_type)
    text = serialize_llm_input(payload)
    try:
        return text, guard.check_input(text, reserve_tokens=reserve_tokens)
    except TokenBudgetExceeded:
        pass
    # Tier 0(트림 우선순위) — 신살 보조 텍스트(modifier·채널 색채)를 캐시 prefix보다 **먼저** 제거.
    # 신살은 보조 레이어라 토큰 압박 시 가장 먼저 버린다 → 무거운 질문에서도 고정 prefix(excerpt)·
    # 후보 본문은 보존돼 캐시 불변(test_fixed_prefix)·풀이 품질을 지킨다(§10-2).
    no_sinsal = _drop_sinsal_aux(payload)
    text = serialize_llm_input(no_sinsal)
    try:
        return text, guard.check_input(text, reserve_tokens=reserve_tokens)
    except TokenBudgetExceeded:
        pass
    # Tier 1 — 그래도 초과면 본문 축소(후보·근거·해석 발췌). 신살은 이미 제거된 상태.
    ci = no_sinsal.chart_interpretation
    shrunk = no_sinsal.model_copy(
        update={
            "event_candidates": no_sinsal.event_candidates[:3],
            "evidence": [
                e.model_copy(update={"readable_paths": e.readable_paths[:1]})
                for e in no_sinsal.evidence[:3]
            ],
            # 해석 발췌도 절반으로 — 일주 본문·명식 구조는 보존(풀이 품질 우선).
            "chart_interpretation": (
                ci.model_copy(update={"excerpts": ci.excerpts[:4]}) if ci else None
            ),
        }
    )
    text = serialize_llm_input(shrunk)
    return text, guard.check_input(text, reserve_tokens=reserve_tokens)
