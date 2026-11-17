"""기능 연결부: ① 사진 인식 → ② 규격 질문 → ③ 수수료 산정·근거 안내.

- ②(이 패키지)는 SQLite(data/processed/fees.db)에 정리한 지역·품목·규격으로 질문하고 규격을 확정한다.
- ③(core/fees.py FeeTable)은 같은 원본(data/fees.csv)을 메모리에 올려 금액·근거·비교·조례 링크를 만든다.
두 모듈은 같은 원본 파일을 읽으므로, 여기서는 이름만 맞춰 넘긴다(지역 ID, 원문 품목명, 원문 규격).
"""
from __future__ import annotations

from etl.build_db import NO_SPEC, SIDO_WIDE
from etl.normalize import nfkc

# ② 실측 단위 -> ③(core/specs.py KIND_UNIT) 단위
UNIT_TO_KIND = {"cm": "length", "㎡": "area", "L": "volume", "kg": "weight", "인치": "inch", "인": "seats"}


def fee_region_id(region) -> str:
    """② region 행 -> ③ region_id('시도 시군구'). 세종처럼 시군구가 없는 곳은 원본 표기('없음')로 되돌린다."""
    sigungu = "없음" if region["sigungu"] == SIDO_WIDE else region["sigungu"]
    return f"{region['sido']} {sigungu}".strip()


def fee_item_name(table, region_id: str, local_raw: str) -> str | None:
    """② 지자체 품목명(NFKC 정규화) -> ③ 원문 품목명."""
    try:
        names = table.items(region_id)
    except Exception:
        return None
    if local_raw in names:
        return local_raw
    return next((n for n in names if nfkc(n) == local_raw), None)


def fee_spec_name(raw_spec: str) -> str:
    return "규격 구분 없음" if raw_spec == NO_SPEC else raw_spec


def to_fee(table, con, handoff: dict, measure: dict | None = None, amount: float | None = None) -> dict | None:
    """②가 확정한 규격을 ③ FeeTable.calculate 로 넘겨 금액·근거를 받는다. 실패하면 None (②의 자체 결과로 표시)."""
    from core.fees import FeeError
    from core.specs import parse_per_unit, parse_range

    region = con.execute("SELECT * FROM region WHERE id=?", (handoff["region_id"],)).fetchone()
    rid = fee_region_id(region)
    item = fee_item_name(table, rid, handoff["local_item"])
    if not item:
        return None
    spec = fee_spec_name(handoff["spec"])
    value = None
    if parse_per_unit(spec):           # 단가형(1㎡당 등): 크기를 넘긴다
        value = amount
    else:                              # 구간형: 같은 기준의 실측값이 있으면 넘겨 '경계값 주의'를 받는다
        r = parse_range(spec)
        if r and measure:
            for dim_unit, v in measure.items():
                if UNIT_TO_KIND.get(dim_unit) == r["kind"]:
                    value = float(v)
                    break
    try:
        res = table.calculate(rid, item, spec=spec, measure=value)
    except FeeError:
        try:
            res = table.calculate(rid, item, spec=spec)
        except FeeError:
            return None
    qty = int(handoff.get("quantity") or 1)
    res["quantity"] = qty
    res["total_fee"] = None if res["fee"] is None else res["fee"] * qty
    res["total_text"] = ("금액 확인 필요" if res["fee"] is None
                         else "무료 (0원)" if res["total_fee"] == 0 else f"{res['total_fee']:,}원")
    return res


def measure_by_unit(engine_result: dict, measure: dict) -> dict:
    """②의 {dim: 값} -> {단위: 값} (③은 단위 기준으로 규격 종류를 판단한다)."""
    from etl.normalize import DIM_LABELS
    out = {}
    for dim, v in (measure or {}).items():
        unit = DIM_LABELS.get(dim, ("", ""))[1]
        if unit and v not in (None, ""):
            out.setdefault(unit, v)
    return out
