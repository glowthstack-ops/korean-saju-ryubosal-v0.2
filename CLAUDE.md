# CLAUDE.md — 사주 통변 서비스 v2 개발 가이드

> 이 파일은 Claude Code의 진입점이다. v2.2 작업 시작 전 반드시 이 파일과 `doc/v2_2/docs/` 하위 설계 문서를 읽을 것.

## 1. Role

- 당신은 정교하고 꼼꼼한 전문 소프트웨어 엔지니어입니다.

## 2. 프로젝트 한 줄 요약

LLM이 사주를 계산·추론하지 않는다. **만세력 엔진이 계산하고, 이벤트 엔진이 가능성을 점수화하고, 오케스트레이터가 질문에 필요한 정보만 선별하며, LLM은 제공된 사실과 점수를 자연어로 설명만 한다.**

## 3. 현재 상태 (이미 완성됨 — 재구현 금지)

- **만세력 엔진** (Python, `backend/packages/`): 원국/대운/세운/월운/일운 간지 계산, 지장간, 십성, 12운성, 공망, 합충형파해(원국+운), 합화(化) 판정, 신살, 격국, 신강약, 용신(후보 모델·용희기구한 역할 배정), 용신 검증(캘리브레이션), 진태양시·균시차 보정, 출생지 전국 시군구 경도 보정
- **API** (FastAPI, `backend/apps/api/`): `/api/v2/manse/*` — calculate(LRU 캐시), calibration/feedback, luck/months, luck/days, calendar
- **사용자용 화면** (Next.js, `frontend/`): 만세력 결과 페이지(명식·형충회합·신살·분포·격국·신강약·용신·검증·운 스트립·플로팅 ToC), 간지달력(일운 오버레이)
- **스택**: Python 3 + FastAPI + pydantic v2 (backend) / Next.js + TypeScript (frontend). DB 미도입 — 사전계산 단계(Phase 2.5)에서 PostgreSQL 도입 예정.

> **주의**: `doc/v2_2/` 설계 문서는 TypeScript/Node.js 스택 기준으로 작성되었으나, 본 리포는 **Python 백엔드에 통합 구현**한다(사용자 확정). zod → pydantic, `src/types/` → `backend/packages/shared_types/` 로 번역하되, 문서의 스키마·목록·규격 **내용**은 그대로 준수한다. 문서 내 "기존 프롬프트 시스템(`buildSajuPrompt` 등)" 언급은 v1 코드베이스 기준이며 본 리포에는 존재하지 않는다.

## 4. 이번에 새로 만드는 것 (v2.2)

| 영역 | 구성요소 | 설계 문서 |
|---|---|---|
| 대화 계층 | Conversation State / Entity Tracking / Question Linking | `doc/v2_2/docs/03_ORCHESTRATOR_SPEC.md` |
| 오케스트레이터 | Question Taxonomy, Intent Schema, Execution Planner, Context Reduction | `doc/v2_2/docs/03_ORCHESTRATOR_SPEC.md` |
| 분석 엔진군 | Event Scoring, Event Form, Timeline, Manifestation, Self Profile, Past Validation, Advice | `doc/v2_2/docs/02_ENGINES_SPEC.md` |
| 생활 운세 계층 | Lifestyle Fortune, Date Selection(택일), Calendar Rule, Risk Avoidance | `doc/v2_2/docs/02_ENGINES_SPEC.md` |
| Event Graph RAG | 노드/엣지 스키마, 근거 경로(evidence path) 생성·검색 | `doc/v2_2/docs/04_EVENT_GRAPH_RAG.md` |
| 사전 데이터 | JSON 사전 스키마, 검증·컴파일 파이프라인 | `doc/v2_2/docs/05_DATA_DICTIONARIES.md` |
| LLM 입력 계약 | 압축 간지달력 + 이벤트 후보 + 금기 규칙 입력 포맷 | `doc/v2_2/docs/06_LLM_INPUT_CONTRACT.md` |
| 실사용 질문 패턴 | 이전 버전 실로그 2,255건 전수 카탈로그 — **파서/오케스트레이터 작업 전 필독, 테스트 케이스 원천** | `doc/v2_2/docs/08_QUESTION_PATTERNS.md` |
| 사전계산 & 동적 컨텍스트 | 운 복합조합 사전계산(T0~T2), Topic Builder M01~M15, 이사 복합 해석, 토큰 예산 | `doc/v2_2/docs/09_PRECOMPUTE_DYNAMIC_CONTEXT.md` |
| 풀이 상품 3종 | 총운(50장)/집중(15장)/대화형 — 목차 전체 규격, 정합성 검사 | `doc/v2_2/docs/10_READING_PRODUCTS.md` |
| 사용자 정보 & 페르소나 | 1단계(생년월일시·출생지)/2단계(직업·거주·결혼·자녀, 스킵 가능), 조합형 페르소나 5축 | `doc/v2_2/docs/11_USER_PROFILE_ONBOARDING.md` |

