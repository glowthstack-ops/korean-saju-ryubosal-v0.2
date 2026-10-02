# 13. 구조 패턴(Structure Pattern) 계층 설계 — P0 초안

> 상태: **초안(draft) — 미승인**. 이 문서는 코드/사전 생성 전 사용자 확정을 위한 설계안이다.
> 근거 자료: 사용자 제공 "명리 구조 용어 카탈로그"(§1~15). 개발 순서는 `07_ROADMAP_TASKS.md`에 편입 예정.

## 0. 목적과 위치

십성 간 **관계 구조 라벨**(식신생재·상관견관·재극인·관인상생 등)을 **일관된 Pattern 객체로 감지·명명하고, 압축 설명 태그로 LLM에 공급**하는 얇은 계층을 신설한다.

- **새 판정 엔진이 아니다.** 감지의 원재료(파격 8종, 합화 판정, 용신·operability, 십성 분포, 관계 그래프)는 이미 `manse_analysis`/`saju_engines`에 존재한다. 이 계층은 그 결과를 **표준 pattern_id로 재라벨링(어댑터)** 하고, 부족한 관계만 신규 감지한다.
- **왜 필요한가**: 현재 관계 라벨이 `exam_outcome_patterns.json`(시험 도메인) 등에 파편적으로 갇혀 있어 재사용·일관성이 없다. 도메인 무관한 단일 사전으로 승격한다.

### 준수 원칙 (CLAUDE.md)

- **원칙 1·4**: 패턴 성립·강도·길흉은 코드가 계산한다. LLM은 압축 설명만 자연어화(`llm_usage: "explanation_tag_only"`).
- **원칙 2**: 전체 사전 투입 금지. 감지된 패턴만 발췌해 LLM 입력에 넣는다.
- **원칙 3·8**: 패턴은 사건·승부 확정어가 아니다. 도메인 후보(`domain_hints`)와 방향 모드(`polarity_mode`)로만 표현.
- **자료 §14 핵심**: 패턴 ≠ 사건 확정. `관인상생 ≠ 취업 확정`. 도메인 힌트로만.

## 1. 아키텍처 (3단계)

```
[감지 원재료] (기존)                     [신규 계층]                    [출력]
GeokgukEvaluation.failures[]  ──┐
StructureAnalysis(합화)         ──┤
AggregatedYongsinResult         ──┼──► pattern_detector  ──► DetectedPattern[]  ──► LLM 입력
십성 분포 / TenGodPair          ──┤    (순수 함수, 어댑터)      + structure_patterns.json     (chartInterpretation
관계 그래프(합충형파해)         ──┘                              (압축 설명·domain_hints)        .detected_patterns[])
```

1. **`structure_patterns.json`** (신규 사전) — 패턴 정의 + 압축 설명. families 9종.
2. **`pattern_detector`** (신규 순수 함수) — `(구조분석, 격국, 용신, 십성분포, 관계그래프) → List[DetectedPattern]`.
3. **LLM 입력 계약 확장** — `chartInterpretation.detected_patterns[]` (docs/06 §12).

## 2. families (자료 §15)

| family | 의미 | 대표 |
|---|---|---|
| `generation_flow` | 기운이 한 방향으로 이어짐 | 식신생재, 관인상생 |
| `mediation` | 극·충을 중간 오행/십성이 통관 | 살인상생, 관인상생 |
| `control` | 흉·강한 압박을 제어 | 식신제살, 관살유제 |
| `conflict` | 한 십성이 다른 십성을 깸 | 상관견관, 재극인 |
| `overload` | 특정 십성 과다/혼잡 | 재다신약, 관살혼잡 |
| `combination_clash` | 운에서 사건 발동 방식 | 합거, 충개, 입묘 |
| `geguk` | 사주 전체 구조명 | 정관격, 종재격 |
| `element_image` | 오행 조합 물상·조후 | (P1) 목화통명 |
| `mixed_structure` | 정·편 혼재 | 관살혼잡(중복 소속 허용) |

## 3. 사전 스키마 — `dictionaries/structure_patterns.json`

기존 `exam_outcome_patterns.json` 헤더 관례(`schema`/`reviewed`/`purpose`)와 십성 로마자 enum(`ZHENGGUAN`, `QISHA` 등)을 따른다.

