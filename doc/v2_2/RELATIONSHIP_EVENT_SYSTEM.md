# RELATIONSHIP_EVENT_SYSTEM — 관계 사건 시스템 명세 (SSOT)

> 상태: **승인 (2026-07-24 데굴님) — P0-A 감사 착수 가능. P0-B는 P0-AUDIT-GATE 통과 후.**
> 근거: 연애 영상 2편 분석 의견서(2026-07-24) + 자산 조사 3건 + 조건부 승인 리뷰
> + 최종 검토(P0 분리·vocab 산출물·병합 규칙·user_facts 제한·shadow 순서 반영).
> 원칙: 연애운 점수 하나를 높이는 작업이 아니라, **관계가 어느 단계에서 어떤 방향으로
> 움직이는지 추적하는 사건 시스템**을 만든다. 배우자궁·배우자성·도화·합충은 동일한
> "사람이 들어온다" 신호가 아니라 활성화·노출·성립·품질·지속·종료 압력에 각각 다르게
> 기여한다.

관련 문서: `MARRIAGE_TIMING_ENHANCEMENT.md`(MT1~6), `EXTERNAL_IMPRESSION_SIGNAL.md`,
`LIFE_EVENT_INFERENCE.md`(발생·경험 분리 캘리브레이션), `docs/10_READING_PRODUCTS.md`(리포트
목차 규격 — 본 작업에서 목차 불변), `docs/17_DAILY_ILJU_FORTUNE.md`(오늘의 운세 — 별도 트랙).

---

## 0. 확정 결정 사항 (2026-07-24)

| # | 결정 | 내용 |
|---|---|---|
| D1 | 신규 벡터 적용 방식 | **우선 shadow**(설명·분류 전용, 점수/랭킹/확신도 delta=0), 검증 후 적용 승격 |
| D2 | 성별 해석 모드 | 기존 성별 정보가 있으면 **전통 모드(남=재성·여=관살) + 중립적 설명 병행**. 중립 모드는 성별 미상·동성 상대 명시·사용자 거부 시 |
| D3 | commitment·formalization | **이번 범위에 포함**하되 사용자 현실 marker 필수(§8-4 예외 규칙) |
| D4 | 오늘의 운세 love 확장 | **별도 릴리즈로 분리**(`DAILY_LOVE_CATALOG_EXPANSION` 트랙, §12) — 본 시스템의 완료 조건 아님 |

---

## 1. 영상 주장 반영/제한 정책 (명리 정책 SSOT)

| 영상 주장 | 판단 | 시스템 반영 방식 |
|---|---|---|
| 일지=배우자궁, 운에서 활성화되면 관계 사건 가능 | 적극 반영 | `spouse_palace_activation` 핵심 신호 |
| 육합·삼합·방합이 배우자궁을 건드리면 연애 가능성 증가 | 조건부 반영 | 합은 **관계 활성화**이지 성사 판정이 아님 |
| 충=변화 (좋은 관계엔 갈등, 정체된 관계엔 변화) | 적극 반영 | 충을 길흉이 아닌 `activation + separation_pressure` 복합 벡터로 처리 |
| 주변 글자가 합을 막거나 극하면 현실화 안 될 수 있음 | 적극 반영 | `realization_blocker`, `contested_combination`, `blocked_activation` |
| 들어오는 십성이 상관·겁재면 불리 | 제한 반영 | 만남은 가능하되 품질·지속성 하락 보정 신호로만 |
| 기혼자에게 연애 신호는 팬 활동·관심 대상 출현으로 발현 | 적극 반영 | 관계 상태별 `alternative_manifestation` |
| 도화 운 → 매력·인기 상승 | 보조 반영 | 도화는 `visibility/attraction` 신호로만 (§6) |
| 여성 편관 강운 → 남성과 엮일 가능성 | 전통 모드에서 반영 | 관성 활성화. 단 성사·품질·결혼은 별도 판단 |
| 관살혼잡 → 이성 문제·이별 | 조건부 반영 | 선택 과다·관계 모호성·경쟁 신호로만 |
| 申=모르는 사람, 辰=아는 사람, 子=사적인 사람 | **규칙화 금지** | 만남 경로는 지지 자체가 아니라 활성화된 원국 궁위+현실 문맥으로 추론 (§9) |
| 도화 많을수록 인기 많음 | **선형 규칙 금지** | 일정 수준 이후 선택 혼란·관계 분산까지 처리 |
| 겁재 오면 상대를 빼앗김 | **단정 금지** | 경쟁·주의 분산·관계 자원 충돌 신호로 제한 |

합충형파해는 결과가 아니라 **작용 방식**이다:
- 합 = 결속뿐 아니라 합거·쟁합·지연·모호한 묶임으로도 발현
- 충 = 이별뿐 아니라 정체 노출·관계 재정의(동거·혼인·이사)로도 발현

---

## 2. 소비 표면 3분리 (억지 통합 금지)

| 표면 | 성격 | 본 시스템 적용 범위 |
|---|---|---|
| 테마사주(리포트) | 개인 명식·5년·고정 목차(R-*/RP-*) | episode·벡터를 섹션별 소유권에 따라 공급 (§10). **목차 불변** |
| AI 채팅 상담 | 개인화·멀티턴·질문 중심 | 관계 상태 해소 + 통합 디렉티브 + episode (§7, §11) |
| 오늘의 운세 | 60일주 공통·비개인화 | **본 시스템 미적용.** 별도 트랙(§12)에서 라이트 카탈로그만 확장 |

---

## 3. 3층 모델 — E4 발현 단계 ≠ 관계 단계 ≠ 관계 상태

E4 timeline의 `awareness→exploration→action→decision→completion`은 **일반 사건의 발현
과정**이다. 관계 단계는 **관계 자체의 상태 머신**이고, 관계 상태(품질)는 또 별도의 축이다.
E4의 `decision`은 "연애 시작 결정"일 수도 "이별 결정"일 수도 있으므로 E4만으로 관계
단계를 알 수 없다. 세 층을 분리해 합성한다.

```python
RelationshipEpisode(
    event_timeline=E4Timeline,            # 기간 묶음·ActivationWindow (기존 E4 재사용)
    relationship_stage=RelationshipStage,  # 관계 진행 단계 (신규 상태 머신)
    relationship_condition=RelationshipCondition,  # 관계 품질 상태 (신규 벡터)
)
```

### 3-1. 관계 단계 (RelationshipStage)

```text
NONE → AWARENESS → CONTACT → DATING → COMMITMENT → FORMALIZATION → MARRIED
```

| 단계 | 의미 | 기존 MarriageStage 대응(호환 매핑) |
|---|---|---|
| NONE | 특정 대상·관계 접점 없음 | (없음) |
| AWARENESS | 관심을 받거나 특정 대상이 눈에 들어옴 | awareness |
| CONTACT | 소개·연락·만남·재접촉 | contact |
| DATING | 상호 관계가 연애로 성립 | relationship |
| COMMITMENT | 독점성·장래·동거·가족 소개 논의 | commitment |
| FORMALIZATION | 약혼·혼인 준비·구체적 절차 | formalization |
| MARRIED | 혼인 또는 사실상 부부 관계 | family_expansion(부분) |

기존 `derive_marriage_stage`의 awareness/relationship 상한 캡·`_MT_ACTION_CODES` 구조는
유지하되, 본 시스템의 canonical 어휘는 위 7단계다. 정확한 매핑은 P0 어휘 감사에서 확정.

**기존 `MarriageStage` 직접 확장 금지 (2026-07-24 확정)** — 기존 enum을 즉시 변경하면
LLM 입력 검증·사전 `stageHint`·리포트 직렬화·회귀 테스트·MT1~MT3 stage 도출·
컨텍스트 리듀서가 동시에 영향받는다. P0에서는 신규 `RelationshipStage` StrEnum을
별도 정의하고 어댑터로만 연결한다:

```python
class RelationshipStage(StrEnum):
    NONE = "none"; AWARENESS = "awareness"; CONTACT = "contact"
    DATING = "dating"; COMMITMENT = "commitment"
    FORMALIZATION = "formalization"; MARRIED = "married"

def marriage_stage_to_relationship_stage(stage: MarriageStage) -> RelationshipStage: ...
```

`family_expansion`은 관계 단계가 아니라 결혼 이후의 가족 사건이므로 신규 상태 머신에서
분리한다: `RelationshipStage.MARRIED` + `FAMILY_EXPANSION` 후속 이벤트.

### 3-2. 관계 상태 (RelationshipCondition)

```text
QUIET / GROWING / AMBIGUOUS / STABLE / FRICTION / DISTANCING / SEPARATED / RECONCILING
```

같은 DATING이라도 `DATING+GROWING`(깊어짐) / `DATING+AMBIGUOUS`(정의 불분명) /
`DATING+FRICTION`(충돌 증가) / `DATING+DISTANCING`(연락 감소)은 서로 다른 사건이다.
이 분리가 "연애운이 있다"와 "연애가 잘된다"를 구분한다.

### 3-3. 상태 전이 불변식

- `NONE → MARRIED`(및 NONE → FORMALIZATION) 직접 점프 금지 — 단 §8-4 예외 근거 있으면 허용
- 현재 연애 없음 → `BREAKUP` 출력 금지 (§8-5 변환 규칙 적용)
- 과거 이별 이력 없음 → `RECONCILIATION` 출력 금지
- 알려진 상대 없음 → 상대의 감정·행동 단정 금지
- 한 사람 명식만으로 "상대도 결혼을 원한다" 판정 금지
- 기혼자에게 별도 문맥 없이 "새 연인이 생긴다" 기본 출력 금지 → 대체 발현(§8-6)
- 동일 episode의 같은 사건을 여러 달 중복 출력 금지

---

## 4. 7축 효과 벡터 — 산출 책임 SSOT

연애운 종합점수 1개로 계산하면 만남·갈등·결혼·이별이 뒤섞인다. 관계 후보마다 7축을
별도 산출하며, **각 축이 어떤 신호를 읽고 어떤 신호를 읽지 않는지**를 아래 표로 고정한다.

```python
RelationshipEffectVector(
    activation, exposure, realization, experience_valence,
    stability, formalization, separation_pressure,
)
```

