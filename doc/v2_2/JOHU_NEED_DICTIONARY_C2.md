# C2 — 조후 필요신 후보 생성부 교체 설계안 (궁통보감 조건부 필요신 사전 v0.3.0)

작성: 2026-10-07 · 상태: **설계안 — 데굴님 감수·승인 대기** (리포 사전·엔진 미수정)
상위: `CASEBOOK_CALIBRATION_PLAN.md` §4 C2 · 데굴님 지침(2026-10-07): 교체 범위는 "조후 필요신 후보를 만드는
부분"에 한정, 한난조습 심각도·충족도와 최종 통합 판단은 별도 유지, 천간 단위 유지, 필요/작동 분리, 첫 글자=용신
매핑 금지, 120칸은 기본값+조건 규칙, 재현성과 예측 성능을 분리 검증.

## 0. 현재 상태 진단

- 조후 사전은 이미 천간 단위 120칸(`dictionaries/johu_yongsin.json` v0.2.0, primary/secondary/avoid/climate_axis)이고
  한난조습 2축 severity(`_climate_axes`)·투간/지장간 작동성·비 severe 시 가산 없음까지 구현돼 있다(2026-07-13 감수 v3).
- **결함은 후보 생성 한 줄이다**: `yong_el = STEM_ELEMENT[primary[0]]` — 셀 첫 글자의 **오행**을 조후 후보로 환원한다.
  궁통보감 취용표의 첫 글자는 한난 교정 글자가 아닌 경우가 많다(亥月 甲: 庚=벽갑인정 → 조후 후보 '金'; 丑月 丙:
  壬=輝映 → 조후 후보 '水'; 寅月 癸: 辛=생수원). severe 축일 때만 교정 오행으로 바꾸므로, 비 severe 셀에서는
  생조·제련·설기 글자가 "조후 후보"라는 이름으로 축 가중치(한난 월 0.40)를 받는다 = 억부와 **중복 가산**.
- 두 번째 결함: 조후 역행 강등(`_climate_harmful`)이 **월지와 화·수 분포**만 보고 적용된다(축 severity 무관). 丑月
  己亥(026, 047/R)처럼 축이 neutral(−5~−7)인데도 水를 기신으로 떨어뜨린다.
- 세 번째: 조후 역할 글자가 원국에 **투간**해 있고 축이 severe인데 그 오행이 구신이 되는 경우(063/L 癸 투간 ·
  severe_heat 60.9 → 水 구신). 필요와 작동이 분리되지 않고, 최종 역할맵이 조후 충족 글자를 거꾸로 깎는다.

## 1. 구성 (데굴님 표에 대응)

| 구성 | 담당 | 이번 변경 |
|---|---|---|
| 일간×월지 120칸 사전 | 전통 필요 천간·역할·관계·출전 | **v0.3.0**: 셀마다 `needs[]` 추가(천간별 역할 태그·관계·출전), v0.2 키 호환 유지 |
| 조건·예외 규칙 | 시기(절입 후 n일)·원국 구성에 따른 후보 변경 | `conditions[]` 슬롯 신설(초안은 비움, 辰月 癸 청명/곡우 등은 2차 감수) |
| 한난조습 평가 | 불균형 심각도·해소 여부 | `_climate_axes` 그대로 |
| 작동성 평가 | 필요 글자의 투간·지장간·부재, 극제 | 기존 투간/지장간 판정 유지 + 조후 역할 글자에만 적용 |
| 최종 통합 판단 | 억부·격국·통관과 함께 평가 | 축 가중치 그대로 + **최저 역할 보장**(§3 규칙 B, 승인 필요) |

## 2. 사전 v0.3.0 스키마

```json
"甲": { "亥": {
  "primary": ["庚"], "secondary": ["丁","丙","戊"], "avoid": [], "climate_axis": "cold",
  "needs": [
    {"stem":"丁","roles":["climate_warm","drain"],"relation":"priority","note":"丁火 조후(겸 설기)","tag_source":"override"},
    {"stem":"庚","roles":["control","pair"],"relation":"pair","note":"庚劈甲引丁 — 丁과 배합, 단독 조후 아님","tag_source":"override"},
    {"stem":"丙","roles":["climate_warm"],"relation":"alternative","note":"丁 부재 시 온난 대체","tag_source":"override"},
    {"stem":"戊","roles":["control"],"relation":"alternative","note":"亥 왕수 제수","tag_source":"override"}
  ],
  "conditions": []
}}
```