```jsonc
{
  "schema": "structure_patterns.v1",
  "reviewed": false,
  "purpose": "십성 관계 구조 라벨을 도메인 무관 단일 사전으로 정의. 감지 강도는 엔진이 계산하고, 여기서는 정의·압축설명·도메인힌트·방향모드만 둔다. 사건·길흉 확정 금지(자료 §14, 절대원칙 1·3·4).",
  "polarity_modes": ["favorable", "unfavorable", "depends_on_yonggi_and_control", "context_only"],
  "patterns": [
    {
      "pattern_id": "GWAN_IN_SANGSAENG",
      "name_ko": "관인상생",
      "name_hanja": "官印相生",
      "family": ["generation_flow", "mediation"],
      "structure": "authority -> resource -> day_master",
      "ten_god_chain": ["ZHENGGUAN", "ZHENGYIN"],
      "evidence": ["관성 존재", "인성 존재", "관→인 상생 접촉(천간/지지)", "인→일간 연결", "월령/투간/통근 중 1+ 활성"],
      "domain_hints": ["career_stability", "license_exam", "promotion", "contract_support"],
      "polarity_mode": "depends_on_yonggi_and_control",
      "severity_inputs": ["신강약", "용기신", "월령", "투간", "통근", "합충", "공망", "operability"],
      "detector_source": "adapter:yongsin.resource_model + relation_graph",
      "llm_usage": "explanation_tag_only",
      "llm_tag": "관인상생: 직장·제도·직책이 자격·문서·후견을 통해 나를 돕는 통관 구조"
    }
    // ... P0 전체 (아래 §5 목록)
  ]
}
```

**필드 규격**
- `pattern_id`: 로마자 대문자 스네이크. `exam_outcome_patterns`의 한글 `pattern` 키와 매핑 테이블 유지(중복 정의 방지).
- `structure`: 십성 그룹(peer/output/wealth/authority/resource) 기준 정규화 관계식. `->` 상생, `X` 극.
- `polarity_mode`: **길흉을 사전이 확정하지 않는다.** 엔진이 용신/operability로 최종 방향 부여.
- `detector_source`: `adapter:<기존 감지기>` 또는 `new:<신규 규칙>`. 재사용 여부를 명시해 중복 구현 차단.
- `llm_tag`: 자료 §14-5의 1:1 압축 설명 문자열. LLM에 그대로 전달.

## 4. 감지기 — `pattern_detector` (신규 순수 함수)

```python
def detect_structure_patterns(
    structure: StructureAnalysis,       # 합충형파해 + 합화 판정
    geokguk: GeokgukResult,             # failures[](파격 8종) + special_pattern
    yongsin: AggregatedYongsinResult,   # 용기신 역할 + operability
    ten_god_dist: TenGodDistribution,   # 십성 분포/과다
    relations: list[RelationEdge],      # 원국+운 관계 그래프
    patterns_dict: StructurePatternDict,
) -> list[DetectedPattern]:
    """구조 패턴 감지. 순수 함수 (input, dict) -> output. 길흉 미확정."""
```

`DetectedPattern` (shared_types 신규):

```python
class DetectedPattern(BaseModel):
    pattern_id: str
    name_ko: str
    strength: float          # 0~1 성립 강도(월령·투간·통근·위치·합충·공망·운반복)
    polarity: EventPolarity  # 엔진이 용기신/operability 참조해 부여 (사전 아님)
    scope: Literal["natal", "luck", "natal_luck"]
    evidence_refs: list[str] # 근거 글자/관계 id (Graph RAG 경로와 연결)
    llm_tag: str             # 사전에서 승계
```

**어댑터 매핑 (기존 감지기 재사용 — 신규 구현 최소화)**

| pattern_id | detector_source | 기존 감지 위치 |
|---|---|---|
| SANGGWAN_GYEONGWAN(상관견관) | adapter | `geokguk_eval._detect_failures` → `shangguan_attacks_officer` |
| GWANSAL_HONJAP(관살혼잡) | adapter | 동 → `mixed_officer_killing` |
| GWANDA_SINYAK(관다신약) | adapter | 동 → `killing_overwhelms_weak` |
| JAEDA_SINYAK(재다신약) | adapter | 동 → `wealth_overwhelms_weak` + `yongsin._jaeda_sinyak` |
| PYEONIN_DOSIK(편인도식) | adapter | 동 → `pyeonin_dosik` |
| GUNGEOP_JAENGJAE(군겁쟁재) | adapter | 동 → `bigyeob_jaengjae` |
| SIKSIN_JESAL(식신제살) | adapter | `yongsin._DAMAGE_REPAIR` → output remedy |
| 합거/합반/충동/충개/입묘/개고 | adapter | `hap_lines`, `relations.py`, `wealth_capacity`(충개고), `structural_context`(입묘) |
| 격국 P0 8종 | adapter | `GeokgukResult.main_structure` / `special_pattern` |
| 식신생재/상관생재/식상생재/재생관/관인상생/살인상생/재생살 | **일부 new** | 관계그래프에서 십성 상생 접촉 신규 감지(exam 사전 로직 일반화) |
| 관살유제/관살무제/인다신약/비겁탈재 | **일부 new** | 제어 성립 여부·인성 과다·비겁의 재 탈취 신규 규칙 |

