# 연애·결혼 시기 판정 고도화 (Marriage/Love Timing Enhancement) — v2

> 전문가 영상 자료(연애·결혼 시기 판정법, 2026-06-30 분석) + 사용자 1차 리뷰(2026-06-30) 기반.
> 본 문서가 연애·결혼 **시기 트리거**의 단일 진실 공급원(SSOT)이며, `docs/02`(E2·E4)·
> `docs/05`(events/relationship)·`docs/09`(3장 combos·M01·M02)의 관계 항목을 보강한다.
> 본 문서는 **초안(reviewed:false)**이며 검수 게이트(validate→compile→regression) 전 운영 반영
> 금지(절대원칙 5). 점수·배수는 단일 영상 가설의 **잠정값**이며 캘리브레이션 전 미보장.

## 0. 핵심 원칙

> **결혼 시기는 activation 하나가 아니라 `발동도(activation) × 단계(stage) × 안정성(stability) ×
> 현재 관계상태(context)`로 본다. 천간(干)에서 오는 자극은 '생각·끌림'(awareness), 지지(支)에서
> 오는 합은 '행동'(action)이며, 배우자궁 발동은 결혼뿐 아니라 이별·갈등·재편·삼각관계도 의미할
> 수 있다.** 모든 트리거는 **기존 후보를 강화·시기 배치·단계 부여**할 뿐 새 결혼을 단정하지
> 않는다(원칙 3·8). 신살·암합과 동일하게 단독으로 길흉을 확정하는 서술을 금지한다(docs/05 §6).

설계의 4대 수정 축(사용자 리뷰):

1. **stage 확장** — awareness/action 2단계로는 결혼(공식화·정착)을 설명 못 한다 → 6단계.
2. **"거의 100%" 제거** — 확정 표현 금지. 합성 신호는 `strong_confluence`로 단계 승급만.
3. **MT2 회귀 차등** — 배우자성 회귀만 action 후보, 비배우자성·오행 회귀는 약한 보조.
4. **MT6 = static prior** — 혼기 범위 보정용. 특정 연·월을 발동시키지 않는다.

산출은 **단일 점수가 아니라 2축**이다(§12):
`activation_score`(관계 사건 발생 가능성) × `stability_score`(안정적 결혼으로 이어질 가능성).

---

## 1. 결혼 도메인 stage 모델 (먼저 고정)

기존 E4 stage(`awareness|exploration|action|decision|completion`, docs/02)는 유지하고,
관계 도메인은 그 위에 **marriage_stage**(6단계)를 refinement로 얹는다. 각 단계는 base E4에 매핑되어
기존 Timeline/Manifestation 파이프라인과 호환된다.

| marriage_stage | 의미 | base E4 매핑 | 대표 신호 |
|---|---|---|---|
| `awareness` | 마음 동함·끌림·관계 생각 | awareness | MT1 일간 干合 단독 |
| `contact` | 소개·연락·만남·썸 | exploration | MT1+약한 지지 자극 |
| `relationship` | 교제 시작·관계 진전 | action | MT3 일지 지지합, MT2 배우자성 회귀 |
| `commitment` | 결혼 논의·상견례·약속·혼인 결정 | decision | relationship + **commitment marker**(아래) |
| `formalization` | 결혼식·혼인신고·동거·가정 형성 | completion | commitment + **공식화 marker**(아래) |
| `family_expansion` | 임신·출산·자녀 이슈 | completion | MT5 + childbirth 신호 |

> **base stage 확장은 하지 않는다 — marriage_stage만 확장한다.** `family_expansion`도 base를
> 새로 늘리지 않고 `completion`에 매핑되는 refinement다(`completion+` 같은 신규 base 없음).

**단계 승급은 신호 누적이 아니라 marker 게이트로만 가능하다**(과승급 방지):

