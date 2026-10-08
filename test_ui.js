// belt_proto.html 화면 테스트 (Playwright). node test_ui.js   (먼저 python3 build.py)
"use strict";
const { chromium } = require("playwright");
const path = require("path");
const URL = "file://" + path.join(__dirname, "belt_proto.html");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let n = 0;
function ok(c, m) { if (!c) throw new Error("ASSERT FAILED: " + m); n++; }
function log(...a) { console.log("[test-ui]", ...a); }

async function open(browser, qs) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } }), page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/fonts\.g|ERR_|Failed to load/.test(m.text())) errs.push(m.text()); });
  await page.goto(URL + "?test=1&sound=0&jitter=0&" + (/plates=/.test(qs) ? "" : "plates=sushi&") + qs);
  await page.waitForFunction(() => window.__belt);
  return { ctx, page, errs };
}
const st = (page) => page.evaluate(() => { const s = window.__belt.game.state; return { phase: s.phase, ui: window.__belt.ui.phase, round: s.round, off: s.off, pushes: s.pushes.slice(), budget: s.budget.slice(), targets: s.targets.slice(), scores: s.scores.slice(), hist: s.history.length }; });
const waitPlay = (page) => page.waitForFunction(() => window.__belt.game.state.phase === "active", null, { timeout: 6000 });
const waitResult = (page) => page.waitForFunction(() => window.__belt.game.state.phase === "result", null, { timeout: 8000 });
const text = (page, sel) => page.evaluate((s) => (document.querySelector(s) || {}).textContent || "", sel);

