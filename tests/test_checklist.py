"""기능④ 배출 전 체크리스트·신청 연결 테스트 (통합하면서 더함. 원본 저장소에는 테스트가 없었다)."""
import json
from pathlib import Path

import pytest

from checklist import routes

DATA = Path(routes.__file__).parent / "data"


@pytest.fixture()
def api():
    import app as flask_app
    return flask_app.app.test_client()


def test_options_lists_25_seoul_districts(api):
    body = api.get("/api/options").get_json()
    assert len(body["districts"]) == 25 and "강남구" in body["districts"]
    assert {h["id"] for h in body["housing"]} == {"house", "apartment"}


def test_checklist_has_three_stages_and_apply_link(api):
    body = api.get("/api/checklist", query_string={"district": "강남구", "item": "sofa", "housing": "house"}).get_json()
    assert [s["id"] for s in body["stages"]] == ["before", "prepare", "putout"]
    assert body["apply"]["url"].startswith("https://")
    texts = [e["id"] for s in body["stages"] for e in s["entries"]]
    assert "mattress_dry" in texts and "fridge_clean" not in texts


def test_appliance_gets_free_pickup_rule(api):
    body = api.get("/api/checklist", query_string={"district": "마포구", "item": "fridge"}).get_json()
    assert any(e["id"] == "free_pickup" for s in body["stages"] for e in s["entries"])


@pytest.mark.parametrize("query", [{"district": "해운대구", "item": "sofa"}, {"district": "강남구", "item": "없음"},
                                   {"district": "강남구", "item": "sofa", "housing": "villa"}])
def test_checklist_rejects_bad_values(api, query):
    assert api.get("/api/checklist", query_string=query).status_code == 400


def test_checklist_page_is_served(api):
    res = api.get("/checklist/")
    assert res.status_code == 200 and "/checklist/static/app.js" in res.get_data(as_text=True)
    assert api.get("/checklist/static/app.js").status_code == 200


def test_link_from_fee_result(api):
    body = api.get("/api/checklist/link", query_string={"sido": "서울특별시", "sigungu": "강남구", "code": "KIMCHI_FRIDGE"}).get_json()
    assert body["available"] and body["item"] == "fridge"
    assert body["url"].startswith("/checklist/?") and "item=fridge" in body["url"]
    other = api.get("/api/checklist/link", query_string={"sido": "서울특별시", "sigungu": "강남구", "code": "WREATH"}).get_json()
    assert other["item"] == "etc"
    busan = api.get("/api/checklist/link", query_string={"sido": "부산광역시", "sigungu": "해운대구", "code": "SOFA"}).get_json()
    assert not busan["available"] and "서울" in busan["reason"]
    assert busan["url"] == "/checklist/?item=sofa"  # 서울이 아니어도 공통 항목 페이지로 갈 수 있다


def test_mapping_points_to_real_checklist_items():
    ids = {i["id"] for i in json.loads((DATA / "checklists.json").read_text(encoding="utf-8"))["items"]}
    assert set(routes.CODE_TO_ITEM) <= ids and "etc" in ids
