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
    yearly_environment.json # 세운 환경(월주 상대 관점) — 십성 10 양방향·12운성 12 상태·관계·통근 어휘, 세운 전용 서술층(2026-10-25)
    sinsal_text.json        # 신살 — 의미/발현 영역/주의점 (공포 조장 금지 톤)
    love_types.json         # 연애 유형 5종(십성군) — 심리·중시·공략·주의·부재 결, 분류기 love_type.py 서술 재료(2026-10-25)
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

### interpretations/transit_peer_mobility_text.json + event_engine/transit_ten_god_branching.json `peer_yongsin_mobility_rules` (2026-10-14 데굴님 확정)

- 규칙: **비겁(비견·겁재)이 용신인 명식에 세운·월운으로 비겁이 들어오면 직장·역할 이동(career_change) 후보를 생성**한다. 이동은 자의(독립·이직)·타의(권고사직·배치 전환) 양방이라 polarity 는 조건부. 간여지동(천간·지지 같은 십성)은 그 기운이 **강하게** 들어온 경우로 기준점이 가장 높고, 약하게(한쪽) 들어와도 관성과의 충 등 다른 작용으로 풀이가 바뀔 수 있어 후보는 항상 만들고 유입 강도만 나눈다(same_god 68 · same_group 58 · stem_only 50 · branch_only 44). 상위 층(대운·세운)에 비겁 뿌리가 있으면 근거 층(`candidate_source_layers`)과 reason `PEER_UPPER_SUPPORT_{layer}`에 적는다. 구현 `saju_engines.peer_mobility_seed`(브랜처 직후 합류 → 6계층 보정 공통), 플래그 `SAJU_PEER_YONGSIN_MOBILITY_ENABLED`(기본 ON).
- 근거: 실사례 `life_event_cases.jsonl` 20261013_career_1 — 1980-11-22 09:40 서울 남(용신 土), 2026-10 戊戌월(겁재 간여지동) 권고사직. 수정 전 엔진은 그 달 career_change 후보가 없었고 '강한 용신운 · 재물 변화 우세'로 읽었다.
- 해석 문구 사전 `transit_peer_mobility_text.json`(항목 3: same_pillar·peer_yongsin_mobility·weak_inflow): `chart_interpretation.incoming_ten_god_note`가 운 간여지동(천간·지지 같은 십성)과 비겁 용신 유입 조건에 맞는 문구를 고르기만 한다(작문 금지). validate가 3 id 정확 커버리지·단정 어휘(반드시·확실히·틀림없이·무조건)를 검사한다. 사건 유형 사전 `event_process_types.json` '이동·교체·재편'의 reason_prefixes 에 `PEER_YONGSIN_MOBILITY` 등록.
- 개인 캘리브레이션: 같은 사건을 `subject_life_events`에 confirmed(delayed_outcome) 1행으로 적재(데굴님 승인) — 개인 시그니처 past_event_match 에 쓰인다.

### event_engine/transit_ten_god_branching.json `favorable_role_tiering` · `transit_clash_mobility_support` (2026-10-15 데굴님 승인)