(async () => {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });

  // ---- 1. 둘이서 모드: 키 매핑, 연타 금지, 예산, 결정적 성공 ----
  {
    const { ctx, page, errs } = await open(browser, "mode=two&roundMs=1200&rounds=3&seed=3");
    ok((await text(page, "#holeBtn")).includes("시작"), "시작 버튼");
    ok(/라운드 1 \/ 3/.test(await text(page, "#round")), "라운드 표시");
    await page.keyboard.press("Space");
    ok((await st(page)).ui === "cd", "Space -> 카운트다운");
    const t = (await st(page)).targets;
    ok(t[0] != null && t[1] != null, "카운트다운 중 주문이 미리 보인다");
    ok(await page.evaluate(() => { const g = window.__belt.game, c = (k) => g.cfg.plates.filter((p) => p.kind === k).length; return document.querySelectorAll(".plate.t0").length === c(g.state.targets[0]) && document.querySelectorAll(".plate.t1").length === c(g.state.targets[1]); }), "두 사람 주문 표시: 같은 맛 접시마다 깃발(둘이서 모드는 공개)");
    await page.keyboard.press("KeyD");
    ok((await st(page)).off === 0, "카운트다운 중 밀기는 무시");
    await waitPlay(page);
    let s = await st(page);
    ok(s.round === 1 && s.ui === "play", "라운드 시작");
    await page.keyboard.press("KeyD"); await page.keyboard.press("ArrowLeft");
    s = await st(page);
    ok(s.pushes[0] === 1 && s.pushes[1] === 1 && s.off === 0, "D=시계(+1, 1P), ←=반시계(-1, 2P): net 0 " + JSON.stringify(s));
    ok(s.budget[0] === 47 && s.budget[1] === 47, "예산 감소(기본 48)");
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyD", key: "d", repeat: true, bubbles: true })));
    ok((await st(page)).pushes[0] === 1, "꾹 누르기(repeat)는 무시");
    // 1P가 자기 주문을 앞으로 가져오고, 2P는 가만히 -> 1P 성공
    const need = await page.evaluate(() => { const g = window.__belt.game; return g.stepsToSeat(g.state.targets[0], 0); });
    for (let i = 0; i < Math.abs(need); i++) await page.keyboard.press(need > 0 ? "KeyD" : "KeyA");
    ok((await st(page)).pushes[0] >= 1, "민 기록");
    await waitResult(page);
    s = await st(page);
    const h = await page.evaluate(() => window.__belt.game.state.history[0]);
    ok(h.success[0] === true, "1P 주문 성공 " + JSON.stringify(h));
    ok(s.scores[0] === h.points[0] && h.points[0] > 0, "점수 반영");
    ok((await text(page, "#ov")).includes("라운드 1 결과"), "결과 카드");
    await page.keyboard.press("KeyD");
    ok((await st(page)).off === h.off, "결과 화면에서는 밀기 무시");
    await page.keyboard.press("Space");                         // 다음 라운드
    ok((await text(page, "#ov")) === "", "결과 카드 닫힘");
    await waitPlay(page);
    ok((await st(page)).round === 2, "2라운드 시작");
    await waitResult(page); await page.keyboard.press("Space");
    await waitPlay(page); await waitResult(page);
    ok((await text(page, "#nextBtn")).includes("결과 보기"), "마지막 라운드는 '결과 보기'");
    await page.keyboard.press("Space");
    ok((await st(page)).phase === "end", "7라운드(여기선 3) 후 종료");
    const end = await text(page, "#ov");
    ok(/둘 다 먹은 라운드/.test(end) && /밀기 사용/.test(end) && end.includes("한 판 더"), "최종 카드: 통계와 다시 하기");
    ok((await page.$$("#ov table tr")).length === 4, "라운드 표(헤더+3)");
    await page.keyboard.press("KeyR");
    s = await st(page);
    ok(s.round === 0 && s.phase === "idle" && s.scores[0] === 0, "R로 새 게임");
    ok(errs.length === 0, "페이지 에러 없음: " + errs.join("|"));
    log("둘이서 모드: 키 매핑 / 카운트다운 / 예산 / 꾹 누르기 금지 / 점수 / 3라운드 종료 / 통계 카드 / R 재시작");
    await ctx.close();
  }

  // ---- 2. 컴퓨터 모드: 상대 주문 숨김, 봇이 민다, 방향키·A/D 모두 내 키 ----
  {
    const { ctx, page, errs } = await open(browser, "mode=bot&roundMs=2500&rounds=2&seed=11&botRate=6");
    await page.keyboard.press("Space"); await waitPlay(page);
    ok(await page.evaluate(() => { const g = window.__belt.game; return document.querySelectorAll(".plate.t1").length === 0 && document.querySelectorAll(".plate.t0").length === g.cfg.plates.filter((p) => p.kind === g.state.targets[0]).length; }), "봇 주문은 접시에 표시되지 않음, 내 주문은 같은 맛 접시마다 깃발");
    ok((await text(page, "#order1")).includes("?"), "봇 주문 패널은 ?");
    ok(!(await text(page, "#order0")).includes("?"), "내 주문은 보임");
    let s = await st(page);
    await page.keyboard.press("ArrowRight"); await page.keyboard.press("KeyA");
    s = await st(page);
    ok(s.pushes[0] === 2, "← →, A D 모두 내 자리(0)");
    // 내가 가만히 있어도 봇이 자기 주문을 향해 민다 (이미 앞에 있지 않다면)
    await sleep(900);
    s = await st(page);
    const botNeeded = await page.evaluate(() => { const g = window.__belt.game; return g.stepsToSeat(g.state.targets[1], 1); });
    ok(s.pushes[1] > 0 || botNeeded === 0, "봇이 움직인다: " + JSON.stringify(s));
    await waitResult(page);
    const r = await text(page, "#ov");
    ok(r.includes("주문") && /컴퓨터|봇/.test(r), "결과 카드에서는 봇 주문도 공개");
    ok(errs.length === 0, "페이지 에러 없음: " + errs.join("|"));
    log("컴퓨터 모드: 봇 주문 숨김 / 내 키(방향키·A D) / 봇이 밀어 옴 / 결과에서 공개");
    await ctx.close();
  }

  // ---- 2b. 기본값은 한 칸 공유 ----
  {
    const { ctx, page, errs } = await open(browser, "mode=two&seed=3");
    ok(await page.evaluate(() => window.__belt.game.cfg.seatRule === "any"), "기본 규칙 = 한 칸 공유");
    ok((await page.$$(".seatf")).length === 1, "기본: 먹는 칸 하나");
    ok((await text(page, "#front0")) === (await text(page, "#front1")), "두 패널이 같은 접시를 가리킴");
    ok(errs.length === 0, "페이지 에러 없음");
    log("기본값: 한 칸 공유");
    await ctx.close();
  }

  // ---- 2c. 색 모드(기본): 10색, 주문 종류, 먹는 칸이 6시 ----
  {
    const { ctx, page, errs } = await open(browser, "plates=color&mode=two&roundMs=1500&rounds=2&seed=11");
    ok((await page.$$(".plate")).length === 10, "접시 10장");
    ok(await page.evaluate(() => window.__belt.game.cfg.pointsBy === "order"), "색 모드: 점수는 주문 종류");
    const pos = await page.evaluate(() => { const b = document.querySelector(".belt").getBoundingClientRect(), f = document.querySelector(".seatf").getBoundingClientRect(); return [f.left + f.width / 2 - (b.left + b.width / 2), f.top + f.height / 2 - (b.top + b.height / 2)]; });
    ok(Math.abs(pos[0]) < 3 && pos[1] > 100, "공유 칸이 정확히 6시 방향 " + pos);
    const names = await page.evaluate(() => [...document.querySelectorAll(".pl-name")].map((e) => e.textContent.split("·")[0]).sort().join());
    ok(names === ["검정", "노랑", "보라", "분홍", "빨강", "주황", "초록", "파랑", "회색", "흰색"].sort().join(), "색 이름 10가지 모두 표시: " + names);
    ok(await page.evaluate(() => [...document.querySelectorAll(".pl-name")].every((e) => /·(물방울|줄무늬|별|하트|체크)$/.test(e.textContent))), "접시 이름표에 무늬도 표시");
    await page.keyboard.press("Space");
    ok(await page.evaluate(() => { const g = window.__belt.game, s = g.state; return [0, 1].every((i) => document.querySelectorAll(".plate.t" + i).length === s.orders[i].plates.length); }), "주문이 받아 주는 접시마다 깃발");
    const o0 = await text(page, "#order0");
    ok(/초밥/.test(o0) && /접시에 올리기/.test(o0) && /(일반|지정|중급|특선)/.test(o0) && /\d+점/.test(o0), "주문표: 만들 초밥 + 올릴 접시 + 종류 + 점수: " + o0);
    ok(await page.evaluate(() => { const g = window.__belt.game, N = g.cfg.plates ? 0 : 0, o = g.state.orders[0], ks = Object.keys(BeltCore.ORDER_TYPES); return BeltCore.ORDER_TYPES[o.type].sushis.indexOf(o.sushi) >= 0 && document.querySelector("#order0 .on").textContent === BeltCore.SUSHI_NAMES[o.sushi] + " 초밥"; }), "주문표의 초밥 이름이 그 급의 목록 안");
    await waitPlay(page);
    // 1P가 가장 가까운 허용 접시로 가져오고 2P는 가만히 -> 1P 성공, 점수 = 주문 종류 점수
    const need = await page.evaluate(() => window.__belt.game.stepsToOrder(0));
    for (let i = 0; i < Math.abs(need); i++) await page.keyboard.press(need > 0 ? "KeyD" : "KeyA");
    await waitResult(page);
    const h = await page.evaluate(() => window.__belt.game.state.history[0]);
    ok(h.success[0] === true && h.points[0] === h.orders[0].points, "1P 성공, 점수 = 주문 종류 점수 " + JSON.stringify(h.points));
    const ov = await text(page, "#ov");
    ok(ov.includes("라운드 1 결과") && /초밥 →/.test(ov), "결과 카드에 주문 문구(초밥 -> 접시)");
    ok(await page.evaluate(() => document.querySelectorAll(".pon .pi.p0.ok").length === 1), "결과: 먹는 칸 접시 위에 1P가 만든 초밥이 올라간다");
    await page.click("#nextBtn");
    ok(await page.evaluate(() => document.querySelectorAll(".pon").length === 0), "다음 라운드로 가면 접시 위 초밥이 치워진다");
    await page.evaluate(() => { document.querySelector("details.settings").open = true; });
    await page.selectOption("#sPlates", "sushi");
    ok((await page.$$(".plate")).length === 12, "맛 12칸으로 전환");
    await page.selectOption("#sPlates", "color");
    ok((await page.$$(".plate")).length === 10, "색 10칸으로 복귀");
    ok(errs.length === 0, "페이지 에러 없음: " + errs.join("|"));
    log("색 모드: 10색 / 무늬 / 주문 종류 / 6시 공유 칸 / 점수 / 전환");
    await ctx.close();
  }

  // ---- 3. 브레이크/자리 규칙 설정이 화면에 반영 ----
  {
    const { ctx, page, errs } = await open(browser, "mode=two&roundMs=2500&brake=cap&cap=2&seatRule=any&seed=5");
    ok((await page.$$(".seatf")).length === 1 && (await text(page, ".seatf")).includes("먹는 칸"), "any: 먹는 칸 하나");
    ok((await text(page, "#budgetLabel0")).includes("이동 범위"), "cap 라벨");
    await page.keyboard.press("Space"); await waitPlay(page);
    for (let i = 0; i < 4; i++) await page.keyboard.press("KeyD");
    let s = await st(page);
    ok(s.off === 2 && s.pushes[0] === 2, "cap=2: 3번째부터 거부 " + JSON.stringify(s));
    ok(/\+2/.test(await text(page, "#bn0")), "이동 범위 표시 +2");
    await page.evaluate(() => { document.querySelector("details.settings").open = true; });
    await page.selectOption("#sBrake", "free");
    ok((await st(page)).round === 0, "설정을 바꾸면 처음부터");
    ok((await text(page, "#bn0")).includes("∞"), "free 표시");
    await page.selectOption("#sRule", "fixed");
    ok((await page.$$(".seatf")).length === 2, "fixed: 자리 둘");
    ok(await page.evaluate(() => window.__belt.game.cfg.seats.join() === "0,6"), "fixed: 자리 [0,6]");
    ok((await text(page, "#frontLbl0")).includes("내 앞"), "fixed: 라벨");
    await page.selectOption("#sRule", "any");
    ok((await page.$$(".seatf")).length === 1 && (await text(page, "#frontLbl1")).includes("같이"), "any 복귀: 공유 라벨");
    ok(errs.length === 0, "페이지 에러 없음: " + errs.join("|"));
    log("설정: any/cap/free/fixed 전환이 화면과 규칙에 반영");
    await ctx.close();
  }

  // ---- 4. 레이아웃: 폰 폭에서 가로 스크롤 없음, 밀기 버튼이 보임 ----
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 820 } }), page = await ctx.newPage();
    await page.goto(URL + "?test=1&sound=0");
    await page.waitForFunction(() => window.__belt);
    const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    ok(sw.sw <= sw.cw, "폰 폭에서 가로 스크롤 없음 " + JSON.stringify(sw));
    await page.keyboard.press("Space"); await waitPlay(page);
    await page.click('#pad0 button[data-dir="1"]');
    ok((await st(page)).pushes[0] === 1, "화면 버튼으로도 밀 수 있다");
    log("폰 폭: 가로 스크롤 없음, 화면 버튼 동작");
    await ctx.close();
  }

  await browser.close();
  console.log(`[test-ui] ALL CHECKS PASSED (${n} assertions)`);
})().catch((e) => { console.error("[test-ui] FAILED:", e); process.exit(1); });
