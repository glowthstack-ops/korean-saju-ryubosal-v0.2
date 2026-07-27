# P2-PROV 설계안 — 후보 기여 provenance 수집

> 상태: **설계 검토 대기** · 기록일 2026-07-27 · 코드 변경 없음
>
> 선행: `ed8215a`(단계 0 — stack_layers 의미 분리). 이 문서는 그 위에서만 성립한다.

## 0. 고정 문장

> `_Acc.add()`에 전달된 모든 신호는 **검토된 evidence**이며, max 경쟁의 최종 승자만
> **selected base evidence**다. 이후 실제 수치를 변경한 modifier는 별도 provenance로
> 기록한다. 어느 집합을 후보의 상위 사건 지지로 인정할지는 shadow 실측과 감수 전까지
> 확정하지 않는다.

---

## 1. 코드 실사에서 확인한 것 (2026-07-27)

설계 전에 `ten_god_brancher.py`·`event_engine_v2.py`를 직접 읽고 확인한 사실이다.
설계 전제가 아니라 **관측된 현재 동작**이다.

### 1-1. `add()`는 점수만 경쟁하고 근거는 무조건 누적한다

```python
def add(ev, rule_id, gods):
    f = factor(gods)
    eff = round(ev.score * f)
    a = acc.setdefault(ev.event, _Acc())
    if eff > a.score:              # ← 점수는 max 경쟁 (strict >)
        a.score = eff
        a.quality = ev.quality or a.quality
        a.src_strength = f
    a.reasons.append(rule_id)      # ← 패자도 무조건 append
    a.ten_gods |= gods             # ← 패자의 십성도 무조건 합집합
```

**귀결 ①** `reason_codes`와 `source_ten_gods`는 이미 *evaluated* 집합이다. *selected*가
아니다. 최종 점수를 만들지 않은 룰의 흔적이 그대로 남는다.

**귀결 ②** 앞선 십성 역산 프로토타입
(`{s.layer for s in signals if s.ten_god in c.source_ten_gods}`)의 과대 귀속은
가능성이 아니라 **구조적 확정 사실**이다. `source_ten_gods`가 패자 십성을 포함하므로
역산은 반드시 실제보다 넓은 층위를 반환한다. production 근거로 쓰지 않는다.

**귀결 ③** 동점 처리는 `>`이므로 **선착 승자 유지**다. provenance를 붙이면서 `>=`로
바꾸면 점수가 바뀐다. 비교 연산자는 건드리지 않는다.

### 1-1-b. 기존 필드의 의미를 고정한다 (이름은 바꾸지 않는다)

```
reasons           해당 event_key에 대해 평가된 모든 rule_id의 합집합 (evaluated union)
source_ten_gods   승패와 무관하게 평가된 모든 십성의 합집합       (evaluated union)
score             max 경쟁의 최종 승자가 만든 값                  (selected)
```

**불변식**

```
reasons와 source_ten_gods는 candidate provenance가 아니다.
selected base evidence를 이 둘에서 역산해서는 안 된다.
```

필드명 변경은 영향 범위가 크므로 이름은 유지하고 docstring에 `evaluated union`을 명시한다.
회귀 테스트로도 고정한다(§10 "패자 누적 확인").

### 1-2. `_Acc`에는 층위도 occurrence도 없다

```python
@dataclass
class _Acc:
    score: int = 0
    quality: str | None = None
    reasons: list[str] = field(default_factory=list)
    ten_gods: set[TenGod] = field(default_factory=set)
    src_strength: float = 1.0
```

`layers`는 후보 루프 **밖**에서 `{s.layer for s in signals}`로 한 번 계산되어 전 후보에
동일하게 부여된다(단계 0에서 `stack_layers`로 이름을 바로잡은 그 값이다).

### 1-3. `TransitSignal`에 occurrence 식별자가 없다

```python
@dataclass
class TransitSignal:
    ten_god: TenGod
    layer: LuckLayer
    source: str        # 'stem' | 'branch_main' | 'branch_mid' | 'branch_initial'
    strength: float = 1.0
    same_group: bool = False
    same_god: bool = False
```

`collect_from_pillar(pillar, layer, is_target)`는 `LuckPillar`(간지 글자 보유)와 layer를
알고 있으므로 occurrence는 **생성 시점에 만들 수 있다**. 다만 `period` 라벨은 현재
`branch(signals, period)`에만 있고 signal에는 없다 — 시그니처 확장이 필요하다.

### 1-4. 모디파이어 체인 실측 (`_score_target` 순서)

```
brancher.branch()                  GENERATOR — base score 확정
relation modifier                  숫자 변경
twelve_stage_modifier              숫자 변경 + event_phase
layer_flow_modifier                숫자 변경 (source_layers 조합으로 배율)
wealth / capacity                  숫자 변경
MarriageEmergenceModifier (MT2)    숫자 변경 · flag 기본 OFF
apply_mt3_directional_tags (MT3)   태그만 · 점수 불변 · flag 기본 OFF
_apply_daewoon_hwa_background      배경 보정
EventRanker.rank()                 conflict boost(±) + _grade() 억제(−6)
_apply_soft_cap                    표시 점수 압축
daewoon_transition_boost           raw_score(랭킹축) 가산
```

### 1-5. `layer_flow_modifier`는 후보별 근거가 아니다 — 상위 지지에서 제외한다

```python
# layer_flow_modifier.py:87 — 입력은 EventCandidateV2.source_layers(= 평가 스택 구성)
mult = self._layer_mult.get(frozenset(c.source_layers), 1.0)
```

