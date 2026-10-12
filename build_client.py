"""
초밥 서빙 게임 — 자체 호스팅(WebSocket 서버) 버전의 클라이언트(public/index.html) 생성 스크립트.

Claude Artifact의 publish/reload 구조를 걷어내고, 실제 Node WebSocket 서버(server.js +
game-room.js)가 상태를 소유한다. 클라이언트는 이제 순수 렌더러 + WS 클라이언트일 뿐이라
예전 버전에 있던 것들이 통째로 사라졌다: 클라이언트측 리듀서, sessionStorage 기반 pending
액션 재시도, publish 충돌/재시도 로직, 라운드별 투표 집계를 로컬에 모아뒀다 라운드 끝에
한 번만 제출하던 방식(그리고 그 방식 때문에 있었던 "제출 직전 리로드로 집계가 날아가는"
버그의 원인 자체)까지 전부. 서버가 모든 액션을 순서대로 처리하는 단일 소유자이므로
클릭 하나하나를 즉시 브로드캐스트해도 안전하고, 오히려 그게 더 단순하다.

TYPES/CELLS/FLOORS/ROOMS 경제 상수는 game-data.js(서버가 require하는 것과 동일 파일)에서
읽어와 클라이언트 JSON에 그대로 반영한다 — 서버와 클라이언트가 다른 소스에서 각자
유지되며 몰래 어긋나는 일을 원천적으로 막기 위함.
"""

import os
import re
import base64
import json

# 2026-08-28: 전반/후반 퍼즐 이미지 분리 (이전엔 REF_DIR 하나를 두 하프가 공유했다 -- 후반용 세트가
# 아직 안 와서 임시로 그랬던 것. 후반 세트가 도착해서 REF_DIR_1(전반)/REF_DIR_2(후반)로 나눔).
REF_DIR_1 = "/home/claude/project/quiz_board/ref"
REF_DIR_2 = "/home/claude/project/quiz_board/ref_2"
COMPRESSED_DIR = "/tmp/compressed"
GAME_DATA_JS = os.path.join(os.path.dirname(__file__), "game-data.js")
OUT_HTML = os.path.join(os.path.dirname(__file__), "public", "index.html")
# 2026-08-27: 종류별 보드 칸 배경으로 쓰는 상자 일러스트 (사용자 제공, ref/box_art/<key>.webp --
# 알파 채널 있는 투명 배경 PNG를 크롭해 webp로 저장해둔 것). CELLS의 퍼즐 이미지(칸마다 다름)와는
# 별개로, 종류(TYPES)당 딱 1장씩만 있고 그 종류의 21칸 전부가 공유해서 쓴다.
BOX_ART_DIR = os.path.join(os.path.dirname(__file__), "box_art")


def load_shared_constants():
    """game-data.js를 파싱해서 TYPES/FLOORS/ROOMS/ELEVATOR_ROUNDS/SECURE_PHASE_MS/VOTE_MS를
    그대로 재사용한다 (정규식으로 각 상수 리터럴을 추출 -- Node를 별도로 실행하지 않고
    빌드 스크립트를 순수 Python으로 유지하기 위함). 값이 하나라도 어긋나면 즉시 실패하도록
    각 상수를 못 찾으면 에러를 낸다."""
    src = open(GAME_DATA_JS, encoding="utf-8").read()

    def grab(name):
        m = re.search(r"const %s = (\[[\s\S]*?\]|\d+(?:\s*\*\s*\d+)*);" % re.escape(name), src)
        if not m:
            raise RuntimeError(f"could not find {name} in game-data.js")
        return m.group(1)

    types_js = grab("TYPES")
    couriers_js = grab("COURIERS")
    floors_js = grab("FLOORS")
    rooms_js = grab("ROOMS")
    elevator_rounds = eval(grab("ELEVATOR_ROUNDS"))
    secure_phase_ms = eval(grab("SECURE_PHASE_MS"))
    vote_ms = eval(grab("VOTE_MS"))
    priority_multiplier = eval(grab("PRIORITY_MULTIPLIER"))
    same_floor_choice_ms = eval(grab("SAME_FLOOR_CHOICE_MS"))
    halves = eval(grab("HALVES"))
    thief_place_ms = eval(grab("THIEF_PLACE_MS"))
    priority_pick_ms = eval(grab("PRIORITY_PICK_MS"))

    # TYPES uses plain (unquoted) JS object keys -- not valid JSON as-is. Quote bare
    # identifier keys before parsing (FLOORS/ROOMS are already flat string arrays, so this
    # is a no-op for them; applying it unconditionally keeps this function generic).
    def js_object_to_json(js):
        js = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', js)
        # strip trailing commas before a closing ] or } (valid in JS, not in JSON)
        js = re.sub(r',(\s*[\]}])', r'\1', js)
        return js

    types = json.loads(js_object_to_json(types_js))
    couriers = json.loads(js_object_to_json(couriers_js))
    floors = json.loads(js_object_to_json(floors_js))
    rooms = json.loads(js_object_to_json(rooms_js))
    return (types, couriers, floors, rooms, elevator_rounds, secure_phase_ms, vote_ms,
            priority_multiplier, same_floor_choice_ms, halves, thief_place_ms, priority_pick_ms)


(TYPES, COURIERS, FLOORS, ROOMS, ELEVATOR_ROUNDS, SECURE_PHASE_MS, VOTE_MS,
 PRIORITY_MULTIPLIER, SAME_FLOOR_CHOICE_MS, HALVES, THIEF_PLACE_MS, PRIORITY_PICK_MS) = load_shared_constants()

# 2026-08-27 개편: 보드가 20칸(4종류x5개 고정)에서 21칸(종류별 count가 다름, 지정 초밥만 6개)으로
# 바뀌면서, 예전의 스와치 개수(2/3/4조각) 기준 이미지 그룹핑은 더 이상 종류별 칸 수와 맞물리지 않는다
# (그 그룹핑은 애초에 시각적 편의였을 뿐 게임 로직과는 무관했다). 이제는 CELLS 순서대로 이미지 파일을
# 그냥 하나씩 배정한다. 21칸에 맞는 원본 PNG가 REF_DIR_1/REF_DIR_2에 없다면, 마지막 이미지를 재사용해
# 자리만 채우고 크게 경고한다 -- 빌드/배포는 막지 않되 실제 플레이에는 쓰면 안 되는 플레이스홀더임을
# 분명히 한다.
#
# 2026-08-28: 전반(half 1)과 후반(half 2)이 서로 다른 21장 세트를 쓴다 (REF_DIR_1/REF_DIR_2).
# 보드 구조(id/catIdx/num, game-data.js의 CELLS)는 두 하프가 그대로 공유하지만 -- 서버는 이미지에
# 관심이 없다, 순전히 클라이언트가 퍼즐 오버레이에 띄우는 이미지만 하프별로 다르다. 그래서 이 파일의
# CELLS는 half별로 두 벌(CELLS_1/CELLS_2)을 만들고, 클라이언트의 cellMeta(id, half)가 그중 하나를
# 골라 쓴다 (렌더 함수 쪽 주석 참고).
TOTAL_CELLS = sum(t["count"] for t in TYPES)
LEGACY_TOTAL_CELLS = 21  # 원본 PNG 한 세트의 장 수 (예전 5/5/5/6 배치) -- PUZZLE_SRC의 번호는 이 번호 체계를 따른다


def load_image_files(ref_dir):
    files = sorted(
        f for f in os.listdir(ref_dir)
        if f.lower().endswith(".png") and f != "contact_sheet.png"
    )
    if len(files) < LEGACY_TOTAL_CELLS:
        print(f"WARNING: {ref_dir} 안에 원본 PNG가 {len(files)}장뿐입니다(예전 배치 기준 {LEGACY_TOTAL_CELLS}장 필요). 부족한 칸은 마지막 이미지를 재사용합니다.")
    return files


def image_for_flat_idx(files, ref_dir, i):
    if not files:
        raise RuntimeError(f"{ref_dir}에 원본 PNG가 하나도 없습니다.")
    return files[i] if i < len(files) else files[-1]


def data_uri_for(png_name):
    jpg_name = png_name.replace(".png", ".jpg")
    path = os.path.join(COMPRESSED_DIR, jpg_name)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


# 2026-10-06: 우봉고 퍼즐 이미지는 "특선 초밥" 칸에만 필요하다(나머지 종류는 미니게임). 퍼즐의 색(조각) 개수는 하프마다
# 다르다 -- 전반 3색, 후반 4색(사용자 요청, game-data.js의 valuable.pieces = [3, 4]와 맞출 것). 원본 이미지 세트는
# 예전 21칸 배치(1~5: 2색, 6~10: 3색, 11~15: 4색, 16~21: 3색)로 번호가 매겨져 있으므로, 색 개수에 맞는 이미지를 골라
# 명시적으로 지정한다. (세트, 번호): 세트 1 = REF_DIR_1(전반 원본), 2 = REF_DIR_2(후반 원본), 번호는 1부터.
#   * 전반 특선 초밥 6칸 = 3색짜리 6장 (전반 세트의 6~10번 + 16번) -- 더는 안 쓰는 중급/지정 접시용 이미지를 재활용.
#   * 후반 특선 초밥 6칸 = 4색짜리 6장 (후반 세트의 11~15번 + 전반 세트의 11번). 후반용 4색 이미지는 5장뿐이라 6번째는
#     전반에서 안 쓰게 된 전반 세트의 4색 이미지를 가져온다 -- 전반에는 4색 이미지가 안 나오므로 한 판 안에서 겹치지 않는다.
# 특선 초밥이 아닌 종류(mini가 있는 종류)의 칸은 src를 비워서 번들에서 이미지를 뺀다(약 4MB -> 1.4MB). 어떤 종류를 다시
# 우봉고로 돌리려면(TYPES의 mini를 null로) 아래 PUZZLE_SRC에 그 종류의 (세트, 번호) 6개를 하프별로 적어야 한다 -- 없으면
# 빌드가 실패한다(빈 퍼즐 이미지가 실전에 나가는 걸 막기 위함).
# 2026-10-08 실물 우봉고 복귀: 네 종류 모두 퍼즐 이미지를 싣는다. 원본 세트의 번호 체계(1~5: 2색, 6~10: 3색, 11~15: 4색,
# 16~21: 3색)에 맞춰 색 개수가 TYPES의 pieces와 같은 이미지를 고른다. 전반은 세트 1, 후반은 세트 2 (서로 다른 이미지).
#   일반 4칸(2색) = 1~4 / 중급 4칸(3색) = 6~9 / 특선 초밥 3칸(4색) = 11~13 / 지정 접시 6칸(3색) = 16~21
PUZZLE_SRC = {
    1: {
        "normal": [(1, 1), (1, 2), (1, 3), (1, 4)],
        "fragile": [(1, 6), (1, 7), (1, 8), (1, 9)],
        "valuable": [(1, 11), (1, 12), (1, 13)],
        "fixed-floor": [(1, 16), (1, 17), (1, 18), (1, 19), (1, 20), (1, 21)],
    },
    2: {
        "normal": [(2, 1), (2, 2), (2, 3), (2, 4)],
        "fragile": [(2, 6), (2, 7), (2, 8), (2, 9)],
        "valuable": [(2, 11), (2, 12), (2, 13)],
        "fixed-floor": [(2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 21)],
    },
}
REF_DIRS = {1: REF_DIR_1, 2: REF_DIR_2}
_FILES_BY_SET = {}


def _files_for_set(set_no):
    if set_no not in _FILES_BY_SET:
        _FILES_BY_SET[set_no] = load_image_files(REF_DIRS[set_no])
    return _FILES_BY_SET[set_no]


def build_cells(half):
    cells = []
    for cat_idx, t in enumerate(TYPES):
        picks = PUZZLE_SRC[half].get(t["key"]) if t.get("mini") is None else None
        if t.get("mini") is None and (picks is None or len(picks) < t["count"]):
            raise RuntimeError(f"{t['name']}은(는) 우봉고인데 PUZZLE_SRC[{half}]에 퍼즐 이미지 {t['count']}장이 지정되어 있지 않습니다.")
        for num_idx in range(t["count"]):
            src = ""
            if picks is not None:
                set_no, n = picks[num_idx]
                files = _files_for_set(set_no)
                src = data_uri_for(image_for_flat_idx(files, REF_DIRS[set_no], n - 1))
            cells.append({
                "id": f"{t['key']}-{num_idx + 1}",
                "catIdx": cat_idx,
                "num": num_idx,
                "src": src,
            })
    return cells


CELLS_1 = build_cells(1)   # 전반
CELLS_2 = build_cells(2)   # 후반


def box_art_data_uri(key):
    path = os.path.join(BOX_ART_DIR, f"{key}.webp")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/webp;base64,{b64}"


# catIdx로 바로 인덱싱해서 쓰는 배열 (TYPES 순서와 항상 같이 감) -- renderBoard가 BOX_ART[catIdx]로 참조.
BOX_ART = [box_art_data_uri(t["key"]) for t in TYPES]

# 2026-10-12: 입장·결과 화면에 쓰는 대표 이미지 (사용자 제공 컨셉 이미지, art/hero.webp -- 좌: 초밥왕, 우: 스시헌터).
HERO_PATH = os.path.join(os.path.dirname(__file__), "art", "hero.webp")
with open(HERO_PATH, "rb") as _f:
    HERO_URL = "data:image/webp;base64," + base64.b64encode(_f.read()).decode("ascii")

TYPES_JSON = json.dumps(TYPES, ensure_ascii=False)
COURIERS_JSON = json.dumps(COURIERS, ensure_ascii=False)
CELLS_1_JSON = json.dumps(CELLS_1, ensure_ascii=False)
CELLS_2_JSON = json.dumps(CELLS_2, ensure_ascii=False)
FLOORS_JSON = json.dumps(FLOORS, ensure_ascii=False)
BOX_ART_JSON = json.dumps(BOX_ART, ensure_ascii=False)
# 초밥 아이콘(내 초밥 목록용): 참고 일러스트에서 잘라 만든 art/sushi_<key>.webp. 없는 키는 클라이언트가 SVG로 대체한다.
SUSHI_IMG = {}
for _k in ("egg", "whitefish", "salmon", "eel"):
    _p = os.path.join(os.path.dirname(__file__), "art", "sushi_" + _k + ".webp")
    if os.path.exists(_p):
        with open(_p, "rb") as _f:
            SUSHI_IMG[_k] = "data:image/webp;base64," + base64.b64encode(_f.read()).decode("ascii")
SUSHI_IMG_JSON = json.dumps(SUSHI_IMG, ensure_ascii=False)
ROOMS_JSON = json.dumps(ROOMS, ensure_ascii=False)

