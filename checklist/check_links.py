"""districts.json의 누리집·신청 페이지 주소가 열리는지 확인한다.  실행: python check_links.py"""
import json
import urllib.request
from pathlib import Path

districts = json.loads((Path(__file__).parent / "data" / "districts.json").read_text(encoding="utf-8"))["districts"]
for d in districts:
    for key in ("homepage", "apply_url"):
        url = d.get(key)
        if not url:
            if key == "apply_url":
                print(f"[비어 있음] {d['name']} apply_url")
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                print(f"[{res.status}] {d['name']} {key} {url}")
        except Exception as e:  # noqa: BLE001
            print(f"[실패] {d['name']} {key} {url} -> {e}")
