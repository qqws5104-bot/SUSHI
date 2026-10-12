// 2026-10-12: 손질 4종이 서로 다른 게임이고(휘젓기/칼질/굽기/뼈 발라내기), 실제 조작으로 끝낼 수 있는지 + 시작 전 설명 화면.
process.env.PORT = "3102";
require("./server.js");
const { chromium } = require("playwright");
const assert = require("assert");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const page = await (await br.newContext({ viewport: { width: 900, height: 800 } })).newPage();
  const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.goto("http://localhost:3102/?room=ZZZZ"); await sleep(500);
  const start = (sushi, pieces, extra) => page.evaluate(([s, p, x]) => {
    document.body.insertAdjacentHTML("beforeend", '<div id="tmg" style="position:fixed;inset:0;background:#fff;z-index:99"></div>');
    window.__res = null; window.__ctl = MiniGames.start(document.getElementById("tmg"), Object.assign({ kind: "prep", sushi: s, pieces: p, onDone: (r) => { window.__res = r; } }, x));
  }, [sushi, pieces, extra || {}]);
  const stop = () => page.evaluate(() => { window.__ctl && window.__ctl.destroy(); const e = document.getElementById("tmg"); e && e.remove(); });
  const done = async (ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (await page.evaluate(() => window.__res)) return await page.evaluate(() => window.__res); await sleep(50); } return null; };
  const sel = (q) => page.$(q);

  // 설명 화면: 첫 만남에는 3줄(목표/조작/주의)이 뜨고 게임은 아직 시작 전, SPACE로 시작
  for (const [s, n, name] of [["egg", 2, "휘젓기"], ["whitefish", 3, "칼질"], ["eel", 4, "굽기"], ["salmon", 3, "뼈 발라내기"]]) {
    await start(s, n, { intro: true }); await sleep(150);
    assert(await sel(".mg-intro"), s + ": 설명 화면");
    assert.strictEqual(await page.$$eval(".mg-intro li", (l) => l.length), 3, s + ": 설명은 3줄");
    assert((await page.textContent(".mg-name")).includes(name), s + ": 제목에 " + name);
    assert(!(await sel(".tm-wrap")), s + ": 설명 중에는 게임 시작 전");
    await page.keyboard.press("Space"); await sleep(150);
    assert(!(await sel(".mg-intro")) && (await sel(".tm-wrap")), s + ": SPACE로 시작");
    await stop();
  }
  // 자동 시작(4초)
  await start("egg", 2, { intro: true }); await sleep(4400);
  assert(await sel(".tm-wrap"), "4초 뒤 자동 시작"); await stop();

  // 서로 다른 게임인지 (구조 비교)
  const sig = {};
  for (const [s, n] of [["egg", 2], ["whitefish", 3], ["eel", 4], ["salmon", 3]]) { await start(s, n); await sleep(200); sig[s] = await page.evaluate(() => document.querySelector(".tm-wrap").className); await stop(); }
  assert.strictEqual(new Set(Object.values(sig)).size, 4, "손질 4종의 화면 구조가 모두 달라야 함: " + JSON.stringify(sig));

  // 실제 조작으로 끝내기
  await start("egg", 2); await sleep(200);
  for (let i = 0; i < 60 && !(await page.evaluate(() => window.__res)); i++) { await page.keyboard.press("Space"); await sleep(70); }
  let r = await done(2000); assert(r && r.ok, "휘젓기: 연타로 완료"); console.log("[prep] 휘젓기", r.ms + "ms"); await stop();

  await start("eel", 4); await sleep(200);
  await page.keyboard.down("Space"); await sleep(1300); await page.keyboard.up("Space"); await sleep(900);
  await page.keyboard.down("Space"); await sleep(400); await page.keyboard.up("Space");
  // 누르고/떼며 초록 구간 유지 -- 사람처럼 짧게 눌렀다 뗐다
  for (let i = 0; i < 80 && !(await page.evaluate(() => window.__res)); i++) { await page.keyboard.down("Space"); await sleep(90); await page.keyboard.up("Space"); await sleep(70); }
  r = await done(15000); assert(r && r.ok, "굽기: 온도 유지로 완료"); console.log("[prep] 굽기", r.ms + "ms, 실수", r.mistakes); await stop();

  await start("salmon", 3); await sleep(300);
  for (let i = 0; i < 40 && !(await page.evaluate(() => window.__res)); i++) {
    const lane = await page.evaluate(() => { const e = document.querySelector(".pr-lane.is-on"); return e ? e.getAttribute("data-lane") : null; });
    if (lane) await page.keyboard.press({ left: "ArrowLeft", up: "ArrowUp", right: "ArrowRight" }[lane]);
    await sleep(160);
  }
  r = await done(3000); assert(r && r.ok && r.mistakes === 0, "뼈 발라내기: 맞는 방향키로 완료"); console.log("[prep] 뼈 발라내기", r.ms + "ms"); await stop();

  await start("whitefish", 3, { testHooks: true }); await sleep(200);
  for (let i = 0; i < 12 && !(await page.evaluate(() => window.__res)); i++) { await page.keyboard.press("Space"); await sleep(90); }
  r = await done(2000); assert(r && r.ok, "칼질(테스트 모드)"); await stop();

  // 테스트 모드: 설명 없이 바로 시작 + SPACE만으로 4종 모두 통과
  for (const [s, n] of [["egg", 2], ["eel", 4], ["salmon", 3]]) {
    await start(s, n, { testHooks: true, intro: true }); await sleep(200);
    assert(!(await sel(".mg-intro")), "테스트 모드는 설명 생략");
    for (let i = 0; i < 20 && !(await page.evaluate(() => window.__res)); i++) { await page.keyboard.press("Space"); await sleep(120); }
    r = await done(2000); assert(r && r.ok, s + ": 테스트 모드 SPACE로 통과"); await stop();
  }

  // 엿보기 = 손님 응대: 손님이 원하는 것을 실제로 눌러서 끝내기 (실수 0) / 틀린 키는 실수
  await page.evaluate(() => { document.body.insertAdjacentHTML("beforeend", '<div id="tmg" style="position:fixed;inset:0;background:#fff;z-index:99"></div>'); window.__res = null; window.__ctl = MiniGames.start(document.getElementById("tmg"), { kind: "peek", intro: true, onDone: (r) => { window.__res = r; } }); });
  await sleep(150); assert(await sel(".mg-intro"), "손님 응대 설명 화면"); assert((await page.textContent(".mg-name")).includes("손님 응대"));
  await page.keyboard.press("Space"); await sleep(500);
  const KEYOF = ["ArrowLeft", "ArrowUp", "ArrowDown", "ArrowRight"];
  let served = 0;
  for (let i = 0; i < 200 && !(await page.evaluate(() => window.__res)); i++) {
    const wants = await page.$$eval(".ps-want:not(.is-got)", (l) => l.map((e) => parseInt(e.getAttribute("data-i"), 10)));
    if (wants.length) { await page.keyboard.press(KEYOF[wants[0]]); served++; }
    await sleep(120);
  }
  r = await done(3000); assert(r && r.ok && r.mistakes === 0 && r.kind === "peek", "손님 응대: 원하는 것을 가져다주면 실수 0으로 완료 " + JSON.stringify(r));
  console.log("[peek] 손님 응대", r.ms + "ms"); await stop();
  await page.evaluate(() => { document.body.insertAdjacentHTML("beforeend", '<div id="tmg" style="position:fixed;inset:0;background:#fff;z-index:99"></div>'); window.__res = null; window.__ctl = MiniGames.start(document.getElementById("tmg"), { kind: "peek", onDone: (r) => { window.__res = r; } }); });
  await sleep(600);
  const w0 = await page.$$eval(".ps-want", (l) => l.map((e) => parseInt(e.getAttribute("data-i"), 10)));
  const wrong = [0, 1, 2, 3].find((k) => !w0.includes(k));
  await page.keyboard.press(KEYOF[wrong]); await sleep(100);
  assert((await page.textContent(".mg-miss")).includes("1"), "틀린 것을 주면 실수 1");
  await stop();
  assert.deepStrictEqual(errs, []);
  console.log("[test-prep-variants] ALL CHECKS PASSED"); await br.close(); process.exit(0);
})().catch((e) => { console.error("[test-prep-variants] FAILED", e); process.exit(1); });
