"""개발 지시서 '9. 테스트 및 검증'의 필수 6개 사례 + 보강 사례."""
import csv

import httpx
import pytest

from spec_question import juso
from spec_question.engine import estimate
from etl.normalize import ItemMatcher, parse_spec
from tests.spec_conftest_helpers import RAW


# 1. 동일 품목을 서로 다른 지역에서 조회하면 수수료가 달라지는지
def test_same_item_different_regions(con, rid):
    a = estimate(con, rid["해운대구"], "WARDROBE", answers={"measure": {"width": 130}})
    b = estimate(con, rid["부여군"], "WARDROBE", answers={"measure": {"width": 130}})
    assert a["status"] == b["status"] == "result"
    assert a["result"]["unit_fee"] == 18000   # 해운대구 '가로 120cm 이상'
    assert b["result"]["unit_fee"] == 15000   # 부여군 '폭120cm이상'
    assert a["result"]["unit_fee"] != b["result"]["unit_fee"]


def test_same_item_regions_ask_different_questions(con, rid):
    """해운대구 소파는 종류→폭(cm), 부여군 쇼파는 인용만 묻는다(지역 기준 맞춤 질문)."""
    a = estimate(con, rid["해운대구"], "SOFA")
    b = estimate(con, rid["부여군"], "SOFA")
    assert a["question"]["id"] == "group"
    assert b["question"]["id"] == "measure.seats"


# 2. 규격을 입력하지 않으면 추가 질문이 표시되는지
def test_missing_spec_returns_question(con, rid):
    r = estimate(con, rid["해운대구"], "FRIDGE")
    assert r["status"] == "question"
    q = r["question"]
    assert q["type"] == "number" and q["unit"] == "L"
    assert q["fallback"]["options"], "크기를 모를 때 고를 공식 규격이 있어야 함"


def test_single_spec_item_asks_nothing(con, rid):
    r = estimate(con, rid["부여군"], "VANITY")  # 화장대 '모든규격'
    assert r["status"] == "result" and r["result"]["unit_fee"] == 5000


# 3. 존재하지 않는 품목 예외 처리
def test_unknown_item(con, rid):
    assert estimate(con, rid["해운대구"], "NO_SUCH_ITEM")["status"] == "not_found"


def test_item_missing_in_region_lists_other_regions(con, rid):
    r = estimate(con, rid["김해시"], "SOFA")
    assert r["status"] == "not_found"
    assert {x["sigungu"] for x in r["other_regions"]} >= {"해운대구", "부여군"}


def test_unknown_item_api(client, rid):
    res = client.get(f"/api/spec/items?region_id={rid['해운대구']}&q=우주선")
    assert res.status_code == 404
    assert client.get("/api/spec/items?region_id=99999").status_code == 404


# 4. 공공데이터 API 응답이 없을 때 오류 처리
def test_juso_timeout(monkeypatch):
    monkeypatch.setenv("JUSO_API_KEY", "dummy")

    def boom(request):
        raise httpx.ReadTimeout("timeout", request=request)
    c = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(juso.JusoError, match="늦어"):
        juso.search_address("해운대구 우동", client=c)


def test_juso_error_code(monkeypatch):
    monkeypatch.setenv("JUSO_API_KEY", "dummy")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"results": {"common": {"errorCode": "E0001", "errorMessage": "승인되지 않은 KEY"}, "juso": None}})))
    with pytest.raises(juso.JusoError, match="승인키") as ei:
        juso.search_address("해운대구 우동", client=c)
    assert ei.value.code == "E0001"


def test_juso_too_broad_is_friendly(monkeypatch):
    monkeypatch.setenv("JUSO_API_KEY", "dummy")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"results": {"common": {"errorCode": "E0006", "errorMessage": "주소를 상세히 입력해 주시기 바랍니다."}, "juso": None}})))
    with pytest.raises(juso.JusoError) as ei:
        juso.search_address("강남구", client=c)
    assert "동 이름이나 건물명" in str(ei.value) and "E0006" not in str(ei.value)


def test_juso_success_maps_region(monkeypatch, con):
    monkeypatch.setenv("JUSO_API_KEY", "dummy")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {
        "common": {"errorCode": "0"},
        "juso": [{"roadAddr": "부산광역시 해운대구 해운대로 1", "siNm": "부산광역시", "sggNm": "해운대구", "emdNm": "우동"}]}})))
    rows = juso.search_address("해운대로", client=c)
    assert juso.resolve_region(con, rows[0]["sido"], rows[0]["sigungu"])["sigungu"] == "해운대구"


def test_address_endpoint_without_key(client, monkeypatch):
    monkeypatch.delenv("JUSO_API_KEY", raising=False)
    res = client.get("/api/address?q=해운대")
    assert res.status_code == 503 and "직접 선택" in res.get_json()["detail"]


