# SINSAL_MODIFIER_SPEC — 신살·길성 보정 레이어 규격 (v2.2)

> 상태: **확정 (2026-06-25 사용자 승인). Phase A 구현 진행.**
> 결정 근거: 사용자 제안 3건(신살 위치·길흉·intent 보정 / 길성·흉살 생애단계·재활성화 4주 전체)을
> 기존 설계문서(05·06·09)·코드 구조와 정합하도록 규격화. 가중치 수치는 **튜닝 가능한 초기 기본값**.
> 진행 방식(사용자 확정): **(A) LLM 입력 enrichment 먼저 → (B) 스코어링 numeric 반영은 나중 별도 PR**.
>
> **확정 결정 4건(2026-06-25)**:
> 1. **도메인 갭** = `Domain` enum 불변. `GENERAL` + `palace_tags`/`subdomain_tags`로 시주/자녀/말년/프로젝트 흡수(§7).
> 2. **필드 배치** = `SinsalItem`(원천) 불변. 파생 해석은 별도 `SinsalModifier` 모델(§3).
> 3. **수치 노출** = LLM payload엔 계수 미노출. 내부 weight → 한글 강도어(약함/보조/강함/매우 강함)로만 변환(§9).
> 4. **생애단계 경계** = 대운 경계 우선 → 나이 fallback → 시점 미상 시 기본 나이대(§8).

---

## 0. 목적과 비목적

**목적**: 신살(길성·흉신·중립)을 "사건 라벨 단독 생성기"가 아니라, **위치(궁성)·운층·길흉·질문 intent·
생애단계에 따라 기존 사건 후보의 해석 방향·강도·리스크·완충을 조정하는 보조 레이어**로
구조화한다. 현재 정성(prose) 지시문으로만 존재하는 보정 원칙을 **결정론적 config + 구조화 태그**로
승격해, LLM이 "신살 이름"이 아니라 "보정된 해석 신호"를 받도록 한다.

**비목적(이번 스펙이 바꾸지 않는 것)**:
- 신살이 신강약·용신·격국을 결정하지 않는다(`SinsalItem.use_for_yongsin_decision=False` 유지).
- (Phase A에서) 이벤트 numeric `score`를 바꾸지 않는다. score 보정은 Phase B(별도 PR, 별도 승인).
- 신살 산출 규칙(어느 글자가 어떤 신살인가)은 **재정의 금지**(09 §75) — 기존 만세력 엔진 산출 사용.

---

## 1. 기존 규격·코드와의 정합 (이미 있는 것 / 신규)

| 항목 | 상태 | 근거 |
|---|---|---|
| 신살=보조(auxiliary), 단독 길흉·사건 판정 금지 | **기존** | `doc/v2_2/docs/05_DATA_DICTIONARIES.md:107` (`role:"auxiliary"`) |
| LLM에 신살을 해석 텍스트(태그)로 전달 | **기존** | `06_LLM_INPUT_CONTRACT.md:60,64-68`; `chart_interpretation._sinsal_excerpts` |
| 길성/흉신/중립 분류 | **기존** | `sinsal_catalog.CATALOG_META[*].polarity` (positive/caution/neutral) |
| 위치(년/월/일/시) 보존 | **기존** | `SinsalItem.position`, `SinsalAnalysis.by_pillar` |
| 원국 vs 운(대운/세운/월운/일운) 구분 | **기존** | `SinsalItem`(원국) / `LuckSinsal`(운), `_LUCK_SINSAL_INSTRUCTION` |
| 위치별 사회궁/개인궁 발현 차이 | **기존(정성)** | `_SINSAL_PALACE_LABEL`, `_SOCIAL_PALACES/_PERSONAL_PALACES` |
| **위치별 수치 가중치** | **신규** | 문서 미정의 → 본 스펙 §4 |
| **길성 완충/흉살 리스크 수치 modifier** | **신규** | 본 스펙 §6 |
| **intent(도메인)별 정렬·게이트** | **신규** | 본 스펙 §7 |
| **년주 길성 생애단계 + 운 재활성화** | **신규** | 본 스펙 §8 |
| **per-event 신살 modifier 태그(LLM)** | **신규** | 본 스펙 §9 |
| **신살의 numeric 스코어링 편입** | **신규(Phase B 보류)** | 본 스펙 §10 |

핵심: **철학·분류·위치·운층 구분은 이미 구현돼 있다.** 본 스펙은 (1) 정성 지시문을 config 수치로
구조화하고, (2) intent 정렬·생애단계·재활성화를 신설하며, (3) LLM 입력에 구조화 modifier 태그를
추가하는 것이다.

