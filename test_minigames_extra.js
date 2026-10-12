// 2026-10-08: 소코반류 시험용 게임 5종(초밥 담기 / 도마 닦기 / 쌍둥이 서빙 / 컨베이어 잇기 / 초밥 쌓기) 시험장 검증.
// 정답을 풀이기(또는 테스트 훅)로 구해서 진짜 키 입력으로 클리어하고, 풀의 모든 판이 풀리는지, 조작(되돌리기/처음부터/막힘/실수)이
// 의도대로인지 확인한다. 서버 필요 없음. 사전: python3 build_minigame_proto.py
"use strict";
const path = require("path");
const { chromium } = require("playwright");
const { iceSolve, twinSolve } = require("./test_puzzle_solvers.js");

const URL = "file://" + path.join(__dirname, "minigame_proto.html");
function log(...a) { console.log("[test-extra]", ...a); }
function assert(c, m) { if (!c) throw new Error("ASSERT FAILED: " + m); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KEY = { U: "ArrowUp", D: "ArrowDown", L: "ArrowLeft", R: "ArrowRight" };
async function waitFor(fn, { timeout = 6000, interval = 50, label = "condition" } = {}) {
  const t0 = Date.now();
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t0 > timeout) throw new Error("timeout waiting for: " + label); await sleep(interval); }
}

