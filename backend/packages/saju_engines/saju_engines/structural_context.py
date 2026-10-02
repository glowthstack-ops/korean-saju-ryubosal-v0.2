"""구조 해석 블록 — 리포트·챗 공용 (v2.2, 2026-06-16).

원국 횡재 그릇·결혼/자산 자원·건강 취약·부귀 지향·연운 시대 기운을 **누출 안전한 한글**로
직렬화하는 단일 소스다. **내부 변수명(영문 그룹·band 코드 등)·원시 점수·퍼센트를 본문에 노출하지
않는다**(LLM 누출 방지 — 사용자 확정 2026-06-16). 리포트(_ReportData)·챗(chat_service)이 동일
포맷터를 호출해 표면화 일관성을 유지한다.
"""

from __future__ import annotations

from saju_shared_types.daewoon_progression import DaewoonProgressionProfile
from saju_shared_types.external_impression import ExternalImpressionProfile
from saju_shared_types.health_vulnerability import HealthVulnerabilityProfile
from saju_shared_types.intent import Domain, IntentJson, QueryType
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.marriage_resource import MarriageResourceProfile
from saju_shared_types.preparation_context import PreparationContext
from saju_shared_types.wealth_capacity import WealthCapacity
from saju_shared_types.wealth_status_lean import WealthStatusLean

from .era_energy import era_curated_note, era_energy_profile
from .health_vulnerability import health_risk_windows
from .marriage_age_prior import analyze_marriage_age_prior
from .marriage_timing_profile import active_marriage_aux
from .relationship_relation_labels import relation_summary_ko

# MT6 혼기 band → 한글 경향(static prior·특정 시기 아님).
_MARRIAGE_AGE_BAND_KO = {
    "early": "이른 인연 경향", "normal": "사회 초·중반(적령) 경향",
    "spouse_palace_direct": "배우자궁 직접(본인 주도) 구조", "late": "만혼 경향",
}

_CAPACITY_BAND_KO = {"strong": "강", "moderate": "중", "weak": "약"}
_GENDER_KO = {"female": "여성", "male": "남성"}
# 배우자성 프레이밍 — 성별 기준(남=재성=배우자, 여=관성=배우자). 헤더가 '관성=배우자'(여성 고정)로
# 하드코딩돼 남성 명식에 여성 기준이 들어가던 오역 교정(2026-06-22 데굴님 지적).
_SPOUSE_FRAME_KO = {
    "female": "관성=배우자(남편)·재성=시댁·물질 환경",
    "male": "재성=배우자(처)·물질 환경, 관성=직위·자식(배우자 아님)",
    "unknown": "배우자성은 성별 기준(남=재성·여=관성)",
}
_LEAN_KO = {
    "parental": "집안·부모 기반",
    "spouse_family": "결혼 후 물질 환경(여성 명식은 시댁 재력 잠재)",
    "self": "자수성가(식상생재) 경향",
}
_GEOKSIN_GROUP_KO = {
    "wealth": "재성", "officer": "관성", "output": "식상",
    "resource": "인성", "peer": "비겁",
}


def spouse_star_directive(gender: str | None) -> str:
    """배우자성 성별 가드 — 남=재성·여=관성. 반대 성별 기준 해석을 막는다(chat·report 공용).

    헤더 외에도 결혼·관계 풀이에 명시 가드를 덧대 '남성에게 관성=배우자' 같은 여성 기준 오역을
    차단한다(2026-06-22 데굴님 지적). 미상이면 특정 배우자성을 단정하지 않도록 안내한다.

    Args:
        gender: 'male'/'female'/'unknown'/None.

    Returns:
        성별별 배우자성 가드 지시문(LLM 입력용).
    """
    if gender == "male":
        return (
            "[배우자성 — 성별 기준]\n주인공은 남성이다. 남성의 배우자(아내)는 재성(정재·편재)이며 "
            "결혼·배우자운은 재성을 중심으로 본다. 정관·편관은 남성에게 직위·명예·자식(자녀)이지 "
            "배우자가 아니다 — '관성=배우자', '여성에게는…' 같은 여성 기준 해석을 남성 사주에 "
            "적용하지 말 것. 결혼 시기는 재성의 등장·합, 비식재 흐름, 일지(배우자궁) 자극으로 보라."
        )
    if gender == "female":
        return (
            "[배우자성 — 성별 기준]\n주인공은 여성이다. 여성의 배우자(남편)는 관성(정관·편관)이며 "
            "결혼·배우자운은 관성을 중심으로 본다. 재성은 시댁·물질 환경이다 — '재성=배우자(아내)' "
            "같은 남성 기준 해석을 여성 사주에 적용하지 말 것. 결혼 시기는 관성의 등장·합, 재생관, "
            "일지(배우자궁) 자극으로 설명하라."
        )
    return (
        "[배우자성 — 성별 기준]\n배우자성은 성별에 따라 다르다(남=재성, 여=관성). 주인공 성별이 "
        "확정되지 않았으니 특정 배우자성을 단정하지 말고 성별 기준을 일반론으로만 언급하라."
    )


# 공망 해석 규칙 — 원국 공망은 배경값이며 운이 충·합·전실로 자극할 때만 발동(CLAUDE.md 원칙 1:
# 공망 활성화는 엔진 계산, LLM 임의 판단 금지). LLM이 발동 신호 없이 '공망이 스친다' 류로 지어내던
# 결함 차단(2026-07-01 데굴님 지적: 7/2 일운은 공망 미발동인데 공망 영향을 서술).
GONGMANG_ACTIVATION_DIRECTIVE = (
    "[공망 해석 규칙 — 필수]\n"
    "원국 공망(명식 헤더의 '공망 XX')은 배경값일 뿐이다. 공망은 특정 시점의 운(대운·세운·월운·"
    "일운)이 그 공망 지지를 충·합·전실로 자극할 때만 발동하며, 엔진이 발동을 판정하면 해당 시점 "
    "블록에 '공망: 공망발동/전실/해소 …' 신호로 표기한다. **그 발동 신호가 없는 시점의 풀이에서는 "
    "공망의 영향·부작용을 언급하지 말 것** — '공망이 스친다/기대를 낮춰라' 같은 임의 서술 금지. "
    "발동 신호가 있을 때만 그 신호(충/합/전실)를 근거로 공망 작용을 설명하라. "
    "공망 충발의 엔진 정의는 '발현 지연 + 변동성 보조'다(방향·사건 성립 판정 불변) — 공망 "
    "충발 하나만으로 실패·무산·공허한 결말을 단정하지 말 것. 독립된 다른 근거가 있을 때 "
    "실현 시점의 불확실성·지연을 보조 설명하는 용도로만 쓰라(2026-07-22 데굴님 확정 불변식). "
    "신호별 방향(2026-08-21 확정 — 三命通會 '合則不能空'): '공망 전실(실체화)'는 공망지가 "
    "채워져 실체화되는 신호, '공망 해소·접촉(합)'은 공망의 차단막이 약해지며 **억제되어 있던 "
    "그 지지·십성·궁위의 본래 작용이 현실화될 수 있는** 신호다 — 이 두 신호를 '공허해진다·"
    "지연된다·공망과 겹친다'로 서술하는 것은 방향 오역이므로 금지. 살아난 대상의 결과가 "
    "길한지 흉한지는 그 글자의 십성·용희기구한으로 별도 판정하라(합 자체는 길흉이 아니다). "
    "또한 운 글자가 공망지와 합·충 관계라는 이유로 그 운 글자 자체를 '공망'이라 부르지 말 것. "
    "공망 글자와 궁위는 명식 헤더의 '공망 XX'와 신호에 표기된 글자 쌍(예: '운 申이 공망지 "
    "巳(시지)와 합')을 그대로 쓰고, 다른 지지를 공망으로 지목해 지어내지 말 것."
)


# 인연 출처(기존 vs 새 인연) — '주변 사람이야 새로운 사람이야?' 류 질문 근거(공용).
PARTNER_SOURCE_DIRECTIVE = (
    "[인연 출처 — 기존 지인 vs 새 인연]\n"
    "'주변·아는 사람이냐 새로운 사람이냐'를 물으면: 배우자운이 합(合)·도화로 들면 가깝고 익숙한 "
    "인연(주변·소개·재회) 경향, 충(沖)·역마로 들면 외부·먼 곳·이동 중의 새로운 인연 경향으로 "
    "설명하라. 다만 사주로 둘 중 하나를 확정할 수는 없으니 단정하지 말고 가능성·경향으로만 안내하라"
    "(어느 쪽이든 열어두고, 본인의 활동 반경을 넓히는 실천을 함께 권할 것)."
)