---

## 2. 절대 원칙 (위반 시 거부)

1. **단독 사건 생성 금지**: 신살은 십성·궁성·합충형파해가 만든 기존 후보를 *보정*만 한다.
   허용 효과 = `interpretation_tag` / `risk_tag` / `mitigation_tag` / `timing_tag` /
   (Phase B) `score_modifier`. 금지 = `primary_event_creation`, `event_label_replacement`.
2. **단정 금지**: 흉살→"반드시 사고/실패/큰 병", 길성→"무조건 성공/완전 면책" 표현 차단.
   흉살=리스크·긴장·변동성 태그, 길성=완충·도움·회복 가능성 태그.
3. **길성은 뒤집기가 아니라 완충**: 길성이 기신운을 용신운으로 바꾸지 않는다. 피해 감소·해결자
   출현·마찰 완화로만(상한 §6).
4. **보조 자료 표기 의무**: 모든 신살 출력에 "(보조 — 단독 판정 금지)" 계열 표기 유지.
5. **결정론**: 위치·길흉·intent·생애단계·재활성화 판정은 전부 엔진(config) 계산. LLM은 받은
   태그를 서술만 한다(규칙 1·12 준수).
6. **수치는 config**: 모든 가중치·계수는 `sinsal_modifier_config.py`(가칭) 상수로 분리해
   shadow/캘리브레이션으로 튜닝 가능하게 둔다(용신 operational_role_config 선례).

---

## 3. 데이터 모델 (Phase A — 확정: 별도 derive 모델)

**원천 모델 불변**: 기존 `SinsalItem`(원국)·`LuckSinsal`(운)은 **수정하지 않는다**(원자료 오염 방지,
Phase B shadow metric 확장 대비). 파생 해석은 **새 모델 `SinsalModifier`** 로 분리한다.

```text
# shared_types/sinsal.py — 신규 SinsalModifier (파생 해석 전용, 원천 SinsalItem 참조)
class SinsalModifier:
    name: str                      # 신살명(역마 등)
    polarity: str                  # positive | caution | neutral (catalog)
    position: str                  # year|month|day|hour (원천 SinsalItem.position 또는 운 발동 자리)
    source: str                    # natal | daewoon | yearly | monthly | daily
    scope: list[str]               # 작동 도메인 키(§4)
    palace_tags: list[str]         # GENERAL 흡수용 궁성/서브도메인(예: ["hour_pillar","children","late_life"])
    domain_match: bool             # 질문 intent ∩ scope (§7)
    activation_status: str         # latent | background | activated | strongly_activated (§8 재활성화)
    life_stage: str                # childhood | youth | middle | late (대운 우선 — §8)
    life_stage_mode: str           # seed | direct | background | accumulated (정점 전/정점/정점 후)
    effect_tags: list[str]         # 한글 효과 태그("이동성 강화","위기 완화·도움 가능성" 등)
    llm_strength: str              # 약함 | 보조 | 강함 | 매우 강함 (내부 weight→밴드, §9)
    # 내부 전용(LLM 미노출): debug/shadow 로그에만
    internal_weight: float         # 합성 가중(위치·intent·운층·생애단계·재활성화) — payload 제외
    internal_factors: list[str]    # 가중 산출 근거 stable key — payload 제외
```

> 규칙 11: 파생 산출은 신살이 없거나 시간미상(hour 없음)·시점미상이어도 안전(빈 리스트/기본값).
> 원천 `SinsalItem`에는 **어떤 필드도 추가하지 않는다**(사용자 확정).

---

## 4. 위치별 작동 (년/월/일/시) — 기본 가중치·범위

위치는 "정적 사건 강도"가 아니라 **작동 범위(scope) + 직접성(event_directness) + 기본 가중치**의
세트다. 초기 기본값(제안값 채택, config 분리·튜닝 대상):

| 위치 | scope(도메인) | event_directness | default_weight | interpretation_mode |
|---|---|---|---|---|
| 년(year) | ancestry, early_life, family_background, outer_reputation, distant_network | 0.45 | 0.60 | background |
| 월(month) | career, organization, parents, social_role, workplace, public_activity | 0.85 | 0.90 | social_reality |
| 일(day) | self, body, spouse, relationship, daily_reality, core_decision | 1.00 | 1.00 | core_life |
| 시(hour) | children, subordinates, future, late_life, output, long_term_project | 0.70 | 0.75 | future_result |

**천간/지지/지장간 layer 가중**(신살은 지지 조합 산출이 다수 → 지지가 주 작동):

