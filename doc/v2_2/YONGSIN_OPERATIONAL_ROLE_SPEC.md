# 용신 작동역할 규격 — 2계층 역할 모델 (YONGSIN_OPERATIONAL_ROLE_SPEC)

> 목적: 용신 확정 이후 희·기·구·한을 **용신 오행 하나만 보고 정적 생극 순환으로 다시 평탄화**하는
> 현행 구조(`candidates.py::_classify_roles`)가, 후보 모델·조후·합·과다 등 엔진이 이미 계산한
> 맥락 신호를 최종 단계에서 버리는 문제를 해결한다. 정적 역할(canonical)은 보존하되, 실제 풀이·
> 점수화가 소비하는 **작동 역할(operational)** 레이어를 신설한다.
>
> 상태: 설계 확정(2026-06-24, 데굴님 승인). 구현은 **단계별 승인** — Phase 0부터 회귀 게이트 통과 후 다음.

---

## 0. 출처·신뢰 등급·정책

**출처**: 본 리포 검증 로그(丁巳/壬子/丁未/癸卯 사례) + 기존 규격 문서
- 정적 5역할 canonical 순환: `doc/yongsin_special_cases_test_cases.md` §역할 배정
- 합화/합반/합거·관살혼잡: `doc/v2_2/HAP_INTERACTION_SPEC.md` (Phase 3 source of truth)
- 조후 operability_modifier: `doc/v2_1/saju_v2_five_element_distribution_algorithm.md` §조후(climate_context)
- 용신 후보 모델: `doc/v2_1/saju_v2_yongsin_candidate_algorithm.md`

**신뢰 등급 태그**: [확정] [다수설] [소수설] [미검증] [기각]

**구현 정책** (2026-06-24 데굴님 확정):
1. **전체 갭을 정식 수정 범위로 인정**하되, 한 번에 구현하지 않는다. docs/spec → 테스트 픽스처 → Phase 0~4 순차 반영, **각 단계 회귀 승인 후 다음**.
2. **수치 계수는 확정 상수로 하드코딩하지 않는다.** 방향·역할명은 본 스펙에서 확정하고, 가중치·임계값·신뢰도 가·감산은 **config/experimental 값**으로 분리한다(§6).
3. **canonical 역할은 절대 제거하지 않는다.** 전통 오행표·기존 테스트 호환을 위해 정적 5역할을 그대로 유지하고, operational은 그 위에 얹는다.
4. 새 명리 규칙을 발명하지 않는다 — 기존 규격(HAP/조후/후보모델)을 인터페이스로 엮는다.

---

## 1. 문제 정의 — "정적 평탄화"

### 1-1. 현행 흐름
`build_yongsin()`는 후보 모델군을 산출·경합시켜 용신 오행을 정한 뒤,
[`candidates.py:777`] `roles = _classify_roles(yongsin_el)` 에서 **용신 오행 하나만으로** 다음을 재계산한다:

```
희신 = 生용신   기신 = 克용신   구신 = 生기신   한신 = 용신生(나머지)
```

예외는 `bridge_tonggwan`, `support_day_master`(무비겁 특수분기) 둘뿐. 그 외 모델(살인상생형 포함)은
모두 정적 순환으로 떨어진다.

### 1-2. 표준 사례 (이 스펙의 회귀 기준 차트)
**年 丁巳 · 月 壬子 · 日 丁未 · 時 癸卯 (일간 丁火, 신약, 절기보정 水 60.3%)**

| | 선택 모델(`resource_as_yongsin`=살인상생형) 자체 역할맵 | 현행 `final`(정적 재분류) |
|---|---|---|
| 용신 | 木 | 木 |
| **희신** | **火 (비겁 방조)** | **水** ← 뒤집힘 |
| **한신** | **水 (官殺)** | **火** ← 뒤집힘 |
| 기신 | 金 | 金 |
| 구신 | 土 | 土 |

- 후보 모델은 reason까지 명시한다: *"비겁은 일간 방조(희신), 재성은 재생살·재극인으로 기신"*.
  즉 엔진은 **火=희신·水=한신을 이미 계산**했는데 정적 재분류가 덮어쓴다.
- 추가 모순: `_climate_harmful`은 이 차트의 水를 **한습 역행(조후 부적격)**으로 이미 플래그한다
  (子월 + 火 11.8% < 22%). 그러나 이 강등은 `useful` 딕셔너리에만 적용되고, 水는 `useful`에
  든 적이 없어(useful={木,火}) **최종 희신 슬롯의 水는 조후 가드를 우회**한다.

### 1-3. 일반화된 결함
정적 평탄화가 유지되면 동형 문제가 반복된다:
- 관살태왕인데 官殺(水)이 희신으로 고정
- 조후상 필요한 火가 단순 한신 처리
- 제살 보조가 될 수 있는 土가 구신으로만 강등
- 丁壬合·관살혼잡·子卯刑 등 맥락이 최종 역할에 미반영
- 정인/편인 차이가 오행 합산으로 소실

→ **단일 버그가 아니라 "용신 최종 역할 결정 계층"의 구조 문제.**

---

## 2. 아키텍처 — 2계층 역할

```
canonical_roles    정적 생극 순환(_classify_roles) 결과. 전통 오행표·하위호환용. 보존·불변.
operational_roles  실제 풀이·이벤트 점수화가 소비하는 작동 역할. 신규.
```

- **canonical**: 用喜忌仇閑 1:1 분할(현행 그대로). 표시·교육·전통 참조용.
- **operational**: 선택 모델의 맥락 역할맵 + 보정자(조후/과다/합/작동성)를 반영한 레이어.
  이벤트 점수·LLM 통변 입력은 **operational을 1차 소비**한다.
  (배선 일부 완성: `event_scoring.py::favorability_map_from_model()` 이미 존재.)
- 마이그레이션 동안 `final`은 canonical의 별칭으로 유지(하위호환). 소비처를 operational로
  단계 이관한 뒤 `final` 의미를 정리한다.

---

## 3. operational_roles 산출 파이프라인

```
[1] 베이스 역할맵 선택
    선택 모델(top_model)의 자체 역할맵이 5역할(용/희/기/구/한) 완비
      → 그 맵을 operational 베이스로 채택
    부분맵 모델(bridge_tonggwan / disease_remedy:* / pattern_sangsin / johu /
               support_day_master 특수분기)
      → 기존 분기(_classify_bridge_roles / 특수분기 / _classify_roles 폴백) 유지
        (※ 안전조건: 부분맵을 무조건 채택하면 None 역할이 생겨 기존 테스트 파손 — §7 참조)

[2] 보정자 적용 (operational 베이스에 덧씌움)
    (a) 조후 가드      : _climate_harmful 가 잡은 한습 水/조열 火 → operational_role 강등·재명명
    (b) 과다 강등      : overload(관살/인성/비겁/식상 태왕) 원소 → "병/과다" 표지
    (c) 합 인터페이스  : HAP 결과(confirmed/conditional/none·합반·쟁합·거살유관)를 官殺 등
                         십성 세력 재산정에 연결 → 역할 재평가 (Phase 3)
    (d) 작동성        : 용신·희신 원소의 투간/통근/정·편인/통관손상 → confidence·operability
                         modifier (Phase 4)

[3] 출력
    각 오행을 ElementRole 로 직렬화(canonical_role + operational_role + 조건 + note)
```

