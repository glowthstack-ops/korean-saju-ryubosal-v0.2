"""용신 작동역할 — 조건부 라벨 정책·조건문 템플릿 (Phase 1, experimental).

YONGSIN_OPERATIONAL_ROLE_SPEC §4-1/§6. 여기의 문구·정책은 확정 명리 상수가 아니라
**튜닝 대상(experimental)** 이다. candidates.py 에 문구를 직접 박지 말고 이 모듈에서만 관리한다.

중요 정책(데굴님 승인): operational_role 은 단순 역할명이 아니라 합성 라벨이 될 수 있다.
"조건부 희신/병" 은 favorable 라벨이 아니라 mixed/conditional 라벨이다 — 향후 scoring 연결 시
"희신" 부분문자열 파싱을 금지하고, 반드시 OPERATIONAL_ROLE_CLASS(또는 exact enum)로만 해석한다.
"""

from __future__ import annotations

from typing import TypedDict


class ConditionTemplate(TypedDict):
    positive_when: list[str]
    negative_when: list[str]
    note: str


# 작동역할 라벨 → 길흉 해석 클래스. 향후 scoring 은 문자열 부분파싱 대신 이 mapper 만 경유한다.
# (Phase 1~2 에서는 생성·노출만 — 아직 어떤 scoring 도 이 표를 소비하지 않는다.)
#   ★ "조후보조신" 은 favorable 보조약이며 primary yongsin(용신)과 동일 가중으로 취급하지 않는다.
#     향후 scoring 연결 시 보조약 가중(용신급 미만)으로만 반영할 것.
OPERATIONAL_ROLE_CLASS: dict[str, str] = {
    "용신": "favorable",
    "희신": "favorable",
    "기신": "unfavorable",
    "구신": "unfavorable",
    "한신": "neutral",
    "조건부 희신/병": "conditional",  # ★ 단순 희신(favorable) 처리 금지 — mixed
    "조건부 제살보조": "conditional",
    "조후보조신": "favorable",  # 보조약 — 용신급 가중 금지(위 주석)
}

# 조후 역행(병) 방향별 negative_when 사유(Phase 2, _climate_harmful 연결).
CLIMATE_HARMFUL_REASON: dict[str, str] = {
    "cold": "한습 심화(조후 역행)",
    "hot": "조열 심화(조후 역행)",
}

# 官殺 합 맥락 사유(Phase 3, resolve_stem_hap·관살혼잡 연결). 텍스트만 config; 배치(positive/
# negative/note)는 _annotate_officer_hap_context 의 규칙으로 결정한다(데굴님 추가조건 1~3):
#   bind(합반)·transform_confirmed = 완화/보강 → positive 또는 note
#   contend(쟁합)·mixed_officer_killing(관살혼잡) = 불안정/탁 → negative
#   away(합거) = note 중심, 단 官이 병이면 완화 맥락을 positive 로
OFFICER_HAP_REASON: dict[str, str] = {
    "bind": "정관/칠살이 천간합으로 묶여(합반) 官 압박 직접성 완화",
    "contend": "쟁합(여러 글자가 다툼)으로 官 합력 약화·작용 불안정",
    "away": "官이 합거(合去)로 끌려가 작용 약화",
    "transform_confirmed": "官이 합화(化)로 印 기류 전환 — 살인상생 흐름 보강(맥락)",
    "mixed_officer_killing": "정관+칠살 혼잡(官殺混雜) — 탁(濁), 거살유관 등 정리 필요",
}

# 官殺 외 십성(財/印/食傷/比劫) 합 맥락 도메인 라벨(#7, experimental). 도메인만 두고 길흉(positive/
# negative/note 배치)은 _annotate_ten_god_hap_context 가 operational role class 로 정한다.
# 官殺은 OFFICER_HAP_REASON(Phase 3) 유지 — 여기 미포함(중복 enrich 방지).
TEN_GOD_HAP_REASON: dict[str, str] = {
    "wealth": "財(재물·계약·현실·이성)",
    "resource": "印(문서·학업·자격·보호)",
    "output": "食傷(표현·성과·이동·기술)",
    "peer": "比劫(자립·경쟁·동료·분탈)",
}
# 합 작용 모드별 공통 문구(중복 절감). 배치(positive/negative/note)는 role class 가 결정.
TEN_GOD_HAP_MODE_PHRASE: dict[str, str] = {
    "bind": "합반으로 묶임",
    "contend": "쟁합 — 다툼·분산·불안정",
    "away": "합거로 끌려감·빠짐",
    "transform": "합화 전환 기류(역할 전환 아님·맥락)",
}

