# OA-10a — 일별 선택 원장 스키마 설계안

> **상태: 조건부 승인 → 구현 착수.** 아래 세 결정이 반영됐다.
> taxonomy 병합 · G0 활성화 · `DICT_VERSION` 승격 · C10 라이브 활성화는 계속 보류.
>
> | 결정 | 확정 |
> |---|---|
> | `history_contract_version` 호환성 | **코드 상수 registry** — DB 테이블 없음 |
> | 과거 90일 | **`CONTRACT_REPLAY`** — `LIVE_COMMITTED` 표기 금지 |
> | 과거 표시 정책 | **`display-selection.legacy-v0`** (별도 고정 adapter) |
>
> 구현 위치: `backend/migrations/017_daily_selection_ledger.sql` ·
> `saju_engines/daily_selection_contracts.py`

C10(`P4_LC_C10`)은 이전 날짜의 선택 결과에 의존한다. 메모리 내 순차 재생만으로는
운영할 수 없으므로, **DB 원자성이 최종 SSOT**이고 Redis는 보조 캐시가 되는 3계층
원장을 둔다.

```
생성 시도            daily_fortune_board_generation   어떤 계약·history 로 만들었나
60일주 결과 원장     daily_fortune_selection_ledger   무엇을 골랐고 왜 골랐나
날짜별 활성 포인터   daily_fortune_active_board       그 날짜의 게시 기준은 무엇인가
```

이 분리가 있어야 백필을 staging 에서 검증한 뒤 **원자적으로 교체**할 수 있고,
동시 생성·재기동·정책 전환이 안전해진다.

---

## 1. DDL 초안

리포 관례를 따른다 — `backend/migrations/017_daily_selection_ledger.sql`,
`CREATE TABLE IF NOT EXISTS`, `TIMESTAMPTZ`, `JSONB`, 한국어 주석.

### 1-1. 보드 생성 단위

```sql
CREATE TYPE daily_generation_status AS ENUM ('STAGING', 'COMMITTED', 'ABORTED');

CREATE TYPE daily_generation_source AS ENUM (
    'LIVE_PREGEN',        -- 23:50 KST 선생성
    'LIVE_ON_DEMAND',     -- 캐시 미스 시 요청 경로 생성
    'CONTRACT_REPLAY',    -- 원장이 없어 당시 계약으로 재현 (실제 게시본이 아님)
    'BACKFILL_REPLAY'     -- 결손·변경 이후 날짜순 재생
);

CREATE TABLE IF NOT EXISTS daily_fortune_board_generation (
    generation_id                UUID PRIMARY KEY,
    fortune_date                 DATE NOT NULL,
    generation_status            daily_generation_status NOT NULL DEFAULT 'STAGING',
    generation_source            daily_generation_source NOT NULL,

    -- 계약 4종. 하나라도 다르면 다른 결과가 나올 수 있다.
    selection_policy_version     TEXT NOT NULL,   -- 이 결과를 만든 표시 정책
    history_contract_version     TEXT NOT NULL,   -- 이 결과를 장기 이력으로 읽는 계약
    taxonomy_version             TEXT NOT NULL,
    active_dict_version          TEXT NOT NULL,
    content_version              TEXT NOT NULL,
    event_selection_contract     TEXT NOT NULL,   -- 동결값(engine.v1|dict.v1.9|polish.v1)

    -- 어떤 이력을 읽고 만들었는가
    history_start_date           DATE NOT NULL,
    history_end_date             DATE NOT NULL,
    history_set_fingerprint      TEXT NOT NULL,
    engine_input_fingerprint     TEXT NOT NULL,
    board_result_fingerprint     TEXT,

    -- 제약 완화 결과 (승인된 override 만 허용된다)
    authorized_domain_overrides  INTEGER NOT NULL DEFAULT 0,
    event_cap_relaxations        INTEGER NOT NULL DEFAULT 0,
    constraint_outcomes          JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    committed_at                 TIMESTAMPTZ,
    replay_batch_id              UUID,

    -- 미래 누수 차단: 오늘 이력을 오늘 보드에 쓸 수 없다.
    CONSTRAINT dfbg_history_is_past
        CHECK (history_end_date < fortune_date),
    CONSTRAINT dfbg_history_range
        CHECK (history_start_date <= history_end_date),
    -- COMMITTED 는 결과 지문과 시각을 반드시 갖는다.
    CONSTRAINT dfbg_committed_needs_result CHECK (
        generation_status <> 'COMMITTED'
        OR (board_result_fingerprint IS NOT NULL AND committed_at IS NOT NULL)
    ),
    -- 설명되지 않은 domain 초과는 저장 자체를 막는다(가드를 DB 로 내린다).
    CONSTRAINT dfbg_no_unauthorized_overflow CHECK (
        (constraint_outcomes ->> 'domain_cap_hard_violation') IS NULL
        OR (constraint_outcomes ->> 'domain_cap_hard_violation')::int = 0
    )
);
```