| 축 | 질문 | 주 산출원 | 읽지 않는 것 |
|---|---|---|---|
| `activation` | 관계 영역에 변화가 발생하는가 | 배우자궁 합충형파해(RelationPalace 신호), 배우자성 출현(MT1), 반복 활성(MT2) | 도화(→exposure), 용신 길흉(→valence) |
| `exposure` | 실제 사람을 접할 환경이 열리는가 | 현재 생활 환경·조직/지인/온라인 접점(궁위 활성), 질문·프로필·발화 사실, transit visibility(§6) | 명식 추론만으로 노출 단정 금지 |
| `realization` | 관심·접촉이 실제 관계로 이어질 수 있는가 | activation + exposure + blocker(합거·쟁합·극) + 작동성(투간·통근·계절) | 도화 단독, 반합 단독 |
| `experience_valence` | 그 관계를 편안하게/부담스럽게 경험하는가 | 용희기신, 관계 압박(편관 부담·겁재 경쟁·상관 마찰), 보호·수용(인성) 신호 | 발생 점수와 혼합 금지 |
| `stability` | 관계가 일정 기간 유지될 힘이 있는가 | 지속 신호(운지 통근 등), 쟁합·합거·형해파의 부정 기여, 층위(대운·세운·월운) 반복 | 활성화 강도(강한 활성≠안정) |
| `formalization` | 독점·동거·혼인 절차로 나아갈 힘이 있는가 | 책임·가족·계약·생활 결합 marker, MT formalization_link, MT6 static prior(참고값) | 배우자성 출현 단독 |
| `separation_pressure` | 거리두기·중단·종료 압력이 커지는가 | 충형파해(배우자궁), 배우자성 합거·무근·약화, 거리·신뢰·접촉 약화, REL 위험 참조 | 겁재·상관·편관 **단독** 트리거 금지 |

`experience_valence`는 발생 점수와 반드시 분리 — `occurrence=confirmed, experience=negative`가
동시에 보존돼야 과거 검증이 가능하다(LIFE_EVENT_INFERENCE 발생·경험 분리 원칙과 일치).

### 4-1. 이중 반영 금지 불변식 (P1 핵심)

`RelationPalaceEngine`의 합충형파해는 **기존 이벤트 점수에 이미 반영**돼 있다
(relation delta ≤22). 같은 신호로 신규 벡터를 만들어 다시 후보 승격에 쓰면 충 하나가
순위를 이중으로 끌어올린다. P0-A 실측에서 랭킹은 점수보다 **confidence 승격**
(palace 부여→strong 후보 승격→상위 정렬축)이 지배함이 확인됐으므로, shadow 불변식은
delta=0만으로 부족하다. 초기 운영 강제(확대판):

```text
usage = shadow_explanation_only
score_delta = 0
raw_score_delta = 0
confidence_delta = 0
personal_match_delta = 0
life_fit_delta = 0
ranking_delta = 0
candidate_generation = false
candidate_suppression = false
```

**P1의 정확한 성격 (2026-07-24 표현 확정)**: P1은 legacy 결함(방향 누수·cap 포화·
new_relationship 사각지대)을 *수정*하는 단계가 아니라, **결함을 손실 없이 관측하고
차세대 사건 분류에 필요한 의미 정보를 생성하는 단계**다. 실제 후보 생성·랭킹 수정은
별도 적용 승인 이후 수행한다. cap 포화 대응으로 벡터 증거는 원시 구조를 보존한다:

```python
RelationshipActivationEvidence(
    relation_kinds=["chung", "hyeong"], independent_causes=2,
    affected_palaces=["day", "year"], compound=True,
    raw_activation=..., capped_legacy_delta=22,
)
```

이후 기존 relation_delta와 벡터의 관계를 다음 중 하나로 정리(별도 승인):
1. 기존 가산을 activation으로 흡수하고 기존 가산 제거
2. 기존 점수 유지 + 신규 벡터는 사건 종류 분류에만 사용 ← **단기 확정(게이트 ⑤)**
3. legacy ranking과 차세대 ranking 병렬 검증

**전환 결정 시점 (옵션 2 영구화 방지)**: P4 shadow episode 검증 완료 후 옵션 1 또는
옵션 3 중 하나를 선택한다. 결정 없이 legacy 점수와 신규 의미 체계를 장기 이중 유지하지
않는다. 처음부터 둘 다 점수에 적용하는 구현은 금지.

### 4-2. D2 병행 해석 병합 규칙 — 신호 계산 1회, 의미 해석만 복수

전통 모드와 중립 모드가 독립적으로 후보·점수를 만들면 같은 신호(예: 여성 명식의 관성
출현)가 두 개의 독립 원인으로 이중 계산된다. 강제 규칙:

```python
PartnerSignal(
    canonical_signal="officer_activation",          # 계산은 이것 1회
    traditional_role="male_partner_signal",          # 해석 lens 1
    neutral_roles=["relationship_responsibility",    # 해석 lens 2
                   "formalization_pressure"],
)
```

점수 불변식: `전통 해석 + 중립 해석 ≠ 독립 원인 수 2` — 증거 계약(§8)의 "독립 원인
2개" 집계에서 같은 canonical_signal의 해석 2종은 원인 1개로만 센다.

출력 우선순위:
- 성별·관계 대상이 명확한 질문 → 전통 해석이 주 설명, 중립 해석은 조건·보완
- 성별 미상·관계 유형 불명확 → 중립 해석이 주 설명
- 사용자가 특정 해석 체계 요청 → 해당 모드가 주 설명
- 두 모드가 충돌 → "둘 다 가능" 나열 금지, 공통으로 확정 가능한 관계 작용만 출력

---

## 5. 배우자궁 활성화 감지기 — 벡터 반환

기존 RelationPalaceEngine·MT2·MT4·structure_patterns(JAENGHAP/HAPGEO/HAPBAN) 신호를
재조합한다(신규 명리 계산 없음). "육합=좋음, 충=나쁨" 계산 금지 — 각 작용을 벡터로 반환.

| 배우자궁 작용 | 활성화 | 안정성 | 종료 압력 | 기본 해석 |
|---|---:|---:|---:|---|
| 육합 | 높음 | 소폭 상승 | 낮음 | 접촉·결속·관계 재정의 |
| 완성 삼합 | 높음 | 문맥 의존 | 낮음 | 관계 영역 확장·집중 |
| 반합·부분 삼합 | 중간 이하 | 중립 | 낮음 | 잠재 활성화, 단독 성사 근거 부족 |
| 방합 | 중간~높음 | 환경 의존 | 낮음 | 동일 환경·집단·생활권 결속 |
| 동일 지지 재림 | 중간~높음 | 문맥 의존 | 중간 | 관계 주제의 반복·강조 |
| 충 | 매우 높음 | 하락 가능 | 높음 | 이동·재정의·갈등·분리 가능성 |
| 형 | 중간 | 하락 | 중간 | 반복 갈등·압박·미해결 문제 |
| 해 | 중간 | 하락 | 중간 | 기대 불일치·서운함·간접 마찰 |
| 파 | 중간 | 하락 | 중간 | 조건·약속 일부 깨짐 |
| 쟁합·투합 | 높음 | 하락 | 중간 | 선택 경쟁·모호성·우선순위 충돌 |
| 합반·합거 | 활성화 유지 | 하락 | 중간 | 신호는 있으나 현실화 지연·흡수 |

이미 나쁜 관계의 배우자궁 충=이별 위험↑, 결혼 논의를 미뤄온 관계의 충=동거·혼인·이사
등 형태 변화 — 현재 관계 상태(§7)와 결합해야 방향이 정해진다.

---

## 6. 도화 정책 + 동적 노출 시기 모듈 (신규)

### 6-1. 정적 프로파일 (기존 재사용)
`external_impression`은 원국 기반 정적 인상 프로파일 — 도화는 이벤트 점수에 이미
미반영이며 visibility 전용. 그대로 유지하고 `visibility_modifier`로만 연결.

### 6-2. transit_relationship_visibility (신규 모듈 — P2)
사용자 요구는 "특정 세운·월운에 도화가 들어올 때 관심·노출·만남 가능성이 증가하는
시기"다. 정적 프로파일과 별개로 **운 기반 동적 visibility**를 신설한다.

```python
TransitRelationshipVisibility(
    period,
    natal_visibility_band,      # external_impression band 재사용
    transit_dohwa_activation,   # 운 도화 (기존 luck_sinsal 감지 재사용)
    hongyeom_activation,
    expression_activation,      # 식상 표현 활성
    visibility_score,
    ambiguity_modifier,         # 과다·중첩 시 선택 혼란 보정
)
```

이 모듈이 보정하는 것: 관심 증가 / 소개·연락 접점 / 사회적 노출 / 후보 수(choice_volume).
**직접 올리면 안 되는 것: 관계 성립 / 관계 안정 / 결혼 진행 / 상대의 진정성.**

도화 과다·중첩 시 보정: `attention_volume↑, selection_clarity↓, relationship_focus↓,
ambiguity↑` — "인기는 많지만 누구와 정할지 어렵다"를 표현할 수 있어야 한다.

---

## 7. 관계 상태 해소기 (Resolver) — 시간·상대 동시 처리

프로필+발화+질문 3원 우선순위만으로는 부족하다. 다음 발화는 서로 다르다:
"지금 남자친구가 있어" / "작년에 남자친구가 있었어" / "남자친구랑 헤어질까?" /
"전 남자친구와 다시 연락하고 있어" / "친구 남자친구 사주를 봐줘"(대상 전환 — 원칙 7).

```python
ResolvedRelationshipState(
    target_id,            # 익명 서명 (실명 아님, risk_engine.RelationshipContext 규약)
    target_role,
    relationship_status,
    contact_state,
    temporal_status,      # current / past / planned / hypothetical
    source_type,          # question / conversation_fact / profile
    source_turn,
    confidence,
)
```

우선순위 + 유효기간:

```text
현재 질문의 명시 사실
> 최근 대화의 현재형 확정 사실 (user_facts 신규 relationship_status 슬롯, user_explicit만)
> 저장된 현재 episode
> 2단계 프로필 marital_status
> 명식 추론 금지 (관계 상태를 사주에서 추측하지 않는다)
```

- **과거형 발화는 현재 상태를 덮어쓰지 않는다** (temporal_status=past로 별도 보존)
- 프로필=연애중인데 "어제 헤어졌어" 발화 → 발화 우선 + **불일치 텔레메트리 기록**
- user_facts 슬롯 신설은 기존 `_FACT_RULES` 규약(rules-first 정규식, LLM 미사용) 준수

### 7-1. user_facts 범위 제한 (2026-07-24 확정)

user_facts 원장은 용량 제한(cap 12)·singleton 병합 성격이라 관계 **이력**(A 시작→A 이별→
B 시작→A 재연락→B 이별) 보존에 부적합하다.

- **P0에서 user_facts에 추가 허용**: 현재 관계 상태 / 현재 연락 상태 / 현재 질문 대상 /
  약혼·결혼 준비 여부 / 사용자가 명시한 **현재형** 사실
- **금지 조항**: user_facts를 장기 관계 이력 저장소로 사용하지 않는다. 만남·시작·이별·
  재회 이력은 이후 별도 원장으로 분리한다(P0 범위 아님):

```python
RelationshipEpisodeFact(
    episode_id, target_id, target_role, event_type,
    occurred_at, status, source_turn, source_quote,
)
```

---

## 8. 사건별 증거 계약

관계 이벤트 사전(최소 키 분리):

