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
    ten_god_domain_interaction.json # 운 유입 십성 × 질문 도메인 기준 십성 생극 → '교차 작용' 1줄(2026-10-01, 서술 전용, 길흉=용기신 원칙 유지)
    ten_gods_text.json      # 십성 10종 — 의미/과다·부재·혼잡/용신·기신 발현 차이/일상 비유
    relations_text.json     # 합충형파해·원진·암합·병존·간여지동·복음·공망 작용 해석 (궁위별/원국 vs 운)
    twelve_stages_text.json # 십이운성 12종 — 에너지 단계 의미/일상 비유
    sinsal_text.json        # 신살 — 의미/발현 영역/주의점 (공포 조장 금지 톤)
    stems_branches_text.json# 천간 10·지지 12 물상 — 모든 비유의 원천 재료
  favorability_rules.json   # 용신/희신/기신/구신/한신 보정
  daily_fortune/            # ★ 일주별 오늘의 운세 (docs/17, 챠트리스 휘발성 콘텐츠) — 2026-07-23 신설
    daily_event_catalog.json    # 생활 사건 28종(good12/caution10/support6) — 십성·관계 세분·오행 affinity, 동의어 그룹
    daily_phrase_templates.json # 조합형 문장 템플릿(사건당 fragment3·action3·result2) + generic fallback + 로또 3종
    daily_lucky_places.json     # 행운의 장소 20종(오행별 4) — 사건 영역 매핑
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
    color_rules.json        # 오행 정색·계열(木靑·火赤·土黃·金白·水黑 + 계열, 2026-10-01) — 오행 보완 색 첨언 전용. 보라·파랑은 배정 보류(검수 큐)
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

### career_fields.json (2026-09-10 신설 — 데굴님 제공 자료)

십성 → 직업 **기능**(생산·표현·거래·관리·통제·탐구·전승) 대응표. 직업명 고정이 아니라 "어떤 기능과 방식으로 일하는가"를 근거로 쓴다. 구성: `principles`(단정 금지 원칙 5) / `ten_gods`(10종: traits·job_groups·distinction·conditions·favorable_roles·caution) / `judgment_factors`(월령·격국·일간 강약·용희신·배합·위치) / `combinations`(식신생재 등 9 — 구조 패턴 id 또는 derived_rule) / `yongsin_modifiers`(용희신 조건 6) / `thresholds`(엔진 문턱 — 자료에 없는 기계 기본값, 감수 대상). 소비: `saju_engines/career_field.py` → 채팅 `[직업 분야 근거]` 블록(점수·판정 아님). reviewed=false.

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
  "narrative": "부드럽고 다정한 정원사 같은 외면과, 바다 같은 지혜와 냉철한 판단력을 품은 내면을 함께 갖춘 사람…",
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
   - **역접 연결 기준(2026-10-01 데굴님 지시)**: '~지만/~보여도/~ㄴ데/~면서도'는 앞뒤가 반대 성질(장점↔약점, 긍정↔부정)일 때만 쓴다. "겉으로는 다정하지만 내면에는 영리함"처럼 둘 다 장점이면 역접이 성립하지 않으므로 "다정한 외면과 영리한 내면을 함께 갖춘"처럼 병렬로 쓴다. ilju.json 1.0.1에서 60갑자 전수 교정(24건), `tests/unit/test_interpretations_dict.py::test_no_false_contrast_between_surface_and_inner`가 겉/속 대조 역접 구문을 lint 한다.
   - **재물 주장 태그(`wealth_claims`, ilju.json 1.1.0 — 2026-10-13 데굴님 확정)**: 일주 사전은 60일주 공용 문안이라 개인의 재물 판정 근거가 될 수 없다. 재물 관련 문장을 문장 단위로 `type` 태그한다 — `fortune_assertion`(재물복 단정) · `interest`(관심·성향) · `ability`(능력 평가, `ability_kind`=business/wealth_sense/preservation/practical_gain 필수) · `accumulation`(축재 결과) · `cultural_symbol`(띠 동물 등 문화적 상징). 복합 문장은 `clauses`에 절별 의미(재물 무관 장점은 `other`)를 기록하고, 무관한 장점이 함께 빠지면 `split_review: true`로 분리 감수 대상임을 표시한다(명리적 부정 판정이 아니다). 서술 블록(`chart_interpretation._serialize_ilju`)은 **재성 역할과 무관하게 문장 유형으로** fortune_assertion·accumulation·ability를 생략하고 고쳐 쓰지 않는다 — ability는 능력 종류별로 필요한 근거(수익 구조 ≠ 사업 판단력, 수익 창출 ≠ 보존·관리)를 현재 엔진이 구분하지 못해 근거 부족으로 생략한다. interest·cultural_symbol은 유지하되 상징은 개인 재물복의 근거로 쓰지 않는다(`context_reducer.ILJU_WEALTH_USE_RULE`가 일주 블록 바로 뒤에 항상 실림: 재성 용희기구한은 작용의 유불리이지 재물 능력의 유무가 아니며, 시기·축재 결과는 운을 함께 확인). validate 단계가 태그 원문 존재·`ability_kind` 정합·`split_review` 절 기록을 교차검증한다. 회귀: `tests/unit/test_ilju_wealth_claims.py`(60일주 전수·재성 역할 5종).
   - **감수 대기(2026-10-13 등록)**: ① 戊子 — 물상·서사 대부분이 재물 내용이라 생략 후 남은 문장만 쓰는 상태(물상 줄 없음, "샘을 너무 깊이 감추면"의 '샘'이 앞 문장 생략으로 지시 대상을 잃음). ② `split_review` 복합 문장 — 아래 표의 재물 무관 장점이 함께 빠져 있어 절 분리 문안이 필요하다. ③ ability 문장 전체 — 능력 종류별 검증 근거(엔진 신호) 정의 후 복원 여부 결정. 이번에 자체 생성 오류 감사기(생성 후 결정론 교정)는 보류했으며, LLM 자체 생성 빈도가 낮다는 것은 확인되지 않은 가정이다.