- 배경: `YongiQualityEngine`이 같은 극성(용신·희신·강한 용신)의 **모든** 후보에 `polarity_rules` 배율을 곱해, 상관 용신의 충돌·이탈(career_change 41)·편관 용신의 압박·편인 용신의 보류가 용신이라는 이유로 더 강해지고 발표·취업·입학 같은 유익형은 뒤에 남았다(외부 검토 지적, 2026-10-15). 사건 '종류'는 십성이 정하고 용·기신은 유불리라는 원칙은 유지하되, **역할에 따른 후보 순위 조정**을 허용한다.
- `favorable_role_tiering`: 용신 역할(`roles`)일 때 **유입 십성별 유익형 사건 목록**(`favorable_events_by_ten_god`, 10십성)에 든 후보에만 모드 배율(`modes`: a=1.10 / b=1.20)을 곱하고 그 외는 1.00. 기존 `polarity_rules` 배율은 이 모드에서 쓰지 않는다(한 곳에서만 곱한다 — 중복 곱 금지). 기신 쪽(quality_flip)은 불변. 기존 단일 운 규칙에 없는 유익형은 `extra_base_events`(편관→promotion 26·편인→creative_output 26)로 모드가 켜졌을 때만 브랜처 기본 후보에 더한다. 출산은 현실 게이트 대상이라 유익형에 넣지 않고, '자립·협력·문제 해결·책임 수행·전문성 활용'은 사건 키가 아니라 작용이라 `yonggi_quality_matrix.json` 용신 문구가 담는다. 용신이라는 이유만으로 취업·승진·입학을 자동 우선하지 않는다(기본점·관계 근거 유지). reason `YONG_TIER_FAVORABLE`(한글 "용신 유익형 가중") / `YONG_TIER_FLAT`(감사용). 구현 `saju_engines.favorable_role_tiering` + `YongiQualityEngine(tiering, tier_mode)` + `TenGodEventBrancher(extra_base_events)`. 플래그 `SAJU_YONG_TIERED_MULTIPLIER_MODE`(off 기본 / a / b — `validate_flags`가 그 외 값을 거부). 비겁 용신 이동 시드(`peer_yongsin_mobility_rules`)와 기준점은 불변 — 그 후보는 유익형 목록 밖이라 모드에서 FLAT(1.00).
- `transit_clash_mobility_support`: 거버닝 스택의 **서로 다른 운 층 사이 지지 충**(대운 壬辰↔월운 戊戌 辰戌충 등)을 이동형 후보(`events`: career_change·relocation)의 **보조 근거**로 `bonus`(4)만큼 후보당 1회 가산한다. 운↔운 충은 층간 충(계층형 grounding)·재물 충개고·합화 상태에서는 이미 계산되지만 사건 점수의 관계 보정(`RelationPalaceEngine`)은 운↔원국 궁위 충만 다뤄 직장·소속 변화 후보에 닿지 않았다. 그 충만으로 '무엇이 변하는가'를 특정하지 않으며, 같은 충을 같은 사건 안에서 여러 이름으로 반복 가산하지 않는다(쌍 전부를 reason 1건 `TRANSIT_CLASH_{층}{지지}-{층}{지지}`에 기록, 한글 "운끼리 충(변화 보조 근거)"). 궁위 관계 보정과 같은 raw 단계(용신 배율 앞)에 둔다. 구현 `saju_engines.transit_clash_support`, 플래그 `SAJU_TRANSIT_CLASH_SUPPORT_ENABLED`(기본 OFF).
- 값은 명리의 확정 수치가 아니라 초기 설계값이다. `scripts/casebook_replay.py --yong-tier-mode {off,a,b} [--transit-clash-support]`로 85사례를 같은 셸에서 재생해 비교하고(시점이 있는 outcome 의 상위 3 적중·방향 오탐, 미기록은 확인 불가로 제외), 적중이 늘면서 오탐이 늘지 않는 안을 택하되 같으면 배율이 작은 a안. 측정 결과는 WORKLOG 2026-10-15 참조. 두 사전 절 모두 reviewed:false.

### interpretations/twelve_stages_text.json `natal_by_palace` — 원국 12운성 궁위별 서사 (2026-10-15 데굴님 지시 '적용 후 감수')

- 외부 교재(wahnjaesky 4장) 대조에서 우리 사전은 단계별 natal 1문장뿐이고 교재는 연·월·일·시 궁위별 해석을 둔 것이 차이였다(`doc/v2_2/EXTERNAL_TEXT_GAP_WAHNJAESKY.md` P1-1). 12단계 × 4궁위 = 48문장을 완화 어휘로 번역해 추가(연주=조상·초년, 월주=부모·형제·청년기·사회 진입, 일주=나·배우자·중년, 시주=자녀·말년). 교재의 단정·흉 어휘('부모 인연 없음', '처를 극함')는 '연이 옅다·거리가 벌어지기 쉽다'로 옮겼다.
- 노출: `chart_interpretation._build_excerpts`가 기둥마다 `kind=twelve_stage_palace`, key "연주 운성 장생" 형식으로 한 줄씩 명식 해석 자료에 싣는다(채팅 구조 블록·리포트 명식 prefix 공용, 시주 미상이면 시주 줄 없음). 문체·서사 전용 — 점수·후보 비개입. 토큰 축소 경로(excerpts[:4])에서는 뒤 순서라 먼저 잘린다.
- lint: 4칸 필수·15자 이상·단정 어휘 금지(`_lint_twelve_stages_text`), 단정 표현 테스트(`test_interpretations_dict`)에 포함. reviewed:false — 실답 노출 로그로 감수.

### interpretations/sinsal_text.json `천사` + sinsal_catalog `CHEONSA` (2026-10-15 데굴님 승인 — evidence 전용 길성)

