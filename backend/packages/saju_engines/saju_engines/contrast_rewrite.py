"""겉/속 거짓 역접 결정론 재작성 — "겉으로는 A지만 내면에는 B" → "겉으로는 A고, 내면에는 B".

배경(2026-10-01): 일주 사전(ilju.json 1.0.1) 교정과 `[일주 요약 규칙]` 문장 형태 지시 뒤에도 실답
(11:13, web-mupfqmrm)에 "己亥 일주는 겉으로는 다정하고 부드럽지만 내면에는 거대한 강물 같은
지혜와 실속을 갖춘 구조입니다"가 다시 나왔다. 원인은 모델 자체의 서술 습관이며, 지시문에 넣었던
**부정 예문**("…지만 내면에는 …처럼 잇지 말고")이 오히려 그 문형을 상기시킨 것으로 본다.
지시로 막지 못하는 문형은 생성 후 결정론으로 고친다(재호출 없음 — 2026-07-27 데굴님 확정 원칙).

규칙(좁게): 한 문장 안에 **겉 표지**(겉으로는/겉보기에는/외면…)와 **속 표지**(내면에는/속은/
안에는…)가 모두 있고 그 사이에 역접·양보 연결어가 있으면, 그 연결어만 대등 연결 '-고'로 바꾼다.
앞 절의 어간은 건드리지 않으므로 활용 오류가 생기지 않는다(부드럽지만→부드럽고, 보이지만→보이고,
같은데→같고, 인데→이고, 부드러운데→부드럽고[ㅂ 불규칙 복원]). 겉/속 표지가 없는 진짜 역접
("신념이 되면 큰 산이지만 벽이 되면")과 속 절이 약점·부담인 문장은 건드리지 않는다. 순수 함수.
"""

from __future__ import annotations

import re

_SURFACE_RE = re.compile(
    r"겉으로(?:는|도)?|겉보기(?:에는|엔|로는)?|겉은|겉모습(?:은|으로는)?|외면(?:은|으로는|적으로는)?"
    r"|표면(?:적으로는|상으로는|은)?|보기에는"
)
_INNER_RE = re.compile(
    r"내면(?:에는|은|으로는|에서는)?|속(?:에는|은|으로는|마음은|마음에는)|안(?:에는|으로는)"
    r"|실제(?:로는|로)|사실(?:은|상)|마음(?:속에는|속은|은)"
)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+")
# 속 절이 약점·부담이면 진짜 역접(긍정→부정)이라 그대로 둔다 — 재작성은 장점↔장점에만.
_NEGATIVE_INNER_RE = re.compile(
    r"불만|부담|답답|서운|외로|피로|압박|불안|고민|스트레스|손해|약점|힘들|무겁|상처|우울|예민"
    r"|지치|분노|화가|욱|두려|걱정|소모|갈등|불편|고독|허전|공허|초조|조급|억눌|눌리"
)

# 역접·양보 연결어 → 대등 연결. 순서 중요(긴 패턴 먼저). 각 항목은 (정규식, 치환 함수).
_HANGUL_BASE = 0xAC00
_JONG_B = 17  # 종성 ㅂ 인덱스


def _add_final_b(syllable: str) -> str:
    """받침 없는 음절에 종성 ㅂ을 붙인다('러'→'럽'). 받침이 있으면 그대로."""
    code = ord(syllable) - _HANGUL_BASE
    if not (0 <= code < 11172):
        return syllable
    if code % 28 != 0:
        return syllable
    return chr(ord(syllable) + _JONG_B)


def _rewrite_connector(segment: str) -> tuple[str, bool]:
    """겉 표지 뒤 ~ 속 표지 앞 구간의 **마지막** 역접 연결어를 '-고'로 바꾼다."""
    rules: list[tuple[re.Pattern[str], object]] = [
        (re.compile(r"보여도,?(?=\s)"), lambda m: "보이고,"),
        (re.compile(r"(?<=[가-힣])지만,?(?=\s)"), lambda m: "고,"),
        (re.compile(r"(?<=[가-힣])지마는,?(?=\s)"), lambda m: "고,"),
        (re.compile(r"인데,?(?=\s)"), lambda m: "이고,"),
        (re.compile(r"한데,?(?=\s)"), lambda m: "하고,"),
        (re.compile(r"같은데,?(?=\s)"), lambda m: "같고,"),
        # ㅂ 불규칙 복원: 부드러운데 → 부드럽고 / 가벼운데 → 가볍고
        (re.compile(r"([가-힣])운데,?(?=\s)"), lambda m: _add_final_b(m.group(1)) + "고,"),
        (re.compile(r"(?<=[가-힣])는데,?(?=\s)"), lambda m: "고,"),
    ]
    best: tuple[int, re.Pattern[str], object, re.Match[str]] | None = None
    for pat, fn in rules:
        for m in pat.finditer(segment):
            if best is None or m.start() > best[0]:
                best = (m.start(), pat, fn, m)
    if best is None:
        return segment, False
    _, _pat, fn, m = best
    return segment[: m.start()] + fn(m) + segment[m.end():], True  # type: ignore[operator]


def rewrite_false_contrast(text: str) -> tuple[str, list[tuple[str, str]]]:
    """겉/속 대조를 역접으로 이은 문장을 대등 연결로 고친다.

    Returns:
        (고친 본문, [(원문 문장, 고친 문장), …]). 고칠 것이 없으면 원문 그대로·빈 목록.
    """
    if not text:
        return text, []
    changes: list[tuple[str, str]] = []
    out_parts: list[str] = []
    # 문장 분리는 공백 기준 split 이라 원문 공백을 그대로 복원할 수 있게 구분자를 보존한다.
    pieces = _SENT_SPLIT_RE.split(text)
    seps = _SENT_SPLIT_RE.findall(text)
    for i, sent in enumerate(pieces):
        new_sent = sent
        s_m = _SURFACE_RE.search(sent)
        if s_m is not None:
            i_m = _INNER_RE.search(sent, s_m.end())
            if i_m is not None and not _NEGATIVE_INNER_RE.search(sent[i_m.end():]):
                segment = sent[s_m.end(): i_m.start()]
                new_seg, changed = _rewrite_connector(segment)
                if changed:
                    new_sent = sent[: s_m.end()] + new_seg + sent[i_m.start():]
                    changes.append((sent, new_sent))
        out_parts.append(new_sent)
        if i < len(seps):
            out_parts.append(seps[i])
    return "".join(out_parts), changes
