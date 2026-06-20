"""결혼·자산 자원 구조(marriage & wealth-source profile) — 원국 해석 보조 (v2.2).

같은 년월일이라도 **시주**가 바뀌면 '결과 자원'이 달라진다는 실사례(2021-09-15 午시 vs 卯시,
둘 다 丙火 여성)를 일반화한 **중립·비단정 구조 신호**다. 자산의 출처(부모 기반 / 배우자 집안 /
자수성가 경향)와 시주 자원 역할, 배우자 별(성별 인지)을 구조로만 표면화한다.

**신규 이벤트 키를 만들지 않는다**(사용자 확정 2026-06-16). '신데렐라·신분 상승' 류 라벨·단정은
쓰지 않으며, 재성 환경은 어디까지나 '물질 기반이 두드러질 잠재'(가능성)로 표현한다. 같은 구조가
흔하므로 예측이 아니라 해석 맥락으로만 쓴다(확증편향 차단).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MarriageResourceProfile(BaseModel):
    """결혼·자산 자원 구조(운 미반영, 성별 인지). 모든 값은 원국만으로 결정된다."""

    gender: str  # female/male/unknown
    wealth_element: str  # 재성 오행(일간이 극하는 오행)
    spouse_star: str  # 배우자 별 십성군 — 여성=관성 / 남성=재성
    spouse_star_present: bool  # 배우자 별이 천간/지지/지장간에 존재
    wealth_in_family_palace: bool  # 재성이 년·월주(부모·집안·초년 자리)에
    wealth_in_result_palace: bool  # 재성이 시주(결혼 후·결과·말년 자리)에
    wealth_strong: bool  # 재성 세력 강(반복·세력 비중)
    resource_support: bool  # 인성 + 일간 뿌리(보호받는 구조)
    wealth_palace_clash: bool  # 재성 지지가 원국 충에 관여(발동·변화 잠재)
    # ── 배우자 인연 결(중립·비단정·비낙인 — 궁합 자료 ⑤⑥, 2026-06-20) ──
    # '바람둥이/과부상' 류 낙인 금지 — 경향·가능성으로만. 남성 재성 과다/여성 관성 과다 = 인연
    # 신호가 많아 한 곳에 매이기보다 끌림이 잦은 결, 미투출 = 인연을 스스로 만들어가는 능동형.
    spouse_star_excess: bool = False  # 배우자 별 과다(남:재다 / 여:관살혼잡 경향)
    spouse_star_absent: bool = False  # 배우자 별 미투출(천간·본기 부재 — 능동형 구조)
    charm_present: bool = False  # 도화·홍염(이성에게 매력적으로 비치는 끌림 경향)
    hour_resource_role: str  # 시주 천간 십성 → 자원 역할(중립 라벨)
    # 자산 출처 경향(중립·가능성) — 'parental'/'spouse_family'/'self' 중복 가능.
    wealth_source_leans: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # 성립 구조 한글 라벨(서술용)
