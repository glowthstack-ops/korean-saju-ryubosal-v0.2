# P0-A relation delta 감사 하네스 (RELATIONSHIP_EVENT_SYSTEM 부록 A-3·A-6)

EventEngineV2의 relation delta(배우자궁 합충형파해 가산)가 관계 이벤트 점수·랭킹에
기여하는 정도를 실측한 읽기 전용 감사 스크립트 묶음(2026-07-24 P0-A).

## 방법
- baseline: `EventEngineV2(_DICTS, **marriage_engine_flags())` — chat_service와 동일 생성
- control: 동일 엔진에서 `_relpalace.apply`만 메모리 내 no-op 패치 후 재스코어링
- 교차확인: `contributions["relation"]` + 유닛 격리(합성 발동 직접 투입)

## 파일
- `measure_relation_delta.py` — 본 측정(시나리오 1~3·7, 연 단위)
- `measure_part2.py` — 쟁합·관살혼잡·도화 비활성(시나리오 4~6)
- `measure_unit.py` — 유닛 격리(kind별 순수 delta·cap 포화)
- `measure_addendum.py` — 남성 실전 명식 교차검증
- `measure_addendum2.py` / `measure_addendum3.py` — 월운 경로 교차검증

## 실행
```bash
cd backend && ../.venv/bin/python scripts/audits/relationship_p0a/measure_relation_delta.py
```

## 핵심 결론(요지 — 상세는 SSOT 부록 A-3·A-6)
relation delta는 성별·연월 층위 무관 "방향 무관 배우자궁 활성"으로 동작 — 충·형에서도
marriage_signal을 relationship_change와 동폭(+22 상한 포화)으로 올리고 new_relationship은
항상 0. 방향 누수는 B2 출력 가드로 차단(점수 불변). 결함 고정은
`tests/regression/test_relation_delta_legacy_behavior.py` 참조(characterization/safety 분리).
