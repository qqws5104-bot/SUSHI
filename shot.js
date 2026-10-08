// 스크린샷 도우미: node shot.js [outDir]
const { chromium } = require("playwright");
const out = process.argv[2] || "shots";
require("fs").mkdirSync(out, { recursive: true });
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  for (const [name, w, h] of [["desk", 1280, 860], ["phone", 390, 820]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h } }); const page = await ctx.newPage();
    const errs = []; page.on("pageerror", (e) => errs.push(e.message)); page.on("console", (m) => { if (m.type() === "error" && !/fonts\.g|ERR_|Failed to load/.test(m.text())) errs.push(m.text()); });
    await page.goto("file://" + __dirname + "/belt_proto.html?test=1&seed=7&sound=0&roundMs=60000");
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${out}/${name}_idle.png` });
    await page.keyboard.press("Space"); await page.waitForTimeout(2600);
    for (let i = 0; i < 4; i++) { await page.keyboard.press("ArrowRight"); await page.waitForTimeout(30); }
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${name}_play.png` });
    console.log(name, errs);
    await ctx.close();
  }
  await b.close();
})();