`commitment_marker` 후보(다음 중 1+):
- 배우자성 직접 투출 + 배우자궁 합/회귀(MT2 배우자성 회귀)
- 대운 또는 세운 관계창 활성 + 월운에서 배우자성/배우자궁 트리거(layer confluence §4)
- 관성/인성/문서성 신호가 관계 도메인과 결합
- 장기 관계 상태(context=dating/engaged)에서 MT1+MT2+MT3 strong_confluence 발생

`formalization_marker` 후보(다음 중 1+):
- 인성/문서/계약 신호가 관계 도메인과 결합
- 관성/제도/사회적 승인 신호(12운성 관대·건록)가 관계 도메인과 결합
- 주거/가정/이사 신호와 결혼 도메인 동시 발동
- 택일/일운에서 안정 신호 보강

> **MT1~MT4 자체는 marker가 아니다.** 특히 일간합·배우자궁 회귀·방합·육합만으로는
> `commitment_marker`/`formalization_marker`가 될 수 없다(합이 겹쳐도 marker 없으면
> `relationship` 이상 불가, §5 cap 연동). awareness/action만으로 "결혼운"을 직접 내보내지
> 않는 것이 본 개정의 1순위 목표.

---

## 2. partner_star 추상화 (먼저 고정)

전통 기준 `여=관성 / 남=재성`은 유지하되, **내부 규칙으로 두고 관계 도메인 신호는
`partner_star`로 추상화**한다(향후 관계 모델 확장 대비, 설정화).

```text
partnerStarRule    : "traditional"
malePartnerStar    : "wealth"           # 남=재성(정재·편재 전체)
femalePartnerStar  : "officer_killing"  # 여=관살(정관·편관 전체)
childStarRule      : { female: "output", male: "officer_killing" }
```

> **여 배우자성은 정관만(officer)이 아니라 관살 전체(officer_killing)로 본다** — 편관 누락 방지.
> 안정성(stability) 평가에서 정관/편관을 분기한다: 정관 중심=안정·공식성 / 편관 중심=강한 끌림·
> 속도·불안정 가능 / 관살혼잡=`mixed_partner_star` risk_flag(§12). 남 배우자성 `wealth`도 정재·편재
> 전체를 의미한다.

- 엔진 내부는 기존대로 `wealth/officer(officer_killing)` 십성군으로 계산하되,
  relationship/marriage 도메인의 signal·reason_code·LLM 입력에서는 `partner_star`(배우자성)/
  `child_star`(자녀성)로 표기한다.
- `marriage_resource.gender` 미상이면 partner_star 게이트는 **양 기준 병기 + confidence 하향**
  (원칙 11 — 부재로 차단 금지).

---

## 3. relationship_context_gate (현재 관계상태)

같은 신호도 사용자의 현재 상태에 따라 해석이 갈린다. 1차 소스는 2단계 프로필
`maritalStatus`(docs/11), 2차는 대화 추출(F9, 사용자 확인 후). docs/02 Reality Context와 동일 경로.

```json
{ "relationshipContext": "unknown | single | dating | engaged | married | divorced",
  "interpretationShift": true }
```

| context | 같은 결혼 신호의 해석 |
|---|---|
| single | 만남·소개·연애 시작 가능성 |
| dating | 교제 확정·관계 진전 |
| engaged | 결혼 논의·상견례·동거 |
| married | 부부 관계 이슈·집안일·출산·재정착 |
| divorced | 재혼 가능성·과거 관계 정리 |
| **unknown** | **결론 하향** — "관계가 있으면 결혼 논의로, 없으면 만남·연애 시작 신호로" 분기를 LLM에 위임 |

> **context는 `activation_score`/`stability_score`를 변경하지 않는다.** `final_label`·`stageLabel`·
> LLM wording·`confidence_band`에만 영향을 준다(점수는 엔진 신호 그대로, 해석 라벨만 보수화).

```json
{ "scoreEffect": "none",
  "labelEffect": "downgrade_if_unknown",
  "llmEffect": "branch_by_relationship_status",
  "confidenceEffect": "lower_confidence_when_unknown" }
```