개발 순서와 작업 단위는 `doc/v2_2/docs/07_ROADMAP_TASKS.md`를 따른다. 각 Phase는 독립 PR 단위이며, 완료 기준 = 타입 정의 + 구현 + 단위 테스트 + 회귀 픽스처 통과.

## 5. 절대 원칙 (위반 시 PR 거부 수준)

1. **LLM 계산 금지**: 간지, 합충형파해 성립 여부, 공망 활성화, 이벤트 점수는 절대 LLM에게 맡기지 않는다. 모두 엔진(코드)이 계산한다.
2. **LLM 입력 = 압축 간지달력 + 이벤트 후보 + 근거 경로 + 해석 제한 규칙**. 전체 간지달력이나 전체 사전을 통째로 넣지 않는다. 단, 이벤트 후보에 해당하는 간지 정보는 반드시 포함한다 (LLM은 간지를 계산할 수 없으므로).
3. **단정 표현 금지**: "반드시 이직한다" 류의 확정 표현은 `prohibited_style`로 차단. "변화 에너지 활성화" + 단계(awareness→exploration→action→decision) 모델로 표현.
4. **이벤트 ≠ 결과**: Trigger Month ≠ Execution Month. Activation Window 개념 필수.
5. **사전(JSON)은 직접 운영 반영 금지**: validate → compile(snapshot) → regression test → 배포 파이프라인을 거친다.
6. **모든 변경은 사용자 리뷰 후 적용**: 소스 파일 수정 전 변경 내용을 먼저 제시하고 승인을 받는다.
7. **대상(Subject) 우선 확정**: 본 서비스는 n명의 동반자 사주 등록을 지원한다. 모든 질문은 intent보다 먼저 "누구의 사주인가"를 확정하며, 모호하면 추측하지 않고 확인 질문을 한다. 실로그 최다 오류가 대상 혼동이다.
8. **승부 단정 금지 + 생활형 횡재 정책(2026-06-20 개정)**: 경쟁 비교(선거/시험/오디션)는 상대 우열 + 근거까지만. 당락·승패 확정 표현은 출력 금지. **생활형 횡재(로또·연금복권·소액 주식 등)는 재물 흐름·유리한 시기·임하는 태도(소액·분산·재미)를 자유롭게 풀이한다** — 과도한 면책·경고 반복으로 위축시키지 않는다. 단 다음 하드 가드는 유지: ①구체 번호·특정 종목 픽 제공 거부 ②당첨·수익 확정 단정 금지(가능성·기류로) ③전 재산 투입 등 과몰입 권유 금지. 번호·종목 픽 요청은 `query_parser`에서 OUT_OF_SCOPE(정책 거부), 흐름·시기 질문은 통과시켜 `_LIFESTYLE_WINDFALL_DIRECTIVE`로 자유 서술.
9. **사전계산 우선**: 운의 복합 조합·작용은 Precompute Store(T0~T2)에서 가져온다. 요청 시점에 즉석 재계산하거나 LLM에 조합 판단을 넘기는 코드는 금지. LLM 호출은 docs/09 8장의 토큰 한도표를 코드 가드로 강제하며, thinking(추론 모드)은 low 이하로 제한한다(Query Parser는 비활성 — v2.2.1 개정, 2026-06-12 사용자 승인).
10. **전체 규격 문서 준수**: docs/08~11의 목록·목차·스키마는 "예시"가 아니라 전체 규격이다. 항목을 임의로 추가·삭제·축약·재해석하지 않는다. 문서에 정의되지 않은 명리 규칙·보정·섹션이 필요해 보이면 구현하지 말고 사용자에게 질문한다.
11. **2단계 프로필은 항상 선택**: 추가 정보(직업/거주/결혼/자녀) 부재로 기능을 차단하거나 오류를 던지는 코드 금지. 모든 모듈은 optional 입력. 미입력 동작은 docs/11 4장 영향표를 따른다.
12. **페르소나 = 문체 전용**: 페르소나 프롬프트 블록은 docs/11 5-3 템플릿 치환으로만 생성(즉석 작문 금지). 페르소나가 점수·날짜·간지·판정에 영향을 주는 구현 금지.

