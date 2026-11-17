"""단가형 규격('…당') 해석 회귀 테스트.

통합 검토에서 찾은 문제: '1인용 당', '폭30센티미터 당', '100ℓ당', '1톤당', '㎡당' 같은 규격(실제 데이터 약 400행, 99개 지자체)을
단가형으로 알아보지 못해 단가를 총액처럼 보여 줬다. ②(etl)와 ③(core/specs)이 같은 해석을 쓰도록 고쳤다.
"""
import pytest

from core.specs import parse_per_unit
from etl.normalize import parse_spec


@pytest.mark.parametrize("raw, amount, unit, kind", [
    ("1인용 당", 1, "인", "seats"),
    ("1인당", 1, "인", "seats"),
    ("폭30센티미터 당", 30, "cm", "length"),
    ("㎡당", 1, "㎡", "area"),
    ("1제곱미터 당", 1, "㎡", "area"),
    ("100ℓ당", 100, "L", "volume"),
    ("50ℓ(1마대)당", 50, "L", "volume"),
    ("1톤당", 1, "톤", "ton"),
    ("kg당", 1, "kg", "weight"),
    ("1쪽당", 1, "쪽", "sections"),
    ("1㎡ 당", 1, "㎡", "area"),
])
def test_per_unit_specs_are_recognized_by_both_modules(raw, amount, unit, kind):
    p = parse_spec(raw)
    assert (p.spec_type, p.per_unit_amount, p.per_unit_unit) == ("per_unit", amount, unit)
    assert parse_per_unit(raw)["kind"] == kind and parse_per_unit(raw)["size"] == amount


@pytest.mark.parametrize("raw", ["1인용(개당)", "개당", "3인용", "가로 120CM 이상", "모든규격"])
def test_not_per_unit(raw):
    assert parse_spec(raw).spec_type != "per_unit"
    assert parse_per_unit(raw) is None


def test_seat_unit_price_is_multiplied():
    """관악구 '소파 1인용 당 3,000원' 같은 요금: 3인용이면 9,000원."""
    from core.fees import FeeTable
    t = FeeTable.from_rows([{"시도명": "서울특별시", "시군구명": "관악구", "대형폐기물명": "소파", "대형폐기물구분명": "가구류",
                   "대형폐기물규격": "1인용 당", "유무료여부": "유료", "수수료": "3000", "데이터기준일자": "2026-01-01"}])
    r = t.calculate("서울특별시 관악구", "소파", spec="1인용 당", measure=3)
    assert r["fee"] == 9000