### 1-2. 일주별 선택 원장

```sql
CREATE TABLE IF NOT EXISTS daily_fortune_selection_ledger (
    generation_id                   UUID NOT NULL
        REFERENCES daily_fortune_board_generation(generation_id) ON DELETE CASCADE,
    fortune_date                    DATE NOT NULL,
    ilju                            TEXT NOT NULL,       -- 한자 2자

    raw_good_winner                 TEXT NOT NULL,
    raw_good_probability            SMALLINT NOT NULL,
    raw_good_band                   TEXT NOT NULL,       -- s5|s4|s3|s2

    display_good_representative     TEXT NOT NULL,
    display_good_probability        SMALLINT NOT NULL,
    display_good_band               TEXT NOT NULL,
    display_good_semantic_family    TEXT NOT NULL,

    support_event                   TEXT NOT NULL,
    caution_event                   TEXT NOT NULL,

    raw_headline                    TEXT NOT NULL,       -- 보드 캡 이전
    final_headline                  TEXT NOT NULL,       -- 보드 캡 이후 = 게시본
    final_headline_semantic_family  TEXT NOT NULL,

    good_selection_reason           TEXT NOT NULL,
    display_displacement_loss       SMALLINT NOT NULL,

    selection_reason_codes          TEXT[] NOT NULL DEFAULT '{}',
    watch_codes                     TEXT[] NOT NULL DEFAULT '{}',

    raw_supporting_groups           SMALLINT,
    display_supporting_groups       SMALLINT,

    ilju_history_fingerprint        TEXT NOT NULL,
    row_result_fingerprint          TEXT NOT NULL,

    PRIMARY KEY (generation_id, ilju),
    CONSTRAINT dfsl_probability_range CHECK (
        raw_good_probability BETWEEN 5 AND 95
        AND display_good_probability BETWEEN 5 AND 95
    ),
    -- 손실은 예산 안이고 음수가 아니다.
    CONSTRAINT dfsl_loss_budget CHECK (display_displacement_loss BETWEEN 0 AND 7),
    -- s5 는 어떤 경우에도 하위 밴드로 내려가지 않는다(C10 계약을 DB 로 내린다).
    CONSTRAINT dfsl_exceptional_band_protected CHECK (
        raw_good_band <> 's5' OR display_good_band = 's5'
    ),
    -- 두 단계 이상 하락 금지.
    CONSTRAINT dfsl_no_two_band_drop CHECK (
        NOT (raw_good_band = 's4' AND display_good_band IN ('s2'))
        AND NOT (raw_good_band = 's3' AND display_good_band = 's2')
    ),
    -- 대표를 바꾸지 않았으면 손실이 0 이다.
    CONSTRAINT dfsl_loss_consistency CHECK (
        display_good_representative <> raw_good_winner OR display_displacement_loss = 0
    )
);
```

