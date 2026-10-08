"use strict";
// 스킨/벨트 화면 확인용 스크린샷 (SECURE_PHASE_MS를 10초로 줄이고 서버를 띄운 상태에서 실행)
const { chromium } = require("playwright");
const BASE = "http://localhost:3000", OUT = "/tmp/shots_sushi";
require("fs").mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function clickSel(p, s) { return p.evaluate((sel) => { const e = document.querySelector(sel); if (!e) return false; e.click(); return true; }, s); }
async function pressSpace(p) { await p.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true, cancelable: true }))); }
async function bodyText(p) { return p.evaluate(() => document.body.innerText); }
async function waitFor(fn, { timeout = 20000, label = "" } = {}) { const t = Date.now(); for (;;) { if (await fn()) return; if (Date.now() - t > timeout) throw new Error("timeout " + label); await sleep(120); } }
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const http = require("http");
  const room = await new Promise((res, rej) => http.get(BASE + "/", (r) => res(new URL(r.headers.location, BASE).searchParams.get("room"))).on("error", rej));
  const url = BASE + "/?room=" + room;
  const c1 = await br.newContext({ viewport: { width: 1280, height: 800 } }), c2 = await br.newContext({ viewport: { width: 1280, height: 800 } }), c3 = await br.newContext({ viewport: { width: 1600, height: 900 } });
  const p1 = await c1.newPage(), p2 = await c2.newPage(), pm = await c3.newPage();
  await p1.goto(url); await p2.goto(url); await pm.goto(url + "&view=main");
  await waitFor(async () => (await p1.locator(".seat-pick").count()) > 0, { label: "pick" });
  await p1.screenshot({ path: OUT + "/1_pick.png" });
  await clickSel(p1, '[data-action="pick-courier"][data-courier="haru"]');
  await clickSel(p2, '[data-action="pick-courier"][data-courier="pado"]');
  await sleep(500); await p1.screenshot({ path: OUT + "/2_lobby.png" });
  await pressSpace(p1); await pressSpace(p2);
  await waitFor(async () => (await bodyText(p1)).includes("초밥 제작"), { label: "secure" });
  await sleep(1500); await p1.screenshot({ path: OUT + "/3_secure.png" });
  await waitFor(async () => (await bodyText(p1)).includes("회전 벨트"), { label: "belt" });
  await sleep(500); await p1.screenshot({ path: OUT + "/4_belt_idle.png" }); await pm.screenshot({ path: OUT + "/4m_main_idle.png" });
  await pressSpace(p1); await pressSpace(p2);
  await waitFor(async () => (await p1.locator('[data-action="vote-up"]').count()) > 0, { label: "vote" });
  for (let i = 0; i < 3; i++) { await clickSel(p1, '[data-action="vote-up"]'); await sleep(120); }
  await sleep(900); await p1.screenshot({ path: OUT + "/5_belt_moving.png" }); await pm.screenshot({ path: OUT + "/5m_main_moving.png" });
  await br.close(); console.log("ok", OUT);
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