| 일주 | 위치 | 문장 | 함께 빠진 재물 무관 내용 |
|---|---|---|---|
| 乙丑 | narrative | 푸른 소가 묵묵히 밭을 갈듯, 화려하게 떠벌리지 않으면서 실속은 야무… | 화려하게 떠벌리지 않음 · 알고 보면 제일 단단한 사람이라는 평판 |
| 甲戌 | narrative | 재물을 다루는 수완이 통이 커서 푼돈보다 목돈의 흐름을 읽고, 일을 … | 일을 맡으면 자기 일처럼 끌고 가는 주인의식 |
| 丁丑 | narrative | 무언가를 깊이 파고들어 연구하는 끈기가 있어 전문 분야에서 실력자가 … | 연구하는 끈기·전문 분야 실력자 |
| 壬午 | narrative | 사람을 끌어당기는 친화력이 있고, 일에서는 손에 잡히는 실속을 야무지… | 사람을 끌어당기는 친화력 |
| 壬午 | narrative | 성실하게 흐르는 강물처럼 꾸준해서 재물도 차곡차곡 모이는 구조예요.… | 성실하고 꾸준함 |
| 戊子 | imagery | 큰 산속 깊은 곳에 숨은 옹달샘 — 묵직한 산의 겉과 맑은 재물의 샘… | 묵직한 산의 겉 |
| 戊子 | narrative | 이 일주는 산속의 옹달샘이라, 듬직하고 과묵한 외면과 반짝이는 재물 … | 듬직하고 과묵한 외면 |
| 戊子 | narrative | 차분히 관찰하다 좋은 기회를 조용히 잡아내는 눈썰미가 있고, 돈이든 … | 차분히 관찰하는 눈썰미 |
| 己丑 | narrative | 손에 잡히는 것을 차곡차곡 쌓는 저축형 기질이라 시간이 갈수록 단단해… | 시간이 갈수록 단단해짐 |
| 庚寅 | narrative | 이 일주는 숲에 길을 내는 도끼라, 생각이 서면 곧장 몸이 움직이는 … | 생각이 서면 곧장 움직이는 행동파·개척자 |
| 辛卯 | narrative | 일과 재물을 다루는 감각도 꼼꼼해서 허투루 새는 것이 없어요.… | 일을 다루는 꼼꼼함 |
| 癸巳 | narrative | 이 일주는 아침 햇살 속의 물안개라, 부드럽고 사근사근한 분위기 뒤에… | 부드럽고 사근사근한 분위기 |
| 癸巳 | narrative | 눈치가 빠르고 상황 파악이 정확해서 어디서든 제 자리를 빨리 찾고, … | 눈치·상황 파악이 정확함 |
| 乙未 | narrative | 재물을 다루는 손끝이 야무지고 부지런해서 살림이든 사업이든 알차게 키… | 부지런함 |
| 丙申 | narrative | 사교성이 좋고 화통해서 처음 보는 사람과도 금세 친해지고, 동시에 여… | 사교성·화통함 · 여러 일을 굴리는 멀티 능력 |
| 己亥 | narrative | 예의가 바르고 단정해서 어디를 가나 환영받고, 자신의 실속을 차분하게… | 예의 바르고 단정해 환영받음 |
| 己亥 | narrative | 노란 돼지는 예로부터 복을 불러오는 풍요로운 존재로 여겨져서, 타고난… | 노란 돼지는 복을 불러오는 존재 · 성실함 |
| 己亥 | traits.light | 타고난 재물 감각과 성실함… | 성실함 |
| 辛丑 | narrative | 손끝이 야무져 허투루 쓰는 것이 없어요.… | 손끝이 야무짐 |
| 甲辰 | narrative | 이 일주는 옥토에 뿌리내린 거목이라, 자기 분야에서 큰 그릇을 키워 … | 자기 분야에서 그릇을 키워 가는 뚝심 |
| 甲辰 | traits.light | 기회를 크게 키우는 사업 감각과 뚝심… | 뚝심 |
| 己酉 | narrative | 이 일주는 추수의 들녘이라, 심은 만큼 거두는 정직한 생산성과 꼼꼼한… | 정직한 생산성·꼼꼼한 마무리 솜씨 |
| 己酉 | narrative | 손끝에서 결과물이 차곡차곡 나오는 구조라 시간이 갈수록 곳간이 차요.… | 결과물이 차곡차곡 나옴 |
| 甲寅 | narrative | 옳다고 믿는 길은 손해를 보더라도 가는 대쪽 기질이 있어 시간이 갈수… | 손해를 보더라도 옳은 길을 가는 대쪽 기질 · 믿을 수 있는 사람으로 섬 |

