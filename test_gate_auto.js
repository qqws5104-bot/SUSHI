// 2026-10-12: 벨트 게이트(idle/result)는 한쪽이 스페이스를 안 눌러도 GATE_AUTO_MS 뒤 자동으로 넘어간다 (평가 G3: 5초 이상 멈춤 금지)
"use strict";
process.env.GATE_AUTO_MS = "300";
const assert = require("assert");
const { GameRoom } = require("./game-room.js");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const room = new GameRoom("TEST", () => {});
  room.joinTeam("A"); room.joinTeam("B"); room.setReady("1"); room.setReady("2");
  room._endSecurePhase();
  const el = room.state.elevator;
  assert.strictEqual(el.state, "idle"); assert.ok(el.gateEndsAt > Date.now(), "자동 진행 시각이 상태에 있어야 함(화면 카운트다운용)");
  room.setElevatorReady("1"); // 한 명만 누름
  assert.strictEqual(el.state, "idle");
  await sleep(450);
  assert.strictEqual(el.state, "voting", "idle 게이트: 한 명만 눌러도 자동으로 라운드 시작 (주문표가 없어 우선 지정 창은 건너뜀)");
  room._resolveRound();
  assert.strictEqual(el.state, "result"); assert.ok(el.gateEndsAt > Date.now());
  await sleep(450);
  assert.strictEqual(el.state, "voting"); assert.strictEqual(el.round, 2, "result 게이트: 아무도 안 눌러도 다음 라운드");
  // 수동으로 먼저 넘기면 낡은 타이머가 다음 게이트를 건드리지 않는다
  room._resolveRound(); room.setElevatorReady("1"); room.setElevatorReady("2");
  assert.strictEqual(el.round, 3); assert.strictEqual(el.state, "voting"); assert.strictEqual(el.gateEndsAt, null);
  await sleep(450);
  assert.strictEqual(el.round, 3, "수동으로 넘긴 뒤 낡은 타이머가 라운드를 더 밀면 안 됨");
  // 마지막 라운드 결과 게이트도 자동으로 하프를 끝낸다
  for (let r = el.round; r < 7; r++) { room._resolveRound(); room.setElevatorReady("1"); room.setElevatorReady("2"); }
  room._resolveRound(); assert.strictEqual(el.round, 7);
  await sleep(450);
  assert.strictEqual(room.state.phase, "halftime", "마지막 result 게이트 자동 진행 -> 하프타임");
  console.log("[test-gate-auto] OK");
})().catch((e) => { console.error(e); process.exit(1); });
