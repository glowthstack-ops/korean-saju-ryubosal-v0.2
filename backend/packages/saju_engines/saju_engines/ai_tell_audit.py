"""한글 AI 티(AI-tell) 문체 층 — 지시문 생성 + 생성 후 결정론 감사(2026-10-19 데굴님 승인).

배경: 테마사주·AI채팅상담·오늘의 운세 본문에 번역투("~에 있어서", "가지고 있다"), 이중 피동,
결산 상투구("결론적으로"), 의의 과장 같은 AI 초안 특유의 말투가 남는다. 분류 체계는
im-not-ai(Humanize KR, MIT) 의 ai-tell-taxonomy 를 `templates/ai_tell_patterns.json` 으로
번안한 것이며, 이 모듈은 그 사전을 **치환만** 해서 쓴다(즉석 작문 없음).

두 역할:
1. `build_style_directive(scope)` — 시스템 프롬프트 뒤에 붙는 `[문체 — 한글 AI 티 제거]` 블록.
2. `audit_ai_tells(text, scope)` — 생성된 본문의 패턴 탐지(로그용) + 의미 무손실 자동 교정.
   자동 교정은 사전의 `fix` 가 있는 항목(A-3·A-8·D-1a)만이며, 교정 전후로 간지·숫자 다중집합이
   달라지면 교정을 전부 버리고 원문을 돌려준다. 큰따옴표 안(직접 인용)은 교정하지 않는다.

점수·간지·날짜·판정은 어디에서도 바꾸지 않는다 — 이 층은 문장 겉모습 전용이다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .dictionaries import AiTellPatternItem, AiTellPatternsFile

Scope = Literal["chat", "report", "daily"]

_DICT_PATH = (
    Path(__file__).resolve().parents[3] / "dictionaries" / "templates" / "ai_tell_patterns.json"
)

# 교정 불변 검사 대상 — 간지 한자·숫자. 이 글자들의 다중집합이 바뀌면 교정을 폐기한다.
_PROTECTED_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥0-9]")
# 큰따옴표 직접 인용 — 교정 제외 구간.
_QUOTE_SPLIT_RE = re.compile(r'("[^"\n]*"|“[^”\n]*”)')
# 문장 분리(상대 주장 감사와 같은 기준) — 종결 부호 뒤 공백/개행.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# 종결 토큰(E-2) — 문장 끝 부호를 뗀 마지막 두 글자('아요'·'예요'·'니다'·'었다')를 종결 단위로 본다.
# 해요체는 전부 '요'로 끝나므로 앞 글자까지 묶어야 '좋아요/많아요'(아요)와 '돼요/와요'를 구분한다.
_ENDING_PUNCT_RE = re.compile(r"[.!?\s]+$")


class AiTellFinding(BaseModel):
    """탐지된 패턴 1건(임계 이상만)."""

    id: str
    severity: str
    label: str
    count: int
    threshold: int
    samples: list[str]


class AiTellFixApplied(BaseModel):
    """적용된 자동 교정 1건."""

    id: str
    before: str
    after: str


class AiTellAudit(BaseModel):
    """감사 결과 — `text` 는 교정 적용본(교정이 없거나 폐기되면 원문)."""

    text: str
    findings: list[AiTellFinding]
    fixes: list[AiTellFixApplied]
    fixes_discarded: bool = False

    @property
    def s1_count(self) -> int:
        return sum(f.count for f in self.findings if f.severity == "S1")

    @property
    def s2_count(self) -> int:
        return sum(f.count for f in self.findings if f.severity == "S2")

    def summary(self) -> str:
        """로그 한 줄용 요약."""
        parts = [f"{f.id}×{f.count}" for f in self.findings]
        return (
            f"fixes={len(self.fixes)} discarded={self.fixes_discarded} "
            f"S1={self.s1_count} S2={self.s2_count} findings=[{' '.join(parts)}]"
        )


@lru_cache(maxsize=1)
def load_ai_tell_patterns(path: Path = _DICT_PATH) -> AiTellPatternsFile:
    """사전 로드·스키마 검증(캐시)."""
    return AiTellPatternsFile.model_validate(json.loads(path.read_text("utf-8")))


def _items_for(scope: Scope) -> list[AiTellPatternItem]:
    return [it for it in load_ai_tell_patterns().items if scope in it.scopes]


def build_style_directive(scope: Scope) -> str:
    """시스템 프롬프트용 문체 블록 — 사전 문구 치환만.

    chat·report: 머리말 + S1 목록 + S2 목록 + 맺음말(충돌 조정). daily: 한 줄(카드 길이용).
    """
    d = load_ai_tell_patterns().directive
    items = _items_for(scope)
    s1 = [it.directive for it in items if it.severity == "S1"]
    s2 = [it.directive for it in items if it.severity == "S2"]
    if scope == "daily":
        return d.preamble["daily"] + ": " + " / ".join(s1 + s2) + "."
    lines = [d.header, d.preamble[scope]]
    if s1:
        lines.append(f"- {d.s1_label}: " + " / ".join(s1) + ".")
    if s2:
        lines.append(f"- {d.s2_label}: " + " / ".join(s2) + ".")
    post = d.postamble.get(scope, "")
    if post:
        lines.append(post)
    return "\n".join(lines)


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _count_matches(item: AiTellPatternItem, text: str) -> tuple[int, list[str]]:
    """항목의 패턴 매치 수와 표본(최대 2, 60자)."""
    if item.region == "tail":
        sents = _sentences(text)
        start = int(len(sents) * 0.7)
        text = " ".join(sents[start:]) if sents else text
    count = 0
    samples: list[str] = []
    for pat in item.patterns:
        for m in re.finditer(pat, text, flags=re.M):
            count += 1
            if len(samples) < 2:
                lo = max(0, m.start() - 20)
                samples.append(text[lo : m.end() + 20].replace("\n", " ").strip()[:60])
    return count, samples


def _ending_token(sentence: str) -> str | None:
    """문장의 종결 토큰 — 끝 부호 제거 후 마지막 두 글자(한글이 아니면 None)."""
    core = _ENDING_PUNCT_RE.sub("", sentence.strip())
    if len(core) < 2 or not re.match(r"[가-힣]{2}$", core[-2:]):
        return None
    return core[-2:]


def _max_ending_run(text: str) -> tuple[int, list[str]]:
    """E-2 — 같은 종결 토큰이 연속되는 최장 길이."""
    run = best = 0
    prev: str | None = None
    sample: list[str] = []
    for s in _sentences(text):
        tok = _ending_token(s)
        if tok is not None and tok == prev:
            run += 1
        else:
            run = 1 if tok is not None else 0
        if run > best:
            best = run
            sample = [s.strip()[:60]]
        prev = tok
    return best, sample


def detect_ai_tells(text: str, scope: Scope = "chat") -> list[AiTellFinding]:
    """임계(threshold) 이상 나타난 패턴만 돌려준다(로그·검수용, 본문 불변)."""
    out: list[AiTellFinding] = []
    if not text or not text.strip():
        return out
    for it in _items_for(scope):
        if it.id == "E-2":
            count, samples = _max_ending_run(text)
        else:
            count, samples = _count_matches(it, text)
        if count >= it.threshold:
            out.append(AiTellFinding(
                id=it.id, severity=it.severity, label=it.label,
                count=count, threshold=it.threshold, samples=samples,
            ))
    return out


def s1_ids(text: str, scope: Scope = "daily") -> set[str]:
    """본문에 나타난 S1 패턴 id 집합(임계 무관, 1회라도) — 오늘의 운세 교정 줄 검증용."""
    found: set[str] = set()
    for it in _items_for(scope):
        if it.severity != "S1" or not it.patterns:
            continue
        if any(re.search(p, text, flags=re.M) for p in it.patterns):
            found.add(it.id)
    return found


def _apply_fix_outside_quotes(text: str, pattern: str, repl: str) -> str:
    parts = _QUOTE_SPLIT_RE.split(text)
    for i in range(0, len(parts), 2):  # 짝수 인덱스 = 따옴표 밖
        parts[i] = re.sub(pattern, repl, parts[i], flags=re.M)
    return "".join(parts)


def apply_safe_fixes(text: str, scope: Scope = "chat") -> tuple[str, list[AiTellFixApplied], bool]:
    """사전 `fix` 가 있는 항목만 표층 치환. 보호 글자(간지·숫자)가 변하면 전부 폐기.

    Returns:
        (교정본, 적용 목록, 폐기 여부). 폐기되면 교정본은 원문이고 적용 목록은 빈 리스트.
    """
    if not text:
        return text, [], False
    out = text
    applied: list[AiTellFixApplied] = []
    for it in _items_for(scope):
        before_item = out
        for fx in it.fix or []:
            out = _apply_fix_outside_quotes(out, fx.pattern, fx.repl)
        if out != before_item:  # 항목당 1건(하위 치환 규칙 수와 무관)
            applied.append(AiTellFixApplied(
                id=it.id,
                before=_diff_sample(before_item, out),
                after=_after_sample(before_item, out),
            ))
    if not applied:
        return text, [], False
    if Counter(_PROTECTED_RE.findall(text)) != Counter(_PROTECTED_RE.findall(out)):
        return text, [], True
    # 연속 공백·문두 공백 정리(삭제 교정의 잔흔). 개행은 보존한다.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"(?m)^[ \t]+", "", out)
    return out, applied, False


def _first_diff(before: str, after: str) -> int:
    n = min(len(before), len(after))
    i = 0
    while i < n and before[i] == after[i]:
        i += 1
    return i


def _diff_sample(before: str, after: str) -> str:
    """첫 변경 지점 주변 40자(교정 전) — 로그 표본."""
    i = _first_diff(before, after)
    return before[max(0, i - 15) : i + 25].replace("\n", " ")


def _after_sample(before: str, after: str) -> str:
    """같은 지점의 교정 후 40자."""
    i = _first_diff(before, after)
    return after[max(0, i - 15) : i + 25].replace("\n", " ")


def audit_ai_tells(text: str, scope: Scope = "chat") -> AiTellAudit:
    """자동 교정 → 잔존 패턴 탐지. 본문 외 어떤 값도 바꾸지 않는다."""
    fixed, fixes, discarded = apply_safe_fixes(text, scope)
    findings = detect_ai_tells(fixed, scope)
    return AiTellAudit(text=fixed, findings=findings, fixes=fixes, fixes_discarded=discarded)