**`semantic_family` 를 하나만 두지 않는다.** C10 은 두 이력을 각각 쓴다 —
`final_headline_semantic_family` 는 사용자 최종 노출(1차 판정),
`display_good_semantic_family` 는 good 슬롯 본문 반복 억제(보조 판정)에 쓰인다.

`selection_reason_codes` 허용값(부분집합 형태로 저장):

```
RAW_GOOD_WINNER_SELECTED
LONGITUDINAL_ALTERNATIVE_SELECTED
LOSS_BUDGET_EXCEEDED
EXCEPTIONAL_SIGNAL_BAND_DOWNGRADE_BLOCKED
LONGITUDINAL_ONE_BAND_DOWNGRADE_SELECTED
STRONG_EVIDENCE_ASYMMETRY
EVENT_CAP_RELAXED_TO_PROTECT_DOMAIN
DOMAIN_CAP_INFEASIBLE_AFTER_EVENT_CAP_RELAXATION
```

`watch_codes` 는 하드 차단 없이 기록만 하는 관찰용이다(현재 `STRONG_EVIDENCE_ASYMMETRY`
72건/270일). canary 표본 감수 대상이며 출시 차단에 쓰지 않는다.

### 1-3. 날짜별 활성 보드 포인터

```sql
CREATE TYPE daily_activation_reason AS ENUM (
    'LIVE_INITIAL', 'REPLAY_RECOVERY', 'BACKFILL_REPLACEMENT', 'EMERGENCY_ROLLBACK'
);

CREATE TABLE IF NOT EXISTS daily_fortune_active_board (
    fortune_date        DATE PRIMARY KEY,
    generation_id       UUID NOT NULL
        REFERENCES daily_fortune_board_generation(generation_id),
    activated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    activation_reason   daily_activation_reason NOT NULL,
    activation_version  BIGINT NOT NULL DEFAULT 1
);
```

**서비스는 원장의 최신 행이나 임의의 `COMMITTED` 행을 읽지 않는다.**
언제나 active pointer 가 가리키는 generation 만 조회한다.

---

## 2. enum·check 요약

| 대상 | 방식 | 이유 |
|---|---|---|
| `generation_status` · `generation_source` · `activation_reason` | PostgreSQL ENUM | 값 집합이 고정이고 오타를 DB 가 막는다 |
| `selection_reason_codes` · `watch_codes` | `TEXT[]` + 애플리케이션 검증 | 코드가 슬라이스마다 늘어난다. ENUM 이면 migration 이 계속 필요하다 |
| 미래 누수 · 손실 예산 · s5 보호 · 2단계 하락 | CHECK | **계약을 코드에만 두지 않는다.** 잘못된 행은 저장 자체가 실패해야 한다 |
| `domain_cap_hard_violation = 0` | CHECK on JSONB | 설명되지 않은 overflow 는 커밋 불가 |

---

## 3. partial unique index

```sql
-- 날짜당 활성 대상이 될 수 있는 COMMITTED generation 은 계약 조합별 1개.
-- 같은 입력·같은 이력으로 다시 계산하면 기존 generation 을 재사용하게 만든다.
CREATE UNIQUE INDEX IF NOT EXISTS dfbg_committed_identity
    ON daily_fortune_board_generation (
        fortune_date, selection_policy_version,
        history_set_fingerprint, engine_input_fingerprint
    )
    WHERE generation_status = 'COMMITTED';

-- 진행 중 STAGING 은 (날짜, 정책, batch) 당 1개만 — 중복 계산을 조기에 막는다.
CREATE UNIQUE INDEX IF NOT EXISTS dfbg_staging_single
    ON daily_fortune_board_generation (
        fortune_date, selection_policy_version, COALESCE(replay_batch_id, generation_id)
    )
    WHERE generation_status = 'STAGING';

-- history 조회 경로 (D-90 ~ D-1 범위 스캔)
CREATE INDEX IF NOT EXISTS dfsl_history_lookup
    ON daily_fortune_selection_ledger (ilju, fortune_date);
CREATE INDEX IF NOT EXISTS dfbg_date_status
    ON daily_fortune_board_generation (fortune_date, generation_status);
```