## 6. 코드 컨벤션

- **backend (Python)**: 타입 힌트와 docstring(한국어, 리포 스타일) 필수. 모든 엔진 입출력은 `backend/packages/shared_types/`의 pydantic 모델로 정의하고 런타임 검증한다(설계 문서의 zod 역할).
- 엔진은 순수 함수 지향: `(input, dictionaries) -> output`. 사이드이펙트(DB, LLM 호출)는 오케스트레이터/서비스 계층에만.
- **frontend (TypeScript)**: strict mode 유지.
- 사전 데이터는 UTF-8(BOM 없음) JSON. 사례 데이터는 JSONL.
- 한자 간지(甲, 亥 등)는 데이터/키에 사용하고, 사용자 노출 문자열은 한글 병기.
- **검증 게이트**: backend 전체 pytest + `ruff` + **production mypy gate** / frontend `tsc` + production build 통과 후 완료 선언.

  | 게이트 | 명령 | 통과 표현 |
  |---|---|---|
  | 전체 pytest | `./scripts/run_suite.sh` | `VALID_SUITE_PASS` |
  | 정적 검사 | `./scripts/lint.sh` | `All checks passed` |
  | production 타입 | `./scripts/typecheck.sh` | `production mypy gate clean` |
  | 유지 스크립트 타입 | `./scripts/typecheck_maintained_scripts.sh` | `maintained scripts mypy gate clean` |
  | 4종 일괄 | `./scripts/gates.sh` (`--quick`=스위트 제외) | `GATE RECORD` 에 게이트별 state·exit |
  | full-tree mypy | `python -m mypy --no-incremental .` | 비차단 부채 감사 — production gate와 혼용 금지 |

  - **게이트는 스크립트로만 호출한다.** 모든 게이트 스크립트가 호출 위치와 무관하게 저장소 루트를 스스로 확정한다. `cd backend && ruff check .` 처럼 손으로 묶으면, 호출자가 이미 `backend`에 있을 때 `cd`가 실패하고 `&&` 때문에 ruff는 **실행되지 않은 채** `cd`의 exit code 1이 lint 실패로 보고된다(2026-08-03 실측). **미실행과 실패는 다른 상태다.**
  - 게이트 출력을 파이프로 넘기지 않는다. `ruff check . | tail -1`은 파이프라인 exit code가 `tail`의 것이라 ruff의 1을 삼킨다(2026-07-30 실측). exit code는 직접 읽는다.

  - **전체 pytest 스위트는 반드시 `./scripts/run_suite.sh`로 실행한다.** pytest exit code가 0이어도 실행 중 저장소 내용이 변경되면 결과는 유효하지 않다. 유효한 전체 스위트 통과는 다음을 **모두** 만족해야 한다.
    - `test_exit_code = 0`
    - `start_head = end_head`
    - `start_fingerprint = end_fingerprint`
    - `verdict = VALID_SUITE_PASS`
  - `SOURCE_CHANGED_DURING_RUN`은 테스트 성공 여부와 무관하게 무효이며 exit 65로 종료한다. 실제로 스위트 실행 중 설정 파일과 그 회귀를 고쳐 결과가 무효화된 사고가 있었고, 그때 `git status` 문자열은 시작·종료가 동일해 상태 비교로는 잡히지 않았다(2026-07-31).
  - worktree가 clean일 필요는 없다. 더러운 채로 시작해도 시작·종료 지문이 같으면 유효한 실행이다.
  - production mypy gate = `./scripts/typecheck.sh` (검사 범위 SSOT는 `backend/pyproject.toml` 의 `[tool.mypy] packages` — CI·문서에 경로를 다시 나열하지 않는다)
  - `mypy clean` 이라는 표현은 쓰지 않는다. 호출 파일 목록에 따라 결과가 달라져 통과하기 쉬운 명령을 고를 수 있기 때문이다(2026-07-30 실측: 같은 코드가 파일 1~2개 0건 / 3-root 7건 / production 9건 / full-tree 331건).
  - 비차단 진단: `cd backend && python -m mypy --no-incremental .` — 2026-07-31 기준 257건(tests 0 · scripts 257 · production 0). 기존 부채이며 blocking 조건이 아니다. 이 숫자는 파일 정리·mypy 버전으로 변할 수 있어 게이트로 쓰지 않는다. **건수는 독립 결함 수가 아니다** — scripts 부채의 66%가 무주석 컬렉션 하나에서 파생된 `var-annotated`/`index` 연쇄다.
  - **유지 스크립트 게이트**: `backend/scripts/` 전체는 기존 부채(2026-07-31 기준 257건/43파일)를 안고 있고 운영 경로에는 없다. **테스트가 import 하는 스크립트는 예외** — `mypy_path` 에 `scripts` 가 있어 실제 import 된 모듈만 tests 게이트가 따라 검사한다(전체 검사가 아니다). 전량 정리는 추진하지 않는다. 대신 **재실행 가치가 있는 것만** allowlist(`scripts/typecheck_maintained_scripts.sh`)에 넣어 0건으로 지킨다. 편입 기준 = 운영 smoke 사용 / 설계 변경 전후 동일 모집단 재현 / 판정 기준선·재현 지문 생성 / 실제 재실행 계획. 일회성 포렌식은 넣지 않으며, 승격 시점부터 0건을 요구한다.
  - 보고 표현은 `production mypy gate clean` · `maintained scripts mypy gate clean` · `full-tree mypy audit: N건` 세 가지만 쓴다. tests 트리는 `tests-tree mypy audit: N건`으로 따로 적는다.