# 용신 작동성(operability) penalty 계수(Phase 4a, experimental). 감점만 — base 1.0 에서 곱연산,
# 최대 1.0. 정인/투간/통근은 가산이 아니라 'penalty 면제'. 적용 순서 고정: no_transmit→no_root→
# pyeonin_only. factors 에는 stable key 를 담고, 표시 문구는 OPERABILITY_REASON 으로 매핑한다.
OPERABILITY_PENALTY: dict[str, float] = {
    "no_transmit": 0.15,    # 용신 투간(透干)無
    "no_root": 0.20,        # 용신 통근(通根)無
    "pyeonin_only": 0.10,   # 印 용신이 편인(偏印)만 투출 — 정인보다 불안정
    "yongsin_void": 0.20,   # 용신 통근 지지가 전부 공망(#6a) — 뿌리 허
    "yongsin_clash": 0.15,  # 용신 통근 지지가 충(六沖)을 받음(#6a) — 작동 불안정
    "yongsin_isolation": 0.15,  # 생조부재+단일출처+손상동반 복합 고립(#6b-1)
    "yongsin_bound": 0.15,  # 용신 투출 천간이 합반/쟁합으로 묶임(#6b-2) — 작동 지연
}
OPERABILITY_REASON: dict[str, str] = {
    "no_transmit": "용신이 천간에 투출 안 됨 — 작동성 약화",
    "no_root": "용신이 지지에 통근 없음 — 무력",
    "pyeonin_only": "印 용신이 편인 위주 — 안정성 낮음(정인 부재)",
    "yongsin_void": "용신 뿌리가 공망 — 있어도 허하거나 늦게 작동",
    "yongsin_clash": "용신 뿌리가 충을 받음 — 작동 불안정",
    "yongsin_isolation": "용신이 생조·동류 없이 고립 + 손상 동반 — 작동 위태",
    "yongsin_bound": "용신 투출 천간이 합반/쟁합으로 묶임 — 작동 지연·불안정",
}

# operability 수치 → 표시용 작동성 밴드(Phase 5a, experimental). **확정 등급이 아니라 표시용 밴드.**
# operability < low → '낮음', < mid → '보통', else '높음'. (표준 0.595=낮음, 4a 0.85=보통.)
OPERABILITY_LEVEL_BANDS: dict[str, float] = {"low": 0.7, "mid": 0.9}

# operability factor key → LLM 프리픽스용 한국어 압축 라벨(Phase 5a). stable key 는 내부 summary
# 에만 두고, 프롬프트에는 이 압축 표현을 노출한다(LLM 즉시 이해·토큰 절약). 미등록 key 는 그대로.
OPERABILITY_FACTOR_SHORT: dict[str, str] = {
    "no_transmit": "투간無",
    "no_root": "통근無",
    "pyeonin_only": "편인만",
    "gyeokgak_zimao": "子卯 격각",
    "yongsin_void": "공망",
    "yongsin_clash": "충",
    "yongsin_isolation": "고립",
    "yongsin_bound": "합반",
}

# operational/legacy 역할 → shadow 점수 가중(#9a, experimental). 계산·검증 전용·실제 scoring 미소비.
# 계층: 용신 > 희신 > 조후보조신(보조약) > 조건부 제살보조(약 보조) > 조건부 희신/병(★mixed·0)·한신
# > 구신 > 기신. 모든 OperationalRole enum 포함. exact label lookup 만(substring 금지). 미등록 label
# 은 fail-fast(KeyError) — 조용히 0 처리 금지.
SHADOW_ROLE_WEIGHT: dict[str, float] = {
    "용신": 1.0,
    "희신": 0.6,
    "조후보조신": 0.35,
    "조건부 제살보조": 0.1,
    "조건부 희신/병": 0.0,
    "한신": 0.0,
    "구신": -0.6,
    "기신": -1.0,
}
# 후보 운(運) 오행 = 간지 천간·지지 표면 오행 평균 가중(#9b, experimental). 지장간은 미포함.
SHADOW_PERIOD_ELEMENT_WEIGHT: dict[str, float] = {"stem": 0.5, "branch": 0.5}

