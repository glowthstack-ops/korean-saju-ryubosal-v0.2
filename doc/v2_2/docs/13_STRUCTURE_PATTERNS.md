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

**중요(고정 프리픽스 캐시 제약)**: `ChartInterpretation`은 사용자별 멀티턴·전 섹션에서 바이트 단위 동일해야 하는 **캐시 프리픽스**다(가변 값 금지 — 타입 docstring 계약). 따라서 이 필드는 **도메인 무관·결정적 상위 N(strength desc)** 으로 채운다. 질문 도메인 필터를 여기 적용하면 프리픽스가 질문마다 달라져 캐시가 무효화된다.

- `select_llm_patterns(all, domain=None, max_count=6)`: 캐시 프리픽스는 `domain=None`(결정적)으로 호출. `domain` 인자는 domain_hints 매칭 우선 정렬을 지원하나 **비캐시(질문 가변) 경로 전용**이다.
- 내부 전체 감지(`detect_structure_patterns`)는 보존하고, LLM 노출은 상위 6개만(내부/노출 분리).
- 직렬화: `serialize_chart_prefix` 최하단 `[구조 패턴 — 설명 태그]` 블록(토큰 가드 후순위 절삭 대상). llm_tag만 노출.
- 지시: `_STRUCTURE_PATTERN_INSTRUCTION`(감지분 있을 때만) — "구조 라벨일 뿐 사건·길흉 확정 아님".

> **후속(선택)**: 질문 도메인 필터를 실제 적용하려면 detected_patterns를 캐시 프리픽스가 아닌 질문 가변 섹션([기준 시점] 이하)에 배치해야 한다. 현재는 캐시 비용 보호를 위해 프리픽스 도메인 무관으로 두었다.

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
- [x] ④ LLM 입력 배선: `ChartInterpretation.detected_patterns`(도메인 무관 top-6, 캐시 안전) + prefix 직렬화 + 금지 단정 지시. inert — 기존 score/confidence/favorability/event_count 불변, 전체 unit+regression green.

### 후속(P0 밖)
- 충개(沖開)·입묘(入墓)·개고(開庫) 감지 — 묘고 신호(wealth_capacity·structural_context) 결과 컨텍스트 배선.
- 질문 도메인 필터를 실제 적용하려면 detected_patterns를 비캐시 질문 섹션으로 이전(§6 후속).
- P1/P2 패턴 확장(상관패인·득비이재·목화통명·종왕격 등, 자료 §13).