**우선순위 원칙**: operational은 canonical을 *대체*하지 않고 *재해석*한다. 두 레이어 모두 출력한다.

---

## 4. 스키마 (`backend/packages/shared_types/saju_shared_types/yongsin.py`)

```python
class ElementRole(BaseModel):
    """오행 1개의 정적/작동 역할 이중 표현."""
    element: str                       # 木/火/土/金/水
    canonical_role: str                # 용신/희신/기신/구신/한신 (정적)
    operational_role: str              # 작동역할 라벨(§4-1 enum)
    positive_when: list[str] = []      # 작동역할이 긍정적으로 발현되는 조건
    negative_when: list[str] = []      # 부정적(병)으로 발현되는 조건
    note: str | None = None

# AggregatedYongsinResult 에 필드 추가
canonical_roles: dict[str, str | None] = {}     # 기존 final 5역할(보존)
operational_roles: list[ElementRole] = []       # 신규 작동역할 레이어
```

### 4-1. operational_role 라벨 enum (확정)
- `용신` `희신` `기신` `구신` `한신` — 작동상 canonical과 동일할 때
- `조건부 희신/병` — 생용신이지만 원국에서 이미 과다·병인 오행(예: 관살태왕의 官殺 水)
- `조후보조신` — canonical 한신이나 조후·일간유지에 필요한 보조 약(예: 子월 丁火의 火) **(D3 확정 기본값)**
- `조건부 제살보조` — canonical 구신이나 과다 오행 제어 보조 가능(예: 水 과다의 土)

> 라벨 집합은 enum으로 고정한다. 즉석 작문 금지(스키마 검증 대상).

### 4-2. 표준 사례의 operational_roles (목표 출력)
```json
[
  {"element":"木","canonical_role":"용신","operational_role":"용신",
   "positive_when":["木 투간/통근","卯未 반합 유효"],
   "negative_when":["子卯 격각으로 통관 손상","木 무근·고립"]},
  {"element":"火","canonical_role":"한신","operational_role":"조후보조신",
   "positive_when":["子월 한습 제거","일간 유지"],
   "negative_when":["水 직극으로 무력"]},
  {"element":"水","canonical_role":"희신","operational_role":"조건부 희신/병",
   "positive_when":["木 작동","火 조후 확보","水 과다 임계 미만"],
   "negative_when":["水 과다","한습 심화","관살 압박 증가"]},
  {"element":"土","canonical_role":"구신","operational_role":"조건부 제살보조",
   "positive_when":["水 과다 제어","건토","火 받침"],
   "negative_when":["습토","일간 설기 과다","木 용신 훼손"]},
  {"element":"金","canonical_role":"기신","operational_role":"기신",
   "negative_when":["木 극·水 생으로 관살 강화"]}
]
```

---

## 5. 보정자 정의

### 5-1. 조후 가드 (Phase 2)
- `_climate_harmful(month_branch, force)` 가 반환한 한습 水/조열 火를 **operational에서 강등**한다:
  - 해당 오행이 operational 희신이면 → `조건부 희신/병`
  - 해당 오행의 상대(한습→火 / 조열→水)가 operational 한신이면 → `조후보조신`으로 격상
- 기존 `operability_modifier`(v2_1 분포 스펙, 예 `excessive_cold_reduces_fire_operability`)와
  값을 공유한다 — 중복 정의 금지. 계수는 §6.

### 5-2. 과다 강등 (Phase 2)
- `_resource_overload`/`_bigyeob_overload`/`_officer_heavy`/`_output_heavy` 가 잡은 태왕 십성의
  오행은 operational에서 `조건부 …/병` 표지 + `negative_when`에 "과다" 사유 기재.

### 5-3. 합 인터페이스 (Phase 3) — HAP_INTERACTION_SPEC이 source of truth
- 본 스펙은 **합 결과를 소비하는 인터페이스만** 정의한다. 합화/합반 세력 차감의 계수·규칙은
  `HAP_INTERACTION_SPEC.md`(또는 config)에서 관리하며 여기서 재정의하지 않는다.
- **요구사항(명시)**: 다음이 官殺 등 십성 세력 재산정에 반드시 연결되어야 한다 —
  - 합화 등급 `confirmed`/`conditional`/`none`
  - 합반(合而不化, 묶임)
  - 쟁합(이 사례: 年丁·日丁이 月壬을 다툼)
  - 거살유관/거관유살(관살혼잡 정리)
- 현재 분포 단계는 관계를 `deferred`로 미반영(`element_distribution.py` trace). Phase 3에서
  이 deferred 경로를 활성화해 officer 세력을 재산정하고, 그 결과를 operational 역할이 소비한다.

### 5-4. 작동성 (Phase 4)
- **투간/통근**: 용신·희신 오행이 천간 투출/지지 통근인지로 confidence·operability modifier 조정.
  현행은 일간 통근만 계산(`rooting.py`) → 용신 오행별 통근 산출로 확장.
- **정/편인 차등** (D4 확정): 印을 살인상생 용신으로 쓸 때 甲(정인)/乙(편인)을 구분하되
  **용신 선택 자체를 바꾸지 않는다.** confidence/operability modifier로만 반영 —
  甲 정인은 안정성 가산, 乙 편인은 작동성은 인정하되 안정성 가산을 낮게. 투간/통근/합화 성립과
  함께 평가. 계수 §6.
- **통관 손상** (D1 확정): 형/해/격각이 용신 통관 흐름을 해치면 operability penalty.
  단 **사건 발생 신호가 아니라 operability penalty로만** 사용(§5-5).

### 5-5. 子卯刑·격각 정책 (D1 확정)
- **관계 이벤트 판정**은 기존 인접 원칙 유지([`relations.py:157`]) — 격각(비인접)은 사건 흉살로 잡지 않는다.
- **Phase 4 용신 작동성/통관 손상 레이어에서만** 격각 관계를 **약가중**으로 반영한다.
  - 의미: 子卯刑 격각은 "사건"이 아니라 "水→木→火 통관이 매끄럽지 않을 수 있다"는 operability penalty.
  - 기본 가중치 0.3 (config, §6) — 인접 형/해 대비 감쇠.

---

## 6. Config / Experimental 계수 (하드코딩 금지)

아래 값은 **확정 상수가 아니라 실험·튜닝 대상**이다. 구현 시 별도 config 모듈/JSON으로 분리하고,
Phase별 회귀·실측으로 조정한다. (정확한 파일 위치는 Phase 0 구현 착수 시 확정.)