4. **운영 로드는 발췌만** — 전체 사전 투입 금지(절대 원칙 2). Planner의 dictionaryScope가 질문 주제와 관련된 엔트리만 선별하고, 사용자별 고정분(일주·원국 활성 십성/신살/관계)은 캐시되는 프롬프트 prefix에 배치한다(docs/06).
5. **일간 중심·상황 의존 해석** — 십성·십이운성·관계 해석은 고정 키워드가 아니라 "일간 기준으로 원국 보유 시 / 운에서 들어올 때 / 용신·기신일 때"를 구분해 집필한다. 정교한 구분이 풀이 정확도를 결정한다(2026-06-12 사용자 확정).
6. **신살·암합 = 보조 자료(auxiliary)** — 풀이의 색채를 더하는 참고일 뿐 결론의 근거가 될 수 없다. `sinsal_text.json`·암합 엔트리는 `role:"auxiliary"`를 의무 표기하고, 신살/암합 단독으로 길흉·이벤트를 판정하는 서술을 금지한다(2026-06-12 사용자 확정).

### interpretations/dohwa_text.json (2026-10-13 신설 — 도화 정비)

**정비 기준(데굴님 확정)**: 글자 보유와 도화 성립을 구분하고, 판정된 사실만 '도화'로 풀이에 연결한다. 판정은 엔진 `saju_engines.dohwa.analyze_dohwa`(원국·운 미반영)가 하고 이 사전은 서술 재료만 준다.