```text
만남·성립: REL_VISIBILITY_RISE / REL_NEW_CONTACT / REL_RECONTACT /
           REL_MUTUAL_INTEREST / RELATIONSHIP_START / RELATIONSHIP_AMBIGUITY
진행:      RELATIONSHIP_DEEPENING / REL_EXCLUSIVITY_DISCUSSION / REL_FAMILY_INTRODUCTION /
           REL_COHABITATION_DISCUSSION / REL_COMMITMENT_DECISION / REL_FORMALIZATION_PREP /
           REL_MARRIAGE_CANDIDATE
갈등·종료: RELATIONSHIP_FRICTION / RELATIONSHIP_DISTANCING / REL_CONTACT_FADE /
           REL_SEPARATION_RISK / REL_RELATIONSHIP_END_CANDIDATE / REL_RECONCILIATION
기혼·장기 대체: REL_PARTNER_REFOCUS / REL_PARTNER_LIFE_CHANGE /
           REL_SOCIAL_ATTRACTION_INCREASE / REL_FANDOM_OR_IDEALIZATION /
           REL_SHARED_LIFE_RESTRUCTURE
```

`REL_RELATIONSHIP_END_CANDIDATE`는 미래 예측용. `RELATIONSHIP_END_CONFIRMED`는 사용자
피드백·과거 사건 분석에서만 사용.

### 8-1. 새로운 만남
직접 원인 1개 또는 **서로 독립적인** 보조 원인 2개 필요.
- 직접: 배우자궁 강한 활성화 / 작동성 있는 배우자성 출현 / 궁·성 동시 연결
- 보조: 도화·표현 매력 상승 / 사회적 노출 증가 / 대운·세운·월운 중첩 / 공망 해소·숨은 배우자성 현실화
- `exposure=DENIED`면 실제 만남으로 승격 금지 → "관심·관계 욕구 증가" 또는 "온라인·간접 관심"으로 강등

### 8-2. 연애 시작
필수: CONTACT 이상 현실 접점 + 배우자궁/배우자성 직접 신호 + realization 임계 충족 +
치명적 blocker 없음. **도화 단독·편관 단독·반합 단독으로 RELATIONSHIP_START 금지.**

### 8-3. 관계 심화
필수: 현재 DATING 이상 + 안정 신호 2개 층위 이상 지속 + 궁/성 반복 활성 +
separation_pressure 임계 미만.

### 8-4. 결혼 논의·공식화 (D3: 포함하되 현실 marker 필수)
필수 그룹: ①현재 관계 존재 또는 이전 기간 관계 형성 궤적 ②궁·성 연결 ③안정성/지속성
신호 ④formalization_link(가족·책임·계약·생활 결합) ⑤대운·세운 또는 세운·월운 층위 중첩.
차단: 강한 쟁합·합반 / 종료 압력이 공식화 신호보다 우세 / 단계 NONE + 중간 궤적 부재.

**궤적 필수의 예외(현재 단계 근거)** — 약혼 중·결혼 날짜 확정·동거+혼인신고 논의·상견례
완료 사용자는 시스템에 과거 궤적이 없어도 결혼 단계 후보 생성 가능:

```text
불변식: NONE → FORMALIZATION 직접 점프 금지
허용 근거: 이전 관계 episode
        OR 현재 stage가 COMMITMENT 이상이라는 사용자 명시 사실
        OR 공식화 현실 marker
```

독신 상태에서 결혼 점수 높은 해 → "그해 결혼" 단정 금지, 궤적으로 출력:
상반기 만남/재접촉 → 중반기 성립·심화 → 하반기 장래·가족 결정 가능성.
궤적 불성립 시 결혼 후보 강등.

### 8-5. 이별·종료 위험
필수: 현재 DATING 이상 + **독립적인 종료 원인 2개 이상** + separation_pressure 임계 충족.
독립 원인 예: 배우자궁 충·형·해·파 / 배우자성 합거·무근·심한 약화 / 경쟁·쟁합 /
현실 조건 붕괴 / 대운·세운 부정 중첩 / 월운의 실제 결정·단절 신호.
관계 없는 사용자에게 같은 신호 → 변환: 연락 안 이어짐 / 썸 흐려짐 / 성립 전 조건 어긋남 /
관심 대상 자주 바뀜.

### 8-6. 기혼·장기 관계 대체 발현
기혼·장기 관계 사용자의 "새 만남" 신호는 기본적으로 REL_PARTNER_REFOCUS·
REL_SOCIAL_ATTRACTION_INCREASE·REL_FANDOM_OR_IDEALIZATION 등으로 변환.

---

## 9. 만남 대상·경로 추론 (source_hints)

특정 지지 1개에 "모르는/아는/사적인 사람"을 할당하지 않는다. **운에서 활성화된 원국
궁위가 관계 신호를 매개하는가**를 본다.

| 활성화 궁위 | 제시 가능한 만남 경로 |
|---|---|
| 년주 | 외부 사회망·지인 확장·먼 지역·공개 활동 |
| 월주 | 직장·학교·조직·반복 출입 환경 |
| 일주 | 가까운 관계망·사적 접촉·이미 알던 사람 |
| 시주 | 취미·온라인·미래 프로젝트·새 커뮤니티 |

확정 사실이 아니라 `source_hint`(channel/confidence/basis)다. 새 사람 vs 기존 사람:
- 운 글자가 원국 관계망과 직접 연결 → 기존 지인·과거 접점 가능성↑
- 원국 연결 없이 운에서만 일시 강출현 → 새로운 사람·행사성 접촉 가능성↑
- 과거 episode와 같은 target_id·동일 구조 재활성화 → 재접촉 가능성
- 배우자궁 복음·반복 + 과거 이별 이력 → 패턴 재현·재회 가능성

상대 성격은 배우자성·십성·오행·활성 궁위 조합으로 제한적으로만. 직업·외모·나이 확장 금지.

---

## 10. 소비 표면별 배선 규격

### 10-1. 리포트(테마사주) 섹션 소유권 — 목차 불변, 내부 공급만 차등

| 섹션 | 신규 정보 소유권 |
|---|---|
| R-01 | 향후 핵심 관계 episode 1~2개 요약 |
| R-02 | 원국 성향만, 시기 사건 최소화 |
| R-03 | 배우자성·배우자궁 정적 구조 |
| R-04 | 관계 사건 종류와 변화 방향 |
| R-05 | 5년 episode 목록·연도별 단계 |
| R-06 | episode 내부 주목 월·activation window |
| R-07 | 위험·조건·현실 확인 포인트 |
| R-08 | 7축 점수 밴드와 근거표 |

궁합(RP-*) 모드 역할 분리: 개인 관계 시기=본인 명식 / 상대 관계 시기=상대 명식 /
두 시기의 동조=pairwise overlay / 결혼 성사=두 명식 공통 단정 금지 + 현실 상태 포함.

### 10-2. 채팅 — 통합 디렉티브 빌더 (신규 디렉티브 개별 추가 금지)

기존 관계 디렉티브(연애·결혼 통합/자기인식/인연출처/비규범 안심/관리/배우자성 가드/
큰 결정/만남 시기/이혼 severity)가 이미 과다하다. 신규 관계 지시는 **통합 빌더**로만:

```python
build_relationship_directive(
    intent, relationship_state, top_episode, risk_refs, output_surface,
) -> str
```

우선순위: 안전 가드 → 사용자 명시 사실 → 현재 관계 단계 → 사건 방향 → 위험 병기 → 표현 형식.

**기존 규범적 디렉티브 상속 금지·별도 감수 대상**:
- `_BIG_DECISION_DIRECTIVE`(운 저점=보류 권고), `_DIVORCE_SEVERITY_DIRECTIVE`(사유 일괄 분류)
- 폭력·위협 명시 시 사주상 회복 가능성을 우선하면 안 됨
- "성격·건강 문제는 극복 가능" 일괄 분류 금지
- 이혼 여부는 엔진이 권고하는 결정이 아님 — 사용자 안전·현실 조건 확인 우선

### 10-3. LLM 입력 — 토큰 예산·선택 직렬화

내부 계산은 실수값 보존, LLM에는 **밴드만** 전달:

```json
{"effect": {"activation": "strong", "realization": "moderate",
            "stability": "weak", "formalization": "weak", "separation": "moderate"}}
```

질문 유형별 축 선택 전송:
- "언제 만나요?" → activation, exposure, realization
- "결혼할까요?" → stability, formalization, separation
- "헤어질까요?" → condition, separation, recovery
- 총운 → 상위 episode의 핵심 축만

context_reducer의 기간 중복 제거·overview 도메인 상한은 재사용하되, **episode 단위 압축을
선행**한다(현 reducer는 event key·신호 계열 중심이라 동일 상대의 만남→성립→심화를 묶지
못함 — episode-aware 압축 신규).

### 10-4. 풀이 6부 고정 형식

①현재 관계 단계 ②기간별 진행 ③근거 ④대상·만남 경로 ⑤관계 품질과 위험 ⑥대체 발현.
좋은 신호와 위험 신호는 상쇄가 아니라 **발생과 경험을 동시에 설명**한다.

---

## 11. REL 위험 엔진과의 역할 분리

```text
relationship_event_engine: 만남 / 시작 / 심화 / 결혼 진행 / 거리두기 / 종료 후보 / 재회
risk_engine.REL:          경쟁 / 책임 충돌 / 금전 결합 위험 / 가족 부담 / 관계 불균형 / 갈등 확대
```

관계 이벤트 후보는 REL 위험 후보를 `risk_refs`로 **참조만** 한다(점수 이관 금지).

**배선과 노출의 단계 분리** (조건부 승인 §6):
- P0/P1: 라이브 입력 → shadow REL 컨텍스트 연결 (`set_risk_shadow_contexts(relationship_contexts=...)`
  갭 해소 — 현재 QA 스크립트 전용). 목적: 상태 해소기 실동작 검증, target_id 유지 확인,
  미혼 사용자 오귀속 측정, separation_pressure와 REL 위험 중복 조기 감사.
- P5: 검증된 REL risk_refs만 LLM에 노출.

**shadow 배선 순서 — 대상 해소가 생성보다 먼저다** (2026-07-24 확정). target_id·현재형
여부가 확정되기 전에 위험 후보를 만들면 shadow 밀도 데이터 자체가 오염된다:

```text
사용자 질문·프로필·동반자 해소 → target_id 결정 → temporal_status 결정
→ exposure 상태 결정 → RiskRelationshipContext 생성 → risk shadow 전달
```

**P0 shadow 필수 계측** (P5 노출 승격 판단의 근거 데이터):

```text
context_created / context_source / target_resolved / target_ambiguous /
temporal_status / profile_fact_conflict / exposure_status /
risk_candidate_count / risk_blocked_count / risk_suppressed_by_target
```

---

## 12. 별도 트랙 — DAILY_LOVE_CATALOG_EXPANSION (D4)

오늘의 운세는 개인 명식·관계 상태·특정 상대·episode를 사용할 수 없다. 본 시스템의
완료 조건에서 제외하고 별도 릴리즈로 관리한다.

- 허용 카탈로그 수준: `love_visibility / love_contact / love_harmony /
  love_misunderstanding / love_distance` (사건 확률 수준의 good/caution)
