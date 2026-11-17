"""공공데이터 CSV -> 정제 -> 표준화 -> SQLite 적재.

사용법:
    python -m etl.build_db                 # data/raw/*.csv, data/manual/*.csv 전부 적재
    python -m etl.build_db --raw path.csv  # 특정 파일만

입력 파일은 공공데이터포털 '전국대형폐기물수거수수료정보표준데이터'(15114146) 원본 CSV
컬럼(시도명,시군구명,대형폐기물명,대형폐기물구분명,대형폐기물규격,유무료여부,수수료,관리기관명,데이터기준일자)을
그대로 사용한다. 조례로 보완한 수동 데이터는 data/manual/ 에 같은 컬럼 + 출처URL,조례명,확인일자 로 둔다.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from etl.normalize import ItemMatcher, nfkc, normalize_name, parse_spec

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "processed" / "fees.db"
REQUIRED = ["시도명", "시군구명", "대형폐기물명", "대형폐기물구분명", "대형폐기물규격", "유무료여부", "수수료", "관리기관명", "데이터기준일자"]
CORE_REQUIRED = ["시도명", "시군구명", "대형폐기물명", "수수료"]
# 포털 CSV(한글) / 공공데이터포털 오픈API(영문 태그, core/api_client.py 가 저장) 둘 다 읽는다 — 기능③ FeeTable 과 같은 규칙
COLUMN_ALIASES = {
    "시도명": ["시도명", "ctpvNm"], "시군구명": ["시군구명", "sggNm"], "대형폐기물명": ["대형폐기물명", "larWasNm", "품목명"],
    "대형폐기물구분명": ["대형폐기물구분명", "larWasSeNm"], "대형폐기물규격": ["대형폐기물규격", "larWasSpcfct", "규격"],
    "유무료여부": ["유무료여부", "paidFreeYn"], "수수료": ["수수료", "fee", "수수료(원)"],
    "관리기관명": ["관리기관명", "mngInstNm", "제공기관명"], "데이터기준일자": ["데이터기준일자", "crtrYmd", "기준일자"],
}
DATASET_URL = "https://www.data.go.kr/data/15114146/standard.do"
SIDO_WIDE = "(시 전체)"
NO_SPEC = "(규격 미기재)"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE data_source (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,              -- standard_data | standard_data_preview | manual_ordinance
  name TEXT NOT NULL,
  url TEXT,
  file_name TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  row_count INTEGER,
  note TEXT
);
CREATE TABLE region (
  id INTEGER PRIMARY KEY,
  sido TEXT NOT NULL,
  sigungu TEXT NOT NULL,
  manager_org TEXT,
  UNIQUE (sido, sigungu)
);
CREATE TABLE standard_item (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category TEXT NOT NULL
);
CREATE TABLE local_item (
  id INTEGER PRIMARY KEY,
  region_id INTEGER NOT NULL REFERENCES region(id),
  raw_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  category_raw TEXT,
  UNIQUE (region_id, raw_name)
);
CREATE TABLE item_mapping (
  local_item_id INTEGER NOT NULL REFERENCES local_item(id),
  standard_item_id INTEGER NOT NULL REFERENCES standard_item(id),
  method TEXT NOT NULL,           -- exact | synonym | typo | split
  PRIMARY KEY (local_item_id, standard_item_id)
);
CREATE TABLE item_specification (
  id INTEGER PRIMARY KEY,
  local_item_id INTEGER NOT NULL REFERENCES local_item(id),
  raw_spec TEXT NOT NULL,
  spec_type TEXT NOT NULL,        -- all | range | categorical | per_unit
  qualifier TEXT,
  ranges_json TEXT NOT NULL,      -- [{dim,unit,min,min_inc,max,max_inc}]
  per_unit_amount REAL,
  per_unit_unit TEXT,
  per_unit_dim TEXT,
  anomalies_json TEXT
);
CREATE TABLE disposal_fee (
  id INTEGER PRIMARY KEY,
  spec_id INTEGER NOT NULL REFERENCES item_specification(id),
  fee INTEGER NOT NULL,
  is_free INTEGER NOT NULL,
  base_date TEXT,
  source_id INTEGER NOT NULL REFERENCES data_source(id),
  source_row INTEGER,
  ordinance_name TEXT,
  ordinance_url TEXT
);
CREATE TABLE data_quality_log (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES data_source(id),
  row_no INTEGER,
  level TEXT NOT NULL,            -- error(적재 제외) | warn(적재, 표시)
  issue TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX idx_local_item_region ON local_item(region_id);
CREATE INDEX idx_spec_local ON item_specification(local_item_id);
CREATE INDEX idx_fee_spec ON disposal_fee(spec_id);
"""