- `roles` 어휘: `climate_warm | climate_cool | climate_dry | climate_moisten`(한난조습 직접 교정 — **조후 축 점수
  대상은 이것뿐**) / `source`(생조) / `drain`(설기) / `control`(제어·제련) / `wealth`(재·소토) / `peer`(방조) / `pair`(배합
  필수). 한 글자가 둘 이상 가질 수 있다(夏月 甲의 癸 = climate_cool + source). 조후 점수는 climate 역할만 쓰고 억부는
  십성 역할만 쓰므로 같은 글자라도 **한 축에서 한 번만** 가산된다.
- `relation`: `priority`(우선) / `pair`(배합: 단독으로 작동하지 않음) / `alternative`(대체재). 첫 글자=용신 매핑을
  하지 않는다 — 조후 후보는 climate 역할 글자 전체이고, 우선순위는 relation 으로만 표현한다.
- `tag_source`: `override`(궁통보감 문맥 수동, 감수 대상) / `mechanical`(십성·축 규칙 자동). 초안은 한난 월(亥子丑·
  巳午未) 60칸 전부와 일부 전이 월을 override 로 태깅했고(157건), 나머지는 mechanical 이다.
- `conditions[]`: `{"when": {"term_after": "穀雨"} | {"chart": "..."} , "needs": [...], "note": ...}` 형식. 초안 비움.
- 검증(`build_johu_snapshot.py` 확장): needs 의 천간이 primary∪secondary 와 같은 집합, roles 어휘 검사, 한난 월 셀에
  climate 역할이 없으면 **경고**(오류 아님 — §4-1). validate → compile(`compiled/johu_yongsin_v0.3.0.json`) → 회귀.

초안 파일: 스크래치패드 `johu_yongsin_v0.3.0_draft.json` (리포 미반영). 한난 월 60칸 태그는 §6 표.

## 3. 엔진 규칙 (승인 항목)

**규칙 A — 조후 후보는 climate 역할 글자만.** `_johu_model`의 후보 오행은 `needs` 중 `climate_*` 역할 글자의 오행에서만
나온다. `source/drain/control/wealth/peer/pair` 글자는 `classical_support`로 모델 reasons·설명에만 싣고 점수에 넣지
않는다(억부·격국 축과 중복 금지). climate 글자가 둘(丁·丙)이면 relation 순으로 첫 글자를 대표로 쓰되 둘 다 작동성을
본다. **climate 글자가 없는 셀**(§4-1의 10칸)은 조후 후보를 내지 않고 축 severity 만 경고로 남긴다.

**규칙 B — 최저 역할 보장(floor).** 최종 5역할 확정 뒤, 기후 축이 `mild` 이상(cold/heat/dry/damp 또는 severe_*)이고
조후 후보 오행이 정해졌으면 그 오행은 **기신·구신이 될 수 없다**(최저 한신). 두 안 중 택일:
- B-1(보수): 최저 한신만 보장.
- B-2(적극): severe 축 + 교정 글자 원국 부재면 최저 **희신**(억부 용신은 유지, 희신 자리만 조후에 양보).
- 근거 사례: 042(辛 午月 severe_heat 74, 壬癸 부재 → 현재 水 구신), 063/L(癸 투간·severe_heat → 水 구신).
- 기존 기준 사주 6건·종격 3종·Case A·표준차트에 대한 영향은 §5 검증으로 확인한다(변화 시 승인 전 유지 안 함).

**규칙 C — 조후 역행 강등은 축 성립 시에만.** `_climate_harmful` 강등(한습 水 / 조열 火 → 용·희 부적격)을 월지+분포가
아니라 `_climate_axes`의 해당 축이 `mild` 이상일 때만 적용한다(severe 한정인 기존 플래그 B보다 한 단계 완화). neutral
축에서는 강등하지 않는다(026·047/R 류). 이것은 C1-a(종격 면제)와 독립이다.

**규칙 D — 필요/작동 분리 출력.** 모델 reasons 에 `need=丁·丙 / present=丙(장간) / absent=丁`처럼 필요 글자와 원국
존재를 따로 적는다. 부재해도 후보에서 지우지 않고(필요는 유지), 존재한다고 충족 판정하지도 않는다(작동성은 투간>
장간>부재 + 극제 여부로 등급만).

