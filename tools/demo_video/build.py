"""시연 영상 만들기: 대본 → 음성(TTS) → 화면 자동 녹화 → 음성·자막 합성.

python3 build.py tts      # 문장별 음성 생성 + 음성인식으로 발음 검증
python3 build.py record   # 앱(127.0.0.1:5000)을 자동 조작하며 녹화
python3 build.py mux      # 녹화 + 음성 + 자막 → demo.mp4
"""
import asyncio, hashlib, json, sys, time
from pathlib import Path

import numpy as np
import soundfile as sf

import script

HERE = Path(__file__).parent
WORK = HERE / "work"
AUD = WORK / "audio"
GAP = 0.35          # 문장 사이 쉼(초)
TAIL = 0.9          # 장면 끝 여유(초)
W, H = 1920, 1080   # 브라우저 화면(= 영상) 크기
Z = 1920 / 1152     # 앱 내용 확대 배율 (1152x648 화면처럼 보이게)
OUT_W, OUT_H = 1920, 1080
SR = 44100


def lines():
    for si, s in enumerate(script.SCENES):
        for li, (sub, say) in enumerate(s["lines"]):
            yield si, li, sub, (say or sub)


def wav_path(text):
    return AUD / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".wav")


# ---------------------------------------------------------------- TTS
def do_tts():
    import tts, asr, re
    AUD.mkdir(parents=True, exist_ok=True)
    report = []
    for si, li, sub, say in lines():
        p = wav_path(say)
        if not p.exists():
            tts.say(say, str(p), sid=5, speed=1.0, steps=24)
        heard = asr.transcribe(str(p))
        import difflib
        han = lambda t: re.sub(r"[^가-힣]", "", t)
        score = difflib.SequenceMatcher(None, han(say), han(heard)).ratio()
        report.append((script.SCENES[si]["id"], li, score >= 0.86, say, f"{heard}  ({score:.2f})"))
    total = sum(sf.info(str(wav_path(say))).duration for *_, say in lines())
    bad = [r for r in report if not r[2]]
    for sid, li, ok, say, heard in bad:
        print(f"[다름] {sid}#{li}\n  원문: {say}\n  인식: {heard}")
    print(f"문장 {len(report)}개, 음성 합계 {total:.1f}s, 인식 불일치 {len(bad)}개")


def timing():
    """장면별 문장 시작 시각(장면 시작 기준)과 장면 길이"""
    out = []
    for s in script.SCENES:
        t, starts = 0.0, []
        for sub, say in s["lines"]:
            starts.append(t)
            t += sf.info(str(wav_path(say or sub))).duration + GAP
        out.append({"starts": starts, "length": t - GAP + TAIL,
                    "durs": [sf.info(str(wav_path(say or sub))).duration for sub, say in s["lines"]]})
    return out


# ---------------------------------------------------------------- 녹화
OVERLAY = r"""
window.__ov = () => {
  if (document.getElementById('__cur')) return;
  if (location.protocol.startsWith('http')) document.body.style.zoom = String(1920 / 1152);
  const root = document.documentElement;
  const st = document.createElement('style');
  st.textContent = `
  #__cur{position:fixed;left:var(--x,-60px);top:var(--y,-60px);width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;
    background:rgba(255,120,0,.30);border:5px solid #ff7800;z-index:2147483647;pointer-events:none;
    transition:left .6s cubic-bezier(.3,.7,.3,1),top .6s cubic-bezier(.3,.7,.3,1)}
  .__ring{position:fixed;width:36px;height:36px;margin:-18px 0 0 -18px;border-radius:50%;border:5px solid #ff7800;
    z-index:2147483646;pointer-events:none;animation:__r .6s ease-out forwards}
  @keyframes __r{to{transform:scale(3);opacity:0}}
  #__badge{position:fixed;top:24px;left:24px;z-index:2147483647;background:#ff7800;color:#fff;
    font:700 30px 'Noto Sans CJK KR',sans-serif;padding:12px 28px;border-radius:999px;box-shadow:0 2px 8px rgba(0,0,0,.25);pointer-events:none}
  #__badge:empty{display:none}
  .__hl{outline:4px solid #ff7800 !important;outline-offset:3px;border-radius:6px;transition:outline-color .3s}`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id = '__cur'; root.appendChild(c);
  const b = document.createElement('div'); b.id = '__badge'; root.appendChild(b);
};
window.__move = (x, y) => { window.__ov(); const c = document.getElementById('__cur'); c.style.left = x + 'px'; c.style.top = y + 'px'; };
window.__ring = (x, y) => { const r = document.createElement('div'); r.className = '__ring'; r.style.left = x + 'px'; r.style.top = y + 'px';
  document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700); };
window.__badge = (t) => { window.__ov(); document.getElementById('__badge').textContent = t; };
document.addEventListener('DOMContentLoaded', () => window.__ov());
"""


