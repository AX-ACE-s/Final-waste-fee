"""시연 영상 녹화 (자막 방식, 음성 없음).

실제 화면을 브라우저로 자동 조작하며 녹화하고, 화면 아래에 자막을 띄운 채 mp4로 저장한다.
.env 에 ANTHROPIC_API_KEY / JUSO_API_KEY 를 넣고 서버를 켜 두면 실제 AI 사진 인식과 도로명주소 검색이 영상에 나온다.
키 값은 화면에 나오지 않는다.

준비 (한 번만)
  pip install playwright
  python -m playwright install chromium
  ffmpeg 설치 (mp4 변환용. 없으면 .webm 으로 남는다)

실행
  python app.py                                   # 다른 창에서 서버 켜 두기
  python tools/demo_video/record.py               # -> tools/demo_video/demo.mp4
  python tools/demo_video/record.py --photo 내소파사진.jpg   # 실제 AI 인식을 보여 줄 사진 (기본: 그림 sample_sofa.jpg)

영상 흐름 (약 4분 30초): 표지 → 지역 선택 → ① 사진 인식 → ② 규격 질문 → ③ 수수료·근거·담기
 → ② 설명 읽기('3인용 쇼파 2개') → ② 실측 보정(장롱 150cm) → ④ 체크리스트 → 상단바로 돌아오기 → 마무리
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
W, H = 1280, 720
SLOW = 1.3  # 자막을 읽을 시간 배율

CAPTION_JS = """
() => {
  if (document.getElementById('__cap')) return;
  const c = document.createElement('div'); c.id = '__cap';
  c.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1100px;background:rgba(20,28,25,.86);color:#fff;font:600 22px/1.45 "Pretendard","Noto Sans CJK KR","Noto Sans KR","Malgun Gothic",sans-serif;padding:12px 22px;border-radius:12px;z-index:99999;text-align:center;pointer-events:none;white-space:pre-line;display:none';
  const k = document.createElement('div'); k.id = '__cur';
  k.style.cssText = 'position:fixed;width:22px;height:22px;border-radius:50%;background:rgba(230,60,40,.55);border:2px solid #fff;z-index:99998;pointer-events:none;transform:translate(-50%,-50%);left:-40px;top:-40px';
  document.documentElement.append(c, k);
  addEventListener('mousemove', (e) => { k.style.left = e.clientX + 'px'; k.style.top = e.clientY + 'px'; }, true);
}
"""

CARD = """<html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#fff;
font-family:'Pretendard','Noto Sans CJK KR','Malgun Gothic',sans-serif;color:#111">{body}</body></html>"""

COVER = CARD.format(body="""<div style="text-align:center"><div style="color:#1f6f5c;font-weight:800;font-size:22px">청년공공AX서포터즈 · 팀 에이스</div>
<h1 style="font-size:46px;margin:14px 0 26px">우리동네 대형폐기물 AI 수거비용 안내</h1>
<div style="display:grid;grid-template-columns:repeat(2,330px);gap:12px;font-size:21px;text-align:left">
<div style="background:#F6F6F6;border-radius:16px;padding:14px 18px">① 사진 기반 품목 인식</div>
<div style="background:#F6F6F6;border-radius:16px;padding:14px 18px">② 지역 기준 규격 질문·실측 보정</div>
<div style="background:#F6F6F6;border-radius:16px;padding:14px 18px">③ 수수료 산정·근거 안내</div>
<div style="background:#F6F6F6;border-radius:16px;padding:14px 18px">④ 배출 전 체크리스트·신청 연결</div></div>
<p style="color:#6E6E6E;font-size:18px;margin-top:26px">공공데이터포털 전국대형폐기물수거수수료정보표준데이터 기준</p></div>""")

OUTRO = CARD.format(body="""<div style="text-align:center;font-size:24px;line-height:1.8"><h1 style="font-size:40px;color:#1f6f5c">정리</h1>
사진·이름으로 품목 확인 → 지역 수수료표에 필요한 규격만 질문 → 공공데이터 기준 수수료와 근거 → 배출 전 체크리스트·신청 연결<br>
<span style="color:#6E6E6E;font-size:20px">확인되지 않은 규격·금액은 지어내지 않고 지자체 확인을 안내합니다.</span><br><br>
<b>청년공공AX서포터즈 · 팀 에이스</b></div>""")


