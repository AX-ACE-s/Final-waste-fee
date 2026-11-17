"""품목명 정규화와 규격(대형폐기물규격) 텍스트 파싱.

원칙: 원문(raw)은 항상 보존하고, 해석 결과는 별도 필드에 담는다.
해석할 수 없는 규격은 억지로 숫자로 바꾸지 않고 '선택형(categorical)'으로 남긴다.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "mappings" / "standard_items.json"

# ---------------------------------------------------------------------------
# 1. 품목명 정규화
# ---------------------------------------------------------------------------

_PAREN = re.compile(r"\([^)]*\)")


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def normalize_name(raw: str, typos: dict | None = None) -> str:
    """'소파(쿠션 별도)' -> '소파', '침대 매트리스' -> '침대매트리스', '쇼파' -> '소파'."""
    s = nfkc(raw).lower()
    s = _PAREN.sub("", s)
    s = re.sub(r"[\s·/+]", "", s)
    s = s.replace(",", "")
    for wrong, right in (typos or {}).items():
        s = s.replace(wrong, right)
    return s


def split_tokens(raw: str, typos: dict | None = None) -> list[str]:
    """복합 품목명 분리: '옥매트, 전기매트, 황토매트' / '서랍장 신발장' -> 개별 토큰."""
    s = _PAREN.sub("", nfkc(raw).lower())
    parts = re.split(r"[,\s·/]+", s)
    toks = [normalize_name(p, typos) for p in parts if p.strip()]
    return [t for t in toks if len(t) >= 2]  # '평 상' → '상' 같은 한 글자 오매칭 방지


@dataclass
class NameMatch:
    codes: list[str]
    method: str  # exact | synonym | typo | split | none


class ItemMatcher:
    def __init__(self, mapping: dict | None = None):
        mapping = mapping or load_mapping()
        self.typos = mapping.get("typos", {})
        self.items = {it["code"]: it for it in mapping["items"]}
        self.syn: dict[str, str] = {}
        for it in mapping["items"]:
            self.syn[normalize_name(it["name"], self.typos)] = it["code"]
            for s in it["synonyms"]:
                self.syn[normalize_name(s, self.typos)] = it["code"]

    def match(self, raw_name: str) -> NameMatch:
        norm = normalize_name(raw_name, self.typos)
        if norm in self.syn:
            code = self.syn[norm]
            if normalize_name(raw_name) != norm:
                return NameMatch([code], "typo")
            exact = norm == normalize_name(self.items[code]["name"], self.typos)
            return NameMatch([code], "exact" if exact else "synonym")
        codes = []
        for tok in split_tokens(raw_name, self.typos):
            if tok in self.syn and self.syn[tok] not in codes:
                codes.append(self.syn[tok])
        if codes:
            return NameMatch(codes, "split")
        return NameMatch([], "none")

    def search(self, query: str) -> list[str]:
        """사용자 검색어 -> 표준 품목 코드 목록 (동의어 부분일치 포함)."""
        q = normalize_name(query, self.typos)
        if not q:
            return []
        hits = []
        for syn, code in self.syn.items():
            if (q in syn or (len(syn) >= 2 and syn in q)) and code not in hits:
                hits.append(code)
        return hits


# ---------------------------------------------------------------------------
# 2. 규격 파싱
# ---------------------------------------------------------------------------

# 단위 -> (차원 기본값, 표준 단위, 환산 계수)
UNITS = {
    "cm": ("length", "cm", 1.0),
    "mm": ("length", "cm", 0.1),
    "m": ("length", "cm", 100.0),
    "인치": ("inch", "인치", 1.0),
    "kg": ("weight", "kg", 1.0),
    "l": ("volume", "L", 1.0),
    "m2": ("area", "㎡", 1.0),
    "톤": ("ton", "톤", 1.0),
}
UNIT_RE = r"(m2|cm|mm|m|인치|kg|l|톤)"
NUM = r"(\d+(?:\.\d+)?)"

# 방향 단어 -> 차원. '가로세로'가 '가로'보다 먼저 검사되어야 한다.
DIM_WORDS = [("가로세로", "width_depth"), ("가로", "width"), ("폭", "width"), ("길이", "length"),
             ("긴면", "length"), ("높이", "height"), ("직경", "diameter")]

DIM_LABELS = {
    "width": ("가로(폭) 길이", "cm"),
    "width_depth": ("가로·세로 길이", "cm"),
    "length": ("길이", "cm"),
    "height": ("높이", "cm"),
    "diameter": ("지름", "cm"),
    "size": ("크기", "cm"),  # 수수료표에 가로·세로·높이 구분 없이 길이만 적힌 경우
    "inch": ("화면 크기", "인치"),
    "weight": ("용량/무게", "kg"),
    "volume": ("용량", "L"),
    "area": ("면적", "㎡"),
    "ton": ("용량", "톤"),
    "seats": ("인용(사용 인원)", "인"),
    "tiers": ("단 수", "단"),
    "count": ("개수", "개"),
}

# 입력값 허용 범위(표준 단위 기준). 이 범위를 벗어나면 단위 착오로 보고 수정 안내.
SANITY = {
    "cm": (10, 1000), "인치": (5, 150), "kg": (0.1, 200), "L": (1, 5000), "㎡": (0.1, 1000),
    "톤": (0.1, 50), "인": (1, 30), "단": (1, 20), "개": (1, 200),
}

PER_UNIT_RE = re.compile(NUM + r"\s*" + UNIT_RE + r"\s*(?:마대)?\s*(?:당|기준)")


@dataclass
class Range:
    dim: str
    unit: str
    min: float | None = None
    min_inc: bool = True
    max: float | None = None
    max_inc: bool = False

    def contains(self, v: float) -> bool:
        if self.min is not None and (v < self.min or (v == self.min and not self.min_inc)):
            return False
        if self.max is not None and (v > self.max or (v == self.max and not self.max_inc)):
            return False
        return True

    def text(self) -> str:
        lo = hi = ""
        if self.min is not None:
            lo = f"{fmt(self.min)}{self.unit} {'이상' if self.min_inc else '초과'}"
        if self.max is not None:
            hi = f"{fmt(self.max)}{self.unit} {'이하' if self.max_inc else '미만'}"
        if self.min is not None and self.max is not None and self.min == self.max:
            return f"{fmt(self.min)}{self.unit}"
        return " ".join(p for p in (lo, hi) if p)


def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


@dataclass
class ParsedSpec:
    raw: str
    spec_type: str  # all | range | categorical | per_unit
    ranges: list[Range] = field(default_factory=list)
    qualifier: str = ""
    per_unit_amount: float | None = None
    per_unit_unit: str | None = None
    per_unit_dim: str | None = None
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _dim_before(text: str, pos: int) -> str | None:
    window = text[max(0, pos - 8):pos]
    window = re.split(r"[,(]", window)[-1]
    for word, dim in DIM_WORDS:
        if word in window:
            return dim
    return None


def _op(word: str | None) -> str | None:
    return word if word in ("이상", "이하", "미만", "초과") else None


def parse_spec(raw: str) -> ParsedSpec:
    original = raw
    s = nfkc(raw).lower()
    s = s.replace("㎏", "kg").replace("ℓ", "l")
    if re.fullmatch(r"모든\s*규격|전\s*규격", s.strip()) or s.strip() in ("", "-"):
        return ParsedSpec(original, "all")

    # 단위당 요금: '1㎡ 당', '100L 마대 기준', '가로 90cm 당', '500ℓ당', '10kg 기준'
    # '1㎡당(100cmx100cm)'처럼 면적·용량·무게 단위가 분명하면 가로×세로 표기가 붙어 있어도 단위당 요금으로 본다.
    m = PER_UNIT_RE.search(s)
    has_rect = re.search(r"\d\s*(?:m|cm)?\s*[x×*]\s*\d", s)
    if m and m.group(2) in UNITS and (not has_rect or m.group(2) in ("m2", "l", "kg")):
        dim0, unit, k = UNITS[m.group(2)]
        dim = _dim_before(s, m.start()) or dim0
        return ParsedSpec(original, "per_unit", per_unit_amount=float(m.group(1)) * k,
                          per_unit_unit=unit, per_unit_dim=dim, qualifier=original)

    # 가로×세로 형태('60cm×100cm 당'), 차량 등급 표기는 단일 치수로 해석하지 않는다(임의 해석 금지).
    if has_rect or "차량" in s:
        return ParsedSpec(original, "categorical", qualifier=original)

    ranges: list[Range] = []
    consumed: list[tuple[int, int]] = []

    def add(dim0: str, unit_key: str, start: int, lo, lo_inc, hi, hi_inc, end: int):
        d0, unit, k = UNITS[unit_key]
        dim = _dim_before(s, start) or ("size" if d0 == "length" else d0)
        ranges.append(Range(dim, unit, None if lo is None else float(lo) * k, lo_inc,
                            None if hi is None else float(hi) * k, hi_inc))
        consumed.append((start, end))

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in consumed)

    # (1) A~B단위 [미만|이하]  /  A단위 이상 ~ B단위 미만
    for mm in re.finditer(NUM + r"\s*" + UNIT_RE + r"?\s*(?:이상)?\s*~\s*" + NUM + r"\s*" + UNIT_RE + r"\s*(미만|이하)?", s):
        u = mm.group(4)
        u1 = mm.group(2) or u
        k1 = UNITS[u1][2] / UNITS[u][2]
        add(UNITS[u][0], u, mm.start(), float(mm.group(1)) * k1, True, mm.group(3),
            mm.group(5) == "이하", mm.end())
    # (2) A[단위] 이상[,] B단위 미만|이하
    for mm in re.finditer(NUM + r"\s*" + UNIT_RE + r"?\s*(이상|초과)\s*,?\s*" + NUM + r"\s*" + UNIT_RE + r"\s*(미만|이하)", s):
        if not free(mm.start(), mm.end()):
            continue
        u = mm.group(5)
        u1 = mm.group(2) or u
        k1 = UNITS[u1][2] / UNITS[u][2]
        add(UNITS[u][0], u, mm.start(), float(mm.group(1)) * k1, mm.group(3) == "이상",
            mm.group(4), mm.group(6) == "이하", mm.end())
    # (3) 단일 경계: A단위 이상|미만|이하|초과  또는 정확값(6.5kg)
    for mm in re.finditer(NUM + r"\s*" + UNIT_RE + r"(?![a-z0-9])\s*(이상|이하|미만|초과)?", s):
        if not free(mm.start(), mm.end()):
            continue
        u, v, op = mm.group(2), float(mm.group(1)), _op(mm.group(3))
        if op in ("이상", "초과"):
            add(UNITS[u][0], u, mm.start(), v, op == "이상", None, False, mm.end())
        elif op in ("이하", "미만"):
            add(UNITS[u][0], u, mm.start(), None, True, v, op == "이하", mm.end())
        else:
            add(UNITS[u][0], u, mm.start(), v, True, v, True, mm.end())

    # (4) 인용/인: '3인용', '2인이하', '6인용 이상', '4인용초과'
    for mm in re.finditer(r"(\d+)\s*인용?\s*(이상|이하|미만|초과)?", s):
        if not free(mm.start(), mm.end()):
            continue
        v, op = float(mm.group(1)), _op(mm.group(2))
        r = Range("seats", "인")
        if op == "이상":
            r.min, r.min_inc = v, True
        elif op == "초과":
            r.min, r.min_inc = v, False
        elif op == "이하":
            r.max, r.max_inc = v, True
        elif op == "미만":
            r.max, r.max_inc = v, False
        else:
            r.min = r.max = v
            r.max_inc = True
        ranges.append(r)
        consumed.append((mm.start(), mm.end()))
    # (5) 단: '5단', '3단 이하', '6단 이상'
    for mm in re.finditer(r"(\d+)\s*단\s*(이상|이하|미만|초과)?", s):
        if not free(mm.start(), mm.end()):
            continue
        v, op = float(mm.group(1)), _op(mm.group(2))
        r = Range("tiers", "단")
        if op in ("이상", "초과"):
            r.min, r.min_inc = v, op == "이상"
        elif op in ("이하", "미만"):
            r.max, r.max_inc = v, op == "이하"
        else:
            r.min = r.max = v
            r.max_inc = True
        ranges.append(r)
        consumed.append((mm.start(), mm.end()))
    # (6) 개수: '5개미만', '10개이상'
    for mm in re.finditer(r"(\d+)\s*개\s*(이상|이하|미만|초과)", s):
        if not free(mm.start(), mm.end()):
            continue
        v, op = float(mm.group(1)), mm.group(2)
        r = Range("count", "개")
        if op in ("이상", "초과"):
            r.min, r.min_inc = v, op == "이상"
        else:
            r.max, r.max_inc = v, op == "이하"
        ranges.append(r)
        consumed.append((mm.start(), mm.end()))

    # 수식어(qualifier) = 원문에서 숫자 구간·방향어·괄호를 걷어낸 나머지
    q = s
    for a, b in sorted(consumed, reverse=True):
        q = q[:a] + " " + q[b:]
    for word, _ in DIM_WORDS:
        q = q.replace(word, " ")
    q = re.sub(r"[()~]", " ", q)
    q = re.sub(r"\s*,\s*", ", ", q)
    q = re.sub(r"\s+", " ", q).strip(" ,")
    q = re.sub(r"(1짝당|1칸당|1채당|개당)", "", q).strip(" ,")

    anomalies = []
    for r in ranges:
        lo, hi = SANITY.get(r.unit, (None, None))
        for v in (r.min, r.max):
            if v is not None and lo is not None and r.unit != "cm" and r.dim not in ("seats", "tiers", "count") and not (lo <= v <= hi):
                anomalies.append(f"비정상 수치 의심: {fmt(v)}{r.unit} (허용 {lo}~{hi})")
            if r.unit == "cm" and v is not None and v < 10:
                anomalies.append(f"단위 오기 의심: {fmt(v)}cm (원문 '{original}')")

    if not ranges:
        return ParsedSpec(original, "categorical", qualifier=original.strip())
    return ParsedSpec(original, "range", ranges=ranges, qualifier=q, anomalies=sorted(set(anomalies)))


if __name__ == "__main__":  # 간단 확인용
    for t in ["가로 1.2~1.6m 미만", "편수, 소형(가로 1.2~1.6m 미만)", "일반형 2인용(가로 1.2~1.5m미만)",
              "3인용(폭 1.8m 이하)", "폭 40이상 80cm 미만", "1㎡ 당", "100L 마대 기준", "29인치 이상 49인치 미만",
              "3㎏~10kg미만", "2M X 2M 이상", "모든규격", "대리석 6인용 이상", "긴면1m이상2m미만",
              "가로세로1m미만", "일반형 1인용(가로 1.2cm 미만)", "수납장 3단 이상", "6.5kg", "높이1m미만"]:
        p = parse_spec(t)
        print(t, "=>", p.spec_type, [(r.dim, r.text()) for r in p.ranges], repr(p.qualifier), p.per_unit_amount, p.anomalies)
