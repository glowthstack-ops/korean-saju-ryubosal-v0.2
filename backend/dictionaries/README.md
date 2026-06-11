# 사전 데이터 (dictionaries)

v2.2 룰 사전의 **원본**(source of truth)을 둔다. 운영에는 직접 반영하지 않는다 —
`validate → compile(snapshot) → regression test → 배포` 파이프라인을 거친다
(절대 원칙 5, docs/05·07).

## 규칙

- UTF-8 (BOM 없음) JSON. 사례 데이터는 JSONL.
- 명리 내용(매핑·가중치)은 도메인 검수가 필요하다. 초안의 모든 항목에 `reviewed: false`를
  붙이고, 사용자 검수 후 `true`로 전환한다(docs/07 Phase 1 주의).
- 한자 간지(甲, 亥 등)는 데이터/키에, 사용자 노출 문자열은 한글 병기.

## 디렉토리 (목표 — docs/05·07)

```
dictionaries/
  common/            # stems, branches, ten_gods, elements
  relations.json     # 천간합/지지합/충형파해/공망 등
  events/
    taxonomy.json    # EventKey + progress/instant/hybrid
    career_change.json
    relocation.json
  favorability_rules.json
```

검증·컴파일은 `backend/scripts/validate_dictionaries.py`가 담당한다(현재 골격).
