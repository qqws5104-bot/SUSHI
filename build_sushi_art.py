"""초밥 스킨용 종류별 보드 칸 일러스트(box_art/<key>.webp) 생성기.
belt-ui.js(sushi_belt 프로토타입)의 topping() SVG를 그대로 가져와 종류별로 초밥 2점을 한 장에 그린다.
실행: python3 build_sushi_art.py  (playwright + chromium 필요, PIL로 webp 저장)"""
import os, sys, re, json
from PIL import Image
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "box_art")
TOP = {
 "salmon": '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#f08a4b"/><path d="M28 44q10-5 18 0M44 39q10-5 18 0M52 50q9-4 16 0" stroke="#ffd9bd" stroke-width="2.4" fill="none" stroke-linecap="round"/>',
 "tuna": '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#b3262e"/><path d="M30 46q20-8 40 0" stroke="#e7727a" stroke-width="3" fill="none" stroke-linecap="round"/>',
 "shrimp": '<path d="M24 52q2-20 28-20q20 0 24 16q-6 6-26 6q-20 0-26-2z" fill="#f4a79b"/><path d="M36 36q3 10 0 18M48 33q3 12 0 22M60 34q3 11 0 20" stroke="#dd6f64" stroke-width="2.6" fill="none" stroke-linecap="round"/><path d="M74 46l10-6l-2 10z" fill="#dd6f64"/>',
 "egg": '<rect x="26" y="34" width="48" height="26" rx="6" fill="#f4cf4a"/><rect x="45" y="30" width="10" height="32" rx="2" fill="#1f2a24"/>',
 "eel": '<ellipse cx="50" cy="46" rx="29" ry="13" fill="#6b3a1e"/><path d="M26 44q24-9 48 0" stroke="#b27a47" stroke-width="3.2" fill="none" stroke-linecap="round"/><path d="M34 52q16 4 32 0" stroke="#3f200d" stroke-width="2.4" fill="none" stroke-linecap="round"/>',
 "octopus": '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#f3dbe1"/><path d="M24 46q26-14 52 0" stroke="#9c4f73" stroke-width="4" fill="none" stroke-linecap="round"/><circle cx="38" cy="48" r="2.2" fill="#c98aa6"/><circle cx="50" cy="50" r="2.2" fill="#c98aa6"/><circle cx="62" cy="48" r="2.2" fill="#c98aa6"/>',
 "ikura": '<rect x="28" y="36" width="44" height="26" rx="9" fill="#1f2a24"/><ellipse cx="50" cy="38" rx="19" ry="8" fill="#f26a2e"/><circle cx="41" cy="36" r="3.4" fill="#ff9a58"/><circle cx="50" cy="33" r="3.4" fill="#ff8a45"/><circle cx="59" cy="36" r="3.4" fill="#ff9a58"/><circle cx="46" cy="40" r="3.2" fill="#e85a22"/><circle cx="55" cy="40" r="3.2" fill="#e85a22"/>',
 "tofu": '<path d="M24 56q-2-22 26-24q28 2 26 24z" fill="#d9922e"/><path d="M30 44h40" stroke="#b36f17" stroke-width="2.4" stroke-dasharray="4 4"/><ellipse cx="50" cy="35" rx="14" ry="5" fill="#fdfbf4"/>',
}
def nigiri(k): return '<ellipse cx="50" cy="58" rx="25" ry="12" fill="#fdfbf4" stroke="#d9d2c0"/>' + TOP[k]
PAIRS = {"normal": ("egg", "tofu"), "fragile": ("salmon", "ikura"), "valuable": ("eel", "tuna"), "fixed-floor": ("shrimp", "octopus")}
def svg(a, b):
    s = 4.1
    def g(k, x, y): return '<g transform="translate(%s %s) scale(%s) translate(-12 -24)">%s</g>' % (x, y, s, nigiri(k))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="620" height="380" viewBox="0 0 620 380">'
            '<ellipse cx="310" cy="330" rx="270" ry="26" fill="rgba(60,40,20,.18)"/>'
            + g(a, 10, 40) + g(b, 300, 130) + '</svg>')
def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium"))
        pg = br.new_page(viewport={"width": 620, "height": 380})
        for key, (a, b) in PAIRS.items():
            pg.set_content('<html><body style="margin:0;background:transparent">' + svg(a, b) + '</body></html>')
            tmp = "/tmp/_art_%s.png" % key
            pg.screenshot(path=tmp, omit_background=True)
            Image.open(tmp).save(os.path.join(OUT, key + ".webp"), "WEBP", quality=90)
            print("wrote", key)
        br.close()
if __name__ == "__main__": main()
