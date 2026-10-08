# C7 부록 — 현 엔진·문서 육친 귀속 인벤토리 (2026-10-08, 에이전트 조사 + 핵심 7곳 직접 재확인)

행 번호는 `backend/` 기준(문서는 `doc/` 기준), 2026-10-08 트리(6fa80ac) 시점.

## 1. 문서 규격
- docs/09 §Topic Builder(166-182): M04 parents_fortune(natal 인성·년월주 + relation_profiles), M05 children(natal 식상·시주 + events/education),
  M06 workplace_relations(관성·비겁), M02 marriage(배우자궁 상태), M13 bond_compare. 형제·시부모·장인장모 담당 모듈 없음.
- docs/10: F-17(연애·결혼+미혼 배우자상 3-3절, 일지·배우자성 물상), F-17b(부모·가족, "M04+육친 신호", 3-4절 인성 동요 신호 기반 건강·돌봄, 사망 단정 금지),
  F-17c(자녀, M05+CHILDBIRTH), F-14 도메인 라벨 '육친', 금지 표현 "육친 사망·사별 단정"(280).
- docs/08: A3/A4/A11 가족 집단, family(166건) 육친 운→M04/M05, children(104)·child_education(28), D2-11, F5, G1.
- docs/11: gender, 시주=자녀 영역(생시 없으면 정밀도 고지), maritalStatus·children → M01/M02/M04/M05 분기, 민감정보 최소 전달.
- 기타: 02_ENGINES_SPEC:388 E13 parent_child(인성↔식상 축·육친 궁위), RISK_DICTIONARY_REVIEW:289 FAMILY_BURDEN(인성=부모·비겁=형제), WORKLOG 5461/7776/10697.