| 키 | 기본값(제안) | 용도 | Phase | 결정 |
|---|---|---|---|---|
| `gyeokgak_operability_weight` | 0.3 | 격각(子卯刑 등) 통관손상 약가중 | 4 | D1 |
| `climate_demote_factor` | (v2_1 operability_modifier 공유) | 한습 水/조열 火 강등폭 | 2 | — |
| `overload_penalty_threshold` | (기존 overload 판정 함수 임계 재사용) | 과다 표지 임계 | 2 | — |
| `hap_officer_reduction` | HAP_SPEC/config 위임 | 합반 官 세력 감산 | 3 | D2 |
| `jeongin_stability_bonus` | +(소) | 甲 정인 살인상생 안정성 가산 | 4 | D4 |
| `pyeonin_stability_bonus` | +(소, 정인보다 낮음) | 乙 편인 안정성 가산 | 4 | D4 |
| `yongsin_rooting_bonus` | +(소) | 용신 오행 투간/통근 시 confidence 가산 | 4 | — |

---

## 7. Phase 계획 + 회귀 게이트

각 Phase는 독립 PR. 완료 기준 = 타입 + 구현 + 단위테스트 + 회귀 픽스처 통과 + **데굴님 승인**.

| Phase | 범위 | 재사용/근거 | 회귀 게이트 |
|---|---|---|---|
| **0** | canonical/operational **계층 분리** + 5역할완비 모델 역할맵 존중 | 테스트조사: 직접 충돌 0건 | 표준사례+1985 골든 픽스처 신규. 단 **부분맵 폴백 보존**(아래 안전조건) |
| **1** | `ElementRole` 조건부 역할 스키마 + 직렬화 | §4 | 스키마 라운드트립·enum 검증 |
| **2** | 조후가드·과다강등을 operational에 연결 | `_climate_harmful`·v2_1 operability | 표준사례 水 희신→`조건부 희신/병`, 火 한신→`조후보조신` 단언 |
| **3** | 합반/합화/관살혼잡 → 官殺 세력 재산정 인터페이스 | **HAP_INTERACTION_SPEC** deferred 활성 | 거살유관·합반 감산 fixture |
| **4** | 용신 작동성(투간/통근·정/편인·격각 통관손상) | rooting 확장·ten_god 정/편 보존·D1 | 투간無 용신 신뢰도 하향, 격각 penalty 단언 |

### 7-1. Phase 0 안전조건 (회귀 파손 방지) [확정]
테스트 조사 결과, operational을 부주의하게 "모델맵 무조건 채택"으로 구현하면 다음이 깨진다:
- `bridge_tonggwan`(2015 차트): 모델맵 heesin/hansin = None → `_classify_bridge_roles` 분기 유지 필수
- `disease_remedy:*`(1980 戊 차트): 부분역할(None) → `_classify_roles` 폴백 필수
- `support_day_master` 특수분기(1985 차트): 기존 인라인 특수맵 유지 필수
→ **5역할 완비 모델만 operational 베이스로 채택, 나머지는 기존 분기 유지.**
회귀 골든 스냅샷은 용신 역할을 고정하지 않으므로(`test_golden_snapshots.py`), 역할 단언은
`test_yongsin.py`/`test_fixture_1980.py` 부분 단언뿐 — 위 조건 준수 시 직접 파손 0건.

---

## 8. 결정 사항 기록 (2026-06-24 데굴님 확정)

| # | 항목 | 확정 방향 |
|---|---|---|
| D1 | 子卯刑 격각 | 관계 이벤트는 인접 원칙 유지. Phase 4 통관손상에서만 격각 약가중(operability penalty, 비-사건). 기본 0.3(config) |
| D2 | 합반 官 세력 감산 | HAP_INTERACTION_SPEC을 source of truth로. 본 스펙은 소비 인터페이스만 정의. 계수는 HAP/config |
| D3 | 조후 火 작동역할명 | canonical은 한신 가능. operational에서 `조후보조신`으로 격상(기본 명칭) |
| D4 | 정/편인 작동성 차등 | 도입하되 용신 선택 불변. confidence/operability modifier로만. 甲 정인 안정성↑, 乙 편인 안정성 가산 낮게. 계수 config/Phase4 |

공통: **방향은 본문 확정, 수치 계수는 config/experimental로 분리**(§6).

---

## 9. 미해결 / 후속

- §6 계수 파일의 정확한 위치·포맷(파이썬 모듈 vs JSON 사전 파이프라인) — Phase 0 착수 시 확정.
- operational_role 소비 측(`event_scoring`/LLM 입력 계약/통변 템플릿) 이관 범위 — Phase 1~2 사이 별도 점검.
- `final` 별칭 폐기 시점 — operational 소비 이관 완료 후.

---

## 10. 후속 로드맵 — operational 소비 + 유사 케이스 확장 (2026-06-24 데굴님)

> **통합 원리(한 줄):** *정적 用喜忌仇閑은 맞지만, 실제 작동은 원국 구조·조후·과다·합반·통근·정편·궁성
> 손상에 따라 달라진다.* Phase 0~4b는 이 패턴의 한 분기(관살태왕+살인상생+한습+木 작동성 저하)를 닫은 것.

### 10-1. 유사 케이스 카탈로그 (전부 같은 패턴)
| # | 케이스 | 대표(이번) | 현 상태 |
|---|---|---|---|
| 1 | 희신이지만 과다해 병 | 水 | Phase 1 일반화 — fallback/disease_remedy 확장 필요 |
| 2 | 한신/구신이나 조후상 필수 | 火 | Phase 2 — 조후 충돌 케이스 확장 필요 |
| 3 | 용신 맞으나 작동성 약함 | 木 | Phase 4a/4b 시작 — 공망·충·합반·고립 추가 필요 |
| 4 | 통관 경로 중간 단절 | 水→木→火 | 통관 오행의 투간/통근/손상/공망/합반 점검 필요 |
| 5 | 합화·합반으로 십성 전환/묶임 | 丁壬合 | Phase 3 官殺만 — 財/印/食傷/比劫 합 맥락 확장 필요 |
| 6 | 좋은+나쁜 십성 혼잡(정/편) | 官殺混雜 | 십성 그룹 합산에서 정/편 구분 보존 필요 |
| 7 | 제살/통제 오행의 양면성 | 土(조건부 제살보조) | Phase 1 일부 — 조건부 보조약 일반화 필요 |
| 8 | 특수격/종격/전왕격 역전 | — | Phase 0 부분맵 폴백 보호 + 특수격 operational 설명 필요 |
| 9 | 운 입자가 원국 operational과 충돌 | 水운 추가 | 운세 이벤트 해석을 canonical 아닌 operational 기준 참조 |

### 10-2. 우선순위 (데굴님 확정 — 실서비스 기준)
```
1. Phase 4b 완료 ✅
2. operational_roles를 LLM 입력에 연결        ← 다음 (가장 중요)
3. 운세 해석에서 operational role 우선 규칙 적용
4. 희신/기신 문자열 파싱 금지, OPERATIONAL_ROLE_CLASS mapper 강제 ✅(2026-07-07 —
   role_class/is_favorable_role/is_unfavorable_role 헬퍼 신설, 클래스 판정 전 사이트
   9개 파일 이관·세분 exact enum 비교는 정책대로 유지. 전체 회귀 불변)
5. 조후 충돌 케이스 확장
6. 용신 operability에 공망·충·합반·고립 추가
7. 官 외 합 맥락 확장: 財/印/食傷/比劫
8. fallback/특수격 operational 설명 확장
9. shadow scoring (operational 기반 병행 점수 — final 비대체)
10. Option A(관계 보정 기반 분포 재산정) = 별도 이니셔티브
```