이 modifier는 후보별 실제 기여가 아니라 **평가에 참여한 전체 운 스택의 조합**으로 배율을
정한다. 따라서 다음 추론은 성립하지 않는다.

```
layer_flow 배율에 대운이 포함됨  →  대운이 이 사건 후보를 지지함   ✗
```

기록 시 반드시 후보 특정성을 분리한다.

```
role              AMPLIFIER (또는 ATTENUATOR)
candidate_specific  false
support_eligible    false
```

**가설 A·B·C 어디에서도 `candidate_specific=false`인 context modifier는 상위 지지로
인정하지 않는다.** 인정하면 다시 거의 모든 후보가 `UPPER_SUPPORTED`가 되어, 단계 0에서
바로잡은 것과 같은 오류를 다른 경로로 재도입하게 된다.

(참고: V2 후보 필드명은 `source_layers` 그대로다. 단계 0에서 이름을 바꾼 것은 legacy
DTO 쪽(`stack_layers`)이며 값의 의미는 양쪽 모두 '평가 스택 구성'으로 동일하다.
P2-PROV에서 이 배율이 **바뀌지 않았음**을 회귀로 고정한다.)

---

## 2. provenance 3종 분리

`add()`에 들어온 모든 신호를 후보 기여로 묶지 않는다.

```
1. evaluated evidence        규칙이 검토한 모든 근거
2. selected base evidence    max 경쟁의 최종 승자 — base score를 실제 결정
3. applied modifier evidence base 확정 후 실제 수치·품질·극성을 바꾼 근거
```

### 2-1. evaluated

```python
@dataclass(frozen=True)
class EvaluatedEvidence:
    evidence_id: str
    event_key: str
    rule_id: str
    formula_id: str
    signal_ids: tuple[str, ...]
    source_occurrences: tuple[str, ...]
    source_layers: tuple[str, ...]
    ten_gods: tuple[str, ...]
    relation_ids: tuple[str, ...]
    proposed_score: float
    score_before: float
    selected_at_evaluation: bool
    selection_reason: str
```

`selection_reason` 값:

```
INITIAL_WINNER              score_before가 초기값이고 승리
REPLACED_LOWER_SCORE        기존 승자를 밀어냄
NOT_SELECTED_LOWER_SCORE    eff < score_before
NOT_SELECTED_EQUAL_SCORE    eff == score_before → 현행 `>`가 기존 승자를 유지
```

`NOT_SELECTED_EQUAL_SCORE`를 별도 값으로 두는 이유는, 동점 정책을 나중에 바꿀 때
영향 범위를 실측으로 알 수 있게 하기 위해서다(이번에는 바꾸지 않는다).

### 2-2. selected base

```python
@dataclass(frozen=True)
class SelectedBaseEvidence:
    evidence_id: str
    event_key: str
    final_base_score: float
    source_occurrences: tuple[str, ...]
    source_layers: tuple[str, ...]
    formula_id: str
    rule_id: str
```

중간에 승자였다가 교체된 근거는 `evaluated`에만 남고 `selected_base`에는 없다.

### 2-3. applied modifier

```python
class EvidenceRole(StrEnum):
    GENERATOR = "GENERATOR"
    AMPLIFIER = "AMPLIFIER"
    ATTENUATOR = "ATTENUATOR"
    POLARITY_ADJUSTER = "POLARITY_ADJUSTER"
    QUALITY_ADJUSTER = "QUALITY_ADJUSTER"
    CONTEXT_ONLY = "CONTEXT_ONLY"


@dataclass(frozen=True)
class AppliedModifierEvidence:
    modifier_id: str
    event_key: str
    role: EvidenceRole
    source_occurrences: tuple[str, ...]
    source_layers: tuple[str, ...]
    formula_id: str | None
    value_before: float
    value_after: float
    # `applied` 하나로는 "실행됐다 / 자격이 있었다 / 실제로 값을 바꿨다"가 뭉개진다.
    invoked: bool                  # modifier 로직이 실행됨
    eligible: bool                 # 적용 조건을 만족함
    selected: bool | None          # 경쟁 구조가 있는 modifier만 의미 있음
    changed_numeric_value: bool    # 정수 점수가 실제로 바뀜
    numeric_effect: float          # 양자화 후 실제 변화량
    pre_quantized_effect: float | None  # 반올림 전 효과
    polarity_alignment: str        # ALIGNED / OPPOSED / NEUTRAL / UNKNOWN
    candidate_specific: bool       # 후보별 근거인가 (스택 조합 배율이면 False)
    support_eligible: bool         # 상위 지지 가설에 투입 가능한가
```

대운이 존재하지만 해당 사건 점수를 **낮춘** 경우를 상위 지지로 보면 안 되므로
층위와 방향을 분리해 기록한다.

> ⚠ `_Acc.score`는 `int`이고 `eff = round(ev.score * f)`다. 반올림에 삼켜진 기여를
> `invoked=False`로 접지 않는다. 예:
>
> ```json
> {"invoked": true, "eligible": true, "changed_numeric_value": false,
>  "pre_quantized_effect": 0.4, "numeric_effect": 0}
> ```
>
> 감수에서 "정수 점수를 실제로 바꾼 기여만 인정" vs "양자화 전 방향성 있는 효과도 인정"
> 두 정의를 비교할 수 있게 한다. 이 필드들의 본격 적용은 **P2-PROV-2**다.

---

## 3. occurrence 식별자