- 외부 교재 3장 신살 36종 대조(gap 문서 §9)에서 후속 후보로 남긴 둘 중 천사만 추가(삼기는 성립 기준 이견·'귀기' 단정 우려로 보류). 성립: 월지 계절 寅卯辰→戊寅日, 巳午未→甲午日, 申酉戌→戊申日, 亥子丑→甲子日 — 일주 한 자리에만. 카테고리 noble_stars·positive, 신살은 evidence 전용(게이트·점수 비개입, daily 신살 채널 8종 밖). 운 신살로는 들어오지 않는다.
- 문구: 길신·auxiliary·flipSide(안일) 의무, 교재 '모친이 어질고 깨끗' 류 가족 단정은 싣지 않음. reviewed:false.

### 외부 교재 대조 P2 — 궁합 보완 2신호·여명 부성 대체 설명층·이중 충 표지·사생지 충 보조 (2026-10-15 데굴님 '권고대로')

- 궁합(`compatibility_engine._element_season_signals`): ①결핍 오행 보완 — 한쪽 오행 비중 <5% 를 상대가 ≥20% 로 가지면 `ELEMENT_COMPLEMENT`(보완, 끌림 가중 1) ②계절(조후) 보완 — 월지 계절이 여름↔겨울이면 `SEASON_COMPLEMENT`(보완), 둘 다 여름/겨울이면 '조후 쏠림' 보조(중립). 교재 기타절 '없는 오행을 가진 상대', '여름생은 겨울생과'. 궁합 정답 데이터가 없어 실답 감수로만 검증.
- 여명 부성 대체(`MarriageResourceProfile.spouse_star_substitute/_basis`): 관성 ≥30% → 인성 / 관성 미투출·<8% → 재성 / 비겁 ≥30%·인성 없음 → 식상 / 신왕·인성 ≥30%·식상 <5% → 재성. **설명 전용** — 배우자 별(여=관성)·점수·판정 불변, 배우자 블록에 "부성 대체 후보(통설·설명 전용)" 한 줄. 점수 반영 여부는 감수 후 별도 결정.
- 이중 충 표지(`event_engine_v2._apply_double_clash_flag`, 플래그 `SAJU_DOUBLE_CLASH_FLAG_ENABLED` 기본 ON): 원국 충 쌍에 든 지지를 운 지지가 다시 충하면 전 후보 fav_adj −STRUCTURE_PILLAR_PENALTY/2(=−0.05), reason `沖_이중충_{운지}→{원국지}`, 기록 키 `contributions.double_clash`. 점수·순위·사건 종류 불변(85사례 방향 오탐으로 측정 — 결과는 WORKLOG).
- 사생지 충 보조(`risk_auxiliary` 구조 플래그 `life_branch_clash` + `risk_auxiliary_amplifiers.json` `AUX_HLT_LIFE_BRANCH_CLASH` strength 0.2): 운 지지가 원국 지지와 寅申·巳亥 충이면 건강·사고 family 후보(흉 극성)에만 보조 증폭. 교재 '사생지 충=병·사망' 은 단정 금지로 번역.
- 합성 감사(용신 9규칙·격국 조건, 보고서만): `var/audit_textbook_rules_20261015.md`, 요약은 `EXTERNAL_TEXT_GAP_WAHNJAESKY.md` §8.
- 테스트 `test_textbook_p2_20261015.py` 5건, `test_risk_auxiliary_amplifiers` 16항목.

### event_engine/transit_ten_god_branching.json `yearly_ten_god_signal_rules` — 세운 육신별 사건 신호 5계열 (2026-10-15, 외부 교재 6장 대조)

- 교재 6장 '세운 육신별 사건표'(비겁·재성·관성·인성·식상년)를 브랜처 단일 운 규칙 10종·조합 규칙과 대조한 결과 대부분은 이미 대응(겁재=손재·분쟁, 재성=재물·계약·혼인, 관성=취업·승진·소송, 인성=문서·학업, 식상=표현·직업 전환). 우리 규칙에 없던 5계열만 보조 규칙으로 — 값은 초기 설계값·감수 대상.
  ① `JIECAI_RESTRAINED_BY_OFFICER`: 겁재 운(세운·월운)인데 원국 천간·지지 본기 또는 대운에 관살이 있으면 겁재 단독 규칙(SINGLE_JIECAI)에서 나온 분쟁·손재 후보 ×0.85(제거 아님). ② `SAME_GOD_HAP_{PEER|AUTHORITY|WEALTH}`: 운 천간이 원국 천간과 천간합을 이루면 비겁=관계 변화·분쟁 +2, 관성=결혼 신호·관계 변화 +2(부정 주의·성사 양면), 재성=결혼 신호 +2(초안 +4 → 85사례 재생에서 결혼 신호 1위 150→347 급증이라 +2로 하향: 271, 적중 동일). ③ `RESOURCE_WEALTH_HAP_SPECULATION`: 인성 운 천간이 원국 재성 천간과 합 → windfall +6(없으면 30 시드; 횡재 가드 유지). ④ `OFFICER_YEAR_RELOCATION`: 관성 세운에 relocation 후보가 없으면 26 시드. ⑤ `OUTPUT_YEAR_RELATIONSHIP_CHANGE`: 식상 세운에 relationship_change 후보가 없으면 30 시드. 시드 극성은 뒤 계층 `_period_role` 이 덮어쓴다.
