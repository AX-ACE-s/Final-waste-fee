"""이 기능이 내보내는 결과 형식.

다음 기능(규격 질문, 무상수거 안내, 화면)이 이 형식을 그대로 받아 쓰므로
필드를 바꿀 때는 반드시 팀에 먼저 알릴 것.
"""
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["높음", "중간", "낮음"]


class Candidate(BaseModel):
    """AI가 제시한 품목 후보 하나."""

    item: str = Field(description="수수료표에 실제로 있는 표준 품목명")
    category: str = Field(default="", description="수수료표의 구분명 (예: 가구, 가전)")
    confidence: Confidence = Field(description="AI가 스스로 밝힌 확신 정도")
    evidence: list[str] = Field(description="사진에서 관찰한 판단 근거")


class RecognitionResult(BaseModel):
    """POST /recognize 응답."""

    sido: str
    sigungu: str
    recognized: bool = Field(description="False면 화면은 '품목 직접 검색'으로 이동")
    candidates: list[Candidate] = Field(default_factory=list, description="가능성 높은 순")
    observed_features: dict[str, str] = Field(
        default_factory=dict,
        description="규격 질문 기능에 넘기는 힌트 (예: {'좌석 수': '3인용으로 보임'})",
    )
    is_appliance: bool = Field(
        default=False, description="1순위 후보가 가전이면 True → 무상수거 안내로 연결"
    )
    message: str = Field(default="", description="실패했을 때 사용자에게 보여줄 안내")