- **금지 키**: `relationship_start / breakup / marriage / reconciliation` — 60일주 공통
  운세에서 실제 사건 구체화 금지
- 개인화 시스템과 별도 버전 관리(dict 버전 트랙 분리)

---

## 13. 스키마 (권장)

```python
@dataclass
class RelationshipEventCandidate:
    event_key: str
    target_id: str | None

    stage_from: str
    stage_to: str
    condition_from: str | None
    condition_to: str | None

    start_period: str
    end_period: str
    peak_period: str | None

    activation_score: float
    exposure_score: float
    realization_score: float
    experience_valence: float
    stability_score: float
    formalization_score: float
    separation_pressure: float

    evidence: list[RelationshipEvidence]
    blockers: list[RelationshipBlocker]
    risk_refs: list[str]
    source_hints: list[SourceHint]
    alternative_manifestations: list[str]

    confidence: str
    narrative_mode: str


episode = RelationshipEpisode(
    episode_key, target_id,
    opening_window, peak_window, decision_window, possible_end_window,
    stage_path, condition_path,
)
```

---

## 14. 구현 로드맵 (조건부 승인 수정판)

각 Phase = 독립 PR. 완료 기준 = 타입 + 구현 + 단위 테스트 + 회귀 픽스처 + (해당 시)
byte 불변 검증.

### P0 — 어휘·런타임·불변식 감사 (P0-A 감사 → 게이트 → P0-B 구현)

실행 순서(2026-07-24 확정): **SSOT 문서 커밋 → P0-A 읽기 전용 감사 → 감사 결과
승인·문서 결정 로그 반영 → P0-B 구현.** 문서와 구현을 한 커밋에 섞지 않는다.

#### P0-A — 읽기 전용 감사
- **REL-EVENT-VOCAB-AUDIT**: 관계 이벤트 키 전 계층 매핑 확정 — EventKeyV2 /
  composite domain signal / TopicBuilder event_keys(M01 `relationship_start·relationship_end`,
  M02 `marriage·childbirth·family_change` 불일치 의심) / LlmEventCandidate.event_key /
  Event Graph event node / structure_patterns domain_hints / 리포트 R-/RP- 필터 /
  daily catalog key. **신규 키 설계보다 이 감사가 먼저다.**
- **기계 검증 가능한 vocab 산출물**: 사람이 읽는 표로 끝내지 않고
  `backend/dictionaries/relationship_event_vocab.json`으로 고정한다. 항목당
  canonical key + 계층별 alias + owner + report_sections + daily_equivalent. lint 규칙:
  ①TopicBuilder 관계 키는 vocab에 존재 ②Event Graph 관계 노드는 vocab에 존재
  ③structure pattern relationship domain hint는 vocab에 존재 ④daily 전용 키의 개인화
  이벤트 유입 금지 ⑤alias에는 canonical key 필수.
- 현재 활성 MT 프로파일 런타임 확인(`ACTIVE_MARRIAGE_PROFILE=production_candidate` 실측)
- **relation delta 기여 실측** — 평균이 아니라 축별 표:

  | 측정 축 | 확인 내용 |
  |---|---|
  | 관계 종류 | 합·충·형·파·해별 delta |
  | 궁위 | 일지와 비일지 차이 |
  | 이벤트 키 | 어떤 관계 키가 상승하는지 |
  | 방향 | 좋은 후보·나쁜 후보 모두 상승하는지 |
  | 랭킹 | Top-N 진입 전후 |
  | MT 중첩 | MT1·MT2·MT3와 중복되는지 |
  | 기간 중복 | 같은 신호가 여러 달 후보를 독점하는지 |
  | 출력 | LLM이 긍정적 만남으로 오독하는지 |

  필수 재현 사례: 배우자궁 충 단독 / 합 단독 / 합+충 / 쟁합 / 합거 / 합반 /
  관살혼잡 / 도화 강하지만 배우자궁 비활성.

  **핵심 질문**: 현재 relation delta가 "관계 사건의 움직임"을 올리는가, "좋은 연애
  가능성"을 올리는가? 후자라면 P1 벡터화 전에 legacy 점수 의미를 수정한다.

#### P0-AUDIT-GATE (P0-B 진입 조건)

```text
① REL-EVENT-VOCAB-AUDIT 완료
② 실제 런타임 MT 프로파일 확인
③ relation delta의 이벤트별 기여 측정
④ 기존 키 유지·alias·migration 결정
⑤ 기존 점수와 신규 벡터의 소유권 결정 초안

위 다섯 결과가 승인되기 전 신규 EventKey·stage enum의 영구 확정 금지.
(공용 타입 골격 작성은 허용, 기존 enum 변경·이벤트 키 확정은 게이트 이후)
```

#### P0-B — 기반 구현 (게이트 통과 후)
- 3층 타입 정의(shared_types) — 신규 `RelationshipStage`(§3-1, MarriageStage 직접 확장
  금지) + `RelationshipCondition` + E4 참조. 기존 `MarriageStage` 호환 어댑터 + 테스트
- 관계 상태 해소기(§7) — user_facts **현재형 사실 슬롯만** 신설(§7-1 범위 제한)
- REL 컨텍스트 shadow 라이브 배선(§11 순서·계측 준수)
- 신규 벡터 완전 inert(D1)

#### P0 완료 기준 (전 항목 충족 필수)

```text
[ ] 8계층 이벤트 키 매핑 완료
[ ] 모든 관계 키에 canonical/alias/owner 지정
[ ] 실제 런타임 MT 프로파일 확인
[ ] relation delta 이벤트별 기여 실측
[ ] 기존 점수와 신규 벡터의 이중 반영 0건
[ ] RelationshipStage·Condition·E4 타입 분리
[ ] 기존 MarriageStage와의 어댑터 테스트
[ ] 현재형·과거형·가정형 상태 해소 테스트
[ ] 프로필과 최신 발화 충돌 시 최신 명시 사실 우선
[ ] 특정 상대 target_id 오귀속 0건
[ ] REL shadow가 라이브 입력을 받되 LLM 노출은 0건
[ ] OFF 또는 flag 비활성 시 기존 출력 byte-identical
```

P0의 목적은 새 연애 풀이를 보여주는 것이 아니라, **그 풀이를 안전하게 만들 기반과
관측 경로를 확보하는 것**이다.

### P1 — 효과 벡터·중복 방지
- 7축 산출 책임(§4 표) 구현 — RelationPalace·MT2·구조 패턴 신호의 벡터 변환
- 이중 반영 금지 불변식(§4-1) 코드 가드 + "OFF 시 byte 불변" 회귀
- 벡터 shadow 텔레메트리

### P2 — 상대성·노출 신호
- 전통 배우자성 모드(기존 재사용) + 성별 중립 모드(D2)
- `transit_relationship_visibility`(§6-2) — 동적 도화·홍염·표현 visibility
- source_hints(§9) + exposure 해소

### P3 — 사건 증거 계약
- contact/start/deepening/commitment/formalization + friction/distancing/separation/reconciliation
- 현재 단계별 승격·강등(§8) + formalization 예외 규칙(§8-4, D3)
- 기혼자 대체 발현(§8-6)
- 도화·편관·반합 단독 성립 금지 가드

### P4 — Episode
- E4 ActivationWindow 재사용 + stage·condition 별도 상태 머신 합성(§3)
- 동일 상대·동일 사건 기간 병합, 재접촉·재회 episode 연결
- context_reducer episode-aware 압축

### P5 — 소비 표면
- 채팅 통합 관계 디렉티브 빌더(§10-2) + 기존 규범 디렉티브 감수
- 테마사주 섹션 소유권 공급(§10-1)
- Pairwise 동조 overlay
- REL risk_refs 노출(§11)
- LLM 토큰 예산·선택 직렬화(§10-3)

### P6 — 상용 검증
- 골든·음성 회귀(§15) + shadow 비교 + 과거 사건 캘리브레이션
- 익명 텔레메트리: relationship_context_source / resolved_relationship_status /
  event_stage / event_condition / episode_count / duplicate_suppression_count /
  risk_ref_count / alternative_manifestation_used / blocked_transition_reason
- 사용자 피드백(발생·경험 분리): 사람이 나타났나 / 관계가 시작됐나 / 기존 관계가 변했나 /
  경험은 좋았나 힘들었나 / 예측 시기와 실제 시기 차이
- canary → 승격

### 별도 트랙 — DAILY_LOVE_CATALOG_EXPANSION (§12)

---

## 15. 검증 기준 (회귀 0건 목표)

| 검증 항목 | 목표 |
|---|--:|
| 연애 중이 아닌 사용자에게 이별 사건 출력 | 0건 |
| 관계 이력 없이 재회 사건 출력 | 0건 |
| 현재 관계·연속 궤적 없이 결혼 단정 | 0건 |
| 도화 단독으로 연애 성립 판정 | 0건 |
| 합 단독으로 결혼 판정 | 0건 |
| 기혼자에게 기본적으로 새 연인 출현 판정 | 0건 |
| 한 사람 명식으로 상대 감정 단정 | 0건 |
| 동일 episode·동일 event 중복 | 0건 |
| 발생 점수와 경험 품질의 혼합 | 0건 |
| 편관·겁재·상관 단독으로 이별 판정 | 0건 |

골든 사례에 반드시 포함할 음성 사례:
- 도화가 강했지만 실제 연애는 없었던 시기
- 배우자성이 들어왔지만 접촉 환경이 없었던 시기
- 배우자궁 충이 있었지만 이별하지 않고 결혼·동거로 전환한 사례
- 합이 있었지만 썸·단기 관계로 끝난 사례
- 연애는 시작했지만 체감은 부정적이었던 사례
- 만남 없이 팬 활동·취미 몰입으로 발현된 기혼 사례
- 같은 해에 만남과 이별이 함께 있었던 사례
- 기존 상대와의 재회였던 사례

---

## 16. 모듈 구성·기존 자산 재사용

```text
relationship_state_resolver.py        # §7 (P0)
relationship_effect_vector.py         # §4 (P1)
spouse_palace_activation.py           # §5 (P1) — 기존 신호 재조합 어댑터
partner_symbol_resolver.py            # §D2 전통+중립 (P2)
transit_relationship_visibility.py    # §6-2 (P2)
relationship_event_contracts.py       # §8 (P3)
relationship_trajectory_engine.py     # §3·E4 합성 (P4)
relationship_episode_builder.py       # §13 episode (P4)
relationship_target_source.py         # §9 (P2)
relationship_narrative_adapter.py     # §10 통합 디렉티브 (P5)
```

