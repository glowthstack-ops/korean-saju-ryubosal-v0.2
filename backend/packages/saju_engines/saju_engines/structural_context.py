"""구조 해석 블록 — 리포트·챗 공용 (v2.2, 2026-06-16).

원국 횡재 그릇·결혼/자산 자원·건강 취약·부귀 지향·연운 시대 기운을 **누출 안전한 한글**로
직렬화하는 단일 소스다. **내부 변수명(영문 그룹·band 코드 등)·원시 점수·퍼센트를 본문에 노출하지
않는다**(LLM 누출 방지 — 사용자 확정 2026-06-16). 리포트(_ReportData)·챗(chat_service)이 동일
포맷터를 호출해 표면화 일관성을 유지한다.
"""

from __future__ import annotations

from saju_shared_types.health_vulnerability import HealthVulnerabilityProfile
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.marriage_resource import MarriageResourceProfile
from saju_shared_types.wealth_capacity import WealthCapacity
from saju_shared_types.wealth_status_lean import WealthStatusLean

from .era_energy import era_curated_note, era_energy_profile
from .health_vulnerability import health_risk_windows

_CAPACITY_BAND_KO = {"strong": "강", "moderate": "중", "weak": "약"}
_GENDER_KO = {"female": "여성", "male": "남성"}
_LEAN_KO = {
    "parental": "집안·부모 기반",
    "spouse_family": "결혼 후 물질 환경(여성 명식은 시댁 재력 잠재)",
    "self": "자수성가(식상생재) 경향",
}
_GEOKSIN_GROUP_KO = {
    "wealth": "재성", "officer": "관성", "output": "식상",
    "resource": "인성", "peer": "비겁",
}


def wealth_capacity_lines(wc: WealthCapacity) -> list[str]:
    """[원국 횡재 그릇] — 운 분리 잠재구조(점수·영문 코드 비노출)."""
    band = _CAPACITY_BAND_KO.get(wc.capacity_band, wc.capacity_band)
    flags = ", ".join(wc.flags) if wc.flags else "두드러진 횡재 구조 약함"
    return [
        "[원국 횡재 그릇 — 운과 분리된 원국 자체의 재물 잠재구조(엔진 판정). '그릇이 있어도 운에서 "
        "발동해야 현실화'를 전제로 서술하고, 당첨·복권 단정과 번호 추천은 절대 금지]",
        f"재성 오행: {wc.wealth_element} · 종합 그릇: {band}",
        f"성립 구조: {flags}",
        "발동 조건(운에서 일어나야 현실화): 재성국 완성(삼합)·묘고 충개고·식상생재. 원국에 "
        "그릇이 없어도 운에서 이 완성이 일어나면 일부 발동하나, 그릇이 받쳐줄수록 크게 난다.",
    ]


def marriage_resource_lines(mr: MarriageResourceProfile) -> list[str]:
    """[결혼·자산 자원 구조] — 성별 인지·중립·비단정(점수 비노출)."""
    spouse = (
        f"{mr.spouse_star} 신호 {'드러남' if mr.spouse_star_present else '약함(지장간 잠복)'}"
    )
    pos = []
    if mr.wealth_in_family_palace:
        pos.append("년월(집안 기반)")
    if mr.wealth_in_result_palace:
        pos.append("시주(결혼 후·결과 자원)")
    wealth_line = "재성 환경: " + (", ".join(pos) if pos else "년월·시주에 약함")
    if mr.wealth_strong:
        wealth_line += " · 세력 강"
    if mr.wealth_palace_clash:
        wealth_line += " · 재성궁 충(발동·변화 잠재)"
    leans = "、".join(_LEAN_KO.get(x, x) for x in mr.wealth_source_leans) or "뚜렷하지 않음"
    lines = [
        "[결혼·자산 자원 구조 — 원국 구조(운 미반영). 가능성·잠재로만 서술하고 '신분 상승·신데렐라·"
        f"반드시' 류 단정 금지. {_GENDER_KO.get(mr.gender, mr.gender)} 명식 — 관성=배우자, "
        "재성=시댁·물질 환경]",
        f"배우자 별({mr.spouse_star}): {spouse}",
        wealth_line,
    ]
    if mr.hour_resource_role:
        lines.append(f"시주 자원 역할: {mr.hour_resource_role}")
    # 배우자 인연 결(중립·비낙인 — 궁합 자료 ⑤⑥): '바람둥이/과부상' 류 낙인 금지, 경향으로만.
    bond: list[str] = []
    if mr.spouse_star_excess:
        if mr.gender == "male":
            bond.append("재성(이성·물질)이 강해 새 자극·인연에 끌리는 경향(호기심 큰 결)")
        elif mr.gender == "female":
            bond.append("관성(이성·인연)이 많아 인연 신호가 복잡할 수 있는 결(관살혼잡 경향)")
        else:
            bond.append("배우자 별 세력이 강해 이성·인연 신호가 두드러지는 결")
    if mr.spouse_star_absent:
        bond.append("배우자 별 미투출 — 인연을 스스로 만들어가는 능동형 구조(부재 단정 아님)")
    if mr.charm_present:
        bond.append("도화·홍염 — 이성에게 매력적으로 비치고 끌림이 잦은 경향")
    if bond:
        lines.append(
            "배우자 인연 결(가능성·경향으로만, 단정·낙인 금지): " + " / ".join(bond)
        )
    lines.append(
        f"자산 출처 경향(가능성): {leans}. 돈의 '출처'(부모/배우자 집안/자수성가)를 구분해 "
        "서술하되 단정하지 말 것."
    )
    return lines