`UNIQUE(fortune_date, ilju, selection_policy_version)` 형태는 **쓰지 않는다** —
정책이 바뀌어도 C10 은 사용자가 이전 정책에서 본 이력을 읽어야 하고, 롤백 후에도
그 기간에 실제 게시된 결과가 history 에서 사라지면 안 되기 때문이다.

---

## 4. active pointer CAS

```sql
-- 신규
INSERT INTO daily_fortune_active_board
    (fortune_date, generation_id, activation_reason, activation_version)
VALUES ($1, $2, $3, 1)
ON CONFLICT (fortune_date) DO NOTHING
RETURNING activation_version;

-- 교체 (기대 버전이 일치할 때만)
UPDATE daily_fortune_active_board
   SET generation_id      = $2,
       activation_reason  = $3,
       activated_at       = now(),
       activation_version = activation_version + 1
 WHERE fortune_date       = $1
   AND activation_version = $4        -- 읽은 시점의 버전
RETURNING activation_version;
```

0행이 반환되면 다른 worker 가 먼저 교체한 것이다 — 재시도하지 않고
`ACTIVATION_CONFLICT` 로 종료한다(자기 결과를 덮어쓰지 않는다).

---

## 5. advisory lock 키

`pg_advisory_xact_lock(bigint)` 는 transaction 종료 시 자동 해제되므로 누수가 없다.

```sql
SELECT pg_advisory_xact_lock(
    hashtextextended(
        $1::text || '|' || $2::text,   -- fortune_date | display_selection_policy_version
        0
    )
);
```

두 층을 쓴다:

* **Redis 락** — 불필요한 중복 계산 방지(성능). 실패해도 정합성은 깨지지 않는다.
* **PG advisory lock + CAS** — 최종 원자성 보장(정합성).

Redis 락만으로 원장 일관성을 보장하지 않는다.

---

## 6. 하루 생성 transaction sequence

```
1.  Redis 락 시도 (선택적 · 중복 계산 방지)
2.  BEGIN
3.  pg_advisory_xact_lock(fortune_date | policy_version)
4.  D-90 ~ D-1 active history 조회
      → 결손이 있으면 §8 fail-closed 경로
5.  history_set_fingerprint 계산
6.  동일 (date, policy, history_fp, input_fp) COMMITTED generation 조회
      → 있으면 재사용하고 9번으로
7.  STAGING generation INSERT
8.  60일주 순차 선택 → selection ledger 60행 INSERT
      → 불변식 검증(60행 · 슬롯 3종 · 도메인 2종 이상 · 손실 예산 · s5 보호)
      → board_result_fingerprint 계산 후 COMMITTED 로 UPDATE
9.  active pointer CAS (§4)
10. COMMIT
11. 보드 캐시 생성 (§9)
```

**캐시는 원장보다 먼저 쓰지 않는다.** 순서가 뒤집히면 캐시가 원장에 없는 결과를
서비스하게 된다.

### 재실행 판정

동일한 `(fortune_date, selection_policy_version, history_set_fingerprint,
engine_input_fingerprint)` 가 이미 COMMITTED 이면 그 generation 을 재사용한다.
다시 계산했는데 `board_result_fingerprint` 가 다르면 **자동 덮어쓰지 않고**
`NONDETERMINISTIC_REPLAY_DETECTED` 로 실패시킨다 — 결정론이 깨진 것은 버그이지
정상 상태가 아니다.

---

## 7. backfill batch transaction sequence

과거 하루가 결손·변경되면 그 하루만 채우면 안 된다. 상태 기반 선택이므로 이후
날짜가 연쇄적으로 달라진다.