| 기존 기능 | 재사용 방식 |
|---|---|
| MT1~MT4·MT6 (`marriage_*.py`) | activation 신호원·formalization_score·static_prior — MT6는 참고값만, 연·월 사건 직접 생성 금지 |
| `derive_marriage_stage`·`marriage_output_guard` | 단계 캡·출력 하드 가드 유지, canonical 어휘 매핑(P0) |
| `RelationPalaceEngine`·MT2·구조 패턴(쟁합·합거·합반·관살혼잡) | §5 벡터 변환 입력(신규 계산 없음) |
| `risk_engine.RelationshipContext`·REL 7그룹·shadow→EXPOSE 게이트 | §11 — P0 shadow 배선, P5 노출 |
| E4 `build_timeline`·ActivationWindow | episode 기간 묶음·발현 단계(§3) |
| `external_impression` | 정적 visibility band(§6-1), transit 모듈의 natal 입력 |
| 2단계 프로필 `marital_status`·`derive_relationship_status` | 해소기 입력원(§7) |
| user_facts 원장 | `relationship_status` 슬롯 신설(user_explicit 규약 유지) |
| companion/Pairwise·`companion_alias` | 대상 해소(원칙 7)·동조 overlay |
| Event Graph | 관계 이벤트·근거 경로 연결(어휘는 P0 감사 결과 준수) |
| context_reducer | 기간 중복 제거·overview 상한 + episode-aware 압축 신규 |
| 텔레메트리(`marriage_telemetry` 채널) | §P6 익명 계측 재사용 |

---

## 부록 A. P0-A 감사 결과·결정 로그 (2026-07-24)

### A-1. 게이트 판정

| 게이트 항목 | 상태 |
|---|---|
| ① REL-EVENT-VOCAB-AUDIT | **완료** — 8계층 실측(A-2) |
| ② 런타임 MT 프로파일 | **완료** — `production_candidate` 활성(MT1/2/3 ON·MT4 shadow·MT6 ON) 실측 |
| ③ relation delta 기여 실측 | **완료**(A-3) + 교차검증 2건 완료(A-6) — **P0-A 폐쇄 (2026-07-24)** |
| ④ 어휘 결정 | **승인** — canonical=taxonomy_v2 21키, 구키 전부 legacy alias(A-4) |
| ⑤ 소유권 결정 | **승인** — legacy relation delta=기존 랭킹의 유일한 소유자, 신규 벡터=shadow 분류·설명 전용(§4-1). 전환 결정은 P4 후 |

### A-2. 8계층 어휘 실측 요약

- canonical 어휘는 **taxonomy_v2 21키**로 이미 수렴 중. 정상 계층: EventKeyV2·LLM 후보·
  Event Graph(`LEGACY_EVENT_KEY_MAP` 리맵)·structure_patterns hints·리포트 필터
  (`EVENT_DOMAIN` taxonomy_v2). daily catalog는 독립 어휘 C(정책상 분리 유지).
- 🔴 **결함 1 (B1 대상)**: `precompute._EVENT_DOMAIN`이 로컬 구키 매핑이라 relations.json이
  내는 21키(`new_relationship`·`relationship_change`·`contract_document`·`health_attention`·
  `legal_conflict`)의 도메인이 전부 `general`로 오분류 저장. 운영 DB 94 composite 실측:
  new_relationship 96건·relationship_change 175건 전부 `domain=general`.
- 🔴 **결함 2 (B1 대상)**: topic_builder 필터가 구키 — M01 `{relationship_start,
  relationship_end}`·M02 `{marriage, childbirth, family_change}`는 **라이브 0매치(연애·결혼
  topic findings 상시 빈 결과)**. 건강(health_attention→general)·시험(education 키 부재)도
  사망, 사업(M14)은 business_start만 부분 동작.
- 근본 원인: relations.json 21키 마이그레이션을 graph_builder만 흡수, precompute·
  topic_builder 미갱신.

### A-3. relation delta 실측 핵심 (측정 하네스: 스크래치패드 p0a/, no-op 대조군 +
`contributions["relation"]` 교차확인 + 유닛 격리 병행, 무발동 대조군 byte 일치 확인)

1. **방향 누수(🔴 B2 대상)**: delta는 중립 활성인데 방향 구분 없이 사전 등재 2키에 균등
   가산 — 충·형 연도에 `marriage_signal`이 `relationship_change`와 같은 폭(+22)으로 상승해
   Top5 진입(기신 해 포함). `has_stability_risk`가 `REL_CHUNG_*` 등을 인식 못해 출력 가드
   미작동.
2. **new_relationship 사각지대**: `relation_palace_modifier.json`에 미등재 — 배우자궁이
   어떤 식으로 발동해도 새 인연 후보 0 가산(MT1 천간합 seed가 유일 경로).
   → legacy 사전에 즉시 추가하지 **않는다**(합의 다의성: 새 접촉/심화/재접촉/기혼 변화/
   모호한 묶임). P1 activation 벡터 반영 → P3 상태·exposure 분기 → P5 이후 적용 검증.
3. **cap 22 포화**: 충 단독=충×2+형+COMPOUND=파×2+COMPOUND=전부 +22 — 복합 정보가
   점수에서 소실(reason에만 잔존). legacy cap은 유지(랭킹 광역 변경 방지), 신규 벡터가
   원시 구조 보존(§4-1 Evidence).
4. **confidence 승격이 랭킹 지배**: +11점으로 10위→3위. → shadow 불변식 확대(§4-1).
5. kind별 순수 delta(50 기준): 충 +22/19 > 형 +19/16 > 육합 +16/16 > 파 +14/12 > 해 +9/8.
6. 쟁합·관살혼잡 전용 처리 없음 — legacy delta에 추가하지 않고 P1~P3에서 구조 패턴
   modifier + 궁 활성화 벡터 + 상태 + exposure 합성으로 처리(역할 혼합 방지).
7. **delta는 후보를 만들지 못함**(십성 신호 없으면 관계 후보 0) — 기존 원칙과 정합.
   신규 증거 계약에서는 `partner-star-driven` / `palace-activation-driven` 두 생성 경로를
   구분하되, P1 shadow에서는 후보 생성 없이 관측만.

### A-4. Canonical 21키 매핑표 (게이트 ④ 확정)

| canonical (21키) | domain | legacy aliases |
|---|---|---|
| career_change | career | career_change, resignation |
| job_gain | career | — |
| promotion | career | promotion |
| business_start | career | business_start |
| business_expansion | career | — |
| wealth_change | wealth | wealth_change, income_change, expense_risk, speculation_risk, asset_volatility |
| windfall | wealth | windfall |
| contract_document | career | contract, document |
| education_admission | education | education_start, exam |
| education_completion | education | education_complete |
| relationship_change | relationship | relationship_end, family_change |
| new_relationship | relationship | relationship_start |
| marriage_signal | relationship | marriage |
| childbirth | relationship | childbirth |
| relocation | relocation | relocation, travel |
| legal_conflict | career | lawsuit |
| health_attention | health | health_issue, surgery |
| social_conflict | career | — |
| preparation_delay | career | — |
| creative_output | career | — |
| public_exposure | career | — |

**주의 — `marriage_signal`의 장래**: 현재 의미가 배우자궁 활성화·성립 가능성·결혼 신호·
충형 변동을 모두 섞고 있으므로, 신규 관계 taxonomy(§8)에서는 canonical로 유지하지 않고
`relationship_activation / relationship_commitment / relationship_formalization`으로 분리한
뒤 legacy alias로 강등하는 것을 전제로 설계한다(P0-B vocab 설계 시 반영).

vocab lint 필수 규칙(P0-B `relationship_event_vocab.json`): alias 순환 금지 / alias 1개가
복수 canonical 지시 금지 / canonical의 재-alias화 금지 / TopicBuilder·Event Graph·structure
pattern 참조 키는 vocab에 존재 / daily 전용 키와 개인화 키 namespace 혼용 금지 / 폐기
키에는 replacement 또는 tombstone 지정. vocab 항목 필수 필드: canonical_key /
legacy_aliases / owner / event_family / stage_effect / condition_effect /
personalized_only / daily_allowed.

### A-5. 감사 재현성·fixture 승격

- 재현성 메타데이터(교차검증 보고서에 기록): repository_commit / dictionary·structure_
  pattern 버전 / ACTIVE_MARRIAGE_PROFILE / runtime·python / timezone / 스크립트 목록 /
  측정 출력 해시.
- fixture 승격: 핵심 측정기를 `scripts/audits/relationship_p0a/`로, 핵심 발견 고정은
  `tests/regression/test_relation_delta_legacy_behavior.py`로 승격(전 스크립트 이관은
  불필요, 발견 고정 fixture만 필수).

---

### A-6. 교차검증 2건 (P0-A 폐쇄 조건 — 2026-07-24 완료)

**남성 실전 명식** (甲戌 일주 양간 + 己亥 일주 음간): 기존 결론과 **일치**.
- 재성 기반(SINGLE_ZHENGCAI) 관계 후보 생성 확인, 배우자궁 합 +16/충 +22(상한) 동일,
  기신 해에도 상승 동일. 충 연도 marriage_signal 방향 누수 재현.
- MT1 남성 재성 干合 경로 발화 확인(양간 甲일간 — 간합 파트너=정재일 때만. 음간 己는
  간합 파트너 甲=정관이라 원리상 미발화 — 결론 불변·보조 발견).
- MT1(new_relationship seed)과 REL(marriage/rel_change)은 키가 갈려 물리적 분리,
  MT2/MT3 중첩 형태는 남녀 동일.
- 뉘앙스(불일치 아님): MT2 회귀 글자가 충에 관여한 사례에서는 SPOUSE_PALACE_CLASHED가
  붙어 기존 가드 트리거 존재 — MT2 미관여 충은 여전히 리스크 코드 없음(B2 대상 재확인).

**월운 경로** (C1 2026년, `score(levels={MONTH})` — chat_service 동일 경로): 기존 결론과
**일치**. 단일 합 delta는 층위 가중으로 16→14 소폭 감소하나 충·다중 발동은 상한 22에
동일 포화. 충 월(2026-07 丑未충×2+형)에서 marriage_signal 49→76(+22) 방향 누수 재현.
confidence 승격이 랭킹 상승 주 동인인 구조 동일(월별 후보 밀도 17~18개에서도).

재현성 메타데이터: repository_commit `7e041dd` / relation_palace_modifier.json(reviewed:
false, cap은 엔진 상수 `_MAX_RELATION_DELTA=22.0`) / structure_patterns v1.1.0 /
ACTIVE_MARRIAGE_PROFILE=production_candidate / Python 3.12.2 / Asia/Seoul /
reference_date=2026-07-24 / 측정 스크립트 8종(스크래치패드 p0a/, 리포 무수정).

## 부록 B. 버그픽스 트랙 B1·B2 계획 (관계 시스템과 독립, 별도 PR)

### 적용 순서 (2026-07-24 확정)

```text
1. P0-A 결과·게이트 결정 SSOT 반영 (본 부록)
2. 문서 단독 커밋
3. B2 방향 누수 가드 핫픽스 → 회귀·기존 출력 안전 감사
4. B1-a 코드·alias·lint → B1-b composite dry-run·재계산·검증
5. P0-A 핵심 fixture 재실행
6. P0-B 착수
```

B2가 B1보다 먼저인 이유: B1이 죽은 관계 신호를 부활시키면 B2 미적용 상태에서 충 기반
marriage_signal 노출이 오히려 증가한다. P0-B 병행 금지 이유: P0-B 타입·vocab은 canonical
어휘 전제 — B1 진행 중 병행하면 alias/canonical 중복 정의·baseline 오염.