HEAD_HTML = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>초밥 서빙 게임 — 라이브</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jua&family=Oswald:wght@500;600;700&family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
  /* 2026-08-27 전면 리스킨: 어두운 남색 테마 -> 사용자가 준 "초밥 요금표" 참고 포스터(크림/베이지
     바탕 + 주황 포인트)에 맞춘 따뜻한 톤. 게임 전체(로비/보드/회전 벨트/하프타임/종료 화면 전부)에
     적용 -- 사용자가 명시적으로 "게임 전체" 범위를 확인했다. 토큰만 바꾸면 대부분의 컴포넌트가
     자동으로 따라오지만, 특정 hex 값을 직접 박아넣은 rgba(...) 리터럴들과, 어두운 배경을 전제로 한
     "옅은 흰색 틴트" 오버레이들은 토큰이 아니라서 이 블록만 바꿔선 안 바뀐다 -- 아래 각 규칙에서
     개별적으로 손봤다 (검색: 2026-08-27 리스킨). */
  :root {
    --bg: #f7ecd9; --bg-deep: #efdcb2; --panel: #fffcf4; --panel-line: rgba(43,29,18,0.14);
    --ink: #2b1d12; --muted: #8a7256; --gold: #e2691a; --gold-ink: #fff8ef;
    --sky: #2569a8; --danger: #c7402d; --ok: #2f8f52; --visited: #d8c7a1;
    --font-display: 'Oswald','Noto Sans KR',sans-serif; --font-body: 'Noto Sans KR',system-ui,-apple-system,sans-serif;
  }
  * { box-sizing: border-box; }
  html,body { margin:0; padding:0; background:var(--bg); color:var(--ink); font-family:var(--font-body); min-height:100%; }
  body { min-height:100vh; }
  #app { min-height:100vh; display:flex; flex-direction:column; }
  button { font-family:inherit; cursor:pointer; }
  .topbar { display:flex; align-items:center; justify-content:space-between; gap:1rem;
    padding:0.9rem clamp(1rem,3vw,2.2rem); border-bottom:1px solid var(--panel-line);
    background:linear-gradient(180deg,var(--bg-deep),rgba(239,220,178,0)); flex-wrap:wrap; }
  .topbar .brand { display:flex; flex-direction:column; gap:0.3rem; }
  .topbar .eyebrow { font-family:var(--font-display); font-size:0.7rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--gold); font-weight:600; }
  .topbar h1 { margin:0; font-size:clamp(1.1rem,2vw,1.5rem); font-weight:700; }
  .topbar .right { display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; }
  .seat-badge { display:inline-flex; align-items:center; gap:0.4rem; padding:0.3rem 0.7rem; border-radius:999px;
    border:1px solid rgba(226,105,26,0.4); background:rgba(226,105,26,0.08); color:var(--gold);
    font-family:var(--font-display); font-size:0.82rem; font-weight:600; }
  .room-chip { display:inline-flex; align-items:center; gap:0.35rem; padding:0.3rem 0.7rem; border-radius:999px;
    border:1px solid rgba(37,105,168,0.35); background:rgba(37,105,168,0.1); color:var(--sky);
    font-family:var(--font-display); font-size:0.82rem; font-weight:600; letter-spacing:0.05em; }
  .conn-banner { position:fixed; top:0; left:0; right:0; z-index:90; text-align:center; padding:0.5rem;
    background:var(--danger); color:#fff; font-family:var(--font-display); font-size:0.85rem; font-weight:600; }
  main.stage { flex:1; padding:clamp(1rem,3vw,2.2rem); display:flex; flex-direction:column; gap:1.2rem; }
  /* Secure phase gets a genuine fit-to-viewport layout instead of a guessed pixel budget: the
     page height is pinned to the viewport (no page scroll) and the board grid is given exactly
     whatever vertical space is left after the header, with its 4 rows set to fill that space
     (grid-template-rows: 1fr) and the boxes stretching to match (aspect-ratio:auto below) --
     so cell size adapts automatically to WHATEVER a given laptop's browser chrome actually
     leaves, rather than a fixed rem/aspect-ratio guess that can be thrown off by toolbars,
     bookmark bars, or OS scaling. board-grid keeps a scroll fallback (overflow-y:auto) in case
     content still can't physically fit (e.g. a very short window) so nothing ever gets clipped. */
  html:has(main.stage--secure), html:has(main.stage--secure) body { height:100%; overflow:hidden; }
  html:has(main.stage--secure) #app { height:100vh; }
  main.stage.stage--secure { padding-left:calc(128px + 1.1rem + 1.6rem); padding-top:clamp(0.5rem,1.6vw,1.1rem); padding-bottom:clamp(0.5rem,1.6vw,1.1rem); min-height:0; }
  @media (max-width:900px) { main.stage.stage--secure { padding-left:clamp(1rem,3vw,2.2rem); } }
  .card { background:var(--panel); border:1px solid var(--panel-line); border-radius:14px; padding:1.2rem 1.4rem; }
  .stage--secure .card { padding:0.8rem 1rem; flex:1; min-height:0; display:flex; flex-direction:column; }
  .btn { border:none; border-radius:10px; padding:0.7rem 1.3rem; font-weight:700; font-size:0.95rem;
    font-family:var(--font-display); letter-spacing:0.01em; transition:transform .12s ease, filter .12s ease; }
  .btn:active { transform:scale(0.96); }
  .btn.primary { background:var(--gold); color:var(--gold-ink); }
  .btn.primary:hover { filter:brightness(1.08); }
  .btn.ghost { background:transparent; color:var(--ink); border:1px solid var(--panel-line); }
  .btn.danger { background:var(--danger); color:#fff; }
  .btn.ok { background:var(--ok); color:#fff; }
  .btn:disabled { opacity:0.4; cursor:not-allowed; transform:none; }
  .btn.big { padding:1.4rem; font-size:1.4rem; border-radius:16px; width:100%; }

  .center-screen { flex:1; display:flex; align-items:center; justify-content:center; padding:2rem 1rem; }
  /* 2026-08-27: 좌석 선택 화면을 "플레이어 1/2" 두 버튼에서 가상 셰프 5종 아이콘 픽커로 교체하면서
     같이 카드 배경 + 장식용 초밥상자 일러스트를 추가했다 (사용자 요청: "처음 시작 페이지에 초밥상자
     모양이 좀 그려져 있으면 좋을 것 같아"). .picker-scene이 그 장식(.lobby-box-deco, 카드 뒤에 옅게
     흩어진 상자 라인아트)의 위치 기준점 -- 카드(.seat-pick) 자체는 z-index로 그 위에 뜬다. */
  .picker-scene { position:relative; width:100%; max-width:680px; display:flex; justify-content:center; }
  .lobby-box-deco { position:absolute; pointer-events:none; z-index:0; }
  .lobby-box-deco svg { width:100%; height:100%; display:block; }
  .seat-pick { position:relative; z-index:1; text-align:center; max-width:640px; width:100%; padding:1.6rem 1.8rem; }
  .seat-pick h2 { font-family:var(--font-display); font-size:1.6rem; margin:0 0 0.4rem; }
  .seat-pick p { color:var(--muted); font-size:0.9rem; margin:0 0 1.4rem; }
  .courier-options { display:flex; gap:0.7rem; justify-content:center; flex-wrap:wrap; max-width:360px; margin:0 auto; }
  .courier-btn { --courier-color:var(--gold); flex:0 1 108px; display:flex; flex-direction:column; align-items:center;
    gap:0.4rem; padding:0.9rem 0.6rem; border-radius:14px; background:var(--panel);
    border:2px solid var(--panel-line); font-family:var(--font-display); color:var(--ink);
    transition:transform .12s ease, border-color .12s ease, box-shadow .12s ease; }
  .courier-btn:not(:disabled):hover { transform:translateY(-2px); border-color:var(--courier-color);
    box-shadow:0 8px 18px rgba(43,29,18,0.14); }
  .courier-btn .courier-icon { width:34px; height:34px; color:var(--courier-color); }
  .courier-btn .courier-icon svg { width:100%; height:100%; display:block; }
  .courier-btn .courier-name { font-size:0.82rem; font-weight:700; }
  .courier-btn.mine { border-color:var(--courier-color); background:color-mix(in srgb, var(--courier-color) 12%, var(--panel)); }
  .courier-btn.taken, .courier-btn:disabled:not(.mine) { opacity:0.45; cursor:not-allowed; }
  .courier-btn .taken-note { display:block; font-size:0.68rem; font-weight:600; color:var(--muted); }
  .room-share { margin-top:1.2rem; padding-top:1.2rem; border-top:1px solid var(--panel-line); color:var(--muted); font-size:0.85rem; }
  .room-share strong { color:var(--sky); font-family:var(--font-display); letter-spacing:0.08em; }

  .lobby-box { text-align:center; max-width:520px; }
  .lobby-box h2 { font-family:var(--font-display); font-size:1.8rem; margin:0 0 0.6rem; }
  .lobby-box p { color:var(--muted); font-size:0.95rem; line-height:1.6; }

  .timer-row { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
  .timer-label { font-family:var(--font-display); font-size:0.85rem; color:var(--muted); letter-spacing:0.05em; }
  .timer-num { font-family:var(--font-display); font-size:1.9rem; font-weight:700; font-variant-numeric:tabular-nums; color:var(--gold); }
  .timer-bar { height:8px; border-radius:999px; background:rgba(43,29,18,0.1); overflow:hidden; margin-top:0.5rem; }
  .timer-bar > i { display:block; height:100%; background:var(--gold); transition:width 0.3s linear; }
  .time-left-big { margin-top:0.6rem; font-family:var(--font-display); font-weight:700; font-size:1.5rem;
    color:var(--gold); font-variant-numeric:tabular-nums; letter-spacing:0.02em; }

  .side-timer { position:fixed; left:1.1rem; top:6.5rem; width:128px; z-index:30; text-align:center;
    background:var(--panel); border:1px solid var(--panel-line); border-radius:14px; padding:0.9rem 0.8rem;
    box-shadow:0 14px 34px rgba(0,0,0,0.4); }
  .side-timer .timer-label { display:block; line-height:1.3; margin-bottom:0.4rem; }
  .side-timer .timer-num { display:block; font-size:1.65rem; }
  .side-timer .timer-bar { margin-top:0.6rem; }
  @media (max-width:900px) { .side-timer { position:static; width:auto; margin:0 0 1rem; display:flex;
    align-items:center; gap:0.9rem; text-align:left; } .side-timer .timer-bar { flex:1; margin-top:0; } }

  .ready-row { display:flex; gap:0.7rem; justify-content:center; margin-top:1.2rem; flex-wrap:wrap; }
  .ready-chip { font-family:var(--font-display); font-size:0.85rem; font-weight:600; padding:0.5rem 0.9rem;
    border-radius:999px; border:1px solid var(--panel-line); color:var(--muted); }
  .ready-chip.is-ready { color:var(--ok); border-color:rgba(47,143,82,0.45); background:rgba(47,143,82,0.1); }
  .space-hint { margin:1.4rem auto 0; width:min(220px,80%); padding:0.9rem; text-align:center; border-radius:10px;
    border:1px solid var(--panel-line); background:rgba(43,29,18,0.035); font-family:var(--font-display);
    letter-spacing:0.08em; color:var(--muted); }
  .key-hint { margin-top:0.6rem; color:var(--muted); font-size:0.78rem; }

  /* 2026-10-06 레일 화면: 제작 보드는 "레일 위의 초밥 4종". 종류마다 한 줄이고, 줄 가운데에 초밥 상자(남은 개수 점 6개),
     내 자리 쪽(1번 = 왼쪽, 2번 = 오른쪽)에 내 버튼이 있다. 버튼을 누르면 내 화면에 그 종류의 미니게임이 뜬다.
     상대 쪽은 비워 둔다(상대가 뭘 하는지는 안 보인다 -- 남은 개수만 공유). 지정 초밥은 접시가 곧 칸이라 버튼 대신 접시 버튼 6개. */
  .board-grid { display:flex; flex-direction:column; gap:0; flex:1; min-height:0; overflow-y:auto; }
  .board-row { flex:1 1 0; min-height:96px; display:grid; grid-template-columns:minmax(0,1fr) minmax(210px,300px) minmax(0,1fr); align-items:stretch; padding:0.28rem 0; }
  .rail-side { display:flex; flex-direction:column; justify-content:center; gap:0.4rem; min-width:0; padding:0 0.7rem; }
  .rail-side.mine { align-items:stretch; }
  .rail-side.theirs { align-items:center; color:var(--muted); font-size:0.7rem; opacity:0.55; }
  .rail-mid { position:relative; display:flex; align-items:center; justify-content:center; padding:0.4rem 0.5rem;
    background:repeating-linear-gradient(180deg,#3b4049 0 14px,#2d3139 14px 18px); box-shadow:inset 0 0 0 3px #1f232b; }
  .rail-head + .board-row .rail-mid { border-radius:12px 12px 0 0; }
  .board-row:last-child .rail-mid { border-radius:0 0 12px 12px; }
  .rail-box { position:relative; width:100%; height:100%; min-height:78px; border-radius:12px; overflow:hidden; border:2px solid rgba(22,35,63,0.55);
    box-shadow:0 5px 10px rgba(0,0,0,0.4); display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.2rem; padding:0.3rem 0.4rem; text-align:center; }
  .rail-box .cell-art { position:absolute; inset:-25% -25%; z-index:0; background-repeat:no-repeat; background-position:center; background-size:cover; opacity:0.55; filter:blur(1px); }
  .rail-box::before { content:""; position:absolute; inset:0; z-index:1; background:linear-gradient(180deg,rgba(255,255,255,0.28),rgba(0,0,0,0.12)); }
  .rail-box > * { position:relative; z-index:2; }
  .rail-box .rb-name { display:inline-flex; align-items:center; gap:0.3rem; background:#f4f1ea; color:#20180f; border:2px solid #16233f; border-radius:6px;
    padding:0.12rem 0.5rem; font-family:var(--font-display); font-weight:800; font-size:0.8rem; line-height:1.15; }
  .rail-box .rb-name .cat-icon { width:15px; height:15px; flex:none; }
  .rail-box .rb-name .cat-icon svg { width:100%; height:100%; display:block; }
  .rail-box .rb-game { font-size:0.68rem; font-weight:700; color:#16233f; background:rgba(255,255,255,0.7); border-radius:999px; padding:0 0.45rem; }
  .rail-box .cat-left { font-family:var(--font-display); font-size:0.7rem; color:#16233f; font-weight:700; }
  .rail-box .cat-left b { font-size:0.9rem; }
  .rail-box .pips { display:flex; gap:4px; background:rgba(255,252,244,0.9); padding:3px 7px; border-radius:999px; }
  .rail-box .pip { width:22px; height:13px; display:inline-block; }
  .rail-box .pip svg { width:100%; height:100%; display:block; overflow:visible; fill:var(--c); stroke:rgba(22,35,63,0.7); stroke-width:1.4; stroke-linejoin:round; }
  .rail-box .pip svg .eye { fill:rgba(22,35,63,0.8); stroke:none; }
  .rail-box .pip.gone { opacity:0.45; }
  .rail-box .pip.gone svg { fill:transparent; stroke-dasharray:2.4 2; }
  .rail-box .pip.gone svg .eye { fill:transparent; }
  .rail-box .stamp { position:absolute; z-index:3; top:50%; left:50%; transform:translate(-50%,-50%) rotate(-8deg); background:var(--danger); color:#fff;
    font-family:var(--font-display); font-weight:800; padding:0.15rem 0.8rem; border-radius:6px; white-space:nowrap; }
  .board-row.is-empty .rail-box { filter:grayscale(1); opacity:0.7; }
  .rail-btn { font:inherit; cursor:pointer; border:2px solid var(--c); border-bottom-width:5px; border-radius:12px; background:var(--panel); color:var(--ink);
    padding:0.5rem 0.6rem; display:flex; flex-direction:column; align-items:center; gap:0.1rem; font-family:var(--font-display); }
  .rail-btn:hover:not(:disabled) { background:#fff6df; }
  .rail-btn:active:not(:disabled) { transform:translateY(3px); border-bottom-width:2px; }
  .rail-btn:disabled { opacity:0.45; cursor:default; }
  .rail-btn .rbt { font-weight:800; font-size:0.9rem; }
  .rail-btn .rbp { font-size:0.7rem; color:var(--muted); font-weight:700; font-variant-numeric:tabular-nums; }
  .floor-btns { display:grid; grid-template-columns:repeat(3,1fr); gap:0.3rem; }
  .floor-btn { font:inherit; font-family:var(--font-display); font-weight:800; font-size:0.85rem; cursor:pointer; border:2px solid var(--c); border-bottom-width:4px; border-radius:9px;
    background:var(--panel); color:var(--ink); padding:0.28rem 0.1rem; }
  .floor-btn:hover:not(.is-gone) { background:#fff6df; }
  .floor-btn.is-gone { cursor:default; opacity:0.4; border-style:dashed; background:transparent; }
  .floor-btn.mine { opacity:1; background:var(--c); border-style:solid; display:flex; flex-direction:column; align-items:center; line-height:1.1; }
  .floor-btn.mine small { font-size:0.62rem; font-weight:700; }
  .my-chips { display:flex; flex-wrap:wrap; gap:0.25rem; justify-content:center; min-height:1.3rem; }
  .my-chip { background:#f4f1ea; color:#20180f; border:2px solid #16233f; border-radius:6px; font-family:var(--font-display); font-weight:700; font-size:0.74rem; padding:0 0.4rem; }
  .rail-side .mine-count { font-size:0.7rem; color:var(--muted); font-weight:700; text-align:center; }
  .rail-head { display:grid; grid-template-columns:minmax(0,1fr) minmax(210px,300px) minmax(0,1fr); font-family:var(--font-display); font-weight:700; font-size:0.78rem; color:var(--muted); padding-bottom:0.3rem; text-align:center; }
  .rail-head .me { color:var(--ink); }
  /* 2026-10-06: 폰/좁은 화면 -- 3열(내 자리|레일|상대 자리)은 안 들어가므로 한 줄을 2열(레일 상자 | 내 버튼)로 줄인다.
     상대 자리 열과 3열 머리글은 숨기고(어차피 비어 있음), 1번/2번 자리 모두 상자가 왼쪽, 내 버튼이 오른쪽. 세로로 길어지면 보드가 스크롤. */
  @media (max-width:860px) {
    .rail-head { display:none; }
    .board-grid { overflow-y:auto; }
    .board-row { flex:none; min-height:0; grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); gap:0.3rem; padding:0.2rem 0; }
    .board-row .rail-side.theirs { display:none; }
    .board-row .rail-mid { order:1; border-radius:12px; padding:0.35rem 0.4rem; }
    .board-row .rail-side.mine { order:2; padding:0 0.2rem; }
    .rail-box { min-height:92px; }
    .rail-btn { padding:0.6rem 0.4rem; }
    .rail-btn .rbt { font-size:0.85rem; }
  }


  /* ---------- 2026-10-07 레일 사이트(/rail): 공용 화면. 3열(1번 자리 | 레일 | 2번 자리)을 어느 폭에서도 유지한다. ---------- */
  body.rail-view { overflow:hidden; }
  body.rail-view #app { height:100vh; min-height:0; }
  .rv { height:100vh; display:flex; flex-direction:column; gap:clamp(0.4rem,1.2vh,0.9rem); padding:clamp(0.5rem,1.5vh,1.2rem) clamp(0.6rem,2vw,2rem) clamp(0.6rem,1.8vh,1.4rem); background:linear-gradient(180deg,var(--bg-deep),var(--bg) 22%); }
  .rv-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex:0 0 auto; }
  .rv-eyebrow { font-family:var(--font-display); font-size:0.7rem; letter-spacing:0.22em; text-transform:uppercase; color:var(--gold); font-weight:600; }
  .rv-head h1 { margin:0.1rem 0 0; font-size:clamp(1.1rem,3.2vh,1.8rem); font-weight:800; }
  .rv-chips { display:flex; gap:0.5rem; flex-wrap:wrap; justify-content:flex-end; }
  .rv-chip { padding:0.25rem 0.8rem; border-radius:999px; font-family:var(--font-display); font-weight:700; font-size:0.85rem; white-space:nowrap; }
  .rv-chip.phase { background:rgba(226,105,26,0.12); border:2px solid rgba(226,105,26,0.5); color:var(--gold); }
  .rv-chip.room { background:rgba(37,105,168,0.1); border:2px solid rgba(37,105,168,0.4); color:var(--sky); }
  .rv-clockrow { flex:0 0 auto; display:flex; align-items:center; gap:0.9rem; }
  .rv-clock-label { font-family:var(--font-display); font-weight:700; color:var(--muted); font-size:0.95rem; white-space:nowrap; }
  .rv-clockrow b { font-family:var(--font-display); font-size:clamp(1.6rem,6vh,3rem); font-variant-numeric:tabular-nums; line-height:1; min-width:3.4ch; }
  .rv-clockrow b.is-low { color:var(--danger); }
  .rv-bar { flex:1; height:0.8rem; border-radius:999px; background:rgba(43,29,18,0.1); overflow:hidden; }
  .rv-bar > i { display:block; height:100%; width:100%; background:var(--gold); border-radius:999px; transition:width 0.25s linear; }
  .rv-center { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; gap:1rem; }
  .rv-center h2 { margin:0; font-size:clamp(1.6rem,6vh,3rem); }
  .rv-center p { margin:0; color:var(--muted); font-size:1.1rem; }
  .rv-sides { display:flex; gap:1rem; margin-top:0.6rem; }
  .rv-code { font:inherit; font-family:var(--font-display); font-size:1.4rem; text-transform:uppercase; width:7ch; text-align:center; padding:0.3rem; border:2px solid var(--muted); border-radius:10px; background:var(--panel); color:var(--ink); }
  .rv-side { --c:#999; display:inline-flex; flex-direction:column; align-items:center; gap:0.1rem; padding:0.25rem 0.9rem; border-radius:12px; border:2px solid var(--c); background:var(--panel); color:var(--ink); font-family:var(--font-display); min-width:0; }
  .rv-side b { font-size:clamp(0.9rem,2.4vh,1.25rem); display:inline-flex; align-items:center; gap:0.35rem; }
  .rv-side .rv-side-icon { width:1.2em; height:1.2em; display:inline-flex; color:var(--c); }
  .rv-side .rv-side-icon svg { width:100%; height:100%; }
  .rv-side small { font-size:0.72rem; color:var(--muted); font-weight:700; }
  .rv-side.is-busy { background:var(--c); }
  .rv-side.is-busy, .rv-side.is-busy small { color:#fff; }
  .rv-board { overflow-y:auto; }
  body.rail-view .rail-head { display:grid; grid-template-columns:minmax(0,1fr) minmax(150px,260px) minmax(0,1fr); align-items:end; gap:0; padding-bottom:0.4rem; }
  body.rail-view .rail-head > .rv-side { justify-self:center; }
  body.rail-view .board-row { flex:1 1 0; min-height:84px; grid-template-columns:minmax(0,1fr) minmax(150px,260px) minmax(0,1fr); gap:0; padding:0.28rem 0; }
  body.rail-view .board-row .rail-mid { order:0; border-radius:0; }
  body.rail-view .rail-head + .board-row .rail-mid { border-radius:12px 12px 0 0; }
  body.rail-view .board-row:last-child .rail-mid { border-radius:0 0 12px 12px; }
  body.rail-view .board-row .rail-side.mine { order:0; padding:0 clamp(0.4rem,1.6vw,1.4rem); }
  body.rail-view .rail-btn { padding:clamp(0.4rem,1.6vh,1rem) 0.6rem; flex:1; justify-content:center; }
  body.rail-view .rail-btn .rbt { font-size:clamp(0.95rem,2.6vh,1.5rem); }
  body.rail-view .rail-btn .rbp { font-size:clamp(0.68rem,1.6vh,0.9rem); }
  body.rail-view .floor-btn { font-size:clamp(0.9rem,2.4vh,1.3rem); padding:clamp(0.3rem,1.2vh,0.7rem) 0.1rem; }
  .rail-btn.is-busy { animation:rv-pulse 1.2s ease-in-out infinite; }
  @keyframes rv-pulse { 50% { opacity:0.55; } }
  @media (prefers-reduced-motion: reduce) { .rail-btn.is-busy { animation:none; } }

  /* 플레이어 화면(레일 모드)의 대기 카드 */
  .rw { display:flex; flex-direction:column; gap:0.8rem; }
  .rw h2 { margin:0; font-size:1.3rem; }
  .rw-sub { margin:0; color:var(--muted); font-size:0.9rem; }
  .rw-sub b { color:var(--ink); }
  .rw-list { display:flex; flex-direction:column; gap:0.5rem; }
  .rw-row { --c:#ccc; display:grid; grid-template-columns:auto minmax(0,1.3fr) auto minmax(0,1fr); align-items:center; gap:0.7rem; padding:0.5rem 0.8rem; border-radius:12px; border:2px solid var(--c); background:var(--panel); }
  .rw-row.is-empty { opacity:0.5; }
  .rw-ico { width:24px; height:24px; display:inline-flex; }
  .rw-ico svg { width:100%; height:100%; }
  .rw-name { font-family:var(--font-display); font-weight:800; display:flex; flex-direction:column; line-height:1.15; }
  .rw-name small { font-weight:700; color:var(--muted); font-size:0.72rem; }
  .rw-left { font-family:var(--font-display); font-weight:700; font-size:0.85rem; white-space:nowrap; }
  .rw-left b { font-size:1.1rem; }
  .rw-mine { display:flex; flex-wrap:wrap; gap:0.25rem; justify-content:flex-end; }
  .rw-mine small { color:var(--muted); }
  @media (max-width:560px) { .rw-row { grid-template-columns:auto minmax(0,1fr) auto; } .rw-mine { grid-column:1 / -1; justify-content:flex-start; } }

  /* on genuinely short viewports, shrink the chrome around the board (topbar + side-timer) too --
     the board itself already fills whatever's left via grid-template-rows:1fr, but a smaller
     topbar/timer leaves it more room to work with before the overflow-y:auto fallback kicks in. */
  @media (max-height:700px) {
    .topbar { padding-top:0.5rem; padding-bottom:0.5rem; }
    .side-timer { top:4.6rem; padding:0.6rem 0.6rem; }
    .side-timer .timer-num { font-size:1.3rem; }
  }

  .overlay { position:fixed; inset:0; background:rgba(6,10,18,0.92); display:flex; align-items:center; justify-content:center;
    z-index:50; padding:1.2rem; }
  .overlay.hidden { display:none; }
  /* 2026-10-06: 화면 높이가 낮아도 그림 + 포기/완료 버튼이 한 화면에 들어오도록 폭을 높이 기준으로도 제한(그림 비율 16:9). */
  .puzzle-frame { max-width:960px; width:min(100%, calc((100vh - 8.5rem) * 16 / 9)); }
  .puzzle-frame img { width:100%; border-radius:12px; display:block; box-shadow:0 20px 60px rgba(0,0,0,0.5); }
  .puzzle-actions { display:flex; gap:0.8rem; margin-top:1rem; }
  .puzzle-actions .btn { flex:1; }

  .elev-layout { display:grid; grid-template-columns:220px 1fr; gap:1.2rem; align-items:start; }
  /* 2026-10-06: 폰/좁은 화면에서는 지금 해야 할 일(우선 초밥 10초 창, 이동 버튼, 준비)이 담긴 오른쪽 카드를 위로 올린다 --
     안 그러면 벨트 게이지/내 초밥 목록 밑으로 밀려서 10초 타이머가 도는 걸 화면 밖에서 놓친다. */
  @media (max-width:820px) { .elev-layout { grid-template-columns:1fr; } .elev-layout > div:last-child { order:-1; } }
  /* left column: gauge + my own package list stacked underneath it, so "what I'm carrying" reads
     right off the same glance as "where the car is" instead of living at the bottom of the far
     wider right-hand panel. */
  .elev-left { display:flex; flex-direction:column; gap:1rem; min-width:0; }
  .elev-left .player-col.me { max-width:none; }
  .elev-left .invoice { padding:0.5rem 0.6rem; gap:0.55rem; }
  .elev-left .invoice .meta .t { font-size:0.82rem; }
  .elev-left .invoice .sticker { font-size:0.68rem; padding:0.18rem 0.4rem; }
  /* Elevator position: a plain list of six floor rows with only the CURRENT one highlighted --
     no cumulative fill from the bottom. (An earlier version filled the whole area beneath the
     current floor like a level gauge; reverted per direct feedback -- it read as "progress" rather
     than "here is the car", which is the wrong metaphor once movement is real and instant per
     click.) */
  .shaft { background:var(--bg-deep); border-radius:14px; border:1px solid var(--panel-line); padding:0.8rem; container-type:inline-size; }
  @property --cur { syntax:'<number>'; inherits:true; initial-value:0; }
  .belt-ring { position:relative; width:100%; height:112cqw; transition:--cur 0.55s cubic-bezier(.4,.1,.2,1); }
  .belt-track { position:absolute; left:14cqw; top:14cqw; width:72cqw; height:72cqw; border-radius:50%; border:3cqw solid rgba(43,29,18,0.13); box-sizing:border-box; }
  .floor-stop { position:absolute; left:50%; top:50cqw; width:24cqw; height:24cqw; margin:-12cqw 0 0 -12cqw;
    --ang:calc(90deg + (var(--cur) - var(--i)) * 60deg);
    transform:rotate(var(--ang)) translateX(36cqw) rotate(calc(var(--ang) * -1)); }
  .floor-stop .car { width:100%; height:100%; border-radius:50%; display:flex; align-items:center; justify-content:center; box-sizing:border-box;
    font-family:var(--font-display); font-weight:800; font-size:7cqw; border:0.8cqw solid rgba(43,29,18,0.28); opacity:0.78;
    transition:transform 160ms ease, opacity 160ms ease, box-shadow 160ms ease; }
  .floor-stop.current .car { opacity:1; transform:scale(1.3); border-color:var(--ink); box-shadow:0 1.4cqw 3.5cqw rgba(43,29,18,0.4); }
  .belt-mark { position:absolute; left:0; right:0; top:100cqw; text-align:center; font-family:var(--font-display); font-weight:800; font-size:6.5cqw; color:var(--ink); letter-spacing:0.04em; }
  .inv-sushi { flex:0 0 auto; width:2.3rem; display:inline-flex; align-items:center; }
  .inv-sushi-svg { width:100%; height:auto; display:block; }
  .invoice .t .inv-type { font-weight:600; font-size:0.72rem; color:var(--muted); margin-left:0.2rem; }
  .round-pill { display:inline-flex; align-items:center; gap:0.4rem; padding:0.3rem 0.8rem; border-radius:999px;
    background:rgba(37,105,168,0.12); color:var(--sky); font-family:var(--font-display); font-weight:600; font-size:0.85rem; }
  .vote-buttons { display:flex; flex-direction:column; gap:0.7rem; margin-top:1rem; }
  .round-result { background:rgba(47,143,82,0.1); border:1px solid rgba(47,143,82,0.28); border-radius:10px; padding:0.9rem 1rem; margin-top:0.8rem; }
  .delivered-callout { margin-top:0.6rem; display:flex; flex-direction:column; gap:0.35rem; }
  .delivered-callout.empty { color:var(--muted); font-size:0.85rem; }
  .delivered-item { display:flex; align-items:center; gap:0.5rem; font-size:0.88rem; }
  .delivered-item .swatch { width:9px; height:18px; border-radius:3px; flex-shrink:0; }

  .invoice-list { display:flex; flex-direction:column; gap:0.5rem; margin-top:0.7rem; }
  .invoice { display:flex; align-items:center; gap:0.7rem; padding:0.55rem 0.7rem; border-radius:9px; background:rgba(43,29,18,0.04); border:1px solid var(--panel-line); }
  .invoice.delivered { opacity:0.65; }
  .invoice .swatch { width:10px; height:34px; border-radius:4px; flex-shrink:0; }
  .invoice .meta { flex:1; }
  .invoice .meta .t { font-weight:700; font-size:0.88rem; }
  .invoice .meta .d { font-size:0.78rem; color:var(--muted); }
  .invoice .sticker { font-family:var(--font-display); font-size:0.72rem; font-weight:700; padding:0.2rem 0.5rem; border-radius:999px;
    background:var(--ok); color:#fff; white-space:nowrap; }
  .invoice .sticker.pending { background:transparent; color:var(--muted); border:1px dashed var(--panel-line); }

  .split-two { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
  @media (max-width:720px) { .split-two { grid-template-columns:1fr; } }
  .player-col h3 { font-family:var(--font-display); font-size:0.95rem; margin:0 0 0.3rem; color:var(--muted); }
  .player-col.me h3 { color:var(--gold); }

  /* 우선 초밥 지정 (회전 벨트 라운드 게이트 "idle"/"result"에 내장, 매 라운드 다시 고름) */
  .invoice.pickable { cursor:pointer; transition:background-color 120ms ease, border-color 120ms ease; }
  .invoice.pickable:hover { background:rgba(43,29,18,0.08); }
  .invoice.is-priority { border-color:var(--gold); background:rgba(226,105,26,0.1); }
  .invoice .priority-flag { font-family:var(--font-display); font-size:0.68rem; font-weight:700; color:var(--gold);
    border:1px solid rgba(226,105,26,0.5); border-radius:999px; padding:0.15rem 0.45rem; white-space:nowrap; }
  /* 2026-10-06: 우선 초밥 지정은 게이트에 끼워 넣던 방식에서 전용 10초 창("priority" 상태)으로 분리됐다. */
  .priority-window { background:rgba(226,105,26,0.08); border:1px solid rgba(226,105,26,0.35); border-radius:12px;
    padding:0.9rem 1rem; margin-top:0.75rem; }
  .priority-window h4 { margin:0 0 0.3rem; font-family:var(--font-display); font-size:1rem; color:var(--gold); }
  .priority-window .pw-sub { color:var(--muted); font-size:0.85rem; margin-bottom:0.6rem; }
  .priority-window .pw-clock { display:flex; align-items:baseline; gap:0.6rem; margin-top:0.2rem; }
  .priority-window .pw-clock .time-left-big { margin-top:0; font-size:1.9rem; }
  .priority-window .timer-bar { margin:0.45rem 0 0.8rem; }
  .priority-window .pw-actions { margin-top:0.7rem; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; }
  .priority-window .pw-actions .key-hint { margin:0; }

  /* same-floor 선택 (같은 접시에 서빙 대기 중인 내 초밥이 2개 이상일 때, SAME_FLOOR_CHOICE_MS 동안) */
  .choice-box { background:rgba(226,105,26,0.08); border:1px solid rgba(226,105,26,0.3); border-radius:12px;
    padding:0.9rem 1rem; margin-top:0.75rem; }
  .choice-box h4 { margin:0 0 0.5rem; font-family:var(--font-display); font-size:0.95rem; color:var(--gold); }
  .choice-list { display:flex; flex-direction:column; gap:0.5rem; }
  .choice-list .invoice.chosen { border-color:var(--ok); background:rgba(47,143,82,0.14); }

  /* 초밥도둑 배치 전용 시간 (후반 전용, "thief" 상태 -- 라운드 이동 전 독립된 전체 화면) */
  .thief-window { background:rgba(199,64,45,0.08); border:1px solid rgba(199,64,45,0.3); border-radius:12px;
    padding:0.9rem 1rem; margin-top:0.75rem; }
  .thief-window h4 { margin:0 0 0.5rem; font-family:var(--font-display); font-size:0.95rem; color:var(--danger); }
  .thief-floors { display:flex; flex-wrap:wrap; gap:0.4rem; }
  .thief-floors .btn { flex:none; padding:0.4rem 0.7rem; font-size:0.8rem; }
  .thief-floors .btn small, .peek-panel .btn small { display:block; font-size:0.62rem; font-weight:600; opacity:0.8; }
  .thief-floors .btn.is-peeked { border-color:var(--danger); box-shadow:0 0 0 2px rgba(199,64,45,0.28); }

  /* 시작 3컷 설명 / 3줄 규칙 / 게이트 카운트다운 / 5초 깜빡임 (2026-10-12) */
  .intro3 { position:fixed; left:calc(50% + 40px); top:12px; transform:translateX(-50%); width:min(440px, 58vw); height:58px; z-index:55; pointer-events:none;
    animation:introLife 10s linear both; animation-delay:calc(var(--el) * -1); }
  .intro3 .cut { position:absolute; inset:0; display:flex; gap:0.8rem; align-items:center; padding:0.4rem 0.8rem; background:#2b1d12; color:#fff; border-radius:14px; opacity:0;
    box-shadow:0 5px 0 rgba(0,0,0,0.22); animation:introCut 3.34s linear both; animation-delay:calc(var(--d) - var(--el)); }
  .intro3 .cut i { flex:none; width:1.9rem; height:1.9rem; border-radius:50%; background:#ffc62e; color:#2b1d12; font-style:normal; font-weight:800; display:grid; place-items:center; font-size:1.1rem; }
  .intro3 .cut b { display:block; font-size:0.95rem; } .intro3 .cut span { display:block; font-size:0.76rem; opacity:0.85; margin-top:0.05rem; }
  @keyframes introCut { 0% { opacity:0; transform:translateY(8px); } 8% { opacity:1; transform:none; } 92% { opacity:1; transform:none; } 100% { opacity:0; } }
  @keyframes introLife { 0%, 97% { opacity:1; visibility:visible; } 100% { opacity:0; visibility:hidden; } }
  .rules3 { margin:0.7rem 0 0; padding:0 0 0 1.3rem; display:flex; flex-direction:column; gap:0.3rem; font-size:0.9rem; color:var(--muted); text-align:left; }
  .rules3 b { color:var(--ink, #2b1d12); }
  .halftime-box .rules3 { display:inline-flex; margin:0.8rem auto 0; }
  .gate-count { display:block; margin-top:0.5rem; font-size:0.8rem; color:var(--muted); text-align:center; }
  @keyframes nudgeBlink { 0%, 100% { transform:none; box-shadow:none; } 50% { transform:scale(1.04); box-shadow:0 0 0 4px rgba(255,198,46,0.9); } }
  body.nudge-on .rail-btn:not([disabled]), body.nudge-on .floor-btn:not([disabled]):not(.is-gone) { animation:nudgeBlink 0.9s ease-in-out infinite; }
  body.nudge-on .rw h2 { animation:nudgeBlink 0.9s ease-in-out infinite; }
  @media (prefers-reduced-motion: reduce) { body.nudge-on .rail-btn, body.nudge-on .floor-btn, body.nudge-on .rw h2 { animation:none; } }
  .sfx-toggle { position:fixed; left:12px; bottom:12px; z-index:70; width:38px; height:38px; display:grid; place-items:center; padding:0; border-radius:50%;
    border:2px solid #2b1d12; background:#fff; color:#2b1d12; cursor:pointer; box-shadow:0 2px 0 #2b1d12; opacity:0.85; }
  .sfx-toggle:hover { opacity:1; } .sfx-toggle:focus-visible { outline:3px solid #ffc62e; outline-offset:2px; }
  /* 엿보기 (2026-10-12) */
  .peek-box { margin:0.9rem 0 0.4rem; padding:0.7rem 0.8rem; border:1.5px dashed var(--panel-line); border-radius:12px; text-align:center; display:flex; flex-direction:column; gap:0.45rem; align-items:center; }
  .peek-box .pb-title { font-family:var(--font-display); font-size:1rem; }
  .peek-box .pb-desc, .peek-box .pb-other { font-size:0.8rem; color:var(--muted); }
  .peek-box .pb-done b { display:block; font-family:var(--font-display); font-size:1.05rem; color:var(--gold); }
  .peek-box .pb-done span { font-size:0.8rem; color:var(--muted); }
  .peek-panel { margin-top:0.8rem; padding:0.6rem 0.7rem; border:1px solid var(--panel-line); border-radius:12px; display:flex; flex-direction:column; gap:0.5rem; }
  .peek-panel h3 { margin:0; font-size:0.85rem; }
  .peek-panel .btn { font-size:0.9rem; padding:0.5rem 0.6rem; line-height:1.25; }
  .peek-seen-list { display:flex; flex-direction:column; gap:0.35rem; }
  .peek-seen { display:flex; align-items:center; gap:0.5rem; font-size:0.85rem; }
  .peek-empty { font-size:0.78rem; color:var(--muted); }
  .peek-pop { position:fixed; left:50%; top:22%; transform:translateX(-50%); z-index:60; background:#2b1d12; color:#fff; border-radius:16px; padding:1rem 1.6rem;
    display:flex; flex-direction:column; align-items:center; gap:0.2rem; box-shadow:0 6px 0 rgba(0,0,0,0.25); animation:peekIn 160ms ease-out; }
  .peek-pop small { font-size:0.78rem; opacity:0.8; } .peek-pop b { font-size:1.9rem; font-family:var(--font-display); font-weight:700; } .peek-pop span { font-size:1.05rem; }
  @keyframes peekIn { from { opacity:0; transform:translate(-50%,-8px); } to { opacity:1; transform:translate(-50%,0); } }

  /* halftime 전환 화면 */
  .halftime-box { text-align:center; max-width:480px; }
  .halftime-box h2 { font-family:var(--font-display); font-size:1.7rem; margin:0 0 0.6rem; color:var(--gold); }
  .halftime-scores { display:flex; gap:1rem; justify-content:center; margin:1rem 0; }
  .halftime-scores .chip { background:var(--panel); border:1px solid var(--panel-line); border-radius:12px;
    padding:0.7rem 1.1rem; font-family:var(--font-display); }
  .halftime-scores .chip .n { display:block; font-size:1.3rem; font-weight:700; color:var(--gold); font-variant-numeric:tabular-nums; }

  .score-table { width:100%; border-collapse:collapse; margin-top:0.6rem; }
  .score-table th, .score-table td { text-align:left; padding:0.45rem 0.5rem; border-bottom:1px solid var(--panel-line); font-size:0.85rem; }
  .score-table th { color:var(--muted); font-weight:600; font-family:var(--font-display); }
  .winner-banner { text-align:center; padding:1.4rem; font-family:var(--font-display); font-size:1.6rem; font-weight:700; color:var(--gold); }
  /* 2026-08-28: 종료 화면 "다시 시작" 게이트 -- 결과 표들 사이에서도 눈에 띄도록 가운데 정렬 + 폭 제한. */
  .restart-gate { max-width:420px; margin:0 auto 1.4rem; text-align:center; }
  /* 2026-10-06: 제작 미니게임 레이어. #app 바깥(body 직속)에 둔다 -- render()가 상태 브로드캐스트마다
     #app 전체를 innerHTML로 갈아엎기 때문에, 미니게임을 #app 안에 넣으면 상대가 초밥을 제작하는 것 같은
     아무 브로드캐스트만 와도 진행 중이던 게임이 통째로 날아간다. 게임 자체의 스타일은 minigames.css. */
  #mg-layer { overflow-y:auto; align-items:flex-start; }
  #mg-layer .mg-wrap { margin:auto; width:100%; max-width:640px; }
  #mg-layer .mg-clock { text-align:center; margin:0 0 0.6rem; color:var(--bg); font-family:var(--font-display); font-size:0.9rem; letter-spacing:0.04em; }
  #mg-layer .mg-clock b { margin-left:0.35rem; font-size:1.15rem; color:var(--gold); font-variant-numeric:tabular-nums; }
  #mg-layer .mg-clock.low b { color:#ff7a66; }
  .cat-game { margin-top:0.15rem; font-size:0.68rem; font-weight:600; color:var(--muted); letter-spacing:0.02em; }
  .toast { position:fixed; left:50%; bottom:1.4rem; transform:translateX(-50%); background:var(--panel); border:1px solid var(--panel-line);
    padding:0.6rem 1.1rem; border-radius:999px; font-size:0.85rem; z-index:80; box-shadow:0 10px 30px rgba(0,0,0,0.4); }
  /* ================= 2026-10-12 POP 테마 =================
     초밥왕(빨강/원목) vs 스시헌터(남색) 콘셉트 이미지 기준. 입장·로비·결과 화면은 그림(hero.webp)을 쓰고,
     플레이 화면은 그림 없이 코드로만: 굵은 먹색 외곽선 + 딱딱한 오프셋 그림자 + 둥근 버튼 + Jua 제목체.
     body[data-team]이 king/hunter면 포인트색(--gold)이 팀색으로 바뀐다(톤 토큰만 바꾸므로 기존 컴포넌트가 따라온다). */
  :root { --pop-line:3px; --pop-shadow:0 4px 0 var(--ink); --pop-yellow:#ffc52e; --pop-cream:#fff6dc;
    --font-pop:'Jua','Noto Sans KR',sans-serif; --team:#e2691a; }
  body[data-team="king"] { --gold:#d9382e; --gold-ink:#fff; --team:#d9382e; --sky:#1f4fa8; }
  body[data-team="hunter"] { --gold:#1f4fa8; --gold-ink:#fff; --team:#1f4fa8; --sky:#d9382e; }
  html, body { background:var(--pop-cream); }
  body { background-image:radial-gradient(rgba(43,29,18,0.09) 1.6px, transparent 1.8px); background-size:22px 22px; }
  h1,h2,h3,h4,.btn,.eyebrow,.timer-num,.time-left-big,.rail-btn .rbt,.floor-btn,.rb-name,.my-chip,.ready-chip,.seat-badge,.room-chip,.round-pill,.winner-banner { font-family:var(--font-pop); }
  h1,h2,h3 { letter-spacing:0.01em; font-weight:400; }

  .topbar { background:#fff; border-bottom:var(--pop-line) solid var(--ink); box-shadow:0 4px 0 var(--team); }
  .topbar .eyebrow { color:var(--team); }
  .topbar h1 { font-weight:400; font-size:clamp(1.2rem,2.3vw,1.7rem); }
  .seat-badge { background:var(--team); color:#fff; border:2px solid var(--ink); box-shadow:0 2px 0 var(--ink); font-size:0.9rem; }
  .room-chip { background:#fff; color:var(--ink); border:2px solid var(--ink); box-shadow:0 2px 0 var(--ink); }

  .card { border:var(--pop-line) solid var(--ink); border-radius:20px; box-shadow:0 6px 0 var(--ink); background:#fff; }
  .btn { border:var(--pop-line) solid var(--ink); border-radius:14px; box-shadow:var(--pop-shadow); font-weight:400; font-size:1.02rem; padding:0.65rem 1.3rem; transition:transform .08s ease, box-shadow .08s ease, filter .12s ease; }
  .btn:active:not(:disabled) { transform:translateY(3px); box-shadow:0 1px 0 var(--ink); }
  .btn.primary { background:var(--team); color:#fff; }
  .btn.ghost { background:#fff; color:var(--ink); border:var(--pop-line) solid var(--ink); }
  .btn.danger { background:#e5483a; } .btn.ok { background:#2fa65a; }
  .btn:disabled { box-shadow:0 2px 0 var(--ink); }
  .btn.big { font-size:1.5rem; padding:1rem 1.2rem; border-radius:18px; }

  /* --- 시작 화면: 코드로 그린 평면 일러스트(왼쪽 초밥왕 가게 / 오른쪽 스시헌터 가게 / 아래 회전 레일). 입장 패널은 그 위에 얹는다 --- */
  .splash { position:relative; flex:1; min-height:100vh; display:flex; align-items:flex-end; justify-content:center; padding:1rem 1rem clamp(7rem,19vh,10rem); background:#f3e7c9; overflow:hidden; }
  .splash > .splash-panel { position:relative; z-index:2; }
  .splash-art { position:absolute; inset:0; z-index:0; overflow:hidden; pointer-events:none; }
  .sa-half { position:absolute; top:0; bottom:0; }
  .sa-king { left:0; width:100%; clip-path:polygon(0 0, 55% 0, 45% 100%, 0 100%); --c:#d93a2b; --cd:#a82a1f; background:var(--c); }
  .sa-hunter { left:0; width:100%; clip-path:polygon(55% 0, 100% 0, 100% 100%, 45% 100%); --c:#1f3f87; --cd:#162d63; background:var(--c); }
  .sa-half::before { content:""; position:absolute; inset:0; opacity:0.16;
    background:radial-gradient(circle at 50% 100%, transparent 0 38%, #fff 39% 42%, transparent 43% 55%, #fff 56% 59%, transparent 60%) 0 0 / 56px 28px; }
  .sa-half::after { content:""; position:absolute; left:0; right:0; top:0; height:7%; background:var(--cd); box-shadow:0 4px 0 rgba(0,0,0,0.18); }
  .sa-sign { position:absolute; top:23%; display:flex; align-items:center; gap:0.6rem; padding:0.35rem 1.4rem 0.45rem; background:#fff6dc; border:var(--pop-line) solid var(--ink); border-radius:16px; box-shadow:0 5px 0 var(--ink); color:var(--c); font-family:var(--font-pop); font-size:clamp(1.9rem,5.2vw,4.2rem); line-height:1.1; white-space:nowrap; }
  .sa-sign svg { width:1.05em; height:1.05em; fill:currentColor; flex:none; }
  .sa-king .sa-sign { left:5%; transform:rotate(-3deg); }
  .sa-hunter .sa-sign { right:5%; transform:rotate(3deg); }
  .sa-noren { position:absolute; top:7%; display:flex; gap:0.5%; }
  .sa-king .sa-noren { left:3%; width:44%; }
  .sa-hunter .sa-noren { right:3%; width:44%; }
  .sa-noren i { flex:1; height:clamp(3rem,13vh,7.5rem); background:#fff6dc; border:var(--pop-line) solid var(--ink); border-top:0; border-radius:0 0 8px 8px;
    clip-path:polygon(0 0,100% 0,100% 100%,50% 88%,0 100%); position:relative; }
  .sa-noren i::after { content:""; position:absolute; left:50%; top:34%; width:46%; aspect-ratio:1; transform:translateX(-50%); border-radius:50%; background:var(--c); }
  .sa-lamp { position:absolute; top:7%; width:clamp(2.2rem,5.4vw,4.2rem); }
  .sa-lamp::before { content:""; display:block; width:3px; height:clamp(1.2rem,5vh,3rem); margin:0 auto; background:var(--ink); }
  .sa-lamp b { display:block; aspect-ratio:0.8; border:var(--pop-line) solid var(--ink); border-radius:46%; background:linear-gradient(90deg, rgba(0,0,0,0.12), transparent 30%, rgba(255,255,255,0.35) 55%, transparent 80%), #fff6dc; box-shadow:inset 0 0.45em 0 -0.2em var(--c), inset 0 -0.45em 0 -0.2em var(--c); }
  .sa-vs { position:absolute; left:50%; top:30%; transform:translate(-50%,-50%) rotate(-8deg); width:clamp(4.2rem,11vw,8rem); aspect-ratio:1; border-radius:50%; background:var(--pop-yellow); border:var(--pop-line) solid var(--ink); box-shadow:0 6px 0 var(--ink);
    display:flex; align-items:center; justify-content:center; font-family:var(--font-pop); font-size:clamp(1.8rem,5vw,3.6rem); color:var(--ink); }
  .sa-belt { position:absolute; left:0; right:0; bottom:0; height:clamp(6rem,17vh,9rem); background:#2b1d12; border-top:var(--pop-line) solid var(--ink); overflow:hidden; }
  .sa-belt::before { content:""; position:absolute; left:0; right:0; top:0; height:0.9rem; background:repeating-linear-gradient(90deg, #4a3523 0 18px, #3a2a1b 18px 36px); }
  .sa-track { position:absolute; left:0; top:50%; display:flex; gap:clamp(1.4rem,4vw,3rem); transform:translateY(-38%); animation:sa-run 26s linear infinite; width:max-content; }
  .sa-plate { flex:none; width:clamp(4.4rem,10vh,6.4rem); aspect-ratio:1; border-radius:50%; background:#fff6dc; border:var(--pop-line) solid var(--ink); box-shadow:0 4px 0 rgba(0,0,0,0.35), inset 0 0 0 0.45rem var(--pc); display:flex; align-items:center; justify-content:center; }
  .sa-plate svg { width:68%; height:auto; display:block; }
  @keyframes sa-run { to { transform:translate(-50%,-38%); } }
  @media (prefers-reduced-motion:reduce) { .sa-track { animation:none; } }
  @media (max-width:640px) { .sa-sign { font-size:1.6rem; padding:0.25rem 0.8rem 0.35rem; } .sa-lamp { display:none; } }
  .splash-panel { width:min(620px,100%); padding:1rem 1.2rem 1.1rem; background:rgba(255,255,255,0.94); border:var(--pop-line) solid var(--ink); border-radius:22px; box-shadow:0 6px 0 var(--ink); text-align:center; }
  .splash-panel .team-row { margin:0 0 0.9rem; }
  .screen-links { margin-top:0.55rem; display:flex; flex-wrap:wrap; gap:0.4rem 0.6rem; justify-content:center; align-items:center; font-size:0.78rem; color:var(--muted); }
  .screen-links a { color:var(--ink); background:#fff; border:2px solid var(--ink); border-radius:999px; padding:0.1rem 0.7rem; text-decoration:none; font-family:var(--font-pop); box-shadow:0 2px 0 var(--ink); }
  .splash-panel .room-share { margin-top:0.9rem; padding-top:0.7rem; font-size:0.8rem; }
  .lobby-box { max-width:720px; width:100%; }
  .lobby-box h2 { font-size:clamp(1.7rem,4vw,2.4rem); margin:0 0 0.4rem; }
  .rule-note { background:var(--pop-yellow); border:2px solid var(--ink); border-radius:14px; padding:0.55rem 0.9rem; color:var(--ink) !important; font-weight:700; box-shadow:0 3px 0 var(--ink); }
  .lobby-box-deco { display:none; }
  .team-row { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:0.6rem; margin:0 0 1.2rem; }
  .team-card { --team:#999; display:flex; flex-direction:column; align-items:center; gap:0.15rem; padding:0.7rem 0.5rem; border:var(--pop-line) solid var(--ink); border-radius:16px;
    background:color-mix(in srgb, var(--team) 12%, #fff); box-shadow:0 4px 0 var(--ink); }
  .team-card .team-icon { width:36px; height:36px; color:var(--team); } .team-card .team-icon svg { width:100%; height:100%; display:block; }
  .team-card .team-name { font-family:var(--font-pop); font-weight:400; font-size:1.35rem; color:var(--team); }
  .team-card .team-state { font-size:0.8rem; font-weight:700; color:var(--muted); }
  .team-card.is-in .team-state { color:var(--ink); }
  .team-card.is-mine { background:var(--team); } .team-card.is-mine .team-icon, .team-card.is-mine .team-name, .team-card.is-mine .team-state { color:#fff; }
  .vs-badge { display:inline-flex; align-items:center; justify-content:center; width:3.2rem; height:3.2rem; border-radius:50%; background:var(--pop-yellow); border:var(--pop-line) solid var(--ink);
    box-shadow:0 3px 0 var(--ink); font-family:var(--font-pop); font-size:1.3rem; transform:rotate(-8deg); }
  .join-btn { background:var(--pop-yellow) !important; color:var(--ink) !important; }
  .room-share { border-top:2px dashed rgba(43,29,18,0.3); }
  .room-share strong { color:var(--ink); background:var(--pop-yellow); padding:0 0.5rem; border-radius:8px; border:2px solid var(--ink); }
  .ready-chip { border:2px solid var(--ink); background:#fff; color:var(--ink); box-shadow:0 2px 0 var(--ink); }
  .ready-chip.is-ready { background:#b9f0c6; color:var(--ink); border-color:var(--ink); }
  .space-hint { border:var(--pop-line) solid var(--ink); border-radius:14px; background:var(--pop-yellow); color:var(--ink); box-shadow:0 4px 0 var(--ink); font-family:var(--font-pop); width:fit-content; min-width:min(240px,86%); max-width:92%; box-sizing:border-box; display:flex; flex-direction:column; align-items:center; gap:0.35rem; padding:0.8rem 1.6rem; word-break:keep-all; letter-spacing:0.02em; }
  .space-hint .sh-key { font-family:var(--font-display); font-size:0.78rem; letter-spacing:0.18em; background:var(--ink); color:var(--pop-yellow); border-radius:6px; padding:0.12rem 0.7rem; }
  .space-hint .sh-label { font-size:1.45rem; line-height:1.2; white-space:nowrap; }
  .winner-banner { font-weight:400; font-size:2rem; color:var(--ink); background:var(--pop-yellow); border:var(--pop-line) solid var(--ink); border-radius:18px; box-shadow:0 5px 0 var(--ink); max-width:420px; margin:0 auto 1.2rem; padding:0.6rem 1rem; }
  .halftime-box h2 { font-weight:400; }
  .halftime-scores .chip, .round-result { border:var(--pop-line) solid var(--ink); border-radius:14px; box-shadow:0 3px 0 var(--ink); background:#fff; }
  .round-result { background:#e4f8e8; }
  .score-table th, .score-table td { border-bottom:2px solid rgba(43,29,18,0.15); }

  /* --- 타이머 / 사이드 --- */
  .timer-bar, .rv-bar, .mv-bar { background:#fff; border:2px solid var(--ink); }
  .timer-bar > i, .rv-bar > i { background:var(--team); }
  .timer-num, .time-left-big { color:var(--team); }
  .side-timer { border:var(--pop-line) solid var(--ink); border-radius:18px; box-shadow:0 5px 0 var(--ink); background:#fff; }
  .round-pill { background:var(--pop-yellow); color:var(--ink); border:2px solid var(--ink); box-shadow:0 2px 0 var(--ink); }
  .toast { border:var(--pop-line) solid var(--ink); box-shadow:0 4px 0 var(--ink); border-radius:16px; font-weight:700; }
  .overlay { background:rgba(43,29,18,0.9); }

  /* --- 제작 보드(레일) --- */
  .rail-mid { box-shadow:inset 0 0 0 3px var(--ink); }
  .rail-box { border:var(--pop-line) solid var(--ink); border-radius:14px; box-shadow:0 3px 0 var(--ink); }
  .rail-box .rb-name { border:2px solid var(--ink); border-radius:999px; font-weight:400; font-size:0.9rem; box-shadow:0 2px 0 var(--ink); }
  .rail-box .rb-game, .rail-box .cat-left { color:var(--ink); }
  .rail-box .pips { border:2px solid var(--ink); }
  .rail-box .pip svg { stroke:var(--ink); stroke-width:1.8; }
  .rail-box .stamp { border:var(--pop-line) solid var(--ink); border-radius:10px; font-weight:400; box-shadow:0 3px 0 var(--ink); }
  .rail-btn { border:var(--pop-line) solid var(--ink); border-bottom-width:var(--pop-line); box-shadow:0 4px 0 var(--ink); background:var(--c); color:var(--ink); border-radius:14px; }
  .rail-btn .rbp { color:var(--ink); opacity:0.75; }
  .rail-btn:hover:not(:disabled) { background:var(--c); filter:brightness(1.08); }
  .rail-btn:active:not(:disabled) { transform:translateY(3px); box-shadow:0 1px 0 var(--ink); border-bottom-width:var(--pop-line); }
  .rail-btn .rbt { font-weight:400; }
  .floor-btn { border:2px solid var(--ink); border-bottom-width:2px; box-shadow:0 3px 0 var(--ink); background:var(--c); color:var(--ink); font-weight:400; border-radius:10px; }
  .floor-btn:hover:not(.is-gone) { background:var(--c); filter:brightness(1.08); }
  .floor-btn:active:not(.is-gone) { transform:translateY(2px); box-shadow:0 1px 0 var(--ink); }
  .floor-btn.is-gone { box-shadow:none; background:transparent; }
  .my-chip { border:2px solid var(--ink); border-radius:999px; font-weight:400; background:#fff; }
  .rv { background:var(--pop-cream); }
  .rv-chip.phase { background:var(--pop-yellow); border:2px solid var(--ink); color:var(--ink); box-shadow:0 2px 0 var(--ink); }
  .rv-chip.room { background:#fff; border:2px solid var(--ink); color:var(--ink); box-shadow:0 2px 0 var(--ink); }
  .rv-side { border:var(--pop-line) solid var(--ink); box-shadow:0 3px 0 var(--ink); background:#fff; }
  .rv-side.is-busy { background:var(--c); }
  .rw-row { border:var(--pop-line) solid var(--ink); border-radius:14px; box-shadow:0 3px 0 var(--ink); background:#fff; }

  /* --- 회전 벨트 --- */
  .shaft { background:#ffe9b0; border:var(--pop-line) solid var(--ink); border-radius:20px; box-shadow:0 5px 0 var(--ink); }
  .belt-track { border:3cqw solid #3b4049; box-shadow:0 0 0 0.9cqw var(--ink); }
  .floor-stop .car { border:1cqw solid var(--ink); opacity:0.92; font-family:var(--font-pop); font-weight:400; font-size:7.5cqw; box-shadow:0 1cqw 0 var(--ink); }
  .floor-stop.current .car { box-shadow:0 1.6cqw 0 var(--ink), 0 0 0 1.4cqw var(--pop-yellow); }
  .belt-mark { font-family:var(--font-pop); font-weight:400; top:106cqw; }
  .invoice { border:2px solid var(--ink); border-radius:12px; background:#fff; box-shadow:0 3px 0 var(--ink); }
  .invoice .swatch { border:2px solid var(--ink); }
  .invoice .sticker { border:2px solid var(--ink); font-weight:400; font-family:var(--font-pop); }
  .invoice .sticker.pending { border-style:dashed; }
  .invoice.is-priority { background:#fff0b8; border-color:var(--ink); }
  .invoice .priority-flag { background:var(--pop-yellow); color:var(--ink); border:2px solid var(--ink); font-family:var(--font-pop); font-weight:400; }
  .invoice.pickable:hover { background:#fff6dc; }
  .priority-window, .choice-box, .thief-window { border:var(--pop-line) solid var(--ink); border-radius:16px; box-shadow:0 4px 0 var(--ink); background:#fff3c4; }
  .thief-window { background:#ffd9d3; }
  .priority-window h4, .choice-box h4 { color:var(--team); font-weight:400; font-size:1.1rem; } .thief-window h4 { color:var(--danger); font-weight:400; font-size:1.1rem; }
  .choice-list .invoice.chosen { background:#c9f1d2; }
  .player-col.me h3 { color:var(--team); }
  /* 서빙 칸 강조 + 방향 화살표 (2026-10-12) */
  .belt-ring { height:120cqw; }
  .belt-mark { top:112cqw; }
  .serve-frame { position:absolute; left:50%; top:86cqw; width:34cqw; height:34cqw; margin:-17cqw 0 0 -17cqw; border-radius:50%; border:2.2cqw solid var(--ink);
    box-shadow:0 0 0 2.4cqw var(--pop-yellow), 0 0 0 4.6cqw var(--ink); pointer-events:none; }
  .serve-arrow { position:absolute; top:92cqw; width:21cqw; margin-top:-10cqw; display:flex; flex-direction:column; align-items:center; pointer-events:none; }
  .serve-arrow.left { left:1.5cqw; } .serve-arrow.right { right:1.5cqw; }
  .serve-arrow.right svg { transform:scaleX(-1); }
  .serve-arrow svg { width:100%; height:auto; display:block; filter:drop-shadow(0 0.8cqw 0 var(--ink)); }
  .serve-arrow polygon { fill:var(--pop-yellow); stroke:var(--ink); stroke-width:3.5; stroke-linejoin:round; }
  .serve-arrow b { margin-top:1.8cqw; font-family:var(--font-pop); font-weight:400; font-size:5.6cqw; color:var(--ink); line-height:1; }
  .vote-buttons { flex-direction:row; gap:0.8rem; }
  .vote-buttons .btn { flex:1; font-size:1.25rem; padding:1rem 0.6rem; }
  .vote-arrow { display:inline-block; font-size:1.6em; line-height:0.8; vertical-align:-0.1em; }
  /* 벨트 접시: 참고 일러스트의 접시처럼 안쪽 링 + 하얀 물고기 문양 (이름은 아래에 작게) */
  .floor-stop .car { flex-direction:column; gap:0.2cqw; position:relative; }
  .floor-stop .car::before { content:""; position:absolute; inset:7%; border-radius:50%; border:0.5cqw solid rgba(255,255,255,0.5); pointer-events:none; }
  .floor-stop .car .car-fish { width:8.5cqw; height:auto; fill:rgba(255,255,255,0.92); stroke:rgba(0,0,0,0.25); stroke-width:1; }
  .floor-stop .car .car-fish .eye { fill:rgba(0,0,0,0.45); stroke:none; }
  .floor-stop .car b { font-weight:400; font-size:6.4cqw; line-height:1; }
  /* 가독성: 글자는 왼쪽 칸, 초밥 그림은 오른쪽 칸 안에만 (겹치지 않게). 점은 작게 + 줄바꿈 */
  .rail-box { padding:0.35rem 46% 0.35rem 0.4rem; box-sizing:border-box; }
  .rail-box .cell-art { inset:8% 3% 8% auto; width:42%; opacity:1; filter:drop-shadow(0 3px 0 rgba(0,0,0,0.25)); background-size:contain; background-position:center; }
  .rail-box::after { content:""; position:absolute; top:0; bottom:0; right:0; width:46%; z-index:0; background:rgba(255,255,255,0.28); }
  .rail-box .rb-name { font-size:0.82rem; padding:0.12rem 0.55rem; white-space:nowrap; }
  .rail-box .rb-game { font-size:0.7rem; }
  .rail-box .pips { flex-wrap:wrap; justify-content:center; gap:2px; padding:3px 5px; max-width:100%; box-sizing:border-box; }
  .rail-box .pip { width:14px; height:9px; }
  .rail-box::before { background:linear-gradient(180deg,rgba(255,255,255,0.18),rgba(0,0,0,0.05)); }
  .rail-box .cat-left { background:rgba(255,255,255,0.9); border:2px solid var(--ink); border-radius:999px; padding:0 0.55rem; color:var(--ink); }
  .rail-box .rb-game { background:rgba(255,255,255,0.9); border:2px solid var(--ink); }
  .inv-sushi { width:3.1rem; }
  .inv-sushi-img { width:100%; height:auto; display:block; filter:drop-shadow(0 2px 0 rgba(0,0,0,0.25)); }
  /* 접시 색 표시 (번호는 안 쓴다): 색 동그라미 + "초록 접시" */
  .invoice .t .inv-type { white-space:nowrap; }
  .plate-tag { display:inline-flex; align-items:center; gap:0.35em; font-weight:700; }
  .plate-dot { display:inline-block; width:1.05em; height:1.05em; flex:none; border-radius:50%; background:var(--p); border:2px solid var(--ink); box-shadow:inset 0 0 0 2px rgba(255,255,255,0.45); }
</style>
</head><body>
<div id="app"></div>
<div class="overlay hidden" id="mg-layer"></div>
"""

APP_JS_TEMPLATE = r"""
(function () {
  "use strict";

  var TYPES = @@TYPES_JSON@@;
  // 2026-08-28: 전반/후반이 서로 다른 21장 퍼즐 이미지 세트를 쓴다 (build_client.py의 REF_DIR_1/
  // REF_DIR_2 참고). 보드 구조(id/catIdx/num)는 동일하고 src(이미지)만 다르므로 배열을 통째로
  // 두 벌 두고, cellMeta(id, half)가 half에 맞는 쪽에서 찾는다.
  var CELLS_1 = @@CELLS_1_JSON@@;
  var CELLS_2 = @@CELLS_2_JSON@@;
  var FLOORS = @@FLOORS_JSON@@;
  var ROOMS = @@ROOMS_JSON@@;
  // 2026-08-27 신설: 좌석 선택 화면에서 고르는 가상 셰프 5종 (game-data.js와 동일 -- 서버가
  // pickCourier에서 이 key 목록으로 유효성 검사도 한다). 실제 셰프 로고를 흉내내면 상표권
  // 문제가 있어서 완전 창작 브랜드로 대체했다 (HANDOVER.md 3.6 참고).
  var COURIERS = @@COURIERS_JSON@@;
  // COURIERS와 순서를 맞춘 손그림 flat 아이콘 (SVG, 순수 표시용이라 서버/game-data.js엔 없음).
  // 2026-08-28 리스킨: 사용자가 준 새 로고 세트에 맞춰 교체 (COURIERS 순서와 동일 -- 하루스시/파도초밥/
  // 참치당/여우초밥/청해스시). 프라이팬+계란(하루스시), 다이아몬드 직인+바코드선(파도초밥),
  // 방패+상자(참치당), 지그재그 화살표(여우초밥), 우편함(청해스시).
  var COURIER_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9l4 3 4-6 4 6 4-3-1.5 7h-13z"></path><path d="M5.5 19h13"></path></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12c3-5 9-6 13-3l5-3v12l-5-3c-4 3-10 2-13-3z"></path><circle cx="8" cy="11" r="1" fill="currentColor"></circle></svg>',
  ];
  // catIdx로 인덱싱하는 종류별 보드-칸 배경 일러스트 (위 BOX_ART_DIR 참고). CELLS[].src(칸마다 다른
  // 퍼즐 이미지, 오버레이 전용)와는 별개 -- 이건 보드 위 21칸 자체의 배경으로 쓴다.
  var BOX_ART = @@BOX_ART_JSON@@;
  // 남은 개수 표시용 물고기(단순 타원 몸통 + 꼬리). 색/테두리는 CSS가 입힌다.
  var FISH_PIP = '<svg viewBox="0 0 26 14" aria-hidden="true"><path d="M2 7c0-3.4 3.6-5.6 8-5.6 3.2 0 5.8 1.2 7.2 3.2L24 1.6v10.8l-6.8-3.2C15.8 11.2 13.2 12.6 10 12.6 5.6 12.6 2 10.4 2 7z"/><circle class="eye" cx="6.2" cy="5.6" r="1.1"/></svg>';
  // 스페이스바 안내 버튼: 키캡 + 라벨 두 줄로 나눠, 좁아도 글자가 어색하게 끊기지 않게 한다.
  function spaceHint(label) {
    return '<div class="space-hint"><span class="sh-key">SPACE</span><span class="sh-label">' + label + '</span></div>';
  }
  var SUSHI_IMG = @@SUSHI_IMG_JSON@@;   // 초밥 키 -> 일러스트(data URI, 투명 컷아웃)
  // 보드 한 줄(종류)의 배경 일러스트: 그 종류의 초밥 컷아웃. 없으면 예전 상자 그림.
  function railArt(catIdx) {
    var k = TYPES[catIdx] && TYPES[catIdx].sushi && TYPES[catIdx].sushi[0];
    return (k && SUSHI_IMG[k]) || BOX_ART[catIdx];
  }
  // 2026-08-27 리스킨: board-label 카드용 평평한 라인 아이콘 (TYPES 순서와 동일 -- 트럭/깨진 유리잔/
  // 보석/체크마크 건물). box_art/의 3D 상자 일러스트와는 다른, 손으로 그린 별도의 단순한 SVG -- 그
  // 일러스트는 라벨 카드 안에 아이콘 크기로 넣기엔 스타일이 안 맞아서(입체 상자 그림 vs 평면 라인
  // 아이콘), 참고 포스터의 "구분/요금" 카드가 쓰는 플랫 아이콘 언어에 맞춰 새로 그렸다.
  var CAT_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="9" width="18" height="7" rx="2"></rect><path d="M6 9V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"></path><path d="M12 5v11"></path></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="11" rx="8" ry="4"></ellipse><path d="M4 11v3c0 2 4 4 8 4s8-2 8-4v-3"></path><circle cx="9" cy="10.5" r="0.8" fill="currentColor"></circle><circle cx="12" cy="9.8" r="0.8" fill="currentColor"></circle><circle cx="15" cy="10.5" r="0.8" fill="currentColor"></circle></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l4.5-6h9L21 9"></path><path d="M3 9l9 12 9-12"></path><path d="M3 9h18"></path><path d="M9 3l3 6 3-6"></path></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 15c0-4 4-7 9-7 5 0 9 3 9 7z"></path><path d="M3 15h18v2H3z"></path><path d="M8 11c1 1 1 3 0 4M12 10c1 1 1 4 0 5M16 11c1 1 1 3 0 4"></path></svg>',
  ];
  // ---------- 효과음 (2026-10-12): 파일 없이 WebAudio로 합성. 브라우저 정책상 첫 클릭/키 입력 뒤부터 소리가 난다. ----------
  // 켜짐/꺼짐은 화면 왼쪽 아래 스피커 버튼 (localStorage에 기억, 못 쓰는 환경이면 그냥 켜짐).
  var SFX = (function () {
    var ctx = null, on = true;
    try { on = localStorage.getItem("bp-sfx") !== "off"; } catch (e) {}
    var SCALE = [523.25, 587.33, 659.25, 783.99, 880.0, 987.77]; // 접시 6개 = 도레미솔라시 (접시마다 고정 음)
    function unlock() {
      if (!ctx) { try { var AC = window.AudioContext || window.webkitAudioContext; if (AC) ctx = new AC(); } catch (e) { ctx = null; } }
      if (ctx && ctx.state === "suspended") { try { ctx.resume(); } catch (e) {} }
    }
    function tone(freq, dur, type, vol, delay, slideTo) {
      if (!on || !ctx || ctx.state !== "running") return;
      var t0 = ctx.currentTime + (delay || 0), o = ctx.createOscillator(), g = ctx.createGain();
      o.type = type || "sine"; o.frequency.setValueAtTime(freq, t0);
      if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); g.connect(ctx.destination); o.start(t0); o.stop(t0 + dur + 0.02);
    }
    return {
      unlock: unlock,
      isOn: function () { return on; },
      toggle: function () { on = !on; try { localStorage.setItem("bp-sfx", on ? "on" : "off"); } catch (e) {} unlock(); if (on) tone(784, 0.1, "triangle", 0.12); return on; },
      click: function () { tone(880, 0.05, "triangle", 0.07); },
      key: function () { tone(660, 0.03, "triangle", 0.04); },
      select: function () { tone(660, 0.08, "triangle", 0.12); tone(990, 0.12, "triangle", 0.12, 0.07); },
      plate: function (i) { var f = SCALE[((i % 6) + 6) % 6]; tone(f, 0.16, "sine", 0.14); tone(f * 2, 0.08, "sine", 0.04); },
      ok: function () { tone(659, 0.12, "triangle", 0.13); tone(784, 0.12, "triangle", 0.13, 0.1); tone(1047, 0.22, "triangle", 0.13, 0.2); },
      bad: function () { tone(220, 0.25, "sawtooth", 0.09, 0, 110); },
      peek: function () { tone(1318, 0.1, "sine", 0.08); tone(1760, 0.18, "sine", 0.08, 0.09); }
    };
  })();
  function sfxButton() {
    if (document.getElementById("sfx-toggle")) return;
    var b = document.createElement("button");
    b.id = "sfx-toggle"; b.type = "button"; b.className = "sfx-toggle";
    function paint() {
      var on = SFX.isOn();
      b.setAttribute("aria-label", on ? "효과음 끄기" : "효과음 켜기"); b.setAttribute("aria-pressed", on ? "true" : "false");
      b.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/>'
        + (on ? '<path d="M16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12"/>' : '<path d="M17 9l5 6M22 9l-5 6"/>') + '</svg>';
    }
    b.addEventListener("click", function (e) { e.stopPropagation(); SFX.toggle(); paint(); });
    paint(); document.body.appendChild(b);
  }
  // 버튼을 누를 때마다: 접시 버튼은 그 접시 음, 초밥 종류/미니게임 선택은 선택음, 나머지는 짧은 틱.
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("button, [data-action]");
    if (!t || t.disabled || t.id === "sfx-toggle") return;
    SFX.unlock();
    var plate = null;
    if (t.hasAttribute("data-floor-idx")) plate = parseInt(t.getAttribute("data-floor-idx"), 10);
    else { var m = /^fixed-floor-(\d+)$/.exec(t.getAttribute("data-cell") || ""); if (m) plate = parseInt(m[1], 10) - 1; }
    var a = t.getAttribute("data-action") || "";
    if (plate !== null && !isNaN(plate)) SFX.plate(plate);
    else if (a === "open-type" || a === "open-cell" || a === "rail-press" || a === "start-peek" || a === "use-peek") SFX.select();
    else SFX.click();
  }, true);
  document.addEventListener("keydown", function (e) {
    SFX.unlock();
    if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
    if (typeof mg !== "undefined" && mg && (e.code === "Space" || e.code.indexOf("Arrow") === 0 || e.code === "Enter")) SFX.key(); // 미니게임 조작
  }, true);
  document.addEventListener("pointerdown", function () { SFX.unlock(); }, true);

  var ELEVATOR_ROUNDS = @@ELEVATOR_ROUNDS@@;
  var SECURE_PHASE_MS = @@SECURE_PHASE_MS@@;
  var VOTE_MS = @@VOTE_MS@@;
  var PRIORITY_MULTIPLIER = @@PRIORITY_MULTIPLIER@@;
  var SAME_FLOOR_CHOICE_MS = @@SAME_FLOOR_CHOICE_MS@@;
  var HALVES = @@HALVES@@;
  var THIEF_PLACE_MS = @@THIEF_PLACE_MS@@;
  var PRIORITY_PICK_MS = @@PRIORITY_PICK_MS@@;
  // 지정 초밥을 제외한 나머지 종류는 칸 번호 대신 A/B/C/D/E로 표기한다 (사용자 요청, 2026-08-27: 대문자로 변경).
  var CELL_LETTERS = ["A", "B", "C", "D", "E", "F"];

  var ROOM = (new URLSearchParams(window.location.search).get("room") || "").trim().toUpperCase();
  // 2026-10-06: ?view=main 이면 "메인 모니터" 화면 -- 좌석을 잡지 않고 상태만 받아서 큰 화면으로 보여준다
  // (renderMain 참고). 서버 입장에서는 좌석 없는 관전 연결이라 게임 진행에는 아무 영향이 없다.
  var MAIN = /[?&]view=main(&|$)/.test(window.location.search);
  if (MAIN) document.body.classList.add("main-view");
  // 2026-10-07: /rail (또는 ?view=rail) 이면 "레일 사이트" -- 두 플레이어가 같이 보는 공용 화면. 좌석을 잡지 않고, 왼쪽(1번)/오른쪽(2번) 버튼을
  // 누르면 서버가 해당 플레이어의 기기에 그 종류의 미니게임을 띄운다 (renderRail 참고). 접속해 있는 동안 플레이어 화면은 레일 모드가 된다.
  var RAIL = window.location.pathname === "/rail" || /[?&]view=rail(&|$)/.test(window.location.search);
  if (RAIL) document.body.classList.add("rail-view");
  // 서버가 상태 메시지마다 실어 보내는 레일 정보 { count: 접속 중인 레일 화면 수, busy: {"1":bool,"2":bool} }.
  var railInfo = { count: 0, busy: { "1": false, "2": false } };
  // 서버 시계와 이 기기 시계의 차이 (서버가 상태 메시지마다 now를 실어 보낸다). 메인 모니터의 카운트다운에만 쓴다.
  var clockOffset = 0;
  function nowMs() { return Date.now() + clockOffset; }

  // ---------- identity: per-tab, survives a refresh (sessionStorage), but a second tab on the
  // same device gets its own id -- so two tabs can hold the two different seats without one
  // stealing the other's seat on reconnect. ----------
  function getClientId() {
    try {
      var id = sessionStorage.getItem("bp-client-id");
      if (!id) { id = "c-" + Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem("bp-client-id", id); }
      return id;
    } catch (e) { return "c-" + Math.random().toString(36).slice(2); }
  }
  var CLIENT_ID = getClientId();
  function mySeat() { try { return sessionStorage.getItem("bp-seat"); } catch (e) { return null; } }
  function setMySeat(s) { try { sessionStorage.setItem("bp-seat", s); } catch (e) {} }

  var state = null; // populated by the first "state" message from the server
  var local = { openCellId: null, toast: null, pending: {} };
  // 5초 이상 아무것도 안 하면(평가 G3) 눌러야 할 버튼이 깜빡인다: 마지막 조작 시각. 클릭/키 입력과 게임 종료 때 갱신된다.
  var lastAct = Date.now();
  var INTRO_MS = 10000;
  // 방금 완료 신호를 보낸 칸(서버 브로드캐스트가 오기 전) -- 종류 버튼이 같은 칸을 또 골라 중복 완료로 무시되는 걸 막는다.
  function markPending(id) { local.pending[id] = Date.now(); }
  var wsConnected = false;

  // half(1|2)로 전반/후반 이미지 세트를 고른다 -- id/catIdx/num은 두 세트가 동일하고 src(이미지)만 다르다.
  function cellMeta(id, half) {
    var arr = half === 2 ? CELLS_2 : CELLS_1;
    for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
    return null;
  }

  // ---------- scoring (pure display functions -- server owns deliveredRound/floorIdx/stolen, this
  // just formats them; no risk of drifting from the server since it's a pure fn of server data.
  // Must stay in exact sync with scoreInvoice/resultLabel/totalScore in game-room.js -- see
  // HANDOVER.md 4.3. ----------
  function scoreInvoice(inv) {
    var t = TYPES[inv.catIdx];
    if (inv.stolen) return -t.penalty;
    if (inv.deliveredRound === null) return -t.penalty;
    var base = t.reward;
    return inv.deliveredWasPriority ? base * PRIORITY_MULTIPLIER : base;
  }
  function resultLabel(inv) {
    // 2026-08-27: 도난당한 주문표도 "미서빙"으로 통합 표기 (사용자 요청 -- 서빙이 안 됐으니까).
    // 페널티/소진 로직(scoreInvoice, deliveredRound 처리)은 그대로, 영구 라벨만 통일했다. 그 라운드의
    // 실시간 안내(renderDeliveredCallout의 "초밥도둑에게 도난당했어요!")는 별개로 남겨둠.
    if (inv.stolen) return "미서빙";
    return inv.deliveredRound === null ? "미서빙" : "성공";
  }
  function totalScore(seat, st) {
    return st.players[seat].invoices.reduce(function (sum, inv) { return sum + scoreInvoice(inv); }, 0);
  }
  function fmtWon(n) {
    var sign = n > 0 ? "+" : (n < 0 ? "-" : "");
    return sign + Math.abs(n).toLocaleString("ko-KR") + "원";
  }

  // ---------- websocket sync: the server is the single source of truth. every action is just a
  // fire-and-forget message; the resulting full state comes back (to everyone in the room) as
  // a broadcast, and render() runs off of that. no client-side reducers, no conflict handling,
  // no pending-action retry queue -- none of that machinery is needed once a real server owns
  // the state and processes messages one at a time. ----------
  var ws = null;
  function wsUrl() {
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + window.location.host + "/ws?room=" + encodeURIComponent(ROOM) + (RAIL ? "&role=rail" : "");
  }
  // 상태가 바뀔 때의 효과음: 벨트가 다른 접시로 움직이면 그 접시 음(둘 다 듣는다), 라운드 결과가 나오면 내 서빙 결과음, 엿보기 도착음.
  function sfxOnState(prev, st) {
    try {
      if (!prev || !st || st.phase !== "elevator" || prev.phase !== "elevator") return;
      var a = prev.elevator, b = st.elevator;
      if (a.round === b.round && a.floorIdx !== b.floorIdx) SFX.plate(b.floorIdx);
      if (a.state !== "result" && b.state === "result" && !MAIN && !RAIL) {
        var seat = mySeat(), last = b.log && b.log[b.log.length - 1];
        if (seat && last && last.round === b.round) {
          var mine = null; last.delivered.forEach(function (d) { if (d.seat === seat) mine = d; });
          if (mine) { if (mine.stolen) SFX.bad(); else SFX.ok(); }
        }
      }
    } catch (e) { /* 효과음 실패는 게임에 영향 없음 */ }
  }
  function connectWS() {
    if (!ROOM) return;
    try { ws = new WebSocket(wsUrl()); } catch (e) { setTimeout(connectWS, 1500); return; }
    ws.onopen = function () {
      wsConnected = true;
      renderConnBanner();
      var seat = RAIL ? null : mySeat();
      ws.send(JSON.stringify({ type: "hello", clientId: CLIENT_ID, seat: seat }));
      if (seat) ws.send(JSON.stringify({ type: "pick-seat", clientId: CLIENT_ID, seat: seat })); // reclaim after reconnect
    };
    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (!msg) return;
      if (msg.type === "state") {
        // the elevator's floorIdx is now real, server-authoritative position -- every click (from
        // either player) already moves it for real before this broadcast goes out, so a plain
        // re-render is enough to show the car actually stepping; no client-side simulation needed.
        var prevState = state;
        state = msg.state;
        sfxOnState(prevState, state);
        if (typeof msg.now === "number") clockOffset = msg.now - Date.now();
        if (msg.rail) railInfo = msg.rail;
        // 2026-08-27: "pick-courier"는 좌석 번호를 클라이언트가 미리 못 정하므로(서버가 정해서
        // 돌려줌 -- game-room.js의 pickCourier), 낙관적으로 sessionStorage에 세팅하는 대신 여기서
        // 매 상태 브로드캐스트마다 "아직 내 좌석을 모르는 상태에서 내 clientId가 어느 좌석 주인이
        // 됐는지"를 확인해서 확정한다. 한 번 확정되면(mySeat() !== null) 더 이상 스캔 안 함.
        if (!mySeat()) {
          ["1", "2"].forEach(function (s) { if (state.seatOwners[s] === CLIENT_ID) setMySeat(s); });
        }
        render();
        syncMiniGame();
      }
      else if (msg.type === "error") { handleWsError(msg); }
      else if (msg.type === "open-game") { onRailOpenGame(msg.cellId); }
      else if (msg.type === "peek-reveal") { onPeekReveal(msg); }
    };
    ws.onclose = function () { wsConnected = false; renderConnBanner(); setTimeout(connectWS, 1200); };
    ws.onerror = function () {};
  }
  function send(action) {
    action.clientId = CLIENT_ID;
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(action));
  }
  function handleWsError(msg) {
    if (msg.code === "seat_taken") {
      try { sessionStorage.removeItem("bp-seat"); } catch (e) {}
      showToast(seatName(msg.seat, state) + " 자리는 이미 다른 사람이 앉았어요.");
      render();
    }
    else if (msg.code === "room_full") {
      showToast("이 방은 이미 두 명이 다 찼어요.");
      render();
    }
  }
  function renderConnBanner() {
    var el = document.getElementById("conn-banner");
    if (wsConnected) { if (el) el.remove(); return; }
    if (el) return;
    var d = document.createElement("div");
    d.id = "conn-banner"; d.className = "conn-banner"; d.textContent = "서버와 연결이 끊겼어요 — 재연결 시도 중...";
    document.body.appendChild(d);
  }

  // ---------- rendering ----------
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
  function fmtClock(ms) {
    if (ms < 0) ms = 0;
    var s = Math.ceil(ms / 1000);
    var m = Math.floor(s / 60); s = s % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  // Combines a floor + room slot into a single realistic-looking building room code, e.g.
  // "401호" (4F, slot 1) or "B03호" (B1, slot 3) -- floorIdx/room are still tracked separately
  // server-side (floorIdx drives elevator delivery-matching), this is purely a display format.
  // 2026-10-12 (사용자: "접시 색만 중요해. 몇번인지는 알릴 필요 없음"): 번호는 더 이상 화면에 안 낸다. 서빙은 접시 색으로만 정해진다
  //   (inv.room은 서버에 남아 있지만 표시 전용 값이라 아무 데도 쓰지 않는다). 함수 이름은 그대로 두고 "접시 색"만 돌려준다.
  function roomCode(floorIdx) {
    return FLOORS[floorIdx] + " 접시";
  }
  // 접시 그림(색 동그라미) + "초록 접시" -- 주문표 목록/결과 표용 HTML.
  function plateTag(floorIdx) {
    return '<span class="plate-tag"><i class="plate-dot" style="--p:' + PLATE_HEX[floorIdx] + '"></i>' + esc(roomCode(floorIdx)) + '</span>';
  }
  // 제작된 초밥의 구체적인 종류 (inv.sushi = TYPES[catIdx].sushi 중 하나, 예: "salmon" -> "연어"). 이름/그림은 minigames.js의 SUSHI.
  function sushiShort(key) { return key && window.MiniGames && MiniGames.SUSHI[key] ? MiniGames.SUSHI[key] : ""; }
  function sushiIcon(key) {
    if (key && SUSHI_IMG[key]) return '<span class="inv-sushi"><img class="inv-sushi-img" alt="" src="' + SUSHI_IMG[key] + '"></span>';
    return key && window.MiniGames && MiniGames.SUSHI[key] ? '<span class="inv-sushi">' + MiniGames.sushiSvg(key, "inv-sushi-svg") + '</span>' : '';
  }
  function invTitle(inv) {
    var t = TYPES[inv.catIdx], sn = sushiShort(inv.sushi);
    return sn ? esc(sn) + ' 초밥 <small class="inv-type">' + fmtWon(t.reward) + '</small>' : esc(t.name) + ' <small class="inv-type">' + fmtWon(t.reward) + '</small>';
  }
  function chipText(inv) { var sn = sushiShort(inv.sushi); return (sn ? sn + ' · ' : '') + FLOORS[inv.floorIdx]; }
  function findInvoiceById(id) {
    if (!state || !state.players) return null;
    var out = null;
    ["1", "2"].forEach(function (sn) { (state.players[sn].invoices || []).forEach(function (v) { if (v.id === id) out = v; }); });
    return out;
  }
  // 칸을 열 때마다 이번에 만들 초밥을 클라이언트가 무작위로 고른다 (TYPES[].sushi 중). 서버는 그 키가 목록에 있는지만 검증해 주문표에 붙인다.
  var sushiPicks = {};
  function newSushiPick(cellId) {
    var m = cellMeta(cellId, state.half), pool = (m && TYPES[m.catIdx].sushi) || [];
    sushiPicks[cellId] = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;
    return sushiPicks[cellId];
  }
  function sushiFor(cellId) { return sushiPicks[cellId] || newSushiPick(cellId); }

  // ---------- 셰프(courier) 표시 이름 -- 2026-08-27 신설 ----------
  // "플레이어 1/2" 대신 화면 곳곳에서 좌석을 부를 때 이걸 쓴다. 아직 그 좌석이 셰프를 안 골랐으면
  // (게임 시작 전 극히 짧은 순간, 혹은 옛 상태 호환) "플레이어 N"으로 그냥 폴백한다.
  function courierByKey(key) {
    for (var i = 0; i < COURIERS.length; i++) if (COURIERS[i].key === key) return COURIERS[i];
    return null;
  }
  function seatName(seat, st) {
    var key = st && st.courierPick && st.courierPick[seat];
    var c = key ? courierByKey(key) : null;
    return c ? c.name : ("플레이어 " + seat);
  }

  // 시작(셰프 선택) 화면 뒤에 옅게 흩뿌리는 장식용 초밥상자 라인아트 -- 2026-08-27 신설
  // (사용자 요청: "처음 시작 페이지에 초밥상자 모양이 좀 그려져 있으면 좋을 것 같아"). 순수 장식이라
  // 클릭 불가(pointer-events:none)이고, 위치/크기/회전/색만 다른 같은 SVG 하나를 4번 찍는다.
  function renderLobbyBoxes() {
    var BOX_SVG = '<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"><path d="M6 14 20 8 34 14 34 30 20 36 6 30Z"></path><path d="M6 14 20 20 34 14M20 20V36"></path></svg>';
    function deco(style) { return '<span class="lobby-box-deco" style="' + style + '">' + BOX_SVG + '</span>'; }
    return deco('top:-4%;left:-3%;width:88px;height:88px;color:var(--gold);opacity:0.16;transform:rotate(-12deg);')
      + deco('top:60%;left:-6%;width:66px;height:66px;color:var(--sky);opacity:0.14;transform:rotate(9deg);')
      + deco('top:-7%;right:-2%;width:74px;height:74px;color:var(--ok);opacity:0.15;transform:rotate(13deg);')
      + deco('top:56%;right:-5%;width:92px;height:92px;color:var(--danger);opacity:0.12;transform:rotate(-9deg);');
  }

  // 2026-10-12: 가게 고르기를 없애고 팀을 입장 순서로 고정했다 -- 먼저 들어온 사람이 초밥왕, 다음 사람이 스시헌터.
  function teamCard(i) {
    var c = COURIERS[i], sn = String(i + 1);
    var owner = state && state.seatOwners && state.seatOwners[sn];
    var mine = owner && owner === CLIENT_ID;
    return '<div class="team-card team-' + c.key + (owner ? ' is-in' : '') + (mine ? ' is-mine' : '') + '" style="--team:' + c.color + '">'
      + '<span class="team-icon">' + COURIER_ICONS[i] + '</span>'
      + '<b class="team-name">' + esc(c.name) + '</b>'
      + '<span class="team-state">' + (mine ? '내 자리' : (owner ? '입장 완료' : '대기 중')) + '</span></div>';
  }
  // 시작 화면 배경 일러스트(코드로 그림). 사진 같은 질감 없이 평면 도형 + 팀 색 + 회전 레일만으로 구성한다.
  var CROWN_SVG = '<svg viewBox="0 0 24 20" aria-hidden="true"><path d="M2 5l5.5 5L12 2l4.5 8L22 5l-2 13H4z"/></svg>';
  var FISH_SVG = '<svg viewBox="0 0 26 14" aria-hidden="true"><path d="M2 7c0-3.4 3.6-5.6 8-5.6 3.2 0 5.8 1.2 7.2 3.2L24 1.6v10.8l-6.8-3.2C15.8 11.2 13.2 12.6 10 12.6 5.6 12.6 2 10.4 2 7z"/></svg>';
  function splashArt() {
    var keys = ["egg", "salmon", "whitefish", "eel"], cols = ["#d93a2b", "#1f3f87", "#f2b233", "#2f9e6a"], plates = "", i;
    for (i = 0; i < 16; i++) {
      var k = keys[i % 4];
      plates += '<span class="sa-plate" style="--pc:' + cols[(i * 3) % 4] + '">' + (window.MiniGames && MiniGames.SUSHI[k] ? MiniGames.sushiSvg(k, "sa-sushi") : '') + '</span>';
    }
    return '<div class="splash-art" aria-hidden="true">'
      + '<div class="sa-half sa-king"><div class="sa-noren"><i></i><i></i><i></i><i></i></div><div class="sa-sign">' + CROWN_SVG + '초밥왕</div></div>'
      + '<div class="sa-half sa-hunter"><div class="sa-noren"><i></i><i></i><i></i><i></i></div><div class="sa-sign">스시헌터' + FISH_SVG + '</div></div>'
      + '<div class="sa-vs">VS</div>'
      + '<div class="sa-belt"><div class="sa-track">' + plates + plates + '</div></div></div>';
  }
  function renderSeatPicker() {
    var roomFull = state && state.seatOwners["1"] && state.seatOwners["2"]
      && state.seatOwners["1"] !== CLIENT_ID && state.seatOwners["2"] !== CLIENT_ID;
    var nextTeam = state && !state.seatOwners["1"] ? COURIERS[0] : COURIERS[1];
    // 2026-10-12: 게임 시작 화면 = 콘셉트 이미지가 화면 전체(배경). 그림 위에 입장 패널만 얹는다 (카드 안에 일러스트를 끼우는 구조가 아님).
    return '<div class="splash">' + splashArt() + '<div class="splash-panel">'
      + '<div class="team-row">' + teamCard(0) + '<span class="vs-badge">VS</span>' + teamCard(1) + '</div>'
      + '<button class="btn primary big join-btn" data-action="join-team"' + (roomFull ? ' disabled' : '') + '>'
      + (roomFull ? '방이 가득 찼어요' : ('입장하기 · ' + esc(nextTeam.name) + '로 시작')) + '</button>'
      + '<div class="room-share">먼저 들어온 사람이 초밥왕, 다음 사람이 스시헌터 · 방 코드 <strong>' + esc(ROOM) + '</strong><br>상대방에게는 지금 이 페이지의 링크를 그대로 보내주면 같은 방으로 들어와요.</div>'
      + '<div class="screen-links">초밥 확보(레일)·관전(메인)은 다른 화면에서: <a href="/rail?room=' + encodeURIComponent(ROOM) + '" target="_blank" rel="noopener">레일 화면 열기</a><a href="/?room=' + encodeURIComponent(ROOM) + '&view=main" target="_blank" rel="noopener">메인 화면 열기</a></div>'
      + '</div></div>';
  }

  function renderTopbar(st, seat) {
    var phaseLabel = { lobby: "대기 중", secure: "초밥 제작", elevator: "회전 벨트", halftime: "하프타임", end: "결과" }[st.phase] || "";
    if (st.half && (st.phase === "secure" || st.phase === "elevator")) {
      phaseLabel += " · " + (st.half === 1 ? "전반" : "후반");
    }
    return '<div class="topbar"><div class="brand"><span class="eyebrow">BeatPhobia · Live</span><h1>초밥 서빙 게임 — ' + phaseLabel + '</h1></div>'
      + '<div class="right"><span class="room-chip">방 ' + esc(ROOM) + '</span>'
      + '<span class="seat-badge">' + (seat ? ("내 팀 · " + seatName(seat, st)) : "입장 전") + '</span></div></div>';
  }

  function renderLobby(st, seat) {
    var otherSeat = seat === "1" ? "2" : (seat === "2" ? "1" : null);
    var mine = seat ? !!st.ready[seat] : false;
    var other = otherSeat ? !!st.ready[otherSeat] : false;
    return '<main class="stage"><div class="center-screen"><div class="lobby-box card">'
      + '<h2>' + esc(seatName("1", st)) + ' VS ' + esc(seatName("2", st)) + '</h2>'
      + '<p class="rule-note">초밥마다 판매가가 달라요(계란 1,000 · 흰살생선 2,000 · 연어 1,500 · 장어 3,000). 만든 초밥을 라운드 안에 못 팔면(서빙 못 함 · 도둑에게 뺏김) <b>원재료값</b>만큼 점수가 깎여요.</p>'
      + '<p>두 사람 모두 입장했으면 각자 자기 키보드의 <strong>스페이스바</strong>를 눌러 준비하세요.<br>'
      + '둘 다 준비되면 자동으로 시작하고, 최대 3분 동안(초밥이 다 떨어지면 일찍 끝나요) 초밥을 만든 뒤 회전 벨트 라운드(총 ' + ELEVATOR_ROUNDS + '라운드)로 넘어가요. 전반·후반 두 번 하고 점수를 합산해요.</p>'
      + '<div class="ready-row">'
      + '<span class="ready-chip' + (mine ? ' is-ready' : '') + '">나 · ' + (seat ? seatName(seat, st) : "-") + (mine ? ' · 준비 완료' : ' · 스페이스바 대기') + '</span>'
      + '<span class="ready-chip' + (other ? ' is-ready' : '') + '">' + (otherSeat ? seatName(otherSeat, st) : "-") + (other ? ' · 준비 완료' : ' · 대기 중') + '</span>'
      + '</div>'
      + spaceHint('준비')
      + '</div></div></main>';
  }

  // ---------- 공유 보드 헬퍼 (2026-10-06) ----------
  function boardCell(st, id) {
    var b = st.board || [];
    for (var i = 0; i < b.length; i++) if (b[i].id === id) return b[i];
    return null;
  }
  function boardLeft(st, catIdx) {
    var n = 0, b = st.board || [];
    for (var i = 0; i < b.length; i++) if (b[i].catIdx === catIdx && !b[i].taken) n++;
    return n;
  }
  // 이 칸을 지금 눌러서 제작할 수 있는가. 지정 초밥은 그 접시(칸)이 비어 있어야 하고, 나머지 종류는 같은 종류
  // 빈 칸이 하나라도 있으면 된다(서버가 대신 빈 칸을 준다). 반환: null이면 가능, 아니면 사유 문구.
  function cellBlockedReason(st, cellId) {
    if (!st || st.phase !== "secure") return "제작 시간이 끝났어요";
    var c = boardCell(st, cellId);
    if (!c) return "제작 시간이 끝났어요";
    var t = TYPES[c.catIdx];
    if (t.fixedFloor) return c.taken ? "다른 사람이 먼저 제작한 접시예요" : null;
    return boardLeft(st, c.catIdx) > 0 ? null : "이 종류 초밥이 모두 소진됐어요";
  }

  function renderBoard(st, seat) {
    var msLeft = st.secureEndsAt ? (st.secureEndsAt - nowMs()) : SECURE_PHASE_MS;
    var pct = Math.max(0, Math.min(100, (msLeft / SECURE_PHASE_MS) * 100));
    var html = '<main class="stage stage--secure">';
    html += '<div class="side-timer" id="side-timer">'
      + '<span class="timer-label">초밥 제작<br>남은 시간</span>'
      + '<span class="timer-num">' + fmtClock(msLeft) + '</span>'
      + '<div class="timer-bar"><i style="width:' + pct + '%"></i></div></div>';

    html += '<div class="card"><div class="board-grid">';
    // 2026-10-06 레일 화면: 종류마다 한 줄 -- 가운데 레일 위에 초밥 상자(남은 개수), 내 자리 쪽에 내 버튼.
    // 1번 자리는 왼쪽, 2번 자리는 오른쪽. 보드는 두 플레이어가 공유한다(종류별 6개 합계) -- 남은 개수만 같이 보이고
    // 상대 쪽 칸은 비워 둔다. 버튼은 "그 종류의 아직 안 가져간 칸"을 열어 준다(칸끼리 구별이 없어서 서버가 어차피 대체함).
    // 지정 초밥만 접시(칸)이 곧 서빙 접시라 버튼 대신 접시 버튼 6개를 둔다.
    var myInvoices = st.players[seat].invoices;
    var boardById = {};
    st.board.forEach(function (c) { boardById[c.id] = c; });
    var meLeft = seat === "1";
    html += '<div class="rail-head">'
      + '<span class="' + (meLeft ? 'me' : '') + '">' + (meLeft ? '내 자리' : '상대 자리') + '</span><span>레일</span>'
      + '<span class="' + (meLeft ? '' : 'me') + '">' + (meLeft ? '상대 자리' : '내 자리') + '</span></div>';
    TYPES.forEach(function (t, catIdx) {
      var left = boardLeft(st, catIdx);
      var invFor = function (cell) {
        for (var i = 0; i < myInvoices.length; i++) { if (myInvoices[i].acquiredSeq === cell.acquiredSeq) return myInvoices[i]; }
        return null;
      };
      var myCells = [];
      for (var n = 0; n < t.count; n++) {
        var c = boardById[t.key + "-" + (n + 1)];
        if (c && c.taken && c.takenBy === seat) myCells.push(c);
      }
      // --- 내 쪽 ---
      var mine = '<div class="rail-side mine" style="--c:' + t.color + '">';
      if (t.fixedFloor) {
        mine += '<div class="floor-btns">';
        for (var num = 0; num < t.count; num++) {
          var cell = boardById[t.key + "-" + (num + 1)];
          if (!cell.taken) mine += '<button class="floor-btn" data-action="open-cell" data-cell="' + cell.id + '">' + esc(FLOORS[num]) + '</button>';
          else if (cell.takenBy === seat) {
            var fInv = invFor(cell);
            mine += '<button class="floor-btn is-gone mine" disabled><span>' + esc(FLOORS[num]) + '</span>' + (fInv ? '<small>' + esc(sushiShort(fInv.sushi)) + '</small>' : '') + '</button>';
          }
          else mine += '<button class="floor-btn is-gone" disabled title="상대가 먼저 가져갔어요">' + esc(FLOORS[num]) + '</button>';
        }
        mine += '</div>';
        mine += '<div class="mine-count">내 초밥 ' + myCells.length + '개 · 접시 버튼을 눌러 주문표 붙이기</div>';
      } else {
        mine += '<button class="rail-btn" data-action="open-type" data-cat="' + catIdx + '"' + (left === 0 ? ' disabled' : '') + '>'
          + '<span class="rbt">' + (left === 0 ? '소진' : esc(MINI_NAME[t.mini] || '우봉고') + ' 시작') + '</span>'
          + '<span class="rbp">팔면 ' + fmtWon(t.reward) + ' · 못 팔면 ' + fmtWon(-t.penalty) + '</span></button>';
        mine += '<div class="my-chips">' + myCells.map(function (c) {
          var inv = invFor(c);
          return '<span class="my-chip">' + (inv ? esc(chipText(inv)) : '제작') + '</span>';
        }).join('') + '</div>';
      }
      mine += '</div>';
      // --- 가운데 레일 위 상자 ---
      var pips = '';
      for (var k = 0; k < t.count; k++) pips += '<span class="pip' + (k < left ? '' : ' gone') + '">' + FISH_PIP + '</span>';
      var mid = '<div class="rail-mid"><div class="rail-box" style="background:' + t.color + ';--c:' + t.color + '">'
        + '<span class="cell-art" style="background-image:url(\'' + railArt(catIdx) + '\')"></span>'
        + '<span class="rb-name"><span class="cat-icon">' + CAT_ICONS[catIdx] + '</span>' + esc(t.name) + '</span>'
        + '<span class="rb-game">' + esc(MINI_NAME[t.mini] || '우봉고') + '</span>'
        + '<span class="pips">' + pips + '</span>'
        + '<span class="cat-left">남은 <b>' + left + '</b> / ' + t.count + '</span>'
        + (left === 0 ? '<span class="stamp">소진</span>' : '')
        + '</div></div>';
      var theirs = '<div class="rail-side theirs"></div>';
      html += '<div class="board-row' + (left === 0 ? ' is-empty' : '') + '" data-cat="' + catIdx + '">'
        + (meLeft ? mine + mid + theirs : theirs + mid + mine) + '</div>';
    });
    html += '</div></div>';
    html += '</main>';
    return html;
  }

  // ---------- 제작 미니게임 (2026-10-06) ----------
  // TYPES[catIdx].mini(game-data.js)가 있는 종류의 칸은 우봉고 대신 minigames.js의 게임을 띄운다
  // (null이면 기존 우봉고 이미지 + "완료" 버튼). 게임은 #app이 아니라 #mg-layer에 mount한다 -- 이유는 CSS 주석 참고.
  // 서버는 이 게임을 모른다: 클라이언트가 끝까지 풀었다고 판정하면 예전과 똑같은 secure-cell 하나만 보낸다.
  var MINI_NAME = { pack: "상자 포장", inspect: "이상 확인", sticker: "주문표 붙이기", map: "주문 서빙", soko: "재료 정리", ice: "초밥 담기", route: "도마 닦기", twin: "쌍둥이 서빙", pipe: "컨베이어 잇기", hanoi: "초밥 쌓기" };
  // ?mgtest=1 이면 불량 검수의 정답 칸에 data-defect를 노출한다 (자동 테스트 전용 -- 일반 플레이엔 안 붙음).
  var TEST_HOOKS = /[?&]mgtest=1(&|$)/.test(location.search);
  var mg = null; // { cellId, ctl }

  // 값이 숫자 하나면 그대로, [전반, 후반] 배열이면 지금 하프 것 (TYPES의 miniLevel/pieces).
  function perHalf(v) { return Array.isArray(v) ? v[(state && state.half === 2) ? 1 : 0] : v; }
  function closeMiniGame() {
    lastAct = Date.now();
    if (mg) { var wasPeek = mg.kind === "peek"; try { mg.ctl.destroy(); } catch (e) { /* ignore */ } mg = null; if (!wasPeek) notifyGameClosed(); }
    var layer = document.getElementById("mg-layer");
    if (layer) { layer.classList.add("hidden"); layer.innerHTML = ""; }
  }
  // 칸을 연다: 미니게임이 있는 종류면 게임, 없으면(특선 초밥) 우봉고 오버레이. open-cell 버튼/레일 화면 지시가 같이 쓴다.
  function openCell(cellId) {
    var m = cellMeta(cellId, state.half);
    if (m && TYPES[m.catIdx].mini && window.MiniGames) { openMiniGame(cellId); return; }
    newSushiPick(cellId);
    local.openCellId = cellId; render();
  }
  // 레일 화면이 "이 칸을 풀어라"고 보냈을 때. 이미 뭔가 하고 있으면(서버도 막지만 경합 대비) 무시한다.
  function onRailOpenGame(cellId) {
    if (!state || state.phase !== "secure" || mg || local.openCellId) return;
    if (cellBlockedReason(state, cellId)) { notifyGameClosed(); return; }
    openCell(cellId);
  }
  // 레일이 열어 준 게임을 닫았다(포기/시간 종료/소진)는 걸 서버에 알린다 -- 레일 화면의 "플레이 중" 표시와 중복 지시 방지용.
  function notifyGameClosed() { send({ type: "game-closed", seat: mySeat() }); }
  function openMiniGame(cellId) {
    var meta = cellMeta(cellId, state.half);
    var t = TYPES[meta.catIdx];
    var pickedSushi = newSushiPick(cellId);
    closeMiniGame();
    var layer = document.getElementById("mg-layer");
    layer.innerHTML = '<div class="mg-wrap"><div class="mg-clock">제작 시간<b id="mg-clock">--:--</b></div><div id="mg-host"></div></div>';
    layer.classList.remove("hidden");
    // 2026-10-12: 초밥 하나 = 손질(액션형 칼질 타이밍) -> 제작(종류별 퍼즐) 두 단계. 칸은 손질을 시작하는 순간부터 내 칸이고,
    // 서버에는 제작까지 끝낸 뒤 secure-cell 한 번만 보낸다(서버 규칙은 그대로).
    mg = { cellId: cellId, ctl: null, stage: "prep", prep: null };
    function beginStage(stage) {
      if (mg.ctl) { try { mg.ctl.destroy(); } catch (e) { /* ignore */ } }
      mg.stage = stage;
      var o = { sushi: pickedSushi, testHooks: TEST_HOOKS, onCancel: function () { closeMiniGame(); } };
      if (stage === "prep") {
        o.kind = "prep"; o.pieces = t.pieces;
        o.onDone = function (res) { mg.prep = res; beginStage("make"); };
      } else {
        o.kind = t.mini; o.level = perHalf(t.miniLevel);
        // 지정 초밥은 칸이 곧 서빙 접시라 주문표에 그 접시를 그대로 찍는다 (호수는 제작 순간 서버가 정하므로 표기 안 함).
        o.label = t.fixedFloor ? FLOORS[meta.num] : null;
        o.onDone = function (res) {
          var id = cellId, prep = mg && mg.prep;
          markPending(id); closeMiniGame();
          send({ type: "secure-cell", seat: mySeat(), cellId: id, sushi: sushiFor(id),
            mini: res && res.ms ? { kind: res.kind, level: res.level, ms: res.ms, mistakes: res.mistakes } : undefined,
            prep: prep && prep.ms ? { ms: prep.ms, mistakes: prep.mistakes } : undefined });
        };
      }
      send({ type: "game-stage", seat: mySeat(), catIdx: meta.catIdx, stage: stage, sushi: pickedSushi }); // 메인 모니터의 "지금 만드는 중" 표시용
      mg.ctl = MiniGames.start(document.getElementById("mg-host"), o);
    }
    beginStage("prep");
    // 자동 테스트 전용(?mgtest=1): 게임을 실제로 풀지 않고 "풀었다"로 처리 -- 많은 칸을 한꺼번에 제작해야 하는
    // 회전 벨트 단계 테스트가 제작 시간 안에 끝나게 하려는 용도다. 미니게임 자체는 test_minigames.js와
    // test_minigames_live.js가 실제로 플레이하며 검증한다. 일반 접속에는 이 함수가 생기지 않는다.
    if (TEST_HOOKS) {
      window.__mgFinish = function () {
        if (!mg) return false;
        var id = mg.cellId;
        markPending(id);
        closeMiniGame();
        send({ type: "secure-cell", seat: mySeat(), cellId: id, sushi: sushiFor(id) });
        return true;
      };
    }
    updateMiniClock();
  }
  // ---- 엿보기 (2026-10-12): 전반-후반 하프타임에 미니게임 1회(재도전 없음) -> 후반 벨트에서 횟수만큼 상대 주문표 1장씩 몰래 보기 ----
  function openPeekGame() {
    var seat = mySeat();
    if (!seat || !state || state.phase !== "halftime" || mg || state.peek[seat].played || !window.MiniGames) return;
    var layer = document.getElementById("mg-layer");
    layer.innerHTML = '<div class="mg-wrap"><div id="mg-host"></div></div>';
    layer.classList.remove("hidden");
    mg = { cellId: null, kind: "peek", ctl: null };
    mg.ctl = MiniGames.start(document.getElementById("mg-host"), {
      kind: "peek", testHooks: TEST_HOOKS,
      onCancel: function () { closeMiniGame(); },
      onDone: function (res) {
        closeMiniGame();
        send({ type: "peek-result", seat: seat, mistakes: res && typeof res.mistakes === "number" ? res.mistakes : 3 });
      },
    });
  }
  function peekInfoFor(seat) { return (state && state.peek && state.peek[seat]) || { charges: 0, played: false, used: 0, seen: [] }; }
  function usePeek() {
    var seat = mySeat();
    if (!seat || !state || state.phase !== "elevator" || state.half !== 2) return;
    if (peekInfoFor(seat).charges <= 0) { showToast("남은 엿보기가 없어요"); return; }
    send({ type: "use-peek", seat: seat });
  }
  function onPeekReveal(msg) {
    if (!msg.ok) { showToast(msg.code === "nothing" ? "더 엿볼 상대 주문이 없어요" : (msg.code === "no_charge" ? "남은 엿보기가 없어요" : "지금은 엿볼 수 없어요")); return; }
    var iv = findInvoiceById(msg.invoiceId);
    if (!iv) return;
    SFX.peek();
    var old = document.getElementById("peek-pop"); if (old) old.remove();
    var d = document.createElement("div");
    d.id = "peek-pop"; d.className = "peek-pop";
    d.innerHTML = '<small>상대 주문표를 엿봤어요</small><b>' + esc(roomCode(iv.floorIdx)) + '</b><span>' + esc(sushiShort(iv.sushi)) + ' 초밥</span>';
    document.body.appendChild(d);
    setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 3400);
  }
  function updateMiniClock() {
    var el = document.getElementById("mg-clock");
    if (!el || !state || state.phase !== "secure" || !state.secureEndsAt) return;
    var left = state.secureEndsAt - nowMs();
    el.textContent = fmtClock(Math.max(0, left));
    el.parentNode.classList.toggle("low", left < 30000);
  }
  // 상태가 바뀔 때마다 호출: 제작 시간이 끝났거나 그 칸이 이미 제작됐으면(재접속 등) 열려 있던 게임을 닫는다.
  function syncMiniGame() {
    if (!mg) return;
    if (mg.kind === "peek") { if (!state || state.phase !== "halftime") closeMiniGame(); return; }
    var why = cellBlockedReason(state, mg.cellId);
    if (why) { closeMiniGame(); showToast(why); }
  }

  function renderPuzzleOverlay(st) {
    var cellId = local.openCellId;
    if (!cellId) return '<div class="overlay hidden" id="puzzle-overlay"></div>';
    var meta = cellMeta(cellId, st.half);
    var t = TYPES[meta.catIdx];
    return '<div class="overlay" id="puzzle-overlay">'
      + '<div class="puzzle-frame">'
      + '<div style="margin-bottom:0.6rem;color:var(--muted);font-family:var(--font-display);font-size:0.85rem;">' + esc(t.name) + ' · 조각 ' + perHalf(t.pieces) + '개</div>'
      + '<img src="' + meta.src + '" alt="우봉고 문제">'
      + '<div class="puzzle-actions">'
      + '<button class="btn danger" data-action="give-up">포기</button>'
      + '<button class="btn ok" data-action="complete-cell" data-cell="' + cellId + '">완료</button>'
      + '</div></div></div>';
  }

  // floorIdx is the real, server-authoritative elevator position -- it moves live as either player
  // clicks (see game-room.js's vote()), so this is a direct rendering of it with no client-side
  // simulation whatsoever: whichever row is floorIdx gets .current, nothing else changes.
  var PLATE_HEX = ["#E0443E", "#F28C28", "#F4D03F", "#3FAE5A", "#3D7FD9", "#8E5BC8"]; // FLOORS 순서와 같은 접시 색
  var PLATE_INK = ["#fff", "#2b1d12", "#2b1d12", "#fff", "#fff", "#fff"];
  // 순환 벨트: 접시 6장이 원으로 놓여 있고, 현재 접시가 항상 6시 "서빙 칸"에 오도록 통째로 돌아간다.
  // cur는 접시 번호(연속값 -- 메인 모니터는 한 바퀴 넘어가도 최단 방향으로 돌도록 누적값을 넘긴다).
  // 각 접시는 .floor-stop (DOM 순서 = FLOORS 순서), 현재 접시에만 .current. 접시 안의 .car가 색 원반이다.
  // 2026-10-12: 서빙 칸(6시)에 굵은 테두리 + 양옆 방향 화살표. 왼쪽 화살표 = 시계 방향(← 키), 오른쪽 화살표 = 반시계 방향(→ 키).
  //   벨트가 시계 방향으로 돌면 6시 자리에서는 접시가 왼쪽으로 지나가므로 화살표 방향이 실제 움직임과 맞다.
  var ARROW_SVG = '<svg viewBox="0 0 60 40" aria-hidden="true"><polygon points="4,20 26,3 26,13 56,13 56,27 26,27 26,37" /></svg>';
  var SERVE_ARROWS = '<span class="serve-arrow left">' + ARROW_SVG + '<b>시계</b></span><span class="serve-arrow right">' + ARROW_SVG + '<b>반시계</b></span>';
  function ringHtml(cur, extraCls, ringId, toCur) {
    var h = '<div class="belt-ring ' + (extraCls || '') + '"' + (ringId ? ' id="' + ringId + '" data-to="' + toCur + '"' : '') + ' style="--cur:' + cur + '"><div class="belt-track"></div><span class="serve-frame"></span>' + SERVE_ARROWS;
    FLOORS.forEach(function (f, i) {
      var isCur = (((Math.round(toCur === undefined ? cur : toCur) % FLOORS.length) + FLOORS.length) % FLOORS.length) === i;
      h += '<div class="floor-stop' + (isCur ? ' current' : '') + '" style="--i:' + i + '"><span class="car" style="background:' + PLATE_HEX[i] + ';color:' + PLATE_INK[i] + '"><svg class="car-fish" viewBox="0 0 40 24" aria-hidden="true"><path d="M3 12c5-8 15-9 22-3l8-5v16l-8-5c-7 6-17 5-22-3z"/><circle cx="9" cy="10" r="1.6" class="eye"/></svg><b>' + f + '</b></span></div>';
    });
    h += '<span class="belt-mark">▲ 서빙 칸</span></div>';
    return h;
  }
  function renderShaft(floorIdx) {
    return '<div class="shaft">' + ringHtml(floorIdx, '') + '</div>';
  }

  function renderInvoiceList(st, seat) {
    var invs = st.players[seat].invoices.slice().sort(function (a, b) { return a.acquiredSeq - b.acquiredSeq; });
    if (!invs.length) return '<div style="color:var(--muted);font-size:0.85rem;">아직 제작한 초밥이 없어요</div>';
    // st.elevator.priorityPick는 "이번 라운드" 우선 초밥 지정값(라운드가 끝나면 서버가 비움) --
    // 아직 안 끝난 항목에만 의미가 있다. 이미 서빙된 항목은 대신 inv.deliveredWasPriority(그 라운드에
    // 서빙 성공했을 때만 영구히 true)로 우선 보너스가 적용됐는지를 보여준다.
    var pickedId = st.elevator ? st.elevator.priorityPick[seat] : null;
    return '<div class="invoice-list">' + invs.map(function (inv) {
      var t = TYPES[inv.catIdx];
      var delivered = inv.deliveredRound !== null;
      var stickerText = inv.stolen ? "미서빙" : (delivered ? ("완료 · R" + inv.deliveredRound) : "대기");
      var isPendingPriority = !delivered && inv.id === pickedId;
      var isPriority = isPendingPriority || inv.deliveredWasPriority;
      var flagText = inv.deliveredWasPriority ? ('우선 x' + PRIORITY_MULTIPLIER + ' 성공') : (isPendingPriority ? ('이번 라운드 우선 x' + PRIORITY_MULTIPLIER) : '');
      return '<div class="invoice' + (delivered ? ' delivered' : '') + (isPriority ? ' is-priority' : '') + '">'
        + '<span class="swatch" style="background:' + t.color + '"></span>'
        + sushiIcon(inv.sushi) + '<div class="meta"><div class="t">' + invTitle(inv) + (flagText ? ' <span class="priority-flag">' + flagText + '</span>' : '') + '</div><div class="d">' + plateTag(inv.floorIdx) + '</div></div>'
        + '<span class="sticker' + (delivered && !inv.stolen ? '' : ' pending') + '">' + stickerText + '</span>'
        + '</div>';
    }).join("") + '</div>';
  }

  // Only ever passed MY OWN delivered items (see renderElevator) -- who received what is private
  // per player, so there is no seat tag here; it's always understood to be "mine".
  function renderDeliveredCallout(delivered) {
    if (!delivered || !delivered.length) return '<div class="delivered-callout empty">이번 라운드에 서빙된 초밥이 없어요</div>';
    return '<div class="delivered-callout">' + delivered.map(function (d) {
      var t = TYPES[d.catIdx];
      var note = d.stolen
        ? ' — <span style="color:var(--danger);font-weight:700;">초밥도둑에게 도난당했어요! (원재료값 ' + fmtWon(-t.penalty) + ')</span>'
        : ' (' + fmtWon(d.priority ? t.reward * PRIORITY_MULTIPLIER : t.reward) + (d.priority ? ' · 우선 x' + PRIORITY_MULTIPLIER : '') + ')';
      return '<div class="delivered-item"><span class="swatch" style="background:' + t.color + '"></span>'
        + plateTag(d.floorIdx) + ' ' + (function () { var iv = findInvoiceById(d.invoiceId), sn = iv ? sushiShort(iv.sushi) : ""; return sn ? esc(sn) + ' 초밥 (' + esc(t.name.replace(" 초밥", "")) + ')' : esc(t.name); })() + note
        + '</div>';
    }).join('') + '</div>';
  }

  // 우선 초밥 지정 전용 시간 ("priority" 상태, PRIORITY_PICK_MS = 10초 -- 2026-10-06 신설; 그 전에는 라운드
  // 게이트에 끼워져 있었고 타이머가 없었다). 매 라운드 다시 골라야 하고(라운드가 끝나면 서버가
  // el.priorityPick을 비운다), 그 라운드 안에 서빙까지 성공해야만 점수가 PRIORITY_MULTIPLIER배가 된다
  // -- 나중 라운드로 넘어가면 보너스는 사라진다(사용자 확인 사항). 내가 "확정"하면 이후엔 바꿀 수 없고,
  // 둘 다 확정하면 10초를 다 기다리지 않고 넘어간다. 시간이 다 되면 확정 여부와 무관하게 그 시점의 지정값이 적용된다.
  function renderPriorityWindow(st, seat) {
    var el = st.elevator;
    var undelivered = st.players[seat].invoices.filter(function (inv) { return inv.deliveredRound === null; })
      .sort(function (a, b) { return a.acquiredSeq - b.acquiredSeq; });
    var confirmed = !!el.priorityConfirmed[seat];
    var otherSeat = seat === "1" ? "2" : "1";
    var pickedId = el.priorityPick[seat];
    var html = '<div class="priority-window">';
    html += '<h4>우선 초밥 지정 (성공 시 점수 ' + PRIORITY_MULTIPLIER + '배)</h4>';
    html += '<div class="pw-sub">이번 라운드 안에 서빙해야만 적용돼요. 안 보내면 보너스는 사라져요.</div>';
    html += '<div class="pw-clock"><span style="color:var(--muted);font-size:0.85rem;">남은 시간</span>'
      + '<span class="time-left-big" id="priority-clock">' + fmtClock(Math.max(0, (el.priorityWindowEndsAt || 0) - nowMs())) + '</span></div>';
    html += '<div class="timer-bar"><i id="priority-bar" style="width:100%"></i></div>';
    html += '<div class="invoice-list">' + undelivered.map(function (inv) {
      var t = TYPES[inv.catIdx];
      var picked = inv.id === pickedId;
      return '<div class="invoice' + (confirmed ? ' delivered' : ' pickable') + (picked ? ' is-priority' : '') + '"'
        + (confirmed ? '' : (' data-action="pick-priority" data-inv="' + (picked ? '' : inv.id) + '"')) + '>'
        + '<span class="swatch" style="background:' + t.color + '"></span>'
        + sushiIcon(inv.sushi) + '<div class="meta"><div class="t">' + invTitle(inv) + '</div><div class="d">' + plateTag(inv.floorIdx) + ' · 팔면 ' + fmtWon(t.reward) + ' / 못 팔면 ' + fmtWon(-t.penalty) + '</div></div>'
        + '<span class="sticker' + (picked ? '' : ' pending') + '">' + (picked ? ('우선 x' + PRIORITY_MULTIPLIER) : '선택') + '</span>'
        + '</div>';
    }).join('') + '</div>';
    if (confirmed) {
      html += '<div class="pw-actions"><span class="ready-chip is-ready">'
        + (pickedId ? '우선 초밥 확정' : '지정 안 함으로 확정') + '</span>'
        + '<span class="ready-chip' + (el.priorityConfirmed[otherSeat] ? ' is-ready' : '') + '">' + seatName(otherSeat, st)
        + (el.priorityConfirmed[otherSeat] ? ' · 확정' : ' · 고르는 중') + '</span></div>';
    } else {
      html += '<div class="pw-actions"><button class="btn primary" data-action="confirm-priority">'
        + (pickedId ? '이걸로 확정' : '지정 안 함으로 확정') + '</button>'
        + '<span class="key-hint">Space로도 확정 · 고른 초밥을 다시 누르면 선택 해제</span></div>';
    }
    html += '</div>';
    return html;
  }

  // 후반 전용: 엿보기 남은 횟수 + 이미 엿본 상대 주문표(아직 서빙 전인 것만). 상대의 접시/초밥 종류만 보인다.
  function renderPeekPanel(st, seat) {
    if (st.half !== 2) return '';
    var pk = peekInfoFor(seat);
    if (!pk.played && !pk.seen.length) return '';
    var seenHtml = pk.seen.map(function (id) { return findInvoiceById(id); }).filter(function (iv) { return iv && iv.deliveredRound === null; }).map(function (iv) {
      return '<div class="peek-seen">' + plateTag(iv.floorIdx) + '<b>' + esc(sushiShort(iv.sushi)) + ' 초밥</b></div>';
    }).join('');
    return '<div class="peek-panel"><h3>엿보기</h3>'
      + '<button class="btn ghost" data-action="use-peek"' + (pk.charges > 0 ? '' : ' disabled') + '>상대 주문 엿보기<small>남은 ' + pk.charges + '회 · E 키</small></button>'
      + (seenHtml ? '<div class="peek-seen-list">' + seenHtml + '</div>' : '<div class="peek-empty">' + (pk.charges > 0 ? '아직 엿본 주문이 없어요' : '엿보기를 다 썼어요') + '</div>')
      + '</div>';
  }

  function renderElevator(st, seat) {
    var html = '<main class="stage"><div class="elev-layout">';
    // left column: gauge, then my own package list directly beneath it -- opponent's list is
    // never rendered here (or anywhere in the elevator phase), only mine.
    html += '<div class="elev-left">' + renderShaft(st.elevator.floorIdx)
      + '<div class="player-col me"><h3>내 초밥</h3>' + renderInvoiceList(st, seat) + '</div>'
      + renderPeekPanel(st, seat)
      + '</div>';

    html += '<div>';
    html += '<div class="card">';
    html += '<span class="round-pill">라운드 ' + st.elevator.round + ' / ' + ELEVATOR_ROUNDS + '</span>';
    html += '<div style="margin-top:0.6rem;font-family:var(--font-display);font-size:1.1rem;">현재 접시: <strong style="color:var(--gold)">' + FLOORS[st.elevator.floorIdx] + '</strong></div>';

    // Pre-round-1 gate: mirrors the between-round "result" ready-row, but with no voting UI at
    // all yet (nothing has been voted on) -- just a moment to review invoices before both players
    // press space to kick off round 1's 5-second vote.
    if (st.elevator.state === "idle") {
      var otherSeat0 = seat === "1" ? "2" : "1";
      var myReady0 = !!st.elevator.readyNext[seat];
      var otherReady0 = !!st.elevator.readyNext[otherSeat0];
      html += rules3([
        '<b>← →</b> 로 벨트를 돌려 내 초밥의 접시에 맞춰요 (라운드당 ' + (VOTE_MS / 1000) + '초)',
        '라운드 시작 때 <b>우선 초밥</b> 1개를 고르면 서빙 성공 시 점수 x' + PRIORITY_MULTIPLIER,
        st.half === 2 ? '후반: <b>초밥도둑</b>으로 상대를 막고, 얻은 <b>엿보기</b>로 상대 주문을 훔쳐봐요' : '못 팔면 마이너스 · 상대의 주문표는 안 보여요'
      ]);
      html += '<div class="ready-row" style="margin-top:0.75rem;">'
        + '<span class="ready-chip' + (myReady0 ? ' is-ready' : '') + '">나 · ' + seatName(seat, st) + (myReady0 ? ' · 준비 완료' : ' · 스페이스바 대기') + '</span>'
        + '<span class="ready-chip' + (otherReady0 ? ' is-ready' : '') + '">' + seatName(otherSeat0, st) + (otherReady0 ? ' · 준비 완료' : ' · 대기 중') + '</span>'
        + '</div>'
        + spaceHint('회전 벨트 시작') + gateAuto(st.elevator);
      html += '</div>';

      html += '</div></div></main>';
      return html;
    }

    // 우선 초밥 지정 전용 시간 (매 라운드 맨 처음, PRIORITY_PICK_MS) -- 독립된 상태 화면.
    if (st.elevator.state === "priority") {
      html += renderPriorityWindow(st, seat);
      html += '</div></div></main>';
      return html;
    }

    // 초밥도둑 배치 전용 시간 (후반 전용, 매 라운드 voting 시작 전 THIEF_PLACE_MS 동안 -- idle/voting 중
    // 아무 때나 놓을 수 있던 예전 방식 대신, 이제는 독립된 상태 화면이다). 배치는 선택사항(건너뛰기
    // 가능)이고, 배치 직후엔 아무 효과 없이 다음 라운드부터 실제로 작동한다 (game-room.js의 el.thieves
    // 참고). 둘 다 배치/건너뛰기를 마치면 타이머를 기다리지 않고 곧장 voting으로 넘어간다.
    // 2026-10-07: 1인당 이 후반 전체를 통틀어 thieves.perHalf(2)번까지 배치 가능 -- usedThisHalf(횟수)가
    // perHalf에 닿으면 서버가 이미 매 라운드 자동으로 스킵 처리해두므로(placeThief 호출 없이도 doneMine이
    // true), 여기서는 "이미 다 썼다"는 걸 구분해서 보여주기만 하면 된다. (마지막 라운드엔 창이 안 열린다.)
    if (st.elevator.state === "thief") {
      var placedMine = st.elevator.thieves.placedThisRound[seat];
      var skippedMine = !!st.elevator.thieves.skipped[seat];
      var perHalf = st.elevator.thieves.perHalf || 1;
      var usedCnt = st.elevator.thieves.usedThisHalf[seat] || 0;
      var usedUpMine = usedCnt >= perHalf;
      var leftMine = Math.max(0, perHalf - usedCnt);
      var doneMine = placedMine !== null && placedMine !== undefined || skippedMine;
      html += '<div class="thief-window">';
      html += '<h4>초밥도둑 배치 (후반 전용, 후반 통틀어 ' + perHalf + '회 · 남은 횟수 ' + leftMine + '회)</h4>';
      if (doneMine) {
        html += '<div style="color:var(--muted);font-size:0.85rem;">'
          + (placedMine !== null && placedMine !== undefined
            ? ('<strong style="color:var(--danger)">' + esc(FLOORS[placedMine]) + '</strong>에 배치했어요. 다음 라운드부터 그 접시에 상대가 서빙하면 뺏어요.')
            : (usedUpMine ? '이번 후반에 초밥도둑을 이미 다 사용했어요 (1인당 ' + perHalf + '회).' : '이번 라운드는 배치하지 않았어요.'))
          + ' 상대를 기다리는 중...</div>';
      } else {
        html += '<div style="color:var(--muted);font-size:0.85rem;margin-bottom:0.5rem;">접시를 골라 배치하면, 다음 라운드에 상대가 그 접시에 서빙할 때 가로채서 상대에게 확정 마이너스 점수를 줘요. 이 후반 동안 총 ' + perHalf + '번까지 놓을 수 있고(라운드당 1개), 마지막 라운드엔 놓을 수 없으니 신중하게 골라주세요.</div>';
        var peekedAt = {};
        peekInfoFor(seat).seen.forEach(function (id) { var iv = findInvoiceById(id); if (iv && iv.deliveredRound === null) peekedAt[iv.floorIdx] = sushiShort(iv.sushi); });
        html += '<div class="thief-floors">' + FLOORS.map(function (f, i) {
          return '<button class="btn ghost' + (peekedAt[i] ? ' is-peeked' : '') + '" data-action="place-thief" data-floor-idx="' + i + '">' + esc(f) + (peekedAt[i] ? '<small>엿봄 · ' + esc(peekedAt[i]) + '</small>' : '') + '</button>';
        }).join('') + '<button class="btn ghost" data-action="skip-thief">건너뛰기</button></div>';
      }
      html += '<div class="time-left-big" id="thief-clock">' + (doneMine ? '' : '남은 시간 계산 중...') + '</div>';
      html += '</div>';
      html += '</div></div></main>';
      return html;
    }

    // 같은 접시 충돌 선택 단계: 이번 라운드 도착한 접시에 내 미서빙 초밥이 2개 이상이면, SAME_FLOOR_CHOICE_MS
    // 동안 어느 걸 먼저 보낼지 고를 수 있다 (안 고르면 서버가 무작위로 정함). 충돌이 없는 플레이어에게는
    // 상대가 고르는 동안 대기 메시지만 보여준다.
    if (st.elevator.state === "choosing") {
      var pc = st.elevator.pendingChoice;
      var myConflict = pc && pc.conflicts[seat];
      html += '<div class="choice-box">';
      if (myConflict) {
        var myChosen = pc.chosen[seat];
        html += '<h4>같은 접시에 초밥이 여러 개예요 — 먼저 보낼 걸 골라주세요</h4>';
        html += '<div class="choice-list">' + myConflict.map(function (invId) {
          var inv = null;
          for (var i = 0; i < st.players[seat].invoices.length; i++) { if (st.players[seat].invoices[i].id === invId) { inv = st.players[seat].invoices[i]; break; } }
          if (!inv) return '';
          var t = TYPES[inv.catIdx];
          var isChosen = myChosen === invId;
          return '<div class="invoice' + (myChosen ? ' delivered' : ' pickable') + (isChosen ? ' chosen' : '') + '"'
            + (myChosen ? '' : (' data-action="choose-delivery" data-inv="' + invId + '"'))
            + '>'
            + '<span class="swatch" style="background:' + t.color + '"></span>'
            + sushiIcon(inv.sushi) + '<div class="meta"><div class="t">' + invTitle(inv) + '</div><div class="d">' + plateTag(inv.floorIdx) + '</div></div>'
            + '<span class="sticker' + (isChosen ? '' : ' pending') + '">' + (isChosen ? '선택됨' : '선택') + '</span>'
            + '</div>';
        }).join('') + '</div>';
        html += '<div class="time-left-big" id="choice-clock">' + (myChosen ? '상대를 기다리는 중...' : '남은 시간 계산 중...') + '</div>';
      } else {
        html += '<h4>잠시만요</h4><div style="color:var(--muted);font-size:0.85rem;">상대방이 같은 접시 초밥 중 먼저 보낼 걸 고르고 있어요...</div>';
      }
      html += '</div>';
      html += '</div></div></main>';
      return html;
    }

    var voting = st.elevator.state === "voting";

    html += '<div class="vote-buttons">';
    html += '<button class="btn big primary" data-action="vote-up"' + (voting ? '' : ' disabled') + '><span class="vote-arrow">←</span> 시계 방향으로</button>';
    html += '<button class="btn big ghost" data-action="vote-down"' + (voting ? '' : ' disabled') + '>반시계 방향으로 <span class="vote-arrow">→</span></button>';
    html += '</div>';
    // per-click counts (mine or the opponent's) are never shown -- the real floor position, shown
    // live in the shaft (whichever row carries .current), is the only movement feedback either
    // player gets during voting.
    html += '<div class="key-hint">' + (voting ? '키보드 ← / → 방향키로도 누를 수 있어요' : '이번 라운드 투표가 끝났어요') + '</div>';

    if (voting) {
      html += '<div class="time-left-big" id="round-clock">남은 시간 계산 중...</div>';
    } else if (st.elevator.log.length) {
      var last = st.elevator.log[st.elevator.log.length - 1];
      // Only the numeric up/down tally is hidden here -- which direction won, and where the
      // elevator ended up, are still shown. Delivered items are filtered to MY seat only: who
      // received what package is private per player (see renderDeliveredCallout).
      var myDelivered = (last.delivered || []).filter(function (d) { return d.seat === seat; });
      html += '<div class="round-result">'
        + '<div>라운드 ' + last.round + ' 결과 — '
        + (last.dir === "tie" ? "제자리" : (last.dir === "up" ? "시계 방향" : "반시계 방향"))
        + ' (현재 ' + FLOORS[last.floorIdx] + ')</div>'
        + renderDeliveredCallout(myDelivered)
        + '</div>';
      var otherSeat = seat === "1" ? "2" : "1";
      var myReady = !!st.elevator.readyNext[seat];
      var otherReady = !!st.elevator.readyNext[otherSeat];
      var nextLabel = st.elevator.round >= ELEVATOR_ROUNDS ? "최종 결과 보기" : "다음 라운드";
      html += '<div class="ready-row">'
        + '<span class="ready-chip' + (myReady ? ' is-ready' : '') + '">나 · ' + seatName(seat, st) + (myReady ? ' · 준비 완료' : ' · 스페이스바 대기') + '</span>'
        + '<span class="ready-chip' + (otherReady ? ' is-ready' : '') + '">' + seatName(otherSeat, st) + (otherReady ? ' · 준비 완료' : ' · 대기 중') + '</span>'
        + '</div>'
        + spaceHint(nextLabel) + gateAuto(st.elevator);
    }
    html += '</div>';

    html += '</div></div></main>';
    return html;
  }

  // 하프타임 전환 화면: 전반이 끝난 뒤 후반(새 보드, 새 주문표, 초밥도둑 해금)을 시작하기 전 결과를 잠깐
  // 보여주고, 둘 다 스페이스바를 누르면 후반의 초밥 제작 페이즈가 시작된다.
  function renderHalftime(st, seat) {
    var otherSeat = seat === "1" ? "2" : "1";
    var myReady = !!st.halftimeReady[seat];
    var otherReady = !!st.halftimeReady[otherSeat];
    var h1 = st.halfHistory[0];
    var html = '<main class="stage"><div class="center-screen"><div class="halftime-box card">';
    html += '<h2>전반 종료</h2>';
    if (h1) {
      html += '<div class="halftime-scores">'
        + '<div class="chip">' + esc(seatName("1", st)) + '<span class="n">' + fmtWon(h1.scores["1"]) + '</span></div>'
        + '<div class="chip">' + esc(seatName("2", st)) + '<span class="n">' + fmtWon(h1.scores["2"]) + '</span></div>'
        + '</div>';
    }
    html += rules3(['초밥 보드가 새로 채워져요', '후반부터 <b style="color:var(--danger)">초밥도둑</b>을 놓을 수 있어요 (후반 2회)', '엿보기에 성공하면 상대 주문표를 몰래 볼 수 있어요']);
    var pkMe = peekInfoFor(seat), pkOther = peekInfoFor(otherSeat);
    html += '<div class="peek-box">';
    if (pkMe.played) {
      html += '<div class="pb-done"><b>엿보기 ' + pkMe.charges + '회 획득</b><span>후반 회전 벨트에서 상대 주문표를 ' + pkMe.charges + '장 몰래 볼 수 있어요</span></div>';
    } else {
      html += '<div class="pb-title">엿보기 얻기</div><div class="pb-desc">상대 가게 창문 틈에 렌즈를 맞춰요. 실수가 적을수록 후반에 상대 주문표를 더 많이 볼 수 있어요 (1회만 도전).</div>'
        + '<button class="btn primary" data-action="start-peek">엿보기 도전</button>';
    }
    html += '<div class="pb-other">' + esc(seatName(otherSeat, st)) + ' · ' + (pkOther.played ? '도전 완료' : '아직 도전 안 함') + '</div></div>';
    html += '<div class="ready-row">'
      + '<span class="ready-chip' + (myReady ? ' is-ready' : '') + '">나 · ' + seatName(seat, st) + (myReady ? ' · 준비 완료' : ' · 스페이스바 대기') + '</span>'
      + '<span class="ready-chip' + (otherReady ? ' is-ready' : '') + '">' + seatName(otherSeat, st) + (otherReady ? ' · 준비 완료' : ' · 대기 중') + '</span>'
      + '</div>'
      + spaceHint('후반 시작');
    html += '</div></div></main>';
    return html;
  }

  // 전반/후반 각각의 스냅샷(st.halfHistory)과, 그 안의 players.invoices로부터 다시 계산한 점수를
  // 그대로 보여준다 -- st.scores(전체 합산)와는 별개로 하프별 내역도 함께 표시. 우선 서빙 여부는
  // (라운드 한정 보너스이므로) inv.deliveredWasPriority에 이미 영구히 기록돼 있다.
  function renderHalfTable(seat, halfEntry) {
    var invs = halfEntry.players[seat].invoices.slice().sort(function (a, b) { return a.acquiredSeq - b.acquiredSeq; });
    var html = '<table class="score-table"><thead><tr><th>종류</th><th>목적지</th><th>결과</th><th>점수</th></tr></thead><tbody>';
    invs.forEach(function (inv) {
      var t = TYPES[inv.catIdx];
      var pts = scoreInvoice(inv);
      var label = resultLabel(inv) + (inv.deliveredWasPriority ? ' · 우선' : '');
      html += '<tr><td>' + esc(t.name) + (sushiShort(inv.sushi) ? ' · ' + esc(sushiShort(inv.sushi)) : '') + '</td><td>' + plateTag(inv.floorIdx) + '</td><td>' + label + '</td><td>' + fmtWon(pts) + '</td></tr>';
    });
    if (!invs.length) html += '<tr><td colspan="4" style="color:var(--muted)">제작한 초밥 없음</td></tr>';
    html += '</tbody></table>';
    return html;
  }

  // 2026-08-28 신설: 종료 화면에서 링크를 새로 안 받아도 같은 방에서 바로 재대결할 수 있는 버튼.
  // halftime/lobby의 "둘 다 눌러야" 게이트와 같은 패턴이되, 스페이스바가 아니라 실제 클릭 버튼으로
  // 만들었다(사용자 요청 -- 결과 화면은 내용이 길어서 스페이스바보다 버튼이 더 눈에 띈다). 내가 이미
  // 누른 뒤에는 버튼을 비활성화하고 "상대방 대기 중" 문구로 바꿔서, 두 번 누르거나 아직 상대가 안
  // 눌렀는데 눌린 것처럼 보이는 걸 방지한다.
  function renderRestartGate(st, seat) {
    var otherSeat = seat === "1" ? "2" : (seat === "2" ? "1" : null);
    var mine = !!(st.restartReady && seat && st.restartReady[seat]);
    var other = !!(st.restartReady && otherSeat && st.restartReady[otherSeat]);
    var html = '<div class="restart-gate card">';
    if (mine) {
      html += '<button class="btn primary big" disabled>' + (other ? '다시 시작하는 중...' : '다시 시작 대기 중 (' + esc(seatName(otherSeat, st)) + ' 응답 대기)') + '</button>';
    } else {
      html += '<button class="btn primary big" data-action="restart-ready">다시 시작</button>';
    }
    html += '<div class="ready-row" style="margin-top:0.6rem;">'
      + '<span class="ready-chip' + (mine ? ' is-ready' : '') + '">나 · ' + (mine ? '준비 완료' : '대기 중') + '</span>'
      + (otherSeat ? '<span class="ready-chip' + (other ? ' is-ready' : '') + '">' + esc(seatName(otherSeat, st)) + (other ? ' · 준비 완료' : ' · 대기 중') + '</span>' : '')
      + '</div>';
    html += '<p style="color:var(--muted);font-size:0.85rem;margin:0.5rem 0 0;">같은 링크에서 좌석/셰프는 그대로 두고 바로 새 게임을 시작해요. 둘 다 눌러야 시작됩니다.</p>';
    html += '</div>';
    return html;
  }

  function renderEnd(st, seat) {
    var s1 = st.scores ? st.scores["1"] : 0, s2 = st.scores ? st.scores["2"] : 0;
    var winner = s1 === s2 ? "무승부" : (s1 > s2 ? (seatName("1", st) + " 승리") : (seatName("2", st) + " 승리"));
    var html = '<main class="stage">';
    html += '<div class="winner-banner">' + esc(winner) + '</div>';
    html += renderRestartGate(st, seat);
    // Game's over -- unlike the elevator phase (where per-round delivery info stays private so
    // players can't read each other's moves mid-game), the ending screen reveals both players'
    // full itemized results (전반 + 후반 각각, 그리고 합산) so they can compare and review the
    // whole run together.
    st.halfHistory.forEach(function (h) {
      html += '<h3 style="font-family:var(--font-display);color:var(--muted);margin:1.2rem 0 0.4rem;">' + (h.half === 1 ? "전반" : "후반") + '</h3>';
      html += '<div class="split-two">';
      ["1", "2"].forEach(function (s) {
        html += '<div class="card"><h3 style="font-family:var(--font-display);margin-top:0;">' + esc(seatName(s, st)) + (s === seat ? ' (나)' : '') + ' — ' + fmtWon(h.scores[s]) + '</h3>';
        html += renderHalfTable(s, h);
        html += '</div>';
      });
      html += '</div>';
    });
    html += '<div class="halftime-scores" style="margin-top:1.4rem;">'
      + '<div class="chip">' + esc(seatName("1", st)) + ' 총점<span class="n">' + fmtWon(s1) + '</span></div>'
      + '<div class="chip">' + esc(seatName("2", st)) + ' 총점<span class="n">' + fmtWon(s2) + '</span></div>'
      + '</div>';
    html += '</main>';
    return html;
  }

  function renderLoading() {
    return '<main class="stage"><div class="center-screen"><div class="lobby-box card"><h2>연결 중...</h2>'
      + '<p>서버에 접속하고 있어요. 잠시만 기다려 주세요.</p></div></div></main>';
  }

  function renderBody() {
    if (RAIL && !ROOM) return renderRailJoin();
    if (!ROOM) return '<main class="stage"><div class="center-screen"><div class="lobby-box card"><h2>잘못된 링크예요</h2><p>방 코드가 없어요. 처음 받은 링크로 다시 들어와 주세요.</p></div></div></main>';
    if (MAIN) return renderMain();
    if (RAIL) return renderRail();
    if (!state) return renderTopbarShell() + renderLoading();
    var seat = mySeat();
    var body = renderTopbar(state, seat);
    if (!seat) return renderSeatPicker();
    if (state.phase === "lobby") {
      // 방어적 체크 (2026-08-28 버그 수정): 이 좌석이 서버에 등록돼 있어도(seat truthy) courierPick이
      // 비어 있으면(재접속 유예 로직으로도 못 막은 예외적 타이밍, 혹은 방이 스윕돼 새로 만들어진 뒤
      // sessionStorage만 남아있던 경우 등) 절대 "스페이스바 대기" 화면을 보여주지 않는다 -- 셰프를
      // 안 골랐는데 대기 화면만 뜨면 사용자가 다시 고를 방법이 없다("한번씩 대기 시간에 셰프 선택이
      // 안 떠" 버그 리포트). 내 셰프가 실제로 정해져 있을 때만 대기 화면, 아니면 선택 화면.
      body += renderLobby(state, seat);
    }
    else if (state.phase === "secure") {
      // 우봉고 오버레이를 열어둔 사이 그 칸(또는 그 종류)이 상대에게 다 넘어갔으면 오버레이를 닫는다 (공유 보드).
      if (local.openCellId) {
        var blocked = cellBlockedReason(state, local.openCellId);
        if (blocked) { local.openCellId = null; notifyGameClosed(); setTimeout(function () { showToast(blocked); }, 0); }
      }
      // 레일 화면이 접속해 있으면 버튼은 그쪽에 있다 -- 내 화면은 "기다리는 화면"이고, 게임은 레일에서 눌렀을 때 뜬다.
      body += (railInfo.count > 0 ? renderRailWaiting(state, seat) : renderBoard(state, seat)) + renderPuzzleOverlay(state) + introHtml(state, false);
    }
    else if (state.phase === "elevator") body += renderElevator(state, seat);
    else if (state.phase === "halftime") body += renderHalftime(state, seat);
    else if (state.phase === "end") body += renderEnd(state, seat);
    return body;
  }
  // 시작 10초 3컷 설명 (2026-10-12, 평가 G1): 전반 제작 단계가 시작되면 화면 아래에 컷 3개가 3.3초씩 지나간다.
  // 조작을 막지 않고(pointer-events 없음) 시간도 안 뺏는다. 다시 그려져도 경과 시간만큼 애니메이션이 이어지게 음수 지연을 쓴다.
  function introHtml(st, big) {
    if (!st || st.phase !== "secure" || st.half !== 1 || !st.secureEndsAt) return '';
    var elapsed = Math.max(0, SECURE_PHASE_MS - (st.secureEndsAt - nowMs()));
    if (elapsed >= INTRO_MS) return '';
    var cuts = [
      ['초밥을 만들어요', '레일에서 종류를 골라 손질하고 퍼즐을 풀어요'],
      ['주문표가 붙어요', '초밥마다 서빙할 접시가 정해져요 · 상대에겐 비밀'],
      ['벨트를 돌려 서빙!', '내 접시에 맞추면 돈, 못 팔면 마이너스']
    ];
    return '<div class="intro3' + (big ? ' big' : '') + '" style="--el:' + (elapsed / 1000).toFixed(2) + 's">'
      + cuts.map(function (c, i) {
        return '<div class="cut" style="--d:' + (i * 3.34).toFixed(2) + 's"><i>' + (i + 1) + '</i><div><b>' + c[0] + '</b><span>' + c[1] + '</span></div></div>';
      }).join('') + '</div>';
  }
  // 단계별 규칙은 3줄 이내 (평가 G2).
  function rules3(lines) {
    return '<ol class="rules3">' + lines.map(function (l) { return '<li>' + l + '</li>'; }).join('') + '</ol>';
  }
  // 게이트(idle/result) 자동 진행 카운트다운 (서버가 GATE_AUTO_MS 뒤 둘 다 준비로 처리한다).
  function gateAuto(el) {
    if (!el.gateEndsAt) return '';
    return '<span class="gate-count" data-ends="' + el.gateEndsAt + '">' + Math.max(0, Math.ceil((el.gateEndsAt - nowMs()) / 1000)) + '초 뒤 자동 진행</span>';
  }
  // 메인 모니터 G4: 제작 중 실시간 현황 / 라운드 서빙 결과(이유 포함, 서빙된 주문표는 공개)
  function mvLive(st) {
    return '<div class="mv-live">' + ["1", "2"].map(function (sn) {
      var made = st.board.filter(function (c) { return c.takenBy === sn; }).length;
      var mk = railInfo.making && railInfo.making[sn];
      var now = mk ? (TYPES[mk.catIdx].name + (mk.stage === "prep" ? ' 손질 중' : ' 제작 중')) : (st.seatOwners[sn] ? '다음 초밥 고르는 중' : '입장 대기');
      return '<div class="mv-live-card' + (mk ? ' is-active' : '') + '"><b>' + esc(seatName(sn, st)) + '</b><span class="mv-live-now">' + esc(now) + '</span><small>만든 초밥 ' + made + '개</small></div>';
    }).join('') + '</div>';
  }
  function mvResult(st) {
    var el = st.elevator, entry = el.log && el.log[el.log.length - 1];
    if (!entry || entry.round !== el.round) return '';
    return '<div class="mv-res">' + ["1", "2"].map(function (sn) {
      var d = null; entry.delivered.forEach(function (x) { if (x.seat === sn) d = x; });
      var line, cls;
      var invs = st.players[sn].invoices, done = invs.filter(function (v) { return v.deliveredRound !== null; }).length;
      if (d) {
        var t = TYPES[d.catIdx], iv = findInvoiceById(d.invoiceId), sname = iv ? sushiShort(iv.sushi) : '';
        var nm = sname ? sname + ' 초밥' : t.name;
        if (d.stolen) { line = FLOORS[d.floorIdx] + ' 접시 · ' + nm + ' — 초밥도둑에게 도난! ' + fmtWon(-t.penalty); cls = ' is-bad'; }
        else { line = FLOORS[d.floorIdx] + ' 접시 · ' + nm + ' — 서빙 성공 ' + fmtWon(d.priority ? t.reward * PRIORITY_MULTIPLIER : t.reward) + (d.priority ? ' (우선 x' + PRIORITY_MULTIPLIER + ')' : ''); cls = ' is-ok'; }
      } else {
        line = (invs.length - done) ? (FLOORS[entry.floorIdx] + ' 접시에 맞는 주문이 없었어요') : '남은 주문이 없어요';
        cls = ' is-none';
      }
      return '<div class="mv-res-row' + cls + '"><b>' + esc(seatName(sn, st)) + '</b><span>' + esc(line) + '</span><small>만든 초밥 ' + invs.length + '개 · 처리 ' + done + '개</small></div>';
    }).join('') + '</div>';
  }
  function renderTopbarShell() {
    return '<div class="topbar"><div class="brand"><span class="eyebrow">BeatPhobia · Live</span><h1>초밥 서빙 게임</h1></div>'
      + '<div class="right"><span class="room-chip">방 ' + esc(ROOM) + '</span></div></div>';
  }


  // ---------- 레일 사이트 (2026-10-07, /rail) ----------
  // 두 플레이어가 같이 보는 공용 화면. 제작 단계에서 종류마다 한 줄: 가운데 레일 위에 초밥 상자(남은 개수 점), 왼쪽 = 1번 자리 버튼,
  // 오른쪽 = 2번 자리 버튼. 버튼을 누르면 서버(rail-press)가 그 자리 플레이어의 기기에 해당 종류 미니게임을 띄운다. 이 화면은 좌석이 없고
  // 비공개 정보(내가 제작한 호수, 우선 초밥 등)는 어디에도 그리지 않는다 -- 남은 개수와 누가 지금 게임 중인지만 보인다.
  function renderRailJoin() {
    return '<main class="stage"><div class="center-screen"><div class="lobby-box card"><h2>레일 화면</h2>'
      + '<p>메인 화면에 뜬 방 코드를 입력하세요.</p>'
      + '<p><input id="rail-code" class="rv-code" maxlength="4" autocomplete="off" autocapitalize="characters" placeholder="방 코드"> '
      + '<button class="btn ok" data-action="rail-join">입장</button></p></div></div></main>';
  }
  function railSideHead(st, side) {
    var key = st.courierPick && st.courierPick[side];
    var c = key ? courierByKey(key) : null;
    var idx = c ? COURIERS.indexOf(c) : -1;
    var here = !!st.seatOwners[side];
    var busy = railInfo.busy && railInfo.busy[side];
    return '<span class="rv-side' + (c ? ' is-on' : '') + (busy ? ' is-busy' : '') + '" data-side="' + side + '"' + (c ? ' style="--c:' + c.color + '"' : '') + '>'
      + (c ? '<span class="rv-side-icon">' + COURIER_ICONS[idx] + '</span>' : '')
      + '<b>' + esc(c ? c.name : '플레이어 ' + side) + '</b>'
      + '<small>' + (!here ? '입장 대기' : (busy ? '게임 중...' : '버튼을 누르세요')) + '</small></span>';
  }
  function railSideButtons(st, side, t, catIdx, left) {
    var here = !!st.seatOwners[side];
    var busy = !!(railInfo.busy && railInfo.busy[side]);
    var html = '<div class="rail-side mine side-' + side + '" style="--c:' + t.color + '">';
    if (t.fixedFloor) {
      html += '<div class="floor-btns">';
      for (var num = 0; num < t.count; num++) {
        var cell = boardCell(st, t.key + "-" + (num + 1));
        var off = !here || busy || (cell && cell.taken);
        html += '<button class="floor-btn' + (cell && cell.taken ? ' is-gone' : '') + '" data-action="rail-press" data-side="' + side + '" data-cat="' + catIdx + '" data-cell="' + t.key + '-' + (num + 1) + '"'
          + (off ? ' disabled' : '') + '>' + esc(FLOORS[num]) + '</button>';
      }
      html += '</div>';
    } else {
      var off2 = !here || busy || left === 0;
      html += '<button class="rail-btn' + (busy ? ' is-busy' : '') + '" data-action="rail-press" data-side="' + side + '" data-cat="' + catIdx + '"' + (off2 ? ' disabled' : '') + '>'
        + '<span class="rbt">' + (left === 0 ? '소진' : (busy ? '게임 중...' : esc(MINI_NAME[t.mini] || '우봉고') + ' 시작')) + '</span>'
        + '<span class="rbp">팔면 ' + fmtWon(t.reward) + ' · 못 팔면 ' + fmtWon(-t.penalty) + '</span></button>';
    }
    return html + '</div>';
  }
  function renderRail() {
    var st = state;
    var head = function (label) {
      return '<header class="rv-head"><div><span class="rv-eyebrow">BeatPhobia · Live</span><h1>레일 화면</h1></div>'
        + '<div class="rv-chips">' + (label ? '<span class="rv-chip phase">' + esc(label) + '</span>' : '') + '<span class="rv-chip room">방 ' + esc(ROOM) + '</span></div></header>';
    };
    if (!st) return '<div class="rv">' + head('') + '<div class="rv-center"><h2>연결 중...</h2></div></div>';
    var halfName = st.half === 2 ? "후반" : "전반";
    if (st.phase !== "secure") {
      var msg = st.phase === "lobby" ? ['참가자를 기다리고 있어요', '두 플레이어가 준비하면 이 화면에 레일이 열려요']
        : st.phase === "elevator" ? ['서빙 중이에요', '다음 초밥 제작 단계에서 레일이 다시 열려요']
        : st.phase === "halftime" ? ['하프타임', '후반이 시작되면 레일이 새 초밥으로 채워져요']
        : ['게임이 끝났어요', '다시 시작하면 레일이 열려요'];
      return '<div class="rv">' + head(st.phase === "lobby" ? '대기 중' : halfName) + '<div class="rv-center"><h2>' + msg[0] + '</h2><p>' + msg[1] + '</p>'
        + '<div class="rv-sides">' + railSideHead(st, "1") + railSideHead(st, "2") + '</div></div></div>';
    }
    var endsAt = st.secureEndsAt || nowMs();
    var html = '<div class="rv">' + head('초밥 제작 · ' + halfName);
    html += '<div class="rv-clockrow"><span class="rv-clock-label">남은 시간</span><b id="rv-clock" data-ends="' + endsAt + '">' + fmtClock(endsAt - nowMs()) + '</b>'
      + '<div class="rv-bar"><i id="rv-bar" data-ends="' + endsAt + '"></i></div></div>';
    html += '<div class="board-grid rv-board">';
    html += '<div class="rail-head">' + railSideHead(st, "1") + '<span>레일</span>' + railSideHead(st, "2") + '</div>';
    TYPES.forEach(function (t, catIdx) {
      var left = boardLeft(st, catIdx), pips = '';
      for (var k = 0; k < t.count; k++) pips += '<span class="pip' + (k < left ? '' : ' gone') + '">' + FISH_PIP + '</span>';
      var mid = '<div class="rail-mid"><div class="rail-box" style="background:' + t.color + ';--c:' + t.color + '">'
        + '<span class="cell-art" style="background-image:url(\'' + railArt(catIdx) + '\')"></span>'
        + '<span class="rb-name"><span class="cat-icon">' + CAT_ICONS[catIdx] + '</span>' + esc(t.name) + '</span>'
        + '<span class="rb-game">' + esc(MINI_NAME[t.mini] || '우봉고') + '</span>'
        + '<span class="pips">' + pips + '</span>'
        + '<span class="cat-left">남은 <b>' + left + '</b> / ' + t.count + '</span>'
        + (left === 0 ? '<span class="stamp">소진</span>' : '')
        + '</div></div>';
      html += '<div class="board-row' + (left === 0 ? ' is-empty' : '') + '" data-cat="' + catIdx + '">'
        + railSideButtons(st, "1", t, catIdx, left) + mid + railSideButtons(st, "2", t, catIdx, left) + '</div>';
    });
    return html + '</div>' + introHtml(st, false) + '</div>';
  }
  function railTick() {
    var c = document.getElementById("rv-clock"), b = document.getElementById("rv-bar");
    if (!c) return;
    var ends = parseInt(c.getAttribute("data-ends"), 10), left = ends - nowMs();
    c.textContent = fmtClock(left);
    c.classList.toggle("is-low", left < 30000);
    if (b) b.style.width = Math.max(0, Math.min(100, left / SECURE_PHASE_MS * 100)) + "%";
  }
  // 플레이어 화면(레일 모드): 버튼은 레일 화면에 있다. 여기선 내 시간, 내 쪽 위치, 종류별 남은 개수와 내가 제작한 호수만 보여 준다.
  function renderRailWaiting(st, seat) {
    var msLeft = st.secureEndsAt ? (st.secureEndsAt - nowMs()) : SECURE_PHASE_MS;
    var pct = Math.max(0, Math.min(100, (msLeft / SECURE_PHASE_MS) * 100));
    var html = '<main class="stage stage--secure">'
      + '<div class="side-timer" id="side-timer"><span class="timer-label">초밥 제작<br>남은 시간</span><span class="timer-num">' + fmtClock(msLeft) + '</span>'
      + '<div class="timer-bar"><i style="width:' + pct + '%"></i></div></div>';
    var mine = st.players[seat].invoices;
    var busy = !!(railInfo.busy && railInfo.busy[seat]);
    html += '<div class="card rw" data-rail-wait="1"><h2>' + (busy ? '게임을 푸는 중이에요' : '레일 화면에서 버튼을 눌러 주세요') + '</h2>'
      + '<p class="rw-sub">내 버튼은 레일 화면의 <b>' + (seat === "1" ? '왼쪽' : '오른쪽') + '</b>에 있어요. 누르면 이 화면에 게임이 떠요.</p><div class="rw-list">';
    TYPES.forEach(function (t, catIdx) {
      var left = boardLeft(st, catIdx);
      var chips = mine.filter(function (inv) { return inv.catIdx === catIdx; })
        .map(function (inv) { return '<span class="my-chip">' + esc(chipText(inv)) + '</span>'; }).join('');
      html += '<div class="rw-row' + (left === 0 ? ' is-empty' : '') + '" data-cat="' + catIdx + '" style="--c:' + t.color + '">'
        + '<span class="rw-ico">' + CAT_ICONS[catIdx] + '</span><span class="rw-name">' + esc(t.name) + '<small>' + esc(MINI_NAME[t.mini] || '우봉고') + '</small></span>'
        + '<span class="rw-left">남은 <b>' + left + '</b>/' + t.count + '</span><span class="rw-mine">' + (chips || '<small>아직 없음</small>') + '</span></div>';
    });
    return html + '</div></div></main>';
  }

  // ---------- 메인 모니터 (2026-10-06, ?view=main) ----------
  // 현장 TV/프로젝터에 띄우는 관전 화면. 요청된 것만 크게 보여준다:
  //   제작 단계    -> 남은 시간 + 종류별 남은 상자 수
  //   회전 벨트   -> 회전 벨트 위치(현재 접시) + 남은 시간
  // 그 외(대기/하프타임/종료)는 흐름이 끊기지 않게 최소한만 (참가 안내, 점수). 플레이어별 비공개 정보(주문표 내용,
  // 우선 초밥 지정, 초밥도둑 배치 위치)는 어디에도 그리지 않는다. 카운트다운 숫자는 data-ends(서버 시각)를 보고
  // mainTick()이 200ms마다 갱신하므로, 상태가 안 바뀌어도 시계는 계속 간다.
  var mvPrevFloor = null, mvCont = 0;
  function mvSeatCard(st, seatNo, readyMap, readyWord) {
    var key = st.courierPick && st.courierPick[seatNo];
    var c = key ? courierByKey(key) : null;
    var idx = c ? COURIERS.indexOf(c) : -1;
    var team = c || COURIERS[Number(seatNo) - 1];   // 아직 입장 전이어도 이 자리의 팀(초밥왕/스시헌터)은 정해져 있다
    var tIdx = COURIERS.indexOf(team);
    var ready = !!(readyMap && readyMap[seatNo]);
    return '<div class="mv-seat' + (c ? ' is-on' : '') + (ready ? ' is-ready' : '') + '"' + (c ? ' style="--c:' + c.color + '"' : '') + '>'
      + (c ? '<span class="mv-seat-icon">' + COURIER_ICONS[idx] + '</span>' + esc(c.name) : '<span class="mv-seat-icon" style="color:var(--muted)">' + COURIER_ICONS[tIdx] + '</span><span style="color:var(--muted)">' + esc(team.name) + '</span>')
      + '<small>' + (!c ? '입장 대기' : (readyMap ? (ready ? readyWord + ' 완료' : '대기 중') : '입장 완료')) + '</small></div>';
  }
  // 엿보기 현황 (하프타임: 획득 횟수 / 후반 벨트: 사용 횟수). 내용(무슨 주문표인지)은 보여주지 않는다.
  function mvPeekRow(st, mode) {
    if (!st.peek) return '';
    return '<div class="mv-peek">' + ["1", "2"].map(function (sn) {
      var pk = st.peek[sn];
      var txt = mode === "halftime" ? (pk.played ? ('엿보기 ' + pk.charges + '회 획득') : '엿보기 도전 전') : ('엿보기 ' + pk.used + '회 사용 · 남은 ' + pk.charges + '회');
      return '<span class="mv-peek-chip">' + esc(seatName(sn, st)) + ' · ' + txt + '</span>';
    }).join('') + '</div>';
  }
  function mvTime(endsAt, totalMs, opts) {
    // 큰 시계 한 덩어리. 값은 mainTick()이 채운다 (초기 문자열만 같은 규칙으로 미리 넣어 깜빡임을 막는다).
    opts = opts || {};
    return '<div class="mv-time" data-ends="' + endsAt + '" data-fmt="' + (opts.sec ? 'sec' : 'clock') + '"' + (opts.lowMs ? ' data-low="' + opts.lowMs + '"' : '') + '>'
      + mvFormat(endsAt, opts.sec ? 'sec' : 'clock') + '</div>';
  }
  function mvFormat(endsAt, fmt) {
    var left = Math.max(0, endsAt - nowMs());
    if (fmt === 'sec') return Math.ceil(left / 1000) + '<small>초</small>';
    return fmtClock(left);
  }
  function renderMain() {
    var st = state;
    var head = function (label) {
      return '<header class="mv-head"><div><span class="mv-eyebrow">BeatPhobia · Live</span><h1>초밥 서빙 게임</h1></div>'
        + '<div class="mv-chips">' + (label ? '<span class="mv-chip phase">' + esc(label) + '</span>' : '')
        + '<span class="mv-chip room">방 ' + esc(ROOM) + '</span></div></header>';
    };
    if (!ROOM) return '<div class="mv">' + head('') + '<div class="mv-body"><div class="mv-center"><h2>방 코드가 없어요</h2><p>주소 끝에 ?view=main 만 붙여 열면 새 방이 만들어져요.</p></div></div></div>';
    if (!st) return '<div class="mv">' + head('') + '<div class="mv-body"><div class="mv-center"><h2>연결 중...</h2></div></div></div>';
    var halfName = st.half === 2 ? "후반" : "전반";
    var html = '';

    if (st.phase === "lobby") {
      var joinUrl = location.origin + "/?room=" + ROOM;
      html = head("대기 중") + '<div class="mv-body"><div class="mv-center">'
        + '<div class="mv-panel"><h2>참가자를 기다리고 있어요</h2>'
        + '<div class="mv-seats">' + mvSeatCard(st, "1", st.ready, "준비") + mvSeatCard(st, "2", st.ready, "준비") + '</div>'
        + '<div class="mv-join">각자 기기에서 이 주소로 들어오세요<b>' + esc(joinUrl) + '</b></div>'
        + '<div class="mv-join mv-join-rail">레일 화면(공용)은 이 주소로<b>' + esc(location.origin + "/rail?room=" + ROOM) + '</b></div></div>'
        + '</div></div>';
    }
    else if (st.phase === "secure") {
      var endsAt = st.secureEndsAt || nowMs();
      var cats = TYPES.map(function (t, catIdx) {
        var left = boardLeft(st, catIdx), pips = '';
        for (var i = 0; i < t.count; i++) pips += '<span class="mv-pip' + (i < left ? '' : ' is-gone') + '">' + FISH_PIP + '</span>';
        return '<div class="mv-cat' + (left === 0 ? ' is-empty' : (left <= 2 ? ' is-few' : '')) + '" style="--c:' + t.color + '">'
          + '<div class="mv-cat-head"><span class="mv-cat-icon">' + CAT_ICONS[catIdx] + '</span><span class="mv-cat-name">' + esc(t.name) + '</span></div>'
          + '<div class="mv-cat-game">' + esc(MINI_NAME[t.mini] || "우봉고") + '</div>'
          + '<div class="mv-left">' + left + '<small>/ ' + t.count + '</small></div>'
          + '<div class="mv-pips">' + pips + '</div></div>';
      }).join('');
      html = head("초밥 제작 · " + halfName) + '<div class="mv-body">'
        + '<div class="mv-secure-top"><div class="mv-label">제작 남은 시간</div>'
        + mvTime(endsAt, SECURE_PHASE_MS, { lowMs: 30000 })
        + '<div class="mv-bar"><i data-ends="' + endsAt + '" data-total="' + SECURE_PHASE_MS + '"></i></div></div>'
        + '<div class="mv-cats">' + cats + '</div>' + mvLive(st) + '</div>' + introHtml(st, true);
    }
    else if (st.phase === "elevator") {
      var el = st.elevator, floorIdx = el.floorIdx;
      var stateLabel = "", ends = null, wait = "";
      if (el.state === "idle") { stateLabel = "출발 준비 중"; wait = "두 플레이어가 준비하면 출발해요"; }
      else if (el.state === "priority") { stateLabel = "우선 초밥 지정 시간"; ends = el.priorityWindowEndsAt; }
      else if (el.state === "thief") { stateLabel = "초밥도둑 배치 시간"; ends = el.thiefWindowEndsAt; }
      else if (el.state === "voting") { stateLabel = "회전 벨트 이동 중!"; ends = el.votingEndsAt; }
      else if (el.state === "choosing") { stateLabel = "같은 접시 초밥 선택 중"; ends = el.pendingChoice && el.pendingChoice.endsAt; }
      else if (el.state === "result") { stateLabel = "라운드 결과 확인 중"; wait = "다음 라운드 준비 대기"; }
      else { stateLabel = "서빙 종료"; }
      // 누적 위치: 벨트가 끝에서 처음으로 넘어가도(순환) 항상 최단 방향으로 도는 것처럼 보이게 한다.
      var mvDelta = 0;
      if (mvPrevFloor === null) mvCont = floorIdx;
      if (mvPrevFloor !== null) { mvDelta = (((floorIdx - mvPrevFloor) % FLOORS.length) + FLOORS.length) % FLOORS.length; if (mvDelta > FLOORS.length / 2) mvDelta -= FLOORS.length; }
      var carFrom = mvCont;
      mvCont += mvDelta;
      html = head("회전 벨트 · " + halfName) + '<div class="mv-body"><div class="mv-elev">'
        + '<div class="mv-shaft">' + ringHtml(carFrom, 'mv', 'mv-car', mvCont) + '</div>'
        + '<div class="mv-elev-main' + (el.state === "result" ? ' is-result' : '') + '">'
        + '<span class="mv-round">라운드 ' + el.round + ' / ' + ELEVATOR_ROUNDS + '</span>'
        + '<div class="mv-nowfloor"><span class="mv-label">현재 접시</span><span class="mv-floor-big">' + FLOORS[floorIdx] + '</span></div>'
        + '<div class="mv-state">' + esc(stateLabel) + '</div>'
        + (ends ? mvTime(ends, 0, { sec: true }) : (wait && !((el.state === "idle" || el.state === "result") && el.gateEndsAt) ? '<div class="mv-wait">' + esc(wait) + '</div>' : ''))
        + ((el.state === "idle" || el.state === "result") && el.gateEndsAt ? '<div class="mv-wait">' + esc(wait) + ' · <b class="mv-time mv-auto" data-ends="' + el.gateEndsAt + '" data-fmt="sec">' + mvFormat(el.gateEndsAt, 'sec') + '</b> 뒤 자동 진행</div>' : '')
        + (el.state === "result" ? mvResult(st) : '')
        + (st.half === 2 ? mvPeekRow(st, "elevator") : '')
        + '</div></div></div>';
      mvPrevFloor = floorIdx;
      return '<div class="mv">' + html + '</div>';
    }
    else if (st.phase === "halftime") {
      var h1 = st.halfHistory && st.halfHistory[0];
      html = head("하프타임") + '<div class="mv-body"><div class="mv-center"><h2>전반 종료</h2>'
        + (h1 ? '<div class="mv-scores">' + ["1", "2"].map(function (sn) { return '<div class="mv-score">' + esc(seatName(sn, st)) + '<b>' + fmtWon(h1.scores[sn]) + '</b></div>'; }).join('') + '</div>' : '')
        + '<p>잠시 후 후반이 시작돼요</p>'
        + '<div class="mv-seats">' + mvSeatCard(st, "1", st.halftimeReady, "준비") + mvSeatCard(st, "2", st.halftimeReady, "준비") + '</div>'
        + mvPeekRow(st, "halftime")
        + '</div></div>';
    }
    else if (st.phase === "end") {
      var s1 = st.scores ? st.scores["1"] : 0, s2 = st.scores ? st.scores["2"] : 0;
      var winner = s1 === s2 ? "무승부" : (s1 > s2 ? (seatName("1", st) + " 승리") : (seatName("2", st) + " 승리"));
      html = head("게임 종료") + '<div class="mv-body"><div class="mv-center"><div class="mv-winner">' + esc(winner) + '</div>'
        + '<div class="mv-scores">' + ["1", "2"].map(function (sn) { return '<div class="mv-score">' + esc(seatName(sn, st)) + ' 총점<b>' + fmtWon(sn === "1" ? s1 : s2) + '</b></div>'; }).join('') + '</div>'
        + '</div></div>';
    }
    if (st.phase !== "elevator") mvPrevFloor = null; // 다음에 회전 벨트가 시작되면 제자리에서 시작
    return '<div class="mv' + (st.phase === "lobby" ? ' mv-splash' : '') + '">' + (st.phase === "lobby" ? splashArt() : '') + html + '</div>';
  }
  // 그린 직후: 회전 벨트 칸을 새 접시로 옮긴다 (이전 접시에서 출발한 모습으로 그려 두었다가 다음 프레임에 이동 -> CSS transition)
  function mainAfterRender() {
    mainTick();
    var car = document.getElementById("mv-car");
    if (!car) return;
    var to = car.getAttribute("data-to");
    if (car.style.getPropertyValue("--cur") === to) return;
    void car.offsetWidth;
    requestAnimationFrame(function () { requestAnimationFrame(function () { car.style.setProperty("--cur", to); }); });
  }
  function mainTick() {
    var n = nowMs();
    Array.prototype.forEach.call(document.querySelectorAll(".mv-time[data-ends]"), function (e) {
      var ends = parseInt(e.getAttribute("data-ends"), 10), fmt = e.getAttribute("data-fmt");
      e.innerHTML = mvFormat(ends, fmt);
      var low = parseInt(e.getAttribute("data-low") || "0", 10);
      e.classList.toggle("is-low", !!low && ends - n < low);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".mv-bar > i[data-ends]"), function (e) {
      var ends = parseInt(e.getAttribute("data-ends"), 10), total = parseInt(e.getAttribute("data-total"), 10);
      var pct = Math.max(0, Math.min(100, (ends - n) / total * 100));
      e.style.width = pct + "%";
      e.classList.toggle("is-low", ends - n < 30000);
    });
  }

  function showToast(msg) {
    var el = document.getElementById("toast");
    if (el) el.remove();
    if (!msg) return;
    var d = document.createElement("div");
    d.id = "toast"; d.className = "toast"; d.textContent = msg;
    document.body.appendChild(d);
    setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 2600);
  }

  function render() {
    // 팀 컬러 테마: 내 좌석이 정해져 있으면 body[data-team]이 king/hunter가 된다 (CSS가 색을 바꾼다). 관전/메인 모니터는 중립.
    var tm = (!MAIN && !RAIL && mySeat()) ? COURIERS[Number(mySeat()) - 1] : null;
    if (tm) document.body.setAttribute("data-team", tm.key); else document.body.removeAttribute("data-team");
    document.getElementById("app").innerHTML = renderBody();
    if (MAIN) mainAfterRender();
    if (RAIL) railTick();
  }

  // ---------- event handling ----------
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-action]");
    if (!t) return;
    var action = t.getAttribute("data-action");

    if (action === "join-team") {
      // 좌석 번호는 서버가 정해서 돌려주므로(먼저 온 사람이 "1" = 초밥왕) 여기선 낙관적으로 세팅하지 않는다 --
      // 다음 "state" 브로드캐스트에서 내 clientId가 어느 좌석의 주인이 됐는지 보고 그때 확정한다
      // (connectWS의 onmessage 참고). 여기선 그냥 요청만 보낸다.
      send({ type: "join-team" });
      return;
    }
    if (action === "open-cell") { openCell(t.getAttribute("data-cell")); return; }
    if (action === "rail-press") {
      // 레일 화면 전용: side(1/2) 쪽 플레이어에게 그 종류 게임을 띄우라고 서버에 요청한다. 칸 선택/중복 방지는 서버가 한다.
      var rp = { type: "rail-press", side: t.getAttribute("data-side"), cat: parseInt(t.getAttribute("data-cat"), 10) };
      var rcell = t.getAttribute("data-cell"); if (rcell) rp.cellId = rcell;
      send(rp);
      return;
    }
    if (action === "rail-join") {
      var rc = (document.getElementById("rail-code").value || "").trim().toUpperCase();
      if (rc) window.location.href = "/rail?room=" + encodeURIComponent(rc);
      return;
    }
    if (action === "open-type") {
      // 레일 화면의 종류 버튼: 그 종류의 아직 안 가져간 칸 중 첫 번째를 연다 (칸끼리 구별이 없는 종류 전용)
      var typeIdx = parseInt(t.getAttribute("data-cat"), 10);
      var tt = TYPES[typeIdx];
      var freeCell = null, sawPending = false;
      for (var fi = 0; fi < state.board.length; fi++) {
        var bc = state.board[fi];
        if (bc.catIdx !== typeIdx || bc.taken) continue;
        if (local.pending[bc.id] && Date.now() - local.pending[bc.id] < 2000) { sawPending = true; continue; } // 방금 내가 끝낸 칸(브로드캐스트 대기 중)
        freeCell = bc; break;
      }
      if (!freeCell) { if (!sawPending) showToast(tt.name + "은(는) 이미 소진됐어요"); return; }
      if (tt.mini && window.MiniGames) { openMiniGame(freeCell.id); return; }
      newSushiPick(freeCell.id);
      local.openCellId = freeCell.id; render(); return;
    }
    if (action === "give-up") { local.openCellId = null; notifyGameClosed(); render(); return; }
    if (action === "complete-cell") {
      var cid = t.getAttribute("data-cell");
      markPending(cid);
      local.openCellId = null;
      send({ type: "secure-cell", seat: mySeat(), cellId: cid, sushi: sushiFor(cid) });
      render();
      return;
    }
    if (action === "vote-up" || action === "vote-down") {
      send({ type: "vote", seat: mySeat(), dir: action === "vote-up" ? "up" : "down" });
      return;
    }
    if (action === "pick-priority") {
      var invId = t.getAttribute("data-inv");
      send({ type: "set-priority", seat: mySeat(), invoiceId: invId ? invId : null });
      return;
    }
    if (action === "confirm-priority") {
      send({ type: "confirm-priority", seat: mySeat() });
      return;
    }
    if (action === "choose-delivery") {
      send({ type: "choose-delivery", seat: mySeat(), invoiceId: t.getAttribute("data-inv") });
      return;
    }
    if (action === "start-peek") { openPeekGame(); return; }
    if (action === "use-peek") { usePeek(); return; }
    if (action === "place-thief") {
      send({ type: "place-thief", seat: mySeat(), floorIdx: parseInt(t.getAttribute("data-floor-idx"), 10) });
      return;
    }
    if (action === "skip-thief") {
      send({ type: "place-thief", seat: mySeat(), floorIdx: null });
      return;
    }
    if (action === "restart-ready") {
      // 다른 ready-gate(vote-up, place-thief 등)와 동일하게 낙관적 로컬 갱신 없이 그냥 보내기만
      // 한다 -- 서버가 다음 state 브로드캐스트로 st.restartReady[seat]를 채워서 돌려주면
      // renderRestartGate가 그걸 보고 버튼을 비활성화한다. 두 번 눌려도 서버가 멱등하게 무시한다.
      send({ type: "restart-ready", seat: mySeat() });
      return;
    }
  });

  document.addEventListener("keydown", function (e) {
    if (MAIN) return; // 메인 모니터는 입력을 받지 않는다 (스페이스/방향키가 게임에 영향 주면 안 됨)
    if (e.code === "Space" || e.key === " " || e.key === "Spacebar") {
      var seat = mySeat();
      if (seat && state && state.phase === "lobby" && !e.repeat && !state.ready[seat]) {
        e.preventDefault();
        send({ type: "set-ready", seat: seat });
      } else if (seat && state && state.phase === "elevator" && (state.elevator.state === "result" || state.elevator.state === "idle") && !e.repeat && !state.elevator.readyNext[seat]) {
        e.preventDefault();
        send({ type: "elevator-ready", seat: seat });
      } else if (seat && state && state.phase === "elevator" && state.elevator.state === "priority" && !e.repeat && !state.elevator.priorityConfirmed[seat]) {
        e.preventDefault();
        send({ type: "confirm-priority", seat: seat });
      } else if (seat && state && state.phase === "halftime" && !mg && !e.repeat && !state.halftimeReady[seat]) {
        e.preventDefault();
        send({ type: "halftime-ready", seat: seat });
      }
      return;
    }
    if (e.code === "KeyE" && !e.repeat && !mg && state && state.phase === "elevator" && state.half === 2) { usePeek(); return; }
    if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
      var seat2 = mySeat();
      if (seat2 && state && state.phase === "elevator" && state.elevator.state === "voting") {
        e.preventDefault();
        send({ type: "vote", seat: seat2, dir: e.code === "ArrowLeft" ? "up" : "down" });   // ← = 시계 방향(서버의 up), → = 반시계(down)
      }
    }
  });

  // 5초 이상 조작이 없으면 눌러야 할 버튼이 깜빡인다 (제작 단계). 게이트 자동 진행 카운트다운도 여기서 갱신한다.
  function nudgeTick() {
    var idle = state.phase === "secure" && !mg && !local.openCellId && nowMs() - lastAct > 5000;
    document.body.classList.toggle("nudge-on", idle);
    Array.prototype.forEach.call(document.querySelectorAll(".gate-count[data-ends]"), function (e) {
      e.textContent = Math.max(0, Math.ceil((parseInt(e.getAttribute("data-ends"), 10) - nowMs()) / 1000)) + "초 뒤 자동 진행";
    });
  }
  document.addEventListener("pointerdown", function () { lastAct = Date.now(); });
  document.addEventListener("keydown", function () { lastAct = Date.now(); });

  // ---------- local countdown display only: the server owns the actual round/phase transitions
  // via its own timers, so there is nothing for the client to "submit" or auto-advance here ----------
  setInterval(function () {
    if (!state) return;
    if (!MAIN) nudgeTick();
    if (MAIN) { mainTick(); return; }
    if (RAIL) { railTick(); return; }
    updateMiniClock();
    if (state.phase === "secure" && state.secureEndsAt) {
      var msLeft = state.secureEndsAt - nowMs();
      var barI = document.querySelector(".timer-bar > i");
      var numEl = document.querySelector(".timer-num");
      if (numEl) numEl.textContent = fmtClock(msLeft);
      if (barI) barI.style.width = Math.max(0, Math.min(100, (msLeft / SECURE_PHASE_MS) * 100)) + "%";
    } else if (state.phase === "elevator" && state.elevator.state === "voting" && state.elevator.votingEndsAt) {
      var left = state.elevator.votingEndsAt - nowMs();
      var clockEl = document.getElementById("round-clock");
      if (clockEl) clockEl.textContent = "남은 시간 " + fmtClock(Math.max(0, left));
    } else if (state.phase === "elevator" && state.elevator.state === "choosing" && state.elevator.pendingChoice) {
      var seatNow = mySeat();
      var alreadyChosen = seatNow && state.elevator.pendingChoice.chosen[seatNow];
      if (!alreadyChosen) {
        var leftC = state.elevator.pendingChoice.endsAt - nowMs();
        var choiceClockEl = document.getElementById("choice-clock");
        if (choiceClockEl) choiceClockEl.textContent = "남은 시간 " + fmtClock(Math.max(0, leftC));
      }
    } else if (state.phase === "elevator" && state.elevator.state === "priority" && state.elevator.priorityWindowEndsAt) {
      var leftP = state.elevator.priorityWindowEndsAt - nowMs();
      var priClockEl = document.getElementById("priority-clock");
      if (priClockEl) priClockEl.textContent = fmtClock(Math.max(0, leftP));
      var priBarEl = document.getElementById("priority-bar");
      if (priBarEl) priBarEl.style.width = Math.max(0, Math.min(100, (leftP / PRIORITY_PICK_MS) * 100)) + "%";
    } else if (state.phase === "elevator" && state.elevator.state === "thief" && state.elevator.thiefWindowEndsAt) {
      var seatNow2 = mySeat();
      var placedNow = seatNow2 && state.elevator.thieves.placedThisRound[seatNow2];
      var skippedNow = seatNow2 && state.elevator.thieves.skipped[seatNow2];
      var doneNow = (placedNow !== null && placedNow !== undefined) || skippedNow;
      if (!doneNow) {
        var leftT = state.elevator.thiefWindowEndsAt - nowMs();
        var thiefClockEl = document.getElementById("thief-clock");
        if (thiefClockEl) thiefClockEl.textContent = "남은 시간 " + fmtClock(Math.max(0, leftT));
      }
    }
  }, 200);

  sfxButton();
  render();
  connectWS();
})();
"""

APP_JS = (APP_JS_TEMPLATE
          .replace("@@TYPES_JSON@@", TYPES_JSON)
          .replace("@@CELLS_1_JSON@@", CELLS_1_JSON)
          .replace("@@CELLS_2_JSON@@", CELLS_2_JSON)
          .replace("@@FLOORS_JSON@@", FLOORS_JSON)
          .replace("@@ROOMS_JSON@@", ROOMS_JSON)
          .replace("@@COURIERS_JSON@@", COURIERS_JSON)
          .replace("@@BOX_ART_JSON@@", BOX_ART_JSON)
          .replace("@@SUSHI_IMG_JSON@@", SUSHI_IMG_JSON)
          .replace("@@HERO_URL@@", HERO_URL)
          .replace("@@ELEVATOR_ROUNDS@@", str(ELEVATOR_ROUNDS))
          .replace("@@SECURE_PHASE_MS@@", str(SECURE_PHASE_MS))
          .replace("@@VOTE_MS@@", str(VOTE_MS))
          .replace("@@PRIORITY_MULTIPLIER@@", str(PRIORITY_MULTIPLIER))
          .replace("@@SAME_FLOOR_CHOICE_MS@@", str(SAME_FLOOR_CHOICE_MS))
          .replace("@@HALVES@@", str(HALVES))
          .replace("@@THIEF_PLACE_MS@@", str(THIEF_PLACE_MS))
          .replace("@@PRIORITY_PICK_MS@@", str(PRIORITY_PICK_MS)))

# 2026-10-06: 제작 미니게임(상자 포장/불량 검수/주문표 붙이기) 모듈을 그대로 인라인한다. 단독 시험장
# (build_minigame_proto.py)이 쓰는 것과 같은 파일이라, 시험장에서 확인한 동작이 게임에서도 똑같다.
_here = os.path.dirname(os.path.abspath(__file__))
MINIGAMES_CSS = open(os.path.join(_here, "minigames.css"), encoding="utf-8").read()
MINIGAMES_JS = open(os.path.join(_here, "minigames.js"), encoding="utf-8").read()
MAINVIEW_CSS = open(os.path.join(_here, "mainview.css"), encoding="utf-8").read()   # 메인 모니터(?view=main) 전용 스타일
assert "</style" not in MAINVIEW_CSS
assert "</script" not in MINIGAMES_JS and "</style" not in MINIGAMES_CSS

full_html = (
    HEAD_HTML.replace("@@HERO_URL@@", HERO_URL).replace("</style>\n</head>", MINIGAMES_CSS + "\n" + MAINVIEW_CSS + "\n</style>\n</head>", 1)
    + '<script>' + MINIGAMES_JS + "</script>\n"
    + '<script>' + APP_JS + "</script>\n"
    + "</body></html>\n"
)
assert MINIGAMES_CSS in full_html, "minigames.css가 HTML에 들어가지 않았다 (HEAD_HTML의 </style></head> 자리를 못 찾음)"

os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(full_html)

size_kb = len(full_html.encode("utf-8")) / 1024
print(f"saved {OUT_HTML} - {size_kb:.1f} KB")