# 운에 따른 일시 취향 변동(D) — 운 십성이 평소 일지 취향과 다르면 일시 끌림, 운 빠지면 흔들림(공용).
TENDENCY_SHIFT_DIRECTIVE = (
    "[운에 따른 일시 취향 변동 — 주의]\n"
    "운(대운·세운)에서 평소 일지 취향과 다른 십성, 특히 인성(기대고 존경할 사람)·식상(자극·표현이 "
    "강한 사람)이 강하게 들면 평소와 다른 타입에 일시적으로 끌릴 수 있다. 이는 운의 일시 작용이라 "
    "그 기운이 빠지면 관계가 흔들리기 쉽다 — '운에 취해' 급히 정하지 말고 평소 취향과의 차이를 "
    "인지하도록 안내하라(불안 조장·단정 금지, 경향으로만)."
)


# 연애운·결혼운 통합 관점(P2, 2026-07-21 영상 자료) — '연애운 없으면 결혼운 좋다' 류 속설
# 이원론 교정. 배우자·연애의 중심 자리는 동일하게 일지(배우자궁)라는 관점만 제공(판정 불변).
LOVE_MARRIAGE_UNIFIED_DIRECTIVE = (
    "[연애운·결혼운 통합 관점] 연애운과 결혼운을 별개의 운으로 나눠 '연애운은 없지만 결혼운은 "
    "좋다' 식 이원 구도로 답하지 말 것 — 연애와 결혼 모두 중심 자리는 일지(배우자궁)이며, "
    "일지 십성 취향(끌리는 결)대로 만나 관계를 유지하는 것이 두 영역 공통의 기준이다. 만남·"
    "결혼의 시기 신호는 제공된 엔진 후보로만 말하고, 사용자가 그 속설 전제를 꺼내면 반박·훈계 "
    "없이 이 관점으로 부드럽게 정리할 것."
)

# 연애 자기인식(C) — 사주에 드러난 이상형 취향을 본인이 인정 않으면 연애가 어긋난다는 앵글(공용).
RELATIONSHIP_SELF_AWARENESS_DIRECTIVE = (
    "[연애 자기인식 — 너 자신을 알라]\n"
    "사주에 드러난 '배우자 취향(이상형)'은 본인이 평소 인정하지 않을 수 있다(예: '성향·마음을 "
    "본다'면서 실제로는 외모·조건에 끌리는 결). 제공된 이상형 경향을 부정·미화하지 말고, 본인이 "
    "실제로 끌리는 타입을 담백하게 받아들이도록 안내하라 — 연애가 어긋나는 흔한 이유가 자기 취향을 "
    "모르거나 인정 않는 데 있다. 낙인·단정 금지, '경향'으로만 따뜻하게 풀 것."
)


# ── 상담 사례 파생 서술 디렉티브(P0) — doc/v2_2/cases/1980_1122_job_report_case.md §5
# (2026-07-03 데굴님 승인). 전부 '서술 방식' 지시이며 점수·날짜·간지·판정에 영향을 주지 않는다
# (원칙 1·12). 채팅·리포트 공용.
CONCLUSION_FIRST_DIRECTIVE = (
    "[결론 선제시] 직업·사업·이직·자금·결혼 등 선택형 질문에는 권하는 방향(결론)을 먼저 한두 "
    "문장으로 제시한 뒤 근거를 설명하라. 예: '지금은 사업을 크게 벌리기보다, 직장 기반을 "
    "유지하면서 부업형 수익화를 병행하는 쪽이 더 안전합니다.' 결론도 단정이 아니라 권고·방향 "
    "표현으로 말할 것."
)

KEYWORD_COMBO_TRANSLATION_DIRECTIVE = (
    "[활동 키워드 번역] 용신·십성·신살·격국 신호를 '화 기운이 좋다' 같은 추상어로 끝내지 말고, "
    "위 [활동 키워드] 블록의 키워드를 2~4개 조합해 생활 언어로 제안하라(예: '온라인, 글쓰기, "
    "정리·기획을 조합하는 방식이 잘 맞습니다'). 직업명 단정이 아니라 적합한 활동축·환경·방식의 "
    "조합으로 제안하고, 블록에 없는 키워드를 새로 만들지 말 것."
)

NON_NORMATIVE_REASSURANCE_DIRECTIVE = (
    "[탈규범 안심] 결혼·직장·사업·인간관계 질문에서 '다들 하니까 해야 한다' 식의 사회적 정답을 "
    "강요하지 마라. 엔진 신호가 특정 선택을 요구하지 않으면 '반드시 결혼해야 풀리는 사주는 "
    "아니다'처럼 선택의 자유를 열어 주고, 어떤 선택을 하든 지킬 본인 기준(독립성·생활 리듬)을 "
    "함께 제시하라."
)

MANAGE_NOT_OVERCOME_DIRECTIVE = (
    "[극복 아니라 관리] 부족한 오행·과다·기신 기질을 '고쳐야 할 문제·극복 대상'으로만 말하지 "
    "마라. 없애는 것이 아니라 상황이 겹칠 때 기준을 세워 관리하는 부분으로 설명하고, 관리 "
    "노하우(루틴·기록·기준선)를 함께 제안하라(예: '이 기질은 없애야 할 문제가 아니라, 돈과 "
    "관계가 섞일 때 기준을 세워 관리해야 하는 부분입니다')."
)

DECISION_ATTITUDE_DIRECTIVE = (
    "[운 품질 → 의사결정 태도] 연도·대운의 운 품질 등급을 의사결정 태도로 번역해 조언하라 — "
    "흐름이 좋은 시기는 직감·기회를 실행으로 옮겨 볼 만하고, 불안정·기신 시기는 확장보다 점검과 "
    "내실이 우선. 등급은 위 데이터 블록의 엔진 판정만 근거로 하고 임의로 매기지 말 것."
)

# 바넘 문장 억제(2026-07-22 데굴님 확정 — 저비용·품질 직결). 실사례: 재물 질문 서두가
# '단정하고 믿음직스러워요·학문적 소양과 인덕' 류 근거 약한 칭찬으로 시작해 답을 늦추고
# 전형적 운세 문장처럼 보이게 함.
BARNUM_SUPPRESSION_DIRECTIVE = (
    "[서두·칭찬 규칙 — 항상 적용]\n"
    "사용자가 성격·성향을 묻지 않았으면 성격 묘사로 시작하지 말 것. 질문 도메인과 직접 "
    "연결되지 않는 미덕 칭찬(단정함·믿음직함·인덕·학문적 소양 등)은 근거가 있어도 생략한다 "
    "— 관계 형성용 칭찬 문구 금지. 첫 문단은 질문에 대한 핵심 판정으로 바로 시작하고, "
    "명식 근거는 그 판정에 필요한 만큼만 본문 중간에 인용한다. 호칭의 반복 사용을 "
    "최소화할 것."
)

# 근거 충실 서술 가드(P4, 2026-07-22 데굴님 확정 — 강제 긍정 대비 폐기, 데이터 기반 대조만).
# 실사례: 표 근거에 없는 '투자 실패·독소 조항·거주지 이동'을 충·공망만으로 창작하고, 전 행
# 신뢰도 '다소 낮음'인데 본문은 정밀 단정으로 서술.
EVIDENCE_FIDELITY_DIRECTIVE = (
    "[근거 충실 서술 가드 — 항상 적용]\n"
    "①제공된 표·근거 블록에 없는 구체적 사건 형태(투자·부동산·계약·문서·이사·소송 등)를 "
    "충·공망·오행 논리만으로 창작하지 말 것 — 그런 사건 형태는 해당 사건 신호가 데이터에 "
    "있을 때만 언급한다. ②신뢰도가 낮은 후보는 '~할 가능성이 있다' 수준으로만 서술하고 "
    "구체적 현실 사건을 단정하지 말 것 — 신뢰도가 낮을수록 서술의 구체성도 낮춘다. "
    "③부정 방향 후보만 있으면 그 사실대로 설명하라 — 데이터에 없는 긍정 시기를 만들어 "
    "위로하지 말 것. 긍정 대조는 표·근거에 실제 긍정 후보가 있을 때만 그 후보로 한다. "
    "④신호 강도(점수)는 길흉이 아니라 발동 강도다 — 강도 높음+부정 방향은 '강하게 부정 "
    "쪽 변동'이지 좋은 운이 아니다."
)

