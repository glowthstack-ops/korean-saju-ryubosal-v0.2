# 운 오행 실현도 — 입력 신호 감사 (P2-0)

P2-a(역할 중립 실현도)를 구현하기 전에 **무엇을 재사용할 수 있고 무엇이 신규인지**를 재현
가능하게 고정한다. 코드·테스트 assertion·production 출력은 변경하지 않았다.

```
실행 커밋   749379b
활성 플래그  SAJU_LUCK_RELATION_STATE_SHADOW_ENABLED=false (미설정 기본값)
            SAJU_LUCK_RELATION_GRAPH_SHADOW_ENABLED=false
production 영향  없음
```

0A·0B와 같은 규칙으로 두 층을 분리해 적는다.

- **관측** — 실행·조회해서 확인한 사실
- **판단** — 그로부터 확정한 P2 개발 범위

---

## 신호별 결과 요약

| 신호 | 기존 자산 | 재사용 | 판단 |
|---|---|---|---|
| 직접 뿌리 | `strength/rooting.py` | **부분** | 일간 전용 — 프리미티브만 재사용 |
| 지장간 | `constants.hidden_stems_for` | **전량** | 그대로 쓴다 |
| 간접 생조 | `constants.GENERATES` | **전량** | 그대로 쓴다 |
| 생조원 충 | `rooting._clashed_branches` | **불가** | 글자 기반·원국 한정 |
| 절각 | **없음** | — | 신규. 정의 확정 필요 |
| 12운성 | `pillars/twelve_unseong.py` | **전량** | 일간 기준이라는 제약 있음 |
| resolved_element | P1-b1 | 소비처 0 | P2-a가 첫 소비자 |

---

## 1. 직접 뿌리 — 질문이 다르다

### 관측

`compute_rooting(pillars, side_balance_score, gongmang_branches)` 는 **일간의** 통근을 낸다.

```python
def _root_kind(hstem: Stem, day_master: Stem, dm_el: Element) -> str | None:
    if hstem == day_master:   return "primary_root"        # 본기
    if el == dm_el:           return "same_element_root"   # 동기
    if GENERATES[el] == dm_el: return "resource_root"      # 인성
```

세 판정이 모두 `day_master` 를 기준점으로 받는다. 계수도 일간 세력 합산용이다.

```
primary_root 1.00 · same_element_root 0.85 · resource_root 0.65
```

### 판단

P2-a의 질문은 다르다.

```
기존   이 명식의 일간이 통근했는가
P2-a   지금 들어온 이 水가 뿌리를 두고 있는가
```

들어온 오행은 일간이 아니다. `compute_rooting` 을 호출해 답을 얻을 수 없고, **일간 대신
대상 오행을 넣어 재호출하는 것도 맞지 않는다** — 반환값이 신강약 점수 체계에 묶여 있어
의미가 달라진다.

```yaml
decision:
  reuse_compute_rooting: false
  reuse_primitives: true          # hidden_stems_for · STEM_ELEMENT · GENERATES
  rationale: SAME_PRIMITIVES_DIFFERENT_QUESTION
```

**계수 0.85/0.65를 P2-a로 가져오지 않는다.** 그 값은 일간 세력 합산용으로 조정된 것이고,
등급 SSOT 모델(감산 누적 금지)과 맞지 않는다.

`_ROOT_KIND_FACTOR` 의 3분류 자체(본기/동기/인성)는 `RootProfile` 에 그대로 옮길 값이 있다.
다만 P2-a 어휘로는 다음이 맞다.

```
본기·동기  →  DIRECT_*_ROOT   (같은 오행)
인성       →  INDIRECT_GENERATION   (생조이지 뿌리가 아니다)
```

지시받은 대로 `금생수` 는 水의 직접 뿌리가 아니다. 기존 `resource_root` 를 뿌리로 세면 그
구분이 무너진다.

---

## 2. 지장간 · 생조 — 그대로 쓴다

### 관측

```python
hidden_stems_for(branch) -> list[tuple[Stem, HiddenStemType, float]]   # 여기·중기·정기
main_hidden_stem(branch) -> Stem                                        # 정기

GENERATES = {木→火, 火→土, 土→金, 金→水, 水→木}
CONTROLS  = {木→土, 土→水, 水→火, 火→金, 金→木}
```

### 판단

역할 중립이고 일간에 의존하지 않는다. **재정의하지 않는다.**