```text
position_layer_weight = { stem: 0.45, branch: 1.00, hidden_stem: 0.35 }
branch_special_weight  = { month_branch: 1.15, day_branch: 1.20, year_branch: 0.75, hour_branch: 0.85 }
```

천간 신살 = "표면·명분" 설명 태그, 지지 신살 = 주 작동, 지장간 = 약한 보조 신호.

---

## 5. 운층(source)별 작동 강도

| source | 의미 | event_power | 비고 |
|---|---|---|---|
| natal(원국) | 상시 성향·기본 환경·반복 패턴 | low~medium | `SinsalItem` |
| 대운(decade) | 10년 무대·환경 변화 | medium | `LuckSinsal` |
| 세운(year) | 그해 사건 주제 | medium~high | `LuckSinsal` |
| 월운(month) | 실제 체감·발생 월 | high_if_supported | 장기 흐름 정합 시 |
| 일운(day) | 택일·실행일 품질 | trigger_only | 장기 흐름 맞을 때만 |

운 신살은 단독이 아니라 **원국 글자를 합·충·형으로 건드려 발동**한다(기존 `_LUCK_SINSAL_INSTRUCTION`
원칙 유지). `LuckSinsal`에 `source`(daewoon/yearly/monthly/daily) 명시 필드 추가 검토.

---

## 6. 길성·흉살 modifier (수치, Phase A=태그 / Phase B=score)

길성·흉살별 효과 계수. **Phase A에서는 LLM 태그로만**(예: "위기 완화·도움 가능성"),
**Phase B에서 score/favorability 보정 수치로** 사용. 상한을 둬 길성의 길흉 뒤집기를 차단.

| 길성 | risk_reduction | max_positive_delta | 강작동 위치 | 해석 |
|---|---|---|---|---|
| 천을귀인 | 0.15 | 0.12 | 일·월 | 귀인 도움·문제 완화·해결자 출현 |
| 천덕귀인 | 0.18 | 0.06 | 월·일 | 큰 흉 감소·보호 |
| 월덕귀인 | 0.12 | 0.07 | 월·일 | 인복·사회적 완충 |
| 문창/학당귀인 | — | 0.10 | 월·시·일 | 학습·문서·시험·기획 강화 |
| 금여/암록/복성/천의성 | 0.10~0.12 | 0.06~0.08 | 일·월 | 안정·숨은 조력·치유 등 |

| 흉살 | risk_modifier | 강작동 위치 | 해석(리스크 태그) |
|---|---|---|---|
| 백호 | 0.15 | 일·월 | 급성 변수·결단성(충형 동반 시 강화) |
| 양인 | 0.12 | 일·월 | 경쟁·긴장·결단 |
| 겁살/재살 | 0.08~0.12 | intent별 | 손실·관재·압박(재물·계약·법무 결합 시 주의) |
| 귀문/원진 | 0.12 | 일·월 | 예민·집착·정서 어긋남 |
| 역마(중립) | activation +0.12 / stability −0.08 | 월·일 | 이동·변동(intent=이직·이사 정렬 시 강) |
| 도화(중립) | exposure +0.12 / 과다 risk +0.08 | 일·월 | 매력·인기·노출(intent=관계/영업 정렬 시 강) |

> 전체 계수표는 `sinsal_modifier_config.py`에 둔다. 위 값은 제안서 채택 **초기 기본값**이며,
> Phase B 진입 전 shadow 하네스로 분포·상한 검증 후 확정.

---

## 7. intent(도메인) 정렬 — 게이트·가중

신살은 **위치 궁성과 질문 intent가 맞을 때만 강하게** 반영한다. 본 리포의 실제 도메인 enum
(`saju_shared_types.intent.Domain`)에 매핑:

`CAREER · RELATIONSHIP · RELOCATION · WEALTH · EDUCATION · HEALTH · GENERAL`

**도메인별 위치 가중(domain_override, 초기 기본값)**:

```text
career:       {year:0.55, month:1.00, day:0.80, hour:0.65}
relationship: {year:0.40, month:0.70, day:1.00, hour:0.60}
health:       {year:0.45, month:0.75, day:1.00, hour:0.70}
wealth:       {year:0.50, month:0.90, day:0.85, hour:0.75}
relocation:   {year:0.55, month:0.90, day:0.95, hour:0.75}
education:    {year:0.45, month:0.90, day:0.85, hour:0.80}   # 제안 children→education 근사
general:      위치 기본값(§4) 사용
```

**정렬 효과**: `domain_match=true`(신살 scope ∩ 질문 domain) → strong; 불일치 → weak_context_tag.
예) 월주 역마 × CAREER = strong; 월주 역마 × RELATIONSHIP = weak. 일지 도화 × RELATIONSHIP =
strong; 일지 도화 × WEALTH = 소비·인기·고객성 약한 태그.

