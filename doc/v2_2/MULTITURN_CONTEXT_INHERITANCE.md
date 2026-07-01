# 멀티턴 맥락 패키지 상속 (Multi-turn Context Package Inheritance) — v1

> 사용자 리뷰(2026-07-01) 기반. 실로그 재현: 1턴 "난 언제쯤 돈이 생길까?"(재물 타이밍) → 2턴
> "2026년"이 재물 스레드를 잃고 일반 총운(직업/관계/문서)으로 흐른 결함의 SSOT.
> 본 문서는 **초안(reviewed:false)**. 결정론 보강을 먼저 하고 임베딩은 보조 게이트로 뒤에 둔다.

## 0. 핵심 재정의

문제는 "임베딩 정확도"가 아니라 **후속 발화의 맥락 패키지 상속 실패**다. 상속 대상은 domain
하나가 아니라 **`domain + query_type + event_key/event_keys + granularity + offer_context`** 다.
"2026년"은 직전 답변의 "어느 해의 월별 흐름을 볼까요?"에 대한 **슬롯 응답**이며, 이 케이스의
정답은 `domain=WEALTH · query_type=TIMING_SEARCH · event=재물 · time=2026 · granularity=month`이다.

> **"시점 상속" 오해 정정**: 이 케이스는 시점 상속 실패가 아니다. "2026년" 자체는 연도로 정상
> 파싱된다. 실패한 것은 **도메인·질문유형·이벤트·월별 의도·제안 맥락**의 상속이다.

## 1. 근본 원인 (실증, 2026-07-01)

상속 "기계"는 이미 구현돼 있다. `conversation.py process_turn`이 **domain(:138) +
query_type·event(:143-157) + time(:168-184)** 를 상속하며, 전부 `is_follow_up=True` 게이트다.
그리고 `parse_message(prev_intent=…)`의 504 브랜치가 단답+시점이면 prev를 복제+시점 교체한다.

| 후속 | 현재 결과 | 원인 |
|---|---|---|
| "올해" | ✅ wealth·timing·event 상속 | 2순위 시점 정규식(:292-296)이 상대시점 매칭 → follow-up |
| "2026년" | ❌ general/overview | 정규식이 **절대연도 `\d{4}년`을 미매칭** → `link_question`이 NEW → prev 미전달 → 상속 스킵 |
| "2026년 총운" | ✅ general(정답) | 총운=fresh-overview → 상속 금지 |
| "2026년 연애운" | ❌ **wealth 오상속** | `link_question`=domain_shift(follow-up) → prev 전달 → parse_message **504 브랜치가 새 도메인 무시하고 prev(재물) 복제** |

즉 병목은 (a) `link_question`이 절대연도 bare 후속을 못 잡음, (b) parse_message 504가 "연도+새
도메인"에서 prev를 통째 복제함(새 도메인이 이겨야 함 — 사용자 우선순위 #1 위반).

## 2. 후속 판정 우선순위 (사용자 안 채택)

```
1. 명시적 새 도메인 / 총운 / 새 풀이 요청   → 새 스레드 (최우선)
2. 직전 제안에 대한 슬롯 응답(offer-slot)    → 상속 + offer 맥락
3. 순수 시점 슬롯 후속(bare time-slot)       → 상속(TIME_SHIFT)
4. 문맥 결합 임베딩 보조 게이트(P4, 지연)
5. 신규 질문
```

## 3. 변경 계획

### P0 — bare 절대시점 후속 인식 (`conversation.link_question`)
2순위 단답 블록(`len(compact) ≤ 10`)에 절대시점 브랜치 추가:
```
_BARE_ABS_TIME_RE = r"\d{3,4}\s*년|상반기|하반기|연초|연말"
if _BARE_ABS_TIME_RE.search(text)
   and not _detect_domains(text)          # 새 도메인 없음(우선순위 #1 보호)
   and not _FRESH_OVERVIEW_RE.search(text) # '총운' 제외
   and not _READING_REQUEST_RE.search(text):
    return self._follow(parent_id, LinkKind.TIME_SHIFT, state)
```
효과: "2026년"이 follow-up → prev 전달 → parse_message 504가 prev(재물) 복제+시점 교체 →
domain·query_type·event 자동 상속. "2026년 총운/연애운"은 가드로 자연 제외.