- 구현 `saju_engines.yearly_ten_god_signals`(브랜처·시드 합류 직후, 성별 가중 앞), `EventEngineV2(enable_yearly_ten_god_signals)`, 플래그 `SAJU_YEARLY_TEN_GOD_SIGNALS_ENABLED`(기본 ON). 한글 라벨 5종(`llm_event_serializer`). `scripts/casebook_replay.py --no-yearly-signals`로 OFF 재생.
- ON/OFF 는 점수 규칙이므로 **85사례·실사례 적중률**로 정한다(데굴님 2026-10-15 정정): 재생 결과는 WORKLOG. 테스트 `test_yearly_ten_god_signals.py` 6건(규칙 로드·세운 전용 시드 / OFF 불변 / 관살 유무별 겁재 완화 / 관합 가중 / 세운 시드 '없을 때만' / 한글 라벨).

### 외부 교재 대조 P1 문구층 4종 + 육친표·유익형 근거 (2026-10-15 데굴님 '적용 후 감수' — 전부 노출)

- `interpretations/relation_palace_pairs_text.json`(신규): 원국 **충·파·해**가 서로 다른 두 궁위 사이에 성립할 때 '어느 자리끼리'의 육친 서사 — kind 3 × pair 6(연-월·연-일·연-시·월-일·월-시·일-시) = 18문장(교재 2장 위치별 해석을 '긴장·거리·과제' 어휘로 번역). `chart_interpretation._relation_palace_pairs` → 발췌 `kind=relation_palace`, key "충 월주-시주(亥·巳)". 같은 (kind, pair)는 1회. lint: 18칸 정확 커버리지·단정 금지.
- `interpretations/void_ten_god_text.json`(신규): 원국 공망 글자(연·월·시지)의 **본기 십성별** 서사 10문장(교재 4장 공망 육신 해석 번역). 발췌 `kind=void_ten_god`, key "공망 巳(시주 정인)". 공망 활성(충발·전실·합) 의미론은 기존 그대로(`GONGMANG_HAP_SEMANTICS`). lint: 10십성 커버리지·단정 금지.
- `health_element_organs.json`: `stems`(10)·`branches`(12) 신체 **부위**와 `clash_pairs`(오행 상전 5쌍 **계열**) 추가 — 질병명은 싣지 않는다(교재의 암·중풍 등은 번역 시 제외, 테스트로 금지어 고정). `structural_context._health_letter_lines`가 취약 오행에 속한 원국 글자의 부위(최대 4)와 상전 계열을 [원국 건강 취약 구조] 블록에 덧붙인다(취약 장기가 없으면 침묵).
- `career_fields.json` `conditions`(11종): 격국·신살 조건층(의약=현침 희용신, 법조=寅巳申·丑戌未 형 희용신, 교육=丙/火, 역술·종교=丙丁·寅午戌·辰戌巳亥, 언론=丁/비겁 강, 기계=金, 중개=土·水, 군경=戊庚壬·형·辰戌巳亥, 운수=희용신 충, 의류=木+辰戌 충, 해운·요식=水+식상 강). `career_field._evaluate_conditions`가 원국 사실(글자·상호작용·용기신 역할·십성군 %)로 판정해 근거 문자열과 함께 `facts.conditions` 로 싣고, 블록에 "[격국·신살 조건 — 보조 신호(단독 확정 금지)]"로 렌더. `ConditionRule`/`ConditionHit` 타입.
- `interpretations/ten_god_relations.json` 1.0.2: 교재 4장 육친표 누락 칸 — 여명 재성=시어머니, 남명 식신=장인·장모, 남명 편관=조부(자녀와 병기), 남명 정인=장모(어머니와 병기). 가족 칸은 관계 질문에서만 쓰는 정책 불변.
- `favorable_role_tiering.literature_basis`: 교재 사길신/사흉신/중성 분류를 유익형 목록의 문헌 근거로 기록(중성 비견·편재는 유익형 최소).
- 테스트 `test_text_layers_20261015.py`(위치 쌍 실사례 월-시 충·중복 없음 / 공망 시지 巳 발췌·무공망 명식 침묵 / 질병 부위 사전·금지어·취약 오행 정합 / 직업 조건 사전·판정·렌더·실사례 土 중개), `test_agent_relations` 갱신.

