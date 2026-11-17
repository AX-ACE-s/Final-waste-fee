"""데이터 분석 리포트 생성: reports/analysis.md + reports/*.csv

    python -m etl.analyze
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict

from spec_question.db import connect
from etl.build_db import DEFAULT_DB, REQUIRED, ROOT, read_csv_any
from etl.normalize import DIM_LABELS

OUT = ROOT / "reports"
CORE = ["SOFA", "MATTRESS", "BED_FRAME", "BED", "WARDROBE", "CLOSET", "DRAWER", "SHOE_CABINET", "DESK", "CHAIR",
        "DINING_TABLE", "BOOKCASE", "DISPLAY_CABINET", "VANITY", "TV", "FRIDGE", "WASHER", "AIRCON", "ELEC_MAT",
        "PIANO", "BICYCLE", "STROLLER"]


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def pct(a, b):
    return f"{(a / b * 100):.1f}%" if b else "-"


def main(db=DEFAULT_DB):
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.csv"):
        old.unlink()
    con = connect(db)
    md = ["# 데이터 분석 리포트 — 지역 기준 규격 질문·실측 보정", ""]
    srcs = con.execute("SELECT * FROM data_source").fetchall()
    regions = con.execute("SELECT * FROM region ORDER BY sido, sigungu").fetchall()
    rname = {r["id"]: f"{r['sido']} {r['sigungu']}" for r in regions}
    md += ["## 0. 분석 대상", ""]
    for s in srcs:
        md.append(f"- `{s['file_name']}` — {s['name']}, {s['row_count']:,}행 (적재 {s['ingested_at']})")
    sidos = Counter(r["sido"] for r in regions)
    md.append(f"- 지자체 {len(regions)}곳 / 시·도 {len(sidos)}곳")
    bd = [r[0] for r in con.execute("SELECT base_date FROM disposal_fee WHERE base_date IS NOT NULL")]
    md.append(f"- 데이터기준일자 범위: {min(bd)} ~ {max(bd)} (지자체마다 갱신 시점이 다름)")
    md.append("")

    # 1. 결측률
    raw_rows = []
    for s in srcs:
        p = next((ROOT / "data").rglob(s["file_name"]), None)
        if p:
            raw_rows += read_csv_any(p)
    cols = list(raw_rows[0].keys()) if raw_rows else REQUIRED
    md += ["## 1. 컬럼별 결측률", "", "| 컬럼 | 결측 행 | 결측률 |", "|---|---|---|"]
    miss = []
    for c in cols:
        n = sum(1 for r in raw_rows if not (r.get(c) or "").strip())
        md.append(f"| {c} | {n:,} | {pct(n, len(raw_rows))} |")
        miss.append([c, n, len(raw_rows)])
    write_csv("missing_rate.csv", ["컬럼", "결측행", "전체행"], miss)
    dup = con.execute("SELECT COUNT(*) FROM data_quality_log WHERE issue='완전 중복 행 제외'").fetchone()[0]
    md += ["", f"- 완전히 같은 행(9개 컬럼 모두 동일) {dup}건은 중복으로 제외했다.",
           "- 규격이 빈 행은 '모든 규격'으로 단정하지 않고 `(규격 미기재)`로 표시한다.", ""]

    # 2. 품목명 표준화
    li = {r["id"]: r for r in con.execute("SELECT * FROM local_item")}
    maps = con.execute("""SELECT m.local_item_id, m.method, s.code, s.name FROM item_mapping m
                          JOIN standard_item s ON s.id=m.standard_item_id""").fetchall()
    mapped = {m["local_item_id"] for m in maps}
    by_method = Counter()
    for lid in mapped:
        by_method[next(m["method"] for m in maps if m["local_item_id"] == lid)] += 1
    names_for_std = defaultdict(set)
    for m in maps:
        names_for_std[m["name"]].add(li[m["local_item_id"]]["raw_name"])
    distinct_raw = {r["raw_name"] for r in li.values()}
    distinct_norm = {r["normalized_name"] for r in li.values()}
    md += ["## 2. 품목명 표준화 전후 비교", "",
           f"- 지자체 품목 레코드(지역×품목명): {len(li):,}개",
           f"- 전국 고유 품목명: 원문 {len(distinct_raw):,}개 → 정규화(공백·괄호·오탈자 제거) 후 {len(distinct_norm):,}개",
           f"- 매핑된 지자체 품목 {len(mapped):,}개가 표준 품목 {len({m['code'] for m in maps})}개로 통합",
           "", "같은 물건을 지역마다 다르게 부르는 예 (원문 표기 수 상위 15):", "",
           "| 표준 품목 | 원문 표기 수 | 원문 표기 예 |", "|---|---|---|"]
    rows = sorted(names_for_std.items(), key=lambda x: -len(x[1]))
    for std, names in rows[:15]:
        ex = " / ".join(sorted(names, key=len)[:8])
        md.append(f"| {std} | {len(names)} | {ex} |")
    write_csv("name_standardization.csv", ["표준품목", "원문표기수", "원문표기"],
              [[s, len(n), " / ".join(sorted(n))] for s, n in rows])
    md.append("")

    # 3. 매핑 성공률
    per_sido = defaultdict(lambda: [0, 0])
    per_region = defaultdict(lambda: [0, 0])
    for r in li.values():
        sido = rname[r["region_id"]].split()[0]
        per_sido[sido][0] += 1
        per_sido[sido][1] += r["id"] in mapped
        per_region[r["region_id"]][0] += 1
        per_region[r["region_id"]][1] += r["id"] in mapped
    md += ["## 3. 매핑 성공률", "", f"- 전체: {len(mapped):,} / {len(li):,} = **{pct(len(mapped), len(li))}**",
           "- 방식별: " + ", ".join(f"{k} {v:,}" for k, v in by_method.most_common()), "",
           "| 시·도 | 지자체 품목 | 매핑 | 성공률 |", "|---|---|---|---|"]
    for k, (t, m) in sorted(per_sido.items(), key=lambda x: -x[1][1] / x[1][0]):
        md.append(f"| {k} | {t:,} | {m:,} | {pct(m, t)} |")
    write_csv("mapping_rate_by_region.csv", ["지역", "지자체품목", "매핑", "성공률"],
              [[rname[k], t, m, round(m / t * 100, 1)] for k, (t, m) in per_region.items()])
    unm = Counter(r["normalized_name"] for r in li.values() if r["id"] not in mapped)
    write_csv("unmapped_items.csv", ["정규화명", "등장지역수"], unm.most_common())
    md += ["", "미매핑 상위(다음에 표준 사전에 넣을 후보): " + ", ".join(f"{k}({v})" for k, v in unm.most_common(15)),
           "", "> 표준 품목 사전은 1차 47종 → 전국 데이터의 미매핑 상위 품목을 보고 97종으로 확장했다. "
               "남은 미매핑 품목은 '그 밖의 우리 지역 품목'으로 원문 그대로 선택할 수 있다.", ""]

    # 4. 지역별 동일 품목 수수료 차이
    fee_rows = con.execute("""SELECT si.code, si.name, li.region_id, f.fee FROM standard_item si
        JOIN item_mapping m ON m.standard_item_id=si.id JOIN local_item li ON li.id=m.local_item_id
        JOIN item_specification s ON s.local_item_id=li.id JOIN disposal_fee f ON f.spec_id=s.id
        WHERE f.is_free=0 AND f.fee>0""").fetchall()
    agg = defaultdict(lambda: defaultdict(list))
    names = {}
    for r in fee_rows:
        agg[r["code"]][r["region_id"]].append(r["fee"])
        names[r["code"]] = r["name"]
    md += ["## 4. 지역별 동일 품목 수수료 차이", "",
           "규격 구간이 지역마다 달라 같은 규격끼리 맞대기 어렵기 때문에, 지역별 **최저 요금(가장 작은 규격)**과 **최고 요금(가장 큰 규격)**의 분포를 비교한다. 무료 품목 제외.", "",
           "| 표준 품목 | 지역 수 | 최저 요금 중앙값 | 최저 요금 범위 | 최고 요금 중앙값 | 최고 요금 범위 |", "|---|---|---|---|---|---|"]
    comp = []
    for code, regs in sorted(agg.items(), key=lambda x: -len(x[1])):
        mins = [min(v) for v in regs.values()]
        maxs = [max(v) for v in regs.values()]
        comp.append([names[code], len(regs), statistics.median(mins), min(mins), max(mins),
                     statistics.median(maxs), min(maxs), max(maxs)])
    for c in comp[:25]:
        md.append(f"| {c[0]} | {c[1]} | {c[2]:,.0f}원 | {c[3]:,}~{c[4]:,}원 | {c[5]:,.0f}원 | {c[6]:,}~{c[7]:,}원 |")
    write_csv("regional_fee_comparison.csv",
              ["표준품목", "지역수", "최저요금_중앙값", "최저요금_최소", "최저요금_최대", "최고요금_중앙값", "최고요금_최소", "최고요금_최대"], comp)
    write_csv("regional_fee_detail.csv", ["표준품목", "지역", "최저요금", "최고요금", "규격수"],
              [[names[c], rname[r], min(v), max(v), len(v)] for c, regs in agg.items() for r, v in regs.items()])

    from spec_question.engine import estimate
    md += ["", "같은 실측값을 넣었을 때 시범 후보 지역의 엔진 계산 결과:", "",
           "| 입력 | " + " | ".join(PILOTS) + " |", "|---|" + "---|" * len(PILOTS)]
    rid = {r["sigungu"]: r["id"] for r in regions if r["sigungu"] in PILOTS}
    for code, ans, label in [("FRIDGE", {"measure": {"volume": 450}}, "냉장고 450L"),
                             ("TV", {"measure": {"inch": 55}}, "TV 55인치"),
                             ("WASHER", {"measure": {"weight": 12}}, "세탁기 12kg"),
                             ("DRAWER", {"measure": {"tiers": 5}}, "서랍장 5단"),
                             ("SOFA", {"measure": {"seats": 3}, "group": "__measure__"}, "소파 3인용")]:
        cells = []
        for g in PILOTS:
            if g not in rid:
                cells.append("-"); continue
            r = estimate(con, rid[g], code, answers=ans)
            if r["status"] == "result":
                cells.append(f"{r['result']['unit_fee']:,}원<br><small>{r['result']['spec']['raw']}</small>")
            elif r["status"] == "question":
                cells.append(f"추가 질문({r['question']['id']})")
            else:
                cells.append(r["status"])
        md.append(f"| {label} | " + " | ".join(cells) + " |")
    md.append("")

    # 5. 지역별 규격 항목 차이
    dims = con.execute("""SELECT si.code, si.name, li.region_id, s.ranges_json, s.spec_type FROM standard_item si
        JOIN item_mapping m ON m.standard_item_id=si.id JOIN local_item li ON li.id=m.local_item_id
        JOIN item_specification s ON s.local_item_id=li.id""").fetchall()
    reg_dims = defaultdict(lambda: defaultdict(set))
    for r in dims:
        ds = {DIM_LABELS[x["dim"]][0] for x in json.loads(r["ranges_json"])}
        if r["spec_type"] == "per_unit":
            ds.add("단위당 요금")
        if not ds and r["spec_type"] == "categorical":
            ds.add("종류·재질(선택형)")
        if not ds and r["spec_type"] == "all":
            ds.add("구분 없음")
        reg_dims[r["code"]][r["region_id"]] |= ds
    md += ["## 5. 지역별 규격 항목(질문 항목) 차이", "",
           "같은 품목이라도 지자체마다 요금을 나누는 기준이 다르다. 그래서 질문을 고정하지 않고 지역 데이터에서 매번 만든다.", "",
           "| 표준 품목 | 지역 수 | 지역들이 쓰는 기준 (해당 지역 수) |", "|---|---|---|"]
    drows = []
    for code in sorted(reg_dims, key=lambda c: -len(reg_dims[c])):
        cnt = Counter(d for ds in reg_dims[code].values() for d in ds)
        if code in CORE:
            md.append(f"| {names.get(code, code)} | {len(reg_dims[code])} | " + ", ".join(f"{k} {v}" for k, v in cnt.most_common(5)) + " |")
        for r, ds in reg_dims[code].items():
            drows.append([names.get(code, code), rname[r], "|".join(sorted(ds))])
    write_csv("spec_dimension_by_region.csv", ["표준품목", "지역", "규격기준"], drows)

    # 6. 파싱 · 품질
    st = con.execute("SELECT spec_type, COUNT(*) c FROM item_specification GROUP BY 1 ORDER BY 2 DESC").fetchall()
    total = sum(r["c"] for r in st)
    meaning = {"range": "수치 구간 → 실측값 자동 매칭", "categorical": "종류·재질 등 → 공식 규격 선택",
               "all": "모든 규격 동일 또는 규격 미기재 → 질문 없음", "per_unit": "단위당 요금 → 수량 입력"}
    md += ["", "## 6. 규격 파싱 결과와 데이터 품질", "", "| 규격 유형 | 행 | 비율 | 화면 처리 |", "|---|---|---|---|"]
    for r in st:
        md.append(f"| {r['spec_type']} | {r['c']:,} | {pct(r['c'], total)} | {meaning.get(r['spec_type'], '')} |")
    q = con.execute("SELECT level, issue, COUNT(*) n FROM data_quality_log GROUP BY 1,2 ORDER BY 3 DESC").fetchall()
    md += ["", "| 품질 이슈 | 건수 | 처리 |", "|---|---|---|"]
    how = {"선택값 결측": "적재, 화면에 '미기재' 표시", "규격 동일·수수료 상이(충돌)": "금액 단정 안 함 → '지자체 확인 필요'",
           "완전 중복 행 제외": "1건만 적재", "규격 이상치": "적재, 결과에 오기 의심 경고"}
    for r in q:
        md.append(f"| {r['issue']} | {r['n']:,} | {how.get(r['issue'], '')} |")
    conf = [r[0] for r in con.execute("SELECT detail FROM data_quality_log WHERE issue LIKE '%충돌%'")]
    conf_reg = Counter(" ".join(d.split()[:2]) for d in conf)
    md += ["", "충돌이 많은 지역: " + ", ".join(f"{k} {v}건" for k, v in conf_reg.most_common(8)),
           "", "충돌 예시: " + "; ".join(conf[:5])]
    write_csv("quality_log.csv", ["level", "issue", "detail"],
              [[r[0], r[1], r[2]] for r in con.execute("SELECT level, issue, detail FROM data_quality_log")])
    cat_diff = con.execute("""SELECT si.name, COUNT(DISTINCT li.category_raw) k FROM standard_item si
        JOIN item_mapping m ON m.standard_item_id=si.id JOIN local_item li ON li.id=m.local_item_id
        GROUP BY si.id HAVING k > 1""").fetchall()
    md += ["", f"- 같은 표준 품목인데 지역마다 '대형폐기물구분명'(가구류/가전제품류/기타)이 다른 품목: {len(cat_diff)}개 "
               f"(예: {', '.join(r['name'] for r in cat_diff[:8])}). 구분명만으로 품목을 분류하면 안 된다는 근거.", ""]

    # 7. 시범 지역 추천
    md += ["## 7. MVP 시범 지자체 후보", "",
           "대표 품목 22종 보유 수, 수치 구간 비율(실측 보정이 잘 되는 정도), 매핑률, 충돌 0건, 최신 기준일을 함께 본다.", "",
           "| 지자체 | 행 | 대표 품목 보유 | 수치 구간 비율 | 매핑률 | 충돌 | 최신 기준일 |", "|---|---|---|---|---|---|---|"]
    score = []
    for r in regions:
        n = con.execute("""SELECT COUNT(*), AVG(s.spec_type='range'), MAX(f.base_date) FROM local_item li
            JOIN item_specification s ON s.local_item_id=li.id JOIN disposal_fee f ON f.spec_id=s.id
            WHERE li.region_id=?""", (r["id"],)).fetchone()
        core = con.execute(f"""SELECT COUNT(DISTINCT si.code) FROM local_item li JOIN item_mapping m ON m.local_item_id=li.id
            JOIN standard_item si ON si.id=m.standard_item_id WHERE li.region_id=? AND si.code IN ({','.join('?' * len(CORE))})""",
                           (r["id"], *CORE)).fetchone()[0]
        nconf = conf_reg.get(f"{r['sido']} {r['sigungu']}", 0)
        t, m = per_region[r["id"]]
        score.append([rname[r["id"]], n[0], core, round((n[1] or 0) * 100), round(m / t * 100) if t else 0, nconf, n[2]])
    score.sort(key=lambda x: (-x[2], x[5], -x[3]))
    for s in score[:10]:
        md.append(f"| {s[0]} | {s[1]} | {s[2]}/22 | {s[3]}% | {s[4]}% | {s[5]} | {s[6]} |")
    write_csv("region_scorecard.csv", ["지자체", "행", "대표품목보유", "수치구간비율", "매핑률", "충돌", "최신기준일"], score)

    md += ["", "## 8. 한계", "",
           "- 규격 문구가 자유 텍스트라 정규식 규칙으로 해석한다. 해석 못 한 문구는 숫자로 바꾸지 않고 선택형으로 남긴다.",
           "- 같은 규격 문구에 수수료가 둘 이상인 '충돌'은 원본에서 재질·종류 등 구분 정보가 빠진 경우가 많다. 금액을 고르지 않고 지자체 확인을 안내한다.",
           "- 지자체마다 데이터기준일자가 다르다(1년 가까이 차이). 결과 화면에 반드시 기준일을 함께 표시한다.",
           "- '이하' 구간이 겹치면 포함관계상 가장 좁은 구간을 적용하고, 그 규칙을 결과 근거에 적는다.", ""]
    (OUT / "analysis.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


PILOTS = ["강남구", "고양시", "순천시"]

if __name__ == "__main__":
    main()
