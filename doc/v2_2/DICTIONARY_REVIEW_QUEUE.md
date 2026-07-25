# 사전 감수 대기 목록 (별도 릴리즈)

> 기능 개발 완료 조건과 **분리된** 목록이다. 사전 감수를 기능 출시 게이트로 묶으면
> 감수 표본이 쌓이기 전에 전체 일정이 멈춘다(D22 — "내부 검수 후 오픈" 모델 폐기).

## 원칙

- 구조 검증과 명리 감수는 다르다. 전자는 컴파일 파이프라인이 보장하고, 후자는 사람의
  판단이다. **파이프라인 통과가 `reviewed` 를 참으로 만들지 않는다.**
- `reviewed:false` 인 채로 서비스하는 것 자체는 금지가 아니다. 금지는 **감수하지 않은
  것을 감수했다고 기록**하는 것이다.
- 빠르게 끝낸다는 이유로 `reviewed:true` 로 바꾸지 않는다 — 어떤 규칙을 승인했는지
  추적할 수 없게 된다.

## 오늘의 운세 사전 3종 (2026-07-26 등록)

| 사전 | 버전 | 구조 검증 | 명리 감수 |
|---|---|---|---|
| `daily_fortune/daily_event_catalog.json` | dict.v1.7 | passed | **대기** |
| `daily_fortune/daily_phrase_templates.json` | dict.v1.7 | passed | **대기** |
| `daily_fortune/daily_lucky_places.json` | dict.v1.7 | passed | **대기** |

**우선순위 근거**: 60일주 전체 사용자에게 매일 반복 노출되므로, 잘못된 규칙 하나의
노출 범위가 커리어 beta 보다 넓다. 다만 커리어 완료 조건은 아니다.

**현재 보호 장치**(감수 전에도 유지되는 것):
- `validate → compile(snapshot) → regression` 파이프라인 통과분만 서비스
  (`compiled/daily_fortune_{DICT_VERSION}.json`, `structural_validation: passed`)
- 사전 수정 후 `DICT_VERSION` 미갱신·재컴파일 누락은 회귀가 차단
  (`tests/regression/test_daily_fortune_snapshot.py`)
- 금지어·한자 노출·로또 정책·커버리지는 `tests/unit/test_daily_fortune_dicts.py`

**감수 후 절차**: 해당 파일의 `reviewed` 를 `true` 로, `review_note` 를 감수자·일자로
바꾸고 `DICT_VERSION` 을 올린 뒤 `python scripts/build_daily_fortune_snapshot.py` 재실행.

## 그 외 대기분

- 위험 사전 REL 7 · MOV 6 · HLT 8 · LEG 6 — `doc/v2_2/RISK_DICTIONARY_REVIEW.md`
- 지역 오행 Tier B — `doc/v2_2/docs/12_REGION_ELEMENT_ENGINE.md`
