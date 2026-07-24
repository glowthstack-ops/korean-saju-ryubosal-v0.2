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
순위를 이중으로 끌어올린다. 초기 운영 강제:

```text
usage = shadow_explanation_only
score_delta = 0 / ranking_delta = 0 / confidence_delta = 0
```

이후 기존 relation_delta와 벡터의 관계를 다음 중 하나로 정리(별도 승인):
1. 기존 가산을 activation으로 흡수하고 기존 가산 제거
2. 기존 점수 유지 + 신규 벡터는 사건 종류 분류에만 사용
3. legacy ranking과 차세대 ranking 병렬 검증

처음부터 둘 다 점수에 적용하는 구현은 금지.

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
