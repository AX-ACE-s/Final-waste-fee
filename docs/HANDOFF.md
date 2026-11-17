# ② → ③ 인계 규격 (규격 확정 → 수수료 산정·근거 안내)

② 지역 기준 맞춤 규격 질문·실측 보정은 **규격 하나가 확정될 때까지**를 맡는다.
확정되면 `POST /api/estimate` 응답의 `result.handoff`로 아래 값을 넘긴다.
③ 수수료 산정 및 근거 안내는 이 값만 받아서 금액 산정·근거 표시·조례 대조를 하면 된다.

```json
"handoff": {
  "region_id": 87,               // DB region.id
  "sido": "서울특별시",
  "sigungu": "강남구",
  "standard_code": "SOFA",        // 표준 품목 코드 (①에서 넘어온 코드와 같은 체계)
  "standard_item": "소파",
  "local_item_id": 10233,         // 지자체 품목 (원문명 아래)
  "local_item": "쇼파",
  "spec_id": 10240,               // 확정된 규격 = DB item_specification.id → disposal_fee 한 행과 1:1
  "spec": "3인용",                // 원문 규격
  "units": 1,                     // 단위당 요금 품목(1㎡당 등)이면 단위 수, 아니면 1
  "quantity": 2                   // 같은 물건 개수
}
```

## ③에서 금액·근거를 꺼내는 쿼리

```sql
SELECT f.fee, f.is_free, f.base_date, d.name AS dataset, d.url, rg.manager_org
FROM disposal_fee f
JOIN item_specification s ON s.id = f.spec_id
JOIN local_item li ON li.id = s.local_item_id
JOIN region rg ON rg.id = li.region_id
JOIN data_source d ON d.id = f.source_id
WHERE f.spec_id = :spec_id;
```

예상 수수료 = `fee × units × quantity` (무료면 0)

## 지금 코드에서 ③에 해당하는 부분 (교체 가능)

- `app/services/engine.py` → `_result()` : 금액 계산, 산정 근거 목록, 출처 블록
- `app/static/app.js` → `showResult()` : 4단계 결과 화면

③ 담당자가 따로 만든 코드가 있으면 이 두 곳을 교체하고, 없으면 그대로 쓰면서 조례(자치법규) 대조만 추가하면 된다.
`status: "needs_confirmation"`(같은 규격에 금액이 둘 이상)일 때는 handoff 대신 `candidates`가 온다.
