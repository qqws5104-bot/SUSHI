"use strict";
const { chromium } = require("playwright");
const { COURIERS } = require("./game-data.js");
const COURIER_NAME = {};
COURIERS.forEach((c) => { COURIER_NAME[c.key] = c.name; });

const BASE = "http://localhost:3000";
function log(...args) { console.log("[test-peek-ui]", ...args); }

async function clickSel(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    el.click();
    return true;
  }, selector);
}
async function countSel(page, selector) { return page.evaluate((sel) => document.querySelectorAll(sel).length, selector); }
async function bodyText(page) { return page.evaluate(() => document.body.innerText); }
async function pressSpace(page) {
  await page.evaluate(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true, cancelable: true }));
  });
}
async function waitFor(fn, { timeout = 15000, interval = 100, label = "condition" } = {}) {
  const start = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - start > timeout) throw new Error("timeout waiting for: " + label);
    await new Promise((r) => setTimeout(r, interval));
  }
}

// 2026-10-06: 라운드 준비(스페이스) 직후 우선 초밥 지정 10초 창이 열린다 -- 지정할 초밥이 있는 쪽은 "확정"으로 통과시킨다.
async function passPriority(p1, p2, nextSel) {
  await waitFor(async () => (await countSel(p1, ".priority-window")) > 0 || (await countSel(p1, nextSel)) > 0, { label: "priority window (or straight on)", timeout: 8000 });
  if ((await countSel(p1, ".priority-window")) === 0) return;
  if (await countSel(p1, '[data-action="confirm-priority"]')) await clickSel(p1, '[data-action="confirm-priority"]');
  if (await countSel(p2, '[data-action="confirm-priority"]')) await clickSel(p2, '[data-action="confirm-priority"]');
  await waitFor(async () => (await countSel(p1, ".priority-window")) === 0, { label: "priority window closes", timeout: 4000 });
}

// 2026-10-12: 초밥 하나 = 손질(타이밍 액션) -> 제작 퍼즐. 테스트 모드에서는 초록 구간이 막대 전체라 SPACE만 눌러도 통과한다.
async function passPrep(page) {
  for (let i = 0; i < 80; i++) {
    const prep = await page.$("#mg-layer .mg-kind-prep");
    if (!prep) { if (i > 5 && (await page.$("#mg-layer .mg-root"))) return; await page.waitForTimeout(100); continue; }
    if (!(await page.$("#mg-layer .mg-kind-prep .mg-done.is-on"))) await page.keyboard.press("Space");
    await page.waitForTimeout(90);
  }
  throw new Error("passPrep: 손질 단계를 통과하지 못함");
}