## 5. P0 패턴 카탈로그 (자료 §13 P0 전체)

성립 조건은 §4 severity_inputs로 강도화한다. 방향은 전부 엔진 판정(사전 확정 금지).

- **생흐름(generation_flow)**: 식신생재(SIKSIN_SAENGJAE), 상관생재(SANGGWAN_SAENGJAE), 식상생재(SIKSANG_SAENGJAE), 재생관(JAE_SAENGGWAN), 관인상생(GWAN_IN_SANGSAENG), 살인상생(SAL_IN_SANGSAENG)
- **제어(control)**: 식신제살(SIKSIN_JESAL), 상관제살(SANGGWAN_JESAL), 관살유제(GWANSAL_YUJE), 관살무제(GWANSAL_MUJE)
- **충돌(conflict)**: 상관견관(SANGGWAN_GYEONGWAN), 재극인(JAE_GEUGIN), 편인도식(PYEONIN_DOSIK), 군겁쟁재(GUNGEOP_JAENGJAE), 비겁탈재(BIGEOP_TALJAE), 재생살(JAE_SAENGSAL)
- **과다(overload)**: 재다신약(JAEDA_SINYAK), 관다신약(GWANDA_SINYAK), 인다신약(INDA_SINYAK), 관살혼잡(GWANSAL_HONJAP)
- **합충(combination_clash)**: 합래(HAPRAE), 합거(HAPGEO), 합반(HAPBAN), 충동(CHUNGDONG), 충개(CHUNGGAE), 입묘(IPMYO), 개고(GAEGO)
- **격국(geguk)**: 정관격, 칠살격, 식신격, 상관격, 정인격, 편인격, 종재격, 종살격

> 재생살은 자료 §4에서 흉 계열이나 "돈 때문에 망한다"가 아니라 **목표·금전 부담을 감당할 보조성 부족**으로 안전 표현(자료 §4 주). polarity_mode=`depends_on_yonggi_and_control`.

## 6. LLM 입력 계약 확장 (docs/06 §12) — 구현 반영

`ChartInterpretation.detected_patterns: list[DetectedPattern]` 추가(전체 사전 금지, 감지분만).

**배치(F1 개정)**: `ChartInterpretation`은 바이트 단위 동일해야 하는 **캐시 프리픽스**라 질문 도메인 필터를 넣을 수 없다. 따라서 detected_patterns는 `LlmInput.detected_patterns`(**질문 가변 필드**)로 두고 `serialize_llm_input`의 **suffix**([기준 시점] 이하, [근거 경로] 직전)에 직렬화한다. 이로써 도메인 필터가 실제로 동작하며 프리픽스 캐시는 그대로 보존된다.

- `select_llm_patterns(all, domains=None, max_count=6)`: `domains`(질문 도메인의 EventKeyV2 집합)가 겹치는 패턴을 앞으로 정렬(soft filter — 매칭이 6개 미만이면 strength 순으로 채워 빈 목록 방지). `domains=None`(일반 질문)이면 strength desc.
- 도메인 매핑: `context_reducer._DOMAIN_EVENT_KEYS` (Domain enum career/wealth/… → EventKeyV2 집합). `build_llm_input`이 `intent.domains`에서 집합을 만들어 선별.
- 내부 전체 감지(`detect_structure_patterns`)는 보존, LLM 노출은 상위 6개만(내부/노출 분리).
- 직렬화: `_append_structure_patterns`가 suffix에 `[구조 패턴 — 설명 태그]` 블록(토큰 가드 후순위). llm_tag만 노출.
- 지시: `_STRUCTURE_PATTERN_INSTRUCTION`(감지분 있을 때만) — "구조 라벨일 뿐 사건·길흉 확정 아님".