def wealth_status_lines(w: WealthStatusLean) -> list[str]:
    """[부/귀 지향] — 영문 그룹·퍼센트 비노출, 정성 표현만."""
    group_ko = _GEOKSIN_GROUP_KO.get(w.geokguk_group, "")
    if w.wealth_pct >= w.officer_pct + 5:
        bias = "재성(재물 기운)이 관성(조직·명예 기운)보다 우세"
    elif w.officer_pct >= w.wealth_pct + 5:
        bias = "관성(조직·명예 기운)이 재성(재물 기운)보다 우세"
    else:
        bias = "재성·관성이 균형"
    parts = [f"주격 {w.geokguk_name}" if w.geokguk_name else ""]
    if group_ko:
        parts.append(f"격신은 {group_ko}")
    parts.append(bias)
    return [
        "[부(富)/귀(貴) 지향 — 원국이 재물(부) 결인지 명예·조직(귀) 결인지. 우열·단정이 아니라 "
        "방향이며 운·선택으로 달라질 수 있음]",
        f"지향: {w.lean} · " + " · ".join(p for p in parts if p),
        w.note,
    ]


def health_lines(
    result: ManseV2Result, hv: HealthVulnerabilityProfile, today_year: int
) -> list[str]:
    """[원국 건강 취약 구조 + 관리 권장 시기] — 의료 면책, 점수 비노출(등급·근거만)."""
    lines = [
        "[원국 건강 취약 구조 — 원국 구조(운 미반영). **의료 진단이 아니며 질병명·수명·사망은 절대 "
        "단정 금지.** '특정 계열은 평소 관리·정기 검진이 도움될 수 있다'는 예방·가능성 관점으로만 "
        "서술하고, 우려 시 전문의 상담을 권하는 톤을 유지할 것]",
    ]
    if hv.vulnerable_organs:
        organs = "; ".join(
            f"{o.organ_category}({o.element}—{o.attacker_element}의 극, 통관 약)"
            for o in hv.vulnerable_organs
        )
        lines.append(f"취약 장기 계열(평소 관리 권장): {organs}")
    else:
        lines.append("취약 장기 계열: 두드러진 손상 구조는 약함")
    body = []
    if hv.weak_body_excess_officer:
        body.append("관다신약(체력 부담·과로 관리)")
    if hv.food_god_weak:
        body.append("식신 약(회복력·식욕 관리)")
    if hv.indirect_resource_strong:
        body.append("편인 강(도식 — 소화·생활리듬 관리)")
    if hv.excess_unfavorable_elements:
        body.append(f"과다 기신 오행 {'·'.join(hv.excess_unfavorable_elements)}")
    if body:
        lines.append("체력·구조 신호: " + " · ".join(body))
    tombs = [t for t in (hv.day_master_tomb_branch, hv.food_god_tomb_branch) if t]
    if tombs:
        lines.append(
            f"입묘 주의 지지: {'·'.join(dict.fromkeys(tombs))} — 운에서 이 지지가 겹치는 시기에 "
            "컨디션·검진을 챙기면 좋음(질병 단정 아님)"
        )
    if hv.stem_symbol_caution:
        lines.append(f"일간 물상 참고: {hv.stem_symbol_caution}")
    windows = health_risk_windows(result, hv, today_year)
    if windows:
        lines.append(
            "관리 권장 시기(운에서 취약 구조가 재자극되는 때 — 질병·사망 예측 아님, 그 무렵 "
            "컨디션·검진을 챙기라는 신호):"
        )
        for w in windows:
            bg = f" {w.daewoon}대운" if w.daewoon else ""
            lines.append(f"- {w.period}년{bg}: {w.level} ({', '.join(w.reasons)})")
    return lines


def era_energy_lines(result: ManseV2Result, year: int) -> list[str]:
    """[올해 시대 기운] — 명리 기운 맥락(경제·시장 예측 금지)."""
    lc = result.luck_cycles
    ganji = ""
    if lc is not None:
        for sw in lc.yearly_luck:
            if sw.label == str(year) and len(sw.ganji) >= 2:
                ganji = sw.ganji
                break
    if not ganji:
        return []
    era = era_energy_profile(ganji[0], ganji[1])
    lines = [
        "[올해 시대 기운 — 그 해 간지의 명리 기운(개인 앞 사회 맥락). 경제·시장·채용 같은 시사 "
        "예측·단정은 절대 금지, 기운의 결로만 서술]",
        era.summary,
    ]
    note = era_curated_note(year, era.year_ganji)
    if note:
        lines.append(f"운영자 시대 노트(참고): {note}")
    return lines