> **확정(2026-06-25)**: `Domain` enum은 **확장하지 않는다**. 제안서의 `children`/`late_life`/
> `project`/`creative_output`은 `domain=GENERAL`로 두고, `SinsalModifier.palace_tags`(예:
> `["hour_pillar","children","late_life","project_output"]`)에 의미를 실어 LLM에 전달한다.
> domain_match 판정 시 GENERAL 질문은 palace_tags와 질문 키워드의 정렬로 보조 매칭한다.

---

## 8. 생애단계 + 운 재활성화 — 4주 × 길성·흉살 전체 (근묘화실)

**원칙**: 위치 가중치는 정적이 아니다. **각 주의 신살(길성·흉살 모두)은 자기 '정점 시기'에만 쓰고
끝나는 것이 아니라, 평생 유지되되 생애단계에 따라 *작동 방식*이 바뀐다.** 정점 이전에는
잠재·예비(seed), 정점 이후에는 배경·누적/잔존(residual)으로 작동하며, 운이 그 주를 건드리면
재활성화된다. 근묘화실(根=년·초년 / 苗=월·청년사회 / 花=일·중년본인 / 實=시·말년결실)을 시기
정점에 매핑한다.

> 제2 제안(년주 길성)은 이 원리의 **한 예시**다. 곡선의 *weight shape*(정점 이전 낮음 → 정점 최대 →
> 정점 이후 중간)는 **길성·흉살 공통**이고, 각 단계의 *의미*만 극성에 따라 달라진다 —
> **길성 = 자산·도움**(seed→accumulated asset), **흉살 = 성향·리스크**(latent tendency→residual pattern).
> 어느 쪽이든 보조 레이어다(단독 사건 생성 금지 — §2).

### 8-1. 일반 곡선 규칙

- **정점(peak)**: 그 주의 궁성 시기 → `direct_*` 모드, weight 최대.
- **정점 이전(pre-peak)**: 아직 발현 전 → `*_seed`/`latent_*` 모드(낮은 weight, "늦게 빛남").
  주로 정점이 늦은 일·시주에 해당.
- **정점 이후(post-peak)**: 한 번 쓰고 사라지지 않고 → `background_*`/`accumulated_*` 모드
  (중간 weight, "후방 지원·누적 자산"). 주로 정점이 이른 년·월주에 해당.

**생애단계 판정(확정 — 대운 경계 우선)**:
```text
1순위: 현재 대운 위치 기준 — 질문 시점이 속한 대운의 순번으로 생애단계 매핑
       (1~2번째 대운=childhood/youth, 중간=middle, 후반=late; 대운 경계=교운일 기준)
2순위(fallback): 나이 밴드 — childhood 0–15 · youth 16–30 · middle 31–45 · late 46+
3순위: 시점 미상 — 기본 나이대(현재 reference_date 기준) 사용
```
근묘화실 해석 구조(년=초년정점 / 월=청년사회정점 / 일=중년본인정점 / 시=말년결실정점)는 유지한다.

### 8-2. 주별 생애단계 작동 — 길성(자산·도움 곡선, 초기 기본값, config 분리)

**년주(year) — 정점=초년. 배경·외부 보호막·먼 인연.**

| 단계 | mode | weight | 의미 |
|---|---|---|---|
| 초년 | direct_environmental_benefit | 0.80 | 초년 환경·가족 보호·성장 배경 |
| 청·중년 | background_asset | 0.55 | 출신·평판·오래된 인맥·윗사람 도움 |
| 말년 | ancestral_and_reputation_support | 0.45 | 가족 자산·누적 평판·오래된 관계망 |

**월주(month) — 정점=청년~중년(사회궁, 작용력 최대). 직장·조직·사회.**

| 단계 | mode | weight | 의미 |
|---|---|---|---|
| 초년 | inherited_social_base(잠재) | 0.50 | 부모·성장환경이 깔아준 사회적 토대(아직 본인 무대 전) |
| 청·중년 | direct_social_benefit(정점) | 0.90 | 직장·조직·사회·제도에서 직접 도움·발탁·평판 |
| 말년 | accumulated_social_capital | 0.60 | 쌓은 경력·사회적 신망·조직 네트워크 자산 |

**일주(day) — 정점=중년(본인·배우자궁, 체감 최대). 나·관계·실생활.**