## 7. 디렉토리 구조 (목표 — Python 번역)

```
backend/
  packages/
    shared_types/        # 공유 타입 + pydantic 스키마 (문서의 src/types/)
    manse_core/          # (기존) 만세력 계산 — 수정 금지, 어댑터만 추가
    manse_analysis/      # (기존) 구조 분석 (신강약/용신/격국/신살)
    manse_calibration/   # (기존) 용신 검증
    engines/             # Event Scoring / Event Form / Timeline / Manifestation /
                         # Self Profile / Past Validation / Advice / Lifestyle / Date Selection
    orchestrator/        # conversation / parser / planner / context_reducer
    graph/               # Event Graph builder / retrieval
    llm/                 # 프롬프트 빌더, 입력 계약 직렬화
  dictionaries/          # JSON 사전 원본
  compiled/              # 검증·컴파일된 스냅샷 (git 추적, 버전 태그)
  scripts/               # validate_dictionaries / build_event_graph / run_regression
  tests/
    fixtures/            # 검증 사례 (cases.jsonl)
    regression/
frontend/                # (기존) Next.js UI
```

신규 패키지의 세부 배치는 각 Phase 착수 시 사용자와 확정한다.

## 8. 필수 준수 규칙 (Checklist)

- **요약 작업 시:** 핵심 내용 누락 금지. 배경/문제/해결책/결과 순으로 정리할 것.
- **코드 작성 시:** 타입 힌트와 docstring은 반드시 포함할 것.
- **반복 검토:** 결과물을 출력하기 전, '요구사항과 대조하여 누락된 항목이 없는지' 스스로 검토할 것.
- **최종 검토:** 결과물을 반영하기 전, 사용자에게 반드시 무엇을 하려는지 설명하고, 진행 확인을 받을 것.
- **완료 기록:** 결과물 반영 후 중요 사항이라면 /doc 내의 파일에 반영해서 최신 상태로 유지할 것.

## 9. 금지 사항

- 모호한 표현을 사용하지 말 것.
- 근거 없는 추측으로 코드를 작성하지 말 것.