## 2. 코드 규칙표
| # | 위치 | 규칙 | 성별 | 출력 | 사전 reviewed |
|---|---|---|---|---|---|
| A | saju_engines/topic_builder.py:926-1036 `_AXIS_TEN_GODS` | M04=편인·정인, M05=식신·상관, M06=편관·정관·비견·겁재 — 십성 분포 비율만(궁위 미사용) | 없음 | axis_score + 기간 신호 | relation_profiles.json 전 항목 false |
| B | dictionaries/relation_profiles.json | spouse/lover/parent_child/colleague/boss/friend/business_partner 축 라벨 | 없음 | 요약 문자열 | false |
| C | saju_engines/marriage_resource.py:7-9,38-39,351,377-379,426-435,477,489-505 | 여명 관성=배우자·재성=시댁 재력, 남명 재성=처; 년월=parental, 시=spouse_family | 있음 | 구조 판정(불리언·lean) | 코드 상수 |
| D | saju_engines/structural_context.py:44-52,59-95 | 여명 "관성=배우자·재성=시댁", 남명 "재성=배우자, 관성=직위·자식" | 있음 | LLM 지시문 | 코드 상수 |
| E | saju_engines/marriage_flow_modifier.py:43-52; event_engine_v2.py:595-596 | 남명 정관 단독 ×0.6, 여명 재성 단독 ×0.7(결혼 신호) | 있음 | 점수 | 잠정값 |
| F | saju_engines/marriage_hap_subtype.py:18-26 | partner_elements 여명=관살, 남명=재성 | 있음 | 점수(MT4) | 코드 |
| G | saju_engines/marriage_awareness_seed.py:36-47 | 여명 정관·편관, 남명 정재·편재, 미상 cap 35 | 있음 | 점수(MT1, OFF) | 코드 |
| H | dictionaries/event_engine/transit_ten_god_branching.json:1609-1651 | relationship_change gender_modifier(소비 코드 0), childbirth primary 식신·상관 | 규격만 | 점수 | false |
| I | 같은 파일 253-268, 873-893 | 운 식신 단독 childbirth 30, 식신+정재 41 | 없음 | 점수 | false |
| J | dictionaries/event_engine/relation_palace_modifier.json:555~ palace_map | year=가족 뿌리(0.75), month=부모·상사(1.25), day=배우자(1.3), hour=자녀(1.0) | 없음 | 점수 보정 | false |
| K | 같은 파일 882-897 CHUNG_RESOURCE_RENEWAL; relation_palace_engine.py:49,302-326 | 운 충이 원국 인성을 치면 contract_document/relocation/career_change(부모 사건 아님), flag 기본 OFF | 없음 | 점수 | false |
| L | saju_engines/addendum_gate_modifier.py:107-110; event_engine_v2.py:1814-1815 | 무파트너면 childbirth→creative_output | 프로필 | 키 전환 | SPEC_ONLY |
| M | dictionaries/risks/relationship.json:687~ REL_FAMILY_BURDEN | 연주 충·형 / 월주 충·형+인성(부모)·비겁(형제) → 가족 책임 부담, 유고 단정 금지 | 없음 | 위험 판정 | **true** |
| N | saju_engines/chart_interpretation.py:48-53 `_PALACE_ROLE` | 연 조부/조모, 월 부친/모친, 일 자신/배우자, 시 아들/딸 | 없음 | 서술(palace_role) | 테스트 없음 |
| O | chart_interpretation.py:648-653; context_reducer.py:312-315,360-365; sinsal_text.json | 연=조상, 월=부모·직장, 일=나·배우자, 시=자녀 | 없음 | 서술 | — |
| P | saju_engines/palace_relationship_network.py | 궁위 간 합충형파해·공망(원국 전용, inert) | 없음 | 서술 | — |
| Q | sinsal_modifier_config.py:25-30; counterfactual_context.py:84-86 | year=ancestry, day=spouse, hour=children 태그 | 없음 | 태그 | — |
| R | structural_context.py:315-333 행동 패턴 3층 | 궁위=보조 단서(서사 규칙) | 없음 | 지시문 | 2026-09-06 조건부 승인 |
| S | chart_interpretation.py:202-203,752-770; interpretations/spouse_palace_tendency.json | 일지 4인자·계절 배우자 성향(판정 인용 금지) | 없음 | 서술 | false("고전 출처 없음") |
| T | spouse_palace_activation.py; partner_star_emergence.py | 배우자궁 활성 7축 벡터·배우자성 투출(shadow) | MT 경유 | shadow | — |
| U | apps/api/.../report_service.py:473-480,650,664,714-724,781,859-867,3477-3486 | F-17/17b/17c 가이드, 배우자상 지시문 | marital_status | 지시문 | — |
| V | report_plan.py:38-39 | F-17b→M04, F-17c→M05 | — | — | — |
| W | saju_engines/query_parser.py:258-284; chat_service.py:1977-1990; conversation.py | 부모어→M04, 자녀어→M05, 형제어→모듈 없음 | — | 라우팅 | — |
| X | relationship_hints.py; companion_alias.py; dictionaries.py:1123-1130 | 동반자 관계 라벨(spouse/parent_child/family) | — | 힌트 | — |
| Y | interpretations/ten_gods_text.json | 비견 "형제", 정인 "어머니 같은 별" 비유 | — | 서술 | false |

## 3. 관찰된 불일치
1. M04/M05 궁위 미사용(docs/09 규격은 년월주·시주 입력). 2. 남명 자녀성: 지시문 "관성=자식" vs M05·childbirth 식상 고정. 3. F-17b "인성 동요 신호"≠코드 CHUNG_RESOURCE_RENEWAL(문서 교체, OFF).
4. 부친·모친 매핑 두 갈래(궁위 월간/월지 vs 십성 인성 통칭), 편재=부친 0건.

## 4. 테스트 고정 현황
test_topic_modules_domain(M04/M05/M06 축), test_realtime_log_misses_20260911(kin axis), test_marriage_resource·flow_modifier·hap_subtype·awareness_seed(성별 배우자성),
test_addendum_gate_modifier(childbirth→creative), test_risk_rel_c5(FAMILY_BURDEN 대상군), test_relation_palace_engine·test_event_engine_v2(월주 career, 인성 충 renewal OFF),
test_palace_relationship_network, test_spouse_palace_tendency, shadow 벡터 3종. **`_PALACE_ROLE` 참조 테스트 없음.**

## 5. 미지원(grep 근거)
특정 지장간 글자 인물 지목 0건 · 편재=부친/정인=모친 개별 매핑 0건 · 시부모(여명 재성=시댁 환경만) · 장인·장모·처가 0건 · 형제 축 모듈 없음(query_parser:262) ·
육친 글자 운→인물 사건 추론(REL_FAMILY_BURDEN 제한적 예외만) · 남명 관성=자녀 이벤트 0건(gender_modifier 소비 코드 0).