## 4. 초안 검토 포인트

### 4-1. climate 역할 글자가 없는 한난 월 셀 (10칸)
丙·丁(火 일간)의 亥子丑, 丁巳, 庚未, 壬未, 癸巳. 궁통보감은 火 일간 겨울에 火를 쓰지 않고 甲(인경·생조)을 쓰며, 庚未는
丁 제련·甲 배합, 壬未는 辛 생원·甲 설기, 癸巳는 辛 생원이다. 규칙 A에 따라 이 셀들은 조후 후보를 내지 않는다.
**질문**: 이 셀들에서 축이 severe 일 때(예: 035 丁巳 severe_heat 45~56) 교정 오행(水)을 '구조 경고'로만 둘지, 낮은
신뢰도(0.25) 보조 후보로 둘지.

### 4-2. 수동 override 중 판단이 갈릴 수 있는 것
- 庚金 겨울: 丁=제련(control), 丙=온난(climate_warm) 분리. 丑月은 丙 priority.
- 丙火 겨울: 壬=輝映(control), 甲=생조(source). 조후 글자 없음.
- 辛金 亥月: 壬=淘洗(drain) priority, 丙=온난 alternative. 子丑月은 丙 priority.
- 여름 水 글자의 이중 역할(climate_cool + source/wealth/drain/peer/control)은 전부 이중 태깅.
- 戊/己 겨울 甲=소토(control) — 조후 아님.

### 4-3. conditions 2차 감수 후보
辰月 癸(청명 후/곡우 후), 寅月 癸(辛 생원 vs 丙 온난의 시기), 未月(大暑 전후 조열 강도), 申月 壬(戊 제수 vs 丁).

## 5. 검증 계획 (재현성 ≠ 예측 성능)

1. **재현성**: 180 사례집 + shadow 33 + 기준 6 + 테스트 코호트에 대해 전/후 비교표 — 조후 후보 변경, 최종 용희기구한
   변경, 변경 근거(어느 규칙), 중복 가산 여부(같은 오행이 climate 와 십성 역할로 두 축에서 가산됐는지 로그).
2. **기준 불변**: `test_yongsin_reference_charts.py` 6건, 종격 3종, Case A, 표준차트, 1965 johu 차트(용水·희金) 등 기존
   엄격 테스트 전부 통과. 변하면 표로 제시하고 승인 전 유지하지 않음.
3. **예측 성능**: 사례집 지표(쌍 비교·시점 대운/세운 극성·이벤트 히트)를 C1 기준선(45.6 / 59.1 / 34.1 / 50.0)과 비교.
   실제 사건·시점만 근거로 쓰고 사례집의 용희기신 표기는 쓰지 않는다(자료 신뢰 경계).
4. **강등 감사**(데굴님 2번): §7 표의 17건을 실제 사건과 조후표로만 재판정.

## 6. 한난 월 60칸 역할 태그 초안 (*=수동 override, 나머지 mechanical)

