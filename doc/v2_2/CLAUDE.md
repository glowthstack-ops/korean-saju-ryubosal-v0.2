# 사주 통변 서비스 v2 — Claude Code 개발 가이드

> 이 파일은 Claude Code의 진입점이다. 작업 시작 전 반드시 이 파일과 `docs/` 하위 설계 문서를 읽을 것.

## 프로젝트 한 줄 요약

LLM이 사주를 계산·추론하지 않는다. **만세력 엔진이 계산하고, 이벤트 엔진이 가능성을 점수화하고, 오케스트레이터가 질문에 필요한 정보만 선별하며, LLM은 제공된 사실과 점수를 자연어로 설명만 한다.**

## 현재 상태 (이미 완성됨 — 재구현 금지)

- **만세력 엔진**: 원국/대운/세운/월운/일운 간지 계산, 지장간, 십성, 12운성, 공망, 합충형파해, 신살 계산 완료
- **사용자용 화면(UI)**: 완성. 운 카드(64px 신살 인디케이터 포함) 등
- **기존 프롬프트 시스템**: `SHINSAL_POSITION_GUIDE`, `buildInitialReadingPrompt`, `buildSajuPrompt` 존재
- **스택**: TypeScript, Node.js, PostgreSQL (MCP: postgres-mcp 읽기전용 계정, GitHub MCP)

## 이번에 새로 만드는 것

| 영역 | 구성요소 | 설계 문서 |
|---|---|---|
| 대화 계층 | Conversation State / Entity Tracking / Question Linking | `docs/03_ORCHESTRATOR_SPEC.md` |
| 오케스트레이터 | Question Taxonomy, Intent Schema, Execution Planner, Context Reduction | `docs/03_ORCHESTRATOR_SPEC.md` |
| 분석 엔진군 | Event Scoring, Event Form, Timeline, Manifestation, Self Profile, Past Validation, Advice | `docs/02_ENGINES_SPEC.md` |
| 생활 운세 계층 | Lifestyle Fortune, Date Selection(택일), Calendar Rule, Risk Avoidance | `docs/02_ENGINES_SPEC.md` |
| Event Graph RAG | 노드/엣지 스키마, 근거 경로(evidence path) 생성·검색 | `docs/04_EVENT_GRAPH_RAG.md` |
| 사전 데이터 | JSON 사전 스키마, 검증·컴파일 파이프라인 | `docs/05_DATA_DICTIONARIES.md` |
| LLM 입력 계약 | 압축 간지달력 + 이벤트 후보 + 금기 규칙 입력 포맷 | `docs/06_LLM_INPUT_CONTRACT.md` |
| 실사용 질문 패턴 | 이전 버전 실로그 2,255건 전수 카탈로그 — **파서/오케스트레이터 작업 전 필독, 테스트 케이스 원천** | `docs/08_QUESTION_PATTERNS.md` |
| 사전계산 & 동적 컨텍스트 | 운 복합조합 사전계산(T0~T2), Topic Builder M01~M15, 이사 복합 해석, 토큰 예산 | `docs/09_PRECOMPUTE_DYNAMIC_CONTEXT.md` |
| 풀이 상품 3종 | 총운(50장)/집중(15장)/대화형 — 목차 전체 규격, 정합성 검사 | `docs/10_READING_PRODUCTS.md` |
| 사용자 정보 & 페르소나 | 1단계(생년월일시·출생지)/2단계(직업·거주·결혼·자녀, 스킵 가능), 조합형 페르소나 5축 | `docs/11_USER_PROFILE_ONBOARDING.md` |

개발 순서와 작업 단위는 `docs/07_ROADMAP_TASKS.md`를 따른다.

## 절대 원칙 (위반 시 PR 거부 수준)