# 5. 표준 품목명과 지역별 품목명 매핑
@pytest.mark.parametrize("raw,codes,method", [
    ("쇼파", ["SOFA"], "typo"),
    ("소파(쿠션 별도)", ["SOFA"], "exact"),
    ("침대 매트리스", ["MATTRESS"], "exact"),
    ("침대매트리스", ["MATTRESS"], "exact"),
    ("서랍장 신발장", ["DRAWER", "SHOE_CABINET"], "split"),
    ("옥매트, 전기매트, 황토매트", ["ELEC_MAT"], "split"),
    ("책꽃이", ["BOOKSHELF"], "typo"),
    ("씽크대", ["SINK"], "typo"),
    ("냉장고(가정용)", ["FRIDGE"], "exact"),
])
def test_name_mapping(raw, codes, method):
    m = ItemMatcher().match(raw)
    assert m.codes == codes and m.method == method


def test_search_with_typo():
    assert "SOFA" in ItemMatcher().search("쇼파 3인용".split()[0])


def test_region_local_names_mapped(con, rid):
    rows = con.execute("""SELECT li.raw_name FROM local_item li JOIN item_mapping m ON m.local_item_id=li.id
                          JOIN standard_item s ON s.id=m.standard_item_id WHERE s.code='SOFA'""").fetchall()
    assert {r[0] for r in rows} == {"소파(쿠션 별도)", "쇼파"}


# 6. 실제 수수료 데이터와 결과 금액 일치 — 원본 CSV 모든 행을 엔진으로 재조회
def test_every_row_fee_matches_source(con, rid):
    with open(RAW, encoding="utf-8-sig") as f:
        src = list(csv.DictReader(f))
    checked = 0
    for row in src:
        r_id = rid[row["시군구명"]]
        li = con.execute("SELECT id FROM local_item WHERE region_id=? AND raw_name=?", (r_id, row["대형폐기물명"])).fetchone()
        specs = con.execute("""SELECT s.id, f.fee, s.per_unit_amount FROM item_specification s JOIN disposal_fee f ON f.spec_id=s.id
                               WHERE s.local_item_id=? AND s.raw_spec=?""", (li[0], row["대형폐기물규격"])).fetchall()
        spec_id, _, per = next(s for s in specs if s[1] == int(row["수수료"]))
        ans = {"spec": spec_id, "amount": per or 1}
        res = estimate(con, r_id, None, li[0], ans)
        if len({s[1] for s in specs}) > 1:
            assert res["status"] == "needs_confirmation", row
            assert int(row["수수료"]) in [c["fee"] for c in res["candidates"]]
        else:
            assert res["status"] == "result", (row, res)
            assert res["result"]["unit_fee"] == int(row["수수료"])
            assert res["result"]["source"]["base_date"] == row["데이터기준일자"]
        checked += 1
    assert checked == len(src) == 363


# ---- 보강: 입력 검증 · 실측 보정 · 단위당 요금 · 충돌 ----
def test_meter_input_hint(con, rid):
    r = estimate(con, rid["부여군"], "WARDROBE", answers={"measure": {"width": 1.3}})
    assert r["status"] == "invalid" and "미터" in r["message"]


def test_non_numeric(con, rid):
    r = estimate(con, rid["부여군"], "WARDROBE", answers={"measure": {"width": "abc"}})
    assert r["status"] == "invalid"


def test_measure_out_of_all_bands_falls_back(con, rid):
    r = estimate(con, rid["해운대구"], "SOFA", answers={"group": "__measure__", "measure": {"width": 200}})
    assert r["status"] == "question" and r["question"]["id"] == "spec" and "구간" in r["warning"]


def test_narrowest_band_rule(con, rid):
    r = estimate(con, rid["해운대구"], "ELEC_MAT", answers={"measure": {"width": 140}})
    assert r["result"]["spec"]["raw"] == "2인용 (가로 150cm 이하)" and r["result"]["unit_fee"] == 10000


def test_measure_correction_after_wrong_choice(con, rid):
    specs = {s["raw_spec"]: s["id"] for s in con.execute(
        """SELECT s.raw_spec, s.id FROM item_specification s JOIN local_item li ON li.id=s.local_item_id
           WHERE li.region_id=? AND li.raw_name='장롱'""", (rid["해운대구"],))}
    r = estimate(con, rid["해운대구"], "WARDROBE",
                 answers={"spec": specs["가로 90cm 미만"], "measure": {"width": 125}})
    c = r["result"]["correction"]
    assert c and c["spec"] == "가로 120cm 이상" and c["fee"] == 18000


