"""전체 원본 CSV(data/raw/ 의 표준데이터)가 있을 때만 도는 검증."""
import csv
from pathlib import Path

import pytest

from etl.build_db import NO_SPEC, SIDO_WIDE, ROOT, build, read_csv_any
from etl.normalize import nfkc

FULL = [p for p in [ROOT / "data" / "fees.csv"] if p.exists()]
pytestmark = pytest.mark.skipif(not FULL, reason="전체 원본 CSV 없음")


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    from spec_question.db import connect
    p = tmp_path_factory.mktemp("full") / "full.db"
    stats = build(p, FULL)
    return connect(p), stats


def test_all_rows_loaded(full):
    con, stats = full
    assert stats["rows_rejected"] == 0
    assert stats["rows_loaded"] + stats["exact_duplicates"] == stats["rows_in"]
    assert con.execute("SELECT COUNT(*) FROM region").fetchone()[0] >= 100


def test_every_row_fee_matches_source(full):
    """원본 모든 행을 엔진으로 재조회해 금액·기준일이 그대로 나오는지(충돌 행은 '확인 필요'로)."""
    from spec_question.engine import estimate
    con, _ = full
    rid = {(r["sido"], r["sigungu"]): r["id"] for r in con.execute("SELECT * FROM region")}
    seen = set()
    for path in FULL:
        for row in read_csv_any(path):
            key = tuple(row.get(k, "") for k in row)
            if key in seen:
                continue
            seen.add(key)
            sg = nfkc(row["시군구명"])
            sg = SIDO_WIDE if sg in ("없음", "-", "해당없음") else sg
            r_id = rid[(nfkc(row["시도명"]), sg)]
            li = con.execute("SELECT id FROM local_item WHERE region_id=? AND raw_name=?",
                             (r_id, nfkc(row["대형폐기물명"]))).fetchone()
            spec_txt = row["대형폐기물규격"].strip() or NO_SPEC
            specs = con.execute("""SELECT s.id, f.fee, s.per_unit_amount FROM item_specification s
                                   JOIN disposal_fee f ON f.spec_id=s.id WHERE s.local_item_id=? AND s.raw_spec=?""",
                                (li[0], spec_txt)).fetchall()
            fee = int(float(row["수수료"].replace(",", "")))
            sid, _, per = next(s for s in specs if s[1] == fee)
            res = estimate(con, r_id, None, li[0], {"spec": sid, "amount": per or 1})
            if len({s[1] for s in specs}) > 1:
                assert res["status"] == "needs_confirmation"
            else:
                assert res["status"] == "result", (row, res)
                expected = 0 if row["유무료여부"].strip() == "무료" else fee
                assert res["result"]["unit_fee"] == expected


def test_sejong_resolves_without_sigungu(full):
    from spec_question.juso import resolve_region
    con, _ = full
    assert resolve_region(con, "세종특별자치시", "")["sigungu"] == SIDO_WIDE


@pytest.mark.parametrize("sigungu,code", [("강남구", "SOFA"), ("고양시", "FRIDGE"), ("고양시", "TV")])
def test_pilot_regions_ask_questions(full, sigungu, code):
    from spec_question.engine import estimate
    con, _ = full
    rid = con.execute("SELECT id FROM region WHERE sigungu=?", (sigungu,)).fetchone()[0]
    r = estimate(con, rid, code)
    assert r["status"] == "question"
