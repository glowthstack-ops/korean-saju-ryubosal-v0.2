# 07. 개발 로드맵 & Claude Code 태스크

각 Phase는 독립 PR 단위로 쪼갠다. **Phase 완료 기준 = 타입 정의 + 구현 + 단위 테스트 + 회귀 픽스처 통과.**
변경 사항은 적용 전 사용자 리뷰를 받는다.

---

## Phase 0. 기반 (1~2일)

- [ ] T0.1 `src/types/` 공유 타입 정의 (Stem, Branch, TenGod, Element, EventKey, IntentJson, EventCandidate 등 — docs/02·03 스키마 그대로)
- [ ] T0.2 zod 스키마 + `dict:validate` 스크립트 골격
- [ ] T0.3 기존 만세력 엔진 출력 → `ManseResult` 어댑터 (만세력 엔진 자체는 수정 금지)
- [ ] T0.4 `GanjiCalendarEntry` 생성기: 기간 입력 → 대운/세운/월운/일운 간지 + 원국과의 RelationHit 산출

**검수 포인트**: 어댑터가 기존 엔진 결과와 1:1 일치하는지 스냅샷 테스트.

## Phase 1. 사전 데이터 MVP (2~4일)

- [ ] T1.1 `common/` 4종 (stems, branches, ten_gods, elements)
- [ ] T1.2 `relations.json` — 천간합 5종, 지지육합/삼합/방합, 충/형/파/해/자형, 공망/복음/병존/간여지동
- [ ] T1.3 `events/taxonomy.json` — EventKey + progress/instant/hybrid 분류
- [ ] T1.4 `events/career_change.json`, `events/relocation.json` (2개 도메인 먼저)
- [ ] T1.5 `favorability_rules.json`
- [ ] T1.6 `dict:validate` + `dict:lint` (충돌 검사) 완성

**주의**: 사전의 명리 내용(매핑·가중치)은 도메인 검수가 필요하다. Claude Code는 초안을 생성하되, 모든 항목에 `reviewed: false` 플래그를 붙이고 사용자 검수 후 true로 전환하는 워크플로를 만든다.

## Phase 2. Event Graph + Scoring (3~5일)

- [ ] T2.1 `graph:build` — 사전 → `compiled/event_graph_vX.json` (노드/엣지, semver)
- [ ] T2.2 인메모리 Graph Retrieval (graphScope 역방향 탐색, 5-hop 제한, EvidenceBundle 출력)
- [ ] T2.3 Event Scoring Engine — base score + favorability 보정 + weight 합산 + 계층 필터(세운 score≥70/Top5)
- [ ] T2.4 readable evidence path 생성기
- [ ] T2.5 회귀 픽스처: "갑기합+정관+기신 → career_change 상위" 등 핵심 케이스 10개

## Phase 2.5. 사전계산 파이프라인 (docs/09) (3~5일)

- [ ] T2.5.1 상호작용 탐지기 — docs/09 2장 전체 목록 구현 (천간합5/충4, 육합6, 삼합4+반합, 방합4+반합, 충6, 형(삼형2+상형+자형4), 파6, 해6, 원진6, 암합 비활성 플래그). **목록 외 관계 임의 추가 금지**
- [ ] T2.5.2 레벨 조합 P01~P11 + 다자합(소스 혼합 삼합/방합/삼형) 탐지
- [ ] T2.5.3 LuckComposite 계산기 + PG 테이블(luck_composites) + dictVersion 무효화
- [ ] T2.5.4 갱신 스케줄러: T0(등록/수정), T1(대운 교체·입춘·절입), T2(일일 배치 — 활성 대상 / lazy+TTL — 비활성)
- [ ] T2.5.5 day 레벨 보존 정리 배치 (과거 90일/미래 400일)
- [ ] T2.5.6 Topic Context Builder M01~M15 골격 + 우선 구현: M03(성향 시프트), M07(career), M10(이사), M15(lifestyle)
- [ ] T2.5.7 M10 이사 Resolver S1~S10 전체 + region_elements/housing_rules 사전 골격(전항목 reviewed:false)
- [ ] T2.5.8 LLM 호출 래퍼: 토큰 한도표(docs/09 8장) 가드 + thinking 비활성 강제 + 입출력 토큰 로깅

