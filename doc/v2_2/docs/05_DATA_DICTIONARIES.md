# 05. 사전(Dictionary) 데이터 스키마 & 유지관리

## 원칙

- 룰/사전 = JSON (사람이 수정하는 원본)
- 누적 사례 = JSONL
- 운영은 **검증·컴파일된 스냅샷**만 읽는다. 원본 JSON 직접 로드 금지.
- intent 중심 분할 로드: 이사 질문이면 `events/relocation.json` + `calendar/`만.

## 파일 레이아웃

```
src/dictionaries/
  common/
    stems.json              # 천간
    branches.json           # 지지/지장간
    ten_gods.json           # 십성 → 도메인 매핑
    elements.json           # 오행 생극
  relations.json            # 합충형파해/공망/병존/복음/간여지동
  interpretations/          # ★ 해석 사전 계층 (v2.2.1 신설) — "글자의 의미"를 LLM에 공급하는 원천
    ilju.json               # 60갑자 일주 — 물상/일주 동물/캐릭터 서사/빛·그림자 성향/배우자궁 함의
    ten_gods_text.json      # 십성 10종 — 의미/과다·부재·혼잡/용신·기신 발현 차이/일상 비유
    relations_text.json     # 합충형파해·원진·암합·병존·간여지동·복음·공망 작용 해석 (궁위별/원국 vs 운)
    twelve_stages_text.json # 십이운성 12종 — 에너지 단계 의미/일상 비유
    sinsal_text.json        # 신살 — 의미/발현 영역/주의점 (공포 조장 금지 톤)
    stems_branches_text.json# 천간 10·지지 12 물상 — 모든 비유의 원천 재료
  favorability_rules.json   # 용신/희신/기신/구신/한신 보정
  events/
    taxonomy.json           # EventKey 표준 + progress/instant/hybrid 분류
    relocation.json         # 이벤트별 신호→이벤트 매핑
    career_change.json
    relationship.json
    wealth.json
    education.json
    health.json
  stage_mapping.json        # 신호 유형 → 타임라인 단계(awareness/action...) 매핑
  calendar/
    son_eomneun_nal.json    # 손없는 날 규칙 (음력 9·0일)
    direction_rules.json    # 방위 규칙
    avoid_days.json         # 금기일/회피일
    holidays.json
  purpose_profiles.json     # 택일 목적별 가중치
  relation_profiles.json    # 궁합 관계 유형별 분석 축 (부부/부모자식/동업... — E13)
  remedy.json               # 개운/보완 6분기 (시기회피/주의행동/오행 생활화... — docs/08 D-3)
  terminology.json          # 명리 용어 교육용 사전 (Q11 — 실측 71건)
  time_expressions.json     # 시점 표현 어휘 (오늘/내일/모레/글피, 하반기, 인생단계... — docs/08 C)
  occupation_taxonomy.json  # 직업 분류 O01~O18 + 물상 매핑 (docs/11 3-1, reviewed:false 시작)
  persona_lexicon.json      # 페르소나 종결어미/난이도 규칙/성별·연령 어휘 (docs/11 5-3)
  honorific_presets.json    # 호칭 프리셋 + 금칙어 필터 (docs/11)
  defaults.json             # 분야별 기본 기간 (연애 6개월 등)
  templates/
    interpretation.json     # 해석 템플릿 (이벤트×polarity별)
    prohibited_styles.json  # 금기 표현
    format_slots.json       # 일일/주간/연간 고정 슬롯
tests/fixtures/
  cases.jsonl               # 검증 사례 (Past Validation 피드백 포함)
compiled/
  event_graph_v1.0.0.json
  event_rules_v1.0.0.json
```

## 핵심 스키마

### stems.json (항목 예)

```json
{
  "version": "1.0.0",
  "items": [
    {
      "stem": "甲",
      "element": "木",
      "yinYang": "양",
      "tenGodByDayMaster": { "己": "정관", "庚": "편재" },
      "domains": ["직업", "규칙", "책임", "압박"]
    }
  ]
}
```

### interpretations/ilju.json (항목 예 — v2.2.1 신설)

```json
{
  "ganji": "己亥",
  "animal": { "color": "노란", "name": "돼지", "derivation": "천간 己=토(황) + 지지 亥=돼지" },
  "imagery": "평화롭고 비옥한 들판(己) 아래로 맑고 깊은 강물(亥)이 유유히 흐르는 형상",
  "narrative": "겉으로는 부드럽고 다정한 정원사 같지만, 내면에 바다 같은 지혜와 냉철한 판단력을 숨긴 사람…",
  "traits": {
    "light": ["온화·단정해 어디서나 환영받음", "실속을 차분히 챙기는 영리함"],
    "shadow": ["속내를 잘 드러내지 않아 답답하게 보일 수 있음"]
  },
  "spouse_palace_note": "일지 정재 — 배우자·재물 안정 지향, 가정에 충실한 경향",
  "computed": { "iljiTenGod": "정재", "twelveStage": "태", "hiddenStems": ["戊", "甲", "壬"] },
  "basis": "자평 통설: 己土가 亥 중 壬水 정재에 좌(坐) — 재성 좌는 실리·안정 지향. 물상은 전답 위 강물의 전통 비유.",
  "reviewed": false
}
```