### B2 — 방향 누수 출력 가드 (긴급)

문자열 포함 검사 확장이 아니라 **명시적 reason 분류 함수**로 구현:

```python
_NEGATIVE_RELATION_REASON_PREFIXES = ("REL_CHUNG_", "REL_HYEONG_", "REL_PA_", "REL_HAE_")

def is_relationship_stability_risk(reason_code: str) -> bool:
    return reason_code.startswith(_NEGATIVE_RELATION_REASON_PREFIXES)
```

`REL_COMPOUND` 처리: 단독 무조건 위험 분류 금지(합 중심 compound 오분류 방지) —
구성 reason에 충·형·파·해가 있으면 위험, 판별 불가면 보수적 미판정+감사 로그.

필수 테스트: CHUNG/HYEONG/PA/HAE→True, HAP 단독→False, HAP+CHUNG→True,
MT2 SPOUSE_PALACE_CLASHED→기존대로 True, 충 기반 marriage_signal 확정·긍정 단정 차단,
**점수·순위·confidence 완전 불변(출력 가드만 변경)**.

### B1 — topic 어휘 사망 (2단계 분리)

**M02 이벤트 구성 결정 (2026-07-24 데굴님 확정)**:

> M02의 canonical 이벤트 키는 `marriage_signal`과 `childbirth`로 제한한다.
> `relationship_change`는 M01이 소유하며 M02와 중복 소비하지 않는다. 기존 composite의
> `family_change`는 원본 키와 taxonomy version을 보존한 read-adapter를 통해 M02에서만
> 호환 소비한다. 향후 commitment·formalization·household 증거가 도입되면
> `relationship_change`의 일부를 키 중복이 아닌 증거 계약으로 M02에 선택적으로 연결한다.

근거: `relationship_change`는 의미 범위가 넓어(연애 갈등·썸 변화 포함) M02가 소비하면
결혼·가정 섹션 오염 + F-17/Y-08(M01·M02 동시 조립)에서 동일 신호 중복 전달. 저장 키
alias(`family_change→relationship_change`)는 정규화 정책일 뿐 **소비 모듈 의미 동일을
뜻하지 않는다**. 장기: taxonomy v2.1에서 `family_household_change` 독립 키 검토(지금은
21키 재변경 없이 provenance 보존으로 처리).

**dual-read 설계 원칙**: 정규화 시 원본 키를 버리지 않는다 —
`source_event_key`·`source_taxonomy_version` 보존. 순서: DB 읽기 → source key 보존 →
canonical 해소 → domain 보정 → TopicBuilder 필터. `general` 도메인 보정은 canonical key가
EVENT_DOMAIN에 명확할 때만(미지 키는 원 도메인 유지+계측). dual-read 계측
(legacy_event_key_read_count / legacy_general_domain_repaired_count / unknown_legacy_key_count /
m01_legacy_signal_count / m02_legacy_family_change_count / canonical_signal_count)으로
B1-b 재계산 후 어댑터 제거 시점을 판단한다.

**MT1 구조적 비대칭 (P0-A 보조 발견 — P2 배우자성 해소기 필수 반영)**: MT1은 "일간 干合
상대 글자가 배우자성에 해당하는 일부 명식(남성은 양간 한정)에서만 작동하는 특수 awareness
seed"다. 일반적 배우자성 출현 엔진으로 설명 금지, **MT1 미발화를 '그 시기 인연 없음'의
음성 근거로 사용 금지**. 남성 음간·여성 대응 극성 fixture 고정 필요.

- **B1-a 코드·호환 계층**: `precompute._EVENT_DOMAIN` → taxonomy_v2 `EVENT_DOMAIN` 교체,
  TopicBuilder 필터 canonical화(M01·M02·건강·시험·사업), legacy key read alias(dual-read),
  vocab lint.
- **B1-b 데이터 재계산**: 영향 composite 탐색 → dry-run → before/after diff 기록 →
  versioned rebuild(`composite_schema_version=taxonomy_v2` 스탬프, 제자리 덮어쓰기 대신
  버전 기록) → 검증 후 전환, rollback 가능 유지.
- 재계산 전 확인: 94건의 환경 출처 / 진행 중 report job 참조 여부 / 캐시 키 taxonomy
  version 포함 여부 / idempotent 여부 / 과거 데이터 읽기 호환.
- 필수 회귀(전 영향 도메인 — 연애·결혼·건강·시험·사업): 필터 전후 후보 수 / 월별 time
  series 복구 / 상위 finding 복구 / 무관 도메인 출력 불변 / legacy composite 읽기 성공 /
  신규 composite canonical 저장.

### B1-b 실행 기록 (2026-07-24 완료 — A안)

- 대상: DB `luck_composites` 33행(subject 1건 = **2026-06-11 스케줄러 통합 테스트 잔재**,
  subject_id_hash `9d0d667c33cf91e5`). **라이브 chat/report는 DB store가 아니라 요청 시
  `CompositeBuilder` 즉석 실행**(store 소비처는 scheduler·subject_store뿐) — 쓰기 경로
  수정이 이미 라이브 즉시 반영되는 구조 확인.
- 실행: 스냅샷 기록(행수·dict 1.0.0·event_key/domain별 신호 수·dry-run 요약) →
  `invalidate_subject` 33행 삭제 → 실사용 경로(즉석 빌드, 새 쓰기 코드)로 재생성 검증:
  **591 신호 전부 canonical·SSOT 도메인 정합, normalizer 계측 legacy=0/repaired=0/unknown=0**.
- smoke: 실차트 M01 연애 findings 5건·M11 건강 4건 **부활 확인**(종전 상시 0매치).
- **M02 composite 신호 0건은 회귀 아님**: relations.json eventDomains에 결혼 계열
  (marriage_signal·childbirth) 자체가 미등재(구키 시절에도 0매치) — 사전 공백. 결혼
  풀이는 MT 레이어·이벤트 엔진 경로가 담당 중이며, M02 확장은 P3 증거 계약
  (relationship_change의 formalization/household 증거 선택 연결)에서 다룬다. 사전 등재는
  원칙 5 파이프라인+감수 사안.
- 확인 2건: 계약·문서 소비 모듈은 **M08 business**(M14=past_validation — 종전 보고
  표기 실수, 코드·테스트는 정확). `contract_document→career`·`legal_conflict→career`는
  taxonomy_v2 `EVENT_DOMAIN`(event_taxonomy_v2.py L102·104)의 명시 의도값 — SSOT 대조 완료.

### fixture 승격 (2026-07-24 완료)

- `scripts/audits/relationship_p0a/` — no-op 대조군·명식 fixture·연/월운·contribution·
  랭킹 리포트 측정기 6종 + README(재현 방법·핵심 결론).
- `tests/regression/test_relation_delta_legacy_behavior.py` — **characterization**(충의
  중립 활성 이중 가산·cap 22 포화·충>합 서열·new_relationship 사각지대·무발동 무변경 —
  legacy 점수 동작 보존, §4-1 소유권 전환 결정으로만 갱신)과 **safety**(충·형·파·해
  reason→stability_risk 판정·합 단독 비위험·가드의 점수 불간섭 — 결함의 사용자 노출
  금지)를 분리 고정. 9건.
- 재실행 검증: 버그픽스(B2·B1-a) 후에도 P0-A 측정값 동일 재현(예: 관살혼잡 2036
  marriage_signal 83→94·relContrib 22.0 — A-3 표와 일치).

### P0-B 진입 게이트 (확장판 — 2026-07-24 전 항목 충족)

```text
[x] P0-A canonical 21키 전체 매핑표가 SSOT 부록에 있음 (A-4)
[x] 남성 실전 명식 1건에서 relation delta 의미가 동일함 (A-6)
[x] 월운 실전 1건에서 점수·confidence 누수가 동일함 (A-6)
[x] B2가 충·형·파·해 기반 결혼 긍정 단정을 차단함 (f4ce222 + safety 회귀)
[x] B2 적용 전후 점수·랭킹은 byte-identical (가드 전용 변경 + 회귀 고정)
[x] B1 canonical/alias lint 통과 (normalizer·매트릭스 테스트)
[x] 기존 composite와 taxonomy_v2 composite 모두 읽을 수 있음 (read-adapter)
[x] 재계산 대상 before/after diff가 기록됨 (dry-run: domain 수리 147건·legacy 0 —
    실측 시점 33행, 94→33은 캐시 프루닝에 의한 자연 변동)
[x] 무관 도메인 회귀가 없음 (topic·report scoping·chat pipeline 통과)
[x] P0-A 핵심 측정 fixture가 재현 가능하게 저장됨 (audits + 회귀 9건)
[x] B1-b 무효화·표준 경로 재생성·계측 0 검증 완료
[x] M08 소유권·contract_document/legal_conflict 도메인 SSOT 대조 완료
```

---

## 부록 C. P0-B 구현 명세 (2026-07-24 승인)

구현 순서(각 단계 = 독립 커밋, OFF 상태 출력 불변 통과 후 다음 단계):

```text
P0-B1  relationship_event_vocab.json + loader + lint
P0-B2  RelationshipStage + RelationshipCondition + adapter
P0-B3  관계 상태 해소기 + 현재형 facts
P0-B4  대상 해소 기반 REL shadow 배선 + 텔레메트리
```

### C-1. M02 0건의 정확한 기록

M02 소비 경로는 정상화됐지만, 현재 upstream 사전(relations.json)에 `marriage_signal`
또는 이에 대응하는 결혼 사건 생성 근거가 부족해 실차트 smoke에서 finding이 0건이다.
**필터 회귀가 아니라 미구현된 증거 계약 범위**다. P3 전까지 M02 복구를 위해
`relationship_change`를 다시 넣는 것 금지.

### C-2. 3층 타입 원칙 (P0-B2)

- `RelationshipStage` 7단계·`RelationshipCondition` 8종은 §3 확정안 그대로.
- 어댑터는 **손실 변환임을 이름에 드러낸다**: `relationship_stage_from_marriage_stage(...)`.
  `family_expansion → MARRIED + family_expansion facet/event`(단계 동일시 금지). 역방향
  round-trip 미보장을 문서·테스트로 고정.
- `SEPARATED`는 stage를 자동 `NONE`으로 바꾸는 값이 아니다 — 별거 부부 =
  `stage=MARRIED + condition=SEPARATED`. 단계·상태는 독립 표현.
- **E4 단계에서 관계 단계 자동 추론 매핑 금지** — episode 합성 시 사건 키+증거 계약 동반.

### C-3. 관계 상태 해소기 원칙 (P0-B3)

- **전역 singleton 금지**: 전역 저장 가능 값은 혼인 상태·현재 연애 여부 개괄뿐. 상대별
  관계 상태/연락 상태/시작·종료/질문 대상 여부는 **target-aware**(`ResolvedRelationshipState`
  — target_id/target_role/stage/condition/contact_state/temporal_status/source/
  source_turn/confidence).