| 유형 | 판정 | 풀이 사용 |
|---|---|---|
| 가도화 | 子午卯酉 보유 — 내부 명칭 **사정지** 유지 | 개성·자기주장 성향으로만. 도화 성립·이성적 매력의 직접 근거 금지 |
| 진도화 | 연지·일지 삼합국 기준 년살 지지가 원국 자리에 있음(기존 신살 판정과 동일) | 기준 지지·성립 자리를 함께 기록. '도화가 있다'의 유일한 근거 |
| 월담도화 | 시지에 진도화 성립 | 진도화의 위치 하위 유형 — 별도 매력 가산 금지. 시주 미상이면 미확정 |
| 나체도화 | **도입(2026-10-13 데굴님 지시)** — 일지가 일간의 12운성 목욕인 일주(甲子·乙巳·庚午·辛亥, 엔진 `twelve_unseong` 값 기준). 포스텔러 소개 견해를 결합해 일주와 **천충지충**(天干四沖 + 지지충)인 원국 기둥 동반 여부를 함께 기록: 동반=두 견해 모두 성립 / 미동반=일지 목욕만으로 성립한다는 견해에 해당 / 시주 미상이고 알려진 기둥에 없으면 미확정 | 성향 "가식 없는 솔직함·꾸미지 않은 매력"(데굴님 제시 표). 진도화와 별도 유형 — 매력 점수 가산 없음 |
| 십성 조합 | 도화 성립 지지의 본기를 일간 기준 십성으로 계산해 비겁·식상·재성·관성·인성으로 분류(자리마다 기록). 편관·정관=관성도화, 편인·정인=인성도화 | 매력의 핵심·발현 방식(데굴님 제시 표 그대로) |

- 구조: `types`(sajeong·jin·wolldam·naked: condition·feature·basis·reviewed) + `combos`(5군: label·tenGods·core·manifestation·basis·reviewed). **사전 항목 9개(유형 4·십성군 5), 풀이에 실리는 해석 문구 8개**(가도화·월담도화·나체도화 특징 3 + 십성군 5 — 진도화 항목은 정의 전용이라 풀이 문구로 쓰지 않는다). validate가 유형 4종·십성군 5종 정확 커버리지, 라벨 `{군}도화`, 소속 십성 정합을 검사한다.
- **해석 문구 노출(2026-10-13 정정)**: 엔진 판정(유형·자리·기준·십성군)·사용 규칙(코드 상수 — 진도화만 '도화', 월담 가산 금지, 사정지 성향 전용)·해석 문구(특징·핵심·발현)를 **기본으로 함께 싣는다**. `reviewed`는 검토 상태 기록용이며 노출 조건이 아니다 — 검수는 실제 사용 결과(풀이)를 보고 판단한다. 노출 로그 `dohwa_text_exposed surface=chat thread=… turn=… keys=[…]` / `surface=report section=… keys=[…]`로 실답을 찾아 검토한다. 경위: 붙여 넣은 외부 검토 의견의 '검수 후 연결'을 지침으로 오인해 승인분만 싣는 게이트와 검수용 플래그(`SAJU_DOHWA_TEXT_REVIEW_EXPOSE`)를 넣었다가(ab49a5d), 데굴님이 실행 불가능한 지침이며 준 적 없다고 정정해 제거했다.
- **'도화 없음' 표현 한정**: 진도화가 없으면 "현재 분석 대상 원국에서 진도화가 확인되지 않음"으로만 쓰고, 운에서 들어오는 도화나 이 블록이 판정하지 않는 유형까지 부정하지 않는다.
- 풀이 블록 `structural_context.dohwa_structure_lines`: 노출 게이트 = 도화·매력·인상 직접 질문 / 관계 도메인 / 명식 분석(외적 인상 블록과 같은 결, 리포트는 결혼 자원 섹션). 보조 자료 표기·자리별 구분·중복 가산 금지·문구 범위 밖 단정 금지 규칙을 함께 싣는다.
- 소비처 정비: 결혼 자원(`charm_present`)·궁합은 글자 보유 조건을 제거했다(도화=진도화, 홍염=일간 기준 홍염 지지 — 각자 조건). 궁합의 개인 도화는 `SINSAL_DOHWA` 보조 신호로 분리해 두 사람의 끌림 점수에 넣지 않는다(한쪽 도화로 상호 끌림 단정 금지). 결혼 자원 일지 왕지 기질은 '도화형'과 "이성 인연이 잦고 끌림이 빠르나…" 서술을 빼고 "개성·자기주장이 뚜렷해 관계에서도 '내 페이스'를 지키려는 결"로 바꿨다. 외적 인상은 후보 비교 후 **D안 확정**(일지 진도화 1.2 · 일지 외 진도화·홍염 1.0 · 같은 진도화 중복 가산 없음 · 글자 보유 신호 제거). 기존 수치를 재사용했다는 사실만으로 가중 타당성이 확보되지는 않는다. 궁합 끌림 감소는 잘못된 가산 제거로 수용하며 기존 '강' 비율 복원 보정은 하지 않는다(7.7%는 이번 표본 결과일 뿐 정확도 검증이 아니다).
- **후속 항목 상태(2026-10-13 종료)**:
  - **질문 기간 운 도화(주제별 기간 질문) — 구현 완료.** '10월 5일 연애운'처럼 기간이 있고 도화가 관련된 질문(관계 도메인 또는 도화·매력 직접 질문)에 `chat_service._luck_dohwa_context`가 그 기간(일 14일·월 12개·연 3개 이내)의 운 기둥에서 운 도화를 뽑아 "[질문 기간 운 도화 — 원국 도화와 별개 층 … 질문한 기간에만 적용]" 블록으로 싣는다. 줄은 기간 총운과 같은 공용 빌더(`chart_interpretation.luck_dohwa_sinsal_line`)라 판정·십성군·기간 규칙이 같고, 기간 총운에 이미 실린 기간은 건너뛴다(중복 삽입 금지). 무관한 주제(직업·재물 등, 매력 직접 질문 제외)에는 붙이지 않는다. 로그 `dohwa_text_exposed surface=chat_luck_range`.
  - **운 도화 × 십성군 — 구현 완료.** 기존 운 진도화 판정(`sinsal_for_luck` '도화')을 그대로 쓰고, `saju_engines.dohwa.analyze_luck_dohwa`가 기준 지지(연지·일지 삼합국)와 운 지지 본기 십성(`LuckPillar.branch_ten_god` — 원국 일간 기준)으로 십성군을 붙인다. 기간 총운의 운 신살 줄(`chart_interpretation.build_luck_grounding`)에 운 종류·기간·운 간지·기준·십성군·십성군 문구('운에 적용된 설명')·사용 규칙(그 기간의 매력 노출·인연 기회로만, 타고난 성향·평생 매력 금지, 원국 도화와 구분)을 1줄로 싣는다. 두 기준이 같은 운 지지를 가리켜도 1건·1줄(가산 없음). 문구 키는 `PeriodFortune.dohwa_text_keys` → 로그 `dohwa_text_exposed surface=chat_period thread=… turn=… period=… keys=[luck_combo:…]`. 별도 승인 게이트 없음.
  - **역마형·화개형 — 구현 완료.** 소비처 검색(풀이·리포트·궁합·인상·적성) 결과 글자 기준으로 신살 이름을 붙이던 곳은 결혼 자원 일지 기질 한 곳이었다 — 생지 '역마형'·이동 지향, 고지 '화개형'을 빼고 글자 성향만 남겼다(신살 이름은 상대 12신살 성립 시에만). 구조 패턴 '역마형(驛馬刑, YEOKMA_PUNISHMENT_ACTIVE)'은 이미 상대 역마 성립+형 기준이고, '이동지 충돌(MOVEMENT_BRANCH_CLASH)'은 충·형 관계가 있어야 하며 '역마 아님·보조 전용'으로 분리돼 있어 유지. 신살 사전의 이동지·사고지 표지 문구도 이미 '보유만으로 역마·화개를 뜻하지 않는다'로 분리돼 있다. 새 명리 규칙·가중치는 추가하지 않았다.
  - **나체도화 — 구현 완료(데굴님 지시).** 아래 조사 기록 끝의 결정 참조. `analyze_dohwa` 의 `DohwaProfile.naked`(일주·천충지충 기둥·동반 상태), 원국 도화 블록 1줄(견해 구분·성향 문구·별도 유형 규칙), 노출 키 `type:naked`. 외적 인상·결혼 자원·궁합 점수에는 넣지 않는다.