층위만으로는 부족하고, 문자열 하나로 급조하면 충돌한다 — 같은 지지가 천간·지지,
target·helper, 원국·운에서 반복될 수 있다.

```
sewoon        ← 부족
2026-07-27:午 ← 충돌 가능
```

구조체로 정의하고 식별자는 여기서 결정적으로 생성한다.

```python
@dataclass(frozen=True)
class SourceOccurrence:
    source_kind: str      # natal / transit
    layer: str            # daewoon / sewoon / wolwoon / ilwoon
    period_key: str       # 2026 / 2026-07 / 2026-07-27
    pillar_position: str  # year / month / day / hour / transit
    component: str        # stem / branch
    glyph: str            # 午
    signal_role: str      # target / helper / context
```

```
transit:ilwoon:2026-07-27:transit:branch:寅:target
natal:-:-:hour:branch:巳:context
```

식별자에 반드시 포함: layer · period · stem/branch · 글자 · target/helper 여부 ·
원국이면 pillar position.

### 3-1. `collect_from_pillar()` 시그니처

positional 순서를 건드리지 않도록 keyword-only로 추가한다.

```python
def collect_from_pillar(
    self,
    pillar: LuckPillar,
    layer: LuckLayer,
    is_target: bool = True,
    *,
    period_key: str | None = None,
) -> list[TransitSignal]:
```

`period_key`는 `branch(signals, period)`가 쓰는 표현과 **같은 SSOT**를 사용한다.
서로 다른 날짜 포맷을 따로 만들면 occurrence 비교가 깨진다.

---

## 4. `candidate_source_layers`는 이번에 채우지 않는다

```python
# 금지 — 감수되지 않은 의미를 확정한다
candidate.candidate_source_layers = selected_base.source_layers
```

shadow 전용 구조로만 수집한다.

```python
@dataclass
class CandidateProvenanceShadow:
    evaluated_layers: list[str]
    selected_base_layers: list[str]
    applied_modifier_layers: list[str]
    aligned_modifier_layers: list[str]
    opposed_modifier_layers: list[str]
```

정식 필드는 계속 비운다.

```
candidate_source_layers = []
layer_evidence_scope    = UNKNOWN
layer_grounding         = None
```

감수 후에만 어떤 shadow 집합을 정식 provenance로 승격할지 결정한다.

---

## 4-1. 최종 승자는 재계산하지 않고 포인터로 추적한다

`evaluated evidence`에서 나중에 최댓값을 다시 찾아 승자를 복원하면 안 된다 — 동점 선착·
라운딩·호출 순서 때문에 현행 승자와 달라질 수 있다. `_Acc`에 shadow 전용 포인터를 둔다.

```python
@dataclass
class _Acc:
    score: int = 0
    ...
    selected_evidence_id: str | None = None   # shadow 전용
```

기존 승자 갱신 분기 **안에서** 함께 기록한다(비교식을 새로 쓰지 않는다).

```
E1 INITIAL_WINNER
E2 NOT_SELECTED_LOWER_SCORE
E3 REPLACED_LOWER_SCORE       → 최종 selected_base는 E3만 가리킨다
```

### 승자가 없는 후보를 허용한다

초깃값이 0이고 모든 `eff`도 0이면 `>`가 한 번도 성립하지 않는다. 그래도 후보는 출력될 수
있으므로 다음 상태를 정상으로 인정한다.

```
selected_evidence_id = None
selection_status     = NO_SELECTED_BASE
```

## 4-2. evidence_id는 occurrence_id와 다르다

하나의 occurrence가 여러 event rule에 평가되므로 둘은 분리한다.

```python
evidence_id = stable_hash(event_key, rule_id, formula_id, sorted(signal_ids))
```

실행 순서 의존을 만들지 않기 위해 **정렬된 signal_ids 기반 해시**를 쓴다. 완전히 동일한
평가가 여러 번 발생할 수 있으면 `evaluation_index`를 **별도 필드로** 기록한다(해시에는
넣지 않는다).

## 4-3. 감사 수집은 recorder가 있을 때만 한다

모든 요청에서 evaluated evidence를 `_Acc`에 보존하면 후보당 메모리·비용이 커진다.
production 계산 객체에 감사 목록을 싣지 않는다.

```python
def branch(
    self,
    signals: list[TransitSignal],
    period: str,
    *,
    provenance_recorder: ProvenanceRecorder | None = None,
) -> list[EventCandidateV2]:
    ...
    if provenance_recorder is not None:
        provenance_recorder.record_evaluated(...)
```

**불변식**

```
recorder=None   기존 실행 경로와 객체 구조·결과가 동일
recorder 활성   감사 데이터만 추가, 계산 결과는 동일
```

이 구조가 API·LLM·리포트 노출 방지도 자연스럽게 해결한다(감사 실행에서만 수집).

---

## 5. 상위 지지 정의 — 하나를 고르지 않고 세 가설을 동시 산출

```
정의 A  strict_generator
  selected base evidence에 대운·세운 occurrence 포함 — 가장 보수적

정의 B  same_formula_effective
  selected base에 상위 층위가 있거나,
  동일 event/formula를 실제로 강화한(ALIGNED) 상위 modifier가 있음

정의 C  any_aligned_effective
  generator·modifier 구분 없이 최종 수치에 양의 방향으로 실제 영향을 준
  대운·세운 evidence가 하나라도 있음
```

후보마다 세 값을 모두 기록한다.

```json
{
  "upper_support_hypotheses": {
    "strict_generator": false,
    "same_formula_effective": true,
    "any_aligned_effective": true
  }
}
```