def get_json(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as res:
        return json.load(res)


def main() -> None:
    ap = argparse.ArgumentParser(description="시연 영상 녹화 (자막 방식)")
    ap.add_argument("--base", default="http://127.0.0.1:5000", help="서버 주소")
    ap.add_argument("--photo", default=str(HERE / "sample_sofa.jpg"), help="사진 인식에 쓸 소파 사진")
    ap.add_argument("--out", default=str(HERE / "demo.mp4"))
    args = ap.parse_args()
    base = args.base.rstrip("/")

    try:
        health, status = get_json(base, "/api/health"), get_json(base, "/status")
    except OSError:
        raise SystemExit(f"서버에 연결할 수 없습니다. 먼저 python app.py 로 서버를 켜 주세요. ({base})")
    mock = status.get("mock_mode", True)
    juso = health.get("juso_api", False)

    work = HERE / "work"
    shutil.rmtree(work, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(work),
                                  record_video_size={"width": W, "height": H})
        p = ctx.new_page()

        def sleep(ms: float) -> None:
            time.sleep(ms / 1000)

        def cap(text: str, ms: float = 0) -> None:
            p.evaluate(CAPTION_JS)
            p.evaluate("""(t) => { const c = document.getElementById('__cap'); c.textContent = t; c.style.display = t ? 'block' : 'none'; }""", text)
            if ms:
                sleep(ms * SLOW)

        def move(sel: str):
            el = p.wait_for_selector(sel, state="visible")
            el.scroll_into_view_if_needed()
            b = el.bounding_box()
            p.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=18)
            sleep(250)
            return el

        def click(sel: str, ms: float = 900) -> None:
            move(sel)
            p.click(sel)
            sleep(ms)

        def click_el(el, ms: float = 1500) -> None:
            b = el.bounding_box()
            p.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=15)
            sleep(250)
            el.click()
            sleep(ms)

        def type_(sel: str, text: str, ms: float = 600) -> None:
            move(sel)
            p.click(sel)
            p.fill(sel, "")
            p.type(sel, text, delay=110)
            sleep(ms)

        def scroll(y: int, ms: float = 1200) -> None:
            p.evaluate("(y) => window.scrollTo({ top: y, behavior: 'smooth' })", y)
            sleep(ms)

        def answer_until_confirmed(value: str, prefer: str = "") -> None:
            """규격이 확정될 때까지 답한다: 선택지면 prefer 가 들어간 것(없으면 첫 번째), 숫자면 value."""
            for _ in range(5):
                if p.query_selector("#qBox .chosen"):
                    return
                if p.query_selector("#measure"):
                    type_("#measure", value)
                    click("#measureGo", 2200)
                    continue
                chips = p.query_selector_all("#qBox .chip")
                if not chips:
                    return
                pick = (p.query_selector(f'#qBox .chip:has-text("{prefer}")') if prefer else None) or chips[0]
                click_el(pick, 2000)

        # 0. 표지
        p.set_content(COVER)
        sleep(7000)

        # 1. 지역
        p.goto(base + "/")
        p.wait_for_selector("#sido option:nth-child(3)", state="attached")
        cap("첫 화면: 버릴 물건의 배출 지역과 사진(또는 이름)으로 시작합니다.\n화면은 품목 확인 → 규격 확인 → 수수료·배출 안내 3단계로 이어집니다.", 6500)
        if juso:
            cap("배출 지역은 도로명주소로 찾을 수 있습니다. 주소를 넣으면 관할 지자체를 찾아 줍니다.", 1500)
            type_("#addr", "강서구청")
            click("#addrBtn", 2500)
            first = p.query_selector(".addr-list li:not(.no)")
            if first:
                click_el(first, 1500)
        if not p.query_selector("#regionChosen:not([hidden])"):
            cap("배출 지역은 시·도/시·군·구에서 고르거나, 주소·동네 이름으로 찾을 수 있습니다.", 1500)
            type_("#addr", "강서구")
            click("#addrBtn", 1200)
            click(".addr-list li >> text=서울특별시 강서구", 1200)
        cap("강서구를 고르면 이제부터 강서구 수수료표 기준으로만 안내합니다.", 4500)

        # 2. ① 사진 인식
        cap("① 사진 기반 품목 인식: 버릴 물건 사진을 올립니다."
            + ("\n(지금은 AI 키를 넣지 않아 연습용 응답으로 동작합니다)" if mock else ""), 3000)
        move(".dropzone")
        p.set_input_files("#photoFile", args.photo)
        sleep(2500)
        click("text=이 사진으로 품목 찾기", 1000)
        p.wait_for_selector("#itemNext", timeout=60000)
        sleep(1500)
        cap("AI는 강서구 수수료표에 실제로 있는 품목 중에서만 후보를 고르고,\n그렇게 판단한 근거(사진에서 본 것)를 함께 보여 줍니다.", 7000)
        cap("후보가 틀리면 아래에서 이름으로 검색하거나 지역 품목 목록에서 직접 고를 수 있습니다.", 5000)
        if not p.query_selector('input[name="item"]:checked'):  # AI가 못 찾았으면 이름으로
            type_("#search", "소파")
            click("#searchBtn", 2000)
        click("#itemNext", 2000)

        # 3. ② 규격 질문
        cap("② 지역 기준 규격 질문: 강서구 수수료표에서 금액을 가르는 규격만 묻습니다.\n왼쪽에는 AI가 사진에서 본 특징이 참고로 표시됩니다.", 7500)
        answer_until_confirmed("3", prefer="3인")
        cap("규격이 확정되었습니다. 원하면 실측값을 넣어 고른 규격이 맞는지 확인할 수도 있습니다.", 5500)
        click("#toResult", 2500)

        # 4. ③ 수수료
        cap("③ 수수료 산정·근거 안내: 공공데이터 기준 예상 수수료를 바로 보여 줍니다.\n지역·품목·규격·데이터 기준일·출처가 한 줄로 함께 표시됩니다.", 7500)
        click("#more summary", 1500)
        cap("「산정 근거 자세히 보기」를 열면 규격 결정 방식, 제공기관,\n다른 규격과의 금액 비교, 조례 원문 링크까지 확인할 수 있습니다.", 4000)
        scroll(380, 4500)
        scroll(0, 1200)
        click("#addCart", 1500)
        cap("「목록에 담기」로 여러 품목을 담아 합계를 낼 수 있습니다. 근거 복사로 신고할 때 붙여 넣을 수도 있습니다.", 5500)

        # 5. ② 설명 읽기
        cap("다른 물건도 확인해 봅니다. 사진이 없으면 이름이나 설명으로 찾습니다.", 2000)
        click("#startOver", 1800)
        type_("#itemName", "3인용 쇼파 2개", 400)
        click("#nameBtn", 2500)
        cap('② 설명 읽기: "쇼파"처럼 다르게 써도 표준 품목(소파)을 찾고,\n"3인용", "2개"를 읽어 규격 질문에 미리 반영합니다.', 7000)
        click("#itemNext", 2500)
        answer_until_confirmed("3", prefer="3인")
        cap("설명에서 3인용을 읽었기 때문에 질문 없이 바로 규격이 확정되었습니다. 개수도 2개로 들어갔습니다.", 6000)
        click("#toResult", 2500)
        cap("2개 기준 합계와 개당 금액이 표시됩니다.", 4500)
        click("#addCart", 1500)
        cap("담은 품목의 합계가 갱신됩니다.", 4000)

        # 6. ② 실측 보정
        click("#startOver", 1500)
        type_("#itemName", "장롱", 400)
        click("#nameBtn", 2500)
        click("#itemNext", 2500)
        cap("② 실측 보정: 장롱처럼 크기로 금액이 갈리는 품목은 줄자로 잰 값을 묻습니다.\ncm/m 단위를 바꿔 넣을 수 있고, 값이 속한 규격 구간을 자동으로 판정합니다.", 7500)
        answer_until_confirmed("150")
        cap("입력한 실측값이 화면에 남고, 그 값으로 확정된 규격을 보여 줍니다.", 5000)
        click("#toResult", 2500)
        cap("경계값에 가까우면 주의 문구를 띄우고, 금액이 확인되지 않은 경우 임의로 계산하지 않습니다.", 5500)

        # 7. ④ 체크리스트
        scroll(0, 600)
        move("#toChecklist")
        cap("④ 배출 전 체크리스트·신청 연결: 결과 화면에서 품목에 맞춘 체크리스트 페이지로 이동합니다.", 3500)
        click("#toChecklist", 500)
        p.wait_for_selector(".cards")
        cap("강서구 · 장롱 기준으로 신고 전 / 물건 준비 / 내놓기 3단계 확인 항목이 나옵니다.\n사는 곳(주택·아파트)에 따라 내놓는 장소 안내가 달라집니다.", 6000)
        scroll(520, 1500)
        for box in p.query_selector_all(".check input")[:4]:
            b = box.bounding_box()
            if b:
                p.mouse.move(b["x"] + 12, b["y"] + 12, steps=12)
                box.click()
                sleep(700)
        cap("항목을 확인할 때마다 남은 개수가 줄고, 마지막에 구청 신청 페이지로 연결합니다.", 3000)
        scroll(99999, 4500)
        scroll(0, 1200)
        cap("위쪽 상단바로 「수수료 확인」과 「배출 전 체크리스트」 두 페이지를 오갈 수 있습니다.", 1800)
        click("#feeLink", 2500)
        cap("수수료 확인으로 돌아오면 보던 결과와 담은 품목이 그대로 남아 있습니다.", 5500)

        # 8. 마무리
        p.set_content(OUTRO)
        sleep(7000)
        video = p.video.path()
        ctx.close()
        browser.close()

    out = Path(args.out)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(out)], check=True)
        print(f"완료: {out}")
    else:
        webm = out.with_suffix(".webm")
        shutil.copy(video, webm)
        print(f"ffmpeg 가 없어 webm 으로 저장했습니다: {webm}")


if __name__ == "__main__":
    main()