class Ctx:
    def __init__(self, page, rec0):
        self.page, self.rec0 = page, rec0
        self.pos = (W / 2, H / 2)
        self.badge_text = ""
        self.t0, self.starts = 0.0, []

    def now(self):
        return time.monotonic() - self.rec0

    def _schedule(self, i, earliest):
        """문장 i 의 시작 시각을 정한다: 앞 문장이 끝난 뒤(GAP), 그리고 화면이 준비된 뒤."""
        prev_end = self.t0 if i == 0 else self.real[i - 1] + self.durs[i - 1] + GAP
        self.real[i] = max(prev_end, earliest)

    async def at(self, i, extra=0.0):
        """화면 조작이 i번째 문장에 도착 → 앞 문장이 끝날 때까지 기다리고, 그때 i번째 문장을 시작한다.
        화면이 늦으면 말이 기다린다(말과 화면이 어긋나지 않게)."""
        for j in range(i):
            if self.real[j] is None:
                self._schedule(j, self.t0)
        self._schedule(i, self.now())
        target = self.real[i] + extra
        if self.now() < target:
            await asyncio.sleep(target - self.now())

    def finish(self):
        for j in range(len(self.durs)):
            if self.real[j] is None:
                self._schedule(j, self.t0)
        return self.real[-1] + self.durs[-1] + TAIL

    async def wait(self, ms):
        await asyncio.sleep(ms / 1000)

    async def _restore(self):
        await self.page.evaluate("window.__ov && window.__ov()")
        await self.page.evaluate("([x,y,b]) => {window.__move(x,y); window.__badge(b)}", [*self.pos, self.badge_text])

    async def goto(self, url):
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        await self._restore()

    async def card(self, html):
        await self.page.set_content(html)
        await self.page.add_script_tag(content=OVERLAY)
        await self._restore()

    async def badge(self, text):
        self.badge_text = text
        await self.page.evaluate("t => window.__badge(t)", text)

    async def _center(self, sel):
        loc = self.page.locator(sel).first
        await loc.wait_for(state="visible", timeout=8000)
        box = await loc.bounding_box()
        if box["y"] < 100 or box["y"] + min(box["height"], 130) > H - 160:
            await self.scroll(sel, offset=-H / 3 / Z)
            box = await loc.bounding_box()
        return loc, (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    async def move(self, sel):
        loc, (x, y) = await self._center(sel)
        self.pos = (x, y)
        await self.page.evaluate("([x,y]) => window.__move(x,y)", [x, y])
        await asyncio.sleep(0.65)
        return loc, (x, y)

    async def click(self, sel, quick=False):
        loc, (x, y) = await self.move(sel)
        await self.page.evaluate("([x,y]) => window.__ring(x,y)", [x, y])
        await asyncio.sleep(0.15 if quick else 0.3)
        await loc.click()
        await asyncio.sleep(0.3)
        await self._restore()

    async def type(self, sel, text, delay=110):
        loc, _ = await self.move(sel)
        await loc.click()
        await self.page.keyboard.type(text, delay=delay)

    async def fill(self, sel, value):
        await self.page.locator(sel).first.fill(value)

    async def clear(self, sel):
        await self.page.locator(sel).first.fill("")

    async def select(self, sel, label):
        loc, _ = await self.move(sel)
        await loc.select_option(label=label)
        await asyncio.sleep(0.6)

    async def scroll(self, sel, offset=-120):
        offset = offset * Z  # 대본의 offset 은 1152x648 기준
        await self.page.evaluate(
            "([s,o]) => { const e = document.querySelector(s) || null; if(!e) return;"
            " const y = e.getBoundingClientRect().top + window.scrollY + o; window.scrollTo({top: Math.max(0,y), behavior: 'smooth'}); }",
            [sel, offset]) if ":has-text" not in sel else await self.page.locator(sel).first.evaluate(
            "(e, o) => window.scrollTo({top: Math.max(0, e.getBoundingClientRect().top + window.scrollY + o), behavior: 'smooth'})", offset)
        await asyncio.sleep(0.9)

    async def hl(self, *sels, ms=2200):
        locs = [self.page.locator(s).first for s in sels]
        for l in locs:
            if await l.count():
                await l.evaluate("e => e.classList.add('__hl')")
        await asyncio.sleep(ms / 1000)
        for l in locs:
            if await l.count():
                await l.evaluate("e => e.classList.remove('__hl')")


async def do_record():
    """CDP 화면 송출(1920x1080) 프레임을 30fps 로 ffmpeg 에 바로 넣어 녹화한다."""
    import base64, io
    from PIL import Image
    from playwright.async_api import async_playwright
    tim = timing()
    out = WORK / "screen.mp4"
    WORK.mkdir(exist_ok=True)
    black = io.BytesIO(); Image.new("RGB", (W, H), (11, 59, 117)).save(black, "JPEG"); black = black.getvalue()
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", "30", "-c:v", "mjpeg", "-i", "-",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14", "-pix_fmt", "yuv420p", str(out),
        stdin=asyncio.subprocess.PIPE)
    state = {"frame": black, "run": True, "written": 0, "late": 0.0}

    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, locale="ko-KR")
        await ctx.add_init_script(OVERLAY)
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)

        def on_frame(f):
            state["frame"] = base64.b64decode(f["data"])
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)
        await page.set_content("<html><body style='margin:0;background:#0b3b75'></body></html>")
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        rec0 = time.monotonic()

        async def writer():
            k = 0
            while state["run"]:
                target = rec0 + k / 30
                lag = time.monotonic() - target
                if lag < 0:
                    await asyncio.sleep(-lag)
                    continue
                state["late"] = max(state["late"], lag)
                proc.stdin.write(state["frame"])
                await proc.stdin.drain()
                k += 1
            state["written"] = k
        wt = asyncio.create_task(writer())

        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        c = Ctx(page, rec0)
        log = []
        await asyncio.sleep(0.5)
        for s, t in zip(script.SCENES, tim):
            c.t0, c.durs = c.now(), t["durs"]
            c.real = [None] * len(c.durs)
            c.real[0] = c.t0
            await s["act"](c)
            end = c.finish()
            over = c.now() - end
            if over < 0:
                await asyncio.sleep(-over)
            delay = [round(r - (c.t0 + p), 1) for r, p in zip(c.real, t["starts"])]
            log.append({"id": s["id"], "t0": c.t0, "abs": c.real})
            print(f"{s['id']:9s} start {c.t0:6.1f}s  계획 {t['length']:5.1f}s  실제 {max(end, c.now()) - c.t0:5.1f}s  문장 지연 {delay}", flush=True)
        await asyncio.sleep(1.0)
        total = c.now()
        state["run"] = False
        await wt
        await cdp.send("Page.stopScreencast")
        await ctx.close()
        await b.close()
    proc.stdin.close()
    await proc.wait()
    json.dump({"scenes": log, "total": total, "video": str(out), "errors": errs, "frames": state["written"]},
              open(WORK / "timeline.json", "w"), ensure_ascii=False, indent=1)
    print("녹화 완료", out, f"{total:.1f}s", f"frames {state['written']} (기대 {total*30:.0f})",
          f"최대 지연 {state['late']:.2f}s", "페이지 오류:", errs)