```
REPLAY_PLANNED
  earliest_affected_date ~ end_date 산출, replay_batch_id 발급
REPLAY_RUNNING
  날짜 오름차순으로 STAGING generation 생성 (배치 내 이력은 배치 결과를 사용)
REPLAY_VALIDATED
  전 날짜 × 60일주 행 수 · fingerprint · 불변식 검증
REPLAY_ACTIVATED
  단일 transaction 에서 활성 포인터 일괄 CAS 교체
REPLAY_ABORTED
  staging 폐기, 기존 active generation 유지
```

원본 active generation 은 새 batch 가 **완전히** 활성화될 때까지 유지한다.
과거 하루의 행만 덮어쓰는 방식은 금지한다.

---

## 8. history 호환성 판정과 fail-closed

### 8-1. 조회 조건

정책 버전이 같은 행이 아니라 **그 날짜에 실제 게시된 결과**를 읽는다.

```
D-90 <= fortune_date <= D-1
AND 해당 날짜의 active generation
AND history_contract_version 이 현재 정책과 호환
```

### 8-2. `CONTRACT_REPLAY` 는 `LIVE_COMMITTED` 가 아니다

| 값 | 의미 |
|---|---|
| `LIVE_PREGEN` · `LIVE_ON_DEMAND` | 서비스가 원장을 사용해 실제 게시한 결과 |
| `CONTRACT_REPLAY` | 원장이 없어 **당시 라이브 계약으로 재현**한 결과 |

C10 최초 배포 전 90일은 대부분 `CONTRACT_REPLAY` 가 된다. 신뢰 가능한 replay 로
인정하려면 다음이 모두 그 날짜의 값과 같아야 한다 — `active_dict_version` ·
`content_version` · display selection policy · seed 계약 · domain rebalance 계약 ·
taxonomy 매핑. **재현할 수 없는 옛 계약에 버전 문자열만 붙여 현재 코드로 실행하지
않는다.**

### 8-3. taxonomy 매핑

C10 이 `semantic_family` 를 정책 입력으로 쓰므로 taxonomy 는 이제 SSOT 다.
과거 `event_key` → 현재 family 매핑을 기록한다:

```
taxonomy_version · event_key · canonical_semantic_family · mapping_status
```

허용은 `EXACT` · `EXPLICIT_COMPAT_MAPPING` 뿐이다. `UNKNOWN` 을 새 family 로
임의 처리하거나 매핑 누락을 "미사용 family" 로 처리하는 것은 금지한다 — 후자는
그 사건을 90일 미사용으로 오인해 결과를 크게 흔든다.

### 8-4. 결손 시 처리

```
history 결손 발견
→ HISTORY_INCOMPLETE_REPLAY_REQUIRED
→ 결정론적 replay 시도
   성공 → C10 실행
   실패 → HISTORY_REPLAY_FAILED
        → HISTORY_INCOMPLETE_FAIL_CLOSED_TO_LEGACY
```

**빈 이력으로 C10 을 실행하지 않는다.** 모든 사건이 "90일 미사용" 으로 인식되어
결과가 크게 흔들린다. fallback 은 아직 라이브가 아닌 P4 가 아니라 **릴리즈 직전의
현행 라이브 선택 정책**(`display-selection.legacy-v0` = 원시 good 1위 + 현행
`_rebalance_headlines`)이다.

---

## 9. 캐시·락 키

```
board cache key
    daily:board:{fortune_date}:{content_version}
         :{display_selection_policy_version}:{board_result_fingerprint}

lock key
    daily:lock:{fortune_date}:{display_selection_policy_version}
```

`history_snapshot_version` 같은 증가 번호는 쓰지 않는다 — 원장 내용과의 실제 연결을
증명하지 못한다. `board_result_fingerprint`(또는 `active_generation_id`)를 포함해야
캐시가 어느 원장 결과인지 확정된다.

정책·사전 버전이 다르면 캐시·락·원장 조회가 모두 분리된다.

---

## 10. migration·rollback

```
017_daily_selection_ledger.sql
```

* `CREATE TABLE IF NOT EXISTS` · `CREATE TYPE` 은 `DO $$ ... EXCEPTION WHEN
  duplicate_object` 로 감싼다(재실행 안전).