### event_engine/transit_ten_god_branching.json `peer_gisin_mobility_rules` + 유익형 근거 코드 (2026-10-15 데굴님 확정)

- 유익·불익의 기준(데굴님): 이동이 자발인가 타의인가가 아니라 **이동 뒤 흐름이 좋은가**. 떠밀려 나가도 그 덕에 맞는 자리로 가면 복이 될 수 있고, 스스로 택해도 화가 될 수 있다. 주체는 미상(`[이동 주체 미상]` 지시문)으로 두고, 흐름은 용신·기신이 정한다.
- 유익형 편입: `favorable_role_tiering.favorable_reason_prefixes = ["PEER_YONGSIN_MOBILITY"]` — 비겁 용신 이동 시드는 사건 키(career_change)로는 흉형과 구분되지 않아 **근거 코드**로 유익형을 인정한다(`FavorableTieringRule.is_favorable(..., reason_codes)`). 모드 a 에서 실사례 2026-10 이동 후보 66→73(순위 2위 유지). 품질은 '기회 가능성'이지 결과 확정이 아니며 문구도 "나쁘지 않게 흐를 수 있다"까지만.
- 기신 대칭 시드 `peer_gisin_mobility_rules`(id `PEER_GISIN_MOBILITY`, `favorability_any: ["기신"]`, 그 외 용신 절과 동일 — 층 세운·월운, 기준점 same_god 68·same_group 58·stem_only 50·branch_only 44): 비겁이 기신인 명식에 비겁 운이 들어오면 경쟁·분탈 압박 속의 이동(불익) 후보. 극성 자리표시 GI, 길흉은 뒤 계층 기신 품질 반전(압박·손실·충돌). 해석 문구 `transit_peer_mobility_text.json` `peer_gisin_mobility`(4 id 정확 커버리지로 lint 갱신), `event_process_types.json` '이동·교체·재편' reason_prefixes 에 등록. 구현 `peer_mobility_seed.load_peer_mobility_rule(dicts, GISIN_SECTION)` + `EventEngineV2(enable_peer_gisin_mobility)`, 플래그 `SAJU_PEER_GISIN_MOBILITY_ENABLED`(기본 ON). 실사례 없음 — 85사례 재생에서 시점 있는 outcome 적중 23/오탐 8 불변, 연도 top-1 career_change 3957→4050·social_conflict 107→95(분포만 이동).
- 검증 픽스처: 1985-05-20 10:00 서울 남(己未 일주, 土=기신) — 2026-10 戊戌(겁재·겁재)에 PEER_GISIN_MOBILITY·PEER_INFLOW_SAME_GOD 후보, 용신 실사례(1980-11-22)에는 기신 시드 없음, 한신·희신·구신 비겁은 문구 침묵.

### event_engine/transit_ten_god_branching.json `role_event_seed_rules` + interpretations/transit_role_event_text.json — 역할별 사건 전환 (2026-10-16 데굴님 확정 6규칙)