| 단계 | mode | weight | 의미 |
|---|---|---|---|
| 초년 | latent_self_seed(잠재) | 0.40 | 기질·매력의 씨앗(아직 본인 결정 무대 전) |
| 청년 | emerging_personal | 0.70 | 배우자·관계 형성기 작동 시작 |
| 중년 | direct_core_benefit(정점) | 1.00 | 본인 선택·배우자·몸·실생활 직접 도움 |
| 말년 | sustained_personal_asset | 0.65 | 체화된 개인 역량·배우자 동반 |

**시주(hour) — 정점=말년 + 자녀·결과물. 늦게 빛나는 결실.**

| 단계 | mode | weight | 의미 |
|---|---|---|---|
| 초·청년 | future_seed(잠재) | 0.35 | 늦게 발현되는 잠재(학문·창작·자녀 인연 씨앗, 미발현) |
| 중년 | emerging_output | 0.65 | 자녀·프로젝트·결과물·전문성 형성 시작 |
| 말년 | direct_late_benefit(정점) | 0.85 | 자녀복·노후 안정·창작물·연구 결과 직접 발현 |

> 문창·학당·태극·천의성처럼 학문·전문·치유 길성이 시주에 있으면 "늦게 발현되는 학문성·연구 성과·
> 후대에 남는 결과물"로 정점 해석을 강화한다(제안서 D).

### 8-3. 재활성화(reactivation) — 4주 공통

평소 비정점 단계에서는 배경/잠재값이지만, 다음 조건에서 보조 사건 신호로 승격(모든 주 동일):

```text
조건(OR):
  - 대운/세운/월운이 그 주(해당 간·지)와 합 또는 충/형/파/해
  - 동일 지지가 운에서 반복(해당 주 지지 재출현)
  - 동일 길성이 운에서 재출현
  - 질문 intent가 그 주의 scope(§4) 궁성과 정렬
효과: weight_boost +0.25, event_power: background/seed → medium
해석 틀(길성): "직접 사건은 현재 운·정점 주가 만들고, 비정점 주의 길성은 그 주 궁성 경로
         (년=오래된 인연·평판 / 월=조직·사회 / 일=본인·배우자 / 시=자녀·결과)로 '도움의 가능성'을 보탠다"
해석 틀(흉살): "비정점 주의 흉살은 그 주 궁성 경로의 '긴장·리스크 가능성'을 보탠다 — 단정 아닌 주의 신호"
금지 해석(전 주·전 극성): ["그 시기에만 작동하고 끝난다", "비정점 시기에 직접 사건 단독 생성",
                 "길성이 흉운을 완전히 제거", "흉살이 반드시 사고/실패를 만든다"]
```

### 8-4. 주별 생애단계 작동 — 흉살(성향·리스크 곡선)

흉살도 **동일한 weight shape(§8-1)·재활성화(§8-3)** 를 따른다. 단 의미는 자산이 아니라 **성향·긴장·
리스크**다(여전히 보조 — 단정 금지, §2·§6). 정점 이전 = 잠재 성향(미발현), 정점 = 직접 발현,
정점 이후 = 체화·잔존 패턴.

| 주(정점) | 정점 이전(잠재) | 정점(직접) | 정점 이후(잔존) |
|---|---|---|---|
| 년(초년) | — | 초년 환경 긴장·집안 이슈·외부 평판 리스크 | 출신·오래된 갈등·평판 약점이 배경 리스크로 잔존 |
| 월(청·중년) | 부모·성장환경의 긴장이 잠재 | 직장·조직 마찰·경쟁·구설·압박(작용력 최대) | 누적된 사회적 마찰 패턴·경력상 갈등 잔재 |
| 일(중년) | 기질의 씨앗(예민·충동 잠재) | 본인 성격 긴장·배우자궁 갈등·몸/건강 긴장 | 체화된 성향·만성 패턴 |
| 시(말년) | 늦게 불거지는 리스크 씨앗(미발현) | 자녀 문제·결과물 압박·노후 건강 리스크 | (정점이 말년이므로 잔존 단계 없음) |

> weight 수치는 §8-2 곡선 shape를 그대로 재사용(자산/리스크 의미만 치환). 흉살의 정점·재활성화
> 시 출력은 §6 흉살 리스크 태그 문안(주의 신호)로만 변환하며, 단정 표현은 금지(§2-2).

### 8-5. 최종 반영 우선순위(특정 시점 사건 판단)

```text
1.대운 → 2.세운 → 3.정점 주(시기에 맞는 주)·일주 자극 → 4.월운 → 5.해당 intent 궁성
→ 6.신살·길성 보정 → 7.비정점 주 길성 = 배경/잠재/완충/외부 도움(보조, 재활성화 시 승격)
```

---

## 9. Phase A — LLM 입력 enrichment (이번 작업)

