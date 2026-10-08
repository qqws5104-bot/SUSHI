// 종료 시각 흔들림 기본값(±1초)으로 실제 한 판이 끝까지 가는지 + 시계가 가장 이른 종료까지만 세는지.
"use strict";
const { chromium } = require("playwright");
const URL = "file://" + require("path").join(__dirname, "belt_proto.html");
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const page = await (await b.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
  const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.goto(URL + "?test=1&sound=0&mode=two&roundMs=2000&rounds=2&seed=9&jitter=1");
  await page.waitForFunction(() => window.__belt);
  await page.keyboard.press("Space");
  await page.waitForFunction(() => window.__belt.game.state.phase === "active");
  const info = await page.evaluate(() => { const s = window.__belt.game.state; return { dur: s.endAt - s.roundStart, early: s.earliestEnd - s.roundStart }; });
  if (info.early !== 1000 || info.dur < 1000 || info.dur > 3000) throw new Error("jitter window wrong " + JSON.stringify(info));
  // 가장 이른 종료 이후에도 끝나지 않았다면 시계는 '!'
  await page.waitForTimeout(Math.max(0, info.early - 100));
  const before = await page.textContent("#clock");
  await page.waitForTimeout(200);
  const phase = await page.evaluate(() => window.__belt.game.state.phase);
  const after = await page.textContent("#clock");
  if (phase === "active" && after !== "!") throw new Error("가장 이른 종료 이후 시계는 '!'여야 함: " + after);
  await page.waitForFunction(() => window.__belt.game.state.phase === "result", null, { timeout: 5000 });
  await page.keyboard.press("Space");
  await page.waitForFunction(() => window.__belt.game.state.phase === "active");
  await page.waitForFunction(() => window.__belt.game.state.phase === "result", null, { timeout: 5000 });
  await page.keyboard.press("Space");
  await page.waitForFunction(() => window.__belt.game.state.phase === "end");
  if (errs.length) throw new Error(errs.join("|"));
  console.log(`[test-ui-jitter] OK: 종료 시각 ${info.dur}ms(허용 1000~3000), 시계 '${before}' -> '${after}', 2라운드 완주`);
  await b.close();
})().catch((e) => { console.error("[test-ui-jitter] FAILED:", e); process.exit(1); });