---

## 4. layer confluence (계층 합류)

결혼은 월운 하나로 판단 금지. 기존 6계층 스택 위에 **관계창 합류 조건**을 둔다.

```text
대운: 관계·결혼이 열리는 큰 환경      세운: 실제 후보 연도
월운: 사건이 움직이는 달               일운: 택일·실행일(execution only)
```

```json
{ "layerConfluence": {
    "requiredForCommitment": ["daewoon_or_sewoon_relationship_window", "monthly_trigger"],
    "dailyUse": "execution_date_only" } }
```

- 월운 MT1이 떠도 대운·세운에 관계창이 없으면 **"가벼운 관심"으로 하향**(awareness 유지, 승급 불가).
- `commitment` 이상은 대운/세운 관계창 + 월운 트리거 동반을 필수로 한다.

---

## 5. 결혼 도메인 점수 cap (포화 방지)

여러 합이 겹치면 점수가 쉽게 포화된다(SCORE_SATURATION_REVIEW와 동일 리스크). 단계별 상한:

```text
awareness            cap 0.60
contact              cap 0.70
relationship/action  cap 0.80
commitment           commitment_marker 없으면 0.75 제한
formalization        formalization_marker 없으면 0.80 제한
```

> MT1+MT3+MT4가 전부 겹쳐도 commitment_marker 없으면 "결혼 확정"까지 못 올라간다.

---

## 6. MT1 — 일간 干合 배우자성 (awareness 신호)

**근거(영상 9:53~11:07)**: 운 천간이 일간과 干合 + 그 천간이 배우자성이면 "마음·생각이 동하나
액션은 빠진" 상태. **기본 stage=awareness이며 단독으로 action까지 승급 금지.**

현 구현 갭: 일간 自合은 event_engine_v2가 합화 길흉 배경값으로만 쓰고 사건 라벨링에서 제외
(`_target_hwa_element`/`_daewoon_hwa_role`). relationship.json `six_combination`은 전부 지지 육합 —
천간 awareness 소스 부재.

### 6.1 신규 어휘·게이트
- `relation: day_master_stem_combine` — 운 천간이 원국 **일간**과 직접 干合(甲己·乙庚·丙辛·丁壬·戊癸).
  化 성립 불요(결합 자체가 awareness). **신규 어휘 — 엔진 미탐지 시 inert(단독 선적용 안전).**
- 배우자성 게이트: 운 천간 십성군이 `partner_star`일 때만 관계 후보로 승격. signal은 성별별
  십성(정관/편관…) 직접 나열 대신 **`tenGodGroup: "partner_star"`** 추상화를 쓴다(§2 일관성 —
  여명 편관 누락·남명 중복 엔트리·gender unknown 충돌 방지). 매칭 시 `resolve_partner_star(gender)`로
  실제 십성군 환원.

### 6.2 4-케이스 분류 + 점수(잠정)

```text
1. 일간합 단독                         base 0.25~0.30, stage awareness
2. + 합하는 글자가 배우자성            +0.10~0.15 (상한 0.40)
3. + 합화 성립 & 화신이 용·희신/관계유리  +0.05~0.10 (상한 0.45)
4. 합거/합반/쟁합·투합 또는 기신        action 승급 금지 + risk_flag 추가
   (끌리나 묶임·애매·삼각·결정 지연)
```

- 초안의 0.4는 **"배우자성까지 맞는 경우의 상한"**으로 재정의(일간합만으로 0.4는 과함).
- relationship.json 엔트리(여명 예):

```json
{ "signal": { "relation": "day_master_stem_combine", "tenGodGroup": "partner_star" },
  "eventCandidates": [
    { "event": "new_relationship", "score": 0.30, "polarity": "conditional",
      "stageHint": "awareness", "partnerStarBonus": 0.10 } ],
  "note": "MT1 일간 干合 + partner_star — 인연 '생각' awareness. 단독 action 금지. 합거·쟁합·기신=risk.",
  "reviewed": false }
```

