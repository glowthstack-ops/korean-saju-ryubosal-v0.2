"""용신 작동역할 — 조건부 라벨 정책·조건문 템플릿 (Phase 1, experimental).

YONGSIN_OPERATIONAL_ROLE_SPEC §4-1/§6. 여기의 문구·정책은 확정 명리 상수가 아니라
**튜닝 대상(experimental)** 이다. candidates.py 에 문구를 직접 박지 말고 이 모듈에서만 관리한다.

중요 정책(데굴님 승인): operational_role 은 단순 역할명이 아니라 합성 라벨이 될 수 있다.
"조건부 희신/병" 은 favorable 라벨이 아니라 mixed/conditional 라벨이다 — 향후 scoring 연결 시
"희신" 부분문자열 파싱을 금지하고, 반드시 OPERATIONAL_ROLE_CLASS(또는 exact enum)로만 해석한다.
"""

from __future__ import annotations

import os as _os
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
    "조건부 한신/병": "conditional",  # 과다 병이 한신으로 강등된 케이스 — 중첩 유입 시 기신성
    "조건부 제살보조": "conditional",
    "조후보조신": "favorable",  # 보조약 — 용신급 가중 금지(위 주석)
}


def role_class(label: str | None) -> str:
    """역할 라벨 → 길흉 해석 클래스 — mapper 경유 단일 진입점(spec §10-2 #4).

    OPERATIONAL_ROLE_CLASS 미등록 라벨(None·빈 문자열 포함)은 "unknown"을 반환한다.
    호출부는 부분문자열 파싱·임시 튜플 묶음 대신 이 함수(또는 exact enum 비교)만 쓴다.
    """
    return OPERATIONAL_ROLE_CLASS.get(label or "", "unknown")


def is_favorable_role(label: str | None) -> bool:
    """역할 라벨이 favorable 클래스(용신·희신·조후보조신)인지 — mapper 경유."""
    return role_class(label) == "favorable"


