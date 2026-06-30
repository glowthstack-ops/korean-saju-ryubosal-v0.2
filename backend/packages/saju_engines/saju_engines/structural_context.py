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
from .marriage_age_prior import analyze_marriage_age_prior
from .marriage_timing_profile import active_marriage_aux

# MT6 혼기 band → 한글 경향(static prior·특정 시기 아님).
_MARRIAGE_AGE_BAND_KO = {
    "early": "이른 인연 경향", "normal": "사회 초·중반(적령) 경향",
    "spouse_palace_direct": "배우자궁 직접(본인 주도) 구조", "late": "만혼 경향",
}

_CAPACITY_BAND_KO = {"strong": "강", "moderate": "중", "weak": "약"}
_GENDER_KO = {"female": "여성", "male": "남성"}
# 배우자성 프레이밍 — 성별 기준(남=재성=배우자, 여=관성=배우자). 헤더가 '관성=배우자'(여성 고정)로
# 하드코딩돼 남성 명식에 여성 기준이 들어가던 오역 교정(2026-06-22 데굴님 지적).
_SPOUSE_FRAME_KO = {
    "female": "관성=배우자(남편)·재성=시댁·물질 환경",
    "male": "재성=배우자(처)·물질 환경, 관성=직위·자식(배우자 아님)",
    "unknown": "배우자성은 성별 기준(남=재성·여=관성)",
}
_LEAN_KO = {
    "parental": "집안·부모 기반",
    "spouse_family": "결혼 후 물질 환경(여성 명식은 시댁 재력 잠재)",
    "self": "자수성가(식상생재) 경향",
}
_GEOKSIN_GROUP_KO = {
    "wealth": "재성", "officer": "관성", "output": "식상",
    "resource": "인성", "peer": "비겁",
}


def spouse_star_directive(gender: str | None) -> str:
    """배우자성 성별 가드 — 남=재성·여=관성. 반대 성별 기준 해석을 막는다(chat·report 공용).

    헤더 외에도 결혼·관계 풀이에 명시 가드를 덧대 '남성에게 관성=배우자' 같은 여성 기준 오역을
    차단한다(2026-06-22 데굴님 지적). 미상이면 특정 배우자성을 단정하지 않도록 안내한다.

    Args:
        gender: 'male'/'female'/'unknown'/None.

    Returns:
        성별별 배우자성 가드 지시문(LLM 입력용).
    """
    if gender == "male":
        return (
            "[배우자성 — 성별 기준]\n주인공은 남성이다. 남성의 배우자(아내)는 재성(정재·편재)이며 "
            "결혼·배우자운은 재성을 중심으로 본다. 정관·편관은 남성에게 직위·명예·자식(자녀)이지 "
            "배우자가 아니다 — '관성=배우자', '여성에게는…' 같은 여성 기준 해석을 남성 사주에 "
            "적용하지 말 것. 결혼 시기는 재성의 등장·합, 비식재 흐름, 일지(배우자궁) 자극으로 보라."
        )
    if gender == "female":
        return (
            "[배우자성 — 성별 기준]\n주인공은 여성이다. 여성의 배우자(남편)는 관성(정관·편관)이며 "
            "결혼·배우자운은 관성을 중심으로 본다. 재성은 시댁·물질 환경이다 — '재성=배우자(아내)' "
            "같은 남성 기준 해석을 여성 사주에 적용하지 말 것. 결혼 시기는 관성의 등장·합, 재생관, "
            "일지(배우자궁) 자극으로 설명하라."
        )
    return (
        "[배우자성 — 성별 기준]\n배우자성은 성별에 따라 다르다(남=재성, 여=관성). 주인공 성별이 "
        "확정되지 않았으니 특정 배우자성을 단정하지 말고 성별 기준을 일반론으로만 언급하라."
    )


# 인연 출처(기존 vs 새 인연) — '주변 사람이야 새로운 사람이야?' 류 질문 근거(공용).
PARTNER_SOURCE_DIRECTIVE = (
    "[인연 출처 — 기존 지인 vs 새 인연]\n"
    "'주변·아는 사람이냐 새로운 사람이냐'를 물으면: 배우자운이 합(合)·도화로 들면 가깝고 익숙한 "
    "인연(주변·소개·재회) 경향, 충(沖)·역마로 들면 외부·먼 곳·이동 중의 새로운 인연 경향으로 "
    "설명하라. 다만 사주로 둘 중 하나를 확정할 수는 없으니 단정하지 말고 가능성·경향으로만 안내하라"
    "(어느 쪽이든 열어두고, 본인의 활동 반경을 넓히는 실천을 함께 권할 것)."
)


