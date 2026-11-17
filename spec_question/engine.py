"""기능 ② 지역 기준 맞춤 규격 질문 · 실측 보정 엔진.

상태를 서버에 저장하지 않는다. 클라이언트가 지금까지의 답(answers)을 보내면
엔진이 '다음에 필요한 질문 1개' 또는 '결과'를 돌려준다.

answers 키
  local_item : int     같은 표준품목에 해당하는 지자체 품목이 여러 개일 때 선택
  group      : str     규격 유형(수식어) 선택. 예: '대리석' / '목재'
  measure    : {dim: number}  실측값(표준 단위: cm, 인치, kg, L, ㎡, 인, 단, 개)
  spec       : int     공식 규격 직접 선택(크기를 모를 때)
  amount     : number  단위당 요금 품목의 수량(㎡, L 등)
  quantity   : int     같은 물건 개수(기본 1)

원칙
  * 지자체 데이터에 있는 규격만 묻는다. 데이터에 없는 항목을 필수로 만들지 않는다.
  * 일치하는 규격이 없거나 데이터가 충돌하면 금액을 만들어내지 않고 '확인 필요'로 돌려준다.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass

from spec_question import describe
from etl.normalize import DIM_LABELS, SANITY, Range, fmt, normalize_name

DIM_PRIORITY = ["width", "length", "height", "size", "width_depth", "diameter", "inch", "volume",
                "weight", "area", "ton", "tiers", "seats", "count"]
MEASURE_GROUP = "__measure__"
LAW_SEARCH = ("https://www.law.go.kr/lsSc.do?section=&menuId=1&subMenuId=15&tabMenuId=81"
              "&eventGubun=060101&query={q}")


def _jong(word: str) -> int | None:
    """마지막 글자의 받침 번호(0=없음). 한글이 아니면 None."""
    for ch in reversed(word.strip()):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28
        if ch.isalnum():
            return None
    return None


def eul(word: str) -> str:
    j = _jong(word)
    return word + ("(을)를" if j is None else "을" if j else "를")


def ro(word: str) -> str:
    j = _jong(word)
    return word + ("(으)로" if j is None else "으로" if j and j != 8 else "로")


class EngineError(Exception):
    def __init__(self, status: str, message: str, **extra):
        super().__init__(message)
        self.payload = {"status": status, "message": message, **extra}


@dataclass
class SpecRow:
    id: int
    raw: str
    spec_type: str
    qualifier: str
    ranges: list[Range]
    per_unit_amount: float | None
    per_unit_unit: str | None
    per_unit_dim: str | None
    anomalies: list[str]
    fee: int
    is_free: bool
    base_date: str | None
    source: dict

    def range_for(self, dim: str) -> Range | None:
        return next((r for r in self.ranges if r.dim == dim), None)

    def option(self) -> dict:
        return {"value": self.id, "label": self.raw}


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def get_region(con, region_id: int) -> sqlite3.Row:
    r = con.execute("SELECT * FROM region WHERE id=?", (region_id,)).fetchone()
    if not r:
        raise EngineError("not_found", "선택한 지역의 수수료 데이터가 없습니다.")
    return r


def local_items_for(con, region_id: int, standard_code: str | None, local_item_id: int | None) -> list[sqlite3.Row]:
    if local_item_id:
        rows = con.execute("SELECT * FROM local_item WHERE id=? AND region_id=?", (local_item_id, region_id)).fetchall()
    else:
        rows = con.execute("""SELECT li.* FROM local_item li JOIN item_mapping m ON m.local_item_id=li.id
                              JOIN standard_item s ON s.id=m.standard_item_id
                              WHERE li.region_id=? AND s.code=? ORDER BY li.raw_name""",
                           (region_id, standard_code)).fetchall()
    return rows


def load_specs(con, local_item_id: int) -> list[SpecRow]:
    out = []
    for r in con.execute("""SELECT s.*, f.fee, f.is_free, f.base_date, f.ordinance_name, f.ordinance_url,
                                   d.kind, d.name AS src_name, d.url AS src_url, d.file_name
                            FROM item_specification s JOIN disposal_fee f ON f.spec_id=s.id
                            JOIN data_source d ON d.id=f.source_id
                            WHERE s.local_item_id=? ORDER BY s.id""", (local_item_id,)):
        out.append(SpecRow(
            r["id"], r["raw_spec"], r["spec_type"], r["qualifier"] or "",
            [Range(**x) for x in json.loads(r["ranges_json"])],
            r["per_unit_amount"], r["per_unit_unit"], r["per_unit_dim"],
            json.loads(r["anomalies_json"] or "[]"), r["fee"], bool(r["is_free"]), r["base_date"],
            {"kind": r["kind"], "name": r["src_name"], "url": r["src_url"], "file": r["file_name"],
             "ordinance_name": r["ordinance_name"], "ordinance_url": r["ordinance_url"]}))
    return out


# ---------------------------------------------------------------------------
# 규격 구조 분석
# ---------------------------------------------------------------------------

def common_dims(rows: list[SpecRow]) -> list[str]:
    """모든 행이 공통으로 가진 수치 기준(우선순위 순)"""
    if len(rows) < 2 or any(r.spec_type != "range" for r in rows):
        return []
    dims = set.intersection(*[{x.dim for x in r.ranges} for r in rows])
    return [d for d in DIM_PRIORITY if d in dims]


def common_dim(rows: list[SpecRow]) -> str | None:
    d = common_dims(rows)
    return d[0] if d else None


def make_groups(rows: list[SpecRow]) -> dict[str, list[SpecRow]]:
    groups: dict[str, list[SpecRow]] = {}
    for r in rows:
        key = (r.qualifier or MEASURE_GROUP) if r.spec_type == "range" else r.raw
        groups.setdefault(key, []).append(r)
    if len(groups) > 1 and all(len(g) == 1 for g in groups.values()):
        ranged = [r for r in rows if r.spec_type == "range"]
        if common_dim(ranged):
            merged = {MEASURE_GROUP: ranged}
            for r in rows:
                if r.spec_type != "range":
                    merged[r.raw] = [r]
            groups = merged
    return groups


def group_label(key: str, rows: list[SpecRow], item_name: str) -> str:
    if key == MEASURE_GROUP:
        d = common_dim(rows)
        how = DIM_LABELS[d][0] if d else "규격"
        return f"일반 {item_name} ({ro(how)} 구분)"
    return key


def _interval(r: Range) -> tuple[float, float]:
    return (-math.inf if r.min is None else r.min, math.inf if r.max is None else r.max)


def match_measure(rows: list[SpecRow], dim: str, value: float) -> tuple[list[SpecRow], str]:
    """실측값이 들어가는 규격 구간을 찾는다. (후보들, 적용 규칙 설명)"""
    cands = [r for r in rows if r.range_for(dim) and r.range_for(dim).contains(value)]
    if len(cands) <= 1:
        return cands, "입력값이 포함되는 규격 구간 적용"
    ivs = {r.id: _interval(r.range_for(dim)) for r in cands}
    uniq = {iv for iv in ivs.values()}
    if len(uniq) == 1:
        return cands, "동일 구간 중복"
    for r in cands:
        lo, hi = ivs[r.id]
        if all(lo >= ivs[o.id][0] and hi <= ivs[o.id][1] for o in cands if o.id != r.id):
            same = [o for o in cands if ivs[o.id] == ivs[r.id]]
            return same, "입력값을 포함하는 구간이 여러 개여서 포함관계상 가장 좁은 구간 적용"
    return cands, "구간 중첩"


def conflicts_of(row: SpecRow, rows: list[SpecRow]) -> list[SpecRow]:
    return [r for r in rows if r.raw == row.raw and r.fee != row.fee]


# ---------------------------------------------------------------------------
# 질문 생성
# ---------------------------------------------------------------------------

def q_choice(qid: str, label: str, options: list[dict], help_: str = "") -> dict:
    return {"id": qid, "type": "choice", "label": label, "help": help_, "options": options}


def q_measure(dim: str, rows: list[SpecRow], item_name: str) -> dict:
    label, unit = DIM_LABELS[dim]
    lo, hi = SANITY.get(unit, (0, 1e9))
    bands = []
    for r in rows:
        rg = r.range_for(dim)
        bands.append({"spec": r.id, "label": r.raw, "range": rg.text()})
    return {
        "id": f"measure.{dim}", "type": "number", "dim": dim, "unit": unit, "min": lo, "max": hi,
        "label": f"{item_name}의 {eul(label)} 입력해 주세요 ({unit})",
        "help": ("이 지역 수수료표는 가로·세로 구분 없이 크기로만 나눠요. 줄자로 잰 값을 넣어 주세요(어느 쪽을 재는지 애매하면 관할 지자체에 확인)." if dim == "size"
                 else "줄자로 잰 값을 넣으면 우리 지역 규격 구간에 자동으로 맞춰 드려요." if unit == "cm"
                 else "몇 인용인지 숫자로 넣어 주세요." if dim == "seats"
                 else "서랍·칸이 몇 단인지 세어서 넣어 주세요." if dim == "tiers"
                 else "개수를 세어서 넣어 주세요." if dim == "count"
                 else "제품 라벨·설명서에 적힌 값을 넣어 주세요."),
        "allow_m": unit == "cm",
        "bands": bands,
        "fallback": q_choice("spec", "정확한 값을 모르면 공식 규격에서 고르세요", [r.option() for r in rows]),
    }


def q_amount(row: SpecRow) -> dict:
    unit = row.per_unit_unit
    label = DIM_LABELS.get(row.per_unit_dim or "", ("수량", unit))[0]
    lo, hi = SANITY.get(unit, (0, 1e9))
    lo, hi = min(lo, row.per_unit_amount), max(hi, row.per_unit_amount * 50)
    return {"id": "amount", "type": "number", "unit": unit, "min": lo, "max": hi,
            "label": f"{eul(label)} 입력해 주세요 ({unit})",
            "help": f"이 지역은 '{row.raw}' 기준으로 수수료를 매겨요. {fmt(row.per_unit_amount)}{unit}마다 {row.fee:,}원.",
            "allow_m": unit == "cm"}


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def _num(v, field: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise EngineError("invalid", "숫자로 입력해 주세요.", field=field)
    if math.isnan(x) or math.isinf(x):
        raise EngineError("invalid", "숫자로 입력해 주세요.", field=field)
    return x


def _check_sanity(x: float, unit: str, field: str, question: dict, bounds: tuple | None = None):
    lo, hi = bounds or SANITY.get(unit, (0, 1e9))
    if x <= 0:
        raise EngineError("invalid", "0보다 큰 값을 입력해 주세요.", field=field, question=question)
    if not (lo <= x <= hi):
        hint = ""
        if unit == "cm" and x < lo:
            hint = f" 혹시 미터(m) 단위로 넣으셨나요? {fmt(x)}m = {fmt(x * 100)}cm"
        elif unit == "cm" and x > hi:
            hint = " 혹시 밀리미터(mm)로 넣으셨나요?"
        raise EngineError("invalid", f"입력값이 허용 범위({fmt(lo)}~{fmt(hi)}{unit})를 벗어났어요.{hint}",
                          field=field, question=question)


def estimate(con, region_id: int, standard_code: str | None = None, local_item_id: int | None = None,
             answers: dict | None = None) -> dict:
    answers = dict(answers or {})
    measure = {k: v for k, v in (answers.get("measure") or {}).items() if v not in (None, "")}
    trail: list[str] = []  # 사용자가 확정한 내용(근거 표시용)
    desc = describe.read(answers.get("description") or "")
    hints = desc["hints"]
    try:
        region = get_region(con, region_id)
        std = None
        if standard_code:
            std = con.execute("SELECT * FROM standard_item WHERE code=?", (standard_code,)).fetchone()
            if not std:
                raise EngineError("not_found", "존재하지 않는 품목입니다. 품목을 다시 검색해 주세요.")
        elif not local_item_id:
            raise EngineError("invalid", "품목을 선택해 주세요.", field="item")

        locals_ = local_items_for(con, region_id, standard_code, local_item_id)
        if not locals_:
            others = []
            if std:
                others = [dict(r) for r in con.execute(
                    """SELECT DISTINCT rg.sido, rg.sigungu FROM region rg JOIN local_item li ON li.region_id=rg.id
                       JOIN item_mapping m ON m.local_item_id=li.id WHERE m.standard_item_id=?""", (std["id"],))]
            raise EngineError("not_found",
                              f"{region['sido']} {region['sigungu']} 수수료 데이터에서 '{std['name'] if std else '해당 품목'}'을(를) 찾지 못했어요. "
                              "관할 구·군청에 품목을 확인해 주세요. (임의로 금액을 계산하지 않습니다)",
                              other_regions=others)
        item_name = std["name"] if std else locals_[0]["raw_name"]

        # 1) 지자체 품목이 여러 개면 선택
        if len(locals_) > 1:
            chosen = answers.get("local_item")
            if (not chosen or int(chosen) not in [l["id"] for l in locals_]) and desc["norm"]:
                hit = [l for l in locals_ if normalize_name(l["raw_name"]) in desc["norm"]]
                if len(hit) == 1:
                    chosen = hit[0]["id"]
                    trail.append("설명에서 읽음 · 지역 품목")
            if not chosen or int(chosen) not in [l["id"] for l in locals_]:
                return {"status": "question", "question": q_choice(
                    "local_item", f"우리 지역에서는 '{item_name}'을(를) 다음 품목으로 나눠요. 어느 쪽인가요?",
                    [{"value": l["id"], "label": l["raw_name"]} for l in locals_])}
            local = next(l for l in locals_ if l["id"] == int(chosen))
        else:
            local = locals_[0]
        trail.append(f"지자체 품목: {local['raw_name']}")

        rows = load_specs(con, local["id"])
        if not rows:
            raise EngineError("not_found", "이 품목의 규격·수수료 데이터가 비어 있어요. 관할 지자체 확인이 필요합니다.")
        # 설명에서 선택지를 고를 때 품목명 자체는 근거로 쓰지 않는다 ('냉장고'가 '양문형 냉장고'를 고르면 안 됨)
        stop = {normalize_name(local["raw_name"])} | set(describe.tokens(local["raw_name"]))
        if std:
            stop |= {s for s, c in describe.matcher().syn.items() if c == std["code"]}

        selected: SpecRow | None = None
        rule = ""
        how = ""

        # 2) 공식 규격을 직접 고른 경우
        if answers.get("spec") not in (None, ""):
            sid = int(answers["spec"])
            selected = next((r for r in rows if r.id == sid), None)
            if not selected:
                raise EngineError("invalid", "이 품목에 없는 규격입니다. 다시 선택해 주세요.", field="spec")
            how = "choice"
            rule = "사용자가 공식 규격을 직접 선택"
        elif len(rows) == 1:
            selected = rows[0]
            how = "single"
            rule = "이 지역은 해당 품목 규격이 하나뿐" if selected.spec_type != "all" else "모든 규격 동일 요금"
        else:
            # 3) 규격 유형(수식어) 그룹
            groups = make_groups(rows)
            if len(groups) > 1:
                g = answers.get("group")
                if g not in groups and desc["norm"]:
                    g = _auto_group(groups, desc, stop)
                    if g:
                        trail.append(f"설명에서 읽음 · 종류: {g if g != MEASURE_GROUP else '일반'}")
                if g not in groups:
                    return {"status": "question", "question": q_choice(
                        "group", f"어떤 종류의 {item_name}인가요?",
                        [{"value": k, "label": group_label(k, v, item_name)} for k, v in groups.items()],
                        "지역 수수료표가 종류별로 요금을 다르게 정해 두었어요.")}
                grp = groups[g]
                if g != MEASURE_GROUP and not trail[-1].startswith("설명에서 읽음 · 종류"):
                    trail.append(f"종류: {g}")
            else:
                grp = rows
            if len(grp) == 1:
                selected, how, rule = grp[0], "group", "선택한 종류의 규격이 하나뿐"
            else:
                dims = common_dims(grp)
                dim = (next((d for d in dims if d in measure), None)
                       or next((d for d in dims if d in hints and _sane(hints[d], d)), None)
                       or (dims[0] if dims else None))
                if dim:
                    q = q_measure(dim, grp, item_name)
                    from_desc = False
                    if dim in measure:
                        v = _num(measure[dim], f"measure.{dim}")
                        _check_sanity(v, q["unit"], f"measure.{dim}", q)
                    elif dim in hints and _sane(hints[dim], dim):
                        v, from_desc = float(hints[dim]), True
                    else:
                        pre = _prefill(dim, hints)
                        if pre:
                            q["prefill"], q["prefill_note"] = pre
                        return {"status": "question", "question": q}
                    cands, rule = match_measure(grp, dim, v)
                    prefix = "설명에서 읽음 · " if from_desc else ("" if dim in ("seats", "tiers", "count") else "실측 ")
                    trail.append(f"{prefix}{DIM_LABELS[dim][0]}: {fmt(v)}{q['unit']}")
                    if not cands:
                        bands = ", ".join(f"{b['label']}" for b in q["bands"])
                        return {"status": "question", "question": q["fallback"],
                                "warning": f"입력하신 {fmt(v)}{q['unit']}에 해당하는 규격 구간이 이 지역 수수료표에 없어요 "
                                           f"(등록된 규격: {bands}). 가장 가까운 공식 규격을 직접 골라 주세요. "
                                           "애매하면 관할 지자체 확인을 권해요."}
                    if len(cands) > 1:
                        return _needs_confirmation(region, item_name, local, cands, trail,
                                                   f"입력값에 해당하는 규격 구간이 수수료표에 {len(cands)}개 있고 금액이 달라요({rule}).")
                    selected, how = cands[0], "measure"
                else:
                    hit = [r for r in grp if desc["norm"] and describe.mentioned(r.raw, desc["norm"], stop)]
                    if len(hit) == 1:
                        selected, how, rule = hit[0], "description", "설명에 적힌 종류와 일치하는 공식 규격 적용"
                        trail.append(f"설명에서 읽음 · 규격: {hit[0].raw}")
                if selected is None and not common_dim(grp) and len(grp) > 1:
                    return {"status": "question", "question": q_choice(
                        "spec", f"{item_name}의 규격을 골라 주세요", [r.option() for r in grp],
                        "지역 수수료표에 적힌 공식 규격 그대로예요.")}

        # 4) 데이터 충돌(같은 규격 문구, 다른 금액)
        conf = conflicts_of(selected, rows)
        if conf:
            return _needs_confirmation(region, item_name, local, [selected, *conf], trail,
                                       "같은 규격에 서로 다른 수수료가 등록되어 있어요(원본 데이터 충돌).")

        # 5) 단위당 요금
        units = 1
        if selected.spec_type == "per_unit":
            q = q_amount(selected)
            if answers.get("amount") in (None, ""):
                return {"status": "question", "question": q}
            amt = _num(answers["amount"], "amount")
            lo, hi = SANITY.get(selected.per_unit_unit, (0, 1e9))
            bounds = (min(lo, selected.per_unit_amount), max(hi, selected.per_unit_amount * 50))
            q["min"], q["max"] = bounds
            _check_sanity(amt, selected.per_unit_unit, "amount", q, bounds)
            units = math.ceil(round(amt / selected.per_unit_amount, 6))
            trail.append(f"수량: {fmt(amt)}{selected.per_unit_unit} → {units}단위")

        qty = answers.get("quantity")
        qty = 1 if qty in (None, "") else qty
        qty = int(_num(qty, "quantity"))
        if not (1 <= qty <= 50):
            raise EngineError("invalid", "개수는 1~50 사이로 입력해 주세요.", field="quantity")

        merged = {**{k: v for k, v in hints.items() if _sane(v, k)}, **measure}
        return _result(region, std, local, selected, rows, how, rule, units, qty, trail, merged, standard_code)
    except EngineError as e:
        return e.payload


def _sane(v, dim: str) -> bool:
    unit = DIM_LABELS.get(dim, ("", ""))[1]
    lo, hi = SANITY.get(unit, (0, 1e9))
    try:
        return lo <= float(v) <= hi
    except (TypeError, ValueError):
        return False


def _prefill(dim: str, hints: dict):
    """설명에 길이가 있지만 방향이 달라(예: '180cm'인데 기준은 '높이') 자동 적용하지 않고 칸에 미리 넣어 둔다."""
    if dim not in describe.LENGTH_DIMS:
        return None
    for d in describe.LENGTH_DIMS:
        if d in hints and _sane(hints[d], d):
            got = describe.short_label(d, hints[d])
            return hints[d], f"설명에서 읽은 '{got}'를 넣어 두었어요. 이 지역은 '{DIM_LABELS[dim][0]}' 기준이라 맞는지 확인하고 눌러 주세요."
    return None


def _auto_group(groups: dict, desc: dict, stop: set) -> str | None:
    named = [k for k in groups if k != MEASURE_GROUP and describe.mentioned(k, desc["norm"], stop)]
    if len(named) == 1:
        return named[0]
    if not named and MEASURE_GROUP in groups:
        if set(desc["hints"]) & set(common_dims(groups[MEASURE_GROUP])):
            return MEASURE_GROUP
    return None


def _source_block(row: SpecRow, region) -> dict:
    return {
        "dataset": row.source["name"],
        "kind": row.source["kind"],
        "url": row.source["url"],
        "file": row.source["file"],
        "base_date": row.base_date,
        "manager_org": region["manager_org"],
        "ordinance_name": row.source["ordinance_name"],
        "ordinance_url": row.source["ordinance_url"],
        "ordinance_search_url": LAW_SEARCH.format(q=f"{region['sigungu']} 폐기물 관리 조례"),
    }


def _needs_confirmation(region, item_name, local, cands: list[SpecRow], trail, message) -> dict:
    return {"status": "needs_confirmation", "message": message + " 금액을 임의로 고르지 않고 관할 지자체 확인을 안내합니다.",
            "region": f"{region['sido']} {region['sigungu']}", "item": item_name, "local_item": local["raw_name"],
            "candidates": [{"spec_id": c.id, "spec": c.raw, "fee": c.fee, "base_date": c.base_date} for c in cands],
            "inputs": trail, "source": _source_block(cands[0], region)}


def _result(region, std, local, row: SpecRow, rows, how, rule, units, qty, trail, measure, standard_code=None) -> dict:
    warnings, correction = [], None
    if row.anomalies:
        warnings.append("원본 규격에 오기가 의심되는 값이 있어요: " + "; ".join(row.anomalies))
    if row.source["kind"] == "standard_data_preview":
        warnings.append("개발용 미리보기 발췌 데이터로 계산했어요. 실제 서비스 전 전체 원본 CSV로 갱신해야 해요.")

    # 실측 보정: 규격을 직접 골랐는데 실측값이 그 규격과 맞지 않으면 다른 규격을 제안
    verify = []
    for rg in row.ranges:
        label, unit = DIM_LABELS[rg.dim]
        v = measure.get(rg.dim)
        if v in (None, ""):
            if how == "choice" and rg.dim not in ("seats", "tiers", "count"):
                verify.append({"dim": rg.dim, "label": label, "unit": unit, "range": rg.text()})
            continue
        v = float(v)
        if how == "choice" and rg.contains(v):
            # 공식 규격을 고른 뒤 실측값으로 확인된 경우(실측 보정 포함): 근거에 실측값과 결정 방식을 남긴다
            note = f"실측 {label}: {fmt(v)}{unit}"
            if note not in trail:
                trail.append(note)
            rule = "공식 규격을 고른 뒤 실측값으로 확인"
        if not rg.contains(v):
            peers = [r for r in rows if r.range_for(rg.dim) and r.qualifier == row.qualifier]
            cands, _ = match_measure(peers, rg.dim, v)
            msg = f"고르신 규격({row.raw})은 {label} {rg.text()}인데 실측값은 {fmt(v)}{unit}이에요."
            if len(cands) == 1:
                correction = {"spec_id": cands[0].id, "spec": cands[0].raw, "fee": cands[0].fee,
                              "message": msg + f" 실측 기준으로는 '{cands[0].raw}'({cands[0].fee:,}원)이 맞아요."}
            else:
                correction = {"spec_id": None, "message": msg + " 맞는 구간을 찾지 못했으니 관할 지자체에 확인해 주세요."}

    unit_fee = 0 if row.is_free else row.fee
    total = unit_fee * units * qty
    basis = [
        f"지역: {region['sido']} {region['sigungu']} (관리기관 {region['manager_org'] or '미기재'})",
        f"표준 품목: {std['name'] if std else '(표준 품목 미매핑)'} ← 지자체 품목명 '{local['raw_name']}'",
        f"적용 규격: {row.raw}",
        f"규격 결정 방식: {rule}",
    ]
    if row.spec_type == "per_unit":
        basis.append(f"계산: {row.fee:,}원 × {units}단위({fmt(row.per_unit_amount)}{row.per_unit_unit}당, 올림) × {qty}개")
        warnings.append("단위 미만 수량의 올림 처리 여부는 지자체마다 다를 수 있어요.")
    elif qty > 1:
        basis.append(f"계산: {unit_fee:,}원 × {qty}개")
    if row.is_free:
        basis.append("유무료여부: 무료")
    return {
        "status": "result",
        "result": {
            "region": {"sido": region["sido"], "sigungu": region["sigungu"], "manager_org": region["manager_org"]},
            "standard_item": std["name"] if std else None,
            "local_item": local["raw_name"],
            "spec": {"id": row.id, "raw": row.raw, "type": row.spec_type},
            "inputs": trail,
            "unit_fee": unit_fee, "units": units, "quantity": qty, "total_fee": total,
            "basis": basis,
            "source": _source_block(row, region),
            "warnings": warnings,
            "verify": verify,
            "correction": correction,
            # ②→③ 넘겨주는 값: 규격 확정 결과. 수수료 산정·근거 안내(③)는 이 값만 받으면 된다.
            "handoff": {
                "region_id": region["id"], "sido": region["sido"], "sigungu": region["sigungu"],
                "standard_code": standard_code, "standard_item": std["name"] if std else None,
                "local_item_id": local["id"], "local_item": local["raw_name"],
                "spec_id": row.id, "spec": row.raw,
                "units": units, "quantity": qty,
            },
        },
    }