# 운세 길흉 '표현 제한'(Phase 5b-2a, experimental) — **점수·랭킹 불변·문장 강도만 clamp.**
# legacy 밴드(±EXPRESSION_BAND) × shadow 가중으로 표현 등급 결정. 등급별 1줄 가이드.
# rollback 안전장치: False 면 [표현 제한] 라인 미노출(즉시 off). 계산·shadow는 영향 없음.
EXPRESSION_CLAMP_ENABLED: bool = True
EXPRESSION_BAND: float = 0.3  # legacy 가중 positive/neutral/negative 경계
EXPRESSION_OPERABILITY_THRESHOLD: float = 0.9  # 용신운 작동성 부기 임계
EXPRESSION_GUIDANCE: dict[str, str] = {
    "길": "유리한 운",
    "조건부·유보": "단순 길운 단정 금지 — 받침 있을 때만 긍정",
    "조건부·유보+주의": "단순 길운 금지·부담 동반 가능",
    "보조 긍정": "보조적으로 도움(주용신급 아님)",
    "주의 속 일부 완화": "주의운이나 과다 제어로 일부 완화",
    "주의": "다소 불리",
    "주의/흉": "불리·주의",
    "중립": "중립",
}

# 도메인별 표현 제한(Phase 5b-2b, experimental) — expression_class를 도메인 언어로 '번역만'.
# 점수·랭킹 불변. 도메인×등급 문구만(십성·오행 하드코딩 금지 — 십성은 5b-1 운 line이 담당).
# 등록 domain은 EXPRESSION_CLASSES 6종 전부 필수(누락=config 오류·완전성 테스트).
# 미상/미매핑 domain은 base fallback.
EXPRESSION_CLASSES: tuple[str, ...] = (
    "길", "조건부·유보", "보조 긍정", "주의 속 일부 완화", "주의/흉", "중립",
)
DOMAIN_EXPRESSION_PHRASE: dict[str, dict[str, str]] = {
    "career": {
        "길": "직업·직책 흐름 유리", "조건부·유보": "책임·압박·조직 이슈 동반",
        "보조 긍정": "활력·표현 보조 도움", "주의 속 일부 완화": "직무 부담 일부 정리",
        "주의/흉": "규정·책임 부담 주의", "중립": "직업 흐름 평이",
    },
    "wealth": {
        "길": "재물·계약 흐름 유리", "조건부·유보": "계약·현실 부담 동반",
        "보조 긍정": "현금흐름 보조 도움", "주의 속 일부 완화": "지출 부담 일부 통제",
        "주의/흉": "손재·과지출 주의", "중립": "재물 흐름 평이",
    },
    "relationship": {
        "길": "관계·인연 흐름 유리", "조건부·유보": "감정 과다·관계 압박 가능",
        "보조 긍정": "매력·표현 보조 도움", "주의 속 일부 완화": "관계 긴장 일부 해소",
        "주의/흉": "관계 갈등·거리감 주의", "중립": "관계 흐름 평이",
    },
    "relocation": {
        "길": "이동·이사 흐름 유리", "조건부·유보": "계약 조건·방향성 확인 필요",
        "보조 긍정": "이동 추진 보조 도움", "주의 속 일부 완화": "이동 변수 일부 정리",
        "주의/흉": "이동·계약 변수 주의", "중립": "이동 흐름 평이",
    },
    "study_document": {
        "길": "학업·자격 흐름 유리", "조건부·유보": "문서·심리 부담 동반",
        "보조 긍정": "학습·표현 보조 도움", "주의 속 일부 완화": "문서 지연 일부 진척",
        "주의/흉": "문서·시험 차질 주의", "중립": "학업 흐름 평이",
    },
}
# 관찰용 결합 스케일(#9b, experimental). shadow_observation_score = score + fav_delta×SPAN(클램프).
# **실제 score 아님 — 유불리 관찰값.** 유불리 ±1 스윙 = score ±30 이동.
SHADOW_SCORE_SPAN: float = 30.0

# 운(運) 입자 오행이 원국에서 이 operational role 일 때 LLM 에 붙일 guard 문구(Phase 5b-1).
# **설명 guard 전용**(experimental) — 점수·랭킹 불변. 라벨별 문구 구분(조건부 희신/병=단순 길운
# 금지, 조후보조신=보조 긍정, 조건부 제살보조=조건부 제어). 키 없는 role 은 미생성(정적 해석 유지).
LUCK_OPERATIONAL_GUARD: dict[str, str] = {
    "조건부 희신/병": (
        "정적 희신성은 있으나 원국 과다·병 — 단순 길운 단정 금지"
        "(용신·조후 받침 시에만 긍정 작동)"
    ),
    "조후보조신": "주용신은 아니나 기후·균형 보조로 작동(받침 역할)",
    "조건부 제살보조": "과다 오행 제어 가능하나 일간 설기·용신 훼손 주의(조건부)",
}

