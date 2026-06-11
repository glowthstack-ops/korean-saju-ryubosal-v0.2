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
```

가장 먼저 만들 것은 **"십성·관계·용기신이 어떤 이벤트로 이어지는가" 매핑 테이블**. 이것이 Event Graph RAG의 뼈대다.