// 2026-10-12: 엿보기 UI -- 하프타임 미니게임(스페이스가 준비 완료로 새지 않는지) / 후반 벨트 패널 / 도둑 배치 표시
// 사전 준비: SECURE_PHASE_MS를 10초로 줄이고 build_client.py 재빌드 + 서버 재시작 (regress.sh가 해 준다).
let DBG = null;
async function main() {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const seedCtx = await browser.newContext();
  const seedPage = await seedCtx.newPage();
  await seedPage.goto(BASE + "/");
  const room = new URL(seedPage.url()).searchParams.get("room");
  await seedCtx.close();
  const roomUrl = BASE + "/?room=" + room + "&mgtest=1";
  const ctx1 = await browser.newContext(), ctx2 = await browser.newContext();
  const p1 = await ctx1.newPage(), p2 = await ctx2.newPage();
  const pm = await (await browser.newContext()).newPage();
  await pm.goto(BASE + "/?room=" + room + "&view=main");
  DBG = [p1, p2];
  const errors = [];
  for (const [label, p] of [["p1", p1], ["p2", p2]]) p.on("pageerror", (e) => errors.push(label + " pageerror: " + e.message));
  await p1.goto(roomUrl); await p2.goto(roomUrl);
  await waitFor(() => countSel(p1, ".splash").then((n) => n > 0), { label: "seat picker" });
  await clickSel(p1, '[data-action="join-team"]');
  await waitFor(async () => (await bodyText(p1)).includes(COURIER_NAME.king), { label: "p1 team" });
  await clickSel(p2, '[data-action="join-team"]');
  await waitFor(async () => (await bodyText(p2)).includes(COURIER_NAME.hunter), { label: "p2 team" });
  await pressSpace(p1); await pressSpace(p2);
  await waitFor(async () => (await bodyText(p1)).includes("회전 벨트") && (await bodyText(p2)).includes("회전 벨트"), { label: "전반 elevator", timeout: 60000 });
  for (let round = 1; round <= 7; round++) {
    await pressSpace(p1); await pressSpace(p2);
    await passPriority(p1, p2, '[data-action="vote-up"]');
    await waitFor(async () => (await countSel(p1, '[data-action="vote-up"]')) > 0, { label: `round ${round} voting`, timeout: 8000 });
    await clickSel(p1, '[data-action="vote-up"]'); await clickSel(p2, '[data-action="vote-up"]');
    await waitFor(async () => (await bodyText(p1)).includes(`라운드 ${round} 결과`), { label: `round ${round} 결과`, timeout: 8000 });
  }
  await pressSpace(p1); await pressSpace(p2);
  await waitFor(async () => (await bodyText(p1)).includes("전반 종료"), { label: "halftime", timeout: 8000 });

  // ---- 하프타임: 엿보기 도전 버튼이 보이고, 게임 중 스페이스는 준비 완료로 새지 않는다 ----
  assert_((await countSel(p1, '[data-action="start-peek"]')) === 1 && (await countSel(p2, '[data-action="start-peek"]')) === 1, "하프타임에 엿보기 도전 버튼이 보여야 함");
  await clickSel(p1, '[data-action="start-peek"]');
  await waitFor(async () => (await countSel(p1, "#mg-layer .mg-kind-peek")) === 1, { label: "peek 게임 열림" });
  for (let i = 0; i < 60; i++) {
    if (!(await p1.$("#mg-layer .mg-kind-peek"))) break;
    await p1.keyboard.press("Space"); await p1.waitForTimeout(90);
  }
  await waitFor(async () => (await countSel(p1, "#mg-layer .mg-kind-peek")) === 0, { label: "peek 게임 종료" });
  await waitFor(async () => (await bodyText(p1)).includes("엿보기 1회 획득"), { label: "엿보기 1회 획득 표시 (테스트 모드는 실수 0)" });
  assert_(!(await bodyText(p1)).includes("나 · 빨강팀 · 준비 완료") && (await countSel(p1, ".ready-chip.is-ready")) === 0, "엿보기 게임 중 누른 스페이스가 준비 완료가 되면 안 됨");
  assert_((await countSel(p1, '[data-action="start-peek"]')) === 0, "한 번 했으면 재도전 버튼은 사라져야 함");
  if (process.env.SHOT) await p1.screenshot({ path: process.env.SHOT + "_half.png" });
  assert_((await bodyText(p2)).includes("도전 완료"), "상대 화면에는 도전 완료만 보임");
  log("하프타임: 엿보기 1회 획득, 재도전 불가, 스페이스 누수 없음");

  // ---- 후반: 2번이 칸 하나를 제작해서 주문표를 만든다 ----
  await pressSpace(p1); await pressSpace(p2);
  await waitFor(async () => (await bodyText(p1)).includes("초밥 제작"), { label: "후반 secure", timeout: 8000 });
  await clickSel(p2, '.rail-btn[data-action="open-type"][data-cat="0"]');
  await waitFor(async () => (await bodyText(pm)).includes("손질 중"), { label: "메인 모니터: 지금 만드는 중(손질)", timeout: 5000 });
  assert_((await bodyText(pm)).includes("일반 초밥 손질 중") || (await bodyText(pm)).includes("계란 초밥 손질 중"), "메인에 종류 + 손질 중이 보여야 함: " + (await bodyText(pm)).slice(0, 200));
  await p2.waitForTimeout(500); await passPrep(p2);
  await waitFor(async () => (await bodyText(pm)).includes("제작 중"), { label: "메인 모니터: 제작 중으로 바뀜", timeout: 3000 });
  await p2.evaluate(() => window.__mgFinish());
  await waitFor(async () => (await bodyText(pm)).includes("만든 초밥 1개"), { label: "메인 모니터: 만든 초밥 1개", timeout: 3000 });
  log("메인 모니터: 손질 중 -> 제작 중 -> 만든 초밥 1개");
  await waitFor(async () => (await bodyText(p1)).includes("회전 벨트"), { label: "후반 elevator", timeout: 60000 });

  // ---- 후반 벨트: 패널 / 엿보기 / 팝업 ----
  assert_((await bodyText(pm)).includes("자동 진행"), "메인 모니터에 게이트 자동 진행 카운트다운이 보여야 함");
  assert_((await countSel(p1, ".peek-panel")) === 1, "엿보기를 얻은 1번 화면에는 엿보기 패널이 있어야 함");
  assert_((await countSel(p2, ".peek-panel")) === 0, "엿보기를 안 한 2번 화면에는 패널이 없어야 함");
  await clickSel(p1, '[data-action="use-peek"]');
  await waitFor(async () => (await countSel(p1, "#peek-pop")) === 1, { label: "엿보기 팝업" });
  assert_((await countSel(p2, "#peek-pop")) === 0, "상대 화면에는 팝업이 뜨면 안 됨");
  await waitFor(async () => (await countSel(p1, ".peek-seen")) === 1, { label: "엿본 주문표 목록" });
  assert_((await bodyText(p1)).includes("남은 0회"), "남은 횟수 0회 (최대 1회를 씀)");
  if (process.env.SHOT) await p1.screenshot({ path: process.env.SHOT + "_elev.png" });
  log("후반 벨트: 엿보기 1회 사용 -> 팝업 + 목록 + 남은 0회 (상대 화면엔 없음)");

  // 도둑 배치 창에서 엿본 접시 표시
  await pressSpace(p1); await pressSpace(p2);
  await passPriority(p1, p2, ".thief-window");
  await waitFor(async () => (await countSel(p1, ".thief-window")) > 0, { label: "thief 창", timeout: 8000 });
  assert_((await countSel(p1, ".thief-floors .is-peeked")) === 1, "엿본 접시가 도둑 배치 버튼에 표시돼야 함");
  assert_((await countSel(p2, ".thief-floors .is-peeked")) === 0, "상대(2번)에게는 표시가 없어야 함");
  if (process.env.SHOT) await p1.screenshot({ path: process.env.SHOT + "_thief.png" });
  log("도둑 배치: 엿본 접시 1곳 표시");

  if (errors.length) throw new Error("page errors: " + errors.join(" | "));
  await browser.close();
  log("ALL CHECKS PASSED");
}
function assert_(c, m) { if (!c) throw new Error("ASSERT FAILED: " + m); }
main().catch(async (e) => {
  console.error("[test-peek-ui] FAILED:", e);
  if (DBG && process.env.DEBUG_DUMP) for (const p of DBG) console.error("---- 화면 ----\n" + (await bodyText(p).catch(() => "?")).slice(0, 600));
  process.exit(1);
});