# 불확실성 번역 규칙(2026-07-22 데굴님 승인, GPT 검토안 P0) — '가능성은 열리지만 조건
# 확인이 필요한 달' 류 추상 문구가 무슨 뜻인지 알 수 없다는 테스터 불만. 대화(chat 상시)와
# 테마 리포트(전 섹션 prefix) 공용 — 추상 상태를 구체 사건·미확정 결과·실제 변수·행동으로
# 번역하도록 강제한다(서술 전용, 점수·판정 불변).
# 표현 결 층(daily docs/17 §23 이식, 2026-09-10 — chat·report 공용). 후보/기간의 '해석'(운 천간
# 십성 유입)은 행동 권유 문장의 결, '결(12운성)'/'흐름'(12운성 유입)은 흐름·결과 서술 문장의 결.
# 문체 힌트일 뿐 점수·판정·간지 사실을 바꾸지 않는다(CLAUDE.md 원칙 12 와 같은 취지).
TONE_LAYER_DIRECTIVE = (
    "[표현 결] 후보·기간의 '해석'(운 천간 십성)은 행동 권유 문장의 결로, '결(12운성)'·'흐름'"
    "(12운성 유입)은 흐름·결과 서술 문장의 결로 삼아 표현을 고를 것 — 같은 사건이라도 "
    "해석·결이 다르면 다른 결로 쓰고, 이 결은 문체 힌트일 뿐 점수·판정·간지 사실을 바꾸지 않는다."
)
UNCERTAINTY_TRANSLATION_DIRECTIVE = (
    "[불확실성 표현 규칙 — 항상 적용]\n"
    "'가능성이 열려요'·'조건 확인이 필요한 달'·'변수가 있어요'·'흐름이 들어와요'·'상황에 "
    "따라 달라져요'·'신중한 접근이 필요해요'·'흐름을 잘 살펴야 해요'·'무리하지 않는 게 "
    "좋아요'·'꼼꼼히 준비하세요' 같은 추상 문구를 단독으로 쓰지 말 것. 불확실한 신호는 "
    "반드시 네 요소로 풀어라: ①무엇이 움직이는가(구체적 사건·행동) ②어디까지 가능한가(되는 "
    "것과 아직 아닌 것을 구분) ③실제 변수가 무엇인가(심사·상대 의사·자금·서류·일정처럼 "
    "이름을 붙일 것) ④사용자가 지금 할 행동 한 가지. 경고·주의 문장은 '대상 과업+예상 실패 "
    "형태+확인 행동+확인 시점' 중 최소 세 요소를 담아야 한다. '조건'이라는 단어는 바로 "
    "뒤에 구체적 조건명이 따라올 때만 허용하며, 구체 변수를 제공 데이터에서 찾을 수 없으면 "
    "'결과 신호보다 준비·탐색 신호가 중심인 시기'로 표현하라."
)

# 명확한 답 계약(2026-08-10 테스터 피드백 반영 — "그래서 어쩌라고, 명확하지 않아 더 답답").
# 원칙(사건 확정 단정 금지)과 명확성은 충돌하지 않는다: 금지는 '성사·발생 단정'이지
# '유불리·시기·행동 판정'이 아니다 — 유불리는 엔진이 이미 계산해 제공한다(용기신·favorability).
# 헤지는 사건 발생 여부에만 걸고, 판정·시기·행동은 단문으로 선언한다. 챗·리포트 공용.
ANSWER_CLARITY_DIRECTIVE = (
    "[명확한 답 계약 — 항상 적용]\n"
    "사용자는 답답해서 묻는다 — 정보 나열이 아니라 정리된 판단을 원한다.\n"
    "① 첫 문단에서 질문에 바로 답하라: 제공된 엔진 판정(길흉·유불리)을 근거로 유리/불리/"
    "조건부 중 하나를 명시적으로 선언하고, 핵심 시기 1~2개와 지금 할 행동 1개를 함께 담아라. "
    "'문서운이 있어?'처럼 예/아니오형 질문이면 '있다/없다/조건부다'로 먼저 답한다. 이는 "
    "사건의 성사·발생을 단정하라는 뜻이 아니다 — 유불리·방향의 판정은 단정이 아니라 제공된 "
    "데이터의 요약이다.\n"
    "② 판정·시기·행동을 말하는 문장에는 유보 표현('~수 있어요'·'~가능성이 보여요'·'~여지가 "
    "있어요')을 붙이지 마라. 불확실성은 유보 어미의 반복이 아니라 조건문으로 번역하라 — "
    "'성사의 조건은 X다'·'X가 확인되면 진행해도 된다'. 유보 표현은 답 전체에서 실제로 "
    "불확실한 대목 **최대 두 문장**으로 제한한다 — 작성을 마친 뒤 '수 있'이 들어간 문장 "
    "수를 세어, 초과분은 단정형 서술이나 조건문('~의 조건은 X다')으로 고쳐 써라.\n"
    "③ 기신·구신·한신 같은 판정 용어를 나열하지 말고 결과어로 번역하라('실속이 새는 달'·"
    "'부담으로 작동하는 기운'). 원어는 근거 설명에 필요한 최소만 쓴다.\n"
    "④ 중요한 것부터 서술하라 — 질문에 직결된 시기·신호를 먼저 충분히, 나머지는 뒤에 짧게. "
    "모든 달을 같은 비중으로 나열하지 마라.\n"
    "⑤ 끝맺음은 시스템 지시의 마무리 한 번에 담되, 오늘 취할 행동이 자연스러운 문장으로 "
    "들어가게 하라(번호 목록·별도 요약 섹션은 만들지 않는다)."
)

AVOID_DATE_CERTAINTY_DIRECTIVE = (
    "[시기 단정 금지] 특정 달·날짜를 결과와 묶어 단정하지 마라('반드시 8월에 됩니다'·'10월에 "
    "취업합니다' 금지). 주목할 달은 '움직임이 강해지는 달'·'제안·면접·자금 흐름을 점검할 만한 "
    "창'처럼 활성화 창으로 표현하고, 신호가 뜨는 달과 결과가 실현되는 달이 다를 수 있음을 "
    "전제로 서술하라."
)

# 반복 행동 패턴·과거 행동 회고 — 3층 분리 규칙(2026-09-06 데굴님 조건부 승인).
# ①원국·궁위 = 행동 성향·역할 구조 ②대운·세운 = 당시 행동을 둘러싼 배경·압력 ③실제 행동·결과
# = 별도 사실. 궁위→행동 단계 연결은 정통 명리 규칙이 아니라 **서사화를 위한 해석 규칙**이며
# 보조 단서로만 쓴다 — '시주=마무리, 천간=마음, 지지=행동, 12운성=태도' 고정 등식 금지
# (천간=외현·의식적 표현, 지지=기반·실질 작동, 12운성=기세·성숙도·작동 상태가 더 가깝다).
BEHAVIOR_PATTERN_DIRECTIVE = (
    "[반복 행동 패턴 질문 — 3층 분리] 사용자가 '왜 항상/늘/끝에 가면 이렇게 하나'처럼 반복되는 "
    "자기 행동의 이유를 물었다. ①원국·궁위 = 행동 성향·역할 구조: 십성 세력·격국·용신·신강약을 "
    "정적 기질로 읽고, 궁위는 보조 단서로만 쓴다 — 연·월주는 출발과 사회 장면의 대응, 일주는 "
    "자기·친밀 관계의 반응, 시주는 후반·결과·표출의 자리라 '마무리·후속 단계'와 연결할 수 있다. "
    "천간은 외현·의식적 표현, 지지는 기반·실질적 작동, 12운성은 기세·성숙도·작동 상태로 읽되 "
    "'천간=마음, 지지=행동, 운성=태도' 같은 고정 등식으로 치환하지 말 것. ②대운·세운은 그 행동을 "
    "둘러싼 배경(압력·기회·관심 방향·변동성)이지 원인이 아니다. ③실제로 무엇을 했는지는 별도 "
    "사실이며 사용자의 자기 보고를 우선한다. '이렇게'처럼 행동이 서술되지 않았으면 명식에서 "
    "읽히는 반복 패턴(특히 마무리 단계)을 먼저 제시하고 실제 그런지 확인 질문 하나로 맺을 것. "
    "'~한 사람이다' 단정 대신 '~로 흐르기 쉬운 결'로 서술하고, 고쳐야 할 결점으로 몰지 말 것."
)

