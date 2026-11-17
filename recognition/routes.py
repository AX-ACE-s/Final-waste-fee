"""기능① 웹 API (Flask Blueprint).

원본: function1 app/main.py (상훈, FastAPI). 통합본 서버가 Flask라서 같은 주소·같은 응답 형식으로 옮겼다.
오류 응답도 원본(FastAPI)과 같은 {"detail": "..."} 형식이라 화면 코드(static/js/api.js)를 그대로 쓴다.

POST /recognize      사진 → 품목 후보와 근거 (RecognitionResult)
GET  /items/search   품목 직접 검색 (원본 API 유지. 통합 화면은 ②의 /api/spec/items 를 쓴다)
GET  /regions        선택할 수 있는 지역 목록 (원본 API 유지. 통합 화면은 ②의 /api/spec/regions 를 쓴다)
GET  /status         AI 키가 없어 연습용 가짜 응답으로 동작하는지
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from . import ai_client, catalog
from .recognition import recognize

MAX_IMAGE_BYTES = 5 * 1024 * 1024

bp = Blueprint("recognition", __name__)


def detect_image_type(data: bytes) -> str | None:
    """파일 앞부분으로 실제 이미지 종류를 확인한다 (확장자·브라우저가 알려준 종류는 믿지 않는다)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _error(status: int, detail: str):
    return jsonify({"detail": detail}), status


@bp.post("/recognize")
def recognize_photo():
    photo = request.files.get("photo")
    if photo is None:
        return _error(422, "사진 파일을 보내 주세요.")
    data = photo.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return _error(413, "사진은 5MB 이하만 올릴 수 있어요.")
    media_type = detect_image_type(data)
    if media_type is None:
        return _error(415, "jpg, png, webp 사진만 올릴 수 있어요.")
    sido = request.form.get("sido", "서울특별시")
    sigungu = request.form.get("sigungu", "마포구")
    # 개인정보 보호: 사진은 디스크에 저장하지 않고 이 요청 안에서만 쓴다.
    result = recognize(data, media_type, sido, sigungu)
    return jsonify(result.model_dump())


@bp.get("/items/search")
def search():
    return jsonify(catalog.search_items(request.args.get("sido", "서울특별시"),
                                        request.args.get("sigungu", "마포구"), request.args.get("q", "")))


@bp.get("/regions")
def regions():
    return jsonify(catalog.get_regions())


@bp.get("/status")
def status():
    return jsonify({"mock_mode": ai_client.is_mock()})