| 일간 | 월지 | 축 | needs (글자[역할;관계], *=수동 override) |
|---|---|---|---|
| 甲 | 巳 | heat | 癸[climate_cool/source;pri*] · 丁[drain;alt*] · 庚[control;alt*] |
| 甲 | 午 | heat | 癸[climate_cool/source;pri*] · 丁[drain;alt*] · 庚[control;alt*] |
| 甲 | 未 | heat | 癸[climate_cool/source;pri*] · 丁[drain;alt*] · 庚[control;alt*] |
| 甲 | 亥 | cold | 庚[control/pair;pai*] · 丁[climate_warm/drain;pri*] · 丙[climate_warm;alt*] · 戊[control;alt*] |
| 甲 | 子 | cold | 丁[climate_warm/drain;pri*] · 庚[control/pair;pai*] · 丙[climate_warm;alt*] |
| 甲 | 丑 | cold | 丁[climate_warm/drain;pri*] · 庚[control/pair;pai*] · 丙[climate_warm;alt*] |
| 乙 | 巳 | heat | 癸[climate_cool/source;pri*] |
| 乙 | 午 | heat | 癸[climate_cool/source;pri*] · 丙[drain;alt*] |
| 乙 | 未 | heat | 癸[climate_cool/source;pri*] · 丙[drain;alt*] |
| 乙 | 亥 | cold | 丙[climate_warm;pri*] · 戊[wealth;alt*] |
| 乙 | 子 | cold | 丙[climate_warm;pri*] |
| 乙 | 丑 | cold | 丙[climate_warm;pri*] |
| 丙 | 巳 | heat | 壬[climate_cool/control;pri*] · 庚[wealth;alt*] · 癸[climate_cool;alt*] |
| 丙 | 午 | heat | 壬[climate_cool/control;pri*] · 庚[wealth;alt*] |
| 丙 | 未 | heat | 壬[climate_cool/control;pri*] · 庚[wealth;alt*] |
| 丙 | 亥 | cold | 甲[source;pri*] · 戊[control;alt*] · 庚[wealth;alt*] · 壬[control;pri*] |
| 丙 | 子 | cold | 壬[control;pri*] · 戊[control;alt*] · 己[control;alt*] |
| 丙 | 丑 | cold | 壬[control;pri*] · 甲[source;pri*] |
| 丁 | 巳 | heat | 甲[source;pri*] · 庚[wealth;alt*] |
| 丁 | 午 | heat | 壬[climate_cool/control;pri*] · 庚[wealth;alt*] · 癸[climate_cool;alt*] |
| 丁 | 未 | heat | 甲[source;pri*] · 壬[climate_cool/control;alt*] · 庚[wealth;alt*] |
| 丁 | 亥 | cold | 甲[source;pri*] · 庚[wealth/pair;pai*] |
| 丁 | 子 | cold | 甲[source;pri*] · 庚[wealth/pair;pai*] |
| 丁 | 丑 | cold | 甲[source;pri*] · 庚[wealth/pair;pai*] |
| 戊 | 巳 | heat | 甲[control;alt*] · 丙[source;alt*] · 癸[climate_cool/wealth;alt*] |
| 戊 | 午 | heat | 壬[climate_cool/wealth;pri*] · 甲[control;alt*] · 丙[source;alt*] |
| 戊 | 未 | heat | 癸[climate_cool/wealth;pri*] · 丙[source;alt*] · 甲[control;alt*] |
| 戊 | 亥 | cold | 甲[control;pri*] · 丙[climate_warm;pri*] |
| 戊 | 子 | cold | 丙[climate_warm;pri*] · 甲[control;pri*] |
| 戊 | 丑 | cold | 丙[climate_warm;pri*] · 甲[control;pri*] |
| 己 | 巳 | heat | 癸[climate_cool/wealth;pri*] · 丙[source;alt*] |
| 己 | 午 | heat | 癸[climate_cool/wealth;pri*] · 丙[source;alt*] |
| 己 | 未 | heat | 癸[climate_cool/wealth;pri*] · 丙[source;alt*] |
| 己 | 亥 | cold | 丙[climate_warm;pri*] · 甲[control;alt*] · 戊[peer;alt*] |
| 己 | 子 | cold | 丙[climate_warm;pri*] · 甲[control;alt*] · 戊[peer;alt*] |
| 己 | 丑 | cold | 丙[climate_warm;pri*] · 甲[control;alt*] · 戊[peer;alt*] |
| 庚 | 巳 | heat | 壬[climate_cool/drain;pri*] · 戊[source;alt*] · 丙[control;alt*] · 丁[control;alt*] |
| 庚 | 午 | heat | 壬[climate_cool/drain;pri*] · 癸[climate_cool;alt*] |
| 庚 | 未 | heat | 丁[control;pri*] · 甲[wealth/pair;pai*] |
| 庚 | 亥 | cold | 丁[control;pri*] · 丙[climate_warm;pri*] |
| 庚 | 子 | cold | 丁[control;pri*] · 甲[pair;pai*] · 丙[climate_warm;pri*] |
| 庚 | 丑 | cold | 丙[climate_warm;pri*] · 丁[control;pri*] · 甲[pair;pai*] |
| 辛 | 巳 | heat | 壬[climate_cool/drain;pri*] · 甲[wealth;alt*] · 癸[climate_cool;alt*] |
| 辛 | 午 | heat | 壬[climate_cool/drain;pri*] · 己[source;alt*] · 癸[climate_cool;alt*] |
| 辛 | 未 | heat | 壬[climate_cool/drain;pri*] · 庚[peer;alt*] · 甲[wealth;alt*] |
| 辛 | 亥 | cold | 壬[drain;pri*] · 丙[climate_warm;alt*] |
| 辛 | 子 | cold | 丙[climate_warm;pri*] · 戊[source;alt*] · 壬[drain;alt*] · 甲[wealth;alt*] |
| 辛 | 丑 | cold | 丙[climate_warm;pri*] · 壬[drain;alt*] · 戊[source;alt*] · 己[source;alt*] |
| 壬 | 巳 | heat | 壬[climate_cool/peer;pri*] · 辛[source;alt*] · 庚[source;alt*] · 癸[climate_cool/peer;alt*] |
| 壬 | 午 | heat | 癸[climate_cool/peer;pri*] · 庚[source;alt*] · 辛[source;alt*] |
| 壬 | 未 | heat | 辛[source;pri*] · 甲[drain;alt*] |
| 壬 | 亥 | cold | 戊[control;pri*] · 丙[climate_warm;pri*] · 庚[source;alt*] |
| 壬 | 子 | cold | 戊[control;pri*] · 丙[climate_warm;pri*] |
| 壬 | 丑 | cold | 丙[climate_warm;pri*] · 丁[climate_warm;alt*] · 甲[drain;alt*] |
| 癸 | 巳 | heat | 辛[source;pri*] |
| 癸 | 午 | heat | 庚[source;pri*] · 辛[source;alt*] · 壬[climate_cool/peer;alt*] · 癸[climate_cool/peer;alt*] |
| 癸 | 未 | heat | 庚[source;pri*] · 辛[source;alt*] · 壬[climate_cool/peer;alt*] · 癸[climate_cool/peer;alt*] |
| 癸 | 亥 | cold | 庚[source;pri*] · 辛[source;alt*] · 戊[control;alt*] · 丁[climate_warm;alt*] |
| 癸 | 子 | cold | 丙[climate_warm;pri*] · 辛[source;alt*] |
| 癸 | 丑 | cold | 丙[climate_warm;pri*] · 丁[climate_warm;alt*] |