**소비 경로(2곳 모두 배선)**:
- **AI 채팅 상담**(`chat_service`→`build_llm_input`): 질문 도메인으로 필터한 상위 6개를 suffix에.
- **테마 사주/리포트 상품**(`report_service.build_section_context`): 섹션별 주입 — 원국 섹션은 도메인 무관 상위 N, 도메인 섹션(`_SECTION_DOMAIN`)은 해당 도메인 우선 선별. 과거·메타 섹션은 생략(반복 방지). `_ReportData.detected_patterns`에 1회 감지 후 섹션마다 `select_llm_patterns`. (주의: F1에서 프리픽스→suffix 이전 시 리포트가 `serialize_chart_prefix`만 써 누락됐던 것을 이때 배선.)

## 7. 파이프라인·검증 (CLAUDE.md 원칙 5)

1. `structure_patterns.json` 작성 → `scripts/validate_dictionaries` 스키마·중복 pattern_id·enum 검증.
2. `compile` 스냅샷(`compiled/structure_patterns_v1.0.0.json`).
3. 회귀 픽스처: `tests/fixtures`의 명식에서 예상 pattern_id 집합 검증. 2025-08 회귀 케이스(정관합 단독 단정 금지) 포함.
4. `pytest` + `ruff` + `mypy` clean.

## 8. 확정 결정 (2026-07-02 사용자 승인)

1. **패턴 저장 위치** = `dictionaries/structure_patterns.json` (루트, 도메인 무관 공용 사전).
2. **exam_outcome_patterns.json 통합** = 관계/구조 패턴 정의는 structure_patterns로 **이관(중복 정의 금지)**. exam 사전에는 `pattern_id` 참조 + 시험 도메인 전용 `fav_delta`/`domain_usage`/`exam_specific_notes`만 남긴다.
3. **strength 공식** = 격국 `score_candidate`의 7인자 재사용. **단 strength는 "패턴 성립 강도"로만 사용** — favorability/confidence/길흉을 직접 바꾸지 않는다. 길흉은 기존 용신/기신/operability 계층에서만 부여.
4. **detected_patterns 상한** = 기본 6개 + 질문 도메인 필터. **내부 전체(`all_detected_patterns`)와 LLM 노출(`chartInterpretation.detected_patterns[]` 최대 6개)을 분리** — 회귀 검증(전체 보존)과 토큰 가드(6개) 동시 충족.

## 9. 불변 가드 (이번 작업 = explanation 강화용 inert 확장)

- `structure_patterns.json`은 **구조 사전이지 길흉 사전이 아니다**. `polarity_mode`는 두되 최종 길흉값을 사전에 고정하지 않는다.
- **기존 감지기 재사용 우선.** 신규 구현은 P0에서 정말 없는 패턴만 최소 구현(§4 "일부 new" 항목).
- **패턴 감지는 event label을 생성하지 않는다.** `domain_hints`(후보 힌트)만 제공. 예: `상관견관 → career_change 확정 금지`, `[career_change, contract_document, legal_conflict]` 후보만. `domain_hints` 값은 EventKeyV2(21종)에 정렬.
- `llm_tag`는 **120자 내외**. 토큰 가드에서 본문을 밀어내지 않도록 **후순위**로 처리(초과 시 우선 절삭 대상).
- **회귀 우선순위**: 기존 score/confidence/favorability/event_count **불변** 확인이 1순위. 본 작업은 새 설명 필드 추가일 뿐 기존 수치 파이프라인을 건드리지 않는다.

## 10. 진행 상태 (각 단계 독립 커밋) — 2026-07-02 완료

- [x] ① `structure_patterns.json` P0 35종 + 설계 문서.
- [x] ② `DetectedPattern` 타입 + `detect_structure_patterns()` 어댑터(+`select_llm_patterns`). 충개/입묘/개고는 묘고 신호 배선 필요 → 후속.
- [x] ③ validate(SCHEMA_BY_PATH+lint)/compile(compiled/structure_patterns_v1.0.0.json, 스냅샷 우선 로드) + 회귀 픽스처(3차트 감지 집합 고정).
- [x] ④ LLM 입력 배선: 최초 `ChartInterpretation.detected_patterns`(캐시 프리픽스)로 구현.
- [x] **F1(도메인 필터 실동작)**: `LlmInput.detected_patterns`(질문 가변)로 이전 + suffix 직렬화 + `_DOMAIN_EVENT_KEYS` 도메인 우선 선별. 프리픽스 캐시 보존, 재물↔직업 질문에서 노출/순서 상이(통합 테스트 검증). inert — 전체 green.

