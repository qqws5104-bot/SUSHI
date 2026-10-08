const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const ctx = await b.newContext({ viewport: { width: 1280, height: 860 } }); const page = await ctx.newPage();
  await page.goto("file://" + __dirname + "/belt_proto.html?test=1&sound=0&mode=two&roundMs=1200&rounds=2&seed=4");
  await page.waitForTimeout(300);
  await page.keyboard.press("Space"); await page.waitForTimeout(1200);
  await page.screenshot({ path: "shots/countdown.png" });
  await page.waitForFunction(() => window.__belt.game.state.phase === "active");
  for (let i = 0; i < 3; i++) await page.keyboard.press("KeyD");
  await page.waitForFunction(() => window.__belt.game.state.phase === "result");
  await page.waitForTimeout(400);
  await page.screenshot({ path: "shots/result.png" });
  await page.keyboard.press("Space"); await page.waitForFunction(() => window.__belt.game.state.phase === "active");
  await page.waitForFunction(() => window.__belt.game.state.phase === "result"); await page.keyboard.press("Space");
  await page.waitForTimeout(400);
  await page.screenshot({ path: "shots/end.png" });
  await b.close();
})();
