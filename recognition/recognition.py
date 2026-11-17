"""핵심 흐름: 품목 목록 준비 → AI에게 질문 → 답을 검증해 결과로 정리."""
import json
import logging

from . import ai_client, catalog
from .schemas import Candidate, RecognitionResult

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 3
CONFIDENCE_LEVELS = ("높음", "중간", "낮음")

INSTRUCTION_TEMPLATE = """\
당신은 주민이 대형폐기물을 신고할 때 품목을 찾도록 돕는 도우미입니다.
사진에서 주민이 버리려는 물건 하나를 찾고, 그 물건이 아래 [품목 목록] 중 무엇에 해당하는지 고르세요.

[품목 목록]
{item_list}

지켜야 할 것:
1. item에는 [품목 목록]에 있는 이름을 글자 그대로 쓰세요. 목록에 없는 이름은 수수료를 조회할 수 없어 쓸모가 없습니다.
2. 후보는 가능성이 높은 순서로 1~{max_candidates}개. 헷갈릴 만한 품목이 있을 때만 여러 개를 내세요.
3. evidence에는 사진에서 실제로 보이는 것만 쓰세요. 주민이 "아, 그래서 이 품목이구나" 하고 확인할 수 있어야 합니다.
4. observed_features에는 크기, 좌석 수, 문 개수, 재질처럼 규격을 정할 때 도움이 될 관찰을 쓰세요. 보이지 않는 것은 쓰지 마세요.
5. 목록에 맞는 품목이 없거나 사진으로 판단할 수 없으면 recognized를 false로 하고 candidates를 비우세요. 억지로 고르는 것보다 낫습니다.

아래 JSON 하나만 출력하세요. 설명 문장이나 코드블록 표시는 붙이지 마세요.
{{"recognized": true, "candidates": [{{"item": "품목명", "confidence": "높음 | 중간 | 낮음", "evidence": ["관찰 1", "관찰 2"]}}], "observed_features": {{"항목": "관찰 내용"}}}}
"""

MSG_NO_DATA = "이 지역의 품목 데이터가 아직 없어요."
MSG_AI_ERROR = "지금은 사진을 분석할 수 없어요. 품목을 직접 검색해 주세요."
MSG_NOT_RECOGNIZED = "사진에서 품목을 찾지 못했어요. 품목을 직접 검색해 주세요."


def build_instruction(items: dict[str, str]) -> str:
    return INSTRUCTION_TEMPLATE.format(item_list=", ".join(items), max_candidates=MAX_CANDIDATES)


def extract_json(text: str) -> dict:
    """AI 답에서 JSON 부분만 꺼낸다. 앞뒤에 다른 글이 섞여 있어도 견딘다."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def validate_candidates(raw_candidates: object, items: dict[str, str]) -> list[Candidate]:
    """목록에 실제로 있는 품목만 남긴다. 이 검증 덕분에 다음 단계의 수수료 조회가 항상 성립한다."""
    if not isinstance(raw_candidates, list):
        return []
    candidates: list[Candidate] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        name = catalog.match_item(str(raw.get("item", "")), items)
        if name is None:
            logger.info("목록에 없는 품목이라 제외: %r", raw.get("item"))
            continue
        if any(c.item == name for c in candidates):
            continue  # 중복 제거
        confidence = raw.get("confidence")
        evidence = raw.get("evidence")
        candidates.append(
            Candidate(
                item=name,
                category=items[name],
                confidence=confidence if confidence in CONFIDENCE_LEVELS else "낮음",
                evidence=[str(e) for e in evidence] if isinstance(evidence, list) else [],
            )
        )
    return candidates[:MAX_CANDIDATES]


def build_result(ai_text: str, sido: str, sigungu: str, items: dict[str, str]) -> RecognitionResult:
    data = extract_json(ai_text)
    candidates = validate_candidates(data.get("candidates"), items)
    recognized = data.get("recognized") is True and len(candidates) > 0
    if not recognized:
        return RecognitionResult(sido=sido, sigungu=sigungu, recognized=False, message=MSG_NOT_RECOGNIZED)

    features = data.get("observed_features")
    return RecognitionResult(
        sido=sido,
        sigungu=sigungu,
        recognized=True,
        candidates=candidates,
        observed_features={str(k): str(v) for k, v in features.items()} if isinstance(features, dict) else {},
        is_appliance=candidates[0].category == catalog.APPLIANCE_CATEGORY,
    )


def recognize(image: bytes, media_type: str, sido: str, sigungu: str) -> RecognitionResult:
    items = catalog.get_items(sido, sigungu)
    if not items:
        return RecognitionResult(sido=sido, sigungu=sigungu, recognized=False, message=MSG_NO_DATA)
    try:
        ai_text = ai_client.ask_ai_about_image(image, media_type, build_instruction(items))
    except Exception:
        # AI 서비스 장애여도 주민은 직접 검색으로 계속 진행할 수 있어야 한다.
        logger.exception("AI 호출 실패")
        return RecognitionResult(sido=sido, sigungu=sigungu, recognized=False, message=MSG_AI_ERROR)
    return build_result(ai_text, sido, sigungu, items)