def read_csv_any(path: Path) -> list[dict]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"인코딩을 판별할 수 없습니다: {path}")
    out = []
    for raw in csv.DictReader(io.StringIO(text)):
        row = {}
        for k, names in COLUMN_ALIASES.items():
            row[k] = next((raw[n] for n in names if raw.get(n) not in (None, "")), "")
        for k, val in raw.items():  # 조례명·출처URL 등 추가 컬럼은 그대로 둔다
            row.setdefault(k, val)
        out.append(row)
    return out


def source_kind(path: Path) -> tuple[str, str]:
    if "manual" in path.parts:
        return "manual_ordinance", "자치법규(조례) 확인 수동 보완 데이터"
    if path.name == "fees_sample.csv":
        return "demo_sample", "시연용 샘플 데이터(가상 지자체)"
    if path.name.startswith("sample_preview"):
        return "standard_data_preview", "전국대형폐기물수거수수료정보표준데이터 (포털 미리보기 발췌)"
    return "standard_data", "전국대형폐기물수거수수료정보표준데이터"


def build(db_path: Path = DEFAULT_DB, files: list[Path] | None = None) -> dict:
    if files is None:
        # 기능③과 같은 원본 파일을 쓴다: data/fees.csv (없으면 시연용 data/fees_sample.csv)
        main = ROOT / "data" / "fees.csv"
        files = [main if main.exists() else ROOT / "data" / "fees_sample.csv"]
        files += sorted((ROOT / "data" / "manual").glob("*.csv"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    matcher = ItemMatcher()

    for it in matcher.items.values():
        con.execute("INSERT INTO standard_item(code,name,category) VALUES (?,?,?)", (it["code"], it["name"], it["category"]))
    std_id = {r[0]: r[1] for r in con.execute("SELECT code,id FROM standard_item")}

    stats = {"files": [], "rows_in": 0, "rows_loaded": 0, "rows_rejected": 0, "exact_duplicates": 0}
    seen_exact: set[tuple] = set()

    for path in files:
        rows = read_csv_any(path)
        kind, name = source_kind(path)
        missing = [c for c in CORE_REQUIRED if rows and not any(r.get(c) for r in rows[:50])]
        if not rows or missing:
            raise ValueError(f"{path.name}: 필수 컬럼 누락 {missing}. 표준데이터 원본 CSV인지 확인하세요.")
        cur = con.execute(
            "INSERT INTO data_source(kind,name,url,file_name,ingested_at,row_count) VALUES (?,?,?,?,?,?)",
            (kind, name, DATASET_URL if kind != "manual_ordinance" else None, path.name,
             datetime.now().isoformat(timespec="seconds"), len(rows)))
        sid = cur.lastrowid
        stats["files"].append({"file": path.name, "kind": kind, "rows": len(rows)})

        def log(row_no, level, issue, detail=""):
            con.execute("INSERT INTO data_quality_log(source_id,row_no,level,issue,detail) VALUES (?,?,?,?,?)",
                        (sid, row_no, level, issue, detail))

        for i, r in enumerate(rows, start=2):  # 헤더가 1행
            stats["rows_in"] += 1
            v = {k: nfkc(r.get(k) or "") for k in REQUIRED}
            empty = [k for k in ("시도명", "시군구명", "대형폐기물명", "수수료") if not v[k]]
            if empty:
                log(i, "error", "필수값 결측", ",".join(empty)); stats["rows_rejected"] += 1; continue
            fee_txt = v["수수료"].replace(",", "").replace("원", "")
            try:
                fee = int(float(fee_txt))
            except ValueError:
                log(i, "error", "수수료 숫자 아님", v["수수료"]); stats["rows_rejected"] += 1; continue
            if fee < 0:
                log(i, "error", "음수 수수료", v["수수료"]); stats["rows_rejected"] += 1; continue
            for k in ("대형폐기물구분명", "대형폐기물규격", "유무료여부", "관리기관명", "데이터기준일자"):
                if not v[k]:
                    log(i, "warn", "선택값 결측", k)
            key = tuple(v[k] for k in REQUIRED)
            if key in seen_exact:
                log(i, "warn", "완전 중복 행 제외", f"{v['시군구명']} {v['대형폐기물명']} {v['대형폐기물규격']}")
                stats["exact_duplicates"] += 1; continue
            seen_exact.add(key)

            if v["시군구명"] in ("없음", "-", "해당없음"):  # 세종특별자치시처럼 시군구가 없는 광역단체
                v["시군구명"] = SIDO_WIDE
            con.execute("INSERT OR IGNORE INTO region(sido,sigungu,manager_org) VALUES (?,?,?)",
                        (v["시도명"], v["시군구명"], v["관리기관명"] or None))
            region_id = con.execute("SELECT id FROM region WHERE sido=? AND sigungu=?", (v["시도명"], v["시군구명"])).fetchone()[0]

            li = con.execute("SELECT id FROM local_item WHERE region_id=? AND raw_name=?", (region_id, v["대형폐기물명"])).fetchone()
            if li:
                local_id = li[0]
            else:
                local_id = con.execute(
                    "INSERT INTO local_item(region_id,raw_name,normalized_name,category_raw) VALUES (?,?,?,?)",
                    (region_id, v["대형폐기물명"], normalize_name(v["대형폐기물명"], matcher.typos), v["대형폐기물구분명"] or None)).lastrowid
                m = matcher.match(v["대형폐기물명"])
                for code in m.codes:
                    con.execute("INSERT INTO item_mapping VALUES (?,?,?)", (local_id, std_id[code], m.method))

            p = parse_spec(r.get("대형폐기물규격") or "")
            for a in p.anomalies:
                log(i, "warn", "규격 이상치", a)
            spec_id = con.execute(
                """INSERT INTO item_specification(local_item_id,raw_spec,spec_type,qualifier,ranges_json,
                   per_unit_amount,per_unit_unit,per_unit_dim,anomalies_json) VALUES (?,?,?,?,?,?,?,?,?)""",
                (local_id, (r.get("대형폐기물규격") or "").strip() or NO_SPEC, p.spec_type, p.qualifier,
                 json.dumps([r.__dict__ for r in p.ranges], ensure_ascii=False),
                 p.per_unit_amount, p.per_unit_unit, p.per_unit_dim, json.dumps(p.anomalies, ensure_ascii=False))).lastrowid
            con.execute(
                "INSERT INTO disposal_fee(spec_id,fee,is_free,base_date,source_id,source_row,ordinance_name,ordinance_url) VALUES (?,?,?,?,?,?,?,?)",
                (spec_id, fee, 1 if v["유무료여부"] == "무료" else 0, v["데이터기준일자"] or None, sid, i,
                 nfkc(r.get("조례명") or "") or None, nfkc(r.get("출처URL") or "") or None))
            stats["rows_loaded"] += 1

    # 같은 지역·품목·규격 문구인데 수수료가 다른 '충돌 중복' 기록
    for row in con.execute("""
        SELECT rg.sido || ' ' || rg.sigungu, li.raw_name, s.raw_spec, GROUP_CONCAT(f.fee), COUNT(*)
        FROM item_specification s JOIN local_item li ON li.id=s.local_item_id JOIN region rg ON rg.id=li.region_id
        JOIN disposal_fee f ON f.spec_id=s.id
        GROUP BY li.id, s.raw_spec HAVING COUNT(DISTINCT f.fee) > 1""").fetchall():
        con.execute("INSERT INTO data_quality_log(source_id,row_no,level,issue,detail) VALUES (NULL,NULL,'warn','규격 동일·수수료 상이(충돌)',?)",
                    (f"{row[0]} {row[1]} [{row[2]}] 수수료={row[3]}",))
    con.commit()
    con.close()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", nargs="*", type=Path)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    a = ap.parse_args()
    print(json.dumps(build(a.db, a.raw), ensure_ascii=False, indent=2))
