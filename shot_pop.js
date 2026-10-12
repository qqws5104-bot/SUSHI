"use strict";
// 팝 UI 확인용: 2번 자리(스시헌터) 테마, 미니게임 창, 메인 모니터, 결과 화면. TEST_HOOKS=1 로 server.js를 띄운 상태에서 실행.
process.env.PORT = "3100"; process.env.TEST_HOOKS = "1";
require("./server.js");
const { chromium } = require("playwright");
const http = require("http");
const BASE = "http://localhost:3100", OUT = "/tmp/shots_pop";
require("fs").mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (p, s) => p.evaluate((sel) => { const e = document.querySelector(sel); if (!e) return false; e.click(); return true; }, s);
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const room = await new Promise((res, rej) => http.get(BASE + "/", (r) => res(new URL(r.headers.location, BASE).searchParams.get("room"))).on("error", rej));
  const url = BASE + "/?room=" + room;
  const mk = async (w, h) => (await br.newContext({ viewport: { width: w, height: h } })).newPage();
  const p1 = await mk(1280, 800), p2 = await mk(1280, 800), pm = await mk(1600, 900);
  await p1.goto(url); await p2.goto(url); await pm.goto(url + "&view=main");
  await sleep(800);
  await sleep(600); await p1.screenshot({ path: OUT + "/0_splash.png" }); await pm.screenshot({ path: OUT + "/0_splash_main.png" });
  await click(p1, '[data-action="join-team"]'); await sleep(300); await click(p2, '[data-action="join-team"]'); await sleep(500);
  await p2.screenshot({ path: OUT + "/a_hunter_lobby.png" }); await pm.screenshot({ path: OUT + "/a_main_lobby.png" });
  for (const p of [p1, p2]) await p.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true })));
  await sleep(1500);
  await p2.screenshot({ path: OUT + "/b_hunter_secure.png" }); await pm.screenshot({ path: OUT + "/b_main_secure.png" });
  // 미니게임 열기: 첫 번째 레일 버튼
  await p2.evaluate(() => { const b = document.querySelector('.rail-side.mine .rail-btn'); if (b) b.click(); });
  await sleep(900); await p2.screenshot({ path: OUT + "/c_minigame.png" });
  const gr = global.__rooms.get(room).room;
  await click(p2, '[data-action="mg-quit"]');
  gr._endSecurePhase(); gr._finishHalf(); gr.halftimeReady("1"); gr.halftimeReady("2"); gr._endSecurePhase(); gr._finishHalf();
  await sleep(1200);
  await p1.screenshot({ path: OUT + "/d_end_p1.png", fullPage: true }); await pm.screenshot({ path: OUT + "/d_end_main.png" });
  await br.close(); console.log("ok", OUT); process.exit(0);
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