* 기존 테이블 변경 없음 — **추가만** 한다. 따라서 rollback 은 `DROP TABLE` 3종 +
  `DROP TYPE` 3종으로 충분하고 기존 기능에 영향이 없다.
* 원장이 비어 있어도 서비스는 `HISTORY_INCOMPLETE_FAIL_CLOSED_TO_LEGACY` 로 현행
  정책을 그대로 쓴다 — migration 적용과 정책 활성화가 **분리**된다.
* 정책 활성화는 KST 날짜 경계에서 `DISPLAY_SELECTION_POLICY_VERSION` 전환으로 한다.

---

## 11. 예상 데이터량과 인덱스

| 대상 | 연간 | 비고 |
|---|---:|---|
| `board_generation` | 365행 + replay 분 | 행당 수백 바이트 |
| `selection_ledger` | 60 × 365 = **21,900행** | 행당 약 300~400B → 연 ~8MB |
| `active_board` | 365행 | |

인덱스는 §3 의 4종이면 충분하다. 주 조회 패턴은 두 가지뿐이다 —
`(ilju, fortune_date)` 범위 스캔(history 90일)과 `(fortune_date)` 단건(active).

### 보존 정책

```
active generation·selection ledger   장기 보존 (TTL 삭제 금지)
superseded generation                최소 400일 후 아카이브 가능
replay audit                          최소 1년
Redis 캐시                            TTL 적용 (유일한 만료 대상)
```

원장이 캐시처럼 만료되면 상태 재현 계약이 무너진다.

---

## 12. 개인정보 미저장 확인

이 원장은 **일주별 공통 보드 이력**이다. 60갑자는 개인이 아니라 그날의 명식 좌표이며,
같은 일주의 모든 사용자가 동일한 카드를 본다.

저장하지 않는 것:

```
subject_id · account_id · 생년월일 · 출생지 · 이름
조회 여부 · 조회 시각 · 세션 · IP · 디바이스
카드 본문 문장 · LLM 프롬프트 · 대화 내용
```

저장하는 것은 `event_key` · 확률 · 밴드 · 사유 코드 · 지문뿐이다.
따라서 GDPR/개인정보 관점의 파기 대상이 아니며, 장기 보존이 가능하다.
`docs/17` 의 "과거 본문 미저장(TTL 캐시 전용)" 원칙과도 충돌하지 않는다 —
본문이 아니라 **선택 결정**만 남긴다.

---

## 13. 확정된 세 결정

### 13-1. 호환성은 코드 상수 registry

DB 호환성 테이블은 만들지 않는다. 운영 중 데이터만 고쳐 과거 이력의 해석 계약을
바꿀 수 있게 되면 재현성이 깨진다. 호환 범위 확대는 코드 리뷰·fixture·과거 원장
replay 테스트·배포를 모두 거친다.

판정은 **두 축을 함께** 본다 — 이력 계약과 taxonomy. `semantic_family` 매핑이
달라지면 같은 `event_key` 도 다른 의미 장면이 되기 때문이다.

    EXACT · EXPLICIT_COMPAT_MAPPING · INCOMPATIBLE · UNKNOWN

`UNKNOWN` 은 **호환으로 간주하지 않고 fail-closed** 한다.

### 13-2. 과거 90일은 `CONTRACT_REPLAY`

    generation_source        = CONTRACT_REPLAY
    selection_policy_version = display-selection.legacy-v0
    replay_fidelity          = EXACT_CONTRACT_REPLAY

`PARTIAL` 재생 결과는 C10 history 로 쓸 수 없다. 옛 계약을 정확히 재현할 수 없으면
현재 코드로 비슷하게 만들지 않고 `CONTRACT_REPLAY_INCOMPLETE` 로 실패시켜 C10 전환을
중단한다.