# 격각(비인접) 형/해 통관손상 allowlist(Phase 4b, experimental). 비인접 형/해 전체가 아니라
# 용신 통관 path 를 직접 손상하는 관계만 화이트리스트로 시작(첫 대상 子卯刑). 이벤트/관계 판정은
# 건드리지 않고 operability penalty 전용. 인접쌍은 기존 이벤트 레이어 영역이므로 여기서 제외.
GYEOKGAK_ALLOWLIST: list[dict] = [
    {
        "factor": "gyeokgak_zimao",
        "branches": ("子", "卯"),          # 격각으로 성립하는 두 지지
        "yongsin_elements": ("木",),       # 통관 손상이 직접 닿는 용신 오행(水生木 수혜자)
        "weight": 0.30,                    # gyeokgak_operability_weight(D1 기본값)
        "reason": "子卯 격각형 — 水生木 통관이 매끄럽지 않음(작동성 손상)",
    },
]

# 조건부 라벨별 기본 조건문 템플릿(서술). 테스트는 문장 전체가 아니라
# 비어있지 않음/핵심 키워드 포함 정도로만 단언할 것(문구 수정 시 회귀 파손 방지).
CONDITION_TEMPLATES: dict[str, ConditionTemplate] = {
    "조건부 희신/병": {
        "positive_when": [
            "용신(생할 대상)이 투간/통근해 살아있음",
            "용신을 극하는 기신이 약함",
        ],
        "negative_when": [
            "해당 오행 과다(임계 초과)",
            "용신이 부실·고립",
            "원국에서 이미 병(病)으로 작동",
        ],
        "note": (
            "생용신이라 이론상 희신성은 있으나 원국에서 이미 과다·병이므로 "
            "추가 유입을 자동 길신으로 처리 금지"
        ),
    },
    "조건부 제살보조": {
        "positive_when": [
            "과다 오행을 제어",
            "일간을 과하게 설기하지 않음",
        ],
        "negative_when": [
            "일간 설기 과다",
            "용신 훼손",
            "스스로 약해 제어력 부족",
        ],
        "note": (
            "과다 오행 제어 보조 가능성이 있으나 일간 설기·용신 훼손 위험이 병존"
        ),
    },
    "조후보조신": {
        "positive_when": [
            "한습/조열 월령 기후 보정",
            "일간 유지·온난(또는 윤택) 공급",
        ],
        "negative_when": [
            "조후 오행이 무력·고립",
            "충극으로 조후 기능 상실",
        ],
        "note": (
            "단순 한신이 아니라 한습 제거·일간 유지에 필요한 조후 보조 약 "
            "(용신급 가중으로 취급 금지)"
        ),
    },
}

# Shadow Validation Harness(검증 도구, experimental) — legacy vs shadow 차가 큰 케이스 WARN 임계.
# **fail 이 아니라 top-N 리뷰 표시용.** 운영 scoring 미연결(검증 전용).
SHADOW_WARN_SCORE_DELTA: int = 18   # abs(score_delta) ≥ → WARN
# rank WARN 은 풀 크기 상대화 — threshold = max(ABS, ceil(level_pool × RATIO)).
# 대운 풀(≈10)은 abs=3, 세운 풀(≈240)은 ceil(12)로 잔흔 제거.
# WARN if abs(rank_delta_level) ≥ threshold.
SHADOW_WARN_RANK_DELTA_ABS: int = 3        # 절대 하한
SHADOW_WARN_RANK_DELTA_RATIO: float = 0.05  # 풀 대비 비율 하한

# Scoring 반영 Phase 1a(operational adjusted score) — **감점 계열 2 component 만·산출만.**
# 마스터 off면 후처리 미호출(byte-identical). component 게이트. spec §14. 랭킹/LLM 미반영(1a).
SCORING_OPERATIONAL_SHADOW_ENABLED: bool = False           # 마스터 게이트(호출부에서 확인)
# component on(2026-06-24 오픈) — 1c guard penalty 산정에 필요. **score/rank 미변경**(penalty 는 1c
# 태그 결정에만 소비·1a sidecar 는 SHADOW_ENABLED off 라 미실행). B 는 임계 −6 에서 사실상 미발동.
SCORING_OPERATIONAL_COMPONENTS: dict[str, bool] = {
    "conditional_byeong_downgrade": True,                  # A: 조건부 희신/병 downgrade
    "low_operability_yongsin": True,                       # B: 낮은 operability 용신운 보정
}
SCORING_OPERATIONAL_COEF: dict[str, float] = {             # experimental — 33차트로 튜닝
    "byeong_max_penalty": 12.0,
    "low_op_max_penalty": 10.0,
    "op_threshold": 0.9,
    "adjusted_floor_ratio": 0.5,                           # adjusted ≥ ceil(legacy×0.5)
}

