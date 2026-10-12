// 2026-10-12 메뉴판: 종류마다 초밥이 하나씩 -- 계란 +1,000/-500 / 흰살생선 +2,000/-1,000 / 연어(지정) +1,500/-1,000 / 장어 +3,000/-1,500. GameRoom 직접 구동.
//   - 제작하면 그 종류의 초밥(inv.sushi)이 주문표에 붙는다
//   - 클라이언트가 보낸 키가 그 종류 것이 아니거나 이상한 값/없음이면 서버가 그 종류의 초밥으로 바로잡는다
//   - 종류끼리 초밥은 겹치지 않는다
"use strict";
const assert = require("assert");
const { GameRoom } = require("./game-room.js");
const { TYPES } = require("./game-data.js");
function log(...a) { console.log("[test-sushi]", ...a); }

const seen = new Set();
TYPES.forEach((t) => {
  assert(Array.isArray(t.sushi) && t.sushi.length === 1, t.key + "는 초밥이 1종");
  t.sushi.forEach((k) => { assert(!seen.has(k), "초밥 키 중복: " + k); seen.add(k); });
});
const MENU = { normal: ["계란", "egg", 1000, 500], fragile: ["흰살생선", "whitefish", 2000, 1000], "fixed-floor": ["연어", "salmon", 1500, 1000], valuable: ["장어", "eel", 3000, 1500] };
TYPES.forEach((t) => {
  const [nm, sushi, reward, penalty] = MENU[t.key];
  assert(t.name === nm + " 초밥", t.key + " 이름은 " + nm + " 초밥, got " + t.name);
  assert(t.reward === reward && t.penalty === penalty, t.key + " 점수는 +" + reward + " / -" + penalty + ", got +" + t.reward + " / -" + t.penalty);
  assert(t.sushi[0] === sushi, t.key + "의 초밥은 " + sushi + ", got " + t.sushi[0]);
});
log("종류별 초밥 1종(계란/흰살생선/연어/장어), 점수표(+판매/-원재료값):", TYPES.map((t) => t.key + "=" + t.sushi[0] + "/" + t.reward).join(" "));

const room = new GameRoom("TEST", () => {});
room.joinTeam("clientA"); room.joinTeam("clientB");
room.setReady("1"); room.setReady("2");
const inv = (seat) => room.state.players[seat].invoices;

room.secureCell("1", "normal-1", "egg");
assert.strictEqual(inv("1")[0].sushi, "egg", "유효한 키는 그대로");
room.secureCell("1", "fragile-1", "salmon"); // 다른 종류의 키 -> 흰살생선으로 바로잡는다
assert.strictEqual(inv("1")[1].sushi, "whitefish");
room.secureCell("1", "valuable-1", "egg");
assert.strictEqual(inv("1")[2].sushi, "eel", "다른 종류의 키는 서버가 대체: " + inv("1")[2].sushi);
room.secureCell("1", "fixed-floor-1", "<script>"); // 이상한 값
assert.strictEqual(inv("1")[3].sushi, "salmon");
room.secureCell("1", "normal-2"); // 키 없음
assert.strictEqual(inv("1")[4].sushi, "egg");
log("유효 키 유지 / 타 종류 키·이상한 값·없음은 서버가 그 종류의 초밥으로 대체");

console.log("[test-sushi] ALL CHECKS PASSED");
process.exit(0);