- **십성 오기 검사(2026-10-13)**: 원국 지지 자리어(연지·월지·일지·시지) 바로 뒤의 십성·십성군을 엔진값과 대조해 명확한 불일치만 재호출 없이 교정하고 조사를 받침에 맞춘다(`saju_engines.ten_god_label_audit`, 채팅 `finalize_answer_full`·리포트 섹션 후처리). 자리어 나열·십성 나열·다른 간지 글자·운 표현 직후·다인 답변(동반자 공동 풀이·궁합)은 건너뛰고, 시주 미상이면 **시지만** 건너뛴다(연지·월지·일지는 그대로 검사). 실답 계기: 프롬프트 '월주 丙子 · 지지 편관'인데 답변 "월지에 자리한 정관".
- 전후 비교(2026-10-13, `scripts/compare_dohwa_consumers.py`, 1950~2009 7일 간격 3,131명·60일주 전부, 결과 `var/compare_dohwa_20261013.txt`): 결혼 자원 도화 표기 70.1%→28.4%, 도화·홍염 끌림 문장 77.9%→49.8%. 궁합 끌림 밴드(1,565쌍) 강 51.5%→7.7%(강→중 43.8%, 중→약 16.1%). 외적 인상 notable 이상 — 현행 A 55.9%, B(성립 기준) 47.7%, C(B+글자 0.3 통합) 48.8%, D(글자 신호 제거) 43.1% → D안 적용. 1차 실행은 9일 간격이라 일지가 辰戌丑未만 표집돼 무효였다 — 스크립트가 60과 서로소 간격·60일주 커버리지를 검사한다.

