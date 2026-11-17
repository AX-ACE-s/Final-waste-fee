"""사용자가 쓴 설명 문장 읽기 — 계획서 ② '제품 설명을 읽고 지자체 표준 품목·규격으로 번역'.

예) "폭 180cm 3인용 소파"  -> 품목 SOFA, 폭 180cm, 3인
    "450리터 양문형 냉장고" -> 품목 FRIDGE, 용량 450L, 단어 '양문형'
    "18평형 에어컨 2개"    -> 품목 AIRCON, 면적 약 59.5㎡, 수량 2

AI 추측이 아니라 규칙으로만 읽는다. 단위가 적힌 숫자만 치수로 보고,
방향(폭·높이 등)이 없는 길이는 엔진이 '확인 필요'로 미리 채워 두기만 한다.
"""
from __future__ import annotations

import re

from etl.normalize import DIM_LABELS, ItemMatcher, fmt, nfkc, normalize_name, parse_spec

PYEONG_M2 = 3.305785  # 1평 = 3.305785㎡
LENGTH_DIMS = ("width", "length", "height", "size", "width_depth", "diameter")

# 한글 단위 → 파서가 아는 단위 (긴 것부터 바꿔야 '센티미터'가 '센티'+'미터'로 쪼개지지 않음)
UNIT_WORDS = [("센티미터", "cm"), ("밀리미터", "mm"), ("킬로그램", "kg"), ("센티", "cm"), ("센치", "cm"),
              ("킬로", "kg"), ("키로", "kg"), ("리터", "l"), ("미터", "m"), ("너비", "폭")]
STOP = {"모든규격", "규격", "기타", "포함", "별도", "이상", "이하", "미만", "초과", "기준"}

_matcher: ItemMatcher | None = None


def matcher() -> ItemMatcher:
    global _matcher
    if _matcher is None:
        _matcher = ItemMatcher()
    return _matcher


def _prep(text: str) -> str:
    s = nfkc(text).lower()
    for a, b in UNIT_WORDS:
        s = s.replace(a, b)
    return re.sub(r"(당|기준)", " ", s)


def short_label(dim: str, v: float) -> str:
    unit = DIM_LABELS[dim][1]
    if dim == "seats":
        return f"{fmt(v)}인용"
    if dim == "tiers":
        return f"{fmt(v)}단"
    name = {"width": "폭", "length": "길이", "height": "높이", "size": "크기", "width_depth": "가로·세로",
            "diameter": "지름", "inch": "화면", "weight": "용량", "volume": "용량", "area": "면적",
            "ton": "용량", "count": "개수"}[dim]
    return f"{name} {fmt(v)}{unit}"


def read(text: str) -> dict:
    """설명 문장 → {items, hints, quantity, labels, norm}"""
    text = (text or "").strip()
    out = {"items": [], "hints": {}, "quantity": None, "labels": [], "norm": ""}
    if not text:
        return out
    s = _prep(text)

    # 평형(에어컨) → ㎡
    m = re.search(r"(\d+(?:\.\d+)?)\s*평형?", s)
    if m:
        v = round(float(m.group(1)) * PYEONG_M2, 1)
        out["hints"]["area"] = v
        out["labels"].append(f"{m.group(1)}평(약 {fmt(v)}㎡)")
        s = s[:m.start()] + " " + s[m.end():]

    # 수량: '2개' (단, '5개 미만'처럼 규격 표현은 제외)
    m = re.search(r"(\d+)\s*개(?!\s*(?:이상|이하|미만|초과))", s)
    if m:
        out["quantity"] = int(m.group(1))
        s = s[:m.start()] + " " + s[m.end():]

    # 치수: 규격 파서를 그대로 써서, 정확한 값(이상·미만 없는 값)만 채택
    p = parse_spec(s)
    for r in p.ranges:
        if r.min is not None and r.min == r.max and r.dim not in out["hints"]:
            out["hints"][r.dim] = r.min
            out["labels"].append(short_label(r.dim, r.min))

    # 품목: 문장 안에 들어 있는 동의어 중 가장 긴 것 우선
    norm = normalize_name(text, matcher().typos)
    out["norm"] = norm
    hits = sorted(((len(syn), code) for syn, code in matcher().syn.items() if len(syn) >= 2 and syn in norm),
                  reverse=True)
    for _, code in hits:
        if code not in out["items"]:
            out["items"].append(code)
    return out


def tokens(text: str) -> list[str]:
    """'라텍스, 포켓스프링' / '보조쇼파(스툴 등)' → 비교용 단어 목록"""
    parts = re.split(r"[,\s/·()\[\]+]+", nfkc(text))
    return [t for t in (normalize_name(p, matcher().typos) for p in parts) if len(t) >= 2 and t not in STOP]


def mentioned(label: str, norm_desc: str, stop: set[str]) -> bool:
    """설명에 이 선택지를 가리키는 단어가 들어 있는가 (품목명 자체는 제외)"""
    return any(t in norm_desc for t in tokens(label) if t not in stop and not any(t in w for w in stop))