날짜별로 당시 값을 쓴다 — `2026-07-29` 까지 `dict.v1.10`, `2026-07-30` 부터
`dict.v1.11`. 과거 표시 결과는

    display_good_representative = raw_good_winner
    good_selection_reason       = RAW_GOOD_WINNER_SELECTED
    display_displacement_loss   = 0

이지만, **`final_headline` 은 당시 보드 재배정 결과까지 포함**한다. 과거 정책에
장기 선택이 없었다는 이유로 보드 cap 을 생략하지 않는다.

### 13-3. `display-selection.legacy-v0` 는 고정 adapter

"현재 코드에서 C10 플래그만 끈 상태"로 정의하지 않는다 — 이후 코드가 변하면 legacy 도
함께 변해 과거 재현이 무너진다. 별도 순수 함수로 고정한다.

    장기 history 참조 없음
    raw good winner 를 display good representative 로 사용
    support·caution 은 당시 `_select_slots` 계약으로 선발
    headline 은 당시 band 계약으로 결정
    board rebalance 는 날짜별 당시 계약 적용
    good_selection_reason = RAW_GOOD_WINNER_SELECTED · loss = 0

golden fixture 경계: OA-6a/6b 전후 · OA-8a/8b 전후 · `dict.v1.10 → v1.11` ·
2026-07-30 날짜 경계 · domain authorized override 날짜(2026-07-30).

## 14. 첫 C10 전환 history

과거 90일 동안 대표가 바뀌지 않은 것은 결함이 아니라 **실제 과거 표시 정책**이다.
C10 은 이 history 를 그대로 받는다.

    D-90 ~ D-1   legacy-v0 CONTRACT_REPLAY
    D            C10 최초 적용

**C10 을 과거에 소급 적용해 self-warmup 을 만드는 것은 금지한다** — 사용자가 보지
않은 사건을 본 것으로 간주하게 된다. 따라서 감사를 둘로 나눈다:

| 감사 | 입력 | 용도 |
|---|---|---|
| 안정 상태 | C10 90일 warm-up → C10 90일 | 이미 통과한 C10 자체 성능 |
| **실제 전환** | legacy-v0 재생 90일 → C10 90일 | **출시 판단 기준** |

전환 후 첫 7일 · 첫 30일 · 전체 90일을 구간별로 측정한다 — 표시 대표 변경률 ·
평균·p90 손실 · key/family coverage · 7일 반복 · Top-5 집중도 ·
authorized override · 특정 사건의 초기 급증.

## 15. legacy fallback 기록

history replay 가 실패해 `legacy-v0` 로 fail-closed 한 날짜도 원장에 기록한다.

    selection_policy_version  = display-selection.legacy-v0
    generation_source         = LIVE_PREGEN | LIVE_ON_DEMAND
    good_selection_reason     = RAW_GOOD_WINNER_SELECTED
    selection_reason_codes   += HISTORY_INCOMPLETE_FAIL_CLOSED_TO_LEGACY

이 날짜는 **실제 게시 결과**이므로 이후 history 에 포함된다. 다만 이미 게시된 날짜를
복구 후 몰래 C10 결과로 교체하지 않는다 — 과거 active pointer 교체는 명시적
`BACKFILL_REPLACEMENT` 절차와 운영 판단이 있을 때만 가능하다.

## 16. 구현 노트 — SQL 에 복제하지 않은 것

`history_start_date = fortune_date - N` 을 CHECK 에 넣지 않았다. lookback 길이는
`LONGTERM_LOOKBACK_DAYS`(현재 89, D-89~D-1) 코드 상수이고, SQL 에 숫자를 복제하면
두 곳이 조용히 어긋난다. DDL 은 **끝점만** 강제하고(`history_end_date =
fortune_date - 1`) 길이는 서비스와 회귀가 지킨다.

> 참고: 승인 지시에는 `fortune_date - 90` 이 예시로 있었으나 현행 정책 상수는 89 다
> (D-89 ~ D-1). 값을 임의로 바꾸지 않고 코드 상수를 SSOT 로 두었다.