### 5-1. 상위 evidence가 있다고 모두 '지지'는 아니다

```
대운 evidence가 후보를 약화 · 일운 evidence가 후보를 생성
→ upper layer present = true / upper support = false / upper opposition = true
```

감사 결과에 방향을 분리해 남긴다.

```json
{"upper_evidence": {"supporting": [], "opposing": ["E17"], "neutral": []}}
```

상위 지지 감수는 최소 네 상태를 다룬다.

```
UPPER_SUPPORT      상위 기여가 후보를 강화
UPPER_OPPOSITION   상위 기여가 후보를 약화
UPPER_MIXED        강화·약화가 함께 존재
NO_UPPER_EFFECT    상위 층위가 있으나 실제 효과 없음
```

`UPPER_MIXED`를 바로 major-event 자격으로 볼지, 별도 조건을 둘지는 P2 감수 대상이다.

---

## 6. 집계 단위 — `744 vs 1064` 혼선 재발 방지

```
request_count
period_count
unique_candidate_count
evaluated_evidence_count
selected_base_evidence_count
applied_modifier_evidence_count
```

불변식:

```
selected_base_evidence_count ≤ unique_candidate_count
  ⚠ 우선 부등식까지만 고정한다. NO_SELECTED_BASE 후보가 존재할 수 있으므로,
    '모든 출력 후보가 승자를 갖는다'가 실측될 때만 등식으로 강화한다.

가설별 후보 분류는 상호 배타:
  upper + minor + unknown == unique_candidate_count

evaluated_evidence_count > unique_candidate_count 는 정상
```

감사 리포트는 세 가설 각각에 대해 위 등식을 명시적으로 검사하고, 깨지면 실패로 처리한다.

---

## 7. score-neutral 보증

```
raw score · effective score · quality · polarity · grade · confidence
rank · Top-N membership · reason_codes/evidence_path 기존 값
API · LLM · 리포트 payload
→ 전부 불변
```

구현은 기존 계산문을 바꾸지 않고 그 직전·직후를 관찰한다.

```python
before = a.score
selected = eff > before          # ← 기존 비교식을 그대로 재사용 (재작성 금지)

if selected:                     # 기존 코드 그대로
    a.score = eff
    a.quality = ev.quality or a.quality
    a.src_strength = f
a.reasons.append(rule_id)
a.ten_gods |= gods

audit.record(                    # shadow — 반환값을 계산에 되먹이지 않는다
    score_before=before, proposed_score=eff, selected_at_evaluation=selected,
)
```

provenance 객체가 계산 결과에 다시 입력되어서는 안 된다.

### 회귀 방식

```
동일 차트 세트에 대해 P2-PROV OFF/ON의 후보 전량을
(event_key, period, score, raw_score, confidence_level, quality, polarity, rank)
튜플로 직렬화해 완전 일치를 요구한다.

layer_flow_modifier가 stack_layers를 읽으므로, 단계 0 전후 동작 동일성도 함께 고정한다.
```

---

## 8. 구현 슬라이스

```
P2-PROV-1  base brancher 관측
           TransitSignal에 occurrence_id·period 추가
           _Acc.add()의 evaluated evidence + 최종 selected base
           계산 불변 회귀

P2-PROV-2  modifier 관측
           relation · twelve_stage · layer_flow · wealth · daewoon_hwa · ranker
           역할(EvidenceRole)·정렬 방향(polarity_alignment) 분리
           계산 불변 회귀

P2-PROV-3  감사 집계
           후보 단위 정규화 · 세 가설 산출 · 등식 검사
           도메인·경로·긍부정별 분포

P2-PROV-4  감수 보고
```

각 슬라이스는 독립 커밋이며, 1이 끝나면 그 시점에 A~D 판정이 가능한지 먼저 본다.

---

## 8-1. P2-PROV-1 범위 확정

### 포함

```
TransitSignal의 occurrence 식별 정보(SourceOccurrence + occurrence_id)
collect_from_pillar()의 period_key 전달 (keyword-only)
_Acc.add() 호출별 evaluated evidence 기록
max 비교의 선택 결과 기록 (selection_reason 4값)
최종 selected base evidence 포인터 (_Acc.selected_evidence_id)
동점 선착 유지 (`>` 불변)
reasons/source_ten_gods는 evaluated union이라는 테스트
audit recorder 기본 OFF
점수·등급·순위·Top-N 불변
```

### 제외

```
modifier provenance            → P2-PROV-2
candidate_source_layers 채우기
layer_grounding 재활성화
EventScope 산출 / Episode 예외 / Top-N 게이트 / −6 제거
최소 기여량 임계값
상위 지지 정의 확정
```

## 8-2. 필수 테스트

```
승자 교체        E1 eff=5 선택 → E2 eff=8 교체
                 selected=E2 · evaluated={E1,E2}

패자 누적 확인   E1 정관 eff=8 · E2 편재 eff=4
                 source_ten_gods={정관,편재}  ← evaluated union
                 selected_base.ten_gods={정관}

동점 선착        E1 eff=8 선택 → E2 eff=8 NOT_SELECTED_EQUAL_SCORE
                 selected=E1

양자화 동점      raw 7.4 → 7 · raw 7.2 → 7
                 현행 호출 순서대로 첫 승자 유지

occurrence 구별  세운 午 vs 일운 午 → 서로 다른 occurrence_id
                 같은 층위·같은 글자라도 stem/branch는 component로 구분

승자 없음        모든 eff=0 → selection_status=NO_SELECTED_BASE 정상 처리

audit OFF/ON     동일 fixture로 score·quality·polarity·reason_codes·
                 source_ten_gods·grade·rank·Top-N 완전 일치

layer-flow 회귀  동일 스택 조합 → 동일 multiplier
                 이번 변경이 이 소비 경로를 건드리지 않음을 고정
```