## 7. 조후 강등 17건 감사 (C1 적용 후 상태, 실제 사건 기준)

| 사례 | 명식 | 월지·축 | 조후 역할 글자(초안) | 원국 존재 | 기후축(값) | C1 후 용/희/기/구/한·모델 | 강등 기록 | 실제 사건(요약) |
|---|---|---|---|---|---|---|---|---|
| 008/L | 癸酉 甲子 甲子 壬申 | 子·cold | 丁[climate_warm/drain] 丙[climate_warm] | 丁:부재 丙:부재 | severe_cold(-83.3) | 金/土/水/木/火·resource_pattern_officer | - | 보험설계사·빚으로 실적·가품 선물 |
| 008/R | 癸酉 甲子 甲子 己巳 | 子·cold | 丁[climate_warm/drain] 丙[climate_warm] | 丁:부재 丙:장간 | severe_cold(-64.2) | 火/木/水/金/土·johu | - | 체육학 석사; 선수촌 컨디션 관리→사직·미국 유학 준비 |
| 015/L | 戊申 乙丑 己亥 甲戌 | 丑·cold | 丙[climate_warm] | 丙:부재 | cold(-27.6) | 木/金/土/火/水·officer_controls_peer | 水(pattern_sangsin) | 일반 회사 CS 직원 |
| 026/L | 戊午 乙丑 己亥 丁卯 | 丑·cold | 丙[climate_warm] | 丙:장간 | neutral(-7.1) | 金/水/火/土/木·eokbu_normal | 水(eokbu_normal) | 검사 |
| 026/R | 戊午 乙丑 己亥 丙寅 | 丑·cold | 丙[climate_warm] | 丙:투간 | neutral(-5.0) | 金/水/火/土/木·eokbu_normal | 水(eokbu_normal) | 월 천만원 요리사 |
| 035/L | 戊寅 丁巳 丁巳 庚子 | 巳·heat | 없음 | - | severe_heat(45.1) | 水/土/火/木/金·officer_controls_peer | 火(pattern_sangsin) | 북미 의대·의사 |
| 035/M | 戊寅 丁巳 丁巳 己酉 | 巳·heat | 없음 | - | severe_heat(55.9) | 水/土/火/木/金·officer_controls_peer | - | 전윤철(기재부장관·감사원장 등) |
| 035/R | 戊寅 丁巳 丁巳 辛丑 | 巳·heat | 없음 | - | severe_heat(49.7) | 水/土/火/木/金·officer_controls_peer | - | 70대 200억 자산() |
| 038/L | 戊戌 己未 戊申 己未 | 未·heat | 癸[climate_cool/wealth] | 癸:부재 | dry(19.7) | 木/金/土/火/水·officer_controls_peer | - | 식당·돈 적음; 배우자 없음 |
| 038/R | 戊戌 己未 戊申 壬戌 | 未·heat | 癸[climate_cool/wealth] | 癸:부재 | dry(9.9) | 木/金/土/火/水·officer_controls_peer | - | 일본 유학·건축으로 큰돈; 배우자 2004 자궁암 진단(2004) |
| 042/L | 丙戌 甲午 辛巳 丁酉 | 午·heat | 壬[climate_cool/drain] 癸[climate_cool] | 壬:부재 癸:부재 | severe_heat(74.3) | 土/金/木/水/火·resource_as_yongsin | - | 30세 이전 극빈(); 영화배우 대성공 |
| 042/R | 丙戌 甲午 辛巳 辛卯 | 午·heat | 壬[climate_cool/drain] 癸[climate_cool] | 壬:부재 癸:부재 | severe_heat(64.2) | 土/金/木/水/火·resource_as_yongsin | - | 부유한 집안; 정치인(대통령) |
| 047/R | 辛丑 辛丑 己酉 庚午 | 丑·cold | 丙[climate_warm] | 丙:장간 | damp(-6.5) | 金/水/火/土/木·eokbu_normal | 水(eokbu_normal) | 심장질환 |
| 063/L | 癸巳 戊午 甲午 壬申 | 午·heat | 癸[climate_cool/source] | 癸:투간 | severe_heat(60.9) | 土/火/木/水/金·disease_remedy:pyeonin_dosik | 火(follow_structure) | 임용고시 다회 낙방; 학원사업 壬戌대운 발재(壬戌) |
| 069/R | 庚戌 丁亥 甲午 己巳 | 亥·cold | 丁[climate_warm/drain] 丙[climate_warm] | 丁:투간 丙:장간 | neutral(8.1) | 木/水/金/土/火·support_day_master | - | 정신질환 |
| 070/R | 辛丑 辛丑 丙午 庚寅 | 丑·cold | 없음 | - | neutral(-4.5) | 火/木/水/金/土·support_day_master | 水(johu) | 금전 관련 수감 |
| 075/L | 庚戌 壬午 丙子 壬辰 | 午·heat | 壬[climate_cool/control] | 壬:투간 | neutral(16.9) | 土/火/木/水/金·disease_remedy:mixed_officer_killing | 火(support_day_master) | 고관대작 |