# ---------------------------------------------------------------- 합성
def ass_time(t):
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def wrap(text, n=34):
    """자막 한 줄 길이 제한(두 줄까지)"""
    if len(text) <= n:
        return text
    words, lines_, cur = text.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines_.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines_.append(cur)
    return r"\N".join(lines_)


def do_mux():
    import subprocess
    tl = json.load(open(WORK / "timeline.json"))
    total = tl["total"]
    track = np.zeros(int((total + 1) * SR), dtype=np.float32)
    events = []
    for sc, s in zip(tl["scenes"], script.SCENES):
        for (sub, say), t in zip(s["lines"], sc["abs"]):
            y, sr = sf.read(str(wav_path(say or sub)), dtype="float32")
            if sr != SR:
                y = np.interp(np.linspace(0, len(y) - 1, int(len(y) * SR / sr)), np.arange(len(y)), y).astype("float32")
            i = int(t * SR)
            track[i:i + len(y)] += y[: len(track) - i]
            events.append((t, t + len(y) / SR, sub))
    peak = np.abs(track).max() or 1
    track = track / peak * 0.89
    sf.write(str(WORK / "narration.wav"), track, SR, subtype="PCM_16")
    ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OUT_W}", f"PlayResY: {OUT_H}", "WrapStyle: 2", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Noto Sans CJK KR,50,&H00FFFFFF,&H00FFFFFF,&H80000000,&H99000000,1,0,0,0,100,100,0,0,3,14,0,2,80,80,34,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for a, b, text in events:
        ass.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b + 0.15)},Sub,,0,0,0,,{wrap(text)}")
    (WORK / "subs.ass").write_text("\n".join(ass), encoding="utf-8")
    out = HERE / "demo.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", tl["video"], "-i", str(WORK / "narration.wav"),
           "-filter_complex", f"[0:v]ass={WORK / 'subs.ass'}[v]",
           "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print("완성:", out, f"{total:.1f}s")


if __name__ == "__main__":
    step = sys.argv[1]
    {"tts": do_tts, "record": lambda: asyncio.run(do_record()), "mux": do_mux}[step]()
