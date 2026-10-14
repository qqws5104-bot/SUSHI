// 2026-10-13: [우봉고 모드] 레일 개편 -- 공용 레일 화면 좌/우 패널에서 두 사람이 각자 키(왼쪽 WASD+SPACE / 오른쪽 방향키+ENTER)로 동시에 손질(회 만들기)
// -> 서버 재료함(stock)에 회가 쌓임(공급량 선점) -> 자리 화면에서 회로 퍼즐 조립(secure-cell fromStock) -> 초밥 제작.
process.env.PORT = "3108"; process.env.TEST_HOOKS = "1";
require("./server.js");
const { chromium } = require("playwright"); const http = require("http");
const assert = require("assert");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, { timeout = 8000, label = "cond" } = {}) { const t = Date.now(); for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t > timeout) throw new Error("timeout: " + label); await sleep(60); } }
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const room = await new Promise((res, rej) => http.get("http://localhost:3108/", (r) => res(new URL(r.headers.location, "http://localhost:3108").searchParams.get("room"))).on("error", rej));
  const mk = async () => (await br.newContext({ viewport: { width: 1280, height: 760 } })).newPage();
  const p1 = await mk(), p2 = await mk(), rail = await mk();
  const base = "http://localhost:3108/?room=" + room + "&mgtest=1";
  await p1.goto(base); await p2.goto(base); await rail.goto("http://localhost:3108/rail?room=" + room + "&mgtest=1"); await sleep(600);
  const click = (p, s) => p.evaluate((q) => { const e = document.querySelector(q); e && e.click(); return !!e; }, s);
  const text = (p) => p.evaluate(() => document.body.innerText);
  const gr = () => global.__rooms.get(room).room; const st = () => gr().state;
  await click(p1, '[data-action="join-team"]'); await sleep(300); await click(p2, '[data-action="join-team"]'); await sleep(300);
  // 플레이 시작 전 게임 방법 설명(4단계 카드): 플레이어 대기실 / 레일 / 메인 모두
  const mainP = await mk(); await mainP.goto("http://localhost:3108/?room=" + room + "&view=main"); await sleep(500);
  for (const [n, pg] of [["대기실", p1], ["레일", rail], ["메인", mainP]]) assert.strictEqual((await pg.$$(".howto li")).length, 4, n + " 대기 화면에 게임 방법 4단계");
  await p1.keyboard.press("Space"); await p2.keyboard.press("Space"); await sleep(800);
  assert.strictEqual(st().phase, "secure");
  assert.deepStrictEqual(st().stock, { "1": [0, 0, 0, 0], "2": [0, 0, 0, 0] }, "재료함 초기값");

  // 레일 화면: 좌/우 패널 + 종류 카드 4장씩
  await waitFor(async () => (await rail.$$("#rp-1 .rp-card")).length === 4 && (await rail.$$("#rp-2 .rp-card")).length === 4, { label: "rail panes" });
  assert((await text(p1)).includes("레일 화면에서 손질해 회를 만드세요"), "자리 화면(레일 모드)에 안내");
  assert.strictEqual(await p1.evaluate(() => !!document.querySelector('.rail-btn[data-action="open-type"]:not([disabled])')), false, "회가 없으면 조립 버튼이 잠김");
  assert((await text(p1)).includes("우봉고"), "자리 화면에 우봉고 표기");

  // 레일 손질(디지털): 1번 = S로 흰살생선(cat 1) 시작 -> 연타, 2번 = 오른쪽 Shift로 장어(cat 2)
  await rail.keyboard.press("KeyD"); await rail.keyboard.press("ArrowRight"); await rail.keyboard.press("ArrowRight"); await sleep(150);
  await rail.keyboard.press("KeyS"); await rail.keyboard.press("ShiftRight"); await sleep(300);
  for (let i = 0; i < 25 && (st().stock["1"][1] < 1 || st().stock["2"][2] < 1); i++) { await rail.keyboard.press("KeyS"); await rail.keyboard.press("ShiftRight"); await sleep(50); }
  await waitFor(() => st().stock["1"][1] >= 1 && st().stock["2"][2] >= 1, { timeout: 8000, label: "양쪽 회 +1" });
  await waitFor(async () => (await p2.evaluate(() => +document.querySelector('.rw-row[data-cat="2"] .rw-kai').textContent)) >= 1, { label: "p2 재료함 표시" });
  await waitFor(() => rail.evaluate(() => !document.querySelector("#rp-1").classList.contains("is-playing") && !document.querySelector("#rp-2").classList.contains("is-playing")), { label: "레일 휴식" }); await sleep(500);
  const k0 = st().stock["2"][2];
  assert.strictEqual(await p2.evaluate(() => !!document.querySelector('.rw-row[data-cat="1"] .rail-btn:not([disabled])')), false, "p2는 흰살생선 회가 없어 잠김");
  // 자리: 조립 = 우봉고 오버레이(퍼즐 이미지 + 포기/완료)
  await click(p2, '.rw-row[data-cat="2"] .rail-btn[data-action="open-type"]'); await sleep(400);
  assert.strictEqual(await p2.evaluate(() => !!document.querySelector("#puzzle-overlay img")), true, "우봉고 퍼즐 이미지");
  assert.strictEqual(await p2.evaluate(() => !!document.querySelector("#mg-layer:not(.hidden)")), false, "디지털 미니게임은 안 뜸");
  await click(p2, '[data-action="give-up"]'); await sleep(200);
  assert.strictEqual(st().stock["2"][2], k0, "포기하면 회는 그대로");
  assert.strictEqual(st().players["2"].invoices.length, 0);
  await click(p2, '.rw-row[data-cat="2"] .rail-btn[data-action="open-type"]'); await sleep(300);
  await click(p2, '[data-action="complete-cell"]');
  await waitFor(() => st().stock["2"][2] === k0 - 1 && st().players["2"].invoices.length === 1, { label: "완료 -> 초밥 제작, 회 소모" });
  assert.strictEqual(st().board.filter((c) => c.takenBy === "2").length, 1);
  assert.strictEqual(st().board.filter((c) => c.takenBy === "1").length, 0, "p1 칸은 그대로");
  // 회가 없는 p1이 완료 메시지를 보내도 칸을 못 가진다
  const r0 = gr(); r0.secureCell("1", "valuable-1", "eel", true); assert.strictEqual(r0.state.players["1"].invoices.length, 0, "회 없이는 조립 불가");
  // 레일을 닫으면 옛 방식(우봉고 오버레이로 바로 확보)
  await rail.close(); await waitFor(async () => (await p1.evaluate(() => !!document.querySelector('.board-grid'))), { label: "레일 없으면 기존 보드" });
  await click(p1, '.board-grid [data-action="open-cell"]'); await sleep(300);
  assert.strictEqual(await p1.evaluate(() => !!document.querySelector("#puzzle-overlay img")), true, "레일 없으면 바로 우봉고");
  console.log("PASS test_rail_ubongo");
  await br.close(); process.exit(0);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