---

## 9. 감수 질문 (P2-PROV-4)

```
base winner만 상위 근거로 볼 것인가
동일 formula의 modifier까지 포함할 것인가
아주 작은 상위 기여(양자화로 numeric_effect=0 포함)도 지지로 인정할 것인가
상위 기여가 반대 polarity면 무엇으로 분류할 것인가
상위과 하위가 서로 반대 방향이면 major-event 자격을 어떻게 볼 것인가
```

---

## 10. 종료 판정 — 구현 결론을 미리 넣지 않는다

```
A. selected base만으로 provenance가 충분
   → strict generator 정의로 감수 진행

B. modifier를 빼면 상위 근거가 과도하게 누락
   → 동일 formula·aligned modifier 포함 검토

C. modifier가 너무 광범위해 거의 모든 후보를 UPPER로 만듦
   → modifier는 사건 자격이 아니라 confidence/quality 근거로만 사용

D. 실제 기여 occurrence를 안정적으로 복원할 수 없음
   → P2 보류, brancher 데이터 모델 재설계
```

---

## 11. 이번 설계에서 명시적으로 하지 않는 것

```
candidate_source_layers 채우기
LayerEvidenceScope 승격
EventScope 산출
Episode 예외 연결
Top-N 게이트
−6 감산 제거
LLM·API·리포트 노출
add()의 비교 연산자 변경(`>` 유지)
```

---

## 12. 관련 코드

- `saju_engines/ten_god_brancher.py` — `_Acc` · `add()` · `collect_from_pillar` · `branch`
- `saju_engines/event_engine_v2.py` — `_score_target` 모디파이어 체인 · `to_legacy_candidate`
- `saju_engines/event_ranker.py` — `_grade`(−6) · `_resolve_conflicts`
- `saju_engines/layer_flow_modifier.py` — `stack_layers` 소비처(동작 불변 확인 대상)
- `saju_engines/signal_occurrence.py` — `occurrence_id()` 규약 재사용
- `saju_engines/layer_evidence_scope.py` — 분류기(입력 준비 전까지 UNKNOWN)


---

## 13. P2-PROV-1 실측 (2026-07-27)

`scripts/audits/provenance_base_survey.py` — 차트 3건 × 세운·월운·일운 전 시점.
selected base evidence(정의 A strict_generator)만으로 분류했다.

```
차트                     후보      근거     승자   UPPER   MINOR  UNKNOWN
A 1980-11-22 남         1863    6866   1863    1807      56        0
B 1992-03-05 여         1976    7139   1976    1905      71        0
C 2001-08-17 남         1900    6213   1900    1823      77        0
합계                     5739   20218   5739    5535     204        0

MINOR_ONLY 3.6% · NO_SELECTED_BASE 0 · UNKNOWN 0
```

### 레벨별 분해 — P2가 관심 갖는 곳에 모집단이 있다

```
day    MINOR 171 / UPPER 1385   → 11.0%
month  MINOR  33 / UPPER  502   →  6.2%
year   MINOR   0 / UPPER 3648   →  0.0%
```

`year`가 0인 것은 구조상 정상이다 — 세운 채점의 target 자체가 상위 층위라
base 승자에 항상 상위 occurrence가 들어간다.

**일운 11%가 핵심이다.** P2의 주 관심사(날짜 선택·일반 길일)가 바로 이 레벨이고,
단계 0 이전 stack 기준 측정에서는 0%였다.

### 종료 판정에 대해 지금 말할 수 있는 것

```
D 배제됨   UNKNOWN 0 · NO_SELECTED_BASE 0
           → occurrence·승자 복원이 안정적으로 된다

C 배제 방향 strict generator만으로 UPPER 96.4%지만 100%가 아니다
           → 모집단이 사라지지 않는다

A 유력     selected base만으로 실사용 가능한 분포가 나온다
```

**B는 아직 판정할 수 없다.** "modifier를 빼면 상위 근거가 과도하게 누락되는가"는
MINOR 204건 중 몇 건이 실제로는 상위 modifier의 aligned 지지를 받는지를 봐야 하고,
그 데이터는 P2-PROV-2에서만 나온다.

### 감사 한계 (다음 감사에서 보완)

```
차트 3건 — 코호트 대표성 없음
일운 표본이 차트 생성 범위에 종속(reference_date 기준 창)
도메인·긍부정별 분해 미실시 → P2-PROV-3
정의 B·C는 미산출 → P2-PROV-2 이후
```


---

## 14. P2-PROV-2 modifier 역할 매핑안 (2026-07-27)

> 상태: **감수 대기** · 코드 변경 없음
>
> 모듈 이름으로 추정하지 않고 6개 modifier를 직접 읽어 5항목(입력 / 변경 대상 /
> occurrence 특정 가능성 / 후보별 여부 / 발생 근거인가)을 확인했다.

### 14-0. 축을 셋이 아니라 넷으로 나눠야 한다

`role` · `candidate_specific` · `support_eligibility`만으로는 실측을 담지 못한다.
**효과는 후보별인데 층위 귀속은 스택 기반**인 modifier가 있기 때문이다.

