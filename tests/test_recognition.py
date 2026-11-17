"""기능① 사진 인식 테스트 (원본: function1 tests/test_recognition.py, 상훈).

통합하면서 바꾼 곳
 - 서버가 FastAPI -> Flask 라서 TestClient 대신 Flask 테스트 클라이언트를 쓴다.
 - 원본의 data/sample_items.csv 는 tests/fixtures/recognition_sample_items.csv 로 옮기고,
   구분명을 실제 데이터 표기('가구류', '가전제품류')로 맞췄다.
 - 실제 데이터(data/fees.csv)로 지역·가전 판단이 맞는지 확인하는 테스트를 끝에 더했다.
API 키 없이 돌아간다.
"""
import json
from pathlib import Path

import pytest

from recognition import ai_client, catalog
from recognition.recognition import build_instruction, build_result, extract_json, recognize
from recognition.routes import detect_image_type

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recognition_sample_items.csv"
SIDO, SIGUNGU = "서울특별시", "마포구"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ITEMS_CSV", str(FIXTURE))


# 원본은 모듈을 읽을 때 샘플 CSV로 ITEMS 를 만든다. 통합본에서도 같은 샘플을 읽도록 잠깐 경로를 바꿔 읽는다.
with pytest.MonkeyPatch.context() as _mp:
    _mp.setenv("ITEMS_CSV", str(FIXTURE))
    ITEMS = catalog.get_items(SIDO, SIGUNGU)


def ai_answer(*candidates, recognized=True, features=None):
    return json.dumps(
        {"recognized": recognized, "candidates": list(candidates), "observed_features": features or {}},
        ensure_ascii=False,
    )


def cand(item, confidence="높음", evidence=("근거",)):
    return {"item": item, "confidence": confidence, "evidence": list(evidence)}


# --- 품목 목록 ---

def test_items_are_unique_per_region():
    assert list(ITEMS).count("소파") == 1  # 규격별로 3줄이지만 품목은 하나
    assert ITEMS["냉장고"] == "가전제품류"


def test_unknown_region_has_no_items():
    assert catalog.get_items("서울특별시", "없는구") == {}


def test_search_ignores_spaces_and_matches_partially():
    assert catalog.search_items(SIDO, SIGUNGU, "매트리스") == ["침대 매트리스"]
    assert catalog.search_items(SIDO, SIGUNGU, "침대매트") == ["침대 매트리스"]
    assert catalog.search_items(SIDO, SIGUNGU, "  ") == []


# --- 지시문 ---

def test_instruction_contains_every_item():
    instruction = build_instruction(ITEMS)
    assert all(name in instruction for name in ITEMS)


# --- AI 답 검증 ---

def test_valid_answer_becomes_result():
    result = build_result(ai_answer(cand("소파"), features={"좌석 수": "3인용"}), SIDO, SIGUNGU, ITEMS)
    assert result.recognized
    assert result.candidates[0].item == "소파"
    assert result.candidates[0].category == "가구류"
    assert result.observed_features == {"좌석 수": "3인용"}
    assert not result.is_appliance


def test_item_outside_list_is_dropped():
    result = build_result(ai_answer(cand("리클라이너"), cand("의자", "중간")), SIDO, SIGUNGU, ITEMS)
    assert [c.item for c in result.candidates] == ["의자"]


def test_only_unknown_items_means_not_recognized():
    result = build_result(ai_answer(cand("리클라이너")), SIDO, SIGUNGU, ITEMS)
    assert not result.recognized and result.candidates == [] and result.message


def test_spacing_difference_is_mapped_to_standard_name():
    result = build_result(ai_answer(cand("침대매트리스")), SIDO, SIGUNGU, ITEMS)
    assert result.candidates[0].item == "침대 매트리스"


def test_duplicates_and_extra_candidates_are_trimmed():
    answer = ai_answer(cand("소파"), cand("소파"), cand("의자"), cand("책상"), cand("식탁"))
    assert [c.item for c in build_result(answer, SIDO, SIGUNGU, ITEMS).candidates] == ["소파", "의자", "책상"]


def test_odd_confidence_falls_back_to_low():
    result = build_result(ai_answer(cand("소파", confidence="95%")), SIDO, SIGUNGU, ITEMS)
    assert result.candidates[0].confidence == "낮음"