### 10-3. 소비 진입점 (조사 확정, 2026-06-24)
- **LLM 입력(#2)**: `chart_interpretation.py`가 ⑤ 명식 해석 블록을 직렬화 — operational_roles·operability를
  여기에 additive로 surface(LLM은 설명만, 점수 불변).
- **역할 문자열 파싱(#4 대상)**: `event_engine_v2`·`relations_engines`·`topic_builder`·`relocation`·
  `chart_interpretation`이 "희신"/"기신" 문자열을 직접 비교. 이관 시 `OPERATIONAL_ROLE_CLASS` mapper 경유 강제.
- **불변 원칙 유지**: #2는 LLM 프롬프트에 맥락만 추가(scoring=final). 실제 점수 이관은 #9 shadow scoring부터.

### 10-4. Option A(분포 재산정) 착수 조건 (데굴님 확정 — 충족 전 착수 금지)
Option A는 distribution 차감→groups→신강약→모델선택→`final`→event scoring 변경까지 가는 고위험
이니셔티브. 아래 **전부 충족 + 별도 명시 승인** 전에는 열지 않는다:
1. operational 기반 **shadow scoring**(#9) 결과가 충분히 축적
2. 대표 **골든 차트 최소 20~30개** 확보(합반/합화/합거/쟁합/관살혼잡 케이스별 기대 결과 정의 포함)
3. **`final` 변경 허용 범위** 합의(어느 케이스에서 신강약/용신이 바뀌어도 되는가)
4. **전면 회귀 리베이스라인** 테스트 준비(골든 스냅샷 재생성 계획)
5. **rollback flag** 설계(분포 차감 on/off 토글 — 즉시 복귀 가능)

### 10-5. Phase 5a 범위 (확정 — operational 소비 1차)
**포함**: ①canonical/operational/operability 요약 `yongsin_operational_summary` adapter(compact)
②`chart_interpretation` ⑤ 블록에 additive surface ③`OPERATIONAL_ROLE_CLASS` mapper exact 해석 강제
④조건부 라벨 문자열 오파싱 방지 ⑤표준사례 prompt 노출 스냅샷 ⑥token budget.
**제외**: event scoring 변경 · 운세 길흉 판단 변경(#3=5b) · shadow scoring(#9) · Option A · `final`/confidence 변경.
**불변 게이트**: `final`/`canonical_roles`/`favorability_map`/event score 전부 불변(테스트 강제).

---

## 11. 통합 정리 — Phase 0~5b-2a 안정화 기준 (2026-06-24)

> operational 레이어 1차 MVP 완료. 본 절은 회귀·확장 시 **고정 기준**이다(이후 변경은 이 절과 대조).

### 11-1. 변경 요약 (Phase별)
| Phase | 한 줄 | 산출물 | 출력 영향 |
|---|---|---|---|
| 0 | canonical/operational 2계층 분리(5역할완비 모델맵 존중) | ElementRole·canonical_roles·operational_roles | 없음 |
| 1 | 과다·병 조건부 라벨 | 조건부 희신/병·조건부 제살보조 | 없음 |
| 2 | 조후 가드 연결 | 조후보조신 | 없음 |
| 3 | 官殺 합 맥락 | officer_hap(note/조건) | 없음 |
| 4a | 작동성 투간/통근·정편인 | operability·no_transmit/no_root/pyeonin_only | 없음 |
| 4b | 子卯 격각 통관손상 | gyeokgak_zimao | 없음 |
| 6a | 공망·충 | yongsin_void·yongsin_clash | 없음 |
| 6b-1/6b-2 | 고립·합반 | yongsin_isolation·yongsin_bound | 없음 |
| 7 | 官 외 합 맥락(財/印/食傷/比劫) | ten_god_hap | 없음 |
| 5a | operational → LLM 명식 블록 surface | yongsin_operational_summary | **프롬프트(설명)** |
| 5b-1 | 운 입자 operational guard | 運 grounding 태그/suffix | **프롬프트(설명)** |
| 9a/9b | shadow 가중·후보 관찰 | shadow_scoring(미소비) | 없음 |
| 5b-2a | 운세 길흉 표현 제한 | [표현 제한] clamp | **프롬프트(표현 강도)** |

### 11-2. 전 구간 불변 원칙 (절대)
operational 전 작업에서 다음은 **한 번도 바뀌지 않았다**(회귀 시 필수 단언):
`final`(yongsin_analysis.final) · `canonical_roles` · `favorability_map(result)` · event `score` ·
`reduce_candidates` 순위 · `polarity` · `groups`/`strength`/distribution · 신강약 · 모델 선택.
→ operational/operability/shadow/표현제한은 전부 **additive·on-demand·표현 전용**. scoring SSOT는 `final`.

### 11-3. 레이어 역할 구분
- **canonical_roles**: 전통 정적 用喜忌仇閑(=final 미러). scoring SSOT.
- **operational_roles**: 실제 작동 역할(조건부/조후보조 라벨 + note/positive/negative_when). 설명용.
- **operability**(용신만, 0~1): 작동성 손상 8 factor 곱연산. final.confidence와 별개.
- **hap context**(officer_hap/ten_god_hap): 합반/쟁합/합거/합화 맥락 주석. 라벨·세력 불변.
- **shadow scoring**(#9): operational 기반 가중·후보 관찰. **미소비**.
- **expression clamp**(5b-2a): legacy vs shadow로 운세 문장 길흉 강도 제한. **점수 불변**.
- 라벨 해석은 항상 `OPERATIONAL_ROLE_CLASS` mapper(문자열 substring 파싱 금지).

### 11-4. 표준사례 golden (丁巳/壬子/丁未/癸卯, 丁火 신약·水 60%)
| 오행 | canonical(=final) | operational | shadow weight | expression(운별) |
|---|---|---|---|---|
| 木 | 용신 | 용신 (operability **0.595**: 투간無·子卯 격각) | 0.595 | 길 + 작동성 낮음 부기 |
| 火 | 한신 | **조후보조신** | 0.35 | 보조 긍정 |
| 水 | 희신 | **조건부 희신/병** (과다+한습+합반/쟁합/관살혼잡) | 0.0 | **조건부·유보** |
| 土 | 구신 | **조건부 제살보조** | 0.1 | 주의 속 일부 완화 |
| 金 | 기신 | 기신 | −1.0 | 주의/흉 |
> 회귀 픽스처: test_yongsin_operational*.py / test_yongsin_operability*.py / test_shadow_scoring*.py /
> test_luck_expression_clamp.py. 표준 operability 0.595는 전 phase 일관 유지.

### 11-5. token budget 회귀 기준
- **월별 overview(候補 다수 경로)는 12000tok 한도에 상시 임박** — `_OPERATIONAL_INSTRUCTION` 등 시스템
  지시문에 절대 문장 추가 금지(과거 2회 초과 발생).
- operational 텍스트는 **단일 기간 블록(build_luck_grounding pillar_line·chart_interpretation summary)에만**.
  후보별 note(_to_llm_candidate)에는 operational guard 금지.
- 프리픽스 summary 블록 ≈115tok, [표현 제한] 1줄(period fortune만). **데이터 라인은 자기설명적이어야**
  (지시문 의존 금지 — "(점수·순위 불변)" 자체 표기).

### 11-6. Phase 5b-2b 진입 조건
도메인별(직업/재물/연애/이동) 표현 제한 확장은 다음 충족 후:
1. §11-4 golden 회귀 안정(全 phase 테스트 green).
2. **도메인별 문구 매핑 설계 확정** — 같은 水라도 직업=관살 압박·재물=계약 부담·연애=관계 압박처럼 분기.
   (expression_class를 도메인에 바로 꽂지 말고 intent×event_domain×operational 매핑 선설계.)
3. token budget 검증(도메인 문구 추가가 단일 기간 블록 내, 후보 경로 미증).

### 11-7. rollback / disable (구현 완료 2026-06-24)
첫 출력 영향(5b-2a)의 즉시 복귀 수단:
- **구현**: config 플래그 `EXPRESSION_CLAMP_ENABLED`(experimental, default True)가 `build_luck_grounding`의
  [표현 제한] 라인 생성을 게이트한다(`_op_config` 모듈 참조 — 런타임 토글 가능). False면 라인 미노출·
  `luck_expression_clamp` 미호출. 테스트 test_expression_clamp_rollback.py(on/off/계산 불변).
- shadow/operational 산출 자체는 미소비라 별도 토글 불요(소비처가 5b-2a 한 곳뿐). 플래그와 무관하게
  `luck_expression_clamp` 결과는 동일(소비처만 게이트).
- Option A 토글(분포 차감)은 §10-4 진입조건에 별도 명시(여기 무관).

---

## 12. Phase 5b-2b — 도메인별 표현 제한 (설계 확정·구현 완료 2026-06-24)

> 5b-2a `expression_class`를 도메인 언어로 **번역만**. score/rank/favorability/final/polarity/event
> score **불변**. LLM 임의 생성 금지(config phrase map). 1줄·단일 기간 블록·후보 경로 미노출·flag off 미노출.
>
> **구현**: `DOMAIN_EXPRESSION_PHRASE`/`EXPRESSION_CLASSES`(config), `domain_to_expression_key`·
> `domain_expression_phrase`(shadow_scoring — parser enum 비종속·str), `build_luck_grounding(domain_key=)`,
> chat_service period fortune에서 `intent.domain.value` 전달. test_domain_expression_phrase.py 8종·
> unit 1017 pass·토큰 ≤12000 유지.

### 12-1. domain_key (5종, 건강 제외)
| 파서 Domain | domain_key | GENERAL/미매핑 → base 5b-2a guidance fallback |
|---|---|---|
| CAREER | `career` | 직업·취업·이직·승진 |
| WEALTH | `wealth` | 재물·계약·투자 |
| RELATIONSHIP | `relationship` | 연애·관계·결혼 |
| RELOCATION | `relocation` | 이사·이동 |
| EDUCATION | `study_document` | 학업·자격·문서 |
- 건강(health) **1차 제외**(민감도↑ — 별도 안전 정책 후속).
- **`build_luck_grounding`에는 parser Domain enum 직접 전달 금지** — chat_service/adapter에서
  `domain_to_expression_key(domain) -> str|None`로 변환해 `domain_key: str | None`만 넘긴다(코어가 파서에 비종속).

### 12-2. phrase map (`DOMAIN_EXPRESSION_PHRASE[domain][class]`, config experimental) — 순화 확정
| class \ domain | career | wealth | relationship | relocation | study_document |
|---|---|---|---|---|---|
| 길 | 직업·직책 흐름 유리 | 재물·계약 흐름 유리 | 관계·인연 흐름 유리 | 이동·이사 흐름 유리 | 학업·자격 흐름 유리 |
| 조건부·유보 | 책임·압박·조직 이슈 동반 | 계약·현실 부담 동반 | 감정 과다·관계 압박 가능 | 계약 조건·방향성 확인 필요 | 문서·심리 부담 동반 |
| 보조 긍정 | 활력·표현 보조 도움 | 현금흐름 보조 도움 | 매력·표현 보조 도움 | 이동 추진 보조 도움 | 학습·표현 보조 도움 |
| 주의 속 일부 완화 | 직무 부담 일부 정리 | 지출 부담 일부 통제 | 관계 긴장 일부 해소 | 이동 변수 일부 정리 | 문서 지연 일부 진척 |
| 주의/흉 | 규정·책임 부담 주의 | 손재·과지출 주의 | 관계 갈등·거리감 주의 | 이동·계약 변수 주의 | 문서·시험 차질 주의 |
| 중립 | 직업 흐름 평이 | 재물 흐름 평이 | 관계 흐름 평이 | 이동 흐름 평이 | 학업 흐름 평이 |
- `조건부·유보+주의`/`주의`는 각각 `조건부·유보`/`주의·흉` 문구 재사용.
- **순화 원칙**: "관재"·"이별 주의"·"투자 유리" 같은 강한 표현 금지 → "규정·책임 부담"·"관계 갈등·거리감"·
  "재물·계약 흐름 유리"처럼 완화.

### 12-3. 십성 하드코딩 금지 (구조)
```
5b-1 운 grounding line   = 운 입자 십성/오행 설명(일간별 변동 반영)
5b-2a expression_class    = 길흉 표현 제한 등급
5b-2b domain phrase       = 그 등급을 도메인 언어로 번역(도메인×등급만)
```
→ 5b-2b는 "해석 변경"이 아니라 "표현 번역". 水=官殺 같은 십성 맥락은 phrase map에 박지 않고 5b-1 line이 담당.

### 12-4. 안전장치·불변
- `EXPRESSION_CLAMP_ENABLED=False` → 도메인 문구 포함 [표현 제한] 라인 전체 미노출.
- domain 미상/GENERAL → 5b-2a base guidance graceful fallback.
- [표현 제한] **1줄**(base→domain 치환, 길이 유사·토큰 중립)·후보 경로 미노출.
- score/rank/favorability/final/polarity/event score **불변**(문장 가드만).

---

## 13. Shadow Validation Harness (검증 도구, 구현 완료 2026-06-24)

> scoring 반영 결정을 **감이 아니라 데이터로** 하기 위한 일괄 리포트 도구. #9a/#9b shadow를 골든
> 차트 × 대표 기간에 산출해 legacy 대비 비교. **운영 score/rank/favorability/final/polarity 불변**
> (Guard #6 스냅샷으로 매 차트 확인) — 어떤 운영 경로도 소비/변경하지 않는다.

### 13-1. 구성
- `data/shadow_charts/charts.jsonl` — 골든 차트 입력(chart_id + BirthInput). 시드 9개(operational_std +
  golden manse 8). **chart_id 익명·리포트에 BirthInput 원본 미노출.** 20~30 누적은 행 추가.
- `saju_engines/shadow_report.py`(순수) — `build_shadow_report(result, candidates, ganji_by_period,
  chart_id, period_level) -> (rows, summary)` + `invariance_snapshot`(Guard #6). 운영 미연결.
- `scripts/shadow_validation_harness.py`(CLI) — charts 로드 → calculate → `score_legacy(YEAR+DAEWOON)`
  → 리포트 → CSV/JSON 저장 + top-N. 옵션 `--charts/--out-dir/--top-n/--dry-run`. 월운은 1차 제외(후속).
- 산출물 `data/shadow_reports/*.csv|json` — **gitignore**(재생성 가능).

### 13-2. 리포트 컬럼(REPORT_COLUMNS 고정)
`chart_id, level, period, ganji, event_key, legacy_score, shadow_observation_score, score_delta,
legacy_fav, shadow_fav, fav_delta, legacy_rank_global, shadow_rank_global, rank_delta_global,
legacy_rank_level, shadow_rank_level, rank_delta_level, expression_class, reason,
operational_roles, operability_factors, warns`. shadow_observation_score=관찰값(실 score 아님).

### 13-2b. 레벨별 랭킹(2026-06-24 보정)
`shadow_rank_diff(diffs, level_by_period=)` — 전역(_global) + 레벨별(_level) 순위 동시 산출.
YEAR(세운)·DAEWOON(대운)을 같은 풀에서 섞으면 대운 1개 shift 가 세운 순위를 밀어내는 착시가 생기므로
**WARN 은 rank_delta_level 기준**(전역은 참고용). 하위호환: level 미지정 시 기존 키(legacy_rank/
shadow_rank/rank_delta/rank_changed)만 반환. YEAR 후보는 기본 calculate 가 top-level yearly_luck 를
안 채우므로(=0) `score_legacy_years` + daewoon_table[].sewoon(장년기 20~60세, --year-window 표본)로
materialize 한다. 실측: 9차트 2778행 중 1439행이 level≠global delta, 180행이 전역 WARN→레벨 非WARN(착시 제거).

### 13-3. Guard (검증 기준)
| # | 체크 | 처리 |
|---|---|---|
| 1 | 조건부 희신/병 운 positive 작동 금지(fav_delta ≤ 0) | 리포트 |
| 2 | 조후보조신 < 용신·희신 가중 | 리포트 |
| 3 | operability<0.9 용신운 과대평가 금지(shadow_fav ≤ legacy_fav) | 리포트 |
| 4 | 조건부 제살보조 과한 길신 승격 금지 | 리포트 |
| 5 | abs(score_delta) ≥ SHADOW_WARN_SCORE_DELTA(18) · abs(rank_delta_level) ≥ **상대 임계** | WARN 플래그 |
| 6 | favorability_map·final·후보 score/polarity 불변 | **hard fail** |
- #1~5 = PASS/WARN(run 실패 안 함·top-N 리뷰용). #6 위반·schema/config 오류 = hard fail.
- missing ganji(candidate.period↔ganji exact match 실패) = skip + `missing_ganji` 집계, 전부 skip = errors.

### 13-3b. rank WARN 임계 상대화(2026-06-24)
큰 풀 과민 WARN 제거 — `threshold = max(SHADOW_WARN_RANK_DELTA_ABS(3), ceil(level_pool ×
SHADOW_WARN_RANK_DELTA_RATIO(0.05)))`, `abs(rank_delta_level) ≥ threshold` 면 WARN. 리포트에
`level_pool_size · rank_delta_pct · rank_warn_threshold` 추가(해석용). 효과: 대운 풀(≈70)→임계 4,
세운 풀(≈240)→임계 12~13. **rank WARN 91%→33%(2778행 929)** — korea 229→26·lunar 237→51(잔흔 제거),
uk_london 268·operational_std 190은 유지(실 영향). score_delta WARN(≥18)이 여전히 가장 안정적 신호.

### 13-4. 주의 — 1차 관찰 사항
- score_delta는 운 간지(오행) 단위 — 동일 기간의 복수 event_key가 같은 score_delta를 갖는 것이 정상.
- 신호 분포(실측): india/japan/us ≈ 무변(shadow≈legacy), uk_london·operational_std·australia 큰 reshuffle.
  → scoring 반영 시 **차트별 영향 편차가 큼**(전면 반영 위험·제한 도메인부터가 안전).
- **본 harness는 검증 전용. scoring/ranking/favorability에 연결 금지.** 누적 리포트로 scoring 반영 판단.

---

## 13-5. Shadow 차트 구조 coverage — 합성 명식 탐색 (2026-06-24)

> scoring 반영 판단을 위해 **다양한 명식 구조에서 operational shadow 가 과발동/미발동하지 않는지**
> 먼저 본다. 실데이터 적중 검증이 아니라 **구조 coverage**. 1차=합성/검증 명식, 실사건은 2단계
> (data/golden_events/, 익명화·동의 후·후속)로 분리.

### 13-5-1. 소싱 원칙
- **손으로 생일 단정 금지.** `scripts/find_shadow_charts.py` 가 deterministic stratified 그리드
  (1950–2009 × 월 × 일{3,13,23} × 12시지 × 성별, 연도 innermost)를 calculate 로 돌려, predicate 를
  만족하는 BirthInput 만 채택. `--max-candidates` 60000(전체 sweep ~51,840)·전 chart 충원 시 조기 종료.
- predicate 는 엔진 산출 바인딩(`shadow_chart_predicates.py`): strength band·five_elements·ten_gods
  groups·operational_roles 라벨·operability_factors·transformed_candidates·geokguk.
- **match_quality**: required 전부=FOUND / `best_match_allowed` spec 만 critical 전부+required 2/3↑=
  BEST_MATCH / 그 외 NOT_FOUND(charts.jsonl 미포함·억지 주입 금지).

### 13-5-2. 24 구조(그룹 1~7) — 도메인 4개는 별도 chat snapshot
관살태왕·살인상생·조건부 희신/병(3) · 조후보조신(2) · 용신 작동성 저하 7 factor(7) · 조건부 제살보조(1)
· 과다/신약 4(재다신약·인성·식상·비겁) · 합 맥락 4 · 특수격 후보 3. (`shadow_chart_specs.py`)
- **hap_confirmed_01**: role 전환·세력 재산정 아님 → **transform note only·final/groups/분포/scoring 불변**
  (invariant_additive 검증). **yongsin_bound_01**(용신 operability factor `yongsin_bound`)과
  **hap_bind_01**(일반 십성 합 맥락 enrich) 분리.
- 특수격·합거(away) 등 희귀 구조는 best_match_allowed(또는 NOT_FOUND 허용).

### 13-5-3. 산출물
- `data/shadow_charts/charts.jsonl` — 기존 9 + 신규 FOUND/BEST_MATCH(match_quality). 커밋.
- `data/shadow_charts/coverage_report.json` — manifest(chart_id·status·match_quality·satisfied/missing
  predicates·expected_shadow_ok·notes·schema_version). **timestamp·로컬 경로·대용량 로그 제외**. 커밋.
- `data/shadow_charts/search_logs/` — gitignore.
- 확장 차트로 harness 재실행 → score/rank/favorability/final/polarity 불변 재확인.

### 13-5-4. 실행 결과 (2026-06-24)
- **1차**(days {3,13,23}, 1950–2009, distinct-birth 우선): FOUND 22(distinct 22)·NOT_FOUND 2
  (jonggyeok/jeonwang). charts.jsonl 9→31.
- **2차 확장**(days {1,6,11,16,21,26}, `--only`): 종격/전왕은 days{3,13,23}에서만 빠졌던 것 — 확장 days
  에서 전왕 75·종격 52/2160샘플 다수 확인. **jonggyeok_01(follow)·jeonwang_01(dominant) FOUND**.
  `geokguk.special_pattern.type`('follow'=종격, 'dominant'=전왕/일행득기)로 판정(종혁격 오분류 방지).
  coverage_report 병합(1차 22 보존). **최종 FOUND 24 · NOT_FOUND 0.** charts.jsonl 31→33.
- harness 33차트·10066행: **불변 매 차트 통과(위반 0)**. 종격/전왕은 WARN(0,0)(극단 단일오행 — shadow≈
  legacy, 과발동 없음).
- **coverage 가드(과발동/미발동 점검) — 33차트 위반 0**: G1(조건부 희신/병 positive 작동 금지)·
  G3(operability<0.9 용신 과대평가 금지)·G4(조건부 제살보조 용신급 승격 금지) 전부 통과. score 편차는
  구신/기신 de-penalize(↑)·조건부 희신/병 downgrade(↓)의 **의도된 operational 보정**.

---

## 14. Scoring 반영 — Phase 1a (operational adjusted score, 산출만) (2026-06-24·구현 완료)

> **구현**: config(SCORING_OPERATIONAL_*) · `saju_engines/scoring_operational.py`
> (`apply_operational_scoring` 순수 — component flag·계수만 / `operational_scoring_sidecar` 마스터 게이트
> wrapper). **sidecar = candidate index 기반 list**((period,event_key) 키 미사용 — 충돌 방지).
> penalties 양수·delta≤0. **EventCandidate·chat_service 미변경**(라이브 service 삽입은 1b). test_scoring_
> operational.py 11종 · 33차트 flag-on 단조성·바닥·가드 G1/G3/G4 위반 0. unit 839 pass.
>
> operational shadow 를 **감점 계열 2 component 로만** scoring 에 반영. **flag off = byte-identical**,
> `.score`·랭킹·`final`/`favorability_map`/`canonical_roles`/`groups`/신강약 **불변**. Option A 제외.
> **1a = adjusted_score 산출만**(랭킹·LLM 미반영). 1b(랭킹 실험)·1c(도메인/intent 적용)는 후속.

### 14-1. feature flag (config experimental)
```python
SCORING_OPERATIONAL_SHADOW_ENABLED = False               # 마스터 — off면 후처리 미호출
SCORING_OPERATIONAL_COMPONENTS = {"conditional_byeong_downgrade": False,
                                  "low_operability_yongsin": False}
SCORING_OPERATIONAL_COEF = {"byeong_max_penalty": 12.0, "low_op_max_penalty": 10.0,
                            "op_threshold": 0.9, "adjusted_floor_ratio": 0.5}
```

### 14-2. score/favorability 분리
`.score`=발생 형성도(불변). operational 반영=**길흉 과대평가 억제**(감점)→ `operational_adjusted_score`
(actual score 아님·랭킹 미사용). favorability(−1~+1) 채널과도 분리.

### 14-3. 산출(sidecar 권장) — EventCandidate 불변
`apply_operational_scoring` 가 (period,event_key)→{operational_adjusted_score, operational_score_delta,
operational_components} sidecar 반환. EventCandidate 미변경 → 1a byte-identical 구조 보장. (1b/1c 에서
additive field 이관 가능, 그때 직렬화 snapshot 검증.)

### 14-4. component 수식 (감점 전용·#9b 동일 표면 오행 stem0.5/branch0.5)
- **A 조건부 희신/병 downgrade** (component on, **legacy_fav(el)>0 일 때만**):
  `penalty_A = byeong_max_penalty × Σ_{el∈G} w(el)·1{op_role(el)=조건부 희신/병 ∧ legacy_weight(el)>0}`
- **B 낮은 operability 용신운** (component on, **용신 오행에만**): G에 용신 포함 ∧ operability<op_threshold →
  `penalty_B = low_op_max_penalty × w(용신∈G) × (1 − operability)`
- 합산·클램프: `adjusted = clamp(legacy − A − B, ⌈legacy×adjusted_floor_ratio⌉, legacy)`,
  `delta = adjusted − legacy ≤ 0`. **두 항 감점만·adjusted ≤ legacy·바닥 보장.**

### 14-5. 적용 위치·대상
- 서비스 계층: `score_legacy` 후 · `reduce_candidates` 전. **flag off → 호출 자체 skip.**
- **1a: `.score`·`_rank_key` 정렬 불변**(adjusted 는 sidecar·미소비).
- 대상 **세운·대운만**(월운 제외) · **도메인 무관**(도메인=표현 전용).

### 14-6. 제외(1차)
조후보조신 상향 · 조건부 제살보조 상향 · 합 맥락 score · 도메인별 score · distribution/groups/final
재계산 · Option A · 랭킹 교체(1b) · 실제 적용(1c).

### 14-7. 검증
flag off byte-identical(직렬화·LLM·reduce·rank) · 감점 단조성(adjusted≤legacy·delta≤0) · 바닥 클램프 ·
랭킹 미교체(1a) · 33차트 harness flag on/off · coverage 가드 G1/G3/G4 위반 0 · flag on 불변(final/
favorability/canonical/groups/신강약/polarity).

### 14-8. Phase 1b — adjusted rank 실험 (설계·구현 완료 2026-06-24)

> **구현**: config(RANK_EXPERIMENT_ENABLED·RANK_TOPN) · scoring_operational.py
> (`adjusted_rank_experiment`·`rank_experiment_sidecar` + `apply_operational_scoring(*, components,
> coef_override)`) · `scripts/scoring_rank_experiment.py`. test_scoring_rank_experiment.py 10종. unit 849.
> **confound 발견·해결**: legacy_rank(=lei_rank_key 입력순서) ≠ score순서라 penalty 0에서도 rank 50/72
> 이동 → **op_rank_delta_level**(score 베이스라인 대비) 신설로 순수 operational 효과 격리.
> **결론**: op_rank_delta — A-only year mean 2.38·B-only 0.99·A+B 2.70(A 지배·B 약함). low_op 10→14→15:
> B-only mean 0.82→1.03→1.06(미미). **B는 14로 올려도 랭킹 영향 경미 → low_op=10 유지 타당**(B는 의도적
> 보조 효과). 실제 .score·rank·reduce·LLM 불변·가드 0.

1a sidecar(operational_adjusted_score)로 **가상 랭킹**만 관찰 — **실제 .score·rank·reduce_candidates·LLM
불변.** 독립 sub-flag·하네스/리포트 전용·서비스 미연결.
- **sub-flag**: `SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED = False`(마스터와 독립).
- **legacy_rank = `score_legacy` 반환 순서**(재계산 금지 — score desc 재정렬 시 엔진 lei_rank_key 순서와
  미묘하게 달라짐). **adjusted_rank = operational_adjusted_score 재정렬**, tie-break=기존 legacy order
  (stable — adjusted 동점은 legacy 순서 유지). **level(year/daewoon) 내부에서만 WARN**, global 참고용.
- **component 분해**: A-only·B-only·A+B 각각 adjusted_rank → rank_delta 비교(B 단독 영향 확인).
- **low_op 시뮬**: `apply_operational_scoring(coef_override=)` 인자 주입(config 불변)으로 low_op 10/14/15 ×
  {B-only, A+B} 비교 → B가 의미 있게 물리는 최소 계수 판단. **실제 계수 변경은 별도 승인.**
- **리포트**: rank_delta_level 분포·top-N(기본 10) 이탈 후보·차트별 max shift·rank WARN(상대임계 §13-3b).
- **불변·검증**: flag off → 실험 wrapper None·byte-identical. 33차트 coverage 가드 G1/G3/G4 위반 0.
- **산출물**: 순수 `adjusted_rank_experiment` + `scripts/scoring_rank_experiment.py`. EventCandidate/
  service/reduce/LLM 미변경. 제외: 실제 랭킹 교체·도메인 적용(1c)·config 계수 변경(별도 승인).

### 14-9. Phase 1c — 제한적 operational 적용 (lei_rank_key 보존, 1c-α 구현 완료 2026-06-24)

> **1c-α 구현**: config(APPLY_ENABLED·APPLY_MODE·APPLY_INTENTS=["career"]·APPLY_COEF·GUARD_PHRASE) ·
> scoring_operational.py `operational_rank_guards`(게이트 조합·selected에 apply 재산출·delta≤−6·max3·
> penalty 유래 1줄·missing 미부착) · context_reducer llm_candidates 매핑 직후 `caution_note` append.
> test_scoring_apply.py 9종. byte-identical(off·非career) 확인·career+on 태그 2개(≤3)·token 8412/10385
> ≤12000·33차트 가드 0. unit 858. **순위·.score·reduce·final/favorability 불변.**
>
> **운영 관찰(scripts/scoring_guard_observe.py, 33차트 guard 21)**: reason 전부 conditional_byeong_
> downgrade(**B는 임계 −6에서 미발동**·max≈4<6, 1b 일치)·과발동 0·미발동 26/33·과장단어 0·기존 caution
> append 17/21(방향 일치·경미 중복)·token +40. career 안정 — wealth 확대·1c-β는 누적 관찰 후 별도 승인.
>
> **caution 중복 정리 + 토큰 헤드룸 가드(2026-06-24)**: ① guard_caution_phrase(기존 caution 마커 有→
> compact·지시문 중복 제거·engine 텍스트 재작성 X). REDUNDANCY_MARKERS·GUARD_PHRASE_COMPACT. ② intent
> 확대 검증(scripts/scoring_guard_intent_report.py) — **relationship+kansal 에서 +태그가 본문 −1384 절단
> 발견**. ③ **토큰 헤드룸 가드**: build_llm_input payload 조립 후 _apply_rank_guards 로 이동·headroom
> (max_input − base − reserve) 내 phrase 실토큰 순차 차감·부족 시 미부착·max_guards 동적 3→1→0·
> HEADROOM_RESERVE=1500. 결과 **전 intent 절단 0**(career 13태그 정상·relationship 본문 보존). test +5·
> unit 863. **본문 우선·태그 후순위.**
>
> **1c-final(2026-06-24)**: domain normalize 버그 수정 — operational_rank_guards 가 domain_to_expression_
> key 로 정규화(EDUCATION value "education"→key "study_document") 후 APPLY_INTENTS 매칭. APPLY_INTENTS
> 기본 5종 확장(career/wealth/relationship/relocation/study_document·master off 라 inert). 최종 회귀
> (scripts/scoring_guard_final_report.py 33차트×5): **전 intent 절단 0·max≤3·과장단어(흉/위험/손실/이별 등)
> 0**(career13·wealth2·relationship1·relocation1·study2). 라우팅 정상(parse_message 5질문 확인). unit 864.
> **오픈 권장: APPLY_ENABLED=True·INTENTS 5종**(master 전환은 최종 확정 후). near-tie/Option A 보류.

1b 결론(adjusted_score 전체 정렬 금지·lei_rank_key 보존) 반영. **감점 계열만·제한 intent·flag off
byte-identical.** `.score`·rank·reduce·final/favorability/canonical/groups/신강약 불변. Option A·조후보조신/
제살보조 상향 제외.
- **flag**: `SCORING_OPERATIONAL_APPLY_ENABLED=False`(마스터)·`APPLY_MODE{rank_guard, near_tie_demotion}`·
  `APPLY_INTENTS=[]`(allowlist·빈=미적용)·`APPLY_COEF{penalty_threshold:6, near_tie_rank_window:3,
  near_tie_score_window:5, max_demotion_cap:2, topn_change_limit:1}`.
- **1c-α rank guard(이번)**: 순위·score·reduce **완전 불변**. `operational_score_delta ≤ −6` 후보에
  **operational_caution 태그**(sidecar·EventCandidate 스키마 불변). **reduce_candidates 이후 실제 LLM 노출
  후보에만**·후보별 1줄·**전체 max 3개**. reason은 1a penalties(조건부 희신/병 downgrade·낮은 operability
  용신)에서만. 파일럿 intent=**career(Domain.CAREER)만**.
- **1c-β near-tie demotion(후속·별도 sub-flag)**: 동일 level·event group·legacy rank≤3·score≤5 인접 쌍만
  max 2칸 후순위화·top-N 변화 ≤1(초과 시 legacy fallback).
  **구현 완료(2026-07-07)** — `scoring_operational.near_tie_demotion_order` + `context_reducer`
  배선(LLM 노출 순서만·엔진 .score/rank/reduce 불변). 게이트 = APPLY_ENABLED ∧ near_tie_demotion
  ∧ domain∈APPLY_INTENTS ∧ component≥1. 검증 15건(test_scoring_near_tie.py — 게이트 5·조건
  미충족 5·cap/top-N 3·배선 2). **운영 기본 off(near_tie_demotion=False → byte-identical) —
  활성화는 누적 관찰 후 별도 승인(기존 결정 유지).**
- **1c-γ prominence**: 5b 중복 — 제외.
- **검증**: flag off byte-identical·intent 미매칭 미적용·token budget 회귀·33차트 가드 G1/G3/G4 위반 0·
  순서/score/rank/final/favorability 불변.