**검수 포인트**: 동일 (대상, 기간, dictVersion) → byte 동일 LuckComposite (결정성). 이사 4인 그룹 질의의 LLM 입력 ≤ 4,500 tok 실측.

## Phase 3. 오케스트레이터 코어 (3~5일)

- [ ] T3.1 Query Parser — 자연어 → IntentJson (경량 LLM 1회 호출, JSON 강제, 실패 시 룰 기반 폴백)
- [ ] T3.2 Broad Query Rewriter (too_broad 판정 + 선택지 생성)
- [ ] T3.3 Execution Planner — queryType별 고정 템플릿 (docs/03 B4)
- [ ] T3.4 Context Reduction Engine
- [ ] T3.5 LLM Input Contract 직렬화기 (docs/06) + 기존 `buildSajuPrompt` 계열과 통합
- [ ] T3.6 다중 intent 파싱 + intent별 답변 섹션 보장 (docs/08 B4/B5 — 실측 7.5%)
- [ ] T3.7 시점 파서 18패턴 (docs/08 C — 글피/나이변환/데드라인 역산/외부일정 앵커/사용자 구간 포함)
- [ ] T3.8 Q11~Q14 비분석 라우트 (용어 교육 / 피드백 정정 / 감정 우선 / out_of_scope 정책 응답)

**검수 포인트**: 동일 질문 → 동일 ExecutionPlan (결정성). **docs/08 H의 골든 테스트 30케이스 전부 통과** + 실로그 기반 질문 50개 추가.

## Phase 4. Conversation Layer (2~4일)

- [ ] T4.1 Conversation State Engine (스레드 저장: PostgreSQL)
- [ ] T4.2 Entity Tracking — 시스템 답변에서도 엔티티 생성
- [ ] T4.3 Question Linking — 룰 우선 + 애매 시 LLM 분류기
- [ ] T4.4 Subject Resolution Engine (docs/03 A0) + Subject Manager (docs/02 E14): 별칭 매핑, 인라인 생년월일 파싱(양/음력·시각·출생지), 임시 인물 누적 참조, 대상 정정 재실행
- [ ] T4.5 claim 엔티티: 시스템 명리 판정 추적 → 이의 제기("편인격 아니야?") 재검산 지원
- [ ] T4.6 통합 테스트: "올해 연애운 → 그 사람은? → 결혼 가능성은?" + "내일운세 → 모레는? → 글피는?" + "1호 2호 둘 다 봐줘" 시나리오

## Phase 5. 예측 엔진 확장 (3~5일)

- [ ] T5.1 Timeline Engine (stage_mapping 사전 + activation window)
- [ ] T5.2 Event Form Engine
- [ ] T5.3 Self Profile Engine (성격검사화 금지 — manifestation 보정 목적으로 한정)
- [ ] T5.4 Manifestation Engine (Reality Context 입력 UI는 별도)
- [ ] T5.5 Advice Engine (+remedy 6분기 — docs/08 D-3) — 능동 제안 계층으로 진행 중: Phase A(타입·사전·파이프라인) 완료, 설계 docs/15
- [ ] T5.6 Compatibility Engine (E13, relation_profiles 사전 포함)
- [ ] T5.7 Competition Engine (E12) + 당락 단정 금지 템플릿 + no_hour 모드

## Phase 6. Past Validation (신뢰 엔진) (2~3일)

- [ ] T6.1 과거 N년 이벤트 후보 생성 (Phase 2 재사용, 역방향)
- [ ] T6.2 사용자 피드백 수집 → cases.jsonl 적재
- [ ] T6.3 Confidence Calibration (맞춘 비율 → 신뢰도 % → 표현 강도 반영)
- [ ] T6.4 온보딩 플로우 연동: 미래 예측 전 과거 검증 먼저 노출

## Phase 7. 생활 운세 & 택일 (3~5일)

