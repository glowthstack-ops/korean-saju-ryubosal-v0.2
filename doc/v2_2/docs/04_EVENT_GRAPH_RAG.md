# 04. Event Graph RAG 스펙

## 개념

문헌을 그래프로 저장하는 것이 아니라, **만세력 엔진이 계산한 운의 작용을 사건 후보 그래프로 변환**하는 구조 (Event Graph RAG). 최종 답변보다 먼저 "이벤트 경로(evidence path)"를 산출한다.

```
사주 엔진 결과 → Event Graph Builder → 이벤트 후보 그래프
→ Graph Retrieval (intent 서브그래프만) → 근거 경로 추출 → LLM
```

Vector RAG(기존 공망 CSV 등 문헌/문체/사례)와는 **하이브리드**:
- Graph RAG: 합충형파해 이벤트 추론, 용신/기신 길흉 반전, 근거 경로
- Vector RAG: 고전 문헌 설명, 풀이 문체, 사례 기반 표현 보강

## 구현 방침

처음부터 Neo4j 등 그래프 DB로 가지 않는다. **JSON 그래프 + TypeScript Graph Builder**로 시작:

```
dictionaries/*.json → build-event-graph.ts → compiled/event_graph_vX.Y.Z.json
                                            → 런타임: 인메모리 인접 리스트 탐색
```

노드 수천 개 수준에서는 인메모리 BFS/DFS로 충분. PostgreSQL 적재는 사례 데이터가 쌓인 뒤 검토.

## 노드 타입

```typescript
type NodeType =
  // 명식 노드
  | 'stem' | 'branch' | 'hidden_stem' | 'ten_god' | 'element' | 'palace' | 'twelve_stage'
  // 운 노드 (시간축 — Temporal)
  | 'daewoon' | 'year_luck' | 'month_luck' | 'day_luck'
  // 관계 노드
  | 'combination' | 'clash' | 'punishment' | 'break' | 'harm' | 'self_punishment'
  | 'void' | 'duplication' | 'fuyin' | 'ganyeo_jidong'
  // 판정 노드
  | 'yongsin' | 'huisin' | 'gisin' | 'gusin' | 'strength' | 'excess_deficiency'
  // 이벤트 노드
  | 'event'           // Event Taxonomy의 EventKey
  // 규칙 노드
  | 'interpretation_rule' | 'prohibition_rule';

interface GraphNode {
  id: string;          // 'stem_甲', 'rel_甲己合', 'event_career_change'
  type: NodeType;
  label: string;       // 사용자 노출용 한글
  attrs: Record<string, unknown>;
}
```

## 엣지 타입

```typescript
type EdgeType =
  | 'contains'           // 운 → 천간/지지
  | 'has_ten_god'        // 甲 → 정관 (일간 기준)
  | 'has_element'
  | 'has_palace'
  | 'combines_with'      // 甲 ↔ 己
  | 'conflicts_with'     // 子 ↔ 午
  | 'punishes'
  | 'generates'          // 생
  | 'overcomes'          // 극
  | 'activates'          // 운 → 관계 성립
  | 'boosts' | 'weakens' | 'cancels'
  | 'is_favorable_for' | 'is_unfavorable_for'   // 용신/기신
  | 'triggers'           // 관계 → 이벤트
  | 'manifests_as'       // 이벤트 → 구체 형태
  | 'supports' | 'contradicts'                   // 보조/충돌 근거
  | 'prohibits_style';   // 금기 표현 규칙 연결

interface GraphEdge {
  from: string; to: string; type: EdgeType;
  weight?: number;       // triggers 엣지의 base 기여도
  modes?: string[];      // 합화/합반/합래/합거 등 후보 모드
}
```

## 변환 예시 (월운 → 그래프)

```
[甲午 월운]
  ├─ contains → [甲]
  ├─ contains → [午]
  ├─ activates → [甲己合]        (원국 己 존재 시)
  └─ time_scope → [2026-06]

[甲]
  ├─ has_ten_god(己기준) → [정관]
  ├─ has_element → [木]
  └─ is_unfavorable_for → [己日干]   (기신 판정 시)

[甲己合]
  ├─ can_trigger → [career_change]  (weight 18)
  ├─ can_trigger → [relocation]
  └─ mode_candidate → [합래 | 합반]

[career_change]
  ├─ polarity ← because [정관 + 기신] → negative_or_forced
  └─ manifests_as → [이직 | 역할변경 | 조직개편]
```

## Retrieval 규칙

1. **전체 검색 금지**. intent의 graphScope(EventKey 목록)에서 역방향으로 `triggers` 엣지를 따라 관련 신호 노드만 탐색.
2. 경로 깊이 제한: 기본 5 hop. evidence path는 `운 노드 → 간지 → 관계 → 판정 보정 → 이벤트` 순서로 정규화.
3. 충돌 근거(`contradicts`)도 함께 반환 — LLM이 일방적 단정을 하지 않도록.
4. `prohibition_rule` 노드는 해당 이벤트에 연결된 것을 항상 첨부 (예: windfall → "당첨 단정 금지").

## Retrieval 출력

```typescript
interface EvidenceBundle {
  eventKey: EventKey;
  paths: EvidencePath[];
  supports: string[];        // 보조 근거 노드 ID
  contradicts: string[];     // 충돌 근거 노드 ID
  prohibitions: string[];    // 금기 표현 규칙
  interpretationHints: string[];  // 해석 규칙 노드의 텍스트
}

interface EvidencePath {
  nodes: string[];           // ['month_2026-06_甲午','stem_甲','tengod_정관','rel_甲己合','gisin_木','event_career_change']
  readable: string[];        // 사용자/LLM용: ['甲午 월운','甲 유입','己일간에게 정관','갑기합','甲木 기신','직업 변화']
  weightSum: number;
}
```

## 사람용 근거 경로 표현 (최종 산출물 형태)

```
甲午 월운
→ 甲이 들어옴
→ 己일간에게 甲은 정관
→ 甲은 원국 己와 갑기합
→ 정관은 직업, 규칙, 상사, 제도, 책임, 압박, 계약 신호
→ 그런데 甲木이 기신
→ 기본적으로는 부담 있는 직업 변화, 원치 않는 책임, 압박성 제안으로 나타나기 쉬움
→ 그러나 甲己合이 합화토로 성립하거나, 午火가 통관 역할을 하면 결과가 완전히 부정적이지만은 않을 수 있음
→ 土가 용신·희신이면 나를 돕는 기반, 자리, 계약, 정착으로 전환
```

이 readable path가 "왜 이런 풀이가 나왔는가"를 설명하는 유료 서비스의 핵심 차별점이다.