```python
class OccurrenceAttribution(StrEnum):
    CANDIDATE = "CANDIDATE"                    # 후보에 기여한 occurrence를 특정 가능
    TARGET_LAYER_ONLY = "TARGET_LAYER_ONLY"    # 채점 대상 층위만 — 상위 공급 불가
    STACK_LEVEL = "STACK_LEVEL"                # 스택 전체로 귀속 — 후보 구분 없음
    NOT_RECOVERABLE = "NOT_RECOVERABLE"        # 현 구조로 층위 복원 불가
```

상위 지지 자격은 `candidate_specific`이 아니라 **`occurrence_attribution`이 결정한다.**
`CANDIDATE`가 아니면 어떤 가설에도 넣을 수 없다.

### 14-1. 실사 결과

| Modifier | 입력 | 변경 | occurrence 귀속 | 후보별 | 자격 |
|---|---|---|---|---|---|
| `relation` | `_relation_hits(result, level, target)` · `_activations(hits, target_layer)` | score · palace · quality | **TARGET_LAYER_ONLY** | 예(궁성·발동) | 구조상 상위 공급 불가 |
| `twelve_stage` | `stage_by_layer`(스택 각 층) × `c.source_layers`(=스택) | score · event_phase | **STACK_LEVEL** | 효과만 예 | INELIGIBLE |
| `layer_flow` | `frozenset(c.source_layers)` · `c.source_ten_gods` | score | **STACK_LEVEL** | 아니오 | INELIGIBLE |
| `wealth` | `{pillar.branch for _layer, pillar in stack}` | score | **NOT_RECOVERABLE** | 도메인만 | INELIGIBLE |
| `daewoon_hwa` | `next(p.stem for layer,p in stack if layer is DAEWOON)` | score × factor | **CANDIDATE**(대운 천간 특정) | quality군만 | REVIEW_REQUIRED |
| `ranker` | conflict rules · evidence grading | score · confidence · 순위 | 후처리 | 후보별이나 사후 | INELIGIBLE |

### 14-2. 근거 인용

```python
# relation — 관계는 target 기둥 × 원국이다. layer = target_layer 하나뿐.
hits = self._relation_hits(result, level, target)
layer = target_layer
activations = _activations(hits, layer) + _bokeum_activations(result, target, layer)
→ 일운 후보의 relation occurrence는 항상 ilwoon이다. 대운·세운을 공급할 수 없다.

# twelve_stage — 층위 판정을 c.source_layers(=스택)로 한다.
for layer in (SEWOON, WOLWOON, DAEWOON, ILWOON):
    if layer not in c.source_layers or layer not in stage_by_layer:
        continue
→ 스택이 전 후보 동일값이므로 층위 루프도 전 후보 동일하다.
  후보별로 달라지는 것은 event_key의 boost/reduce뿐이다.

# layer_flow — 두 입력 모두 provenance가 아니다.
mult = self._layer_mult.get(frozenset(c.source_layers), 1.0)   # 스택 구성
ten_god_repeat = bool(set(c.source_ten_gods) & repeated_gods)  # evaluated union

# wealth — 층위를 집합으로 뭉개 반환값에 남기지 않는다.
luck_branches = {pillar.branch for _layer, pillar in stack}
→ 어느 층 지지가 발동시켰는지 복원 불가.

# daewoon_hwa — 유일하게 대운을 명시적으로 특정한다.
dw_stem = next((p.stem for layer, p in stack if layer is LuckLayer.DAEWOON), None)
→ 다만 후보별이 아니라 quality(길/흉)군별로 같은 factor를 적용한다.
```

### 14-3. 판정 B에 대한 사전 신호 (중요)

```
일운 후보에게 대운·세운 occurrence를 특정해 공급할 수 있는 modifier는
daewoon_hwa 하나뿐이고, 그마저 후보별이 아니라 quality군(길/흉) 단위다.

relation      target layer only
twelve_stage  stack level
layer_flow    stack level
wealth        복원 불가
ranker        후처리
```

즉 **modifier를 포함해도 후보별 상위 지지는 거의 생기지 않을 가능성이 높다.**
이는 PROV-1의 종료 판정 A(strict generator 유력)를 강화하는 방향이다.

⚠ 다만 이것은 **구조 실사에 의한 예측이지 실측이 아니다.** `daewoon_hwa`가 MINOR
204건 중 몇 건에 실제로 걸리는지는 세어봐야 한다. 예측으로 B를 닫지 않는다.

### 14-4. 그래서 PROV-2 범위를 줄일 수 있다

원안(2a: relation·twelve_stage·wealth·daewoon_hwa / 2b: layer_flow·ranker)은
상위 지지 판정에 기여하지 못하는 modifier에 관측 비용을 크게 쓴다.

```
축소안 PROV-2a  daewoon_hwa만 관측
                → MINOR 204건 중 대운 배경 보정을 받은 수를 센다
                → 판정 B를 여는 최소 경로

축소안 PROV-2b  나머지 5종은 '자격 없음 사유'만 정적으로 기록
                → 관측 코드 대신 이 매핑표를 계약으로 고정
                → 나중에 입력 의미가 바뀌면 회귀로 잡히게 한다
```

원안대로 6종 전부 관측할지, 축소안으로 갈지는 감수 대상이다.

### 14-5. 공통 스키마 (원안 유지 + 축 추가)