### 후속
- [x] **F2**: 충개(沖開)·입묘(入墓)·개고(開庫) 감지 — natal 구조 어댑터. 입묘=일간/식신 묘지 지지 존재(health_vulnerability), 충개=묘고 충 지지쌍(辰戌/丑未), 개고=동일 묘고 병존(wealth_capacity.storage_repeat). 운 activation 은 EventEngine 소관.
- [x] **F3**: P1/P2 패턴 확장 25종(사전 60종). 감지 어댑터/규칙:
  - 십성특화: 상관패인(상관+정인), 득비이재(재다신약+비겁), 살중용인/용식(killing 구제 파생), 탐재괴인(재과다+인 훼손)
  - 상태: 신왕재왕/재약(band 신강계 × 재성 강/약), 양인합살(양인격+편관)
  - 오행물상: 목화통명(木일간+火), 금수상관(金일간+水), 오행극제 7종(토다금매·수다목부·목다토붕·화다금삭·금다목절·토다수탁·수다화멸 — five_elements 과다/존재)
  - 합충: 쟁합·투합(resolve_stem_hap contend)
  - 격국: 전왕 5종(곡직·염상·가색·종혁·윤하 — special_pattern dominant), 종아격·종세격(follow)
  - JAE_GEUGIN(재극인) 감지 규칙도 이때 배선(P0 미방출 갭 해소). inert — 1308 passed.

- [x] **F4**: 미배선 P1/P2 7종 추가(사전 67종) + 버그 수정.
  - 상관용인(상관격+인성)·상관상진(상관격+관무)·제살태과(식상≫편관)·수화기제/미제(五行 水火 균형/불균형)
  - 합충병견(합+충 공존)·충중봉합(충·합 지지 공유) — `interactions.relation_type`
  - **버그 수정**: `relation_type`이 한글이 아니라 영문 enum(`clash`/`six_combination`/`three_harmony`/`stem_combination`/`directional`/…)임을 반영. 기존 P0 CHUNGDONG이 `"충" in rt`로 매칭 실패해 미발동하던 결함까지 해소.

- [x] **F5**: 잡기재관격(雜氣財官格) 추가(사전 68종). 월지 사고(辰戌丑未) 지장간에 재/관이 있으면 감지, 투간 시 강도 상향(미투간=개고 대기). `hidden_stems_for`+`ten_god`+투간 검사로 결정적 감지. context_only.

