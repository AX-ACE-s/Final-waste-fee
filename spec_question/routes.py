"""기능② 규격 질문·실측 보정 API (Flask Blueprint) + ①·③ 연결.

/api/spec/regions   지역 목록(시도별)
/api/address        행안부 주소검색 → 관할 지역
/api/spec/items     지역의 품목(표준 품목 + 원문 품목) 검색
/api/spec/parse     설명 문장 읽기(품목·치수·수량)
/api/spec/resolve   ①이 고른 지자체 품목명 → ②의 지역 품목·표준 품목
/api/spec/estimate  다음 질문 1개 또는 확정 결과(+ ③ 수수료·근거)
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from flask import Blueprint, jsonify, request

from etl.build_db import DEFAULT_DB, build
from etl.normalize import ItemMatcher, nfkc

from . import bridge, describe, juso
from .db import connect
from .engine import estimate

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_state: dict = {"con": None}
_matcher = ItemMatcher()


def ensure_db(force: bool = False, db_path: Path = DEFAULT_DB) -> None:
    """data/fees.csv 가 DB보다 새로우면(또는 DB가 없으면) 다시 만든다. ③의 API 자동 갱신 뒤에도 호출된다."""
    src = ROOT / "data" / "fees.csv"
    if not src.exists():
        src = ROOT / "data" / "fees_sample.csv"
    with _lock:
        stale = not db_path.exists() or src.stat().st_mtime > db_path.stat().st_mtime
        if force or stale:
            tmp = db_path.with_suffix(".building.db")
            build(tmp)
            tmp.replace(db_path)
            _state["con"] = None


def set_connection(con: sqlite3.Connection | None) -> None:  # 테스트용
    _state["con"] = con


def con() -> sqlite3.Connection:
    if _state["con"] is None:
        _state["con"] = connect(DEFAULT_DB)
    return _state["con"]


def create_blueprint(get_table: Callable) -> Blueprint:
    bp = Blueprint("spec_question", __name__)

    @bp.get("/api/spec/regions")
    def regions():
        out: dict[str, list] = {}
        for r in con().execute("SELECT id,sido,sigungu,manager_org FROM region ORDER BY sido,sigungu"):
            out.setdefault(r["sido"], []).append({"id": r["id"], "sigungu": r["sigungu"], "manager_org": r["manager_org"]})
        return jsonify([{"sido": k, "sigungu": v} for k, v in out.items()])

    @bp.get("/api/address")
    def address():
        q = request.args.get("q", "")
        try:
            rows = juso.search_address(q)
        except juso.JusoError as e:
            return jsonify({"detail": str(e)}), 503
        for row in rows:
            reg = juso.resolve_region(con(), row["sido"], row["sigungu"])
            row["region_id"] = reg["id"] if reg else None
            row["supported"] = bool(reg)
        return jsonify(rows)

    @bp.get("/api/spec/items")
    def items():
        region_id = request.args.get("region_id", type=int)
        q = request.args.get("q", "").strip()
        c = con()
        if not region_id or not c.execute("SELECT 1 FROM region WHERE id=?", (region_id,)).fetchone():
            return jsonify({"detail": "지원하지 않는 지역입니다."}), 404
        std = [dict(r) for r in c.execute(
            """SELECT s.code, s.name, s.category FROM standard_item s JOIN item_mapping m ON m.standard_item_id=s.id
               JOIN local_item li ON li.id=m.local_item_id WHERE li.region_id=?
               GROUP BY s.id ORDER BY s.category, s.name""", (region_id,))]
        unmapped = [dict(r) for r in c.execute(
            """SELECT li.id AS local_item_id, li.raw_name AS name, li.category_raw AS category FROM local_item li
               WHERE li.region_id=? AND li.id NOT IN (SELECT local_item_id FROM item_mapping) ORDER BY li.raw_name""",
            (region_id,))]
        if q:
            codes = set(_matcher.search(q))
            nq = q.replace(" ", "")
            std = [s for s in std if s["code"] in codes or nq in s["name"].replace(" ", "")]
            unmapped = [u for u in unmapped if nq in u["name"].replace(" ", "")]
            if not std and not unmapped:
                return jsonify({"detail": f"'{q}'에 해당하는 품목이 이 지역 수수료표에 없어요. 다른 이름으로 검색하거나 목록에서 골라 주세요."}), 404
        return jsonify({"standard": std, "local_only": unmapped})

    @bp.get("/api/spec/parse")
    def parse():
        text = request.args.get("text", "")
        region_id = request.args.get("region_id", type=int)
        d = describe.read(text)
        items = d["items"]
        if region_id:
            have = {r[0] for r in con().execute(
                """SELECT DISTINCT s.code FROM standard_item s JOIN item_mapping m ON m.standard_item_id=s.id
                   JOIN local_item li ON li.id=m.local_item_id WHERE li.region_id=?""", (region_id,))}
            items = [c for c in items if c in have]
        return jsonify({"items": items, "hints": d["hints"], "quantity": d["quantity"], "labels": d["labels"]})

    @bp.get("/api/spec/resolve")
    def resolve():
        """① 사진 인식(recognition/)이 고른 품목은 수수료표 원문 품목명이다. ②가 질문할 수 있게 지역 품목 ID로 바꾼다."""
        region_id = request.args.get("region_id", type=int)
        name = nfkc(request.args.get("item", "").strip())
        c = con()
        li = c.execute("SELECT id, raw_name FROM local_item WHERE region_id=? AND raw_name=?", (region_id, name)).fetchone()
        if not li:  # 띄어쓰기만 다른 경우
            li = next((r for r in c.execute("SELECT id, raw_name FROM local_item WHERE region_id=?", (region_id,))
                       if r["raw_name"].replace(" ", "") == name.replace(" ", "")), None)
        if not li:
            return jsonify({"detail": f"'{name}'은(는) 이 지역 수수료표에 없는 품목이에요."}), 404
        std = c.execute("""SELECT s.code, s.name FROM item_mapping m JOIN standard_item s ON s.id=m.standard_item_id
                           WHERE m.local_item_id=?""", (li["id"],)).fetchone()
        return jsonify({"local_item_id": li["id"], "local_name": li["raw_name"],
                        "standard_code": std["code"] if std else None, "standard_name": std["name"] if std else None})

    @bp.post("/api/spec/estimate")
    def post_estimate():
        body = request.get_json(silent=True) or {}
        answers = body.get("answers") or {}
        res = estimate(con(), body.get("region_id"), body.get("standard_code"), body.get("local_item_id"), answers)
        # ②가 규격을 확정했으면 ③(수수료 산정·근거 안내)으로 넘긴다
        hand = None
        if res.get("status") == "result":
            hand = res["result"]["handoff"]
        elif res.get("status") == "needs_confirmation" and len({c["spec"] for c in res["candidates"]}) == 1:
            # 같은 규격 문구에 금액이 여러 개(원본 충돌) → ③이 후보 금액·설명을 보여 준다
            c0 = res["candidates"][0]
            row = con().execute("SELECT li.region_id, li.raw_name FROM item_specification s JOIN local_item li ON li.id=s.local_item_id WHERE s.id=?",
                                (c0["spec_id"],)).fetchone()
            hand = {"region_id": row["region_id"], "local_item": row["raw_name"], "spec": c0["spec"],
                    "quantity": answers.get("quantity") or 1}
        if hand:
            merged = {**describe.read(answers.get("description") or "")["hints"], **(answers.get("measure") or {})}
            fd = bridge.to_fee(get_table(), con(), hand, bridge.measure_by_unit(res, merged), answers.get("amount"))
            if fd and res.get("status") == "result":
                # ③의 설명 문장에 ②가 규격을 정한 방식(실측·설명 읽기·직접 선택)을 반영한다
                rule = next((b.split(": ", 1)[1] for b in res["result"]["basis"] if b.startswith("규격 결정 방식")), "")
                if rule and fd["basis"]["decided_by"] == "사용자 선택":
                    fd["basis"]["decided_by"] = rule
                    fd["explanation"] = fd["explanation"].replace("선택하신 규격입니다", rule)
                    fd["copy_text"] = fd["copy_text"].replace("(사용자 선택)", f"({rule})")
            res["fee_detail"] = fd
        return jsonify(res)

    return bp
