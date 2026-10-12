// 2026-10-08 초밥 스킨: 제작하면 구체적인 초밥 종류(inv.sushi)가 주문표에 붙는다 -- GameRoom 직접 구동.
//   - 클라이언트가 보낸 키가 그 종류의 목록(TYPES[].sushi)에 있으면 그대로 붙는다
//   - 목록에 없는 키(다른 종류의 초밥, 이상한 값, 없음)는 서버가 그 종류 목록에서 무작위로 고른다
//   - 종류마다 목록은 서로 겹치지 않고, 모든 주문표는 항상 자기 종류의 초밥만 갖는다
"use strict";
const assert = require("assert");
const { GameRoom } = require("./game-room.js");
const { TYPES } = require("./game-data.js");
function log(...a) { console.log("[test-sushi]", ...a); }

const seen = new Set();
TYPES.forEach((t) => {
  assert(Array.isArray(t.sushi) && t.sushi.length === 2, t.key + "는 초밥이 2종");
  t.sushi.forEach((k) => { assert(!seen.has(k), "초밥 키 중복: " + k); seen.add(k); });
});
log("종류별 초밥 2종, 서로 겹치지 않음:", TYPES.map((t) => t.key + "=" + t.sushi.join("/")).join(" "));

const room = new GameRoom("TEST", () => {});
room.joinTeam("clientA"); room.joinTeam("clientB");
room.setReady("1"); room.setReady("2");
const inv = (seat) => room.state.players[seat].invoices;

room.secureCell("1", "normal-1", "tofu");
assert.strictEqual(inv("1")[0].sushi, "tofu", "유효한 키는 그대로");
room.secureCell("1", "fragile-1", "salmon");
assert.strictEqual(inv("1")[1].sushi, "salmon");
room.secureCell("1", "valuable-1", "egg"); // 다른 종류의 키 -> 무시하고 특선 목록에서 고른다
assert(TYPES[2].sushi.includes(inv("1")[2].sushi), "다른 종류의 키는 서버가 대체: " + inv("1")[2].sushi);
room.secureCell("1", "fixed-floor-1", "<script>"); // 이상한 값
assert(TYPES[3].sushi.includes(inv("1")[3].sushi));
room.secureCell("1", "normal-2"); // 키 없음
assert(TYPES[0].sushi.includes(inv("1")[4].sushi));
log("유효 키 유지 / 타 종류 키·이상한 값·없음은 서버가 목록에서 대체");

// 무작위 대체가 한쪽으로만 쏠리지 않는다 (200번 중 둘 다 나온다)
const got = new Set();
for (let i = 0; i < 200; i++) {
  const r = new GameRoom("T" + i, () => {});
  r.joinTeam("a"); r.joinTeam("b"); r.setReady("1"); r.setReady("2");
  r.secureCell("1", "fragile-1", null);
  got.add(r.state.players["1"].invoices[0].sushi);
}
assert.strictEqual(got.size, 2, "서버 무작위는 두 가지 모두 나온다: " + [...got]);
log("서버 무작위 대체: 두 종류 모두 나옴");
console.log("[test-sushi] ALL CHECKS PASSED");
process.exit(0); // GameRoom의 제작 타이머가 프로세스를 붙잡고 있다