#### 나체도화 조사 기록 (2026-10-13 — 조사 경위, 같은 날 도입 결정)

제시 목록(甲子·乙巳·丁亥·庚午·辛亥·戊午 일주)의 정의·출처·성립 조건을 확인했다. 정비 기준은 "목욕 일주라는 사실만으로 나체도화와 동일시하지 않고, 출처별 정의를 확인한다"였다(목욕 기준 사용 자체를 금지한 것은 아니다). 확인한 자료들 사이에 정의가 달랐고 제시 목록 전체를 뒷받침하는 근거를 확보하지 못해, 목록을 임의로 합치지 않고 **일단 미도입으로 종료**했다(이후 같은 날 데굴님 지시로 아래 '결정'대로 도입 — 현재 상태는 도입).

| 자료 | 정의·성립 조건 | 해당 일주 |
|---|---|---|
| 포스텔러 X 게시물(un7qi3) | 일지가 12운성 목욕지(목욕=도화 대응). 일주만으로 성립한다는 입장과 **천충지충까지 있어야** 한다는 입장이 함께 소개됨 | 甲子·庚午·辛亥·乙巳 |
| 网易号 "甲子家"(2020-04-24) | 확인한 해당 자료에서는 '裸形桃花'를 甲子일에 월주·시주 庚午(또는 庚午에 甲子)인 경우로 정의 — 두 천간이 모두 목욕을 만나고 지지가 충. 별도 항목으로 '日主自坐沐浴'(甲子·乙巳·辛亥)·'日主桃花'(甲子·乙巳·庚午·辛亥·甲午·庚子·癸亥)를 따로 듦 | 甲子·庚午의 기둥 조합 |
| 무신 정리 글(moooshin) | "일주 자체가 도화의 왕지나 목욕지에 앉아 있는 구조" — 본문 목록과 표 목록이 서로 다름(정화/정유) | 甲子·乙巳·庚午·辛亥 + 불일치 1 |
| 사주클래스 | 일지 자체가 도화이면서 목욕지와 함께 읽는다는 설명뿐 — 성립 규칙·목록 없음 | 없음 |

- 결론: ①확인한 자료 다수는 '일지 목욕'(甲子·乙巳·庚午·辛亥)으로 정의했다. ②포스텔러 게시물은 천충지충을 추가 요건으로 보는 입장도 함께 소개했고, 확인한 网易号 자료에서는 특정 기둥 조합(甲子+庚午)으로 정의해 자료 간 정의가 달랐다. ③확인한 자료에서는 제시 목록의 丁亥(12운성 태)·戊午(제왕)를 포함하는 근거를 찾지 못했다. 정의 차이와 근거 미확보로 당시에는 미도입으로 두었다(추가 조사는 완료 조건이 아니다) — 이후 결정은 아래.
- 도입 조건: 정의·성립 조건이 하나로 확정된 출처(원전 또는 데굴님 확정 기준)가 주어지면 진도화와 별도 유형으로 기록하고, 기존 매력 점수에 자동 가산하지 않는 형태로 구현한다.
- **결정(2026-10-13 데굴님 지시)**: '일지 목욕'(甲子·乙巳·庚午·辛亥) 정의와 포스텔러 게시물이 소개한 견해(일주만으로 성립 / 천충지충까지 있어야 성립)를 합쳐 적용한다 — 일지 목욕이면 성립으로 보고, 천충지충 동반 여부를 함께 기록해 어느 견해에서 성립하는지 구분한다. 제시 목록의 丁亥·戊午는 이 정의에 해당하지 않아 포함하지 않는다. 운 기둥과의 천충지충(운에서 들어오는 경우)은 이번 범위 밖.

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