- 시간성 4종: CURRENT(갱신 가능) / PAST(현재 갱신 금지) / PLANNED(계획 상태만) /
  HYPOTHETICAL(갱신 금지). "어제 헤어졌어"=CURRENT 종료 갱신.
- 출처 우선순위: 현재 질문 명시 > 최근 대화 현재형 confirmed > 저장된 대상별 현재 상태 >
  2단계 프로필 > unknown. **명식 추론으로 관계 상태 추정 금지.**
- 정정·부정 fixture 필수: "있는 게 아니라 전 남자친구야" / "기혼이라 했는데 이혼했어" /
  "연애 중은 아니고 연락만" — corrected·superseded 의미 보존(첫 관계어만 저장 금지).
- 친구·제3자의 연애 사실을 사용자 상태로 저장 금지.

### C-4. REL shadow 배선 조건 (P0-B4)

- **shadow 불변식**: 이벤트 후보 생성·점수·confidence·랭킹·LLM 입력·리포트/채팅 출력
  전부 불변. 내부 side channel·텔레메트리만 변경. 기존 위험 엔진 expose 설정과 무관하게
  P0-B에서 관계 컨텍스트의 LLM payload 유입 0 확인.
- **fail-closed**: 동명 별칭 2인·"그 사람" 불명·제3자 오인 가능·과거/현재 상대 미구분·
  일반 질문+다중 등록 상대 → 컨텍스트 미생성, `target_ambiguous=true, context_created=false`
  계측만.
- **일반 연애운 질문**("올해 연애운 어때?")에서 임의 spouse/current_partner 컨텍스트 생성
  금지 — 관계 상태 개괄값만(generic relationship context).
- **익명 target_id**: 실명·별명 원문 저장 금지 / 동일 대화·프로필 내 안정 동일 / 계정 간
  연결 불가 / 로그 역추적 불가 / inline·등록 상대 동일 미확정 시 병합 금지.
- 계측 10종(+디버그 2종): relationship_context_attempted/created/source,
  target_resolved/ambiguous, temporal_status, profile_fact_conflict, exposure_status,
  risk_candidate_count, risk_blocked_or_suppressed_count
  (+context_deduplicated_count, context_drop_reason). 전부 PII 없이 enum·count.

### C-5. relationship_event_vocab.json 규칙 (P0-B1)

항목 필수 필드: canonical_key / legacy_aliases / family / owner / personalized_allowed /
daily_allowed / deprecated. lint: canonical 중복 금지 / alias 중복·순환·canonical 충돌
금지 / owner 없는 키 금지 / 개인화 전용 키 daily 사용 금지 / TopicBuilder·structure
pattern domain_hints·Event Graph event node 참조 키 미등록 금지 / 폐기 키 replacement
또는 tombstone 필수 / family_change provenance 호환 규칙 회귀 고정 / vocab family와
taxonomy `EVENT_DOMAIN` 일치 lint(장기적으로 vocab이 관계 키 메타데이터 SSOT).

### C-6. P0-B 완료 게이트

```text
[ ] 21개 canonical key와 모든 legacy alias가 lint 통과
[ ] TopicBuilder·Event Graph·structure pattern 참조 정합
[ ] 신규 RelationshipStage가 기존 MarriageStage를 수정하지 않음
[ ] adapter의 손실 변환이 문서·테스트로 고정
[ ] stage와 condition을 독립적으로 표현 가능
[ ] 현재형·과거형·계획형·가정형 해소 테스트 통과
[ ] 정정·부정 발화가 이전 사실을 올바르게 supersede
[ ] 프로필과 최신 사용자 사실 충돌 시 최신 현재형 사실 우선
[ ] 친구·제3자의 연애 사실을 사용자 상태로 저장하지 않음
[ ] 다중 상대 target_id 오귀속 0건
[ ] 애매한 대상은 fail-closed
[ ] 일반 연애운 질문에서 특정 상대 위험을 생성하지 않음
[ ] REL shadow context가 live input에서 생성됨
[ ] REL shadow의 LLM 노출 0건
[ ] 점수·confidence·랭킹 변화 0건
[ ] 채팅·리포트 출력 byte-identical
[ ] 텔레메트리 10종 PII 없음
[ ] ruff·mypy·관련 회귀 clean
```

### C-7. P0-B3 폐쇄 보완 (2026-07-24 리뷰 반영)

- **LLM 노출 실측 결과**: 신규 관계 user_facts 슬롯이 기존 `user_facts_block()`(무필터
  직렬화)을 통해 LLM에 노출되는 경로가 **실재했음** — "출력 불변·소비 코드 0" 초기 주장
  은 부정확했다. 보완: `_STATE_ONLY_FACT_KEYS`(relationship_status·marital_correction)를
  블록 직렬화에서 제외(상태 해소 전용). 무구조 문장 노출은 대상·시간성·정정 상태를
  잃으므로, LLM 전달은 통합 관계 컨텍스트+안전 가드 준비 후(P0-B4/P5) 별도 경로로만.
- **다중 상대 evidence 보존**: `relationship_status`를 singleton→누적으로 전환 — 전역
  singleton이면 현재 연인+전 연인+별거 배우자의 원문이 마지막 발화에 supersede돼 유실.
  정정 판정은 resolver 소관, ledger는 양쪽 원문 보존(회귀 고정).
  `marital_correction`은 전역 singleton 유지(혼인 상태 정정은 단일 사실).
- **다중 절·다중 대상 fail-closed**: 한 발화에 배우자·현재 연인·전 연인 중 2범주 이상
  상태 서술 공존 시 자동 저장 금지 + `ambiguous_multiple_targets` 사유 계측(정정 발화는
  같은 대상 재서술이라 제외).
- **planned 조건 축소**: 막연 계획("언젠가/나중에 결혼할 예정")은 planned 보존만 하고
  신규 상태(COMMITMENT 함의) 생성 금지. 질문형 미래("결혼할 수 있을까?")는 HYPOTHETICAL.
- **overview 세분화**: 단일 has_partner 압축 금지 — has_legal_spouse /
  has_active_romantic_partner / has_separated_spouse / has_current_contact_target /
  active_target_count 분리 파생(B4 위험 role 오귀속 방지).
- **P0-B4 실행 순서 확정**: 발화 parse → companion/alias 대상 resolve →
  temporal/제3자 판정 → decide → ConversationState apply → **갱신된(이번 turn 적용 후)
  상태로** RiskRelationshipContext 생성 → set_risk_shadow_contexts. write 금지 발화
  (가정·과거·제3자)는 기존 상태 유지. 단일 has_partner로 current_partner 컨텍스트 생성
  금지 — 세분 overview로 role 구분.

### C-8. P0-B4 구현 기록 (2026-07-24 완료)

- **배선**: `apps/api/saju_api/services/relationship_shadow.py` — 확정 순서(parse→대상
  resolve→temporal/제3자 판정→decide→apply→**이번 turn 반영 후 상태로** 컨텍스트 생성→
  `set_risk_shadow_contexts`). chat 주 채점 직전 주입, `take_risk_shadow` 직후 해제
  (싱글턴 잔류·타 요청 오염 방지).
- **하드 게이트(불변식 1)**: `REL_LIVE_CONTEXT_EXPOSE_ENABLED=False`(P5 승인 전 True
  전환 금지) + `strip_live_relationship_candidates` — live 컨텍스트 전용 target
  네임스페이스(relstate-/profile-role:/attached:)로 후보를 결정적 식별해 **위험 모드
  무관하게** 노출 경로(build_risk_payload 입력)에서 제거. QA·비관계 후보는 보존.
- **idempotency(불변식 2)**: `store.last_applied_signature`(turn+발화 해시) — 동일 turn
  재처리 시 state write 0·retry_skipped 계측(컨텍스트는 결정론 재생성).
- **역할 규칙(C-7 표)**: MARRIED→spouse(별거=relationship_status="separated"·contact
  추론 금지·대상 제거 금지) / DATING·COMMITMENT·FORMALIZATION→current_partner /
  CONTACT→dating_partner / **전 연인 role 사전 부재→컨텍스트 미생성+unsupported_role
  기록(current_partner 대체 금지)** / generic·제3자·다중 대상→생성 금지(다중 대상
  fail-closed는 신규 write 금지일 뿐 기존 상태 초기화 아님 — 테스트 고정).
- **소스 3종 분리(자동 병합 금지)**: 발화(relstate- opaque)/프로필 익명 slot
  (profile-role: — 발화 상태 존재 시 중복 생성 억제)/첨부 칩(attached: —
  is_question_target=True). 첨부 role 연결은 관계 유형 확정 경로가 있는 spouse/romance
  한정, 그 외는 P5.
- **exposure 규칙**: 발화·프로필 확인 관계만 CONFIRMED. financial_tie·
  shared_responsibility 항상 None(자동 추론 금지 — UNKNOWN≠CONFIRMED 유지).
- **오류 격리**: 전 단계 예외 → 빈 컨텍스트+resolver_error 계측, 본 응답 비차단.
- **계측 10+2종**: enum·count·bool·opaque id만(원문·별명·자유 문자열 금지 — 테스트로
  고정). drop_reason enum 고정(target_ambiguous/multiple_targets/third_party/past_only/
  hypothetical/planned_only/unsupported_role/missing_target/state_conflict/
  resolver_error/no_signal/generic_question).
- **byte-identical 범위(§9 정의 채택)**: EventCandidate·score·confidence·ranking·비shadow
  LLM 입력·리포트 입력 불변(관계 컨텍스트는 risk shadow 사이드채널만 관여, 노출 경로는
  하드 게이트로 차단). 변경 허용: ConversationState.relationship_states·state-only
  facts·shadow 사이드채널·익명 텔레메트리.
- 검증: 신규 15건 + 관련 105건(chat pipeline·golden questions) + 위험·가드 146건 통과,
  ruff·mypy clean. user_facts_block의 리포트 경로 공유 여부: report_service는
  user_facts_block 미사용(채팅 전용 — state-only 필터로 충분) 확인.

### C-9. P0-B 완료 게이트 판정 (2026-07-24)

C-6 게이트 18항 전항 충족 — P0-B1(41be4a9)·P0-B2(8bf931e)·P0-B3(f1ffd32+6c9f0de)·
P0-B4(본 커밋). **P0 전체 폐쇄. 다음 단계 = P1(7축 효과 벡터 shadow — §4-1 확대
불변식 적용).** 잔여 메모: 관계 evidence 누적의 user_facts cap 침식 retention 테스트
(P0-B4 차단점 아님 — P1에서 고정), 첨부 상대 relation_type 자동 해소·소스 간 dedup은 P5.

---

## 부록 D. P1 구현 명세 (2026-07-24 승인)

핵심 원칙: **P1은 7축을 모두 숫자로 채우는 작업이 아니다 — 근거가 있는 축만 평가하고,
근거가 없는 축은 0점이 아니라 `insufficient_evidence`로 보존한다**("약하다"≠"판정 불가").