판정 메모(엔진 관점, 사람 감수 전):
- 중복 가산 유형(규칙 A 대상): 070/R(丙 丑月: 壬=輝映이 '조후 水'로 후보) → C2 후 조후 후보 없음.
- 강등 과잉 유형(규칙 C 대상): 026/L·R, 047/R — 축 neutral 인데 월지 규칙으로 水 강등.
- 최저 역할 위반 유형(규칙 B 대상): 042/L·R(severe_heat, 水 부재 → 구신), 063/L(癸 투간·severe_heat → 水 구신).
- 조후 글자 없음 유형(§4-1): 035 L/M/R(丁 巳月) — 현재 억부가 水 용신을 내므로 결과는 같고 근거만 바뀐다.
- 이미 해소: 008/R(C1-b 후 johu 火), 008/L(火 한신), 038(水 한신), 069/R(火 한신), 075/L(축 neutral·壬 투간, 병약 모델 —
  규칙 B 비대상).

## 8. 작업 순서 (승인 후)

1. 사전 v0.3.0 반영 + `build_johu_snapshot.py` 검증 확장 + 스냅샷 컴파일(`JOHU_YONGSIN_VERSION` 0.3.0).
2. `_johu_model` 후보 생성부 교체(규칙 A·D), `_climate_harmful` 게이트(규칙 C), floor(규칙 B) — 각각 플래그.
3. §5 검증표 생성 스크립트(`scripts/johu_ab_compare.py`) → 전/후 표 제시 → 승인 → 커밋.
