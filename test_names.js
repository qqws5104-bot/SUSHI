// 2026-10-12: 팀 이름 -- 입장 전 입력 → 입장 시 서버 저장, 대기실에서 수정, 중복/긴 이름/태그 정리, 한글 입력 중 렌더에 포커스·값 유지,
// 이름 입력 중 스페이스가 준비로 먹히지 않음, 메인 모니터·시작 화면 간판에 이름 표시, 기본 이름 폴백.
process.env.PORT = "3103"; process.env.TEST_HOOKS = "1";
require("./server.js");
const { chromium } = require("playwright"); const http = require("http");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const assert = require("assert");
(async () => {
  const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const room = await new Promise((res, rej) => http.get("http://localhost:3103/", (r) => res(new URL(r.headers.location, "http://localhost:3103").searchParams.get("room"))).on("error", rej));
  const mk = async () => (await br.newContext()).newPage();
  const p1 = await mk(), p2 = await mk(), main = await mk();
  const url = "http://localhost:3103/?room=" + room;
  await p1.goto(url); await p2.goto(url); await main.goto(url + "&view=main"); await sleep(700);
  const body = (p) => p.evaluate(() => document.body.innerText);
  const st = () => global.__rooms.get(room).room.state;

  // 1) 입장 전: 입력칸 + 기본 이름 placeholder, 간판 기본 이름
  assert((await p1.getAttribute("#name-join", "placeholder")).includes("빨강팀"), "기본 이름 placeholder");
  assert.strictEqual(await p1.getAttribute("#name-join", "maxlength"), "8");
  assert((await p1.evaluate(() => document.querySelector(".sa-king .sa-sign").textContent)).includes("빨강팀"), "간판 기본 이름");

  // 2) 입력 중 상대가 입장해 state가 바뀌어도(=렌더) 값·포커스 유지
  await p1.click("#name-join"); await p1.keyboard.type("라면 장인");
  await p2.fill("#name-join", "빨강팀"); // 이건 p2의 입력칸 (아직 입장 전)
  await p2.click('[data-action="join-team"]'); await sleep(400); // p2가 좌석 1을 먼저 가져감 (이름 = 기본과 같은 "빨강팀")
  assert.strictEqual(await p1.inputValue("#name-join"), "라면 장인", "렌더 후에도 입력값 유지");
  assert(await p1.evaluate(() => document.activeElement && document.activeElement.id === "name-join"), "렌더 후에도 포커스 유지");
  // 입력칸에서 Space/방향키가 게임 조작으로 먹히지 않음 (스페이스 = 이름 속 공백)
  assert.strictEqual(st().ready["1"], false);

  // 3) p1 입장(Enter) → 좌석 2, 이름 저장
  await p1.keyboard.press("Enter"); await sleep(500);
  assert.strictEqual(st().seatOwners["2"] !== null, true);
  assert.strictEqual(st().names["2"], "라면 장인", "입장 시 이름 저장");
  assert.strictEqual(st().names["1"], "빨강팀", "p2가 직접 입력한 이름");
  assert((await body(main)).includes("라면 장인"), "메인 모니터에 이름");
  assert((await body(p2)).includes("라면 장인"), "상대 화면에 이름");

  // 4) 대기실에서 수정: 같은 이름 거부(토스트), 긴 이름 8자 컷, 태그 제거
  await p1.fill("#name-lobby", "빨강팀"); await p1.evaluate(() => document.getElementById("name-lobby").blur()); await sleep(400);
  assert.strictEqual(st().names["2"], "라면 장인", "상대와 같은 이름은 거부");
  assert((await body(p1)).includes("같은 이름"), "거부 토스트");
  await p1.fill("#name-lobby", "<b>가나다라마바사아자차</b>"); await p1.evaluate(() => document.getElementById("name-lobby").blur()); await sleep(400);
  assert.strictEqual(st().names["2"], "b가나다라마", "입력칸 8자 제한 + 태그 문자 제거");
  assert.strictEqual(global.__rooms.get(room).room.setName("2", "<b>가나다라마바사아자차</b>").name, "b가나다라마바사", "서버도 8자로 자름");
  await p1.fill("#name-lobby", ""); await p1.evaluate(() => document.getElementById("name-lobby").blur()); await sleep(400);
  assert.strictEqual(st().names["2"], "", "비우면 기본 이름");
  assert((await body(p2)).includes("남색팀"), "비우면 남색팀 폴백");
  await p1.fill("#name-lobby", "남색 고래"); await p1.evaluate(() => document.getElementById("name-lobby").blur()); await sleep(400);
  assert.strictEqual(st().names["2"], "남색 고래");

  // 5) 입력 중 Space로 준비되지 않는다 / 입력칸 밖 Space는 준비
  await p1.click("#name-lobby"); await p1.keyboard.press("Space"); await sleep(300);
  assert.strictEqual(st().ready["2"], false, "입력 중 스페이스는 준비가 아님");
  await p1.evaluate(() => document.activeElement.blur());
  await p1.keyboard.press("Space"); await sleep(300);
  assert.strictEqual(st().ready["2"], true, "입력칸 밖 스페이스는 준비");

  // 6) 게임 시작 후엔 이름 변경 불가
  const gr = global.__rooms.get(room).room;
  await p2.keyboard.press("Space"); await sleep(500);
  assert.strictEqual(st().phase, "secure");
  assert.strictEqual(gr.setName("1", "x").ok, false, "로비 아니면 거부");
  assert((await body(main)).includes("남색 고래"), "메인 모니터 라이브 카드에 이름");
  console.log("PASS test_names");
  await br.close(); process.exit(0);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