- `tenGodGroup: "partner_star"` 단일 엔트리로 양 성별 커버(성별별 십성 직접 나열·대칭 엔트리 불요).
  `stageHint`·`partnerStarBonus`·`tenGodGroup`은 신설 필드(docs/05 §events). `stageHint`는
  `MarriageStage` enum 값만 허용(§15 게이트).

---

## 7. MT2 — 일지 투출 글자 운 회귀

**근거(영상 0:17~1:30, 7:30~8:40)**: 일지 지장간 중 투출(透出)한 글자가 운으로 돌아올 때 배우자궁
발동. **무차별 발동 방지를 위해 회귀를 분리하고 게이트한다.**

### 7.1 원국 필드 (MarriageEmergenceNatal)
```
day_branch_emerged_stems: list[{
  stem, element, ten_god, source_pillars, is_day_master_exposure, is_partner_star }]
  # 일지 지장간 ∩ 원국 천간4(글자 일치). 정적·비단정. is_day_master_exposure=일간 자기 투출(weak).
```

### 7.2 회귀 2종 + 배수(잠정·구현 확정)
> **정정(2026-06-30)**: 일간 기준 천간↔십성은 1:1(전단사)이라 '글자 다름 + 십성 동일'(same_ten_god)
> 티어는 **실현 불가능**하다(같은 십성 ⟺ 같은 글자). 따라서 의미 있는 회귀는 2종뿐이다.

```text
A. same_stem_return     일지 투출 글자가 운 천간으로 정확 회귀(동일 글자)   strength ×1.0 (강)
B. same_element_return  같은 오행·음양 짝(글자 다름) 회귀                     strength ×0.40 (약·배경)
```
strength는 후보 점수에 곱하지 않고 **절대 delta 상한**으로 환산한다(과증폭 방지):
partner_star → same_stem +10 / same_element +4. 비배우자성·일간 투출 → same_stem +5 / same_element +1.

### 7.3 게이트 (결정 2 확정)
> **비배우자성 투출 글자도 약하게 인정하되, 단독으로 결혼 action까지 승격하지 않는다.
> 배우자성일 때만 강화한다.**

```text
배우자성 회귀(is_partner_star)  → relationship 후보 강화(증폭만, 승급 아님)
비배우자성·일간 투출 회귀         → 약한 배경 보조만
same_element 회귀                → 배경 가중(최소). 증폭형이라 단독 이벤트 생성은 원천 불가
```

- **MT2 emergence_return은 BOKEUM과 같은 "원국 글자의 운 회귀" 구조를 갖지만(개념적 탐지 모델),
  라이브 스코어링에서는 `relation_palace_modifier`가 아니라 전용 `MarriageEmergenceModifier`(증폭형)
  가 처리한다**(사용자 확정 2026-06-30). same_stem/same_ten_god/same_element 3종 강도 차등,
  partner_star 게이트, spouse_palace_clashed 분기가 relation_palace의 flat bonus 구조와 맞지 않기
  때문이다. `RelationKind.EMERGENCE_RETURN`은 도입하지 않는다. **단독 사건 생성 금지(증폭만)** —
  기존 new_relationship/marriage_signal/relationship_change 후보에만 근거·delta를 얹는다.
- **same_stem ×1.0 / same_ten_god ×0.65 / same_element ×0.30**은 내부 strength 계수이며, 후보 점수
  전체에 곱하지 않고 **절대 delta 상한**으로 환산한다(과증폭 방지). same_element는 배경 근거(증폭
  최소·stage 승급 금지). 배우자성 회귀만 relationship 후보 강화, 비배우자성은 awareness 보조까지만.
  **일간 투출(is_day_master_exposure)**은 partner_star가 아닌 weak로 분류(자기 의식 발동, action 금지).
