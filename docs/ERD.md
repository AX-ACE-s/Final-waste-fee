# 데이터베이스 ERD

```mermaid
erDiagram
    data_source ||--o{ disposal_fee : "출처"
    data_source ||--o{ data_quality_log : "품질 기록"
    region ||--o{ local_item : "지자체 품목"
    local_item ||--o{ item_mapping : ""
    standard_item ||--o{ item_mapping : ""
    local_item ||--o{ item_specification : "규격"
    item_specification ||--|| disposal_fee : "수수료"

    data_source {
        int id PK
        text kind "standard_data | standard_data_preview | manual_ordinance"
        text name
        text url
        text file_name
        text ingested_at
        int row_count
    }
    region {
        int id PK
        text sido "시도명"
        text sigungu "시군구명"
        text manager_org "관리기관명"
    }
    standard_item {
        int id PK
        text code UK "SOFA, MATTRESS ..."
        text name
        text category
    }
    local_item {
        int id PK
        int region_id FK
        text raw_name "대형폐기물명(원문)"
        text normalized_name
        text category_raw "대형폐기물구분명"
    }
    item_mapping {
        int local_item_id PK,FK
        int standard_item_id PK,FK
        text method "exact | synonym | typo | split"
    }
    item_specification {
        int id PK
        int local_item_id FK
        text raw_spec "대형폐기물규격(원문)"
        text spec_type "all | range | categorical | per_unit"
        text qualifier "종류·재질 등 수식어"
        text ranges_json "[{dim,unit,min,min_inc,max,max_inc}]"
        real per_unit_amount
        text per_unit_unit
        text anomalies_json
    }
    disposal_fee {
        int id PK
        int spec_id FK
        int fee "수수료"
        int is_free "유무료여부"
        text base_date "데이터기준일자"
        int source_id FK
        int source_row
        text ordinance_name
        text ordinance_url
    }
    data_quality_log {
        int id PK
        int source_id FK
        int row_no
        text level "error | warn"
        text issue
        text detail
    }
```

## 설계 메모

- **원문 보존**: `raw_name`, `raw_spec`은 원본 그대로 저장하고 해석 결과(`normalized_name`, `ranges_json`)는 별도 컬럼에 둔다. 결과 화면에는 항상 원문 규격을 보여준다.
- **지역 품목 ↔ 표준 품목은 다대다**: 해운대구 `서랍장 신발장` 한 줄이 표준 품목 `서랍장`, `신발장` 둘 다에 연결된다. 반대로 부여군 `장식장`, `진열장`은 같은 표준 품목 하나에 연결되어 화면에서 먼저 어느 쪽인지 묻는다.
- **ItemSpecification 1 : DisposalFee 1**: 원본 한 행 = 규격 1개 + 수수료 1개. 같은 규격 문구에 수수료가 2개 있는 '충돌'은 행을 합치지 않고 그대로 두고, 엔진이 '확인 필요'로 처리한다.
- **질문 항목은 저장하지 않고 규격에서 계산**: 지시서의 `ItemSpecification(품목별 규격 및 질문 항목)`은 `ranges_json`·`qualifier`·`spec_type`으로 대체했다. 질문을 따로 저장하면 데이터 갱신 때 질문과 규격이 어긋날 수 있어서, 매 요청마다 그 지역의 실제 규격으로 질문을 만든다.
