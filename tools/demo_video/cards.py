"""영상용 제목·데이터·마무리 카드 (HTML)."""

BASE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
html{margin:0;height:100%;overflow:hidden}
body{margin:0;zoom:1.6667;width:1152px;height:648px;font-family:'Noto Sans CJK KR','Noto Sans KR',sans-serif;}
body{background:linear-gradient(135deg,#0b3b75 0%,#123f7a 55%,#1d5fbf 100%);color:#fff;display:flex;align-items:center;justify-content:center;}
.box{width:86%;max-width:980px}
.kicker{font-size:22px;letter-spacing:.04em;opacity:.85;margin:0 0 14px}
h1{font-size:46px;line-height:1.25;margin:0 0 18px;font-weight:800}
p.sub{font-size:22px;opacity:.92;margin:0 0 30px;line-height:1.55}
.chips{display:flex;flex-wrap:wrap;gap:12px}
.chip{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:9px 18px;font-size:19px}
.chip b{color:#ffd28a}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:8px}
.stat{background:rgba(255,255,255,.12);border-radius:16px;padding:22px 18px}
.stat .n{font-size:44px;font-weight:800;color:#ffd28a}
.stat .l{font-size:18px;opacity:.9;margin-top:6px;line-height:1.4}
ul{font-size:22px;line-height:1.75;margin:0 0 26px;padding-left:26px}
.src{font-size:16px;opacity:.75;margin-top:18px}
</style></head><body><div class="box">{body}</div></body></html>"""


def intro() -> str:
    return BASE.replace("{body}", """
<p class="kicker">청년 공공AX 서포터즈 · 팀 에이스</p>
<h1>우리동네 대형폐기물<br>AI 수거비용 산정 서비스</h1>
<p class="sub">지역마다 다른 규격 기준에 맞춰 필요한 것만 묻고,<br>근거와 함께 예상 수수료를 알려 드립니다.</p>
<div class="chips">
  <span class="chip"><b>②</b> 지역 기준 맞춤 규격 질문·실측 보정 — 강문정</span>
  <span class="chip"><b>③</b> 수수료 산정·근거 안내 — 정하영</span>
</div>""")


def data_card() -> str:
    return BASE.replace("{body}", """
<p class="kicker">사용한 공공데이터</p>
<h1>전국대형폐기물수거수수료정보 표준데이터</h1>
<div class="grid">
  <div class="stat"><div class="n">23,186</div><div class="l">수수료 행<br>(지자체·품목·규격)</div></div>
  <div class="stat"><div class="n">143</div><div class="l">지자체</div></div>
  <div class="stat"><div class="n">111</div><div class="l">표준 품목으로<br>이름 통일</div></div>
  <div class="stat"><div class="n">576</div><div class="l">같은 규격·다른 금액<br>(확인 필요로 안내)</div></div>
</div>
<p class="src">출처: 공공데이터포털 data.go.kr/data/15114146 · 행정안전부 도로명주소 API · 국가법령정보센터 자치법규</p>""")


def outro() -> str:
    return BASE.replace("{body}", """
<p class="kicker">정리</p>
<h1>필요한 규격만 묻고, 근거와 함께 안내합니다</h1>
<ul>
  <li>지역 수수료표에 실제로 있는 규격만 질문 · 설명 문장과 실측값으로 자동 판정</li>
  <li>금액과 함께 산정 근거 · 다른 규격 비교 · 조례 별표 원문 링크 · 데이터 기준일</li>
  <li>원본 데이터 전 행을 다시 조회해 금액 일치를 자동 테스트로 확인 (테스트 171개)</li>
  <li>금액이 충돌하는 데이터는 임의로 고르지 않고 지자체 확인 안내</li>
</ul>
<div class="chips"><span class="chip">다음 단계: ① 사진 인식 · ④ 배출 전 체크리스트 연동</span></div>
<p class="sub" style="margin-top:34px;font-size:30px;font-weight:700">감사합니다 · 팀 에이스</p>""")