RETRO_BEHAVIOR_DIRECTIVE = (
    "[과거 행동 회고 — 3층 분리] 사용자가 '그때 왜 그랬을까'처럼 지난 행동·선택의 배경을 물었다. "
    "①원국·궁위 = 행동 성향·역할 구조(정적 기질). ②대운·세운 = 당시 행동을 둘러싼 배경 — "
    "압력·기회·관심 방향·변동성을 설명하는 시기적 신호로만 쓴다. 예: '그 시기에는 관성 압박과 "
    "충이 겹쳐 관계나 직장 문제를 빨리 정리하려는 방향으로 해석되기도 해요'는 가능하지만 "
    "'그 운 때문에 퇴사했다'는 인과 확정은 금지. ③실제 행동·결과는 별도 사실 — 사용자가 무엇을 "
    "했는지 말하지 않았으면 사건을 창작하지 말 것. 질문이 가리키는 시점이 데이터에 있으면(앞선 "
    "대화에서 이어진 시기·명시 연월) 그 시기의 배경 신호로 서술하고, 시점 데이터가 없으면 운 "
    "배경을 추정하지 말고 원국 성향 층만 서술한 뒤 언제·어떤 일이었는지 확인 질문 하나로 맺을 것. "
    "사용자의 자기 보고와 다르면 자기 보고를 우선한다."
)

TRAIT_FEEDBACK_DIRECTIVE = (
    "[성향 반박 수용 — 풀이와 실제가 다르다는 피드백] 사용자가 '풀이에는 그렇다는데 실제 나는 "
    "아니다'라고 하면 회피하거나 원래 설명을 반복하지 마라. ① 사용자의 실제 경험을 우선 사실로 "
    "인정하고, ② 그 성향이 원국의 정적 잠재와 운·환경에서의 작동이 다를 수 있음을 구분해 어떤 "
    "조건에서 드러나고 어떤 조건에서 잠복하는지로 재해석하며, ③ 필요하면 언제·어떤 상황에서 "
    "달랐는지 확인 질문을 하라. 사용자의 자기 보고를 부정하는 단정 금지."
)


# 오행 한자 → 사전 source_id(영문 키). 활동 키워드·개운 행동 사전 공용.
_ELEMENT_EN = {"木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water"}


def activity_keyword_lines(
    favorable: list[tuple[str, str]],
    cautious: list[tuple[str, str]],
    natal_sinsal: set[str],
    keyword_map: dict,
) -> list[str]:
    """[활동 키워드] 블록 — 용신·신살 신호를 생활 활동 키워드로 번역할 재료를 직렬화한다.

    activity_keyword_map.json(reviewed:false 초안)의 항목만 사용하며, 엔진이 확정한
    용희기구한 역할·원국 신살로 항목을 **결정론적으로 선별**한다(LLM 임의 선택 금지 —
    원칙 1). 직업 추천이 아니라 활동축·환경·방식 제안 전용(직업명 단정 금지).

    Args:
        favorable: 살리면 좋은 오행 [(한자, 역할 한글)] — 용신·희신.
        cautious: 기준이 필요한 오행 [(한자, 역할 한글)] — 기신·구신.
        natal_sinsal: 원국 신살 이름 집합(엔진 판정 — 예 '현침').
        keyword_map: activity_keyword_map.json 파싱 결과.

    Returns:
        직렬화 라인 목록. 매칭 항목이 없으면 빈 목록(블록 미부착).
    """
    entries = keyword_map.get("entries", [])
    by_element = {
        e["source_id"]: e for e in entries if e.get("source_type") == "element"
    }
    lines: list[str] = []
    for hanja, role_ko in favorable:
        entry = by_element.get(_ELEMENT_EN.get(hanja, ""))
        if not entry:
            continue
        kws = ", ".join(entry["activity_keywords"])
        line = f"살리면 좋은 기운 {hanja}({role_ko}): {kws}"
        if entry.get("caution"):
            line += f" — 주의: {entry['caution']}"
        lines.append(line)
    for hanja, role_ko in cautious:
        entry = by_element.get(_ELEMENT_EN.get(hanja, ""))
        if not entry:
            continue
        area = ", ".join(entry["activity_keywords"][:4])
        caution = entry.get("caution") or "기준을 세워 관리한다."
        lines.append(
            f"기준을 세울 기운 {hanja}({role_ko}): 관련 영역({area})에서는 {caution}"
        )
    for entry in entries:
        if entry.get("source_type") != "star":
            continue
        korean = entry.get("korean", "")
        if korean in natal_sinsal or korean.removesuffix("살") in natal_sinsal:
            kws = ", ".join(entry["activity_keywords"])
            line = f"원국 신살 {korean}: {kws}"
            if entry.get("safe_rule"):
                line += f" ({entry['safe_rule']})"
            lines.append(line)
    if not lines:
        return []
    return [
        "[활동 키워드 — 엔진 용신·신살 기준 번역 재료(직업 단정 금지, 조합 제안 전용)]",
        *lines,
    ]


def remedy_action_lines(
    favorable_elements: list[str], action_map: dict,
) -> list[str]:
    """[개운 행동] 블록 — 보완할 오행(용신·희신)의 생활 행동 제안을 직렬화한다.

    remedy_action_map.json(reviewed:false 초안)의 element_actions만 사용한다.
    개운 행동은 주술적 처방·결과 보장이 아니라 생활 리듬·선택 습관 보완 조언이며,
    행동·환경·루틴을 색상·물건보다 우선한다(사전 principles — 원칙 3).

    Args:
        favorable_elements: 보완할 오행 한자 목록(용신·희신 — 엔진 확정값).
        action_map: remedy_action_map.json 파싱 결과.

    Returns:
        직렬화 라인 목록. 매칭 항목이 없으면 빈 목록(블록 미부착).
    """
    actions = action_map.get("element_actions", {})
    lines: list[str] = []
    for hanja in favorable_elements:
        entry = actions.get(_ELEMENT_EN.get(hanja, ""))
        if not entry:
            continue
        rec = ", ".join(entry["recommended_actions"])
        avoid = ", ".join(entry.get("avoid", []))
        line = f"{hanja} 보완 행동({entry['core_need']}): {rec}"
        if avoid:
            line += f" / 피할 것: {avoid}"
        lines.append(line)
    if not lines:
        return []
    principles = action_map.get("principles", {})
    note = principles.get(
        "not_magic",
        "개운 행동은 결과를 보장하는 처방이 아니라 생활 리듬 보완 조언이다.",
    )
    return [
        "[개운 행동 — 생활 행동 제안(주술적 처방·결과 보장 표현 금지)]",
        *lines,
        f"원칙: {note} '이 행동을 하면 반드시 된다' 표현 금지.",
    ]


def wealth_capacity_lines(wc: WealthCapacity) -> list[str]:
    """[원국 횡재 그릇] — 운 분리 잠재구조(점수·영문 코드 비노출)."""
    band = _CAPACITY_BAND_KO.get(wc.capacity_band, wc.capacity_band)
    flags = ", ".join(wc.flags) if wc.flags else "두드러진 횡재 구조 약함"
    return [
        "[원국 횡재 그릇 — 운과 분리된 원국 자체의 재물 잠재구조(엔진 판정). '그릇이 있어도 운에서 "
        "발동해야 현실화'를 전제로 서술하고, 당첨·복권 단정과 번호 추천은 절대 금지]",
        f"재성 오행: {wc.wealth_element} · 종합 그릇: {band}",
        f"성립 구조: {flags}",
        "발동 조건(운에서 일어나야 현실화): 재성국 완성(삼합)·묘고 충개고·식상생재. 원국에 "
        "그릇이 없어도 운에서 이 완성이 일어나면 일부 발동하나, 그릇이 받쳐줄수록 크게 난다.",
    ]


_PREP_GRADE_KO = {"strong": "강", "moderate": "중", "weak": "약"}
_PREP_SIGNAL_KO = {"output": "식상(생산·기술·결과물)", "peer": "비겁(독립·자기 기반, 조건부)"}
_PREP_ROLE_KO = {
    "manifestation": (
        "올해는 재성 유입 '발현 후보'년 — 앞선 준비가 있었는지에 따라 회수 폭이 갈린다"
    ),
    "preparation": "올해는 '준비기' — 다가올 재성 유입년을 향해 기반을 정리하는 흐름",
    "none": "",
}


