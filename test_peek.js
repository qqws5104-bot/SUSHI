// 2026-10-12: 엿보기 -- 하프타임 미니게임 결과(3/2/1회, 1인 1회), 후반 벨트에서 상대 미서빙 주문표 1장씩 엿보기
"use strict";
const assert = require("assert");
const { GameRoom, peekChargesFor } = require("./game-room.js");
const { ELEVATOR_ROUNDS } = require("./game-data.js");
function log(...a) { console.log("[test-peek]", ...a); }

assert.strictEqual(peekChargesFor(0), 2); assert.strictEqual(peekChargesFor(1), 2); assert.strictEqual(peekChargesFor(2), 1);
assert.strictEqual(peekChargesFor(3), 1); assert.strictEqual(peekChargesFor(9), 1); assert.strictEqual(peekChargesFor(NaN), 1);

const room = new GameRoom("TEST", () => {});
room.joinTeam("A"); room.joinTeam("B"); room.setReady("1"); room.setReady("2");
const st = room.state;
assert.deepStrictEqual(st.peek["1"], { charges: 0, played: false, used: 0, seen: [] });
// 전반엔 엿보기 결과도 사용도 불가
room.peekEarned("1", 0); assert.strictEqual(st.peek["1"].played, false, "하프타임이 아니면 무시");
// 전반: 칸 몇 개 제작 후 벨트 -> 하프타임
const take = (seat, id, sushi) => room.secureCell(seat, id, sushi);
room._endSecurePhase(); // 전반엔 제작 없이 넘긴다 (주문표가 없으면 우선 초밥 지정 창도 자동 통과)
assert.deepStrictEqual(room.usePeek("1"), { ok: false, code: "phase" }, "전반 벨트에서는 사용 불가");
const gate = () => { room.setElevatorReady("1"); room.setElevatorReady("2"); };
for (let r = 1; r <= ELEVATOR_ROUNDS; r++) { gate(); room._resolveRound(); }
gate();
assert.strictEqual(st.phase, "halftime");

// 하프타임: 1인 1회, 횟수 결정
room.peekEarned("1", 0);
assert.strictEqual(st.peek["1"].charges, 2, "최대 2회"); assert.strictEqual(st.peek["1"].played, true);
room.peekEarned("1", 5); assert.strictEqual(st.peek["1"].charges, 2, "재도전 불가");
room.peekEarned("2", 4); assert.strictEqual(st.peek["2"].charges, 1);
room.halftimeReady("1"); room.halftimeReady("2");
assert.strictEqual(st.half, 2); assert.strictEqual(st.peek["1"].charges, 2, "후반 시작해도 유지");

// 후반 제작: 1번은 3장, 2번은 1장
take("1", "normal-1", "egg"); take("1", "normal-2", "egg"); take("1", "normal-3", "egg");
take("2", "normal-4", "egg");
room._endSecurePhase();
assert.strictEqual(st.phase, "elevator");
const mine1 = st.players["1"].invoices.length, mine2 = st.players["2"].invoices.length;
assert.ok(mine1 >= 1 && mine2 >= 1, "주문표가 있어야 함: " + mine1 + "/" + mine2);

// 2번: 1회 -> 1번 주문표 중 하나, 이후 no_charge
let r = room.usePeek("2");
assert.ok(r.ok, "엿보기 성공"); assert.ok(st.players["1"].invoices.some((i) => i.id === r.invoiceId), "상대(1번) 주문표여야 함");
assert.strictEqual(st.peek["2"].charges, 0); assert.strictEqual(st.peek["2"].used, 1); assert.deepStrictEqual(st.peek["2"].seen, [r.invoiceId]);
assert.deepStrictEqual(room.usePeek("2"), { ok: false, code: "no_charge" });

// 1번: 상대(2번) 주문표 수만큼만 서로 다른 것을 볼 수 있고, 다 보면 nothing(횟수 소모 없음)
const seenIds = [];
for (let i = 0; i < mine2; i++) { const x = room.usePeek("1"); assert.ok(x.ok); assert.ok(!seenIds.includes(x.invoiceId), "중복 엿보기 없음"); seenIds.push(x.invoiceId); }
const before = st.peek["1"].charges;
if (before > 0) { assert.deepStrictEqual(room.usePeek("1"), { ok: false, code: "nothing" }); assert.strictEqual(st.peek["1"].charges, before, "nothing이면 횟수 안 줄어듦"); }
assert.ok(st.peek["1"].used === mine2);

// 서빙 끝난 주문표는 엿볼 수 없다
const room2 = new GameRoom("T2", () => {});
room2.joinTeam("A"); room2.joinTeam("B");
room2.state.phase = "elevator"; room2.state.half = 2;
room2.state.peek["1"].charges = 2;
room2.state.players["2"].invoices.push({ id: "x1", catIdx: 0, floorIdx: 0, sushi: "egg", acquiredSeq: 1, deliveredRound: 3, stolen: false, deliveredWasPriority: false });
assert.deepStrictEqual(room2.usePeek("1"), { ok: false, code: "nothing" }, "이미 서빙된 주문표는 제외");

// 다시 시작하면 초기화
st.phase = "end"; room.restartReady("1"); room.restartReady("2");
assert.deepStrictEqual(st.peek["1"], { charges: 0, played: false, used: 0, seen: [] });
log("OK: 2/1회 계산(최대 2회), 1인 1회, 후반 전용, 중복 없음, 서빙된 주문표 제외, 재시작 초기화");
process.exit(0);