- **spouse_palace_clashed 분기**: 회귀 글자가 일지 충에 관여하면 배우자궁이 움직인 *근거*는 남기되
  결혼 성사로 긍정 증폭하지 않는다 — marriage_signal 긍정 증폭 금지, new_relationship/relationship_change는
  `MT2_EMERGENCE_CLASHED`·`spouse_palace_clashed` 태그(stability 하향).
- 적용 layer: 대운(10년 배경)·세운(연도 강화)·월운(월 사건성)·일운(택일 참고). 일운 단독 사건 생성
  금지(증폭형이라 자동 충족). `day_branch_emerged_stems`는 저장하되 일간 투출은 weak flag로 구분.

---

## 8. MT3 — 방합 action 후보 (어휘 보강)

**근거(영상 11:24~13:48)**: 지지합은 행동 트리거이며 육합·삼합·**방합** 포함. 단 방합은 사회적
무리·가족·환경 합류로도 나타나므로 **spousePalace 게이트 유지 + 추가 조건**.

```json
{ "signal": { "relation": "directional", "spousePalace": true },
  "eventCandidates": [
    { "event": "new_relationship", "score": 0.45, "polarity": "conditional",
      "stageHint": "relationship" } ],
  "note": "방합이 일지(배우자궁) 포함 — 관계 행동 후보(육합보다 약·세력형). commitment/formalization 승급 불가·단독 결혼 금지.",
  "reviewed": false }
```

> **vocabulary 정정(2026-06-30 구현 확인)**: 방합 relation 값은 `directional`이다(relations.json
> `type` = InteractionKind.BRANCH_DIRECTIONAL). `branch_directional`이 아니다.
>
> **⚠️ 적용 순서 제약**: `directional`은 **이미 탐지·매칭되는 어휘**다. `spousePalace` 게이트가
> 엔진에 없는 상태에서 본 엔트리를 추가하면 **모든 방합에 오발동**한다. 따라서 MT3 엔트리는
> 단독으로 사전에 넣지 않고 **spousePalace 게이트 엔진 구현과 한 단위로** 적용한다(MT1·MT5는
> 신규 어휘라 매칭기가 무시 → inert, 단독 선적용 안전).

방합을 관계 신호로 인정하는 추가 조건:
```text
1. 일지가 방합 구성에 직접 포함되는가? (spousePalace)
2. 방합 결과 오행이 배우자성/결혼 관련 십성과 연결되는가?
3. 완성형인가 반합/부분합인가? (왕지 포함 플래그, docs/09 3장)
4. 대운·세운 레벨에서 이미 관계창이 열려 있는가? (layer confluence §4)
```
- 단독 stageHint는 `relationship`으로 **고정**한다. "action candidate"는 note에만 둔다(base action과
  혼동 방지). 실제 결혼은 MT1·MT2·배우자성 투출·관인/문서/가족 신호 동반 필요.

---

## 9. MT4 — 합 종류 차등(육합 > 삼합 > 방합) + subtype 보존

**근거(영상 11:49~11:57)**: 육합="부부의 합" 1순위. **관계 도메인 한정** subtype 배수 +
방합 예외 보정.

```json
"hap_subtype_multipliers": {
  "affection": {
    "six_combination": 1.0,
    "three_harmony": 0.85,
    "directional": 0.70,
    "directional_spouse_palace": 0.75,
    "directional_partner_element": 0.80
  } }
```

- **`hap_subtype_multipliers`는 relationship/marriage 도메인에서만 적용한다.** career·relocation·
  wealth 등 타 도메인 HAP 가중에는 영향을 주지 않는다.
- relationship.json base score는 그대로, **일지궁 발동 보너스에만** subtype 배수 적용.
- 방합 단독은 action 승급 금지(§8). 위 예외는 일지 포함·배우자성 결과 오행일 때만.
- reason_code는 subtype 원형을 풀어 남긴다(검색·디버깅 용이): `MT4_HAP_SIX` / `MT4_HAP_THREE` /
  `MT4_HAP_DIRECTIONAL_DAY` (`DIR` 축약 금지).