def preparation_context_lines(ctx: PreparationContext) -> list[str]:
    """[재물 준비기 신호] — 발현 후보년·선행 준비년(서술 전용, 데굴님 확정 2026-07-12).

    미검출이면 빈 목록(무언급). 불변식: 점수·후보 순위·발현 시점·confidence·favorability
    불변, 사건 생성 금지 — 헤더와 말미 디렉티브로 LLM에도 강제한다.
    """
    if not ctx.is_detected:
        return []
    out = [
        "[재물 준비기 신호 — 서술 전용 맥락(점수·순위·시기·확신도 변경 금지). 발현 후보는 "
        "'확정'이 아니라 등급이며, 준비년은 사건이 아니라 흐름이다]",
    ]
    for c in ctx.manifestation_candidates:
        pos = "천간·지지 모두 재성" if len(c.wealth_positions) == 2 else (
            "천간 재성" if c.wealth_positions == ["stem"] else "지지 본기 재성"
        )
        out.append(f"발현 후보 {c.year}({c.ganji}) · 등급 {_PREP_GRADE_KO[c.grade]} — {pos}"
                   + (" + 식상 동반(식상생재 유입)" if c.grade == "moderate" else ""))
    for p in ctx.preparation_years:
        sig = "、".join(_PREP_SIGNAL_KO[s] for s in p.signals)
        tier = "주 준비기(직전 해)" if p.weight >= 1.0 else "약한 선행 준비기(2년 전)"
        line = (
            f"준비년 {p.year}({p.ganji}) → {p.target_year} 대비 {tier}"
            f" · 신호 {sig} · 강도 {_PREP_GRADE_KO[p.strength]}"
        )
        if p.resource_support:
            line += " · 인성 동반(배운 것을 결과물로 전환하는 준비 — 보조)"
        out.append(line)
    role = _PREP_ROLE_KO[ctx.current_year_role]
    if role:
        out.append(f"현재 위치: {role}.")
    out += [
        "서술 규칙: ①과거 준비년은 회상·확인형으로만('~한 흐름이 있었다면') — 실제 준비 여부는 "
        "사용자의 몫, 준비 사건을 지어내지 말 것 ②'준비했으니 반드시 수익' 류 인과 확정 금지 — "
        "'앞선 시기의 기반 정리가 발현년의 재물 활동과 연결될 수 있다' 수준까지만 ③질문의 시간 "
        "지평을 넘는 발현 후보년은 서술하지 말 것 ④비겁 단독 준비 신호는 경쟁·지출 분산으로도 "
        "작동하므로 조건부로만 언급.",
    ]
    return out


def marriage_resource_lines(mr: MarriageResourceProfile) -> list[str]:
    """[결혼·자산 자원 구조] — 성별 인지·중립·비단정(점수 비노출)."""
    spouse = (
        f"{mr.spouse_star} 신호 {'드러남' if mr.spouse_star_present else '약함(지장간 잠복)'}"
    )
    pos = []
    if mr.wealth_in_family_palace:
        pos.append("집안·초년 기반권")
    if mr.wealth_in_result_palace:
        pos.append("결혼 후·결과 자원(시주)")
    # 정확한 자리 목록을 1차로 제시 — '년월' 뭉뚱그림 라벨을 LLM이 '연주와 월주에 재성'으로
    # 옮겨 말하던 오독 교정(2026-07-21 데굴님 실로그). 환경 결 라벨은 보조로만 덧붙인다.
    if mr.wealth_positions:
        wealth_line = (
            "재성 위치(명식 그대로 — 이 자리 표기만 인용하고 재성이 없는 주(柱)로 옮겨 말하지 "
            "말 것): " + "·".join(mr.wealth_positions)
        )
        if pos:
            wealth_line += " · 환경 결: " + ", ".join(pos)
    else:
        wealth_line = "재성 환경: " + (", ".join(pos) if pos else "년월·시주에 약함")
    if mr.wealth_strong:
        wealth_line += " · 세력 강"
    if mr.wealth_palace_clash:
        wealth_line += " · 재성궁 충(발동·변화 잠재)"
    leans = "、".join(_LEAN_KO.get(x, x) for x in mr.wealth_source_leans) or "뚜렷하지 않음"
    spouse_frame = _SPOUSE_FRAME_KO.get(mr.gender, _SPOUSE_FRAME_KO["unknown"])
    lines = [
        "[결혼·자산 자원 구조 — 원국 구조(운 미반영). 가능성·잠재로만 서술하고 '신분 상승·신데렐라·"
        f"반드시' 류 단정 금지. {_GENDER_KO.get(mr.gender, mr.gender)} 명식 — {spouse_frame}]",
        f"배우자 별({mr.spouse_star}): {spouse}",
        wealth_line,
    ]
    if mr.hour_resource_role:
        lines.append(f"시주 자원 역할: {mr.hour_resource_role}")
    # 배우자 인연 결(중립·비낙인 — 궁합 자료 ⑤⑥): '바람둥이/과부상' 류 낙인 금지, 경향으로만.
    bond: list[str] = []
    if mr.spouse_star_excess:
        if mr.gender == "male":
            bond.append("재성(이성·물질)이 강해 새 자극·인연에 끌리는 경향(호기심 큰 결)")
        elif mr.gender == "female":
            bond.append("관성(이성·인연)이 많아 인연 신호가 복잡할 수 있는 결(관살혼잡 경향)")
        else:
            bond.append("배우자 별 세력이 강해 이성·인연 신호가 두드러지는 결")
    if mr.spouse_star_absent:
        bond.append("배우자 별 미투출 — 인연을 스스로 만들어가는 능동형 구조(부재 단정 아님)")
    if mr.charm_present:
        bond.append("도화·홍염 — 이성에게 매력적으로 비치고 끌림이 잦은 경향")
    if mr.day_branch_tendency:
        bond.append(f"배우자궁(일지) 기질 {mr.day_branch_tendency}")
    if bond:
        lines.append(
            "배우자 인연 결(가능성·경향으로만, 단정·낙인 금지): " + " / ".join(bond)
        )
    # A) 배우자 취향(이상형) — 일지 십성 기준 끌리는 타입(경향) + 잘 안 맞기 쉬운 결.
    if mr.ideal_type_tendency:
        lines.append(
            f"배우자 취향(이상형 — 일지 십성, 경향·단정 아님): {mr.ideal_type_tendency}"
        )
    if mr.ideal_type_friction:
        # 본성과 다른 기준의 '결심 선택'은 수년에 걸쳐 마찰이 커지기 쉽다는 전문가 견해
        # (2026-07-21 영상 자료) — 이별·이혼 단정 금지, 자기 취향 인식 보조로만.
        lines.append(
            f"잘 안 맞기 쉬운 결(경향 — 낙인·이별 단정 아님): {mr.ideal_type_friction}. "
            "일지 취향과 반대 결을 '결심'으로 고르면 시간이 지나며 본성과 마찰이 커지기 "
            "쉬우니, 조건과 끌림이 함께 가는 상대인지로 안내할 것."
        )
    # B) 생애 단계별 연애 대상 — 연·월·시지 십성(경향·시기 단정 아님).
    if mr.life_stage_ideals:
        lines.append(
            "생애 단계 연애 대상(연·월·시지, 경향·시기 단정 아님): "
            + " / ".join(mr.life_stage_ideals)
        )
    # 관계 친화·돌봄 성향 — 십성 구조×신강약(관계에 어떻게 임하는가, 경향·비단정).
    if mr.relationship_affinity:
        lines.append(
            "관계 친화·돌봄 성향(경향·단정 아님): " + " / ".join(mr.relationship_affinity)
        )
    # E·F·G) 배우자복 품질 — 배우자별 청탁·뿌리 / 배우자궁 안정 / 배우자성=용신 덕(경향·비단정).
    quality: list[str] = []
    if mr.spouse_star_clean:
        q = "배우자별이 하나로 깔끔(선택 분명·관계 안정)"
        if mr.spouse_star_rooted:
            q += " + 뿌리 튼튼(능력·집안 등 현실적 도움 받기 쉬운 결)"
        quality.append(q)
    elif mr.spouse_star_rooted:
        quality.append("배우자별 뿌리 있음(영향력 오래가는 결)")
    if mr.spouse_palace_stable:
        quality.append(
            "배우자궁(일지) 충·형·원진 없이 안정 — 관계 내구성이 좋아 갈등도 제자리로 돌아오는 결"
        )
    else:
        quality.append(
            "배우자궁(일지) " + "·".join(mr.spouse_palace_afflictions)
            + " — 관계가 흔들리기 쉬운 결이나 개운·궁합·노력으로 보완 가능(이혼 단정 아님, "
            "남·환경 탓보다 본인 대응이 관건)"
        )
        # 관계질 라벨(P4 — 중립 설명, 판정·점수 미개입): 각 살의 관계 결을 낙인 없이 병기.
        rel_notes = [
            f"{a}({relation_summary_ko(a)})"
            for a in mr.spouse_palace_afflictions if relation_summary_ko(a)
        ]
        if rel_notes:
            quality.append("  · 관계질 참고: " + " / ".join(rel_notes))
    if mr.spouse_is_yongsin:
        quality.append(
            f"배우자성({mr.spouse_star})이 용신/희신 — 배우자가 부족한 기운을 채워주는 "
            "'에어컨/보일러' 역할로, 결혼하며 더 풀리는 배우자 덕(경향)"
        )
    if quality:
        lines.append("배우자복 품질(경향·단정 아님): " + " / ".join(quality))
    lines.append(
        f"자산 출처 경향(가능성): {leans}. 돈의 '출처'(부모/배우자 집안/자수성가)를 구분해 "
        "서술하되 단정하지 말 것."
    )
    return lines