```python
@dataclass(frozen=True)
class ModifierContributionEvidence:
    modifier_id: str
    event_key: str

    role: EvidenceRole
    candidate_specific: bool
    occurrence_attribution: OccurrenceAttribution   # ← 추가
    support_eligibility: SupportEligibility

    source_signal_ids: tuple[str, ...]
    source_occurrence_ids: tuple[str, ...]
    source_layers: tuple[str, ...]

    formula_id: str | None
    base_formula_id: str | None
    formula_relation: FormulaRelation

    value_before: float | int | None
    value_after: float | int | None
    pre_quantized_effect: float | None
    numeric_effect: float | int | None

    invoked: bool
    eligible: bool
    changed_numeric_value: bool

    candidate_alignment: CandidateAlignment    # 발생·강도 방향
    favorability_effect: FavorabilityEffect    # 결과 유불리 방향
```

`candidate_alignment`와 `favorability_effect`를 나누는 이유: 상위 세운이 해고 위험
후보 점수를 높이면 발생 근거로는 `SUPPORTS`지만 결과는 `WORSENS`다.

```python
class FormulaRelation(StrEnum):
    EXACT_SAME = "EXACT_SAME"
    SAME_EVENT_FAMILY = "SAME_EVENT_FAMILY"
    DOMAIN_ONLY = "DOMAIN_ONLY"
    UNRELATED = "UNRELATED"
    UNKNOWN = "UNKNOWN"
```

### 14-6. 가설 정의 (PROV-3 산출)

```
A   strict generator            selected base에 상위 occurrence 존재
                                실측: UPPER 96.4% / MINOR 3.6% (일운 11.0%)

B   same-formula effective      A OR (occurrence_attribution=CANDIDATE
                                     + formula_relation=EXACT_SAME
                                     + candidate_alignment=SUPPORTS
                                     + changed_numeric_value=true)

C1  any aligned numeric         A OR (CANDIDATE + 실제 정수 증가)

C2  pre-quantized 포함          C1 OR (정수 동일 + pre_quantized_effect > 0)
```

모든 가설에서 제외:

```
occurrence_attribution != CANDIDATE
support_eligibility = INELIGIBLE
role = CONTEXT_MULTIPLIER / RANKING_ADJUSTER
```

### 14-7. 대운 occurrence 보강

`_daewoon_pillar`가 `label=d.ganji`라 `period_key`가 기간이 아니다(`"甲子"`).
`daewoon_hwa`를 관측하면 대운 occurrence가 직접 등장하므로 보강이 필요하다.

```
analysis_run_id + layer=daewoon + cycle_index + ganji
```

`cycle_index`를 현 객체에서 못 얻으면 `analysis_run_id + daewoon + 간지`를
**request-local identity**로만 쓰고, 전역 집계에서 서로 다른 요청을 합치지 않는다.

### 14-8. PROV-2 완료 불변식

```
score · quality · polarity · confidence · rank · Top-N 불변
API · LLM · 리포트 불변
candidate_source_layers 빈 값 유지 · layer_grounding 비활성 유지
EventScope 미산출 · −6 유지
```

특히 ranker 관측에서 순위가 조금이라도 달라지면 실패다. 기존 정렬 호출의 전후만
기록하며, 감사 ID나 새 필드가 tie-breaker에 들어가면 안 된다.


---

## 15. P2-PROV-2a 실측 (2026-07-27)

### 15-1. 1차 시도는 인공물이었다 — 기록해 둔다

`_apply_daewoon_hwa_background`를 base 직후에 붙여 관측했더니 `eligible=0`이 나왔다.
원인은 `quality`가 `branch()` 직후에는 전부 `None`이고 파이프라인 후반
(`_yongi` · `_exam` · `_career_mobility`)에서 채워지기 때문이다.

```
발견이 아니라 감사 배치가 만든 인공물이었다.
→ recorder를 score() → _score_impl() → _score_target()으로 배선해
  실제 파이프라인 위치에서 다시 측정했다.
```

**교훈**: modifier 관측은 반드시 운영 호출 순서 위에서 해야 한다. 스택을 밖에서
재구성하는 방식(PROV-1에서 쓴 방식)은 base 단계까지만 유효하다.

### 15-2. 결과 — 분모는 unique MINOR 후보 204

```
invoked              56   27.5%
eligible             56   27.5%
changed_numeric      56   27.5%
pre_quantized_only    0    0.0%
no_effect             0    0.0%

align:SUPPORTS       31   (흉 사건 점수 상승)
align:OPPOSES        25   (길 사건 점수 하락)
fav:WORSENS          56   (전부)
```

`fav:WORSENS` 100%는 세 차트의 해당 대운이 모두 압력(化神 기·구)이기 때문이다 —
길 사건은 낮추고 흉 사건은 올리므로 양쪽 다 결과는 악화다. `candidate_alignment`와
`favorability_effect`를 나눈 설계가 여기서 실제로 갈린다.

### 15-3. 판정 B — A와 동일하게 유지한다

```
MINOR 204건 중 대운 배경 보정을 받은 후보   56 (27.5%)
그중 발생 방향을 지지한 후보                31 (15.2%)

그러나
  candidate_specific = False       quality군 단위 — event_key로 분기하지 않는다
  formula_relation   = UNRELATED   base 승자 formula와 무관하게 적용된다
```

가설 B의 요건(`EXACT_SAME` + `candidate_specific`)을 만족하지 못한다.
**따라서 B = A이며, 31건을 상위 사건 지지로 승격하지 않는다.**

대신 별도 관찰값으로 남긴다.

```
UPPER_BACKGROUND_ADJUSTED = 56/204 = 27.5%

의미: 상위 대운 occurrence가 후보의 품질·길흉에 영향을 주었으나
      사건 발생의 상위 근거로는 인정되지 않음
용도: LLM 설명에는 유용할 수 있음. P2 major-event 자격에는 미사용
```