**목표**: score 불변. LLM에 "이름"이 아니라 "위치·길흉·intent·생애단계가 반영된 구조화 해석 태그"
전달.

### 9-0. 수치 노출 정책(확정) — LLM엔 한글 강도어만

내부 `internal_weight`(0~1+)는 **LLM payload에서 제외**하고 다음 4밴드 한글 강도어로만 변환한다.
숫자는 debug/shadow 로그에만 남긴다(LLM이 점수로 오해·과반영 방지).

| internal_weight | llm_strength |
|---|---|
| 0.00 ~ 0.25 | 약함 |
| 0.25 ~ 0.55 | 보조 |
| 0.55 ~ 0.80 | 강함 |
| 0.80 이상 | 매우 강함 |

`effect_tags`(완충/주의/이동성 강화/배경 지원 등)도 숫자 없는 한글 태그로만 전달한다.

### 9-1. 생애단계/재활성화 안내 — A-2(리포트 경로 전용, 2026-06-25 확정)
- **챗 경로 불가(측정 결과)**: 무거운 도메인 질문(career ≈ 10,856 tok)은 trim 임계 아래
  여유가 ~140 tok뿐. 챗 프롬프트에 근묘화실 안내 텍스트를 추가하면 `serialize_with_guard`의
  excerpt 트리머(`excerpts[:4]`)가 그 질문에서만 발동 → 캐시 고정 prefix의 신살 excerpt가
  차등 삭제 → `test_fixed_prefix_identical_across_questions`(캐시 불변) 위반. 따라서 챗은 A-1만.
- **리포트 경로에 부착(확정)**: 토큰 예산이 큰 리포트(총운 50장)의 신살 섹션 작성 지침
  `report_service._SECTION_GUIDES["F-05"]`에 근묘화실 정점 시기·평생 작동(정점 전 잠재/정점 후
  배경·누적)·운 재활성화 원리를 추가(보조 전제·단정 금지 유지). 챗 토큰·캐시 불변에 무영향.
- **후속 옵션(보류)**: 챗에도 넣으려면 trim 우선순위 리팩터(신살 텍스트를 캐시 excerpt보다 먼저
  트림) 필요 — 별도 작업.