1. **LLM 계산 금지**: 간지, 합충형파해 성립 여부, 공망 활성화, 이벤트 점수는 절대 LLM에게 맡기지 않는다. 모두 엔진(코드)이 계산한다.
2. **LLM 입력 = 압축 간지달력 + 이벤트 후보 + 근거 경로 + 해석 제한 규칙**. 전체 간지달력이나 전체 사전을 통째로 넣지 않는다. 단, 이벤트 후보에 해당하는 간지 정보는 반드시 포함한다 (LLM은 간지를 계산할 수 없으므로).
3. **단정 표현 금지**: "반드시 이직한다" 류의 확정 표현은 `prohibited_style`로 차단. "변화 에너지 활성화" + 단계(awareness→exploration→action→decision) 모델로 표현.
4. **이벤트 ≠ 결과**: Trigger Month ≠ Execution Month. Activation Window 개념 필수.
5. **사전(JSON)은 직접 운영 반영 금지**: validate → compile(snapshot) → regression test → 배포 파이프라인을 거친다.
6. **모든 변경은 사용자 리뷰 후 적용**: 소스 파일 수정 전 변경 내용을 먼저 제시하고 승인을 받는다.
7. **대상(Subject) 우선 확정**: 본 서비스는 n명의 동반자 사주 등록을 지원한다. 모든 질문은 intent보다 먼저 "누구의 사주인가"를 확정하며, 모호하면 추측하지 않고 확인 질문을 한다. 실로그 최다 오류가 대상 혼동이다.
8. **승부 단정 금지**: 경쟁 비교(선거/시험/오디션)는 상대 우열 + 근거까지만. 당락·승패 확정 표현은 출력 금지. 로또 번호 생성은 어떤 형태로도 거부.
9. **사전계산 우선**: 운의 복합 조합·작용은 Precompute Store(T0~T2)에서 가져온다. 요청 시점에 즉석 재계산하거나 LLM에 조합 판단을 넘기는 코드는 금지. LLM 호출은 docs/09 8장의 토큰 한도표를 코드 가드로 강제하며, extended thinking은 모든 운영 호출에서 비활성이다.
10. **전체 규격 문서 준수**: docs/08~11의 목록·목차·스키마는 "예시"가 아니라 전체 규격이다. 항목을 임의로 추가·삭제·축약·재해석하지 않는다. 문서에 정의되지 않은 명리 규칙·보정·섹션이 필요해 보이면 구현하지 말고 사용자에게 질문한다.
11. **2단계 프로필은 항상 선택**: 추가 정보(직업/거주/결혼/자녀) 부재로 기능을 차단하거나 오류를 던지는 코드 금지. 모든 모듈은 optional 입력. 미입력 동작은 docs/11 4장 영향표를 따른다.
12. **페르소나 = 문체 전용**: 페르소나 프롬프트 블록은 docs/11 5-3 템플릿 치환으로만 생성(즉석 작문 금지). 페르소나가 점수·날짜·간지·판정에 영향을 주는 구현 금지.

## 코드 컨벤션

- TypeScript strict mode. 모든 엔진 입출력은 `src/types/` 의 인터페이스로 정의하고 zod 스키마로 런타임 검증.
- 엔진은 순수 함수 지향: `(input, dictionaries) => output`. 사이드이펙트(DB, LLM 호출)는 오케스트레이터/서비스 계층에만.
- 사전 데이터는 UTF-8(BOM 없음) JSON. 사례 데이터는 JSONL.
- 한자 간지(甲, 亥 등)는 데이터/키에 사용하고, 사용자 노출 문자열은 한글 병기.

## 디렉토리 구조 (목표)

```
src/
  types/              # 공유 타입 + zod 스키마
  engines/
    manse/            # (기존) 만세력 엔진 — 수정 금지, 어댑터만 추가
    chart-analysis/   # 사주 구조 분석 (신강약/용신/격국)
    event/            # Event Scoring Engine
    event-form/       # Event Form Engine
    timeline/         # Timeline Engine
    manifestation/    # Manifestation Engine
    self-profile/     # Self Profile Engine
    past-validation/  # Past Validation Engine
    advice/           # Advice Engine
    lifestyle/        # 일일/주간/연간 운세
    date-selection/   # 택일 (Date Selection + Calendar Rule + Risk)
  orchestrator/
    conversation/     # State / Entity / Question Linking
    parser/           # Query Parser → Intent JSON
    planner/          # Execution Planner
    context-reducer/  # Context Reduction
  graph/
    builder/          # Event Graph Builder
    retrieval/        # Graph RAG 검색
  dictionaries/       # JSON 사전 원본
  compiled/           # 검증·컴파일된 스냅샷 (git 추적, 버전 태그)
  llm/                # 프롬프트 빌더, 입력 계약 직렬화
scripts/
  validate-dictionaries.ts
  build-event-graph.ts
  run-regression.ts
tests/
  fixtures/           # 검증 사례 (cases.jsonl)
  regression/
```
