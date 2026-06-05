# 사주서비스 v2 — 격국 분석 명세서

> 목적: 월지 중심 격국 후보, 성패, 안정도, 보조 구조를 계산하기 위한 명세서.  
> 원칙: 격국은 현대 v2에서 참고/보조 모델이며, 단독 용신 확정 기준으로 사용하지 않는다.

---

## 1. 입력

```yaml
geokguk_input:
  pillars:
  hidden_stems:
  ten_god_analysis:
  structure_analysis:
  strength_analysis:
```

---

## 2. 주격 산출

기본은 월지 정기 십성 기준이다.

```yaml
month_branch_basis:
  branch:
  hidden_stems:
    main:
    middle:
    residual:
  main_ten_god:
```

주격 후보:

```text
비견격
겁재격
식신격
상관격
편재격
정재격
편관격
정관격
편인격
정인격
건록격/양인격 등 특수 월령 구조
```

---

## 3. 투간 여부

```yaml
exposure:
  main_qi_exposed:
  same_ten_god_exposed:
  exposed_position:
  exposure_strength:
```

월지 정기가 천간에 투간하면 격의 현실성이 높아진다.

---

## 4. 성격/패격/중성

```yaml
formation_level:
  성:
    condition:
      - 월지 정기 강함
      - 투간 또는 통근
      - 구조 손상 적음

  중성:
    condition:
      - 격 후보는 있으나 투간/통근 일부 부족
      - 손상과 보조가 혼재

  패:
    condition:
      - 월지 손상 큼
      - 핵심 십성 충/합거/공망 등
      - 격을 지탱하는 구조 약함
```

---

## 5. 보조 구조

`보조격`이라는 표현을 남발하지 않는다.

권장 표현:

```text
주격: 정재격
보조 구조:
- 년주 상관 발현
- 월간 편인 발현
- 시주 비견 발현
```

---

## 6. 안정도

```yaml
geokguk_stability:
  score:
  label: stable | mixed | unstable
  reasons:
    - month_branch_supported
    - main_qi_exposed
    - month_branch_clashed
    - self_punishment
```

---

## 7. 출력

```yaml
geokguk_analysis:
  main_structure:
  basis:
  exposure:
  formation_level:
  stability:
  auxiliary_structures:
  warnings:
```

---

## 8. 구현 금지 사항

```text
1. 월지 정기만 보고 격국을 확정하지 말 것.
2. 보조 구조를 모두 보조격이라고 부르지 말 것.
3. 격국만으로 용신을 확정하지 말 것.
4. 월지 충/공망/합화 가능성을 무시하지 말 것.
