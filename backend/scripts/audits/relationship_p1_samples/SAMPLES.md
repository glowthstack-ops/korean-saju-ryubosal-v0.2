# P1-5 중간 승인 샘플 (2026-07-24)

candidate-linked(22)는 실전 명식 legacy 실측 — 본문 표 참조. 어댑터 단독 사례의 event_adjusted/legacy_delta/legacy_capped는 None(필드 분리).

**해석 주의(승인 §11)**: 표의 activation 값(예: 사례 22의 34.98 strong)은 **합성 전 evidence base 진단 총량**이다 — 같은 root(운 글자)에서 파생된 복수 kind의 단순 합이 포함될 수 있으며, P1-5 root-normalized 최종 축 값이 아니다. 최종 band는 root dedupe·modifier 적용 후 합성기가 재산출한다.

## 사례 요약표

| 사례 | activation | stability(net) | separation | sup/prs | ev | grp | root | 미해소 | 대체 | 비고 |
|---|---|---|---|---|--:|--:|--:|--:|--:|---|
| 01 육합 단독 | evaluated 13.604 (moderate) | evaluated 0.3 (strong) | insufficient_evidence | 0.3/0.0 | 1 | 1 | 1 | 0 | 0 | separation=근거부족(부정 신호 없음≠낮음) |
| 02 충 단독 | evaluated 19.435 (moderate) | evaluated -1.0 (weak) | evaluated 1.0 (strong) | 0.0/1.0 | 1 | 1 | 1 | 0 | 0 | sep strong·stability 음수 |
| 03 합+충 | evaluated 33.039 (strong) | evaluated -0.7 (moderate) | evaluated 1.0 (strong) | 0.3/1.0 | 2 | 1 | 2 | 0 | 0 | 상반 evidence 동시 보존·compound |
| 04 충2(참여자 상이)+형 | evaluated 54.418 (strong) | evaluated -2.8 (weak) | evaluated 1.0 (strong) | 0.0/2.8 | 3 | 1 | 2 | 0 | 0 | 합법적 별도 원인 3(cap 이전 구조) |
| 05 파 단독 | evaluated 11.661 (weak) | evaluated -0.6 (moderate) | evaluated 0.55 (moderate) | 0.0/0.6 | 1 | 1 | 1 | 0 | 0 | 충보다 작은 압력 |
| 06 해 단독 | evaluated 7.774 (weak) | evaluated -0.6 (moderate) | evaluated 0.55 (moderate) | 0.0/0.6 | 1 | 1 | 1 | 0 | 0 |  |
| 07 무발동 | insufficient_evidence | insufficient_evidence | insufficient_evidence | 0.0/0.0 | 0 | 0 | 0 | 0 | 0 | 전 축 근거 없음(0 아님) |
| 08 비일지(월주 충)만 | insufficient_evidence | insufficient_evidence | insufficient_evidence | 0.0/0.0 | 1 | 1 | 1 | 0 | 0 | evidence 보존·배우자궁 축 미평가 |
| 09 완전 동일 hit 2 | evaluated 19.435 (moderate) | evaluated -1.0 (weak) | evaluated 1.0 (strong) | 0.0/1.0 | 1 | 1 | 1 | 0 | 0 | dedupe: evidence 1·dup 2·강도 1회 |
| 10 EXACT+PROVISIONAL 동일 hit | evaluated 13.604 (moderate) | evaluated 0.3 (strong) | insufficient_evidence | 0.3/0.0 | 1 | 1 | 1 | 0 | 1 | 대체: 유효 1·unres 0·superseded 1 |
| 11 같은 기간 천간+지지 | evaluated 33.039 (strong) | evaluated -0.7 (moderate) | evaluated 1.0 (strong) | 0.3/1.0 | 2 | 1 | 2 | 0 | 0 | period 1·signal 2·root 2 |
| 12 RP+MT2 동일 글자(RP측) | evaluated 13.604 (moderate) | evaluated 0.3 (strong) | insufficient_evidence | 0.3/0.0 | 1 | 1 | 1 | 0 | 0 | MT2와 signal 동일 → root 1(합성기) |
| 12 종합판정 | — | — | — | —/— | 2 | 2 | 1 | 0 | 0 | evidence 2종·semantic group 2·root 1 |
| 13 MT2 same_stem | —(축 미평가) | — | — | —/— | 1 | 1 | 1 | 0 | 0 | realization EVALUATED 승격 금지(보조 evidence만) |
| 14 MT2 same_element | — | — | — | —/— | 1 | 1 | 1 | 0 | 0 | base 4.0(약한 tier) |
| 15 MT2 clashed(blocker) | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | 0점 아님 — blocker evidence 1(SPOUSE_PALACE_CLASHED) |
| 16 blocker-only(base 없음) | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | realization=INSUFFICIENT(BLOCKED 아님)+blocker 보존 |
| 17 modifier JAENGHAP | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | effects=['ambiguity_increase', 'stability_support_weaken'] axes=['stability', 'realization'] derived=True — 원인 기여 0 |
| 18 modifier HAPGEO | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | effects=['realization_blocker'] axes=['realization'] derived=False — 원인 기여 0 |
| 20 modifier MULTI_RELATION_STRESS | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | effects=['focus_dilution', 'ambiguity_increase'] axes=['stability'] derived=False — 원인 기여 0 |
| 19 natal static 두 기간 | — | — | — | —/— | 0 | 0 | 0 | 0 | 0 | 동일 ID(natal:GWANSAL_HONJAP==natal:GWANSAL_HONJAP)·기간 누적 0·trigger 없음 |
| 21 순서 역전(정방향) | evaluated 46.559 (strong) | evaluated -1.5 (weak) | evaluated 1.0 (strong) | 0.3/1.8 | 3 | 1 | 3 | 0 | 0 | 역순과 동일=True |