# 운에 따른 일시 취향 변동(D) — 운 십성이 평소 일지 취향과 다르면 일시 끌림, 운 빠지면 흔들림(공용).
TENDENCY_SHIFT_DIRECTIVE = (
    "[운에 따른 일시 취향 변동 — 주의]\n"
    "운(대운·세운)에서 평소 일지 취향과 다른 십성, 특히 인성(기대고 존경할 사람)·식상(자극·표현이 "
    "강한 사람)이 강하게 들면 평소와 다른 타입에 일시적으로 끌릴 수 있다. 이는 운의 일시 작용이라 "
    "그 기운이 빠지면 관계가 흔들리기 쉽다 — '운에 취해' 급히 정하지 말고 평소 취향과의 차이를 "
    "인지하도록 안내하라(불안 조장·단정 금지, 경향으로만)."
)


# 연애 자기인식(C) — 사주에 드러난 이상형 취향을 본인이 인정 않으면 연애가 어긋난다는 앵글(공용).
RELATIONSHIP_SELF_AWARENESS_DIRECTIVE = (
    "[연애 자기인식 — 너 자신을 알라]\n"
    "사주에 드러난 '배우자 취향(이상형)'은 본인이 평소 인정하지 않을 수 있다(예: '성향·마음을 "
    "본다'면서 실제로는 외모·조건에 끌리는 결). 제공된 이상형 경향을 부정·미화하지 말고, 본인이 "
    "실제로 끌리는 타입을 담백하게 받아들이도록 안내하라 — 연애가 어긋나는 흔한 이유가 자기 취향을 "
    "모르거나 인정 않는 데 있다. 낙인·단정 금지, '경향'으로만 따뜻하게 풀 것."
)


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
    spouse_frame = _SPOUSE_FRAME_KO.get(mr.gender, _SPOUSE_FRAME_KO["unknown"])
    lines = [
        "[결혼·자산 자원 구조 — 원국 구조(운 미반영). 가능성·잠재로만 서술하고 '신분 상승·신데렐라·"
        f"반드시' 류 단정 금지. {_GENDER_KO.get(mr.gender, mr.gender)} 명식 — {spouse_frame}]",
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
    if mr.day_branch_tendency:
        bond.append(f"배우자궁(일지) 기질 {mr.day_branch_tendency}")
    if bond:
        lines.append(
            "배우자 인연 결(가능성·경향으로만, 단정·낙인 금지): " + " / ".join(bond)
        )
    # A) 배우자 취향(이상형) — 일지 십성 기준 끌리는 타입(경향).
    if mr.ideal_type_tendency:
        lines.append(
            f"배우자 취향(이상형 — 일지 십성, 경향·단정 아님): {mr.ideal_type_tendency}"
        )
    # B) 생애 단계별 연애 대상 — 연·월·시지 십성(경향·시기 단정 아님).
    if mr.life_stage_ideals:
        lines.append(
            "생애 단계 연애 대상(연·월·시지, 경향·시기 단정 아님): "
            + " / ".join(mr.life_stage_ideals)
        )
    # 관계 친화·돌봄 성향 — 십성 구조×신강약(관계에 어떻게 임하는가, 경향·비단정).
    if mr.relationship_affinity:
        lines.append(
            "관계 친화·돌봄 성향(경향·단정 아님): " + " / ".join(mr.relationship_affinity)
        )
    # E·F·G) 배우자복 품질 — 배우자별 청탁·뿌리 / 배우자궁 안정 / 배우자성=용신 덕(경향·비단정).
    quality: list[str] = []
    if mr.spouse_star_clean:
        q = "배우자별이 하나로 깔끔(선택 분명·관계 안정)"
        if mr.spouse_star_rooted:
            q += " + 뿌리 튼튼(능력·집안 등 현실적 도움 받기 쉬운 결)"
        quality.append(q)
    elif mr.spouse_star_rooted:
        quality.append("배우자별 뿌리 있음(영향력 오래가는 결)")
    if mr.spouse_palace_stable:
        quality.append(
            "배우자궁(일지) 충·형·원진 없이 안정 — 관계 내구성이 좋아 갈등도 제자리로 돌아오는 결"
        )
    else:
        quality.append(
            "배우자궁(일지) " + "·".join(mr.spouse_palace_afflictions)
            + " — 관계가 흔들리기 쉬운 결이나 개운·궁합·노력으로 보완 가능(이혼 단정 아님, "
            "남·환경 탓보다 본인 대응이 관건)"
        )
    if mr.spouse_is_yongsin:
        quality.append(
            f"배우자성({mr.spouse_star})이 용신/희신 — 배우자가 부족한 기운을 채워주는 "
            "'에어컨/보일러' 역할로, 결혼하며 더 풀리는 배우자 덕(경향)"
        )
    if quality:
        lines.append("배우자복 품질(경향·단정 아님): " + " / ".join(quality))
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


# ── 대운 풀이 관점·교체기 신호(2026-06-23, 전문가 강의 참고 — 채팅·리포트 공용) ──
# 계산 불변(점수·날짜·간지·판정 무관). 대운을 '환경/공간감(플랫폼)이 닥쳐오는 흐름'으로,
# 핵심을 '이 대운이 나에게(용신·조후) 맞느냐'로 잡는 서술 관점만 제공한다(절대원칙 1·8 준수).
DAEWOON_FRAMING_DIRECTIVE = (
    "[대운 풀이 관점] 대운은 '내가 바꾸는 것'이 아니라 계절이 닥치듯 환경·공간감(플랫폼)이 "
    "바뀌어 오는 10년 흐름이다. 핵심은 '운이 바뀐다'가 아니라 '이 대운이 나에게(용신·조후) 맞는 "
    "대운이냐' — 맞으면 같은 노력이 순풍을, 안 맞으면 역풍이 된다(안 맞는 평운·기신 구간은 포기가 "
    "아니라 지금 하던 것을 지키며 내실을 다지고 다음 맞는 대운을 준비). 대운의 전반 0-4년은 "
    "천간(드러남), 후반 5-9년은 지지(기반·환경)가 주도하는 시기 차이도 반영하고, 새 환경에 "
    "적응하며 그 대운의 미션(이동·전환·확장·정착 등)을 수행하는 관점으로 — 단정 말고 에너지·"
    "방향·적응으로 풀 것."
)
DAEWOON_TRANSITION_SIGNALS_DIRECTIVE = (
    "[대운 교체기 체감 신호 — 단정 아님, 사람·정도 차이] 교운(대운 교체) 무렵엔 흔히 다음이 함께 "
    "나타난다: 주변 사람이 바뀌고 새 인연이 들어옴 · 안 하던 새 일을 도모하고 싶어짐 · '뭔가 "
    "해봐야 할 것 같은' 막연한 기대 · 가까운 이들의 반대가 늘어남 · 거주지·환경을 바꾸거나 물건을 "
    "정리하고 싶어짐 · 외모·분위기 변화. '겪으셨을 수 있다/겪을 수 있다'로 가능 형태로만 짚고, "
    "확정·예언으로 말하지 말 것."
)


def marriage_age_prior_lines(result: ManseV2Result) -> list[str]:
    """[혼기 경향 — static prior] MT6 배우자성 위치 기반 광역 혼기 경향(특정 시기 아님).

    활성 프로파일 aux(mt6_age_prior)가 켜졌을 때만 산출한다 — default 프로파일은 빈 목록(출력 불변).
    event trigger가 아니므로 특정 연·월을 말하지 않고, 실제 시점은 운이 결정함을 명시한다.

    Args:
        result: 만세 결과(pillars·gender).

    Returns:
        혼기 경향 1~2줄(미상·미산출·프로파일 off면 빈 목록).
    """
    if not active_marriage_aux().get("mt6_age_prior"):
        return []
    prior = analyze_marriage_age_prior(result)
    if prior.band == "unknown" or not prior.positions:
        return []
    band_ko = _MARRIAGE_AGE_BAND_KO.get(prior.band, prior.band)
    note = (
        f"[혼기 경향(static prior·특정 시기 아님)] 배우자성이 {'·'.join(prior.positions)}에 "
        f"드러나 {band_ko}. 실제 결혼 시점은 운(대운·세운)이 결정하며, 넓은 경향으로만 참고."
    )
    lines = [note]
    if "spouse_palace_direct" in prior.structural_flags and prior.band != "spouse_palace_direct":
        lines.append(
            "  (일지=배우자궁에 배우자성 직접 — 결혼이 본인 현실·배우자궁 문제로 직접 들어오는 결)"
        )
    if prior.confidence == "low":
        lines.append("  ※ 성별 미상 — 약한 참고(혼기 보정 미사용)")
    return lines
