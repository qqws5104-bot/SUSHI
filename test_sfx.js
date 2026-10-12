// 2026-10-12: 효과음 -- 버튼/접시/미니게임 선택/벨트 이동 때 소리(오실레이터)가 실제로 만들어지는지, 끄기 버튼이 먹는지.
process.env.PORT = "3101"; process.env.TEST_HOOKS = "1";
require("./server.js");
const { chromium } = require("playwright"); const http = require("http");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const assert = require("assert");
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--autoplay-policy=no-user-gesture-required"] });
  const room = await new Promise((res, rej) => http.get("http://localhost:3101/", (r) => res(new URL(r.headers.location, "http://localhost:3101").searchParams.get("room"))).on("error", rej));
  const ctx = await br.newContext(); const p1 = await ctx.newPage(); const p2 = await (await br.newContext()).newPage();
  const spy = () => { window.__tones = []; const orig = AudioContext.prototype.createOscillator; AudioContext.prototype.createOscillator = function () { const o = orig.call(this); const f = o.start.bind(o); o.start = function (t) { window.__tones.push(this.frequency.value); return f(t); }; return o; }; };
  for (const p of [p1, p2]) await p.addInitScript(spy);
  const url = "http://localhost:3101/?room=" + room;
  await p1.goto(url); await p2.goto(url); await sleep(700);
  const tones = (p) => p.evaluate(() => window.__tones.length);
  const click = (p, s) => p.evaluate((q) => { const e = document.querySelector(q); e && e.click(); return !!e; }, s);
  assert(await p1.$("#sfx-toggle"), "효과음 토글 버튼이 있어야 함");
  await p1.mouse.click(400, 300); // 사용자 제스처로 오디오 잠금 해제
  await click(p1, '[data-action="join-team"]'); await sleep(300); await click(p2, '[data-action="join-team"]'); await sleep(300);
  assert((await tones(p1)) > 0, "일반 버튼 클릭에 소리");
  for (const p of [p1, p2]) await p.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true })));
  await sleep(1200);
  let n = await tones(p1);
  await click(p1, '.rail-btn[data-action="open-type"]'); await sleep(200);
  assert((await tones(p1)) >= n + 2, "미니게임 선택음(2음)");
  n = await tones(p1);
  await click(p1, '[data-action="mg-quit"], .mg-quit, #mg-layer button'); await sleep(200);
  // 벨트: 접시가 바뀌면 둘 다 소리
  const gr = global.__rooms.get(room).room;
  await click(p1, '#mg-layer [data-action="mg-quit"]');
  gr._endSecurePhase(); await sleep(300);
  gr.setElevatorReady("1"); gr.setElevatorReady("2"); await sleep(300);
  const a = await tones(p1), b = await tones(p2);
  gr.vote("1", "up"); await sleep(300);
  assert((await tones(p1)) >= a + 2 && (await tones(p2)) >= b + 2, "벨트가 움직이면 두 플레이어 모두 접시 음");
  // 끄기
  await click(p1, "#sfx-toggle"); await sleep(100);
  const off = await tones(p1); gr.vote("1", "up"); await sleep(300);
  assert.strictEqual(await tones(p1), off, "끄면 소리 없음");
  assert.strictEqual(await p1.getAttribute("#sfx-toggle", "aria-pressed"), "false");
  console.log("[test-sfx] ALL CHECKS PASSED");
  await br.close(); process.exit(0);
})().catch((e) => { console.error("[test-sfx] FAILED", e); process.exit(1); });
