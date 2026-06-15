"""사전계산 갱신 스케줄러 (v2.2 Phase 2.5 T2.5.4·T2.5.5, docs/09 1장).

갱신 트리거 구현 방식: 운 레벨의 period_key는 경계(입춘=세운, 절입=월운, 교운일=대운,
자정=일운)를 지나면 **자연히 새 키가 된다**. 따라서 "현재 기준일의 레코드가 모두
존재하는가"를 보장하는 ensure-current 방식이 곧 T1/T2 경계 갱신이다:

  T0  on_subject_upsert  — 등록/출생정보 수정 시 전체 재계산(기존 레코드 무효화)
  T1  ensure_current     — 입춘/절입/교운 경계 후 첫 접근(또는 배치)에서 누락분 보충
  T2  daily_batch        — 활성 대상 매일 재계산(+day 보존 정리), 비활성은 lazy
  사전 버전 변경        — on_dict_version_change: 구버전 전체 무효화 후 재계산은 lazy

만세력 계산 함수는 주입받는다(`compute: (BirthInput) -> ManseV2Result`) — 엔진 패키지가
서비스 계층(apps/api)에 역의존하지 않도록 하기 위함이다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from saju_manse_analysis.luck.luck_calendar import luck_month_label

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.subject import SubjectRecord

from .precompute import CompositeBuilder
from .precompute_store import PrecomputeStore

if TYPE_CHECKING:
    from saju_manse_core.calendar.solar_terms import SolarTermTable

ComputeFn = Callable[[BirthInput], ManseV2Result]


class PrecomputeScheduler:
    """저장소·계산기·만세 계산 함수를 묶는 갱신 조정자(결정론, cron 와이어링은 운영 계층)."""

    def __init__(
        self,
        store: PrecomputeStore,
        builder: CompositeBuilder,
        compute: ComputeFn,
        dict_version: str,
        table: SolarTermTable | None = None,
        timezone: str = "Asia/Seoul",
    ) -> None:
        """compute는 만세력 서비스의 calculate(캐시 포함)를 주입한다.

        table: 절기 테이블(``month_branch`` 보유). 주입 시 당월 월운 키를 절기 기준으로
            잡는다(미주입 시 양력 ``today.month`` 폴백 — 절기 경계 직전 한 달 어긋날 수 있음).
        timezone: 월운 라벨을 만들 타임존(차트 라벨 생성 타임존과 일치해야 정합).
        """
        self._store = store
        self._builder = builder
        self._compute = compute
        self._dict_version = dict_version
        self._table = table
        self._timezone = timezone

    # ── T0: 등록/수정 ────────────────────────────────────────────

    def on_subject_upsert(
        self, subject: SubjectRecord, today: date, computed_at: str
    ) -> int:
        """대상 등록/출생정보 수정: 기존 레코드 전체 무효화 후 T0~T2 재계산.

        Returns:
            저장된 LuckComposite 건수.
        """
        self._store.invalidate_subject(subject.subject_id)
        composites = self._build_all(subject, today, computed_at)
        return self._store.upsert(composites)

    # ── T1/T2: 경계 보충 (lazy ensure-current) ───────────────────

    def ensure_current(
        self, subject: SubjectRecord, today: date, computed_at: str
    ) -> int:
        """기준일(today)의 레벨별 현재 period_key 레코드가 없으면 보충한다.

        입춘/절입/교운/자정 경계를 지나면 현재 키가 바뀌므로, 누락 보충이 곧 경계
        갱신이다. 이미 모두 존재하면 0건(재계산 없음 — 멱등).
        """
        missing = self._missing_levels(subject.subject_id, today)
        if not missing:
            return 0
        composites = self._build_all(subject, today, computed_at)
        to_save = [c for c in composites if c.level in missing]
        return self._store.upsert(to_save)

    def _missing_levels(self, subject_id: str, today: date) -> set[CompositeLevel]:
        """오늘 기준으로 비어 있는 레벨 집합(현재 period_key 기준)."""
        v = self._dict_version
        missing: set[CompositeLevel] = set()
        if self._store.get(subject_id, CompositeLevel.NATAL, "natal", v) is None:
            missing.add(CompositeLevel.NATAL)
            missing.add(CompositeLevel.DAEWOON)  # natal 부재 = 초기 상태 → 대운도 보충
        year_key = str(today.year)
        if self._store.get(subject_id, CompositeLevel.YEAR, year_key, v) is None:
            missing.add(CompositeLevel.YEAR)
        # 월운 period_key는 절입 기준 라벨(YYYY-MM) — 양력 당월(today.month)이 아니라
        # 오늘이 속한 절기 월운 라벨로 조회해야 한다(절기 경계 직전 구간 어긋남 보정).
        if self._table is not None:
            month_key = luck_month_label(today, self._table, self._timezone)
        else:
            month_key = f"{today.year}-{today.month:02d}"
        if self._store.get(subject_id, CompositeLevel.MONTH, month_key, v) is None:
            missing.add(CompositeLevel.MONTH)
        if self._store.get(subject_id, CompositeLevel.DAY, today.isoformat(), v) is None:
            missing.add(CompositeLevel.DAY)
        return missing

    # ── T2: 일일 배치(활성 대상) + 보존 정리 ──────────────────────

    def daily_batch(
        self, active_subjects: list[SubjectRecord], today: date, computed_at: str
    ) -> dict[str, int]:
        """활성 대상의 ensure-current 일괄 실행 + day 레벨 보존 정리(T2.5.5).

        Returns:
            {"subjects": 처리 대상 수, "saved": 저장 건수, "purged": 정리 건수}.
        """
        saved = 0
        for subject in active_subjects:
            saved += self.ensure_current(subject, today, computed_at)
        purged = self._store.purge_day_records(today)
        return {"subjects": len(active_subjects), "saved": saved, "purged": purged}

    # ── 비활성 대상 lazy 조회 ─────────────────────────────────────

    def lazy_get(
        self, subject: SubjectRecord, level: CompositeLevel, period_key: str,
        today: date, computed_at: str,
    ) -> LuckComposite | None:
        """레코드 조회 — 없으면 그 자리에서 계산·저장 후 반환(비활성 대상 경로)."""
        found = self._store.get(
            subject.subject_id, level, period_key, self._dict_version
        )
        if found is not None:
            return found
        composites = self._build_all(subject, today, computed_at)
        self._store.upsert(composites)
        return self._store.get(subject.subject_id, level, period_key, self._dict_version)

    # ── 사전 버전 변경 ───────────────────────────────────────────

    def on_dict_version_change(self) -> int:
        """구버전 레코드 전체 무효화(재계산은 이후 접근/배치에서 lazy로 수행)."""
        return self._store.invalidate_other_versions(self._dict_version)

    # ── 내부 ─────────────────────────────────────────────────────

    def _build_all(
        self, subject: SubjectRecord, today: date, computed_at: str
    ) -> list[LuckComposite]:
        """기준일을 today로 고정해 만세 계산 → 전체 레벨 LuckComposite."""
        birth = subject.birth.model_copy(update={"reference_date": today})
        result = self._compute(birth)
        return self._builder.build(
            result, subject.subject_id, self._dict_version, computed_at,
        )