`hidden_stems_for` 가 budget(합=1.0)을 함께 주지만 P2-a는 **존재 여부**만 쓴다. budget을
점수로 환산하면 감산 누적 모델로 되돌아간다.

---

## 3. 생조원 충 — 기존 판정을 쓸 수 없다

### 관측

```python
def _clashed_branches(branches: list[tuple[str, Branch]]) -> set[Branch]:
    """원국 내 지지충에 걸린 지지 집합(통근 신뢰도 약화용)."""
```

두 가지 제약이 있다.

```
원국 한정   운 지지를 받지 않는다 — 운이 생조원을 치는 경우를 낼 수 없다
글자 기반   set[Branch] 를 돌려준다 — 일지 戌과 시지 戌을 구별하지 못한다
```

두 번째가 특히 문제다. P1-a에서 자리 기반으로 바꾼 뒤 링크가 9건→7건으로 줄었던 것과 같은
성질의 오차다.

### 판단

```yaml
decision:
  reuse_clashed_branches: false
  use_instead: branch_relation_collector.collect_branch_relation_instances
  rationale: CHARACTER_KEYED_AND_NATAL_ONLY
```

P1-b0 collector가 이미 자리 기반이고 운↔원국·운↔운을 모두 낸다. 생조원 충은 그쪽에서 가져온다.

`_root_reliability` 의 감산(공망+충 0.45 / 공망 0.60 / 충 0.75)도 가져오지 않는다 — 감산
누적 금지 지시와 충돌하고, 값의 출처가 신강약 캘리브레이션이다.

---

## 4. 절각 — 코드베이스에 없다

### 관측

```
grep -rn "절각" --include=*.py packages/   → 0건
```

명세에 나오지만 구현도, 대응하는 기존 관계 이름도 없다.

### 판단

**신규 신호다.** "천간이 자신을 극하는 지지 위에 놓임" 이 출발점이고, 미정이던 세 가지를
사용자가 확정했다(2026-08-01).

```yaml
cut_off_rule:
  hidden_stem_scope: MAIN_ONLY          # 정기(본기)만 — 여기·중기 미포함
  position_scope: SAME_PILLAR_ONLY      # 같은 기둥(주) 한정 — 인접 기둥 제외
  transit_stem_over_natal_branch: false # 운 천간 ↔ 원국 지지 조합 제외
```

세 결정 모두 **판정을 좁히는 방향**이다. 근거가 확인된 조합만 남기고, 넓히는 것은 사례가
쌓인 뒤에 한다.

성립 예:

```
운 간지 癸未 → 未 정기 己土 → 癸水를 극 → CUT_OFF_PRESENT
운 간지 癸酉 → 酉 정기 辛金 → 癸水를 생   → 미성립
```

`SAME_PILLAR_ONLY` 이므로 판정 단위는 **간지 한 쌍**이다. 천간이 없는 원국 지지 단독이나
서로 다른 기둥의 조합은 대상이 아니다. 구현은 `main_hidden_stem(branch)` +
`CONTROLS[STEM_ELEMENT[hidden]] == STEM_ELEMENT[stem]` 로 닫힌다 — 신규 사전이 필요 없다.

절각이 확정됐으므로 `SUPPRESSED` 등급이 첫 shadow에서 도달 가능하다.

---

## 5. 12운성 — 쓸 수 있으나 기준점이 일간이다

### 관측

```python
def twelve_unseong(day_master: Stem, branch: Branch) -> str:
    jangsaeng = JANGSAENG_BRANCH[day_master]
    direction = 1 if STEM_YINYANG[day_master] is YinYang.YANG else -1
    steps = (BRANCH_INDEX[branch] - BRANCH_INDEX[jangsaeng]) * direction % 12
    return TWELVE_STAGES[steps]
```

순수 함수이고 `Stem` 을 인자로 받는다. 한글 문자열("장생"…)을 돌려주며
`TWELVE_STAGE_KO_TO_KEY` 로 로마자 키 매핑이 있다.

### 판단

일간을 넘기게 돼 있지만 **임의 천간을 넣어도 계산은 성립한다.** 다만 "이 운 글자의 12운성"
이 무엇을 기준으로 한 값인지가 의미를 가른다.

```
day_master 기준   이 사람에게 이 지지가 어떤 단계인가       (기존 용법)
대상 천간 기준     이 오행이 이 지지에서 어떤 단계인가        (P2-a가 원하는 것)
```