## Evidence 상세표

| Case | ID | Group | Kind | Period | Signal | Prec | Dup | Compound | base | eadj | ldelta | lcap | natal | transit |
|---|---|---|---|---|---|---|--:|---|--:|---|---|---|---|---|
| 01 육합 단독 | spa:sewoon:HAP:day_pillar:branch:::丑:子: | palace_activation | HAP | sewoon:2029 | sewoon:2029:branch:子 | exact | 1 | — | 13.604 | None | None | None | 丑 | 子 |
| 02 충 단독 | spa:sewoon:CHUNG:day_pillar:branch:::丑:未: | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 1 | — | 19.435 | None | None | None | 丑 | 未 |
| 03 합+충 | spa:sewoon:CHUNG:day_pillar:branch:::丑:未: | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 1 | CHUNG+HAP | 19.435 | None | None | None | 丑 | 未 |
| 03 합+충 | spa:sewoon:HAP:day_pillar:branch:::丑:子: | palace_activation | HAP | sewoon:2027 | sewoon:2027:branch:子 | exact | 1 | CHUNG+HAP | 13.604 | None | None | None | 丑 | 子 |
| 04 충2(참여자 상이)+형 | spa:sewoon:CHUNG:day_pillar:branch:::丑:未:natal:day | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 1 | CHUNG+HYEONG | 19.435 | None | None | None | 丑 | 未 |
| 04 충2(참여자 상이)+형 | spa:sewoon:CHUNG:day_pillar:branch:::未:未:natal:year | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 1 | CHUNG+HYEONG | 19.435 | None | None | None | 未 | 未 |
| 04 충2(참여자 상이)+형 | spa:sewoon:HYEONG:day_pillar:branch:::丑:戌: | palace_activation | HYEONG | sewoon:2027 | sewoon:2027:branch:戌 | exact | 1 | CHUNG+HYEONG | 15.548 | None | None | None | 丑 | 戌 |
| 05 파 단독 | spa:sewoon:PA:day_pillar:branch:::丑:戌: | palace_activation | PA | sewoon:2029 | sewoon:2029:branch:戌 | exact | 1 | — | 11.661 | None | None | None | 丑 | 戌 |
| 06 해 단독 | spa:sewoon:HAE:day_pillar:branch:::丑:午: | palace_activation | HAE | sewoon:2029 | sewoon:2029:branch:午 | exact | 1 | — | 7.774 | None | None | None | 丑 | 午 |
| 08 비일지(월주 충)만 | spa:sewoon:CHUNG:month_pillar:branch:::寅:申: | palace_activation | CHUNG | sewoon:2029 | sewoon:2029:branch:申 | exact | 1 | — | 17.969 | None | None | None | 寅 | 申 |
| 09 완전 동일 hit 2 | spa:sewoon:CHUNG:day_pillar:branch:::丑:未: | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 2 | — | 19.435 | None | None | None | 丑 | 未 |
| 10 EXACT+PROVISIONAL 동일 hit | spa:sewoon:HAP:day_pillar:branch:::丑:己: | palace_activation | HAP | sewoon:2029 | sewoon:2029:stem:己 | exact | 1 | — | 13.604 | None | None | None | 丑 | 己 |
| 11 같은 기간 천간+지지 | spa:sewoon:CHUNG:day_pillar:branch:::寅:申: | palace_activation | CHUNG | sewoon:2028 | sewoon:2028:branch:申 | exact | 1 | CHUNG+HAP | 19.435 | None | None | None | 寅 | 申 |
| 11 같은 기간 천간+지지 | spa:sewoon:HAP:day_pillar:branch:::癸:戊: | palace_activation | HAP | sewoon:2028 | sewoon:2028:stem:戊 | exact | 1 | CHUNG+HAP | 13.604 | None | None | None | 癸 | 戊 |
| 12 RP+MT2 동일 글자(RP측) | spa:sewoon:HAP:day_pillar:branch:::丑:己: | palace_activation | HAP | sewoon:2029 | sewoon:2029:stem:己 | exact | 1 | — | 13.604 | None | None | None | 丑 | 己 |
| 12 RP+MT2 동일 글자(MT2측) | pse:sewoon:MT2:same_stem:己 | partner_star_emergence | EMERGENCE | sewoon:2029 | sewoon:2029:stem:己 | exact | 1 | — | 10.0 | None | None | None | 己 | 己 |
| 21 순서 역전(정방향) | spa:sewoon:CHUNG:day_pillar:branch:::丑:未: | palace_activation | CHUNG | sewoon:2027 | sewoon:2027:branch:未 | exact | 1 | CHUNG+HAP+HYEONG | 19.435 | None | None | None | 丑 | 未 |
| 21 순서 역전(정방향) | spa:sewoon:HAP:day_pillar:branch:::丑:子: | palace_activation | HAP | sewoon:2027 | sewoon:2027:branch:子 | exact | 1 | CHUNG+HAP+HYEONG | 13.604 | None | None | None | 丑 | 子 |
| 21 순서 역전(정방향) | spa:wolwoon:HYEONG:day_pillar:branch:::丑:戌: | palace_activation | HYEONG | wolwoon:2027 | wolwoon:2027:branch:戌 | exact | 1 | CHUNG+HAP+HYEONG | 13.52 | None | None | None | 丑 | 戌 |

## 사례 22 — candidate-linked (C1 여성 1985-03-15, 2027 丁未 세운)

| 이벤트 | legacy score(ctrl→base) | conf | rank(ctrl→base) | event_adjusted(pre-cap) | legacy_delta | capped |
|---|---|---|---|--:|--:|---|
| marriage_signal | 61→86 | strong_event_candidate | 6→4 | 54.4 | 22.0 | True |
| new_relationship | 23→23 | weak_event_candidate | 13→13 | 0.0 | 0.0 | False |
| relationship_change | 62→86 | strong_event_candidate | 4→5 | 65.3 | 22.0 | True |

어댑터 벡터(동일 활성·EXACT): activation=34.983(strong) / stability net=-1.8(sup 0.0/prs 1.8) / separation=1.0(strong) / evidence 2·root 1 — base 합=34.983(이벤트 무관 — 위 pre-cap과 의미 분리)

shadow 전후 legacy score/confidence/rank: **완전 동일**(벡터는 별도 산출 — 엔진 미개입).