# Scoring Phase 1b(adjusted rank 실험) — sub-flag 독립·하네스/리포트 전용·서비스 미연결.
# 실제 .score/rank/reduce_candidates/LLM 불변 — adjusted_rank 는 관찰용. spec §14-8.
SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED: bool = False
SCORING_OPERATIONAL_RANK_TOPN: int = 10            # top-N 이탈 기준(level별·CLI override 가능)

# Scoring Phase 1c-α(rank guard 태그) — 순위·score·reduce 불변·career 한정. spec §14-9.
# 게이트 조합 전부 만족 시에만: APPLY_ENABLED ∧ rank_guard ∧ domain∈APPLY_INTENTS ∧ component≥1 ∧
# operational_score_delta ≤ −penalty_threshold. master off = byte-identical.
# 오픈 활성화(2026-06-24 데굴님 확정) — 5 핵심 intent rank guard 운영 적용. 되돌리려면 False 한 줄.
# 순위·.score·reduce 불변·본문 우선 헤드룸 가드·과한 긍정만 차단(흉 과장 X).
SCORING_OPERATIONAL_APPLY_ENABLED: bool = True
SCORING_OPERATIONAL_APPLY_MODE: dict[str, bool] = {
    "rank_guard": True, "near_tie_demotion": False,  # near_tie 는 1c-β 후속(미구현)
}
# 표현 key 기준 allowlist(domain_to_expression_key 정규화). master off 면 inert.
# study_document = Domain.EDUCATION.value("education") 정규화 후 key.
SCORING_OPERATIONAL_APPLY_INTENTS: list[str] = [
    "career", "wealth", "relationship", "relocation", "study_document",
]
SCORING_OPERATIONAL_APPLY_COEF: dict[str, int] = {
    "penalty_threshold": 6, "max_guards": 3,
    "near_tie_rank_window": 3, "near_tie_score_window": 5,   # 1c-β 후속(미사용)
    "max_demotion_cap": 2, "topn_change_limit": 1,
}
# 태그 문구(penalty 유래 2종) — "흉" 단정이 아니라 **과한 긍정만 차단**.
SCORING_OPERATIONAL_GUARD_PHRASE: dict[str, str] = {
    "conditional_byeong_downgrade": "[해석 주의] 조건부 희신/병 — 과한 긍정 금지",
    "low_operability_yongsin": "[해석 주의] 용신 작동성 낮음 — 강한 길운 단정 금지",
}
# 기존 caution_note 가 이미 '과대긍정 차단' 의미를 담으면 reason 만 append(지시문 중복 제거).
SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT: dict[str, str] = {
    "conditional_byeong_downgrade": "[해석 주의] 조건부 희신/병",
    "low_operability_yongsin": "[해석 주의] 용신 작동성 낮음",
}
# 기존 caution 에 이 마커가 있으면 '과한 긍정 금지' 지시문 중복 → compact 사용. "좋은" 단독 등
# 과탐지 위험 마커는 금지(실측 기반만).
SCORING_OPERATIONAL_REDUNDANCY_MARKERS: list[str] = [
    "과하게 단정", "과한 긍정", "단정하지 말", "단정 말", "좋은 달로", "좋은 흐름으로 단정",
]
# 토큰 헤드룸 가드(spec §14-9) — **본문 우선·태그 후순위.** guard 태그가 토큰예산을 넘겨 본문
# 재축소(절단)를 유발하지 않게, payload 조립 후 실제 phrase 토큰을 순차 차감해 헤드룸 내에서만 부착.
# headroom = max_input_tokens − base_tokens − reserve. reserve 미상 시 HEADROOM_RESERVE(보수).
SCORING_OPERATIONAL_GUARD_TOKEN_EST: int = 25      # phrase 토큰 추정 실패 시 폴백 상한
# reserved_tokens 미전달 시 system+trailing 보수 예약.
SCORING_OPERATIONAL_HEADROOM_RESERVE: int = 1500
