"""시연 영상 대본과 화면 조작.

각 장면: badge(왼쪽 위 표시), lines[(자막, 음성용 문장 또는 None)], act(c) 화면 조작.
c.at(i) 는 i번째 문장이 시작될 때까지 기다린다 → 말과 화면을 맞춘다.
"""
import cards

APP = "http://127.0.0.1:5000/"


async def intro(c):
    await c.card(cards.intro())


async def data(c):
    await c.card(cards.data_card())


async def region(c):
    await c.goto(APP)
    await c.badge("② 지역 선택")
    await c.at(1)
    await c.type("#addr", "강남구")
    await c.click("#addrBtn")
    await c.wait(900)
    await c.at(2)
    await c.click("#addrList li[data-i='0']")
    await c.hl("#sido", "#sigungu", "#regionInfo")


async def describe(c):
    await c.badge("② 설명 읽기")
    await c.scroll("#itemQ", offset=-140)
    await c.at(1)
    await c.type("#itemQ", "3인용 쇼파 2개")
    await c.wait(1300)
    await c.at(2)
    await c.hl("#descInfo", "#itemList .chip.on", "#qty")
    await c.at(3)
    await c.click("#start")
    await c.wait(900)
    await c.hl("#confirmTrail")


async def result(c):
    await c.badge("③ 수수료·근거")
    await c.click("#toResult")
    await c.wait(700)
    await c.hl("#resultBox .fee")
    await c.at(1)
    await c.scroll("#resultBox .explain", offset=-170)
    await c.hl("#resultBox .explain")
    await c.at(2)
    await c.scroll("#resultBox table.alt", offset=-200)
    await c.hl("#resultBox table.alt")
    await c.at(3)
    await c.scroll("#resultBox h3:has-text('조례 별표')", offset=-140)
    await c.hl("#resultBox h3:has-text('조례 별표') + ul")
    await c.wait(1800)
    await c.scroll("#resultBox .src", offset=-260)
    await c.hl("#resultBox .src")
    await c.at(4)
    await c.click("#addCart")
    await c.wait(600)


async def question(c):
    await c.badge("② 규격 질문")
    await c.click("#again")
    await c.wait(500)
    await c.fill("#qty", "1")
    await c.scroll("#itemQ", offset=-200)
    await c.clear("#itemQ")
    await c.type("#itemQ", "냉장고")
    await c.wait(1100)
    await c.click("#start")
    await c.wait(700)
    await c.at(1)
    await c.hl("#qBox .opts")
    await c.at(2)
    await c.click("#qBox .opt:has-text('일반 냉장고')")
    await c.wait(700)
    await c.hl("#qBox .q-label")
    await c.at(3)
    await c.type("#numIn", "450")
    await c.click("#numOk")
    await c.wait(900)
    await c.click("#toResult")
    await c.wait(700)
    await c.hl("#resultBox .fee", "#resultBox dl.kv")
    await c.click("#addCart", quick=True)


async def measure(c):
    await c.badge("② 실측 보정")
    await c.click("#again")
    await c.wait(500)
    await c.fill("#qty", "1")
    await c.scroll("#itemQ", offset=-200)
    await c.clear("#itemQ")
    await c.type("#itemQ", "장롱")
    await c.wait(1100)
    await c.click("#start")
    await c.wait(800)
    await c.at(1)
    await c.type("#numIn", "1.3")
    await c.click("#numOk")
    await c.wait(700)
    await c.hl("#qBox .err")
    await c.at(2)
    await c.scroll("#qBox .fallback", offset=-200)
    await c.click("#qBox .fallback .opt:has-text('100cm 미만')")
    await c.wait(800)
    await c.at(3)
    await c.type("#verifyBox input[data-dim]", "130")
    await c.click("#verifyBtn")
    await c.wait(900)
    await c.hl("#verifyBox .warn")
    await c.at(4)
    await c.click("#applyFix")
    await c.wait(800)
    await c.click("#toResult")
    await c.wait(700)
    await c.hl("#resultBox .fee", "#resultBox dl.kv")
    await c.click("#addCart", quick=True)