후자를 쓰려면 기준 천간을 정해야 한다. 음양에 따라 `direction` 이 뒤집히므로 임의로 고르면
같은 지지에서 결과가 반대로 나온다(壬-未=양 / 癸-未=묘).

사용자가 확정했다(2026-08-01).

```yaml
twelve_stage_reference_stem: ACTUAL_PILLAR_STEM
```

**대표 천간을 지어내지 않는다.** 간지에는 이미 천간이 있으므로 그것을 쓴다 — 운 글자는 운
간지의 천간을, 원국 글자는 그 기둥의 천간을 기준으로 한다. 음양 문제가 발생하지 않는다.

12운성은 **보조 신호**이고 단독으로 `SUPPRESSED` 를 만들지 않는다. 이미 약한 구조를 확인하는
근거이지 별도 감점이 아니다.

---

## 6. `resolved_element` 소비 지점 — 없다

### 관측

```
grep -rn "resolved_element" packages/ apps/ (관계 모듈·테스트 제외)  → 0건
```

P1-b1이 만든 `resolved_element` 를 읽는 production 코드가 없다. shadow 플래그가 OFF이므로
당연한 결과이며, **P2-a가 첫 소비자**가 된다.

### 판단

P1-c에서 환원된 경우 원래 오행을 쓴다는 지시는 이미 구조적으로 만족된다.

```
亥: 水 → 木 → 환원 → resolved_element = 水, status = ORIGINAL
```

P1-c1a가 결과 상태를 `ORIGINAL` + 원래 오행으로 두었으므로, P2-a는 `resolved_element` 를
그대로 읽으면 된다. **환원 여부를 P2-a가 다시 판정할 필요가 없다.**

`UNCONFIRMED` 는 `resolved_element = None` 이므로 `UNKNOWN` 으로 가는 경로도 그대로 성립한다.

---

## 7. evidence 중복 가능성

### 관측

하나의 `clash:卯酉` 인스턴스가 현재 그래프에서 만들 수 있는 결과가 여럿이다.

```
POTENTIALLY_DISRUPTED_BY   삼합 교란
생조원 酉 불안정
卯未 결합 방해 → 未土 잔존 → 水를 극함
```

P1-a 링크 구조상 같은 `relation_id` 가 서로 다른 dependency에 여러 번 등장한다(실측: 사례
A에서 `clash:卯酉` 가 DISRUPTED 링크 2건에 참여).

### 판단

지시받은 대로 원인과 결과를 분리하고 `evidence_id` 별 기여를 한 번만 센다.

```yaml
cause:
  evidence_id: clash:卯酉@natal.year.branch:卯+sewoon.branch:酉
consequences:
  - INDIRECT_SUPPORT_DISRUPTED
  - HARMONY_COMPLETION_BLOCKED
```

이것이 감산 누적형을 쓰지 않는 실제 이유다. 독립 감점 방식이면 같은 卯酉冲이 세 번 깎는다.

---

## P2 착수 시 확정해야 할 것

코드 진행을 막지 않는 순서로 적는다.

네 건 모두 확정됐다(2026-08-01 사용자 승인).

```
절각 지장간   정기(본기)만
절각 자리     같은 기둥(주)만
절각 운↔원국  제외
12운성 기준   해당 간지의 실제 천간
```

경계 명식 역할 감수는 P2-b가 역할표를 **입력으로** 받으므로 P2 착수를 막지 않는다.

신규 사전이나 신규 상수는 필요 없다. 네 신호 모두 기존 프리미티브로 닫힌다.

```
절각      main_hidden_stem · CONTROLS · STEM_ELEMENT
12운성    twelve_unseong (인자만 바꿔 호출)
뿌리      hidden_stems_for · STEM_ELEMENT
생조      GENERATES
생조원 충  collect_branch_relation_instances (P1-b0)
```

---

## 별건 유지

**CAL-ROLE-BORDERLINE-01** — 경계 명식 용신 모델 선택 감수. 0A에서 등록했고 P2의
선행조건이 아니다. P2-b가 `ENGINE_NATIVE` / `SOURCE_FIXTURE` 두 역할표를 각각 투영하므로,
P2 shadow 결과가 쌓인 뒤 어느 역할표가 과거 검증과 더 일관되는지를 자료로 삼을 수 있다.

**P2가 과거 사건으로 용신을 자동 재선택하지 않는다.** 감수 자료만 제공한다.