### D-1. 축별 평가 가능성

- 직접 산출 가능: activation / stability / separation_pressure / 일부 experience_valence
- 제한적: realization / formalization
- 현실 컨텍스트 없이는 확정 금지: exposure (P0-B 관계 상태는 대상 존재·접촉 상태이지
  새 만남의 현실 환경 전체가 아니다)

```python
class EffectAxisValue:
    band: EffectBand | None
    evidence: list[...]
    status: AxisStatus  # evaluated | insufficient_evidence | not_applicable | blocked
```

### D-2. RelationshipActivationEvidence 원칙

필드: relation_kind / source_layer / affected_palace / on_spouse_palace /
independent_cause_id / compound_group_id / raw_strength / legacy_delta / legacy_capped /
reason_codes. **reason_codes 개수 ≠ 독립 원인 수** — `independent_cause_id`를 결정적으로
부여하고 독립 원인 수는 이를 기준으로 계산(REL_CHUNG_day+REL_CHUNG_year+REL_COMPOUND가
2개 원인인지 1구조의 다중 표현인지 구분).

### D-3. P1 확대 불변식 (§4-1 + 2026-07-24 추가)

```text
후보 생성·삭제·흡수 없음
score/raw/confidence/personal_match/life_fit 불변
ranking·Top-N 불변
timeline delta = 0 / marriage_stage delta = 0
stability_risk delta = 0 (B2 가드는 기존 REL reason만 계속 사용 —
  P1 벡터는 별도 승인 전 출력 가드 관여 금지)
risk candidate delta = 0
LLM payload·report section input delta = 0
변경 허용 = shadow side channel + 익명 telemetry
```

### D-4. 구현 순서·완료 게이트

P1-0 retention(086acd0)·선행 보강(23e89ec — provenance 이중화·동시 재처리) **완료**.
P1-1 타입(EffectVector·AxisStatus·Evidence) → P1-2 RelationPalace adapter(activation/
stability/separation) → P1-3 MT2 보조 evidence(기존 MT2 점수와 별개·중복 집계 금지) →
P1-4 구조 패턴 modifier(쟁합·합거·합반=ambiguity·stability 분리, 관살혼잡 과대 계산
금지) → P1-5 벡터 합성기(§4 SSOT 준수) → P1-6 shadow 채널·telemetry → P1-7 legacy 비교
감사.

**P1-2 보완 결정(2026-07-24 리뷰 6항)**: ①강도 필드 의미 분리 —
`base_relation_strength`(이벤트 무관 기본 강도, cap·likely·MT4 미적용)와
`event_adjusted_legacy_strength/legacy_delta/legacy_capped`(특정 이벤트 결합 후에만
정의 — 어댑터 단계 None) ②`independent_cause_id` 입력 순서 불변(전 필드 서명 정렬+
개수 기반 #k) ③stability=signed 축(음=불안정 압력·양=안정 순효과, separation과 분리 —
형·해는 안정↓이되 즉시 종료 압력 아님) 명문화 ④**합 단독 separation은 '낮음' 평가가
아니라 INSUFFICIENT_EVIDENCE**(§5 표의 '낮음'은 직접 근거 아님 — 부정 신호 없음≠분리
위험 낮음) ⑤`shared_trigger_id` 신설(같은 운 글자 파생 신호의 root 1개 계산 — 어댑터는
잠정 서명, P1-3에서 운 글자 주입 정밀화) ⑥compound_group_id를 구성 evidence 각각에
연결+`derived_from_evidence_ids`(구조 패턴 파생 역추적). MT2는 realization을 EVALUATED로
올리지 않고 보조 evidence만(§8). P1-6 전 폐쇄: provenance 전 변환 경로 단조성(공통
merge 함수+직렬화 직전 최종 방어선)·telemetry processing key·5-tuple→named 타입.

완료 게이트(2026-07-24 승인안 §14): 7축 AxisStatus 전수 / 근거 없음≠약함 / cap 이전
원시 구조 보존 / reason 수≠원인 수 / 충·형·파·해의 activation·separation 차등 / 합
단독으로 formalization 상승 금지 / MT2-RelationPalace 중복 집계 금지 / 도화는 P1 벡터
입력 금지 / D-3 불변식 전항 / live provenance 흡수 후 차단 유지 / PII 없는 텔레메트리 /
ruff·mypy·회귀 clean.

### D-5. P1-6 완료 기록 (2026-07-24)

**P1-6 전 항목 완료** — 3개 커밋으로 마감:

1. **Draft/Envelope 2단 telemetry (553e262)** — `RelationshipEffectShadowDraft`
   (Top-N 이전·audit 미결)와 `finalize_shadow_envelope`(reducer 이후 결합)를 타입
   수준으로 분리(미완성 draft는 telemetry DTO 변환 불가). NO_CANDIDATE는 정상
   관측으로 audit_degraded 분모(eligible)에서 제외, `detailed_` 접두사로 상세
   선택분만 결합. `select_detailed_drafts`(HMAC 정렬 상위 cap)·§4 불변식
   (record success+failure=detail_selected, truncated=vector_success-detail_selected).
   aggregate는 draft(전 성공 기간)에서 직접 누적.

2. **chat 배선 실행 계약 §12 (d31aaae)** — Top-N 이전 Draft 생성 → 전체 aggregate
   즉시 누적 → 상세 cap개만 bounded 보존 → production reducer(payload) 이후 상세
   Draft에만 audit/rank 결합 → Envelope finalize → allowlist batch 1회 emit →
   sidecar 폐기. `EventEngineV2.take_relationship_shadow()`가 채점 중 수집한 불변
   projection(탐지 재호출·cands 변형 0 — 주 채점 bit 동일 회귀)을 반환하고,
   `relationship_vector_sidecar`가 어댑터·합성기에 걸어 Draft를 만든다. legacy
   audit join은 서명 기반 1건만(`candidate_join_signature` — event_key 단독 금지),
   복수 매치 JOIN_AMBIGUOUS·최종만 존재 JOIN_NOT_FOUND·후보 없음 NO_CANDIDATE
   fail-closed. pre_reduce_rank=reducer 입력 순서, final_rank=Top-N 순서. 전 구간
   try/except 격리(관측 전용 — 후보·점수·payload delta 0). 실 chat 스모크 22기간
   emit 확인.

3. **live provenance 무결성 (65bb050)** — `rebuild_risk_candidate`(주 방어선):
   RiskCandidate 재구성 SSOT, live provenance=OR(base·sources·update) 단조 보존
   (True→False 강등 불가). 억제 경로 2개 rebuild site·score_shadow를 helper 경유로
   전환. 정적 감사 스크립트(`audit_risk_candidate_rebuilds` — AST로 model_copy/
   model_construct/replace/copy 수집, 미승인 raw 재구성 실패)로 신규 우회 site 유입
   차단. 2차 fail-safe(namespace 필터)와 독립 — 회귀가 각 층 단독 차단 + 둘 다
   유실 시 누출(load-bearing)을 검증.

**게이트 판정**: 7축 AxisStatus 전수(P1-5 합성기)·근거 없음≠약함(INSUFFICIENT_
EVIDENCE)·cap 이전 원시 구조 보존(base_relation_strength)·MT2-RelationPalace 중복
집계 금지(root 1회+superseded)·D-3 불변식(delta 0 — 주 채점 bit 동일 회귀)·live
provenance 흡수 후 차단 유지(e2e)·PII 없는 텔레메트리(allowlist DTO + 금지 문자열
회귀)·ruff·mypy·회귀 clean **전항 충족**.

### D-6. P1-7 완료 기록 (2026-07-24) — legacy 비교 감사

**P1-7 종료** — 감사 전용·읽기 전용(score/rank/candidate/payload delta 0). SSOT 요약,
전체 관찰 지도는 `RELATIONSHIP_P1_7_HANDOFF.md`.

- **P1-7a(a1ea8ec)** — 비교 DTO·고정 enum·분류기: `LegacyVectorComparisonClass` 9종
  (§6 보수화 `REVIEW_REQUIRED_DIRECTION_MISMATCH` — P1 formalization 미평가라 leakage
  확정은 P3 이후)·`CandidateAbsentSubclass`(부재는 오류 아님·P3 신호)·비교 3층 분리
  (family 합산 금지·축 미평가 0 비교 금지·기간)·별도 `cmp.v1` allowlist·delta≠
  activation 동일 척도 금지.
- **P1-7b(a716fc1)** — 결정적 harness: `synthesize_period_vector` 공유(production·
  harness drift 방지)·fixture 6종(성별×음양 decoupled)·legacy precap 재현·§4 매트릭스
  A/B/C·REPORT.md 331 record. 읽기 전용 회귀(감사 전후 채점 byte 동일).
- **P1-7d-lite(a9a3fb0)** — 중첩 독립 finding(§2·§3: primary_class가 가리는 복합
  현상 보존 — cap_saturated finding 53 vs primary 28) + production coarse aggregate
  (`cmp.prod.v1`: relation_delta 없이 coverage·분포만 — delta·cap class 0·audit 결손
  not_observable 분리·전체 vs family 부재 분리·§7 금지 준수)·chat 배선·§5 중립 서술.

**게이트 전항 충족**(감사 16항 + coarse 15항 — HANDOFF §F). P2(캘리브레이션 — HANDOFF
§C)·P3(증거 계약 — §D)는 각각 별도 승인 착수. legacy cap은 별도 기술 부채(§E,
추적 ID `LEGACY-REL-CAP-01`).

### D-7. P1 전체 종료 (2026-07-24) — CLOSED

```
P1-1 types                    : 완료
P1-2 RelationPalace adapter   : 완료
P1-3 MT2 adapter              : 완료
P1-4 structure modifier       : 완료
P1-5 vector synthesizer       : 완료
P1-6 shadow channel·telemetry : 완료
P1-7 legacy comparison audit  : 완료

P1 status               : CLOSED
usage                   : shadow_only
production behavior delta: 0 (score·rank·candidate·Top-N·LLM/report/risk payload 불변)
```

**P1에서 아직 완료되지 않은 것(명시 분리)**: 벡터 계수의 현실 타당성·strong/moderate
band 적정성(→P2) / 후보 생성 증거 계약·formalization·realization 축(→P3) / legacy cap
migration(→`LEGACY-REL-CAP-01`) / production empirical validation(표본 축적 전 —
coarse aggregate 배선만 검증, 22기간은 분포 근거 아님).

**다음 트랙 = P2 벡터 캘리브레이션 우선**(P3 증거 계약이 P2 계수·band에 의존 —
strong threshold가 바뀌면 P3 후보 승격 조건도 바뀌므로 계수 안정화 선행). P2 목표는
**legacy delta 재현이 아니라** 관계 구조가 7축에 일관·비과대 반영되는지 검증과 상대
강도·band 결정. 순서: P2-0 조정 가능 값·불변식 고정 → P2-1 민감도 → P2-2 의미 단조성
회귀 → P2-3 경계 사례 감수 → P2-4 calibration version 고정 → P3.