### 9.1 HAP 붕괴 금지 (중요)
RelationPalaceEngine이 육합/삼합/방합을 `HAP` 하나로 뭉개는 현 구조를 수정. `RelationActivation`에
subtype 보존:
```json
{ "relationType": "hap",
  "hapSubtype": "six_harmony | three_harmony | directional",
  "involvesSpousePalace": true,
  "domain": "relationship" }
```
> reason_code에 원 subtype을 반드시 남겨, LLM이 "합이 있어서 좋다"로 뭉뚱그리지 않게 한다.

### 9.2 구현 상태 (2026-06-30) — shadow 검증 완료·apply 운영 보류
구현 완료: `marriage_hap_subtype.py`(순수 함수) + RelationActivation hap_subtype/element +
relation_palace.apply 3-state(off/shadow/apply) + `enable_mt4_subtype` flag. **모든 multiplier ≤1.0,
관계 도메인 한정, unknown/stem fallback 1.0, off==shadow byte 동일** 검증. shadow 영향(4차트×25년):
육합·천간합 0(불변), 삼합 −12.2, 방합 −65.3. **apply는 순위 변화·방합 큰 감쇠 때문에 golden
사례 비교 전까지 운영 기본값 OFF로 보류**(사용자 결정). apply 통과 기준은 WORKLOG 참조.

---

## 10. MT5 — 지장간 partner+child 동시 운반 (일반화)

**근거(영상 15:12~16:48)**: 한 지지의 지장간이 배우자성+자녀성을 동시 운반 → 가정 형성 욕구.
**`officer+output` 고정 금지** — 성별·관계 모델별로 partner_star/child_star가 다르므로 일반화한다.

```json
{ "signal": { "branchHiddenTenGods": ["partner_star", "child_star"] },
  "eventCandidates": [
    { "event": "family_formation_signal", "score": 0.40, "polarity": "conditional",
      "stageHint": "awareness", "topicHint": "family_formation" } ],
  "note": "MT5 유입 지지가 배우자성+자녀성 동시 운반 — 가정 주제 활성. family_expansion 직승 금지.",
  "reviewed": false }
```

> **stageHint는 `awareness`로 둔다(family_formation은 stage가 아니라 event/topic).** `MarriageStage`
> enum에 `family_formation_*` 같은 임의 stage를 만들지 않는다(§1 base 미확장 원칙·§15 게이트).
> 가정 형성 맥락은 `topicHint`/event(`family_formation_signal`)/reason_code로 표현한다.

- partner_star/child_star는 §2 추상화 사용(여: 관성+식상 / 남: 재성+관살).
- **MT5 단독은 `family_expansion`으로 직접 승급 금지** — 가정 형성 *욕구*이지 출산운이 아니다:
```text
단독 MT5 (stage=awareness, topic=family_formation)     reason_code MT5_FAMILY_FORMATION_AWARENESS
MT5 + relationship/commitment 상태                      family_expansion_candidate
MT5 + formalization_marker + child_star 강화            childbirth/child_issue 후보 (M05 연결)
```

---

## 11. MT6 — 배우자성 위치별 혼기 (static prior, event 아님)

**근거(영상 2:02~2:44)**: 배우자성이 어느 기둥에 투출했나로 이른/제때/늦은 인연 경향.
**event trigger가 아니라 broad timing 보정용 static prior.**

```json
{ "marriageAgePrior": {
    "source": "partner_star_position",
    "role": "static_prior",
    "affects": ["broad_timing_window", "stage_threshold"],
    "doesNotTriggerEvent": true } }
```

| 배우자성 위치 | 혼기 경향(prior) |
|---|---|
| 년주 | 이른 인연 |
| 월주 | 사회생활 초·중반(적령) |
| 일지(배우자궁) | 배우자궁 직접 — 본인 주도 |
| 시주 | 늦은 인연(만혼 경향) |

- "언제 결혼할까?" 같은 **광역 질문**의 기본 창을 잡는 데만 쓴다. 실제 시점은 대운·세운·월운
  발동이 결정(prior는 약한 가중·단정 금지).