### 9-2. 이벤트 후보(`LlmEventCandidate`) — 가변 측
- 신규 필드 `sinsal_modifiers: list[LlmSinsalModifier]` 추가(제안 #11). LLM 노출 subset
  (`SinsalModifier`에서 `internal_weight`/`internal_factors` 제외):
  ```text
  LlmSinsalModifier = { star, position, source, polarity, domain_match(bool),
                        activation_status, llm_strength, effect_tags, palace_tags }
  예: {star:"역마", position:"month", source:"yearly", polarity:"neutral", domain_match:true,
       activation_status:"strongly_activated", llm_strength:"강함", effect_tags:["이동·변동성 강화"]}
      {star:"천을귀인", position:"day", source:"natal", polarity:"positive", domain_match:true,
       activation_status:"activated", llm_strength:"보조", effect_tags:["위기 완화·도움 가능성"]}
  ```
- 운 신살이 원국 어느 자리를 합·충·형으로 건드려 발동했는지(재활성화 포함)를 activation_status·effect에 반영.
- `llm_guidance` 한 줄: "이직 압력은 강하나 무리한 계약보다 주변 조언·보호장치로 조정" 류.

### 9-2b. A-1 구현 결정(토큰 가드, 2026-06-25)
- **부착 대상 쿼리**: 궁성 정렬이 의미 있는 `DOMAIN_ANALYSIS`/`EVENT_EXPLANATION`/`TIMING_SEARCH`/
  `DECISION_SUPPORT`에만 부착. 광역 총운(`FORTUNE_OVERVIEW`)은 12달 요약으로 이미 토큰이 빽빽해
  per-후보 신살이 변별력 없이 토큰만 늘리므로 제외(회귀: `test_monthly_overview` 토큰 초과 방지).
- **부착 후보 수**: natal 신살은 도메인 레벨(후보 무관 동일)이라 상위 `SINSAL_PAYLOAD_MAX_CANDIDATES`
  (기본 2)개 후보에만 부착 — 전 후보 중복으로 인한 토큰 낭비 차단.
- 두 값 모두 `sinsal_modifier_config.py` 상수(튜닝 가능).

### 9-3. 직렬화·지시문
- context_reducer 직렬화(현 `신살(보조): a,b` 라인)를 위치·길흉·domain_match가 보이는 형태로
  승격. 기존 `_SINSAL_POSITION_INSTRUCTION`·`_LUCK_SINSAL_INSTRUCTION`·`_AUXILIARY_INSTRUCTION`은
  유지하되, "구조화 태그가 있으면 그 effect/domain_match를 우선 따른다"는 한 줄 추가.

### 9-4. 사전(`sinsal_text.json`)
- `byPosition`(social/personal)·`fromLuck`은 이미 존재. 년주 길성 생애단계·재활성화 문안이
  부족하면 `sinsal_text.json`에 `lifeStage`/`reactivation` 필드 보강(validate→compile 파이프라인,
  규칙 5).

---

## 10. Phase B — 스코어링 numeric 반영

용신 operational_role(`scoring_operational.py`)과 **동일한 shadow sidecar 패턴**으로 구현한다.
**B-1(shadow 관측) 먼저 → 분포 검증 → B-2(운영 반영) 별도 승인.**

### 10-1a. B-1(폐기) — score 채널 모델

초기 B-1은 신살 numeric 을 `score`(발생 가능성)에 일률 가산했다. **shadow 검증에서 구조적 결함 확인
(2026-06-25)** → **폐기**:
- 같은 기간 내 모든 사건에 동일 delta(96%) — 사건 변별 불가, 기간 전체 일률 이동.
- **길흉 방향 역행(≈981행)**: 길성(+)이 흉사건 발생 가능성을 올리고 흉살(−)이 길사건을 내림 —
  신살은 발생 가능성 장치가 아니므로(스펙 §2-1·§6) 잘못된 채널.

### 10-1b. B-1 v2(구현 완료 2026-06-25) — favorability/risk/mitigation/texture 채널 shadow

> **상태**: 구현·검증 완료. 게이트 OFF 기본. 33차트 관측(career): 10,066행,
> **occurrence_score_delta=0 전행**(발생 가능성 불변), 채널 활성 49%, fav −0.12~0.12·risk/mit 0~0.20,
> 불변 위반 0. 방향 역행 소멸. B-2 진입은 별도 승인.


신살은 **발생 가능성(occurrence_score)을 바꾸지 않는다**(`occurrence_score_delta = 0` 고정). 이미
생성된 사건 후보의 **길흉·리스크·완충·질감** 채널만 보정한다(사용자 확정 2026-06-25).

- **모듈**: `sinsal_numeric_scoring.py`. `apply_sinsal_channel_shadow(result, candidates,
  ganji_by_period, *, domain, coef_override) -> list[dict]`(순수). 게이트 wrapper
  `sinsal_channel_sidecar(...)` 는 `SINSAL_NUMERIC_SHADOW_ENABLED` off면 `None`.
- **불변(강화)**: `occurrence_score`/`ranking`/`favorability 원본`/`polarity`/`final`/operational guard
  **무변경**. EventCandidate 미변경(index 기반 dict). event_engine·reduce·LLM 미투입.
- **채널별 산출(재활성 신살만, §8 기간 신호)**:
  ```
  for 후보 c (period P, 운간지 G):
    occurrence_score_delta = 0                                  # 발생 가능성 절대 불변
    fav = risk = mit = 0; texture = []
    for 원국 신살 s (polarity, position) where react(G,s):       # 복음 재활성만(배경 신살 제외)
      w = DOMAIN_OVERRIDE[domain][position] or PILLAR_DEFAULT_WEIGHT[position]   # §7 위치/intent
      if 길성: mit += AUSPICIOUS[s].mitigation × w × BOOST;  fav += AUSPICIOUS[s].favorability × w
      elif 흉살: risk += INAUSPICIOUS[s].risk × w × BOOST;   fav += INAUSPICIOUS[s].favorability × w (음수)
      elif 중립: texture += [TEXTURE[s]]                      # 역마·도화·화개·문창 = 질감 태그(숫자 0)
    clamp: fav∈[−CAP,+CAP], risk∈[0,CAP], mit∈[0,CAP]          # 0~1 분수 스케일(§6)
  ```
  길성=완충·도움(mitigation↑·favorability↑), 흉살=리스크·마찰(risk↑·favorability↓), 중립=질감 태그.
  → 길성이 흉사건 발생 가능성을 올리는 역행 소멸(발생 가능성 채널 미접촉).
- **산출물**: `sinsal_shadow_report.py`(독립) → 채널 컬럼(occurrence_score_delta=0·favorability_delta·
  risk_delta·mitigation_delta·texture_tags). `scripts/sinsal_shadow_harness.py` → CSV/JSON.
- **LLM 노출(B-2 시)**: 숫자 미노출 — `완충/도움 가능성`·`리스크 상승·주의`·`이동성` 등 한글 태그만(§9).
- **불변 테스트**: gate off→None, occurrence_score_delta 항상 0, 후보 객체 불변,
  invariance_snapshot(score/polarity) before==after, 채널 부호(길성 mit≥0·fav≥0 / 흉살 risk≥0·fav≤0),
  중립=texture만, 캡 경계.

### 10-2. B-2 운영 반영 (구현 완료 2026-06-25 — 리포트 + 챗)

- **리포트 경로**: `report_event_input.precise_candidate_clusters` 기간 클러스터에 채널 색채 노트
  1줄 부착 — `channel_note_ko(fav,risk,mit,texture)` 로 **숫자 없는 한글**(`신살 시기색채: 완충 큼·
  리스크 주의·유리한 색채 (이동·변동성)`). 게이트 `SINSAL_CHANNEL_APPLY_ENABLED`(롤백 1줄).
- **챗 경로(트림 우선순위 리팩터로 활성화)**: `LlmEventCandidate.sinsal_channel_note` 추가,
  `build_llm_input`에서 상위 N후보에 period 채널 노트 부착(신살 비용 ≈169tok).
- **트림 우선순위(§10-2 핵심)**: `serialize_with_guard` 다단계화 —
  **Tier0**: 토큰 초과 시 신살 보조(modifier·채널 노트)를 **캐시 prefix(excerpt)보다 먼저** 제거
  (`_drop_sinsal_aux`). 신살 의존 지시문도 조건부라 자동 제거. → 무거운 질문(career)에서도
  고정 prefix·후보 본문 보존 → **캐시 불변(test_fixed_prefix) 유지**. **Tier1**: 그래도 초과면
  기존 축소(excerpts[:4]·후보[:3]·근거 trim, 이미 신살 제거된 상태).
- **불변**: occurrence_score·ranking·favorability_ko 수치 무변경(보조 텍스트만). 챗 prefix 불변 검증
  (career·연애운 prefix 동일).
- **검증**: full suite 1113 pass. Tier0 강제 초과 테스트(신살 먼저 제거·excerpt 보존), 숫자 미노출.
- 규칙 9(사전계산) 정합: 복합 조합은 Precompute Store 경유. 요청 시 즉석 재계산 금지.

---

## 11. Config (튜닝 가능 초기 기본값)

신규 `saju_engines/sinsal_modifier_config.py`(가칭)에 집약:
`PILLAR_SCOPE`, `PILLAR_DEFAULT_WEIGHT`, `PILLAR_EVENT_DIRECTNESS`, `POSITION_LAYER_WEIGHT`,
`BRANCH_SPECIAL_WEIGHT`, `DOMAIN_OVERRIDE`, `AUSPICIOUS_EFFECT`, `INAUSPICIOUS_EFFECT`,
`SOURCE_EVENT_POWER`, `YEAR_AUSPICIOUS_LIFE_STAGE`, `REACTIVATION`. 값 출처 = 본 스펙(제안 채택).

---

## 12. 테스트·검증 계획

- 단위: 위치별 scope/weight derive, domain_match 게이트, 생애단계 분기(초년/중년/말년 경계),
  재활성화 조건(합/충/동일지지/intent), 시간미상(hour 없음) 안전, 구형 결과 fallback.
- 회귀: 기존 신살 테스트(`test_sinsal.py`, `test_chart_interpretation.py`) 불변 + 신규 픽스처.
- 통합: 채팅/리포트에서 `sinsal_modifiers` 직렬화가 토큰 한도(docs/09 8장) 내인지(규칙 9).
- Phase B 진입 시: shadow 하네스로 score/rank 영향 분포 관측(운영 불변 확인).

---

## 13. 확정 결정 기록 (2026-06-25 — 전부 확정)

1. **§7 도메인 갭** = ✅ `Domain` enum 불변. GENERAL + `palace_tags`로 children/late_life/project 흡수.
2. **§3 필드 배치** = ✅ `SinsalItem` 불변. 별도 `SinsalModifier` derive 모델.
3. **§8 범위·경계** = ✅ 4주 × 길성·흉살 전체. 생애단계 = 대운 경계 우선 → 나이 fallback → 시점 미상 기본.
4. **§6 계수** = ✅ 제안 계수표를 `initial_default`로 채택(고정값 아님, shadow·사례로 튜닝).
5. **§9 수치 노출** = ✅ LLM엔 계수 미노출, 한글 강도어(약함/보조/강함/매우 강함)·effect_tags만.

**Phase A 불변 보장**: event_score · favorability · final role · operational guard 변경 없음.
신살은 단독 사건 생성 금지. 길성=완충·도움·회복 / 흉살=리스크·긴장·주의 태그.
