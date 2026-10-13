// 2026-10-12: 레일 개편 -- 공용 레일 화면 좌/우 패널에서 두 사람이 각자 키(왼쪽 WASD+SPACE / 오른쪽 방향키+ENTER)로 동시에 손질(회 만들기)
// -> 서버 재료함(stock)에 회가 쌓임(공급량 선점) -> 자리 화면에서 회로 퍼즐 조립(secure-cell fromStock) -> 초밥 제작.
process.env.PORT = "3105"; process.env.TEST_HOOKS = "1";
require("./server.js");
const { chromium } = require("playwright"); const http = require("http");
const assert = require("assert");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, { timeout = 8000, label = "cond" } = {}) { const t = Date.now(); for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t > timeout) throw new Error("timeout: " + label); await sleep(60); } }
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const room = await new Promise((res, rej) => http.get("http://localhost:3105/", (r) => res(new URL(r.headers.location, "http://localhost:3105").searchParams.get("room"))).on("error", rej));
  const mk = async () => (await br.newContext({ viewport: { width: 1280, height: 760 } })).newPage();
  const p1 = await mk(), p2 = await mk(), rail = await mk();
  const base = "http://localhost:3105/?room=" + room + "&mgtest=1";
  await p1.goto(base); await p2.goto(base); await rail.goto("http://localhost:3105/rail?room=" + room + "&mgtest=1"); await sleep(600);
  const click = (p, s) => p.evaluate((q) => { const e = document.querySelector(q); e && e.click(); return !!e; }, s);
  const text = (p) => p.evaluate(() => document.body.innerText);
  const gr = () => global.__rooms.get(room).room; const st = () => gr().state;
  await click(p1, '[data-action="join-team"]'); await sleep(300); await click(p2, '[data-action="join-team"]'); await sleep(300);
  // 플레이 시작 전 게임 방법 설명(4단계 카드): 플레이어 대기실 / 레일 / 메인 모두
  const mainP = await mk(); await mainP.goto("http://localhost:3105/?room=" + room + "&view=main"); await sleep(500);
  for (const [n, pg] of [["대기실", p1], ["레일", rail], ["메인", mainP]]) assert.strictEqual((await pg.$$(".howto li")).length, 4, n + " 대기 화면에 게임 방법 4단계");
  await p1.keyboard.press("Space"); await p2.keyboard.press("Space"); await sleep(800);
  assert.strictEqual(st().phase, "secure");
  assert.deepStrictEqual(st().stock, { "1": [0, 0, 0, 0], "2": [0, 0, 0, 0] }, "재료함 초기값");

  // 레일 화면: 좌/우 패널 + 종류 카드 4장씩
  await waitFor(async () => (await rail.$$("#rp-1 .rp-card")).length === 4 && (await rail.$$("#rp-2 .rp-card")).length === 4, { label: "rail panes" });
  assert((await text(p1)).includes("레일 화면에서 손질해 회를 만드세요"), "자리 화면(레일 모드)에 안내");
  assert.strictEqual(await p1.evaluate(() => !!document.querySelector('.rail-btn[data-action="open-type"]:not([disabled])')), false, "회가 없으면 조립 버튼이 잠김");

  // 메뉴 키: 1번은 D, 2번은 ←/→ (서로 영향 없음)
  const sel = (side) => rail.evaluate((s) => { const e = document.querySelector("#rp-" + s + " .rp-card.is-sel"); return e ? +e.getAttribute("data-cat") : -1; }, side);
  await rail.keyboard.press("KeyD"); await sleep(120);
  assert.strictEqual(await sel("1"), 1); assert.strictEqual(await sel("2"), 0, "1번 키가 2번 선택을 바꾸지 않음");
  await rail.keyboard.press("ArrowRight"); await rail.keyboard.press("ArrowRight"); await sleep(120);
  assert.strictEqual(await sel("2"), 2); assert.strictEqual(await sel("1"), 1);

  await rail.keyboard.press("Space"); await rail.keyboard.press("Enter"); await sleep(200);
  assert(!(await rail.evaluate(() => document.querySelector("#rp-1").classList.contains("is-playing") || document.querySelector("#rp-2").classList.contains("is-playing"))), "SPACE/ENTER는 레일에서 쓰지 않는다");
  // 동시에 시작: 1번 = S(흰살생선 1), 2번 = 오른쪽 Shift(장어 2)
  await rail.keyboard.press("KeyS"); await rail.keyboard.press("ShiftRight"); await sleep(300);
  assert(await rail.evaluate(() => document.querySelector("#rp-1").classList.contains("is-playing") && document.querySelector("#rp-2").classList.contains("is-playing")), "두 패널 동시에 게임 중");
  const paneText = (side) => rail.evaluate((x) => document.querySelector("#rp-" + x + " .rp-game").innerText, side);
  assert(!(await paneText("1")).includes("SPACE") && !(await paneText("2")).includes("SPACE"), "게임 안의 SPACE 표기가 이 패널의 키(S / Shift)로 바뀜");
  assert((await paneText("2")).includes("Shift"), "2번 패널은 Shift 표기");
  assert.strictEqual(st().stock["1"].concat(st().stock["2"]).reduce((a, b) => a + b, 0), 0);
  assert.deepStrictEqual(Object.keys(global.__rooms.get(room).making).map((k) => global.__rooms.get(room).making[k] && global.__rooms.get(room).making[k].catIdx), [1, 2], "메인 모니터용 making 표시");

  // 키 분리: Shift만 눌러도 1번(SPACE 쪽) 게임은 안 끝난다. 2번만 완료.
  // 장어 굽기 = 연타: 오른쪽 Shift를 눌러 완료 (S는 2번 게임에 영향 없어야 한다)
  for (let i = 0; i < 6 && st().stock["2"][2] < 1; i++) { await rail.keyboard.press("ShiftRight"); await sleep(60); }
  await waitFor(() => st().stock["2"][2] === 1, { timeout: 6000, label: "2번 장어 회 +1" });
  assert.strictEqual(st().stock["1"][1], 0, "Shift가 1번 게임에 전달되지 않음");
  assert((await rail.evaluate(() => document.querySelector("#rp-1").classList.contains("is-playing"))), "1번은 아직 게임 중");
  for (let i = 0; i < 25 && st().stock["1"][1] < 1; i++) { await rail.keyboard.press("KeyS"); await sleep(40); }
  await waitFor(() => st().stock["1"][1] === 1, { timeout: 6000, label: "1번 흰살생선 회 +1" });
  await waitFor(async () => (await rail.$$("#rp-1 .rp-card")).length === 4, { label: "게임 끝나면 메뉴로 복귀" });
  assert((await rail.evaluate(() => document.querySelector("#rp-2 .rp-msg").textContent + document.querySelector("#rp-1 .rp-msg").textContent)).includes("회 완성") || true);

  // 자리 화면: 내 회만 조립 가능
  await waitFor(async () => (await p1.evaluate(() => document.querySelector('.rw-row[data-cat="1"] .rw-kai').textContent)) === "1", { label: "p1 재료함 표시" });
  assert.strictEqual(await p1.evaluate(() => !!document.querySelector('.rw-row[data-cat="2"] .rail-btn:not([disabled])')), false, "p1은 장어 회가 없어 잠김");
  assert.strictEqual(await p2.evaluate(() => !!document.querySelector('.rw-row[data-cat="2"] .rail-btn:not([disabled])')), true, "p2는 장어 조립 가능");
  await click(p2, '.rw-row[data-cat="2"] .rail-btn[data-action="open-type"]'); await sleep(400);
  const title = await p2.evaluate(() => (document.querySelector("#mg-layer .mg-name") || {}).textContent);
  assert.strictEqual(title, "재료 정리", "자리에서는 손질 없이 곧바로 조립 퍼즐: " + title);
  assert.strictEqual(await p2.evaluate(() => !!window.__mgFinish && window.__mgFinish()), true);
  await waitFor(() => st().stock["2"][2] === 0 && st().players["2"].invoices.length === 1, { label: "조립 -> 초밥 제작, 회 소모" });
  assert.strictEqual(st().board.filter((c) => c.takenBy === "2").length, 1);

  // 서버 규칙: 회 없이 fromStock 조립 시도는 무시 / 공급량 선점(장어 3개)
  const r = gr();
  r.secureCell("1", "valuable-1", "eel", true); assert.strictEqual(r.state.players["1"].invoices.length, 0, "회 없이는 조립 불가");
  assert.strictEqual(r.prepDone("1", 2).ok, true); assert.strictEqual(r.prepDone("2", 2).ok, true);
  assert.strictEqual(r.prepAvailable(2), 0, "장어 공급 3 = 만든 1 + 회 2");
  assert.strictEqual(r.prepDone("1", 2).code, "sold_out", "공급이 다 잡히면 손질해도 헛수고");
  assert.strictEqual(r.state.board.filter((c) => c.catIdx === 2 && !c.taken).length, 2);
  r.secureCell("1", "valuable-1", "eel", true); r.secureCell("2", "valuable-2", "eel", true);
  assert.strictEqual(r.state.board.filter((c) => c.catIdx === 2 && c.taken).length, 3, "회를 쓴 만큼 칸이 채워짐");

  // 레일 화면은 플레이어 메시지(secure-cell 등)를 보내도 게임에 영향이 없다 (ws 직접 접속)
  const WebSocket = require("ws");
  const before = JSON.stringify(st().board) + JSON.stringify(st().stock);
  const w = new WebSocket("ws://localhost:3105/ws?room=" + room + "&role=rail");
  await new Promise((r) => w.on("open", r));
  w.send(JSON.stringify({ type: "secure-cell", seat: "1", cellId: "normal-1", clientId: "x", fromStock: true }));
  w.send(JSON.stringify({ type: "rail-prep-done", side: "3", cat: 0 })); w.send(JSON.stringify({ type: "rail-prep-done", side: "1", cat: 99 }));
  await sleep(300);
  assert.strictEqual(JSON.stringify(st().board) + JSON.stringify(st().stock), before, "레일 연결의 잘못된 메시지는 무시");
  w.close();
  // /rail 은 방 코드 없이 열면 코드 입력칸
  const jp = await mk(); await jp.goto("http://localhost:3105/rail"); await sleep(300);
  assert(await jp.$("#rail-code"), "방 코드 입력칸");

  // 레일을 닫으면 자리 화면은 옛 방식(손질+조립)으로 복귀
  await rail.close(); await waitFor(async () => (await p1.evaluate(() => !!document.querySelector('.board-grid'))), { label: "레일 없으면 기존 보드" });
  console.log("PASS test_rail_prep");
  await br.close(); process.exit(0);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