---

## 12. risk_flags / negative relation matrix + 2축 산출

배우자궁 발동은 결혼뿐 아니라 이별·갈등·재편·삼각도 의미한다. **결혼 로직은 risk_flag와 함께
봐야** 오판(강한 발동=결혼)을 막는다.

### 12.1 risk_flags
```text
spouse_palace_clash         일지 충        spouse_palace_punishment  일지 형
spouse_palace_harm          일지 해        spouse_palace_break       일지 파
spouse_star_void            배우자성 공망   spouse_star_clashed       배우자성 충극
competition_signal          비겁쟁재·쟁합·삼각관계
shangguan_officer_conflict  상관견관(여명 관성 손상)
mixed_partner_star          관살혼잡 / 재성혼잡
```
(대부분 marriage_resource·relations 엔진이 이미 계산 — flag로 노출·집계만 신설.)

### 12.2 2축 출력 + 재분기
```text
activation_score : 관계 사건이 일어날 가능성 (MT1~MT5 합성)
stability_score  : 안정적 결혼으로 이어질 가능성 (risk_flags·배우자궁 안정·배우자성=용신 역산)
```

> **risk_flags는 단순 감점이 아니라, activation이 높은 사건을 marriage가 아닌
> `relationship_change`/`conflict`/`separation_candidate`로 재분기(re-route)한다.** stability가
> 낮으면 같은 발동이라도 사건 종류 자체가 바뀐다.

| activation | stability | 재분기 결과 |
|---|---|---|
| 높음 | 높음 | `relationship_progress` / `marriage_discussion` |
| 높음 | 낮음 | `relationship_change` / `conflict` / `separation` / `unstable_attraction` |
| 낮음 | 높음 | 관계 안정, 사건성 낮음 |

> "사건은 큰데 좋은 결혼은 아닌 시기"를 분리하는 것이 핵심. 충+기신 배우자궁 발동은
> marriage가 아니라 relationship_change로 라우팅(현 relationship.json 방향 유지).

---

## 13. 타입·어휘 변경 요약