- 배경: 사건 종류는 십성 단일 운 규칙이 정하고 용·기신은 배율·품질만 바꾼다(2026-06-16 분리 원칙). 그래서 사흉신(상관·편관·편인)이 **용신**인 명식의 그 십성 운은 흉성 기본 가지(충돌·이탈 / 압박 / 보류)에 용신 배율만 붙고, 사길신(정관·정인·식신)이 **기신**인 명식의 그 운은 길성 기본 가지(취업 / 문서 / 성과)에 압박 품질만 붙어 사건 종류가 현실과 어긋났다. 비겁 이동 시드에 이은 **두 번째 예외**이며, 브랜처 기본 가지는 바꾸지 않고(브랜처는 favorability 를 모르는 채 유지) 같은 자리(브랜처 직후 합류)에서 역할별 사건 후보를 시드로 더해 **순위로** 전환한다.
- 규칙 6종(`rules[]`, 규칙별 `enabled`): 상관 용신 → creative_output·public_exposure / 편관 용신 → job_gain·promotion / 편인 용신 → education_admission·creative_output / 정관 기신 → career_change / 정인 기신 → preparation_delay / 식신 기신 → health_attention·wealth_change. 역할 판정은 **유입 십성의 오행**(일간 기준 십성군 → 오행, `role_event_seed.incoming_element`)이 fav_map 에서 용신/기신인가로 한다 — 상관·식신은 같은 오행이라 "상관 용신"은 식상 오행이 용신이고 들어온 십성이 상관인 경우다.
- 기준점·강도: 비겁 시드와 같은 유입 4단계(`base_by_inflow` same_god 68·same_group 58·stem_only 50·branch_only 44), 둘째 사건은 `secondary_ratio`(0.85). 근거 코드 `ROLE_SEED_<십성>_<YONG|GI>` + `ROLE_INFLOW_*` + `ROLE_UPPER_SUPPORT_<layer>`(상위 층 같은 십성 뿌리), 기여 키 `role_event_seed`(비겁 시드 기여와 별도 보존). 극성 자리표시는 용신 규칙 YONG·기신 규칙 GI(뒤 계층 `_period_role` 이 덮어쓴다). 용신 규칙 3종의 사건은 `favorable_role_tiering` 유익형 목록에 이미 있어 품질군 차등 모드에서도 유익형이다.
- 문구층(항상 노출): `transit_role_event_text.json` 6항목((십성, 역할) → text, `RoleEventTextFile` 6 id 정확 커버리지·id↔십성×역할 일치·단정 어휘 lint). `incoming_ten_god_note` 가 운 천간·지지 십성 각각의 (십성, 역할)이 사전에 있으면 1회 부착 — 채팅·리포트 공용 직렬화라 두 입구에 같이 나간다. 사길신 용신·사흉신 기신은 대상이 아니다(기본 가지가 맞다).
- 점수층: `saju_engines.role_event_seed`(`load_role_event_seed_config`·`produce_role_event_seeds`·`merge_role_event_seeds`), `EventEngineV2(enable_role_event_seed, role_event_seed_rule_ids)`, 플래그 `SAJU_ROLE_EVENT_SEED_ENABLED`(코드 기본 OFF — 회귀 기준선, 운영은 `.env.beta` 로 ON), health `role_event_seed_enabled`, `casebook_replay --role-event-seed [--role-seed-only RULE_ID]`, 한글 라벨 11종.
- 측정(2026-10-16, 85사례 180명식 같은 셸 off/on, 시점 있는 outcome 44건 상위 노출 적중·방향 오탐 |fav|≥0.1): **적중 23/오탐 8 → 23/8 불변**, 재물 '-' 2건의 fav 가 실제 방향으로 이동(CASE-023 R −0.0→−0.05, CASE-042 L −0.04→−0.11). 연도 top-1 분포: career_change 4197→4149·contract 2429→2384 감소, creative_output 2068→2112·education_admission 226→256·health_attention 197→235·preparation_delay 898→913 증가. 적중 하락 없음 → 데굴님 기준(점수 규칙은 적중률)상 ON 가능해 운영 노출·실답 감수. 규칙별 분리 측정은 합산이 무손실이라 85사례로는 변별이 없어 생략(`--role-seed-only` 로 재현 가능). 현대 실사례(`life_event_cases.jsonl`)는 아직 0건 — 규칙당 1건 등록이 후속.
- 검증 픽스처(전부 2026-10 戊戌 = 土 간여지동): 1978-09-02 남 丁(상관 용신) / 1978-10-27 남 壬(편관 용신) / 1978-06-17 남 庚(편인 용신) / 1979-02-25 남 癸(정관 기신) / 1978-10-16 남 辛(정인 기신) / 1978-01-14 14:30 여 丙(식신 기신). 두 사전 절 모두 reviewed:false.

### career_fields.json 간지론 번역층 7절 + sinsal_direction.json `entrance_customer_group` (2026-10-16 데굴님 승인 — 외부 강의 「제2강 직업선택」)

