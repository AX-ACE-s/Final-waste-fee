"""행정안전부 도로명주소 검색 API 클라이언트 (공공데이터포털 15057017 / business.juso.go.kr).

응답에서 siNm(시도), sggNm(시군구)만 사용해 관할 지자체(region)와 연결한다.
키(JUSO_API_KEY)가 없거나 API가 실패하면 예외를 올리고, 화면은 시·도/시·군·구 직접 선택으로 대체한다.
"""
from __future__ import annotations

import os

import httpx

JUSO_URL = os.getenv("JUSO_API_URL", "https://business.juso.go.kr/addrlink/addrLinkApi.do")


class JusoError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


# 행안부 도로명주소 API 오류코드 -> 사용자에게 보여 줄 안내문
FRIENDLY = {
    "E0001": "주소검색 승인키 설정에 문제가 있어요. 아래에서 지역을 직접 선택해 주세요.",
    "E0005": "검색어를 입력해 주세요.",
    "E0006": "검색어가 너무 넓어요. 동 이름이나 건물명까지 입력해 보세요. (예: 강남구 역삼동, 해운대구청)",
    "E0008": "검색어를 두 글자 이상 입력해 주세요.",
    "E0009": "검색어에 사용할 수 없는 문자가 있어요.",
    "E0010": "검색어가 너무 길어요. 조금 줄여서 입력해 주세요.",
    "E0011": "검색어에 사용할 수 없는 문자가 있어요.",
    "E0012": "검색어에 사용할 수 없는 문자가 있어요.",
}
FALLBACK_MSG = "주소를 찾는 중 문제가 생겼어요. 아래에서 지역을 직접 선택해 주세요."


def search_address(keyword: str, *, client: httpx.Client | None = None, timeout: float = 5.0) -> list[dict]:
    key = os.getenv("JUSO_API_KEY")
    if not key:
        raise JusoError("주소검색을 쓸 수 없어요. 아래에서 지역을 직접 선택해 주세요.", code="NO_KEY")
    if len(keyword.strip()) < 2:
        raise JusoError(FRIENDLY["E0008"], code="E0008")
    params = {"confmKey": key, "currentPage": 1, "countPerPage": 10, "keyword": keyword, "resultType": "json"}
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(JUSO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        raise JusoError("주소검색 응답이 늦어지고 있어요. 아래에서 지역을 직접 선택해 주세요.", code="TIMEOUT")
    except (httpx.HTTPError, ValueError) as e:
        raise JusoError(FALLBACK_MSG, code="HTTP")
    finally:
        if own:
            client.close()
    results = (data or {}).get("results") or {}
    common = results.get("common") or {}
    if common.get("errorCode") not in (None, "0"):
        raise JusoError(FRIENDLY.get(common.get("errorCode"), FALLBACK_MSG), code=common.get("errorCode"))
    out = []
    for j in results.get("juso") or []:
        out.append({"road_addr": j.get("roadAddr"), "jibun_addr": j.get("jibunAddr"),
                    "sido": j.get("siNm"), "sigungu": j.get("sggNm"), "emd": j.get("emdNm")})
    return out


def resolve_region(con, sido: str | None, sigungu: str | None):
    """'수원시 장안구'처럼 일반구가 붙은 경우 시 단위로도 찾아본다."""
    if not sido:
        return None
    if not sigungu:  # 세종특별자치시: 주소 API의 sggNm이 비어 있음
        return con.execute("SELECT * FROM region WHERE sido=? AND sigungu='(시 전체)'", (sido,)).fetchone()
    r = con.execute("SELECT * FROM region WHERE sido=? AND sigungu=?", (sido, sigungu)).fetchone()
    if r:
        return r
    head = sigungu.split()[0]
    return con.execute("SELECT * FROM region WHERE sido=? AND sigungu=?", (sido, head)).fetchone()
