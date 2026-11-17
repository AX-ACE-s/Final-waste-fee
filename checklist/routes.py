"""기능④ 배출 전 체크리스트·신청 연결 (서울특별시) — Flask Blueprint.

원본: un6i-feature-checklist app.py (지윤). 통합본 서버에 붙이려고 Flask 앱을 Blueprint 로 바꿨고,
체크리스트를 만드는 규칙(build_checklist, build_apply)과 데이터(data/*.json)는 원본 그대로다.

GET /checklist/                                 체크리스트 화면 (원본 static/index.html)
GET /api/options                                자치구·품목·주거형태 목록
GET /api/checklist?district=&item=&housing=     체크리스트 + 신청 연결 정보
GET /api/checklist/link?sido=&sigungu=&code=    (통합하면서 더함) 수수료 결과 화면 → 체크리스트 주소
"""
import json
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, jsonify, request, send_from_directory

BASE = Path(__file__).parent
DATA = BASE / "data"
STAGES = [
    {"id": "before", "name": "신고 전에 확인하기"},
    {"id": "prepare", "name": "물건 준비하기"},
    {"id": "putout", "name": "내놓기"},
]

bp = Blueprint("checklist", __name__, static_folder="static", static_url_path="/checklist/static")


def load(name):
    # 요청마다 다시 읽어서, JSON을 고치면 서버 재시작 없이 반영된다.
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def rule_applies(rule, item, housing):
    """rule["when"]의 조건(category / items / housing)을 모두 만족하면 True."""
    when = rule.get("when", {})
    if "category" in when and item["category"] not in when["category"]:
        return False
    if "items" in when and item["id"] not in when["items"]:
        return False
    if "housing" in when and housing not in when["housing"]:
        return False
    return True


def build_checklist(district, item, housing, rules):
    stages = []
    for stage in STAGES:
        entries = []
        for rule in rules:
            if rule["stage"] != stage["id"] or not rule_applies(rule, item, housing):
                continue
            entry = {"id": rule["id"], "text": rule["text"], "why": rule.get("why", "")}
            # 자치구마다 다른 항목: districts.json에 값이 있으면 그 값을, 없으면 '확인 필요' 표시
            field = rule.get("district_field")
            if field:
                entry["local"] = district.get(field)
                entry["needs_local_check"] = not district.get(field)
            entries.append(entry)
        if entries:
            stages.append({**stage, "entries": entries})
    return stages


def build_apply(district):
    if district.get("apply_url"):
        return {
            "url": district["apply_url"],
            "label": f"{district['name']} 대형폐기물 신청 페이지 열기",
            "direct": True,
            "hint": "",
        }
    return {
        "url": district["homepage"],
        "label": f"{district['name']}청 누리집 열기",
        "direct": False,
        "hint": "누리집 검색창에 ‘대형폐기물’을 입력하면 신청 메뉴로 갈 수 있습니다.",
    }


@bp.get("/checklist/")
def index():
    return send_from_directory(bp.static_folder, "index.html")


@bp.get("/api/options")
def options():
    districts = load("districts.json")["districts"]
    cl = load("checklists.json")
    return jsonify(
        districts=[d["name"] for d in districts],
        categories=cl["categories"],
        items=cl["items"],
        housing=cl["housing"],
    )


@bp.get("/api/checklist")
def checklist():
    districts = {d["name"]: d for d in load("districts.json")["districts"]}
    cl = load("checklists.json")
    items = {i["id"]: i for i in cl["items"]}
    housing_ids = [h["id"] for h in cl["housing"]]

    district = districts.get(request.args.get("district", ""))
    item = items.get(request.args.get("item", ""))
    housing = request.args.get("housing", housing_ids[0])

    if district is None:
        return jsonify(error="서울특별시 25개 자치구 중 하나를 선택하세요."), 400
    if item is None:
        return jsonify(error="버릴 품목을 선택하세요."), 400
    if housing not in housing_ids:
        return jsonify(error="주거 형태 값이 올바르지 않습니다."), 400

    return jsonify(
        district=district["name"],
        item=item,
        housing=housing,
        stages=build_checklist(district, item, housing, cl["rules"]),
        apply=build_apply(district),
        basis={
            "updated": cl["basis"]["updated"],
            "sources": cl["basis"]["sources"],
            "district_verified_on": district.get("verified_on"),
        },
    )


# ---- 통합하면서 더한 부분: 수수료 결과(①②③)에서 체크리스트로 넘어가기 -------------------------
# ②의 표준 품목 코드 → 체크리스트 품목 id. 목록에 없는 품목은 '그 밖의 물건'(etc) 공통 목록으로 보낸다.
# 큰 가전(식기세척기·안마의자 등)은 '소형 가전' 규칙(여러 개 모아 무상수거)이 맞지 않아 etc 로 둔다.
CODE_TO_ITEM = {
    "wardrobe": ["WARDROBE", "CLOSET"],
    "bed": ["BED_FRAME", "BED", "BED_SET", "BABY_BED", "STONE_BED"],
    "mattress": ["MATTRESS"],
    "sofa": ["SOFA"],
    "desk": ["DESK", "DINING_TABLE", "TABLE", "SIDE_TABLE", "LOW_TABLE"],
    "chair": ["CHAIR"],
    "drawer": ["DRAWER", "CABINET", "CUPBOARD", "DISPLAY_CABINET", "LIVING_CABINET", "SHOE_CABINET", "FILE_CABINET"],
    "bookshelf": ["BOOKCASE", "BOOKSHELF"],
    "vanity": ["VANITY"],
    "fridge": ["FRIDGE", "KIMCHI_FRIDGE"],
    "washer": ["WASHER", "DRUM_WASHER", "DRYER", "SPIN_DRYER"],
    "aircon": ["AIRCON"],
    "tv": ["TV"],
    "small_appliance": ["FAN", "MICROWAVE", "RICE_COOKER", "IRON", "AUDIO", "SPEAKER", "VACUUM", "HUMIDIFIER",
                        "AIR_PURIFIER", "BIDET", "PRINTER", "FAX", "VIDEO", "COMPUTER", "DISH_DRYER"],
    "mirror": ["MIRROR"],
    "bedding": ["BEDDING", "CARPET"],
    "bicycle": ["BICYCLE"],
    "piano": ["PIANO"],
}
_ITEM_BY_CODE = {code: item for item, codes in CODE_TO_ITEM.items() for code in codes}
SEOUL = "서울특별시"


def checklist_item_for(code: str | None) -> str:
    return _ITEM_BY_CODE.get(code or "", "etc")


@bp.get("/api/checklist/link")
def link():
    """available: 그 지역(서울 자치구) 기준 안내가 있는지. 없어도 공통 항목을 볼 수 있게 주소는 항상 준다."""
    sido, sigungu = request.args.get("sido", ""), request.args.get("sigungu", "")
    districts = [d["name"] for d in load("districts.json")["districts"]]
    item = checklist_item_for(request.args.get("code"))
    names = {i["id"]: i["name"] for i in load("checklists.json")["items"]}
    available = sido == SEOUL and sigungu in districts
    query = {"district": sigungu, "item": item} if available else {"item": item}
    return jsonify(available=available, item=item, item_name=names.get(item, ""),
                   url="/checklist/?" + urlencode(query),
                   reason="" if available else
                   "체크리스트의 구청별 안내는 지금 서울특별시 25개 자치구 기준이에요. 공통 확인 항목을 참고하고, "
                   "배출 장소·시간은 관할 지자체 안내를 확인해 주세요.")


@bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response
