# D0 종료 — 무료 오늘의 사주 관계 의미론

> 판정: **적용 대상 없음 · 미착수 종료** · 기록일 2026-07-27
>
> "문제가 발견되지 않았다"가 아니라 **"현재 출력 계약상 발생 경로가 없다"**로 기록한다.
> 출력 필드가 확장되면 재검토해야 하므로 재개 조건을 함께 남긴다.

## 배경

개인 총운(챗)에서 관계 의미 역전이 실제로 발생했다 — 엔진이 `寅亥合 → 합반·합거 ·
壬/甲 흉 제거(유리)`로 판정했는데 답변은 "합하여 기신 木을 강화한다"로 정반대를 냈다.
이를 canonical claim + 결정론적 문장 교체로 고쳤다.

무료 오늘의 사주(`daily_ilju_fortune`)도 `half_harmony`·`punishment_full` 등 관계
종류를 계산하므로 같은 역전이 가능한지 조사했다.

## 조사한 경로

```
출력 타입   DailyIljuFortune
필드        ilju · ilju_ko · day_stem_ko · headline · headline_event_key
            events(3) · lucky_place · lotto_phrase · love_line · polished
            → 관계를 서술하는 필드가 없다

headline    _headline(dicts, headline_event.event_key, band, seed, salt)
            → 사전에서 event_key로 조회. 관계 종류를 문장화하지 않는다

관계 사용처  _branch_relations(day↔ilju, month↔ilju, year↔ilju)
            → relation_affinity 가중치로 **점수 계산에만** 소비

LLM polish  build_polish_payload → {ilju, event_key, headline, place_phrase, lotto}
            → relation_type·관계 근거가 payload에 없다
```

## 판정 근거

```
- 관계 유형은 relation_affinity 점수 입력으로만 사용된다
- 사용자 출력 필드에 관계 설명 필드가 없다
- headline은 event_key 사전에서 생성된다
- LLM polish payload에 relation_type·관계 근거가 없다
- LLM이 반합·합반·충·형을 재해석할 입력 자체가 없다

→ 개인 총운에서 발생한 관계 의미 역전이 구조적으로 재현되지 않는다
```

canonical claim이나 에코 감사를 여기 추가하면 보호가 아니라 **불필요한 복잡성만
늘어난다**(관계를 말하지 않는 상품에 관계 서술 가드를 다는 셈).

## 재개 조건 — 아래 중 하나가 생기면 재검토한다

```
- relation_type 또는 relation_claim이 LLM polish payload에 추가됨
- headline · events · love_line에서 관계명을 직접 서술하기 시작함
- 합·충·형 관계를 사용자에게 근거로 노출하는 기능이 추가됨
- LLM이 원시 relation_affinity 근거를 받아 자유 서술하게 됨
```

이 중 하나가 생기기 전에는 관계 의미론 패치를 무료 상품에 적용하지 않는다.

## 조사 중 정정한 오판

최초 판단은 "`half_harmony`를 계산하므로 반합을 합반으로 오서술할 수 있다"였다.
이는 **계산과 서술을 혼동한 것**이다. 관계를 계산한다는 사실이 관계를 문장화한다는
뜻은 아니다. 이후 유사 조사에서도 **출력 필드와 LLM payload를 먼저 확인**한다.

## 상품별 적용 범위 (현재 확정)

| 상품 | 관계 의미론 | 계층형 grounding · 층위 캡 |
|---|---|---|
| 챗 총운(일·월·연) | 적용됨 | 적용됨 |
| 챗 도메인 질문(이직·연애 등) | 미적용 | 미적용 — D1 경로 감사 대상 |
| 테마사주 리포트 | 미적용 | 미적용 — D2 별도 사이클 |
| 무료 오늘의 사주 | **대상 없음** | **적용 금지**(chartless — 개인 대운 없음) |

무료 상품에 개인 운의 층위 위계·사건 판단을 가져오는 것은 어떤 경우에도 금지한다.

## 관련 코드

- `saju_engines/daily_ilju_fortune.py` — `_branch_relations` · `_headline`
- `shared_types/daily_fortune.py` — `DailyIljuFortune` 출력 계약
- `saju_api/services/daily_fortune_polish.py` — `build_polish_payload`
