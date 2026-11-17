"""계획서 ② '제품 설명을 읽고 지자체 품목·규격으로 번역' — 설명 문장 읽기."""
import pytest

from spec_question import describe
from spec_question.engine import estimate


@pytest.mark.parametrize("text,item,hints,qty", [
    ("폭 180cm 3인용 소파", "SOFA", {"width": 180, "seats": 3}, None),
    ("450리터 냉장고", "FRIDGE", {"volume": 450}, None),
    ("세탁기 12키로", "WASHER", {"weight": 12}, None),
    ("55인치 티비", "TV", {"inch": 55}, None),
    ("5단 서랍장 2개", "DRAWER", {"tiers": 5}, 2),
    ("장롱 1.2미터", "WARDROBE", {"size": 120}, None),
    ("2인용 침대 매트리스", "MATTRESS", {"seats": 2}, None),  # 더 긴 이름(침대매트리스)이 '침대'보다 우선
])
def test_read_description(text, item, hints, qty):
    d = describe.read(text)
    assert d["items"][0] == item
    assert d["hints"] == hints
    assert d["quantity"] == qty


def test_read_pyeong_to_m2():
    d = describe.read("18평형 에어컨")
    assert d["items"][0] == "AIRCON" and d["hints"]["area"] == pytest.approx(59.5)


def test_description_skips_questions(con, rid):
    """설명만으로 종류·폭이 확정되면 질문 없이 결과까지 간다(해운대구 소파: 일반 소파 / 폭 기준)."""
    r = estimate(con, rid["해운대구"], "SOFA", answers={"description": "폭 180cm 3인용 소파"})
    assert r["status"] == "result"
    assert r["result"]["spec"]["raw"] == "3인용(폭 1.8m 이하)" and r["result"]["unit_fee"] == 15000
    assert any("설명에서 읽음" in t for t in r["result"]["inputs"])


def test_description_picks_group_by_word(con, rid):
    """'라텍스'라는 단어로 종류를 고르고, 폭 150cm로 구간을 고른다."""
    r = estimate(con, rid["해운대구"], "MATTRESS", answers={"description": "라텍스 매트리스 가로 150cm"})
    assert r["result"]["spec"]["raw"].startswith("라텍스, 포켓스프링 2인용") and r["result"]["unit_fee"] == 20000


def test_item_name_alone_does_not_pick_group(con, rid):
    """품목명만 쓰면 아무것도 고르지 않고 그대로 묻는다(품목명이 선택지 이름에 들어 있어도)."""
    r = estimate(con, rid["해운대구"], "SOFA", answers={"description": "소파"})
    assert r["status"] == "question" and r["question"]["id"] == "group"


def test_description_picks_categorical_spec(con, rid):
    r = estimate(con, rid["해운대구"], "PIANO", answers={"description": "업라이트 피아노"})
    assert r["result"]["spec"]["raw"] == "업라이트" and r["result"]["unit_fee"] == 20000


def test_description_picks_local_item(con, rid):
    r = estimate(con, rid["부여군"], "ELEC_MAT", answers={"description": "전기장판 2인용"})
    assert r["result"]["local_item"] == "전기장판" and r["result"]["unit_fee"] == 5000


def test_direction_mismatch_is_prefilled_not_applied(con, rid):
    """'180cm'처럼 방향 없는 길이는 '가로' 기준 품목에 자동 적용하지 않고 입력칸에 미리 넣어 확인받는다."""
    r = estimate(con, rid["해운대구"], "WARDROBE", answers={"description": "장롱 180cm"})
    q = r["question"]
    assert r["status"] == "question" and q["dim"] == "width"
    assert q["prefill"] == 180 and "확인" in q["prefill_note"]


def test_explicit_answer_beats_description(con, rid):
    """설명보다 사용자가 직접 입력한 값이 우선."""
    r = estimate(con, rid["부여군"], "SOFA", answers={"description": "3인용 쇼파", "measure": {"seats": 2}})
    assert r["result"]["spec"]["raw"] == "2인이하"


def test_description_contradiction_triggers_correction(con, rid):
    """설명에는 폭 125cm인데 '가로 90cm 미만'을 직접 고르면 보정 안내."""
    sid = con.execute("""SELECT s.id FROM item_specification s JOIN local_item li ON li.id=s.local_item_id
                         WHERE li.region_id=? AND li.raw_name='장롱' AND s.raw_spec='가로 90cm 미만'""",
                      (rid["해운대구"],)).fetchone()[0]
    r = estimate(con, rid["해운대구"], "WARDROBE", answers={"description": "가로 125cm 장롱", "spec": sid})
    assert r["result"]["correction"]["spec"] == "가로 120cm 이상"


def test_handoff_payload(con, rid):
    """②→③ 넘겨주는 값."""
    r = estimate(con, rid["해운대구"], "FRIDGE", answers={"description": "450리터 냉장고"})
    h = r["result"]["handoff"]
    assert h["standard_code"] == "FRIDGE" and h["sigungu"] == "해운대구"
    assert h["spec"] == "300L 이상 500L 미만" and h["spec_id"] and h["quantity"] == 1


def test_parse_api_filters_by_region(client, rid):
    d = client.get("/api/spec/parse", query_string={"text": "2인용 침대 매트리스", "region_id": rid["부여군"]}).get_json()
    assert d["items"][0] == "MATTRESS" and d["hints"] == {"seats": 2}
    d = client.get("/api/spec/parse", query_string={"text": "소파", "region_id": rid["김해시"]}).get_json()
    assert d["items"] == []   # 김해시 데이터에는 소파가 없음