- 출처: 간지론 기반 외부 강의. 전부 **학파 서술층**(서술 전용·inert)이며 렌더는 '[간지론 관점]' 머리말 + "간지론에서는 ~로 본다" 어투를 강제한다(데굴님 2026-10-16: 이번 내용 전체가 간지론 기반이라 학파 표기로 서술). 억부·조후 용신 판정과 합산·상쇄하지 않고 나란히 둔다. 선택 절이라 없으면 층이 꺼진다(`CareerFieldDict` 필드 전부 `None` 허용).
- `ganji_school`(라벨·어투) / `orientation`(직업 유형 축: 관·인=직장형 vs 식·재=상업형, 월지 2·월간 1·년주 0.5·일지 0.5·시주 0.25 가중, 분포 10%p 차 +1, 월지 충 −1, 여유폭 1.5 — 교재에 수치가 없어 초기 설계값) / `palace_priority`(월지→월간→년주→일지, 근묘화실 사용 시기) / `officer_position`(관성 천간 통근·무근·지지만, 정관·편관, 관인 인접=책임자형, 관 유 인 무, 대운 인성 대체, 관성 多 — '서울/지방'은 지역 단정이라 '조직 격·규모'로 번역) / `workplace_notes`(인성 과다) / `business_types`(식신 천간·지지, 상관, 정재, 편재, 정인, 편인, 겁재·양인 — 유흥주점·사채·전당포·기획부동산 제외, 상위 3칸만 렌더) / `business_rules`(식상·재성 인접/떨어짐, 재성만, 정관 강+재성, 비겁 多+관성, 비겁 지지 無, 인성 無=임대, 재성 오행) / `business_timing`(인성 대운이 식상을 누르면 운영·위임형, 식·재 대운, 대운>세운).
- 구현 `career_field._apply_ganji_school`(기준일 `today`로 현재 대운 사용 — 채팅·리포트가 전달) → `CareerFieldFacts.orientation/palace_lines/officer_lines/workplace_lines/business_lines/timing_lines` → `_render_ganji_school`. 업종·사업 시기는 상업형·혼합형에만, 관성 위치는 관성이 있을 때만. 지시문(`_CAREER_FIELD_DIRECTIVE`·`_CAREER_FIELD_REPORT_DIRECTIVE`)에 학파 서술·합산 금지·프로필 우선 규칙 추가. 2단계 프로필 직업이 있으면 그것이 사실(원칙 11).
- `sinsal_direction.json` `entrance_customer_group`: 출입구 제2기준(간지론) — 연지 삼합의 '앞 그룹'(각 지지 +3: 申子辰→亥卯未·寅午戌→巳酉丑·巳酉丑→申子辰·亥卯未→寅午戌)을 손님으로 보고 그 국 왕지 방위(동/서/북/남)로 출입문. 목적 `sales` 에만 `SinsalDirectionRecommendation.second_basis` 로 붙고 12신살 picks 와 합산하지 않는다(쥐띠: 12신살 지살=서 vs 간지론=동 — 학파별 병기). 조상·단골 쪽문 해석 불채택. 스냅샷 `compiled/sinsal_direction_v1.2.0.json` in-place 재빌드(선택 절 추가, 기존 항목 불변).
- 테스트 `test_career_ganji_layer.py`(사전 7절·어휘 정책·선택 절 부재·유형 축 5픽스처·월지 가중/충 간섭·대운 축·궁위·관성 위치 3형·업종 상한·사업 시기 2형·정관 규칙·렌더·지시문) / `test_entrance_second_basis.py`(사전·4삼합 표·12신살 불변·sales 전용·렌더 1회). 픽스처 1976-01-05(직장형·천간 통근·관인 인접) / 1976-01-19(직장형·지지만) / 1976-03-22(혼합형) / 1976-01-26(상업형·인성 대운) / 1980-11-22(상업형·월지 충).

### interpretations/love_types.json — 연애 유형 5종 (2026-10-25 데굴님 승인 — 외부 강의 「연애운 셀프 리딩 2탄」, doc/v2_2/EXTERNAL_TEXT_GAP_LOVE_TIMING.md P2-6)

- 구조: `items` 5건(group 비겁·식상·재성·관성·인성 × tenGods·meaning·psychology·wants·approach·caution·absent·basis·reviewed). `absent` 는 해당 군 미투출 시 결(관성·재성·식상만, 비겁·인성은 빈 문자열 — 강의에 없음).
- 판정은 엔진 `saju_engines.love_type.classify_love_type`: ① 같은 군 가시(천간+지지 본기) ≥3(둘이면 많은 쪽 주·다음 부) → ② 간여지동 기둥(월·일·시·연 순, ①과 다른 군이면 부 유형) → ③ 월지 본기(만 50세 이하) / 일지 본기(51세+) — 강의의 20~37/38+ 는 **100세 밴드**(`time_parser.LIFE_STAGE_AGE_RANGES`, 2026-08-07 확정)로 번역, 나이 미상이면 월지 + 일지 전환 안내. 나이는 호출처(채팅 `_structural_context`·리포트 `ReportData`)가 `age_from_result(result, today)`로 넘긴다.
- 노출: `structural_context.marriage_resource_lines` 끝 `[연애 유형 — …]` 블록(채팅 관계·총운 도메인, 리포트 결혼 자원 블록 R-02/RP-02 등 공용). 문구는 기본 노출(reviewed 는 노출 조건 아님, 검수는 실답으로).
- 린트(`_lint_love_types`): 5군 정확 커버리지·소속 십성 정합·금지 어휘(외도·바람·바람둥이·과부·반드시·확정). 강의 원문의 외도·성욕 어휘는 신뢰·욕구 어휘로 바꿨다.
- 같은 날 결혼 자원(`MarriageResourceProfile`)에 추가된 서술 필드(P2-2~P2-7: 정/편 축·혼재, 배우자성 자리 천간=지향·지지=환경, 간여지동 배우자성, 연상/동갑/연하 경향, 무재·무관 어휘, 만혼·비혼 중립·비겁 과다)와 궁합 `PEER_EXCESS` 보조 신호는 사전 없이 코드 라벨이다.

