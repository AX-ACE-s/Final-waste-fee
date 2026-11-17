"""AI 호출부. 사진과 지시문을 보내고 AI가 쓴 글(문자열)을 그대로 돌려준다.

다른 AI API로 바꾸고 싶으면 ask_ai_about_image() 안쪽만 고치면 된다.
"""
import base64
import json
import os

MOCK_ANSWER = json.dumps(
    {
        "recognized": True,
        "candidates": [
            {
                "item": "소파",
                "confidence": "높음",
                "evidence": ["[가짜 응답] 등받이와 양쪽 팔걸이가 보임", "[가짜 응답] 좌석 쿠션이 3칸"],
            },
            {"item": "의자", "confidence": "낮음", "evidence": ["[가짜 응답] 앉는 용도의 가구"]},
        ],
        "observed_features": {"좌석 수": "3인용으로 보임", "재질": "천"},
    },
    ensure_ascii=False,
)


def is_mock() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def ask_ai_about_image(image: bytes, media_type: str, instruction: str) -> str:
    if is_mock():
        return MOCK_ANSWER  # API 키 없이도 화면·연동을 시험할 수 있게 하는 가짜 응답

    import anthropic  # 키가 있을 때만 필요

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수를 자동으로 읽는다
    response = client.messages.create(
        model=os.getenv("AI_MODEL", "claude-sonnet-4-5"),
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image).decode(),
                        },
                    },
                    {"type": "text", "text": instruction},
                ],
            }
        ],
    )
    return "".join(block.text for block in response.content if block.type == "text")