### P0b — "연도+새 도메인" 오상속 수정 (`query_parser.parse_message`)
504 브랜치 조건에 `and not _detect_domains(text)` 추가 → 새 도메인이 명시된 단답은 prev를 복제하지
않고 정상 파싱(도메인=텍스트가 이김). "2026년 연애운" → relationship. (테스트 #3 통과)

### P1 — offer-slot 링킹 + granularity=month
- `ConversationState.last_offer: str = ""` 추가. `chat()` 답변 확정 지점(chat_service:2332)에서
  `state.last_offer = _extract_offer(answer)` 저장(비offer면 "" — 자동 만료).
- `link_question`: `state.last_offer`가 있고 단답이며 새도메인/총운/새풀이 아니면 follow-up
  (`LinkKind.TIME_SHIFT` 재사용) — 시점이 아닌 슬롯 답변도 제안과 연결.
- `process_turn`: 후속이고 `last_offer`가 월별 함의(`월별|달별|월\s*단위`)면 상속된 time_range의
  granularity를 `MONTH`로(+`granularity_override`). ("어느 해의 월별 흐름" → 월별)
- chat_service 지시문(2190): 기존 `is_affirm_continue` 게이트를 **follow-up 슬롯 턴**까지 확장해
  `_OFFER_CONTINUE_DIRECTIVE`(직전 제안 이어풀기)를 주입. offer는 `prior_answer`에서 추출(이미 로드됨).

### P2 — 상속 필드 확장
domain·query_type·event는 이미 상속(§1). **granularity 상속만 P1에서 추가**. 그 외 기존 로직 유지.

### P3 — 회귀 테스트(최소 7)
| # | 시나리오 | 기대 |
|---|---|---|
| 1 | 재물 타이밍 → "2026년" | domain=WEALTH, time=2026, (offer시)granularity=month |
| 2 | 재물 타이밍 → "2026년 총운" | GENERAL/FORTUNE_OVERVIEW, 재물 상속 금지 |
| 3 | 재물 타이밍 → "2026년 연애운" | RELATIONSHIP 전환 |
| 4 | 재물 타이밍 → "내년" | WEALTH 상속 |
| 5 | 재물 월별 → "5월" | WEALTH 상속 + month=5 |
| 6 | 이사운 → "2026년" | RELOCATION 상속 |
| 7 | offer 없음 + "2026년" | active_topic 강하면 후속, 아니면 GENERAL |

### P4 — 문맥 결합 임베딩 (지연)
`_augment_domain_by_similarity`의 입력을 `classify(question)` → `classify(직전 질문/offer + 현재)`로
확장. domain·event만 보강(query_type·점수·간지·판정 미개입, 원칙 1·9). **실로그 평가셋 확보 후**
임계 재튜닝(현 doc/INTENT_SIMILARITY 100%는 40건 토이셋 — 과적합 경계).

## 4. 가드/안티회귀 원칙
- **새 도메인 명시가 언제나 최우선**(우선순위 #1). bare-slot·offer-slot은 `not _detect_domains`
  가드 필수.
- 총운/전체운/새 풀이 요청은 상속 금지(`_FRESH_OVERVIEW_RE`/`_READING_REQUEST_RE`).
- 임베딩은 boost/gate 전용 — 점수·간지·판정·query_type 미개입.

## 5. 결정 로그 (2026-07-01 사용자 승인)
1. 문제를 domain 상속 실패가 아니라 **맥락 패키지(domain+query_type+event+granularity+offer) 상속
   실패**로 재정의.
2. `len≥12` 완화 대신 **bare-slot/offer-slot 전용 규칙 + 우선순위**.
3. 임베딩은 단독 발화 분류가 아니라 **문맥 결합 보조**로 이동(P4 지연).
4. **P0b 포함**(연도+새도메인 오상속 수정), **`ConversationState.last_offer` 추가** 승인.