async def total(c):
    await c.badge("③ 여러 품목 합계")
    await c.scroll("#cartCard", offset=-120)
    await c.hl("#cartCard")


async def conflict(c):
    await c.badge("③ 데이터 충돌 처리")
    await c.click("#again")
    await c.wait(500)
    await c.scroll("#sido", offset=-200)
    await c.select("#sido", "부산광역시")
    await c.select("#sigungu", "남구")
    await c.fill("#qty", "1")
    await c.at(1)
    await c.clear("#itemQ")
    await c.type("#itemQ", "라텍스 매트리스 1인용")
    await c.wait(1100)
    await c.click("#start")
    await c.wait(900)
    await c.at(2)
    await c.click("#toResult")
    await c.wait(700)
    await c.hl("#resultBox .warn", "#resultBox .fee", "#resultBox .conflict")


async def outro(c):
    await c.badge("")
    await c.card(cards.outro())


SCENES = [
    dict(id="intro", act=intro, lines=[
        ("안녕하세요. 팀 에이스의 우리동네 대형폐기물 수거비용 산정 서비스 시연입니다.", None),
        ("대형폐기물 수수료는 지자체마다 품목 이름과 규격 기준이 달라서 주민이 직접 판단하기 어렵고, "
         "잘못 신고하면 미수거나 차액 징수로 이어집니다.", None),
        ("이번 영상에서는 지역 기준 맞춤 규격 질문과, 수수료 산정 및 근거 안내 기능을 보여 드리겠습니다.", None),
    ]),
    dict(id="data", act=data, lines=[
        ("데이터는 공공데이터포털의 전국 대형폐기물 수수료 표준데이터 23,186건, 143개 지자체를 정제해 사용했습니다.",
         "데이터는 공공데이터포털의 전국 대형폐기물 수수료 표준데이터 약 이만 삼천 건, 백사십삼 개 지자체 자료를 정제해 사용했습니다."),
        ("지역마다 다른 품목 이름은 111개 표준 품목으로 통일했습니다.",
         "지역마다 다른 품목 이름은 백십일 개 표준 품목으로 통일했습니다."),
    ]),
    dict(id="region", act=region, lines=[
        ("먼저 배출 지역을 고릅니다.", None),
        ("주소 검색창에 강남구를 입력하면, 데이터에 있는 지역을 바로 찾아 줍니다.", None),
        ("선택하면 시·도와 시·군·구, 관리기관이 함께 채워집니다.", "선택하면 시도와 시군구, 관리기관이 함께 채워집니다."),
    ]),
    dict(id="describe", act=describe, lines=[
        ("버릴 물건은 이름만 써도 되고, 크기나 개수를 넣은 설명으로 써도 됩니다.", None),
        ("'3인용 쇼파 2개'라고 입력해 보겠습니다.", "삼인용 쇼파 두 개라고 입력해 보겠습니다."),
        ("'쇼파'라는 표기를 표준 품목인 소파로 연결하고, 3인용과 2개라는 정보를 읽어 냅니다.",
         "쇼파라는 표기를 표준 품목인 소파로 연결하고, 삼인용과 두 개라는 정보를 읽어 냅니다."),
        ("설명에서 규격을 이미 읽었기 때문에, 추가 질문 없이 확인 단계로 넘어갑니다.", None),
    ]),
    dict(id="result", act=result, lines=[
        ("결과입니다. 강남구 소파 3인용은 개당 7,000원, 2개라서 14,000원입니다.",
         "결과입니다. 강남구 소파 삼인용은 개당 칠천 원, 두 개라서 만 사천 원입니다."),
        ("왜 이 규격과 금액인지 설명하는 문장과, 데이터 기준일과 관리기관이 함께 나옵니다.", None),
        ("다른 규격과의 금액 차이도 비교해 주어, 잘못 신고하면 얼마나 달라지는지 알 수 있습니다.", None),
        ("아래에는 강남구 조례의 수수료 별표 원문 링크와 데이터 출처가 이어집니다.", None),
        ("이 품목은 합계를 위해 목록에 담아 두겠습니다.", None),
    ]),
    dict(id="question", act=question, lines=[
        ("이번에는 크기 없이 '냉장고'만 입력해 보겠습니다. 크기를 모를 때는 질문으로 규격을 확정합니다.",
         "이번에는 크기 없이 냉장고만 입력해 보겠습니다. 크기를 모를 때는 질문으로 규격을 확정합니다."),
        ("강남구 수수료표는 냉장고를 일반형과 양문형으로 나누기 때문에, 먼저 종류를 묻습니다.", None),
        ("일반형은 용량으로 요금이 나뉘어서 용량만 추가로 묻습니다. 수수료표에 없는 항목은 묻지 않습니다.", None),
        ("450리터를 넣으면 300리터 이상 규격으로 자동 판정되어 6,000원이 나옵니다.",
         "사백오십 리터를 넣으면, 삼백 리터 이상 규격으로 자동 판정되어 육천 원이 나옵니다."),
    ]),
    dict(id="measure", act=measure, lines=[
        ("다음은 장롱입니다. 강남구는 장롱을 크기로만 나누기 때문에, 줄자로 잰 크기를 묻습니다.", None),
        ("1.3처럼 미터 단위로 잘못 넣으면, 혹시 130센티미터인지 다시 확인해 줍니다.",
         "일 점 삼처럼 미터 단위로 잘못 넣으면, 혹시 백삼십 센티미터인지 다시 확인해 줍니다."),
        ("크기를 잘 모를 때는 공식 규격 중에서 고를 수도 있습니다. 이번엔 '100cm 미만'을 골라 보겠습니다.",
         "크기를 잘 모를 때는 공식 규격 중에서 고를 수도 있습니다. 이번엔 백 센티미터 미만을 골라 보겠습니다."),
        ("확인 단계에서 실측값 130cm를 넣으면, 고른 규격과 맞지 않는다고 알려 주고 맞는 규격을 제안합니다.",
         "확인 단계에서 실측값 백삼십 센티미터를 넣으면, 고른 규격과 맞지 않는다고 알려 주고 맞는 규격을 제안합니다."),
        ("제안을 누르면 '100cm 이상' 규격, 15,000원으로 바로잡힙니다.",
         "제안을 누르면 백 센티미터 이상 규격, 만 오천 원으로 바로잡힙니다."),
    ]),
    dict(id="total", act=total, lines=[
        ("담아 둔 소파 2개와 냉장고, 장롱의 예상 합계는 35,000원입니다.",
         "담아 둔 소파 두 개와 냉장고, 장롱의 예상 합계는 삼만 오천 원입니다."),
        ("같은 지역 안에서 여러 품목을 한 번에 계산할 수 있습니다.", None),
    ]),
    dict(id="conflict", act=conflict, lines=[
        ("공공데이터에는 같은 규격에 금액이 두 개씩 등록된 경우가 576건 있습니다.",
         "공공데이터에는 같은 규격에 금액이 두 개씩 등록된 경우가 오백칠십육 건 있습니다."),
        ("부산 남구의 라텍스 매트리스 1인용이 그런 경우입니다.", "부산 남구의 라텍스 매트리스 일인용이 그런 경우입니다."),
        ("이때는 금액을 임의로 고르지 않고, 등록된 금액을 모두 보여 주며 지자체 확인을 안내합니다.", None),
    ]),
    dict(id="outro", act=outro, lines=[
        ("정리하면, 지역마다 다른 규격 기준에 맞춰 필요한 것만 묻고, 확정된 규격으로 수수료와 근거를 함께 안내합니다.", None),
        ("원본 데이터의 모든 행을 다시 조회해 금액이 일치하는지 자동 테스트로 확인했습니다.", None),
        ("사진 인식과 배출 전 체크리스트 기능은 이어서 연동할 예정입니다. 감사합니다.", None),
    ]),
]
