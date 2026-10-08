# 실사례 픽스처(사고·손실·호전) — 스키마와 운용 (P3, 2026-09-18)

목적: 전문가 참고 기준의 "발생→진행→결과→후속 영향"(부정) / "기회→진행→성취→유지"(긍정) 구분으로 **실제로 일어난 사건**을
기록하고, 엔진 출력(공통 사건 유형·사건 키·위험/기회 family·금지 표현)이 그 사실과 어긋나지 않는지 회귀로 지킨다.
실사례는 만들어내지 않는다 — 운영 중 수집한다(2026-09-18 데굴님: 현재 줄 수 있는 데이터 없음).

- 파일: `backend/tests/fixtures/life_event_cases.jsonl` (한 줄 = 한 사례, `template: true` 행은 러너가 건너뜀)
- 러너: `backend/tests/regression/test_life_event_cases.py` — 사례가 0건이면 skip, 있으면 사례마다 엔진을 돌려 `expect` 대조
- 개인정보: 이름·연락처 금지. 생년월일시·출생지·성별만. `source`에 수집 경로를 적는다.

## 행 스키마
| 필드 | 뜻 |
|---|---|
| caseId | 고유 id(`YYYYMMDD_<도메인>_<n>`) |
| subject | BirthInput 인자(birth_date·birth_time·birth_place_name·gender·latitude·longitude·timezone) |
| domain / valence | 생활 영역(life_event_lexicon areas id) / negative·positive |
| observed | 발생·진행·결과·후속 영향(부정) 또는 기회 발생·진행·실제 성취·유지·후속 효과(긍정) — 자유 텍스트, 시점 포함 |
| period / granularity | 엔진 대조 시점 라벨(`2027-02`)과 단위(month·year) |
| expect.process_types_any | 그 시점 후보의 '사건 유형'에 하나라도 있어야 하는 이름 |
| expect.event_keys_any | 그 시점 후보 사건 키에 하나라도 있어야 하는 키 |
| expect.risk_families_any / opportunity_families_any | 위험/기회 family 기대(비면 검사 안 함) |
| expect.forbidden_claims | dry_run 프롬프트·후보 줄에 나오면 안 되는 문구 |
| reviewed / notes | 감수 여부·비고 |

## 판정 원칙
- 사례는 엔진의 '정답'이 아니라 **어긋남 감지용**이다. 실패 시 규칙을 바로 고치지 말고 WORKLOG에 사례·원인을 기록하고 승인 후 조정한다.
- 손실·탈락은 '경쟁·배분' 유형의 자동 결론이 아니므로, 기대에 '손실·손상'을 넣을 때는 실제 손실이 관찰된 사례만.