### 15-4. 정정 — 인용해야 할 수치는 레벨별이다

엔진 전 구간 실행으로 바꾸자 세운 표본이 달라졌다.

```
                   스택 재구성    엔진 실행
year UPPER            3648          384
전체 후보             5739         2475
MINOR_ONLY 비율        3.6%         8.2%

day   MINOR 171 / UPPER 1385   11.0%   ← 동일
month MINOR  33 / UPPER  502    6.2%   ← 동일
MINOR 절대수 204                        ← 동일
```

`idx.sewoon_by_year`가 `luck_cycles.yearly_luck`보다 넓어 세운 분모만 달라졌다.
**레벨별 수치와 MINOR 절대수는 두 방식에서 동일**하므로, 이후 인용은 전체 비율이
아니라 레벨별 수치를 쓴다. §13의 3.6%는 세운 분모가 과대한 값이었다.

### 15-5. 종료 판정

```
A 채택 방향   selected base만으로 day 11.0% / month 6.2%의 모집단이 나온다
B = A         daewoon_hwa는 quality군 배경이라 B를 A보다 넓히지 못한다
C1·C2         daewoon_hwa 외에 후보별 numeric modifier가 없어 산출 대상이 없다
D 배제        UNKNOWN 0 · NO_SELECTED_BASE 0
```

남은 감수는 "A를 P2의 상위 사건 지지 정의로 확정할 것인가"와
"`UPPER_BACKGROUND_ADJUSTED`를 LLM 설명에 쓸 것인가" 두 가지다.


---

## 16. P2-PROV-3-lite 실측 (2026-07-27) — 12명식

`scripts/audits/provenance_lite_survey.py` · 전 표본 **동일 full-pipeline 경로**
(`EventEngineV2.score`)로만 산출했다. §13의 전체 3.6%(스택 재구성)와 섞지 않는다.

```
차트 12건 · 후보 9493 · MINOR 729
UNKNOWN 0 · NO_SELECTED_BASE 0
불변식 upper + minor + unknown == unique candidates → 9493 == 9493 ✓
```

### 16-1. 레벨별 — 모집단은 일운에 있다

```
day    MINOR 587 / UPPER 5260
month  MINOR 142 / UPPER 2002
year   MINOR   0 / UPPER 1502

day MINOR 비율   1.0% ~ 22.7% (평균 10.6%)
```

⚠ 편차가 제안 범위(7~15%)보다 넓다. 다만 **12명식 전부에서 MINOR가 관측**됐고
(최소 차트 09도 8건), 특정 명식 고유 현상이 아니다. 편차 자체는 명식 구조 차이로
보이며, 이 값을 게이트 임계로 쓰지 않으므로 P2 진행에는 지장이 없다.

### 16-2. 도메인별 — 한 도메인에 몰려 있지 않다

```
career        360   (day 292)
relationship  221   (day 174)
health         55   (day  40)
wealth         49   (day  38)
education      44   (day  43)
```

5개 도메인에 분포한다. career·relationship이 큰 것은 후보 생성량 자체가 많기 때문으로
보이며, **P2의 사용자 영향은 이직·연애 답변에 가장 크게 나타난다.**

### 16-3. 긍부정 — 양방향 게이트가 필요하다

```
positive 372 · negative 327 · neutral 30
```

거의 균형이다. minor-only 부정 후보 327건은 P2가 막아야 할 "일운만 불리 →
이별·해고·계약 파기" 비약의 실제 모집단이고, 긍정 372건은 "일운만 유리 →
취업 성사·큰 수익" 비약의 모집단이다. **대칭 적용이 설계가 아니라 실측 요구다.**

### 16-4. 정정 — `fav:WORSENS 100%`는 표본 특성이었다

```
차트 3건  minor: WORSENS 56 / IMPROVES 0     ← 100%
차트 12건 minor: WORSENS 56 / IMPROVES 71    ← 양방향
          upper: WORSENS 635 / IMPROVES 504
```

§15-2의 100%는 세 명식의 해당 대운이 모두 압력(化神 기·구)이었기 때문이다.
표본을 넓히자 우호 대운에서 `IMPROVES`가 정상적으로 나온다. **구조적 결과가 아니라
표본 편중이었다.**

### 16-5. A의 의미 안정성 — 표본 검증 통과

차트 04(MINOR 비율 최고 22.7%)의 일운 MINOR 97건 전수 확인:

```
승자 occurrence에 대운·세운이 섞인 건수      0   ✓
상위 evaluated 근거가 있었으나 승자가 아닌 건수  51
```

51건이 핵심이다 — 대운·세운 근거가 **평가는 됐지만 base 승자가 되지 못했다.**
evaluated union과 selected base를 나눈 설계가 실제로 작동한 증거다.

```
표본 2026-06-01 contract_document
  승자 rule=SINGLE_PIANYIN score=26.0
       occ=('transit:wolwoon:2026-06:transit:stem:甲:context',)
  평가 INITIAL_WINNER 26.0 layers=('wolwoon',)
```

### 16-6. 종료 조건 판정

```
데이터 안정성    UNKNOWN 0 · NO_SELECTED_BASE 0 · 등식 성립       ✓
모집단 실재      12명식 전부 · 5개 도메인 · 긍부정 양방향          ✓
A의 의미 안정성  승자 occurrence에 상위 층위 혼입 0건              ✓
배경 보정 분리   daewoon_hwa는 base formula·occurrence에 미개입    ✓
```

**A를 PROV-4 감수에 올릴 수 있다.**