def is_unfavorable_role(label: str | None) -> bool:
    """역할 라벨이 unfavorable 클래스(기신·구신)인지 — mapper 경유."""
    return role_class(label) == "unfavorable"

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
    # #6c 투출 천간 자리 손상(2026-10-08 데굴님 승인: shadow 비교용 초기값 — 확정 수치 아님, 반복
    # 튜닝 금지). 복수 투출이면 (손상 자리 수 / 투출 자리 수) 비율을 곱한다. 좌하 지지가 용신
    # 통근이면 #6a 담당.
    "yongsin_stem_clash": 0.10,       # 투출 천간이 인접 천간과 천간충(甲庚·乙辛·丙壬·丁癸)
    "yongsin_stem_controlled": 0.10,  # 인접 천간 오행이 용신 오행을 극(같은 천간이 충이면 충만)
    "yongsin_seat_void": 0.10,        # 투출 천간의 좌하 지지 공망(비통근 좌하)
    "yongsin_seat_clash": 0.10,       # 좌하 지지가 六沖(비통근 좌하)
}
OPERABILITY_REASON: dict[str, str] = {
    "no_transmit": "용신이 천간에 투출 안 됨 — 작동성 약화",
    "no_root": "용신이 지지에 통근 없음 — 무력",
    "pyeonin_only": "印 용신이 편인 위주 — 안정성 낮음(정인 부재)",
    "yongsin_void": "용신 뿌리가 공망 — 있어도 허하거나 늦게 작동",
    "yongsin_clash": "용신 뿌리가 충을 받음 — 작동 불안정",
    "yongsin_isolation": "용신이 생조·동류 없이 고립 + 손상 동반 — 작동 위태",
    "yongsin_bound": "용신 투출 천간이 합반/쟁합으로 묶임 — 작동 지연·불안정",
    "yongsin_stem_clash": "용신 투출 천간이 옆 천간과 충 — 드러난 작동이 흔들림",
    "yongsin_stem_controlled": "용신 투출 천간이 옆 천간에 극을 받음 — 드러난 작동 약화",
    "yongsin_seat_void": "용신 투출 천간의 자리 지지가 공망 — 실린 곳이 허함",
    "yongsin_seat_clash": "용신 투출 천간의 자리 지지가 충 — 실린 곳이 흔들림",
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
    "yongsin_stem_clash": "천간충",
    "yongsin_stem_controlled": "천간극",
    "yongsin_seat_void": "좌하공망",
    "yongsin_seat_clash": "좌하충",
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
    "조건부 한신/병": 0.0,  # 한신과 동일 0 — 점수 계열 불변(서술 가드 전용)
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
    "조건부 한신/병": (
        "정적 한신이나 원국 과다·병 — 소량은 보조 가능하나 "
        "중첩 유입 시 기신성(불리)으로 서술, 길운 판정 금지"
    ),
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
    "조건부 한신/병": {
        "positive_when": [
            "소량 유입이 용신 통관 경로로 흡수됨",
            "용신(통관 오행)이 투간/통근해 살아있음",
        ],
        "negative_when": [
            "해당 오행 중첩 유입(천간·지지 동시 등)",
            "원국에서 이미 과다·병으로 작동",
            "통관 오행이 부실해 범람",
        ],
        "note": (
            "정적으로는 한신이나 원국에서 이미 과다·병 — 중첩 유입 시 "
            "기신성으로 서술하고 중립 한신으로 처리 금지"
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
    # near_tie(1c-β)는 구현 완료(scoring_operational.near_tie_demotion_order) —
    # 활성화는 누적 관찰 후 별도 승인(스펙 §14 1c-β). off = byte-identical.
    "rank_guard": True, "near_tie_demotion": False,
}
# 표현 key 기준 allowlist(domain_to_expression_key 정규화). master off 면 inert.
# study_document = Domain.EDUCATION.value("education") 정규화 후 key.
SCORING_OPERATIONAL_APPLY_INTENTS: list[str] = [
    "career", "wealth", "relationship", "relocation", "study_document",
]
SCORING_OPERATIONAL_APPLY_COEF: dict[str, int] = {
    "penalty_threshold": 6, "max_guards": 3,
    "near_tie_rank_window": 3, "near_tie_score_window": 5,   # 1c-β(near_tie_demotion_order)
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


# ── 희신 기능 어휘(2026-10-01 데굴님 승인 C) ──────────────────────────────────────────────
# 희신은 '용신 후보 2등'이 아니라 기능이 있어야 한다(生용신만으로 확정 금지 — 더 큰 불균형을 만들
# 수 있다). key 는 모델·추적·LLM 요약이 공유하는 stable key, 값은 노출 문구.
HEESIN_FUNCTION_KO: dict[str, str] = {
    "generate_yongsin": "生용신(용신을 생해 보강)",
    "protect_yongsin": "護용신(용신을 극하는 기신 제어)",
    "control_gisin": "制기신(과다·병 오행 제어)",
    "support_day_master": "방신(일간 방조)",
    "complete_flow": "유통(용신 설기 흐름 완성)",
    "restrain_day_master": "일간 억제·조후 보조",
    "climate_helper": "조후 보조",
    "bridge_support": "통관 보조",
}
# 모델 유형 → 희신 기능. food_rescue:* 는 접두 매칭(호출부). 미등록 모델은 정적 폴백(生용신).
MODEL_HEESIN_FUNCTION: dict[str, str] = {
    "support_day_master": "generate_yongsin",      # 용=비겁, 희=인성(인성이 비겁을 생)
    "resource_as_yongsin": "generate_yongsin",     # 용=인성, 희=관살(관인상생)
    "output_as_yongsin": "generate_yongsin",       # 용=식상, 희=비겁(비겁이 식상을 생)
    "eokbu_normal": "complete_flow",               # 용=식상, 희=재성(식상생재 유통)
    "wealth_breaks_resource": "restrain_day_master",  # 용=재성, 희=관성(일간 억제·조후)
    "resource_pattern_officer": "control_gisin",   # 용=관성, 희=재성(과다 인성 제어)
    "officer_controls_peer": "bridge_support",     # 용=관성, 희=식상(비겁→식상→재 통관)
    "resource_curbs_output": "support_day_master", # 용=인성, 희=비겁(방신)
    "food_rescue": "control_gisin",                # 용=비겁(통관), 희=재성(制印)
    "johu": "generate_yongsin",
    "dominant_one_element": "complete_flow",
    "pattern_sangsin": "generate_yongsin",
    "disease_remedy": "generate_yongsin",
    "bridge_tonggwan": "bridge_support",
}
# 같은 model_type 에 라벨이 둘인 경우 — 살인상생형(살중용인)은 희=비겁 방신.
MODEL_LABEL_HEESIN_FUNCTION: dict[str, str] = {
    "살인상생형(살중용인)": "support_day_master",
}

# ── 후보 부작용 감사(2026-10-01 데굴님 승인 A1 — 주석 전용, A2 계수는 플래그) ────────────────
# 한 오행은 여러 방향으로 작용한다(金은 木을 극하면서 水를 생). 후보가 생하는 오행이 과다·병이면
# feeds_excess, 후보가 극하는 오행이 용신·조후 필요신이면 controls_needed.
COLLATERAL_REASON: dict[str, str] = {
    "feeds_excess": "{el}({role})은 과다 {target}을 생함 — 부작용(과다 심화)",
    "controls_needed": "{el}({role})은 {target}({target_role})을 극함 — 부작용(필요 기운 손상)",
}
#: A2 — 부작용 후보의 모델 신뢰도 계수. 기본 OFF(주석만). 672 그리드 재스캔 보고 후 데굴님 확정.
COLLATERAL_SCORE_ENABLED: bool = False
COLLATERAL_PENALTY: float = 0.85

# ── 축 충돌·강등 게이트(2026-10-01 데굴님 승인 B) ────────────────────────────────────────
#: 조후 역행 강등(_climate_harmful → 용·희 부적격)을 기후 축 severe(|값|≥40)일 때만 적용.
#: 기본 OFF = 기존 동작(월령+분포 임계만). 그리드 비교 후 전환 여부 확정.
CLIMATE_DEMOTE_REQUIRE_SEVERE: bool = False

# ── 전왕 성립 조건(2026-10-01 데굴님 승인 E) ───────────────────────────────────────────────
#: 전왕(일행득기)은 압도 오행을 극하는 오행이 투간·통근 없이 부재할 때만 진(眞)전왕. 극 오행이
#: 남아 있으면 가(假)전왕으로 억부와 경쟁(종격 real/pseudo 와 같은 패턴). 기본 OFF.
DOMINANT_REQUIRE_NO_CONTROLLER: bool = False
#: 극 오행 '잔존' 판정 임계(월령 보정 분포 %). 이 미만이면 부재로 본다(투간 여부는 호출부 보강).
DOMINANT_CONTROLLER_PRESENT_PCT: float = 8.0

# ── C1 특수격↔용신 정합(2026-10-07 데굴님 승인, CASEBOOK_CALIBRATION_PLAN §3 F1) ─────────────
#: C1-a — 진종(從)·진전왕(專旺)이 확정된 명식에서는 조후 역행 강등(_climate_harmful)을 적용하지
#: 않는다. 종격 용신(윤하격의 水, 염상격의 火, 종재격의 재성 …)이 월령 한습·조열 때문에 기신으로
#: 뒤집히던 결함(사례집 11건 중 8건). 조후 필요는 경고·서술 레이어로만 남긴다.
SPECIAL_SKIP_CLIMATE_DEMOTE: bool = True
#: C1-b — 전왕(일행득기)을 용신 '특수격 단독 주도'(special 축 1.0)로 취급하는 조건을 격국의
#: 특수격 치환 게이트(geokguk.special_pattern.override — 압도 ≥80%)와 동일하게 맞춘다.
#: 60~80% 구간은 격국이 정격(양인·건록·월겁 …)으로 두므로 용신도 가전왕(假專旺)으로 억부와
#: 경쟁시킨다(일간 동기 오행이 용신이 되던 059·067·053 류 교정).
DOMINANT_SPECIAL_REQUIRE_OVERRIDE: bool = True
#: C1-d — 부분맵 모델(조후·격국 상신 등, 용신만 내는 모델)이 선택되면 기·구신을 정적 생극
#: 순환이 아니라 집계된 불리 후보(억부 맥락: 신강이면 인성·비겁)로 배정하고 한신은 나머지 오행.
#: 기준 사주 2018-01-09 창원(丁酉·癸丑·辛丑·甲午, 조후 火): 기대 한신 水가 정적 순환 때문에
#: 기신이 되던 결함. 통관·무비겁 특수분기와 완비 모델맵 승격은 그대로다.
PARTIAL_MAP_ADOPT_AGGREGATED_UNFAVORABLE: bool = True
# ── C2 조후 필요신 후보 생성부 교체(2026-10-07 데굴님 결정 A·C, B 보류) ──────────────────────
#: 결정 A — 조후 후보는 사전 needs[] 의 climate_* 역할 천간만. 생조·설기·제련·배합 글자는 설명에만.
#: climate 글자가 없는 셀(丙·丁 겨울 등 10칸)은 후보를 내지 않고 교정 필요 오행을 경고로만 표시
#: (0.25 보조 후보 금지). OFF 면 v0.2 동작(셀 첫 글자 오행 환원).
JOHU_CLIMATE_ROLE_ONLY: bool = True
# #6c 투출 천간 자리 손상(2026-10-08 데굴님 승인, shadow 선행) — 기본 OFF = 기존 byte 불변. 운 천간
# 제외(원국 투출 자리 한정). 환경변수 SAJU_YONGSIN_STEM_DAMAGE_ENABLED.
YONGSIN_STEM_DAMAGE_ENABLED: bool = (
    _os.environ.get("SAJU_YONGSIN_STEM_DAMAGE_ENABLED", "false").strip().lower()
    in ("1", "true", "yes")
)
#: 결정 C — 조후 역행 감점 모드(후보 유지, 자동 강등 없음; mild 약한 감점·severe 강한 감점).
#:   "axis_graded"        기후 축(계산)이 mild 이상일 때만, 월지 무관 — 결정 C 문면. 단 축 공식이
#:                        분포 중심이라 卯·辰월에서도 발동하고 丑月 창원 2018(기준 사주)은
#:                        neutral 로 빠져 火 용신을 잃는다 → 재결정 전까지 기본값으로 쓰지 않는다.
#:   "month_axis_graded"  한난 월(亥子丑/巳午未)을 필요조건으로, 축으로 강도만(severe=강, 그 외=약).
#:   "legacy_month_demote" 월지+분포 기준 강등(CLIMATE_DEMOTE_REQUIRE_SEVERE 적용) — v0.2 동작.
CLIMATE_PENALTY_MODE: str = "month_axis_graded"
#: 감점 계수 — 214명식 A/B 스윕(2026-10-07): 0.6/0.3 이면 CASE-020(未月 甲, 전문가 '水 필요')이
#: 火 통관 용신으로 뒤집힌다. 0.4/0.2 는 기준 사주·골든 불변, 역할표 변경 1건(020/R 구·한 교환) →
#: 제안값.
CLIMATE_PENALTY_MILD: float = 0.4
CLIMATE_PENALTY_SEVERE: float = 0.2
#: 결정 B(보류) — 조후 필요 오행의 최저 역할 보장은 구현하지 않는다(조후 필요성 ≠ 종합 용희기구한).

#: (C1-c 종격 게이트 정합은 보류 — 격국 종격 신호가 root_score<8 기준이라 교과서 종살격
#: 庚申·庚申·甲申·庚午(root 30)조차 신호가 없다. 종격은 용신 쪽 세력군 판정을 유지하고, C1-a
#: 면제만 양쪽 합의(override) 때 적용한다. 검출기 통일은 골든 스냅샷에 닿아 별도 결정 사항.)
