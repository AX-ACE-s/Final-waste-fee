"""품목 목록(카탈로그): 표준데이터 CSV에서 지자체별 표준 품목명을 읽는다.

원본: 기능① function1 app/catalog.py (상훈). 통합하면서 바꾼 곳: 읽는 파일 경로, 가전 구분명, 파일 갱신 감지.

AI는 여기서 나온 이름 안에서만 고를 수 있고, AI의 답도 여기 이름과 대조해 검증한다.
"""
import csv
import os
from functools import lru_cache
from pathlib import Path

# 실제 표준데이터 CSV(data/fees.csv) 헤더와 맞춤 (통합 시 확인 완료)
COL_SIDO = "시도명"
COL_SIGUNGU = "시군구명"
COL_ITEM = "대형폐기물명"
COL_CATEGORY = "대형폐기물구분명"

APPLIANCE_CATEGORY = "가전제품류"  # 실제 데이터의 구분명 표기 (통합 시 '가전' -> '가전제품류'로 맞춤)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _csv_path() -> Path:
    # 통합본: 수수료(③)·규격(②)과 같은 원본 data/fees.csv 를 읽는다. 없으면 시연용 샘플.
    path = Path(os.getenv("ITEMS_CSV", "data/fees.csv"))
    path = path if path.is_absolute() else _PROJECT_ROOT / path
    if not path.exists() and "ITEMS_CSV" not in os.environ:
        path = _PROJECT_ROOT / "data" / "fees_sample.csv"
    return path


def _rows() -> tuple[dict, ...]:
    path = _csv_path()
    # 수정 시각을 함께 넘겨, 서버가 데이터를 새로 받으면(공공데이터 API 갱신) 다시 읽게 한다.
    return _read_rows(str(path), path.stat().st_mtime if path.exists() else 0)


@lru_cache(maxsize=4)
def _read_rows(path: str, _mtime: float = 0) -> tuple[dict, ...]:
    # 공공데이터 CSV는 UTF-8 또는 CP949(EUC-KR)로 제공되므로 둘 다 시도한다.
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                rows = tuple(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
        missing = {COL_SIDO, COL_SIGUNGU, COL_ITEM} - set(rows[0].keys() if rows else [])
        if missing:
            raise ValueError(f"CSV에 필요한 열이 없습니다: {missing}. catalog.py의 COL_* 를 확인하세요.")
        return rows
    raise ValueError(f"CSV 인코딩을 알 수 없습니다: {path}")


def normalize(name: str) -> str:
    """이름 비교용: 공백 차이를 무시한다 ('침대 매트리스' == '침대매트리스')."""
    return "".join(name.split())


def get_regions() -> dict[str, list[str]]:
    """데이터에 들어 있는 지역 목록 {시도명: [시군구명, ...]}. 화면의 지역 선택 상자에 쓴다."""
    regions: dict[str, list[str]] = {}
    for row in _rows():
        sigungus = regions.setdefault(row[COL_SIDO].strip(), [])
        if row[COL_SIGUNGU].strip() not in sigungus:
            sigungus.append(row[COL_SIGUNGU].strip())
    return regions


def get_items(sido: str, sigungu: str) -> dict[str, str]:
    """해당 지자체의 {표준 품목명: 구분명}. 같은 품목이 규격별로 여러 줄이어도 한 번만 담는다."""
    items: dict[str, str] = {}
    for row in _rows():
        if row[COL_SIDO].strip() == sido.strip() and row[COL_SIGUNGU].strip() == sigungu.strip():
            items.setdefault(row[COL_ITEM].strip(), (row.get(COL_CATEGORY) or "").strip())
    return items


def match_item(name: str, items: dict[str, str]) -> str | None:
    """AI가 답한 이름을 표준 품목명으로 되돌린다. 목록에 없으면 None.

    1) 띄어쓰기만 다른 이름 ('침대매트리스' -> '침대 매트리스')
    2) (통합하면서 더함) 같은 품목의 다른 표기 ('소파' -> 수수료표의 '쇼파'). 기능②의 이름 정리 규칙을 쓴다.
       후보가 둘 이상이면 어느 것인지 알 수 없으므로 고르지 않는다.
    """
    target = normalize(name)
    for standard_name in items:
        if normalize(standard_name) == target:
            return standard_name
    code = _standard_code(name)
    same = [n for n in items if code and _standard_code(n) == code]
    return same[0] if len(same) == 1 else None


@lru_cache(maxsize=1)
def _matcher():
    from etl.normalize import ItemMatcher  # 기능②의 표준 품목·비슷한 말 사전
    return ItemMatcher()


@lru_cache(maxsize=4096)
def _standard_code(name: str) -> str | None:
    """이름 하나가 가리키는 표준 품목 코드. 여러 품목이 섞인 이름('서랍장 신발장')은 None."""
    m = _matcher().match(name)
    return m.codes[0] if m.method in ("exact", "synonym", "typo") and len(m.codes) == 1 else None


def search_items(sido: str, sigungu: str, query: str) -> list[str]:
    """인식 실패 시 쓰는 직접 검색 (부분 일치)."""
    q = normalize(query)
    if not q:
        return []
    return [name for name in get_items(sido, sigungu) if q in normalize(name)]
