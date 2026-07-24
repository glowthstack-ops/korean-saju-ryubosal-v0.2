# P2-3 블라인드 감수 템플릿 — 관계 벡터 계수 (RELATIONSHIP_VECTOR_CALIBRATION §11)

> **목적**: C0/C1 구조와 weight shortlist를 사람이 감수해 결정한다. **구조 이름에 따른
> 편향을 없애기 위해 profile 이름을 숨기고**(Profile A/B/C…), 각 축을 독립적으로
> 평가한다. "C0와 C1 중 무엇이 좋은가"를 직접 묻지 않는다.

## 0. 감수 원칙

- **블라인드**: profile 실명(D0_baseline·D1_C1_act…)을 감수자에게 노출하지 않는다.
  무작위 라벨(A~G)로 제시하고, 라벨↔profile 매핑은 감수 종료 후 개봉한다.
- **축 독립 평가**: activation·stability·separation 각각 따로 적정성을 판단한다.
  구조/weight가 무엇을 바꿨는지 알려주지 않는다.
- **legacy 비참조**: legacy 후보·delta는 정답이 아니다. 참고 열로도 제시하지 않는다
  (감수 후 별도 분석에서만). 감수는 **명리 의미상 적정성**만 본다.
- **자동 채택 없음**: 감수 결과는 P2-4 결정의 입력이지 자동 규칙이 아니다.

## 1. 감수 표본 구성 (§4 — 24~30건)

**disagreement 15건만 쓰면 차이 큰 사례만 보는 편향** → control 사례를 더한다.

| 군 | 출처 | 건수 |
|---|---|--:|
| profile disagreement | P2-1D 경계 사례(band/sign/sep 갈림·C0≠C1·D1≠D3) | 15 |
| control(전 profile 일치) | single-kind root·same-root compound·cross-root compound·HAP only·HAP+negative·JAENGHAP·PA+HAE·MT2/RP same-root 대표 | 9~15 |
| **합계** | | **24~30** |

> control은 "차이가 나는 곳에서만 C1이 좋아 보이는지, 평범한 사례에서도 의미를
> 유지하는지" 확인용. disagreement와 분리 표기(감수자에겐 섞어 무작위 제시).

## 2. 사례 제시 형식 (per 사례)

profile 라벨을 숨긴 채, 각 사례에 대해 전 profile의 3축 값·band를 나란히 제시:

```
[사례 #12]  root 수: 2 · kind 조합: 충+형(같은 root) · modifier: 없음

           Profile A   Profile B   Profile C   Profile D   ...
activation  strong      moderate    strong      strong
stability   -1.24(neg)  -1.24(neg)  -0.99(neg)  -1.24(neg)
separation  1.18(str)   1.18(str)   1.18(str)   0.94(mod)
```

(변화를 만든 contribution은 감수 후 분석용으로 별도 보관 — 감수 중 비노출.)

## 3. 감수 응답 형식 (축별 독립)

각 사례·각 profile에 대해:

```
Activation:  [ ] 너무 약함  [ ] 적절함  [ ] 너무 강함  [ ] 판단 근거 부족
Stability:   [ ] 압력 과소  [ ] 적절함  [ ] 압력 과대  [ ] 판단 근거 부족
Separation:  [ ] 과소       [ ] 적절함  [ ] 과대       [ ] 판단 근거 부족
```

추가 선택(사례 단위):
```
[ ] 프로필 간 의미 있는 차이 없음
```

> "어느 profile이 최선?"을 직접 묻지 않는다. 축별 적정성 응답을 모아 P2-4에서 집계한다.

## 4. C1 채택 기준 (§12 — 감수 집계 후 판단)

C1은 "분리 가능하다"는 이유로 채택하지 않는다. 아래가 **여러 구조군에서 반복**돼야 한다:

```
same-root compound에서
  activation factor는 0.3보다 낮은 값이 더 적절 (감수 다수 "activation 너무 강함")
동시에
  stability/separation pressure는 동일하게 낮출 필요 없음 (감수 "pressure 적절함")
```

반복 확인 대상 구조군(최소):
```
CHUNG + HYEONG   ·   PA + HAE   ·   HAP + negative   ·   RP + MT2 same-root
```

**반대 신호 → C0 유지**:
- D3(CHUNG bonus 국소 조정)가 D1(구조 분리)과 같은 문제를 더 단순하게 해결
  (P2-1D 실측: D1은 root≥2도 약화·D3는 root=1만 — 문제 성격이 다르면 각각 weight로
  해결 가능한지 우선 검토)
- C0와 C1의 감수 차이가 작음(대부분 "차이 없음" 또는 "둘 다 적절")

## 5. weight shortlist 결정

축별 감수 집계로 다음을 판단(자동 아님):
```
activation.CHUNG bonus 하향이 다수 사례에서 "적절→적절" 유지하며 "너무 강함"을 줄이는가
stability.pressure.CHUNG 하향이 "압력 과대"를 줄이는가 (과소로 넘기지 않고)
separation.CHUNG 하향이 ordering 유지하며 "과대"를 줄이는가
support.HAP 조정이 stability 방향을 의미상 개선하는가
```

## 6. P2-4 연결 (감수 종료 후)

```
감수 집계 → C0/C1 구조 결정 → weight shortlist 확정
→ calibration profile 확정(rel.vec.cal.v2 후보) → RELATIONSHIP_CALIBRATION_VERSION bump
→ 실험 telemetry와 분리 → P3 증거 계약(4축)은 별도 트랙
```

**주의**: P2-4에서 실제 값을 채택할 때만 공식 CALIBRATION_VERSION을 올린다. 그 전까지
모든 profile은 experiment_only·production BASELINE 불변(§8·§9 versioning).

---

## 부록 — 감수 진행 체크리스트

```
[ ] profile 라벨 무작위화(A~G)·매핑 봉인
[ ] disagreement 15 + control 9~15 = 24~30건 구성
[ ] 축별 값·band만 제시(contribution·legacy 비노출)
[ ] 축 독립 응답 수집(강/적/약/근거부족)
[ ] "차이 없음" 선택 허용
[ ] 집계 후 라벨 개봉·구조군별 C1 적절성 반복 확인
[ ] C0 유지 vs C1 채택 결정 근거 기록
[ ] weight shortlist 결정 근거 기록
[ ] 결정은 P2-4 입력(자동 규칙 아님)
```