- [ ] T7.1 Calendar Rule Engine (손없는 날 계산 — 음력 변환 필요, 절기/공휴일 데이터)
- [ ] T7.2 Risk Avoidance (금기일/회피일)
- [ ] T7.3 Date Selection Engine (목적별 가중치 프로파일 + 5단계 점수)
- [ ] T7.4 Reality Constraint 입력 처리
- [ ] T7.5 Lifestyle Fortune Engine + format_slots 템플릿
- [ ] T7.6 windfall/speculation 표현 제한 검증 테스트 (로또 번호 거부 케이스 포함 — docs/08 G6)
- [ ] T7.7 방위/시진/체인 스케줄링 확장 (docs/02 E10 보강)

## Phase 8.5. 사용자 프로필 & 페르소나 (docs/11) (2~4일)

- [ ] T8.5.1 BasicProfile 입력 플로우 (양/음력·윤달, 시간 모름/대략 시간대, 해외 출생, 진태양시 보정 연동 — 기존 만세력 보정 재사용)
- [ ] T8.5.2 ExtendedProfile 입력 플로우 — **전 필드 스킵 가능 + just-in-time 수집 + 세션 내 재요청 금지** + 개별 삭제·캐시 무효화
- [ ] T8.5.3 occupation_taxonomy.json (O01~O18, 물상 매핑 reviewed:false) + E3/E6 연동
- [ ] T8.5.4 maritalStatus/children → M01/M02 분기 + 자녀 동반자 등록 제안 플로우
- [ ] T8.5.5 PersonaConfig 5축 설정 UI 계약 + 조합 제약 검증 (docs/11 5-2) + 금칙어 필터
- [ ] T8.5.6 페르소나 프롬프트 블록 조립기 (5-3 템플릿 치환 전용) + persona_lexicon.json
- [ ] T8.5.7 페르소나 준수 검사 4종 (5-4) — 대화/보고서 공통
- [ ] T8.5.8 대화 추출 → 사용자 확인 → 프로필 갱신 파이프라인 (F9 연동)
- [ ] T8.5.9 미입력 영향표(docs/11 4장) 동작 테스트: 각 필드 부재 시 차단 없이 한계 고지
- [ ] T8.5.10 쌍둥이 시주 조정 (docs/11 2-2): multipleBirth 입력 → 시주 60갑자 (order-1)칸 전진(일/월/년주 불변, wrap 시 twin_wrap_convention 플래그), 변형 2종 생성·전환 UI, 안내 문구 고정 템플릿 노출(등록 직후 1회 + 시주 관련 풀이 1회), Past Validation 변형 비교 추천(자동 전환 금지)
- [ ] T8.5.11 쌍둥이 단위 테스트: 乙丑 기준 둘째=丙寅·셋째=丁卯, 亥時 둘째 wrap=子時·일주 불변, 동반자 쌍둥이 동일 동작

## Phase 9. 풀이 상품 (docs/10) (4~6일)

- [ ] T9.1 ReportSpec → SectionPlan 생성기 (RPT_FULL 22섹션 / RPT_FOCUS 8섹션 — **목차 변경 금지**)
- [ ] T9.2 섹션별 생성 워커 (병렬 ≤4, dependsOn 준수) + 비동기 작업 큐
- [ ] T9.3 정합성 검사 8종 (docs/10 7장) + 섹션 재생성 루프(≤2회)
- [ ] T9.4 docx/pdf 조립 (표지/목차/dictVersion 부록)
- [ ] T9.5 페르소나 3종 사전 + 페르소나 준수 검사
- [ ] T9.6 CHAT↔보고서 연계 (too_broad 시 상품 제안 카드)
- [ ] T9.7 원가 대시보드: 호출별 productCode/sectionId/토큰 집계

## Phase 8. 통합 & 품질 (지속)

- [ ] T8.1 E2E: 질문 → 답변 전체 파이프라인 통합 테스트 (질문 유형 Q1~Q9 각 5개)
- [ ] T8.2 토큰 측정: Context Reduction 전/후 입력 토큰 비교 리포트
- [ ] T8.3 회귀 테스트 CI 연동
- [ ] T8.4 모델 평가 하네스 — 후보 모델별 instruction 준수/날짜 구체성/용어 정확도 비교 (기존 Gemini 평가 방법론 재사용)