### interpretations/yearly_environment.json — 세운 환경 '월주 상대 관점' (2026-10-25 데굴님 승인 — 외부 강의 별의당 「운명의 병오년」)

- 출처·대조: `doc/v2_2/EXTERNAL_TEXT_GAP_BYEOLUIDANG_YEARLY_ENV.md`. 세운을 두 방향으로 읽는다 — ①**환경** = 월주(명주가 살아가는 환경) ↔ 세운의 상대 기운, ②**태도** = 일간 기준 세운 십성·12운성(기존 `[세운:]` 줄). 이 사전은 ①의 어휘만 담는 **학파 서술층**(서술 전용·inert)이며 렌더는 '[월주 상대 관점]' 머리말 + "월주와 세운의 상대 기운으로 보면 ~" 어투를 강제한다(간지론 층과 같은 규약). 길흉·유불리는 일간 기준 용희기구한 판정이 정하고 이 층은 점수·후보·역할에 관여하지 않는다. **세운 전용**(대운·월운 미적용 — 데굴님 결정).
- 사실 계산(`saju_engines.yearly_environment.build_yearly_environment`, 신규 명리 규칙 없음 — 기존 순수 함수 재사용): 월간 기준 세운 천간·지지(본기) 십성 + 세운 지지 12운성(`twelve_unseong(월간, 세운지지)`) / 세운 천간 기준 월간·월지(본기) 십성 + 월지 12운성 / 세운 지지 ↔ 월지 두 글자 관계(충·육합·반합(왕지 포함)·삼합 부분·방합 부분·형·자형·파·해 — 원국 다른 자리까지 끄는 삼합 완성·삼형은 기존 grounding 담당) / 세운 천간 ↔ 월간 천간합·천간충 / 통근 비교(세운 천간·월간이 {월지, 세운 지지} 지장간(본기·중기·여기)에 동오행 뿌리). 강의 사례 재현: 壬寅 월주 × 丙午 → 壬에게 丙 편재·午 정재·胎 / 丙에게 壬 편관·寅 편인·長生 / 寅午 반합 / 丙壬충 / 丙 寅○午○·壬 寅×午×.
- 사전 절: `label`·`narration` / `tenGodEnv[10]`(forward=시절이 환경에 들여오는 것, reverse=환경이 시절에게 어떤 자리인가) / `stageEnv[12]`(hanja 포함 상태 어휘 — 목욕=호기심·의외성, 건록=존재감 확립, 사=집중·몰입) / `relationEnv`(12키: stem_clash=긴장·관문(소멸 아님)…none) / `rootingEnv`(4상태 luck_only·both·month_only·neither) / `synthesis`(환경 한 문장 → 태도 한 문장 → 한 해 주제 합성 지시 + "비겁 운 = 무조건 극재 아님"). `YearlyEnvironmentFile` + `_lint_yearly_environment`(십성 10·운성 12 정확 커버리지, 관계/통근 키 집합, 단정 어휘). reviewed:false.
- 배선: 채팅 '해당 연 총운'(`PeriodFortune.environment_lines`, `[세운:]`·운 요약 줄 뒤) + 리포트 F-11·Y-04(`_ReportData.yearly_sewoon_block` — 채팅 패리티로 `build_luck_grounding` 세운 줄·형충회합·신살·공망까지 함께 신설). `_YEARLY_INSTRUCTION` 에 환경→태도→주제 순서 지시. 같은 날 어휘 보강: 겁재 `incoming`/`asYongsin`(존재감 확립·영역 개척 결), 목욕 `incoming`(호기심·의외성), 건록 `incoming`(존재감 확립). 회귀 `tests/unit/test_yearly_environment.py`.

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