- [x] **F6(2026-09-17, 용어 감사 반영 — `doc/v2_2/STRUCTURE_TERMS_AUDIT_2026-09-17.md`)**: 신규 63종 + 별칭 19건(사전 154종, 스냅샷 v1.2.0). 데굴님 승인 "적용 조건을 정확히 정의해 풀이에 활용".
  - **별칭 필드** `aliases`(entry·DetectedPattern) + `DetectedPattern.llm_line`(= llm_tag + `[별칭: …]`, 별칭 없으면 바이트 동일). report_service·context_reducer 배선 교체. 린트: 별칭이 다른 패턴 정식 명칭과 충돌 금지.
  - **두 오행 배합 8종**(화토성자·토금육수·금백수청·수목청화·금목동량·목토소통·토수지소·화금주인): 일간 오행 × 상대 오행 존재(결핍 아님) + **일간 비신약**(약한 일간의 生은 설기) + 대응 과다 물상 미성립. 금백수청은 金/土/火 과다 없음(탁수·열조 배제), 목토소통·토수지소는 일간 오행 과다 또는 표면 30%+.
  - **과다 물상 13종**(목다화식·화다토초·금다수탁 / 목다수축·화다목분·토다화회·금다토변·수다금침 / 목견금결·토중목절·수다토류·화염수열·금다화식): 과다 오행 + 상대 '존재하되 약'(결핍 또는 표면 12% 미만). 기존 7종(존재만)과 임계가 다름. 목다화식 성립 시 목화통명 억제.
  - **조후 명칭 4종**: 한목향양(木일간·亥子丑월·火 존재, 투간 시 강도↑), 금한수랭(金/水일간·겨울·火 결핍), 화염토조(火/土일간·巳午未월·水 결핍), 천한지동(한습 부담+겨울+천간 火 부재).
  - **천간 비유 8종**(context_only, 강도 0.45): 등라계갑(乙일간+甲), 벽갑인정(丁·甲·庚 동시), 정화련금(丁·庚, 벽갑 미성립 시), 병화탈광(丁일간+丙), 갑목소토(甲+土 과다/25%+), 무토제수(戊+水 과다), 수탕기호(甲일간+水 과다+寅), 화치승룡(甲일간+火 과다+辰).
  - **십성 배합·균형 14종**: 관살제겁·재제효인(파격 구제 근거 파생), 재관인상생(재·관·인 병존+재극인 없음), 식상설수/인다용재/기식취인(용신 `final.selected_model` 어댑터 — 점수 불변), 거살유관/거관유살(관살 병존+편관/정관 합거), 재자약살(신강+편관 약+재), 신살양정(중화~신강, 관 세력/일간 세력 0.8~1.25, 제·화 존재), 재다생살(편관+재 30%+·신약), 인왕신왕(신강+인성 35%+), 신왕무의(신강+식재관 ≤15%), 살중제경(관살≥2, 1≤제·화<관살), 설기태과(신약+식상 35%+).
  - **작용 2종**: 기신합거(합에 묶인 천간의 정적 역할 기신/구신 — 원국 합반·운 합거 공통), 탐합망극(합반+묶인 천간이 합 밖 천간을 극하는 오행).
  - **버그 수정(F6 2차)**: 합 루프가 `canonical_roles`(역할→오행 키)를 오행→역할로 뒤집어 써서 `affected.role`이 항상 빈 문자열이었다 → `favorability_map(result)`로 교체. 원국 천간합은 direction 없이 bind로만 판정되므로 거살유관/거관유살/기신합거는 bind·away 공통 조건. 용신 유력/무력은 `canonical_roles["yongsin"]`을 읽는다.
  - **300명식 무작위 스캔 후 조정**: 재관인상생은 병존(45%)이 아니라 재생관+관인/살인상생 연쇄+재극인·탐재괴인 없음+인성 표면 12%+(29%). 갑목소토는 土 과다 또는 30%+(24%→10%). 성중유패는 격 신뢰 A/B+active 파격+구제 없음(18%, 성격 등급은 파격 0일 때만 나와 원안대로면 0건). 천한지동은 한습 부담+丙丁 천간 부재+(겨울 월지 또는 火 표면 0). 용신 유력 0.4/무력 0.5(거의 전 명식 해당 → 상위 6 잠식 방지).
  - **격국 6종**: 잡기인수격(사고 월지 지장간 인성+투간), 화토·화금·화수·화목·화화격(`chart_transform` 化神 매핑, 진화 0.6/가화 0.45).
  - **특수 배치 3종**(context_only): 일록귀시(시지 12운성 건록), 시상편재(시간 편재+통근), 천원일기(4천간 동일).
  - **평가 4종**: 성중유패(성격 등급+active 파격), 패중유성(failure_with_rescue), 용신 유력/무력(정적 용신 오행 통근·표면 12%·결핍).
  - **B 등급(미구현, 사용자 결정 대기)**: 양신성상·조토불생금/습토회화·재인불애/재인상전·관다위살·재관쌍미·탐생망극·청기유통/거탁유청·종왕격/종강격·천지동류·유정/무정·변격. 결정 항목은 감사 문서 §4.
  - 회귀: 픽스처 5차트 감지 집합 갱신(제거 0·추가 12: 정화련금·성중유패·기식취인·신왕무의·살중제경·패중유성·잡기인수격·용신 유력×3·용신 무력×2). 단위 `tests/unit/test_structure_patterns_f6_terms.py`.

### 미배선(deferred, 자료 §13)
- **암충격·도충격(비천록마 계열)**: 지지 허충으로 재/관을 불러오는 특수격. 학파차가 크고 적용 일주 제한이 강하며 geokguk 미산출 → 근거 없는 추정 구현 회피(원칙 9·10). 재개 조건: ①doc/v2_2 정식 규칙 ②적용 일주 whitelist ③동일 지지 3+·허자 충출·실제 관성 부재·신강 조건 확정 ④golden sample 10건+ ⑤shadow-only 회귀 관측 후 오탐 검수. 설명 태그로도 노출하지 않는다(해석 확장 리스크).
- 고전 성별 단정어(여명상관다극부 등): 자료 §13 주의 — 서비스 미노출(비단정 표현 변환 대상).