def wealth_status_lines(w: WealthStatusLean) -> list[str]:
    """[부/귀 지향] — 영문 그룹·퍼센트 비노출, 정성 표현만."""
    group_ko = _GEOKSIN_GROUP_KO.get(w.geokguk_group, "")
    if w.wealth_pct >= w.officer_pct + 5:
        bias = "재성(재물 기운)이 관성(조직·명예 기운)보다 우세"
    elif w.officer_pct >= w.wealth_pct + 5:
        bias = "관성(조직·명예 기운)이 재성(재물 기운)보다 우세"
    else:
        bias = "재성·관성이 균형"
    parts = [f"주격 {w.geokguk_name}" if w.geokguk_name else ""]
    if group_ko:
        parts.append(f"격신은 {group_ko}")
    parts.append(bias)
    return [
        "[부(富)/귀(貴) 지향 — 원국이 재물(부) 결인지 명예·조직(귀) 결인지. 우열·단정이 아니라 "
        "방향이며 운·선택으로 달라질 수 있음]",
        f"지향: {w.lean} · " + " · ".join(p for p in parts if p),
        w.note,
    ]


def health_lines(
    result: ManseV2Result, hv: HealthVulnerabilityProfile, today_year: int
) -> list[str]:
    """[원국 건강 취약 구조 + 관리 권장 시기] — 의료 면책, 점수 비노출(등급·근거만)."""
    lines = [
        "[원국 건강 취약 구조 — 원국 구조(운 미반영). **의료 진단이 아니며 질병명·수명·사망은 절대 "
        "단정 금지.** '특정 계열은 평소 관리·정기 검진이 도움될 수 있다'는 예방·가능성 관점으로만 "
        "서술하고, 우려 시 전문의 상담을 권하는 톤을 유지할 것]",
    ]
    if hv.vulnerable_organs:
        organs = "; ".join(
            f"{o.organ_category}({o.element}—{o.attacker_element}의 극, 통관 약)"
            for o in hv.vulnerable_organs
        )
        lines.append(f"취약 장기 계열(평소 관리 권장): {organs}")
    else:
        lines.append("취약 장기 계열: 두드러진 손상 구조는 약함")
    body = []
    if hv.weak_body_excess_officer:
        body.append("관다신약(체력 부담·과로 관리)")
    if hv.food_god_weak:
        body.append("식신 약(회복력·식욕 관리)")
    if hv.indirect_resource_strong:
        body.append("편인 강(도식 — 소화·생활리듬 관리)")
    if hv.excess_unfavorable_elements:
        body.append(f"과다 기신 오행 {'·'.join(hv.excess_unfavorable_elements)}")
    if body:
        lines.append("체력·구조 신호: " + " · ".join(body))
    tombs = [t for t in (hv.day_master_tomb_branch, hv.food_god_tomb_branch) if t]
    if tombs:
        lines.append(
            f"입묘 주의 지지: {'·'.join(dict.fromkeys(tombs))} — 운에서 이 지지가 겹치는 시기에 "
            "컨디션·검진을 챙기면 좋음(질병 단정 아님)"
        )
    if hv.stem_symbol_caution:
        lines.append(f"일간 물상 참고: {hv.stem_symbol_caution}")
    windows = health_risk_windows(result, hv, today_year)
    if windows:
        lines.append(
            "관리 권장 시기(운에서 취약 구조가 재자극되는 때 — 질병·사망 예측 아님, 그 무렵 "
            "컨디션·검진을 챙기라는 신호):"
        )
        for w in windows:
            bg = f" {w.daewoon}대운" if w.daewoon else ""
            lines.append(f"- {w.period}년{bg}: {w.level} ({', '.join(w.reasons)})")
    return lines


def era_energy_lines(result: ManseV2Result, year: int) -> list[str]:
    """[올해 시대 기운] — 명리 기운 맥락(경제·시장 예측 금지)."""
    lc = result.luck_cycles
    ganji = ""
    if lc is not None:
        for sw in lc.yearly_luck:
            if sw.label == str(year) and len(sw.ganji) >= 2:
                ganji = sw.ganji
                break
    if not ganji:
        return []
    era = era_energy_profile(ganji[0], ganji[1])
    lines = [
        "[올해 시대 기운 — 그 해 간지의 명리 기운(개인 앞 사회 맥락). 경제·시장·채용 같은 시사 "
        "예측·단정은 절대 금지, 기운의 결로만 서술]",
        era.summary,
    ]
    note = era_curated_note(year, era.year_ganji)
    if note:
        lines.append(f"운영자 시대 노트(참고): {note}")
    return lines


# ── 대운 풀이 관점·교체기 신호(2026-06-23, 전문가 강의 참고 — 채팅·리포트 공용) ──
# 계산 불변(점수·날짜·간지·판정 무관). 대운을 '환경/공간감(플랫폼)이 닥쳐오는 흐름'으로,
# 핵심을 '이 대운이 나에게(용신·조후) 맞느냐'로 잡는 서술 관점만 제공한다(절대원칙 1·8 준수).
# 발현 순서는 하드 전/후반 분할이 아니라 그라데이션 prior + 예외 모드(2026-07-21 개정,
# doc/v2_2/DAEWOON_PROGRESSION_NARRATIVE.md).
DAEWOON_FRAMING_DIRECTIVE = (
    "[대운 풀이 관점] 대운은 '내가 바꾸는 것'이 아니라 계절이 닥치듯 환경·공간감(플랫폼)이 "
    "바뀌어 오는 10년 흐름이다. 핵심은 '운이 바뀐다'가 아니라 '이 대운이 나에게(용신·조후) 맞는 "
    "대운이냐' — 맞으면 같은 노력이 순풍을, 안 맞으면 역풍이 된다(안 맞는 평운·기신 구간은 포기가 "
    "아니라 지금 하던 것을 지키며 내실을 다지고 다음 맞는 대운을 준비). 발현 순서는 대개 천간이 "
    "나타내는 계기·외부 변화가 상대적으로 먼저 인식되고, 시간이 지나며 지지가 나타내는 생활환경·"
    "관계·현실 조건이 누적·구체화되기 쉽다 — 단 이는 고정된 전/후반 연차 분할이 아니라 일반적 "
    "경향이며, 지지의 충·형·합국 성립은 현실 변화를 초입부터 부르고 천간의 강한 작동은 외부 "
    "주제를 전 기간 지속시킬 수 있다('주도'로 단정하지 말고 '상대적으로 드러나기 쉽다'로 표현). "
    "새 환경에 적응하며 그 대운의 미션(이동·전환·확장·정착 등)을 수행하는 관점으로 — 단정 말고 "
    "에너지·방향·적응으로 풀 것."
)
DAEWOON_TRANSITION_SIGNALS_DIRECTIVE = (
    "[대운 교체기 체감 신호 — 단정 아님, 사람·정도 차이] 교운(대운 교체) 무렵엔 흔히 다음이 함께 "
    "나타난다: 주변 사람이 바뀌고 새 인연이 들어옴 · 안 하던 새 일을 도모하고 싶어짐 · '뭔가 "
    "해봐야 할 것 같은' 막연한 기대 · 가까운 이들의 반대가 늘어남 · 거주지·환경을 바꾸거나 물건을 "
    "정리하고 싶어짐 · 외모·분위기 변화. '겪으셨을 수 있다/겪을 수 있다'로 가능 형태로만 짚고, "
    "확정·예언으로 말하지 말 것."
)