| 항목 | 위치 | 변경 |
|---|---|---|
| `marriage_stage` | shared_types(신설) | 6단계 enum + base E4 매핑 |
| `partner_star`/`child_star` | marriage domain 추상화 | 내부 wealth/officer → 도메인 표기 |
| `relationshipContext` 게이트 | Reality Context | maritalStatus 연동, 해석 분기(점수 무개입) |
| `layerConfluence` | event_engine | commitment 승급 조건 |
| 도메인 cap | 결혼 점수 | 단계별 상한 + marker 게이트 |
| `RelationKind` | event_engine.py | `DAY_STEM_HAP`·`EMERGENCE_RETURN` 신설 |
| `RelationActivation` | relation_palace_engine.py | `hapSubtype`·`involvesSpousePalace` 보존 |
| `relation` 어휘 | events/*.json | `day_master_stem_combine`(신규·inert) / 방합은 기존 `directional` 사용(신규 아님) |
| signal 키 | docs/05 §events·dictionaries.py | `tenGodGroup`·`spousePalace`·`branchHiddenTenGods`(SignalSpec) / `stageHint`·`partnerStarBonus`·`topicHint`(EventCandidateSpec) |
| `MarriageResourceProfile` | marriage_resource.py | `day_branch_emerged_stems`·risk_flags·marriageAgePrior |
| `family_formation_signal` | event_taxonomy_v2.py | **신규 이벤트키 — 21키 하드셋 확장(8곳 연쇄)**. 적용 범위 별도 결정 필요(§16) |
| relationship.json | dictionaries/events | MT1·MT5는 단독 선적용 안전(inert) / **MT3는 spousePalace 게이트 엔진과 한 단위로** |
| relation_palace_modifier.json | dictionaries/event_engine | `hap_subtype_multipliers`(affection 한정)·compound 패턴 |

> **MT1×MT3 동시 발동**: "거의 100%" 제거. compound 효과는 단계 승급 후보를 만들 뿐이다.
> **`strong_confluence`는 `commitment_marker`/`formalization_marker`를 대체하지 않는다.** 계층:
>
> ```text
> MT1 + MT3                          → awareness → relationship/action candidate 승급 가능
> MT1 + MT3 + commitment_marker      → commitment 후보 가능
> MT1 + MT3 + formalization_marker   → formalization 후보 가능
> ```
>
> reason_code: `strong_confluence`/`high_relationship_activation`/`marriage_discussion_candidate`.

---

## 14. 메인 스펙 반영 순서 (사용자 확정)

```text
1. stage 모델 확장 (§1)          — awareness/contact/relationship/commitment/formalization/family_expansion
2. partner_star 추상화 (§2)      — 남=재·여=관 내부 유지, 도메인은 partner_star
3. MT1~MT5 signal 정의 (§6~10)   — 단독 stage · 승급 조건 · cap · risk_flag
4. hap subtype 보존 (§9)         — HAP 붕괴 금지
5. negative relation matrix (§12) — 일지 충형파해·공망·쟁합·배우자성 손상 + 2축
6. MT6 static prior (§11)        — event 아님, broad window 보정
7. 회귀 테스트 (§15)
```
> 1·2를 먼저 고정한 뒤 3~6을 붙인다(가장 안전 — 사용자 권고).

---

## 15. 회귀·검수 게이트

1. 신규 신호 전부 `reviewed:false` — 컴파일은 되되 가중치는 전문가 감수 전 미보장(원칙 5).
2. **feature OFF 시 기존 결과 불변**(전 항목 modifier 0).
3. 과승급 방지 회귀:
   - 일간 干合 단독이 결혼(commitment+)으로 승급되지 않는지
   - 방합 단독이 결혼으로 승급되지 않는지
   - 배우자궁 충이 marriage가 아니라 relationship_change(관계 변동·갈등)로 분리되는지
   - MT2 오행만 회귀(C)가 단독 이벤트로 뜨지 않는지
4. 2축 회귀: activation 높음 + stability 낮음 케이스가 "결혼 확정"으로 새지 않는지.
5. 단정 금지: 모든 신규 신호 polarity=conditional, "거의 100%"류 표현 부재
   (`test_relationship_decision_directives.py` 확장).
6. **stageHint enum 검증**: `stageHint`는 `MarriageStage` enum 값만 허용. `family_formation_awareness`
   같은 임의 stage 문자열은 검증자가 거부(§1 base 미확장 원칙 보장).
7. 토큰·thinking 한도는 docs/09 8장 그대로(신규 LLM 호출 없음 — 전부 엔진 계산).

## 16. 미결 — 캘리브레이션 전 잠정

- MT1 점수(0.25~0.45 밴드)·MT2 회귀 배수·MT4 subtype 배수는 단일 영상 가설의 잠정값.
- `child_star`(남=관살) 정의는 통설 다수안 채택 — 감수 시 재확인.
- stability_score 산식(risk_flag 가중)은 §12 정성 규칙 → 캘리브레이션 사례로 수치화 예정.
- **`family_formation_signal` 신규 이벤트키 = 21키 하드셋(Phase 7) 확장** — EVENT_KO·EVENT_TYPE·
  affection·DOMAIN·PROHIBITIONS·LEGACY_EVENT_KEY_MAP·검증 카테고리·택일대상 등 다운스트림 8곳
  연쇄. 원칙 10(택소노미 임의 확장 금지)에 따라 적용 범위를 사용자와 별도 확정한다. 후보:
  (a) 22번째 키로 정식 등록(전 매핑 보강) / (b) `MARRIAGE_SIGNAL`에 topicHint=family_formation으로
  흡수(키 미증설) / (c) MT5 엔진 활성 시점까지 보류. **확정 전 MT5 엔트리는 inert(downstream drop)**.