async function main() {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const page = await (await browser.newContext({ viewport: { width: 900, height: 900 } })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/fonts\.g|ERR_|Failed to load resource/.test(m.text())) errors.push("console: " + m.text()); });
  await page.goto(URL);

  async function launch(kind, level) {
    await page.evaluate(({ kind, level }) => {
      if (window.__ctl) { window.__ctl.destroy(); window.__ctl = null; }
      document.getElementById("menu").hidden = true; document.getElementById("play").hidden = false;
      window.__res = null;
      window.__ctl = MiniGames.start(document.getElementById("host"), { kind, level, testHooks: true, label: "주황", onDone: (r) => { window.__res = r; }, onCancel() {} });
    }, { kind, level });
  }
  const result = () => page.evaluate(() => window.__res);
  const miss = async () => parseInt((await page.textContent(".mg-miss")).replace(/\D/g, ""), 10);
  const attr = (name) => page.getAttribute(".mg-body", name);
  const plan = async () => JSON.parse(await attr("data-plan"));
  async function pressKeys(path, gap) { for (const ch of path) { await page.keyboard.press(KEY[ch]); if (gap) await sleep(gap); } }
  async function poolRows(kind, per) { // 풀에서 여러 판을 뽑아 중복 없이 모은다
    const raw = await page.evaluate(({ kind, per }) => { const out = []; for (let lv = 1; lv <= 3; lv++) for (let k = 0; k < per; k++) { MiniGames.start(document.getElementById("host"), { kind, level: lv, testHooks: true, onDone() {} }); out.push([lv, document.querySelector(".mg-body").getAttribute("data-plan")]); } document.getElementById("host").innerHTML = ""; return out; }, { kind, per });
    const seen = new Set(), res = [];
    for (const [lv, p] of raw) { const o = JSON.parse(p), k = lv + JSON.stringify(o); if (!seen.has(k)) { seen.add(k); res.push([lv, o]); } }
    return res;
  }

  // ================= 초밥 담기 =================
  {
    const ranges = {};
    for (const [lv, o] of await poolRows("ice", 60)) {
      const sol = iceSolve(o.rows); assert(sol !== null, `ice L${lv}: every pool puzzle must be solvable\n${o.rows.join("\n")}`);
      (ranges[lv] = ranges[lv] || []).push(sol.length);
    }
    log("ice: 풀의 모든 판이 풀림 -- 최적 미끄러짐 수 " + Object.keys(ranges).map((l) => `L${l} ${Math.min(...ranges[l])}~${Math.max(...ranges[l])}(${ranges[l].length}판)`).join(" / "));
    for (let lv = 1; lv <= 3; lv++) {
      await launch("ice", lv);
      const o = await plan(), sol = iceSolve(o.rows);
      await pressKeys(sol, 700); // 미끄러지는 동안은 입력이 잠기므로 간격을 둔다
      await waitFor(result, { timeout: 8000, label: `ice L${lv} done` });
      const r = await result(); assert(r.ok && r.kind === "ice" && r.level === lv, "ice result " + JSON.stringify(r));
      log(`ice L${lv}: 최적 ${sol.length}번 미끄러져 클리어 (${r.ms}ms)`);
    }
    await launch("ice", 2);
    const o = await plan(), sol = iceSolve(o.rows), st = async () => (await attr("data-ic")).split(",").map(Number);
    const [x0, y0] = await st();
    await page.keyboard.press(KEY[sol[0]]); await sleep(700);
    assert((await st())[3] === 1, "one slide counted");
    await page.keyboard.press("z"); await sleep(50);
    const s1 = await st(); assert(s1[0] === x0 && s1[1] === y0 && s1[3] === 0, "undo returns to start");
    await page.keyboard.press(KEY[sol[0]]); await sleep(700); await page.keyboard.press("r"); await sleep(50);
    const s2 = await st(); assert(s2[0] === x0 && s2[1] === y0 && s2[3] === 0, "R restarts");
    // 벽 쪽: 방향 4개 중 움직이지 않는 방향은 제자리
    let bumped = false;
    for (const k of ["U", "D", "L", "R"]) { const b = await st(); await page.keyboard.press(KEY[k]); await sleep(700); const a = await st(); if (a[3] === b[3]) { bumped = true; assert(a[0] === b[0] && a[1] === b[1], "blocked direction stays put"); } else { await page.keyboard.press("r"); await sleep(50); } }
    log("ice: 되돌리기(Z), 처음부터(R), 벽 쪽은 제자리");
  }

  // ================= 쌍둥이 서빙 =================
  {
    const ranges = {};
    for (const [lv, o] of await poolRows("twin", 60)) {
      const sol = twinSolve(o.rows, !!o.mirror); assert(sol !== null, `twin L${lv}: every pool puzzle must be solvable\n${o.rows.join("\n")}`);
      assert(!!o.mirror === (lv === 3), `twin L${lv}: mirror only on L3`);
      (ranges[lv] = ranges[lv] || []).push(sol.length);
    }
    log("twin: 풀의 모든 판이 풀림 -- 최적 걸음 " + Object.keys(ranges).map((l) => `L${l} ${Math.min(...ranges[l])}~${Math.max(...ranges[l])}(${ranges[l].length}판)`).join(" / "));
    for (let lv = 1; lv <= 3; lv++) {
      await launch("twin", lv);
      const o = await plan(), sol = twinSolve(o.rows, !!o.mirror);
      await pressKeys(sol);
      await waitFor(result, { label: `twin L${lv} done` });
      const r = await result(); assert(r.ok && r.kind === "twin" && r.level === lv, "twin result " + JSON.stringify(r));
      log(`twin L${lv}: 최적 ${sol.length}걸음으로 클리어${o.mirror ? " (B 좌우 반대)" : ""} (${r.ms}ms)`);
    }
    await launch("twin", 2);
    const o = await plan(), sol = twinSolve(o.rows, false), st = async () => (await attr("data-tw")).split(",").map(Number);
    const s0 = await st();
    await pressKeys(sol.slice(0, 2)); assert((await st())[4] === 2, "2 moves counted");
    await page.keyboard.press("Backspace"); await page.keyboard.press("Backspace");
    const s1 = await st(); assert(s1.slice(0, 4).join() === s0.slice(0, 4).join() && s1[4] === 0, "undo x2 returns both couriers");
    await pressKeys(sol.slice(0, 3)); await page.keyboard.press("r");
    const s2 = await st(); assert(s2.slice(0, 4).join() === s0.slice(0, 4).join() && s2[4] === 0, "R restarts");
    assert((await miss()) === 0, "no mistakes in twin");
    log("twin: 되돌리기/처음부터로 두 초밥원이 함께 돌아감");
  }

  // ================= 도마 닦기 (한붓그리기 -- 점+선 그래프, 오일러 경로) =================
  {
    const trailOk = (o) => { // 풀이 점 순서가 모든 선을 정확히 한 번씩 지나는가
      const left = o.edges.map((e) => e.slice().sort((x, y) => x - y).join("-")); let ok = o.path.length === o.edges.length + 1;
      for (let i = 0; i + 1 < o.path.length && ok; i++) { const k = [o.path[i], o.path[i + 1]].sort((x, y) => x - y).join("-"), at = left.indexOf(k); if (at < 0) ok = false; else left.splice(at, 1); }
      return ok && left.length === 0;
    };
    const degOf = (o) => { const d = o.vertices.map(() => 0); o.edges.forEach(([a, b]) => { d[a]++; d[b]++; }); return d; };
    const sizes = {};
    for (const [lv, o] of await poolRows("route", 40)) {
      assert(trailOk(o), `route L${lv}: generated plan's solution must cover every line exactly once`);
      const d = degOf(o), odd = d.filter((x) => x % 2).length;
      assert(d.every((x) => x >= 2) && (lv === 1 ? odd === 0 : odd === 2), `route L${lv}: degrees >=2 and ${lv === 1 ? "no" : "exactly two"} odd points, got ${d}`);
      if (odd === 2) assert(d[o.path[0]] % 2 === 1, `route L${lv}: solution starts at an odd point`);
      sizes[lv] = o.edges.length;
    }
    log("route: 실행 중 생성한 판 모두 풀 수 있음 (얼룩 선 수 L1 " + sizes[1] + " / L2 " + sizes[2] + " / L3 " + sizes[3] + ")");
    const tap = (v) => page.dispatchEvent(`.eu-hit[data-v="${v}"]`, "pointerdown");
    for (let lv = 1; lv <= 3; lv++) {
      await launch("route", lv);
      const o = await plan(); for (const v of o.path) await tap(v);
      await waitFor(result, { label: `route L${lv} done` });
      const r = await result(); assert(r.ok && r.kind === "route" && r.mistakes === 0, "route clean run " + JSON.stringify(r));
      log(`route L${lv}: 선 ${o.edges.length}개를 한 번씩 닦아 클리어 (${r.ms}ms, 실수 0)`);
    }
    // 방향키 + Space 조작, 되돌리기 / 처음부터 / 막다른 길
    const st = async () => (await attr("data-eu")).split(",").map(Number);
    await launch("route", 3); let o = await plan();
    await tap(o.path[0]); assert((await st()).join() === `${o.path[0]},0`, "tapping a point starts there");
    await tap(o.path[1]); await tap(o.path[2]); assert((await st())[1] === 2, "two lines wiped");
    await page.keyboard.press("z"); assert((await st())[1] === 1, "Z undoes one line");
    await page.keyboard.press("r"); assert((await st()).join() === "-1,0", "R restarts with no start point");
    // 짝수 점에서 시작하면 어차피 못 끝낸다 -> 첫 선을 닦는 순간 막다른 길 = 실수 1회 + 안내
    const deg = degOf(o), evenV = deg.findIndex((x) => x % 2 === 0);
    await tap(evenV); const nb = o.edges.find((e) => e.includes(evenV)), other = nb[0] === evenV ? nb[1] : nb[0];
    await tap(other);
    assert((await miss()) === 1, "starting at an even point wastes the run: one mistake once the dead end happens");
    assert((await page.textContent(".mg-freeze-note")).length > 0, "a note explains the dead end");
    await page.keyboard.press("z");
    assert((await page.textContent(".mg-freeze-note")).length === 0 && (await miss()) === 1, "undoing out of the dead end clears the note");
    await page.keyboard.press("r"); for (const v of o.path) await tap(v);
    await waitFor(result, { label: "route after dead end done" });
    assert((await result()).mistakes === 1, "the dead-end mistake is in the result");
    // 키보드만으로: 방향키로 시작 점 선택 후 Space, 방향키로 선 따라가기 (가장 가까운 방향의 선)
    await launch("route", 1); o = await plan();
    await page.keyboard.press("Space"); assert((await st())[0] >= 0, "Space starts at the highlighted point");
    log("route: 점 눌러 시작/선 닦기, Z 한 선 되돌리기, R 처음부터, 막다른 길 = 실수 1회 + 안내, Space로 키보드 시작");
  }

  // ================= 컨베이어 잇기 =================
  {
    const st = async () => (await attr("data-pp")).split(",").map(Number);
    async function solvePipe() {
      const pl = await plan(); let [cx, cy] = await st();
      for (let i = 0; i < pl.presses.length; i++) {
        if (!pl.presses[i]) continue;
        const tx = i % pl.W, ty = (i / pl.W) | 0;
        while (cx !== tx) { await page.keyboard.press(cx < tx ? "ArrowRight" : "ArrowLeft"); cx += cx < tx ? 1 : -1; }
        while (cy !== ty) { await page.keyboard.press(cy < ty ? "ArrowDown" : "ArrowUp"); cy += cy < ty ? 1 : -1; }
        for (let k = 0; k < pl.presses[i]; k++) await page.keyboard.press("Space");
      }
    }
    const dims = [[4, 3], [5, 4], [6, 5]];
    for (let lv = 1; lv <= 3; lv++) {
      for (let k = 0; k < 12; k++) { await launch("pipe", lv); assert(!(await result()), "a fresh pipe puzzle starts unsolved"); const pl = await plan(); assert(pl.W === dims[lv - 1][0] && pl.H === dims[lv - 1][1], "pipe size"); }
      await launch("pipe", lv);
      const f0 = (await st())[2]; await solvePipe();
      await waitFor(result, { label: `pipe L${lv} done` });
      const r = await result(); assert(r.ok && r.kind === "pipe" && r.mistakes === 0, "pipe result " + JSON.stringify(r));
      log(`pipe L${lv}: ${dims[lv - 1].join("x")} 판을 돌려서 입구-출구 연결, 클리어 (${r.ms}ms)`);
    }
    await launch("pipe", 2);
    const pl = await plan(), idx = pl.presses.findIndex((p) => p > 0), tx = idx % pl.W, ty = (idx / pl.W) | 0;
    let [cx, cy] = await st(); assert(cx === 0, "cursor starts at the entrance column");
    for (let i = 0; i < tx; i++) await page.keyboard.press("ArrowRight"); for (let i = 0; i < ty; i++) await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Space"); assert((await st())[3] === 1, "rotation recorded"); await page.keyboard.press("Backspace"); assert((await st())[3] === 0, "undo rotation");
    log("pipe: 새 판은 항상 미완성으로 시작, 스페이스로 회전, Z/Backspace 되돌리기");
  }

  // ================= 초밥 쌓기 (하노이) =================
  {
    const st = async () => (await attr("data-hn")).split(",").map(Number);
    async function playMoves(moves) { for (const [a, b] of moves) { await page.keyboard.press(String(a + 1)); await page.keyboard.press("Space"); await page.keyboard.press(String(b + 1)); await page.keyboard.press("Space"); } }
    for (let lv = 1; lv <= 3; lv++) {
      await launch("hanoi", lv);
      const pl = await plan(); assert(pl.n === lv + 2 && pl.solution.length === Math.pow(2, pl.n) - 1, "optimal hanoi solution length");
      await playMoves(pl.solution);
      await waitFor(result, { label: `hanoi L${lv} done` });
      const r = await result(); assert(r.ok && r.kind === "hanoi" && r.mistakes === 0, "hanoi result " + JSON.stringify(r));
      log(`hanoi L${lv}: 상자 ${pl.n}개 최적 ${pl.solution.length}수로 클리어 (${r.ms}ms, 실수 0)`);
    }
    await launch("hanoi", 2);
    const pl = await plan();
    await playMoves([pl.solution[0]]); // 가장 작은 상자를 옮김
    assert((await st())[2] === 1, "one move counted");
    // 큰 상자를 작은 상자 위에 -> 실수
    await page.keyboard.press("1"); await page.keyboard.press("Space"); await page.keyboard.press(String(pl.solution[0][1] + 1)); await page.keyboard.press("Space");
    assert((await miss()) === 1, "big on small is one mistake"); assert((await st())[1] > 0, "the box is still in hand after a refused drop");
    await page.keyboard.press("1"); await page.keyboard.press("Space"); // 원래 칸(왼쪽)에 되놓기
    assert((await st())[1] === 0 && (await st())[2] === 1, "putting it back where it came from is free");
    await page.keyboard.press("Backspace"); assert((await st())[2] === 0, "undo takes the last move back");
    await page.keyboard.press("r"); assert((await st())[2] === 0, "R restarts");
    log("hanoi: 큰 상자를 작은 상자 위에 = 실수(손에 그대로), 제자리에 되놓기 무료, Z 되돌리기, R 처음부터");
  }

  if (errors.length) throw new Error("page errors: " + errors.join(" | "));
  await browser.close();
  log("ALL CHECKS PASSED");
}
main().catch((e) => { console.error("[test-extra] FAILED:", e); process.exit(1); });