**해석 사전(interpretations/) 공통 규칙:**

1. **`basis` 필드 의무** — 모든 서술의 명리적 근거(자평 통설 기준)를 명시한다. 전문가 감수는 이 필드를 기준으로 수행하며, `scripts/export_review_sheet.py`로 감수 시트를 추출한다.
2. **`computed` 블록은 만세력 엔진과 전수 교차검증** — validate 단계에서 십성·십이운성·지장간·오행색·띠 동물이 엔진 계산과 하나라도 어긋나면 컴파일 실패. (서술의 기술적 오류를 기계적으로 차단)
3. **`narrative`·`imagery`는 `basis`에서 도출 가능한 범위로만 집필** — 근거 없는 단정(수명·재앙·확정 길흉)은 `templates/prohibited_styles.json`과 동일 기준으로 사전 콘텐츠에서도 금지. 일상 속 비유와 서사를 적극 사용한다(사용자 이해도 우선 — 2026-06-12 사용자 확정).
4. **운영 로드는 발췌만** — 전체 사전 투입 금지(절대 원칙 2). Planner의 dictionaryScope가 질문 주제와 관련된 엔트리만 선별하고, 사용자별 고정분(일주·원국 활성 십성/신살/관계)은 캐시되는 프롬프트 prefix에 배치한다(docs/06).
5. **일간 중심·상황 의존 해석** — 십성·십이운성·관계 해석은 고정 키워드가 아니라 "일간 기준으로 원국 보유 시 / 운에서 들어올 때 / 용신·기신일 때"를 구분해 집필한다. 정교한 구분이 풀이 정확도를 결정한다(2026-06-12 사용자 확정).
6. **신살·암합 = 보조 자료(auxiliary)** — 풀이의 색채를 더하는 참고일 뿐 결론의 근거가 될 수 없다. `sinsal_text.json`·암합 엔트리는 `role:"auxiliary"`를 의무 표기하고, 신살/암합 단독으로 길흉·이벤트를 판정하는 서술을 금지한다(2026-06-12 사용자 확정).

### relations.json (항목 예)

```json
{
  "id": "rel_甲己合",
  "type": "stem_combination",
  "name": "갑기합",
  "participants": ["甲", "己"],
  "resultElement": "土",
  "possibleModes": ["합화", "합반", "합래", "합거"],
  "eventDomains": ["career_change", "contract", "relocation"],
  "baseScore": 0.6
}
```

### favorability_rules.json (항목 예)

```json
{
  "ruleId": "unfavorable_ten_god_activation",
  "condition": { "favorability": "기신", "tenGod": "정관" },
  "effect": {
    "polarity": "negative_or_forced",
    "scoreModifier": -0.25,
    "interpretation": "책임, 압박, 강제성 증가"
  }
}
```

이 사전이 없으면 모든 합·충이 무차별 이벤트가 된다. 용신=긍정 강화 / 희신=완만한 긍정 / 기신=부담·강제성 / 구신=손실·왜곡 / 한신=조건부.

### events/*.json (신호→이벤트 매핑 예)

```json
{
  "signal": { "tenGod": "정관", "relation": "stem_combination", "favorability": "기신" },
  "eventCandidates": [
    { "event": "career_change", "score": 0.75, "polarity": "forced_or_burdensome" },
    { "event": "contract", "score": 0.62, "polarity": "conditional" }
  ]
}
```

signal 키(v2.2.1): `tenGod`(운 천간 십성) / **`branchTenGod`(운 지지 본기 십성 — 신설)** /
`relation` / `favorability` / `shinsal` / `daewoonTransition` / `tenGodGroupStrong` /
**`natalWealthCapacity`(원국 횡재 그릇 strong/moderate — Phase 1 신설)**. 모든 키는 AND 조건이다.

> **partner_star 추상화 (관계/결혼 도메인, MARRIAGE_TIMING_ENHANCEMENT §2)**: 전통 기준
> 여=관살(officer_killing)·남=재성(wealth)은 **내부 규칙으로 유지**하되, relationship/marriage
> 도메인의 signal·reason_code·LLM 입력은 `partner_star`(배우자성)·`child_star`(자녀성)로 추상화
> 표기한다. 매핑은 `partnerStarRule`(traditional) 설정으로 관리하며, gender 미상 시 차단하지
> 않고 양 기준 병기 + confidence 하향(원칙 11). 안정성 평가에서 정관/편관을 분기한다(정관=공식·안정,
> 편관=강한 끌림·불안정, 관살혼잡=`mixed_partner_star` risk_flag).