def test_per_unit_fee(con, rid):
    r = estimate(con, rid["해운대구"], "CARPET")
    assert r["question"]["id"] == "amount"
    r = estimate(con, rid["해운대구"], "CARPET", answers={"amount": 2.3, "quantity": 2})
    assert r["result"]["units"] == 3 and r["result"]["total_fee"] == 2500 * 3 * 2


def test_conflicting_duplicate_not_guessed(con, rid):
    r = estimate(con, rid["해운대구"], "BATHTUB", answers={"measure": {"length": 150}})
    assert r["status"] == "needs_confirmation"
    assert sorted(c["fee"] for c in r["candidates"]) == [9000, 12000]


def test_local_item_choice_when_multiple(con, rid):
    r = estimate(con, rid["부여군"], "DISPLAY_CABINET")
    assert r["question"]["id"] == "local_item"
    assert {o["label"] for o in r["question"]["options"]} == {"장식장", "진열장"}


def test_quantity_validation(con, rid):
    assert estimate(con, rid["부여군"], "VANITY", answers={"quantity": 0})["status"] == "invalid"


def test_estimate_api_flow(client, rid):
    body = {"region_id": rid["해운대구"], "standard_code": "MATTRESS", "answers": {}}
    r = client.post("/api/spec/estimate", json=body).get_json()
    assert r["question"]["id"] == "group"
    body["answers"] = {"group": "일반형", "measure": {"width": 140}}
    r = client.post("/api/spec/estimate", json=body).get_json()
    assert r["status"] == "result" and r["result"]["total_fee"] == 15000
    assert r["result"]["source"]["url"].startswith("https://www.data.go.kr/data/15114146")
    # ②가 확정한 규격이 ③(수수료 산정·근거 안내)으로 이어진다
    fd = r["fee_detail"]
    assert fd["fee"] == 15000 and fd["basis"]["spec"] == "일반형 2인용(가로 1.2~1.5m 미만)"
    assert fd["explanation"] and fd["alternatives"] and "입력값이 포함되는" in fd["basis"]["decided_by"]


# ---- 파서 ----
@pytest.mark.parametrize("text,dim,lo,hi", [
    ("가로 1.2~1.6m 미만", "width", 120, 160),
    ("폭 40이상 80cm 미만", "width", 40, 80),
    ("29인치 이상 49인치 미만", "inch", 29, 49),
    ("3㎏~10kg미만", "weight", 3, 10),
    ("긴면1m이상2m미만", "length", 100, 200),
    ("높이1m미만", "height", None, 100),
    ("500L 이상 1000L 미만", "volume", 500, 1000),
])
def test_parse_ranges(text, dim, lo, hi):
    p = parse_spec(text)
    r = next(x for x in p.ranges if x.dim == dim)
    assert (r.min, r.max) == (lo, hi)


def test_parse_special():
    assert parse_spec("모든 규격").spec_type == "all"
    assert parse_spec("2M X 2M 이상").spec_type == "categorical"
    assert parse_spec("1㎡ 당").spec_type == "per_unit"
    assert parse_spec("일반형 1인용(가로 1.2cm 미만)").anomalies


# ---- 실제 주소검색 API 응답(2026-11, 키 발급 후 직접 호출한 결과)으로 검증 ----
def test_juso_real_response_shape(monkeypatch, con):
    import json
    from pathlib import Path
    body = json.loads((Path(__file__).parent / "fixtures" / "juso_real_response.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("JUSO_API_KEY", "dummy")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    rows = juso.search_address("해운대구청", client=c)
    assert rows[0]["sido"] == "부산광역시" and rows[0]["sigungu"] == "해운대구"
    assert rows[0]["road_addr"] == "부산광역시 해운대구 중동2로 11 (중동)"
    assert juso.resolve_region(con, rows[0]["sido"], rows[0]["sigungu"]) is not None


def test_correction_for_count_dimension(con, rid):
    """서랍장 규격을 '3단 이하'로 골랐는데 실측이 6단이면 맞는 규격을 제안한다(인용·단·개수도 보정 대상)."""
    sid = con.execute("""SELECT s.id FROM item_specification s JOIN local_item li ON li.id=s.local_item_id
                         JOIN item_mapping m ON m.local_item_id=li.id JOIN standard_item si ON si.id=m.standard_item_id
                         WHERE li.region_id=? AND si.code='DRAWER' AND s.raw_spec='3단 이하'""", (rid["해운대구"],)).fetchone()[0]
    r = estimate(con, rid["해운대구"], "DRAWER", answers={"spec": sid, "measure": {"tiers": 6}})
    c = r["result"]["correction"]
    assert c and c["spec"] == "6단 이상" and c["fee"] == 14000