# ── 대운 발현 진행 모드(2026-07-21 데굴님 확정 — 하드 전/후반 분할 대체, 서술 전용) ──
# 대운표 행 표기용 짧은 라벨. 점수·판정 불변(doc/v2_2/DAEWOON_PROGRESSION_NARRATIVE.md).
PROGRESSION_MODE_KO: dict[str, str] = {
    "default_gradient": "점진(계기→현실화)",
    "branch_early_activation": "지지 조기 발동",
    "stem_persistent": "천간 지속",
    "coactivated": "동시 발현",
    "weak_manifestation": "약발현(명분 위주)",
    "indeterminate": "단정 불가(세운·월운 확인)",
}
_PROGRESSION_MODE_DESC: dict[str, str] = {
    "branch_early_activation": (
        "지지의 충·형·합국·공망 발동이 강하게 성립 — 생활환경·관계·현실 조건의 변화가 후반을 "
        "기다리지 않고 운 초입부터 나타날 수 있다"
    ),
    "stem_persistent": (
        "천간의 작동성이 강함(통근) — 직책·계약·평가·선택 같은 외부 주제가 초기에만 머물지 않고 "
        "대운 전 기간에 걸쳐 반복될 수 있다"
    ),
    "coactivated": (
        "천간의 외부 계기와 지지의 현실 변화가 함께 강화 — 제안·결정과 실제 환경 변화가 짧은 "
        "간격으로 이어질 수 있다"
    ),
    "weak_manifestation": (
        "천간 무근·합거 또는 지지 공망 — 신호가 명분·가능성 수준에 머물고 실제 결과로는 더디게 "
        "이어질 수 있다"
    ),
    "indeterminate": (
        "발동과 저하 신호가 상충 — 이 대운은 전반·후반으로 나눠 단정하지 말고 세운·월운이 어느 "
        "글자를 활성화하는지로 시점을 좁힐 것"
    ),
}


def daewoon_progression_lines(profiles: list[DaewoonProgressionProfile]) -> list[str]:
    """[대운 발현 진행 신호] — 기본 그라데이션 prior를 뒤집는 예외 대운만 표기(서술 전용).

    전 대운이 default_gradient면 빈 목록(디렉티브의 기본 prior 문구로 충분 — 무언급).
    불변식: 점수·순위·시기·확신도 불변, 사건 생성 금지 — 헤더로 LLM에도 강제한다.
    """
    exceptional = [p for p in profiles if p.mode != "default_gradient"]
    if not exceptional:
        return []
    out = [
        "[대운 발현 진행 신호 — 서술 전용(점수·순위·시기·확신도 변경 금지). 기본 경향은 '계기 "
        "선인식 → 현실화 누적'이지만, 아래 대운은 엔진 판정 예외 모드가 그 순서보다 우선한다]",
    ]
    for p in exceptional:
        desc = _PROGRESSION_MODE_DESC.get(p.mode, "")
        out.append(
            f"{p.ganji} 대운({p.start_age}세~): {PROGRESSION_MODE_KO.get(p.mode, p.mode)}"
            + (f" — {desc}" if desc else "")
        )
    out.append(
        "서술 규칙: ①위 모드는 발현 '순서·양상'의 경향이지 사건·길흉 확정이 아님 ②'전반에는 "
        "천간 사건, 후반에는 지지 사건'처럼 연차로 나눠 단정하지 말 것 ③구체 발동 시점은 세운·"
        "월운 활성화가 결정한다고 안내할 것."
    )
    return out


def marriage_age_prior_lines(result: ManseV2Result) -> list[str]:
    """[혼기 경향 — static prior] MT6 배우자성 위치 기반 광역 혼기 경향(특정 시기 아님).

    활성 프로파일 aux(mt6_age_prior)가 켜졌을 때만 산출한다 — default 프로파일은 빈 목록(출력 불변).
    event trigger가 아니므로 특정 연·월을 말하지 않고, 실제 시점은 운이 결정함을 명시한다.

    Args:
        result: 만세 결과(pillars·gender).

    Returns:
        혼기 경향 1~2줄(미상·미산출·프로파일 off면 빈 목록).
    """
    if not active_marriage_aux().get("mt6_age_prior"):
        return []
    prior = analyze_marriage_age_prior(result)
    if prior.band == "unknown" or not prior.positions:
        return []
    band_ko = _MARRIAGE_AGE_BAND_KO.get(prior.band, prior.band)
    note = (
        f"[혼기 경향(static prior·특정 시기 아님)] 배우자성이 {'·'.join(prior.positions)}에 "
        f"드러나 {band_ko}. 실제 결혼 시점은 운(대운·세운)이 결정하며, 넓은 경향으로만 참고."
    )
    lines = [note]
    if "spouse_palace_direct" in prior.structural_flags and prior.band != "spouse_palace_direct":
        lines.append(
            "  (일지=배우자궁에 배우자성 직접 — 결혼이 본인 현실·배우자궁 문제로 직접 들어오는 결)"
        )
    if prior.confidence == "low":
        lines.append("  ※ 성별 미상 — 약한 참고(혼기 보정 미사용)")
    return lines


# ── 외적 인상·매력 신호 표면화 (SSOT: doc/v2_2/EXTERNAL_IMPRESSION_SIGNAL.md) ──
# 노출은 intent allowlist·gender·band로 게이트한다. '이직운/건강운'에 매력 신호가 튀어나오지 않게
# 관계·총운·명식분석·외모 직접질문에서만 표면화한다. 미해당 시 완전 무언급(빈 목록).
_IMPRESSION_ALLOW_DOMAINS = frozenset({Domain.RELATIONSHIP, Domain.GENERAL})
_IMPRESSION_SUPPRESS_DOMAINS = frozenset(
    {Domain.CAREER, Domain.WEALTH, Domain.HEALTH, Domain.EDUCATION, Domain.RELOCATION}
)
# 사용자가 직접 외모·매력·인상을 물으면 suppress를 무시하고 노출한다.
_IMPRESSION_DIRECT_KEYWORDS = (
    "외모", "매력", "첫인상", "생김새", "인상이", "이성에게", "끌림", "끌리는", "호감형",
    "도화", "분위기 있", "예쁘", "잘생", "이쁘", "얼굴",
)


def _is_appearance_question(question: str) -> bool:
    """질문이 외모·매력·인상을 직접 묻는가 — suppress 도메인에서도 노출 허용하는 예외 판정."""
    q = question or ""
    return any(kw in q for kw in _IMPRESSION_DIRECT_KEYWORDS)


def external_impression_lines(
    profile: ExternalImpressionProfile, intent: IntentJson, question: str = "",
) -> list[str]:
    """[외적 인상·분위기 구조] — 인상·표현매력·관계적 끌림 보조 신호(미모 단정 아님).

    노출 게이트: ①band(none이면 무언급, weak는 직접질문에만) ②intent allowlist(관계·총운·명식분석·
    외모 직접질문만, 커리어·재물·건강 등은 억제) ③성별 미상(confidence=low)이면 직접질문·strong일
    때만. 하드 가드(용모 우열·성적 매력·성별 고정 표현 금지)를 지시문에 명시하되, 재미 위주 정보라
    과잉 면책 없이 가벼운 톤으로 서술하도록 안내한다.

    Args:
        profile: analyze_external_impression 결과.
        intent: 확정 intent(도메인·질문유형).
        question: 원문 질문(외모 직접질문 예외 판정용).

    Returns:
        LLM 입력 지시문 목록. 노출 조건 미충족 시 빈 목록(완전 무언급).
    """
    if profile.band == "none":
        return []
    direct = _is_appearance_question(question)
    domain = intent.domain
    allow = (
        direct
        or domain in _IMPRESSION_ALLOW_DOMAINS
        or intent.query_type is QueryType.CHART_ANALYSIS
    )
    suppressed = domain in _IMPRESSION_SUPPRESS_DOMAINS and not direct

    if profile.band in ("notable", "strong"):
        if suppressed or not allow:
            return []
        if profile.confidence == "low" and not (direct or profile.band == "strong"):
            return []
    elif profile.band == "weak":
        if not direct:  # 약한 신호는 사용자가 직접 물을 때만, 매우 조심스럽게.
            return []
    else:
        return []

    scored = [s for s in profile.signals if s.tier != "note"]
    notes = [s for s in profile.signals if s.tier == "note"]
    lines = [
        "[외적 인상·분위기 구조 — 원국 구조(운 미반영). 외모를 '단정'하지 말고 첫인상·분위기·"
        "표현 매력·관계적 끌림의 방향으로만 서술하라. 용모의 우열이나 선정적·성별 고정 표현은 쓰지 "
        "말 것. 재미 위주의 가벼운 정보이니 과한 면책·경고 반복 없이 긍정적으로 녹여 풀되, 강도는 "
        "단정하지 말 것]",
    ]
    for s in scored:
        line = f"- {s.modern_ko}"
        if s.note:
            line += f" (참고: {s.note})"
        lines.append(line)
    for s in notes:
        lines.append(f"- (참고) {s.modern_ko}")
    return lines