> **원국 횡재 그릇(natalWealthCapacity, Phase 1, 2026-06-16)**: `wealth_capacity` 분석(身強임재·
> 재성 투간·재성 뿌리·암장 식상·재성국 삼합 씨앗·묘고 반복)이 산출하는 원국 그릇 강도. windfall(횡재)
> 해석 규칙은 이 그릇이 받쳐줄 때만 가산한다(그릇 + 운 발동 = 현실화). 그래프 컴파일 시 `wealth_capacity_*`
> 노드 → 규칙 `supports` 엣지로 표현된다(event_graph **v1.1.0**). **로또 1등 당첨 사주 1건에서 도출한
> 가설**이므로 reviewed:false로 두고, 같은 구조가 비당첨자에게도 흔함(확증편향)을 전제로 점수는
> 캘리브레이션 후 확정한다(절대원칙 5). **당첨 단정·로또 번호 생성은 어떤 형태로도 금지**(prohibit_windfall).

> **횡재 발동(Phase 2, 2026-06-16)**: 그릇은 '담을 잠재'일 뿐, **운에서 발동해야 현실화**한다.
> `detect_wealth_activations`가 거버닝 스택(원국+대운+세운+월)에서 ① 재성국 완성(삼합) ② 묘고 충개고
> (辰戌·丑未충) ③ 식상생재(운 천간 식상+재성 동시 투간)를 판정하고, `WealthActivationModifier`가
> windfall/wealth_change 후보 점수를 **그릇 배율(strong 1.0 / moderate 0.7 / weak 0.5) × 발동 가중**으로
> 보수 가산한다. **원국에 씨앗이 없어도 운에서 완성되는 경로**를 포함한다(그릇은 하드 게이트가 아니라
> 배율 — 사용자 보완). 단순 '재성 투간(운)'은 평범한 재물 운(base가 이미 wealth_change 생성)이라 횡재
> 발동에서 제외한다. 가중치는 잠정(Phase 4 캘리브레이션). events/wealth.json에는 그릇 게이트 없는
> '운 완성' windfall 후보(편재+삼합, 재성 지지 충)도 추가돼 그래프가 두 경로를 모두 표현한다.

> **동반 신호 매트릭스 원칙 (regression_2025_08)**: 합·정관 신호는 "사건 후보"만 만든다.
> 최종 사건명은 동반 신호 매트릭스(일치 신호의 구성·개수 합산)가 결정한다.
> 예: 甲申월 = 甲己合+정관(직장 후보)이라도 역마+申 상관(식상 이동성)이 동반하면
> 이동·이사 신호가 우세 — "정관합=직장운" 단정은 금지 회귀(cases.jsonl 기준 사례).

### templates/interpretation.json (예)

```json
{
  "event": "career_change",
  "polarity": "forced_or_burdensome",
  "template": "{timeScope}에는 {trigger} 때문에 {domain} 변화 신호가 있습니다. 다만 {unfavorableReason}이므로 자발적 확장보다는 외부 조건에 의한 변화로 보는 편이 자연스럽습니다."
}
```

### cases.jsonl (행 예)

```json
{"caseId":"case_001","signals":["甲己合","정관","기신","대운교체기"],"predictedEvent":"career_change","actualEvent":"unwanted_relocation","time":"2026-06","matched":true,"notes":"정관합이 이직보다 이동/배치 변경으로 발현"}
```

## 유지관리 파이프라인 (필수)

```
JSON 사전 수정
  ↓
npm run dict:validate     # zod 스키마 검증: 필수 필드, EventKey 유효성, score 범위
                          # + interpretations/ computed 블록 ↔ 만세력 엔진 전수 교차검증
  ↓
npm run dict:lint         # 충돌 검사:
                          #  - 같은 신호가 상반 이벤트를 동시에 강하게 유발
                          #  - 기신인데 polarity=positive / 용신인데 무조건 negative
                          #  - relation id 중복
  ↓
npm run graph:build       # compiled/event_graph_vX.Y.Z.json 생성 (semver + updated_at)
  ↓
npm run test:regression   # cases.jsonl 재실행 — 기존에 맞춘 사례가 깨지는지 비교
  ↓
배포 (스냅샷 버전 교체)
```

회귀 테스트 기준 예: "갑기합+정관+기신 → 원치 않는 이동/직업변화"가 여전히 상위권인지.

## MVP 구축 우선순위

```
1순위: common/ (천간/지지/십성/오행)
2순위: relations.json (합충형파해)
3순위: events/taxonomy.json + 십성→이벤트 매핑 (career, relocation 먼저)
4순위: favorability_rules.json
5순위: templates/
6순위: cases.jsonl (운영하며 누적)
7순위(v2.2.1 — 풀이 품질 보완): interpretations/ilju + ten_gods_text + relations_text
8순위(v2.2.1): interpretations/twelve_stages_text + sinsal_text + stems_branches_text,
              terminology.json, templates/interpretation·prohibited_styles, events/ 누락 4종
```

가장 먼저 만들 것은 **"십성·관계·용기신이 어떤 이벤트로 이어지는가" 매핑 테이블**. 이것이 Event Graph RAG의 뼈대다.