---

## 의존 관계

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 2.5 ──► Phase 3 ──► Phase 4
                                       │             │
                                       ▼             ▼
                                    Phase 5       Phase 6
                                       │
                                       ▼
                                    Phase 7 ──► Phase 9 ──► Phase 8
```

Phase 3까지 완료되면 "단일 질문 → 정확한 풀이" MVP가 동작한다. Phase 4 이후가 재방문율(대화 연속성)을 결정한다.

---

## 리스크 & 미해결 사항 (정직하게 기록)

1. **사전 가중치 캘리브레이션 데이터 부재**: base_score, weight, modifier 수치는 현재 추정치다. cases.jsonl이 충분히 쌓이기 전까지는 점수의 절대값보다 **상대 순위**만 신뢰하고, UI/문구도 순위 중심으로 설계할 것.
2. **용신 자동 판정 정확도**: 종격/가종격, 조후 우선 케이스는 룰 충돌이 잦다. confidence 필드로 불확실성을 전파하고, 낮으면 LLM 표현을 보수화.
3. **Past Validation의 콜드리딩화 위험**: 후보 이벤트 폭을 넓게 잡으면 "뭐든 맞는" 결과가 된다. 연도당 후보 2개 이하, score 임계값 엄격 적용.
4. **손없는 날 음력 변환**: 만세력 엔진에 음력 변환이 이미 있다면 재사용. 없으면 별도 라이브러리 검토 필요 (이 부분은 기존 엔진 확인 후 결정).
5. **Self Profile 범위 통제**: 보정 모디파이어 산출 외 기능 확장 금지. MBTI화는 명시적 안티 골.
6. **법적/윤리 표현**: 건강(수술)·투자(주식/로또) 관련 출력은 의료·투자 조언이 아님을 고지하는 문구를 템플릿 레벨에 고정.
7. **대상 혼동 (실측 최다 오류)**: subject 모호 시 추측 실행 금지, 확인 질문 우선. 대상 전환 후에는 답변 서두에 대상을 명시해 사용자가 즉시 검증 가능하게.
8. **실존 공인 승부 예측 (실측 존재)**: 선거 당락 등 단정 출력은 명예·선거 리스크. E12 정책(상대 우열까지만 + 한계 고지)을 우회하는 표현이 없는지 출력 테스트 필수.
9. **미성년 사용자 실재 (실측 79건)**: 본인이 미성년인 세션과 자녀를 subject로 한 세션을 구분, 표현·도메인 제한 정책 적용 (docs/08 G2).
10. **프롬프트 추출 시도 실재 (실측)**: 시스템 내부(모델/프롬프트/CoT/RAG 구성) 비공개 고정 응답. 사용자 페이스트(JSON/코드)를 질문으로 오인하지 않는 파서 방어.
11. **지역오행/주거타입 보정의 명리 근거 부족**: region_elements·housing_rules는 표준이 없어 자체 기준 — 전 항목 reviewed:false, 사용자 검수 전 해당 기능 출시 금지 (docs/09 9장).
12. **보고서 원가**: RPT_FULL은 최대 44회 호출. 정합성 재생성률이 높으면 원가 초과 — 재생성률 >20% 시 섹션 프롬프트 점검을 운영 알림으로.
13. **사전계산 정합**: dictVersion 불일치 데이터 혼용 금지 — Composite 조회 시 버전 필터 필수.
14. **프로필 민감정보**: 결혼/자녀/직업은 해당 질문에 필요한 필드만 LLM에 전달 (전체 프로필 일괄 주입 금지 — docs/11 8장). 호칭 custom은 금칙어 필터 필수.
15. **물상 매핑·페르소나 어휘 검수**: occupation 물상 매핑과 persona_lexicon은 reviewed:false 상태로 출시 금지.
16. **쌍둥이 시주 전진법은 유파 관습**: 시각 그대로 보는 유파도 있음 — 단정 금지, 안내 문구로 선택권 제공(자동 전환 금지). 亥→子 wrap의 일주 처리(불변)는 규격이지만 야자시 유파 쟁점이므로 twin_wrap_convention 플래그로 격리.