# ── 문서·계약 주의점(2026-08-10 승인 P2) — 대중 콘텐츠형 자기점검을 엔진 판정으로 번역 ──
# 조건 성립 시에만 블록 생성(미성립=None → 기존 프롬프트 byte 불변). 서술 전용(inert) —
# 점수·후보·간지·판정에 영향 없음. 약세 임계 12%는 relation_target_ten_god_rules의
# weak_group_power_lt와 동일 기준(계층 간 정합), 과다 임계 30%는 십성군 세력 강 관례 재사용.
_RESOURCE_EXCESS_PCT = 30.0
_RESOURCE_WEAK_PCT = 12.0
# 일간 오행을 생(生)하는 오행 = 인성 오행(生我者印).
_RESOURCE_ELEMENT_OF: dict[str, str] = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}
_UNFAVORABLE_ROLES = frozenset({"기신", "구신"})


def document_caution_block(result: ManseV2Result) -> str | None:
    """문서·계약형 질문용 개인화 주의점 블록. 조건 미성립이면 None(무주입).

    스크립트형 대중 콘텐츠가 "네 사주가 인성 과다인지/뿌리가 있는지 스스로 봐라"로
    시청자에게 맡기는 두 자기점검을, 엔진이 이미 계산한 값(십성군 세력·용기신 역할)으로
    확정해 주입한다 — ①인성 과다(+기신/구신이면 강조)=계약이 나를 묶는 문서가 될 수 있음
    ②인성 약세=성사보다 동요·지연 배경. 원시 퍼센트·내부 코드는 본문에 노출하지 않는다
    (모듈 누출 계약). 마무리 계약 준수 — 위치 고정('말미에' 류) 없이 본문에 녹여 쓰게 한다.

    Args:
        result: 만세 결과(force_analysis·pillars·yongsin_analysis 사용, 전부 optional 안전).

    Returns:
        주의점 블록 문자열, 또는 조건 미성립 시 None.
    """
    fa = result.force_analysis
    if fa is None:
        return None
    resource_pct = float(fa.ten_gods.groups.get("resource", 0.0))

    unfavorable = False
    if result.pillars is not None and result.pillars.day.stem:
        from saju_shared_types.constants import STEM_ELEMENT, Stem

        from .event_scoring import favorability_map

        try:
            day_el = str(STEM_ELEMENT[Stem(result.pillars.day.stem)])
        except (KeyError, ValueError):
            day_el = ""
        resource_el = _RESOURCE_ELEMENT_OF.get(day_el, "")
        role = favorability_map(result).get(resource_el, "")
        unfavorable = role in _UNFAVORABLE_ROLES

    lines: list[str] = []
    if resource_pct >= _RESOURCE_EXCESS_PCT:
        line = (
            "- 이 명식은 문서·자격·후견의 기운(인성)이 두텁게 자리한 구조다. 새 계약·문서가 "
            "기회이면서 동시에 나를 묶는 의무가 될 수 있으니, 도장을 찍기 전 조항·기간·해지 "
            "조건을 점검하는 태도를 함께 권하라."
        )
        if unfavorable:
            line += (
                " 특히 이 기운은 이 명식에서 부담으로 작동하기 쉬운 축이라, 계약의 실속"
                "(비용·의무·구속 기간)을 따져보도록 안내하라."
            )
        lines.append(line)
    elif resource_pct < _RESOURCE_WEAK_PCT:
        lines.append(
            "- 이 명식은 문서·자격·후견의 기운(인성)이 얇게 자리한 구조다. 문서·계약 신호가 "
            "와도 단번의 성사보다 흔들림·지연을 거치기 쉬우니, 확정 전에 보완 장치(재검토 "
            "시간·믿을 만한 검토자)를 두는 태도를 권하라."
        )
    if not lines:
        return None
    return (
        "[문서·계약 주의점 — 엔진 판정]\n"
        + "\n".join(lines)
        + "\n서술 지침: 이 주의점은 별도 경고 섹션이나 고정 마무리 문구로 만들지 말고, "
        "계약·문서를 다루는 대목의 본문 흐름에 자연스럽게 한 번만 녹여 서술하라."
    )


# 문서운 물상 어휘(2026-08-10 P4) — 서술 전용. 물상·서사 풍부화 정책(풀이 품질 정책)의
# 문서 도메인 적용. 은유는 장식이며 근거가 아니다 — 신호 없는 대목에서 은유로 사건을
# 만들어내는 것을 지시문 자체가 차단한다. 감수 대상(어휘 추가·삭제는 감수에서).
DOCUMENT_IMAGERY_DIRECTIVE = (
    "[문서운 물상 어휘 — 서술 전용]\n"
    "계약·문서·자격 신호를 서술할 때 추상어로 끝내지 말고 물상 은유를 한두 번 활용하라 — "
    "'도장을 쥐는 흐름', '멈춰 있던 문서가 움직이기 시작한다', '기존 판을 갈아끼우는 교체' 등. "
    "은유는 엔진 신호가 있는 대목에서만 쓰고, 은유를 근거 삼아 데이터에 없는 사건·시기를 "
    "만들어내지 말 것(성사·당첨 단정 금지 규칙은 그대로 적용)."
)

_FAVORABLE_ROLES = frozenset({"용신", "희신"})


def document_contrast_block(result: ManseV2Result) -> str | None:
    """문서·계약형 질문용 대비(contrast) 블록 — 인성이 이롭게 작동하는 명식 한정(P3).

    주의점(document_caution_block)의 보완 서사다: 같은 계약·문서 신호가 명식에 따라
    '묶는 의무'가 되기도 '기회·결실'이 되기도 한다는 대비를, 이 명식의 계산된 역할
    (인성 오행=용신/희신)과 알맞은 세력(과다·약세 아님)을 근거로 한 문장 짚게 한다.
    주의점 조건(과다/약세)이 성립하면 None — 두 블록은 상호 배타(중복 서술 방지).
    서술 전용(inert), 원시 퍼센트·내부 코드 미노출, 위치 고정 문구 없음.

    Args:
        result: 만세 결과(force_analysis·pillars·yongsin_analysis 사용, optional 안전).

    Returns:
        대비 블록 문자열, 또는 조건 미성립 시 None.
    """
    fa = result.force_analysis
    if fa is None or result.pillars is None or not result.pillars.day.stem:
        return None
    resource_pct = float(fa.ten_gods.groups.get("resource", 0.0))
    if not (_RESOURCE_WEAK_PCT <= resource_pct < _RESOURCE_EXCESS_PCT):
        return None

    from saju_shared_types.constants import STEM_ELEMENT, Stem

    from .event_scoring import favorability_map

    try:
        day_el = str(STEM_ELEMENT[Stem(result.pillars.day.stem)])
    except (KeyError, ValueError):
        return None
    role = favorability_map(result).get(_RESOURCE_ELEMENT_OF.get(day_el, ""), "")
    if role not in _FAVORABLE_ROLES:
        return None
    return (
        "[문서·계약 대비 관점 — 엔진 판정]\n"
        "- 이 명식은 문서·자격·후견의 기운(인성)이 이롭게 작동하는 축이며 세력도 알맞게 "
        "자리한다. 같은 계약·문서 신호가 어떤 명식에서는 나를 묶는 의무가 되기 쉽지만, 이 "
        "명식에서는 기회·결실 쪽으로 발현되기 쉽다 — 계약을 다룰 때 이 대비를 근거와 함께 "
        "한 문장으로 짚어 주라(당첨·성사 단정은 금지, 발현되기 쉬운 방향으로만).\n"
        "서술 지침: 별도 섹션·고정 마무리 문구로 만들지 말고 관련 대목의 본문 흐름에 "
        "자연스럽게 한 번만 녹여 서술하라."
    )