def test_appliance_flag_follows_top_candidate():
    assert build_result(ai_answer(cand("냉장고"), cand("장롱")), SIDO, SIGUNGU, ITEMS).is_appliance
    assert not build_result(ai_answer(cand("장롱"), cand("냉장고")), SIDO, SIGUNGU, ITEMS).is_appliance


def test_ai_says_not_recognized():
    result = build_result(ai_answer(recognized=False), SIDO, SIGUNGU, ITEMS)
    assert not result.recognized and result.message


@pytest.mark.parametrize("text", ["", "잘 모르겠습니다", "{깨진 json", "[1, 2]", '{"candidates": "소파"}'])
def test_broken_answers_do_not_crash(text):
    assert not build_result(text, SIDO, SIGUNGU, ITEMS).recognized


def test_json_wrapped_in_other_text_is_extracted():
    assert extract_json('```json\n{"recognized": true}\n``` 입니다')["recognized"] is True


# --- 전체 흐름 ---

def test_ai_failure_leads_to_search_not_error(monkeypatch):
    def boom(*args):
        raise RuntimeError("AI 서버 장애")

    monkeypatch.setattr(ai_client, "ask_ai_about_image", boom)
    result = recognize(JPEG, "image/jpeg", SIDO, SIGUNGU)
    assert not result.recognized and "검색" in result.message


def test_region_without_data(monkeypatch):
    result = recognize(JPEG, "image/jpeg", "서울특별시", "없는구")
    assert not result.recognized and result.message


# --- API ---

@pytest.fixture()
def api():
    import app as flask_app
    return flask_app.app.test_client()


def test_image_type_detection():
    assert detect_image_type(JPEG) == "image/jpeg"
    assert detect_image_type(b"\x89PNG\r\n\x1a\n...") == "image/png"
    assert detect_image_type(b"RIFF0000WEBPVP8 ") == "image/webp"
    assert detect_image_type(b"%PDF-1.7") is None


def _photo(data):
    import io
    return (io.BytesIO(data), "a.jpg")


def test_api_recognize_in_mock_mode(api):
    res = api.post("/recognize", data={"sido": SIDO, "sigungu": SIGUNGU, "photo": _photo(JPEG)})
    body = res.get_json()
    assert res.status_code == 200
    assert body["recognized"] and body["candidates"][0]["item"] == "소파"
    assert body["candidates"][0]["evidence"]


def test_api_rejects_non_image(api):
    res = api.post("/recognize", data={"photo": _photo(b"%PDF-1.7 not an image")})
    assert res.status_code == 415


def test_api_rejects_large_file(api):
    res = api.post("/recognize", data={"photo": _photo(JPEG + b"0" * (5 * 1024 * 1024))})
    assert res.status_code == 413


def test_api_search_and_status(api):
    assert api.get("/items/search", query_string={"q": "소파"}).get_json() == ["소파"]
    assert api.get("/status").get_json() == {"mock_mode": True}


def test_api_regions(api):
    assert api.get("/regions").get_json() == {"서울특별시": ["마포구"]}


def test_screen_files_are_served(api):
    assert "text/html" in api.get("/").headers["content-type"]
    assert api.get("/static/js/app.js").status_code == 200
    assert api.get("/static/css/style.css").status_code == 200


# --- 통합: 실제 데이터(data/fees.csv)로 동작 (통합하면서 더함) ---

def test_other_spelling_is_mapped_to_region_name():
    """수수료표에 '쇼파'로 적힌 지역에서 AI가 '소파'라고 답해도 후보에서 빠지지 않는다."""
    items = {"쇼파": "가구류", "의자": "가구류"}
    assert catalog.match_item("소파", items) == "쇼파"
    assert catalog.match_item("리클라이너", items) is None


REAL = Path(__file__).resolve().parent.parent / "data" / "fees.csv"


@pytest.mark.skipif(not REAL.exists(), reason="실제 데이터(data/fees.csv)가 없으면 건너뜀")
def test_real_data_regions_and_appliance_flag(monkeypatch):
    monkeypatch.setenv("ITEMS_CSV", str(REAL))
    items = catalog.get_items("서울특별시", "강남구")
    assert items and items.get("냉장고") == catalog.APPLIANCE_CATEGORY
    answer = ai_answer(cand("냉장고"))
    assert build_result(answer, "서울특별시", "강남구", items).is_appliance
    assert "세종특별자치시" in catalog.get_regions()
