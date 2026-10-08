// belt-core.js 규칙 테스트 (서버/브라우저 불필요). node test_core.js
"use strict";
const B = require("./belt-core.js");
let n = 0;
// 처음 만든 6칸 6종 규칙(맛이 전부 한 번씩) -- 원형 수학/브레이크/점수 같은 기본 규칙은 이 설정으로 검증한다.
const CLASSIC = { plates: B.PLATES6, seats: [0, 3], seatRule: "fixed", coopDeal: 0, budget: 36, cap: 3 };
const mk = (cfg) => B.create(Object.assign({ endJitter: 0 }, CLASSIC, cfg));   // 규칙 테스트는 종료 시각을 정확히 고정(jitter 0)
const FIXED12 = { seatRule: "fixed", seats: [0, 6] };                           // 각자 자리가 있는 12칸 8종 (옛 기본값)
const mk12 = (cfg) => B.create(Object.assign({ endJitter: 0 }, FIXED12, cfg));  // 12칸 8종 + 각자 자리
const mkShared = (cfg) => B.create(Object.assign({ endJitter: 0 }, cfg));       // 현재 기본값: 12칸 8종 + 한 칸 공유
function ok(c, m) { if (!c) throw new Error("ASSERT FAILED: " + m); n++; }
function eq(a, b, m) { ok(JSON.stringify(a) === JSON.stringify(b), `${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); }

// ---- 1. 접시 배치: 정반대 칸 쌍은 같은 가격대 ----
(() => {
  const P = B.PLATES6, N = P.length;
  for (let i = 0; i < N / 2; i++) eq(P[i].tier, P[i + N / 2].tier, `정반대 접시 쌍 ${i}-${i + N / 2} 가격대`);
  eq(new Set(P.map((p) => p.name)).size, N, "접시 이름 중복 없음");
})();

// ---- 2. 원형 수학 ----
(() => {
  const g = mk({ rng: B.mulberry32(5) });
  g.begin(0);
  for (let off = -13; off <= 13; off++) {
    g.state.off = off;
    for (let p = 0; p < g.N; p++) eq(g.plateAt(g.slotOf(p)), p, `plateAt(slotOf(${p})) off=${off}`);
  }
  g.state.off = 0;
  eq([0, 1, 2, 3, 4, 5].map((s) => g.plateAt(s)), [0, 1, 2, 3, 4, 5], "off=0이면 접시 p는 칸 p");
  g.state.off = 1;
  eq(g.plateAt(1), 0, "+1 밀면 접시 0이 칸 1(시계 방향)로");
  eq(g.slotOf(5), 0, "벨트는 끝이 없다: 접시 5가 칸 0으로 넘어간다");
  g.state.off = -1;
  eq(g.slotOf(0), 5, "-1 밀면 접시 0은 칸 5로 (벽 없이 반대편으로)");
})();

// ---- 3. stepsToSeat: 가까운 방향, 0이면 도착, 반대편은 +쪽 ----
(() => {
  const g = mk({ rng: B.mulberry32(5) });
  g.begin(0); g.state.off = 0;
  eq(g.stepsToSeat(0, 0), 0, "접시 0은 자리 0 앞");
  eq(g.stepsToSeat(1, 0), -1, "접시 1(칸1)을 자리 0으로: 반시계 1칸");
  eq(g.stepsToSeat(5, 0), 1, "접시 5(칸5)를 자리 0으로: 시계 1칸");
  eq(g.stepsToSeat(3, 0), 3, "정반대는 시계 3칸(동률이면 +)");
  eq(g.stepsToSeat(3, 1), 0, "자리 1은 칸 3");
  // 벨트를 실제로 그만큼 밀면 도착하는지 전수 확인
  for (let p = 0; p < g.N; p++) for (let seat = 0; seat < 2; seat++) {
    const g2 = mk({ rng: B.mulberry32(5), brake: "free" });
    g2.begin(0);
    const d = g2.stepsToSeat(p, seat);
    for (let i = 0; i < Math.abs(d); i++) ok(g2.push(0, d > 0 ? 1 : -1, 1).ok, "push");
    eq(g2.eatenBy(seat), p, `접시 ${p}를 자리 ${seat}로 ${d}칸 밀어서 도착`);
    eq(g2.stepsToSeat(p, seat), 0, "도착 후 steps 0");
  }
})();

// ---- 4. 브레이크: budget ----
(() => {
  const g = mk({ rng: B.mulberry32(2), brake: "budget", budget: 3 });
  eq(g.push(0, 1, 0).reason, "inactive", "라운드 시작 전 밀기 거부");
  g.begin(1000);
  ok(g.push(0, 1, 1100).ok && g.push(0, 1, 1200).ok && g.push(0, -1, 1300).ok, "예산 3번 사용 가능");
  eq(g.push(0, 1, 1400).reason, "no-budget", "예산 소진 후 거부");
  eq(g.state.budget, [0, 3], "예산은 사람별");
  ok(g.push(1, -1, 1500).ok, "상대 예산은 그대로");
  eq(g.push(1, 0, 1500).reason, "bad-dir", "잘못된 방향");
  eq(g.state.off, 0 + 1 + 1 - 1 - 1, "net 이동 = 합산");
  ok(g.push(1, 1, 5999).ok, "마감 직전 밀기 OK");
  eq(g.push(1, 1, 6000).reason, "inactive", "마감 시각 이후 거부");
})();

// ---- 5. 브레이크: cap (라운드 시작 위치 기준) ----
(() => {
  const g = mk({ rng: B.mulberry32(2), brake: "cap", cap: 2 });
  g.begin(0);
  ok(g.push(0, 1, 1).ok && g.push(0, 1, 2).ok, "2칸까지 OK");
  eq(g.push(0, 1, 3).reason, "cap", "3칸째는 거부");
  eq(g.state.off, 2, "거부된 밀기는 안 움직임");
  ok(g.push(1, -1, 4).ok && g.push(1, -1, 5).ok && g.push(1, -1, 6).ok && g.push(1, -1, 7).ok, "반대로는 -2까지 가능(되돌려 놓고 더)");
  eq(g.state.off, -2, "하한 -2");
  eq(g.push(1, -1, 8).reason, "cap", "-3은 거부");
  g.tick(5000); g.next();
  g.begin(6000);
  eq(g.state.startOff, -2, "다음 라운드는 멈춘 자리에서 시작");
  ok(g.push(0, 1, 6100).ok && g.push(0, 1, 6200).ok, "새 라운드는 멈춘 자리(-2) 기준 ±2: 0까지 2칸 OK");
  eq(g.push(0, 1, 6300).reason, "cap", "그 이상 거부 (이전 라운드 기준이 아님)");
  ok(g.push(1, -1, 6400).ok && g.push(1, -1, 6500).ok && g.push(1, -1, 6600).ok && g.push(1, -1, 6700).ok, "반대로는 -4까지 4칸");
  eq(g.push(1, -1, 6800).reason, "cap", "-4 아래 거부");
})();

// ---- 6. 브레이크: free ----
(() => {
  const g = mk({ rng: B.mulberry32(2), brake: "free" });
  g.begin(0);
  for (let i = 0; i < 200; i++) ok(g.push(0, 1, i).ok, "free는 제한 없음");
  eq(g.state.off, 200, "200칸");
})();

// ---- 7. 점수: fixed ----
(() => {
  const g = mk({ rng: B.mulberry32(9), brake: "free" });
  g.begin(0);
  g.state.targets = [g.eatenBy(0), g.eatenBy(1)];   // 둘 다 이미 자기 앞에 와 있는 상태
  const r = g.tick(5000);
  eq(r.success, [true, true], "둘 다 성공(동시 만족)");
  const t0 = B.PLATES6[r.eaten[0]].tier, t1 = B.PLATES6[r.eaten[1]].tier;
  eq(r.points, [g.cfg.tierPoints[t0], g.cfg.tierPoints[t1]], "가격대 점수");
  eq(g.state.phase, "result", "result 단계");
  g.next();
  eq(g.state.phase, "idle", "다음 라운드 대기");
  g.begin(6000);
  g.state.targets = [(g.eatenBy(0) + 1) % 6, (g.eatenBy(1) + 1) % 6];
  const r2 = g.tick(11000);
  eq(r2.success, [false, false], "둘 다 실패");
  eq(r2.points, [0, 0], "실패는 0점");
  eq(g.state.scores[0], r.points[0], "누적 점수");
  eq(g.summary().both, 1, "summary both"); eq(g.summary().none, 1, "summary none");
})();

// ---- 8. 자리 규칙 any: 기준 칸(seats[0])의 접시를 둘 다 먹는다 ----
(() => {
  const g = mk({ rng: B.mulberry32(9), brake: "free", seatRule: "any" });
  g.begin(0);
  eq(g.eatenBy(0), g.eatenBy(1), "any: 둘이 먹는 접시가 같다");
  g.state.targets = [g.eatenBy(0), g.eatenBy(0)];
  eq(g.tick(5000).success, [true, true], "any: 같은 맛을 원하면 둘 다 성공");
  g.next(); g.begin(6000);
  const t = g.eatenBy(0);
  g.state.targets = [t, (t + 1) % 6];
  eq(g.tick(11000).success, [true, false], "any: 다른 맛이면 한쪽만");
  g.next(); g.begin(12000);
  eq(g.stepsToSeat(g.state.targets[1], 1), g.stepsToSeat(g.state.targets[1], 0), "any: 목표 칸이 자리와 무관");
})();

// ---- 9. 7라운드 진행과 종료 ----
(() => {
  const g = mk({ rng: B.mulberry32(3) });
  for (let r = 1; r <= g.cfg.rounds; r++) {
    ok(g.begin(r * 10000), `round ${r} begin`);
    eq(g.state.round, r, "round 번호");
    ok(!g.begin(r * 10000 + 1), "active 중 begin 거부");
    eq(g.tick(r * 10000 + 4999), null, "마감 전 tick은 아무 일 없음");
    ok(g.tick(r * 10000 + 5000), "마감 시 결과");
    ok(g.next(), "next");
  }
  eq(g.state.phase, "end", "7라운드 후 end");
  ok(!g.begin(999999), "end 후 begin 거부");
  eq(g.state.history.length, 7, "기록 7개");
})();

// ---- 9b. deal: 라운드 시작 전에 주문을 미리 뽑는다 ----
(() => {
  const g = mk({ rng: B.mulberry32(4) });
  ok(g.deal(), "idle에서 deal");
  const t = g.state.targets.slice();
  ok(!g.deal(), "이미 뽑았으면 다시 안 뽑음");
  g.begin(0);
  eq(g.state.targets, t, "begin은 미리 뽑은 주문을 그대로 쓴다");
  eq(g.state.dealt, false, "begin 후 dealt 해제");
  g.tick(5000); g.next();
  ok(g.deal(), "다음 라운드는 새로 뽑는다");
})();

// ---- 9c. endJitter: 실제 종료 시각은 roundMs ±jitter 안에서 무작위, 그 전엔 끝나지 않는다 ----
(() => {
  const g = B.create({ rng: B.mulberry32(8), endJitter: 1000 });
  const ends = new Set();
  for (let r = 0; r < g.cfg.rounds; r++) {
    g.begin(r * 20000);
    const d = g.state.endAt - r * 20000;
    ok(d >= 4000 && d <= 6000, "종료는 4000..6000ms 사이: " + d);
    eq(g.state.earliestEnd - r * 20000, 4000, "가장 이른 종료 = roundMs - jitter");
    ends.add(d);
    eq(g.tick(r * 20000 + 3999), null, "가장 이른 시각 전에는 끝나지 않는다");
    ok(g.push(0, 1, r * 20000 + 3999).ok, "끝나기 전 밀기 OK");
    ok(g.tick(r * 20000 + 6000), "6000ms에는 반드시 끝난다");
    g.next();
  }
  ok(ends.size > 1, "라운드마다 종료 시각이 다르다");
})();

// ---- 10. 봇 전체 시뮬레이션: 규칙별로 벨트가 어떻게 되는지 (판단용 숫자) ----
function sim(cfg, botA, botB, games, seed) {
  const rng = B.mulberry32(seed), out = { both: 0, one: 0, none: 0, moved: 0, scoreDiff: 0, rounds: 0, used: 0 };
  for (let k = 0; k < games; k++) {
    const g = B.create(Object.assign({ rng }, cfg.__shared ? {} : cfg.__new ? FIXED12 : CLASSIC, cfg)), a = B.makeBot(g, 0, botA, rng), b = B.makeBot(g, 1, botB, rng);
    let now = 0;
    while (g.state.phase !== "end") {
      if (g.state.phase === "idle") g.begin(now);
      for (let t = 0; t < 8000; t += 25) { now += 25; if ((now / 25) % 2) { a.step(now); b.step(now); } else { b.step(now); a.step(now); } g.tick(now); if (g.state.phase !== "active") break; }
      g.tick(now + 1);
      if (g.state.phase === "result") g.next();
    }
    const s = g.summary();
    out.both += s.both; out.one += s.one; out.none += s.none; out.moved += s.avgMoved; out.rounds += s.rounds;
    out.scoreDiff += s.scores[0] - s.scores[1]; out.used += (s.used[0] + s.used[1]) / 2;
  }
  out.moved /= games; out.scoreDiff /= games; out.used /= games;
  return out;
}
(() => {
  const same = { rate: 3 };
  const free = sim({ brake: "free", endJitter: 0 }, same, same, 200, 11);
  const budget = sim({ brake: "budget", budget: 36, endJitter: 0 }, same, same, 200, 11);
  const cap = sim({ brake: "cap", cap: 3, endJitter: 0 }, same, same, 200, 11);
  console.log("시뮬레이션(봇 vs 봇, 같은 실력 초당 3회, 200판): 7라운드 합계 / 라운드당 평균 이동 칸 / 사람당 밀기 사용");
  for (const [nm, r] of [["free", free], ["budget36", budget], ["cap3", cap]]) console.log(`  ${nm.padEnd(8)} 둘다 ${r.both} 한쪽 ${r.one} 둘다실패 ${r.none} (판수 200) 평균이동 ${r.moved.toFixed(2)} 사용 ${r.used.toFixed(1)} 점수차 ${r.scoreDiff.toFixed(2)}`);
  ok(free.rounds === 1400 && budget.rounds === 1400, "봇 시뮬레이션이 매 판 7라운드를 끝낸다");
  ok(Math.abs(budget.scoreDiff) < 1.5, "같은 실력이면 평균 점수차가 작다 (자리 위치로 인한 편향 없음): " + budget.scoreDiff);
  // 연타가 더 빠른 쪽이 이기는가 (실력 차이가 결과를 얼마나 좌우하는가)
  const fast = sim({ brake: "budget", budget: 36, endJitter: 0 }, { rate: 6 }, { rate: 3 }, 200, 21);
  const fastFree = sim({ brake: "free", endJitter: 0 }, { rate: 6 }, { rate: 3 }, 200, 21);
  console.log(`  연타 2배 차이 -- budget36 점수차(빠른 쪽 - 느린 쪽) ${fast.scoreDiff.toFixed(2)} / free ${fastFree.scoreDiff.toFixed(2)}`);
})();

// ---- 12. 12칸 8종 배치 (현재 기본값) ----
(() => {
  const P = B.PLATES, N = P.length, K = B.KINDS.length;
  eq(N, 12, "접시 12개"); eq(K, 8, "맛 8종");
  eq(new Set(P.map((p) => p.kind)).size, 8, "벨트에 8종이 모두 있다");
  for (let i = 0; i < N / 2; i++) eq(P[i].tier, P[i + N / 2].tier, `정반대 쌍 ${i}-${i + 6} 같은 가격대`);
  const byKind = {}; P.forEach((p, i) => (byKind[p.kind] = byKind[p.kind] || []).push(i));
  const dups = Object.values(byKind).filter((a) => a.length > 1);
  eq(dups.length, 4, "4종은 2개씩");
  dups.forEach((a) => { eq(a.length, 2, "복사본 2개"); eq(Math.min((a[1] - a[0] + N) % N, (a[0] - a[1] + N) % N), 3, "복사본은 3칸 떨어져 있다"); ok((a[1] - a[0] + N) % N !== N / 2, "복사본이 정반대에 놓이지 않는다"); });
  eq(Object.values(byKind).filter((a) => a.length === 1).length, 4, "4종은 1개씩");
  // 가격대 분포: 흰 4 / 파랑 4 / 금 4
  eq([1, 2, 3].map((t) => P.filter((p) => p.tier === t).length), [4, 4, 4], "가격대별 접시 4개씩");
})();

(() => {
  // optionsToSeat: 같은 맛 복사본은 길이 둘, 가까운 순. 그만큼 밀면 정말 도착한다.
  const N = 12;
  for (let off = -5; off <= 5; off += 5) for (let kind = 0; kind < 8; kind++) for (let seat = 0; seat < 2; seat++) {
    const g = mk12({ rng: B.mulberry32(1), brake: "free" }); g.begin(0); g.state.off = off;
    const opts = g.optionsToSeat(kind, seat), copies = B.PLATES.filter((p) => p.kind === kind).length;
    eq(opts.length, copies, `맛 ${kind} 복사본 수`);
    ok(opts.length < 2 || Math.abs(opts[0].steps) <= Math.abs(opts[1].steps), "가까운 순");
    eq(g.stepsToSeat(kind, seat), opts[0].steps, "stepsToSeat = 가장 가까운 길");
    ok(Math.abs(opts[0].steps) <= N / 2, "한 방향으로 최대 6칸");
    opts.forEach((o) => {
      const g2 = mk12({ rng: B.mulberry32(1), brake: "free" }); g2.begin(0); g2.state.off = off;
      for (let i = 0; i < Math.abs(o.steps); i++) g2.push(0, o.steps > 0 ? 1 : -1, 1);
      eq(g2.eatenBy(seat), o.plate, `맛 ${kind}의 복사본 ${o.plate}를 자리 ${seat}로 ${o.steps}칸 밀어서 도착`);
    });
  }
  // 같은 맛 접시 아무거나 먹어도 성공, 점수는 먹은 접시 기준
  const g = mk12({ rng: B.mulberry32(1), brake: "free" }); g.begin(0);
  const kindAt0 = B.PLATES[g.eatenBy(0)].kind;
  g.state.targets = [kindAt0, (kindAt0 + 1) % 8];
  const r = g.tick(5000);
  eq(r.success[0], true, "맛이 같으면 성공"); eq(r.points[0], g.cfg.tierPoints[B.PLATES[r.eaten[0]].tier], "먹은 접시의 가격대 점수");
})();

(() => {
  // 협력 주문 배정: coopDeal 1이면 항상 두 사람이 동시에 맞출 길이 있다 / 0이면 독립 무작위
  const canBoth = (g) => { for (let s = 0; s < g.N; s++) { const off = g.state.off + s; if (g.cfg.plates[B.mod(g.cfg.seats[0] - off, g.N)].kind === g.state.targets[0] && g.cfg.plates[B.mod(g.cfg.seats[1] - off, g.N)].kind === g.state.targets[1]) return true; } return false; };
  function rate(cfg, trials) {
    const rng = B.mulberry32(77); let hit = 0;
    for (let t = 0; t < trials; t++) {
      const g = mk12(Object.assign({ rng, brake: "free" }, cfg)); g.state.off = Math.floor(rng() * 40) - 20; g.deal();
      if (canBoth(g)) hit++;
    }
    return hit / trials;
  }
  eq(rate({ coopDeal: 1 }, 2000), 1, "coopDeal=1: 항상 동시에 맞출 길이 있다");
  const r0 = rate({ coopDeal: 0 }, 20000), r3 = rate({ coopDeal: 0.3 }, 20000);
  console.log(`동시에 맞출 수 있는 주문 쌍 비율: coopDeal 0 -> ${r0.toFixed(3)} / 0.3 -> ${r3.toFixed(3)} / 1 -> 1.000 (6칸 6종 기준은 0.167)`);
  ok(r0 > 0.12 && r0 < 0.24, "무작위 배정이면 약 18%: " + r0);
  ok(r3 > r0 + 0.15, "coopDeal 0.3이면 눈에 띄게 늘어난다: " + r3);
  // 어디서든(any) 규칙에서 coopDeal=1이면 둘의 주문이 같은 맛이 된다
  const g = mk12({ rng: B.mulberry32(3), seatRule: "any", coopDeal: 1 }); g.deal();
  eq(g.state.targets[0], g.state.targets[1], "any 규칙: 맞물리는 주문 = 같은 맛");
})();

(() => {
  // 12칸 기본 설정으로 한 판이 끝까지 간다 + 봇 시뮬레이션 숫자
  const bots = { rate: 3 };
  const d0 = sim({ __new: true, endJitter: 0, coopDeal: 0 }, bots, bots, 300, 5);
  const d3 = sim({ __new: true, endJitter: 0, coopDeal: 0.3 }, bots, bots, 300, 5);
  const dFree = sim({ __new: true, endJitter: 0, coopDeal: 0.3, brake: "free" }, bots, bots, 300, 5);
  console.log("12칸 8종 봇 시뮬레이션 (같은 실력 초당 3회, 300판, 7라운드): 둘다 먹음 / 한쪽만 / 둘 다 실패 -- 판당 평균 라운드 수");
  for (const [nm, r] of [["coopDeal 0  ", d0], ["coopDeal 0.3", d3], ["0.3, 제한없음", dFree]]) console.log(`  ${nm} 둘다 ${(r.both / 300).toFixed(2)} 한쪽 ${(r.one / 300).toFixed(2)} 실패 ${(r.none / 300).toFixed(2)} / 평균이동 ${r.moved.toFixed(2)} 밀기사용 ${r.used.toFixed(1)}/48`);
  ok(d0.rounds === 2100 && d3.rounds === 2100, "300판 x 7라운드");
  ok(d3.both > d0.both * 1.3, "coopDeal이 봇 사이의 동시 만족도 늘린다");
})();

// ---- 12b. 한 칸 공유 (현재 기본값) ----
(() => {
  const g = mkShared({ rng: B.mulberry32(2) });
  eq(g.cfg.seatRule, "any", "기본 규칙은 한 칸 공유"); eq(g.cfg.seats, [9, 3], "공유 칸 = 슬롯 9 (6시 방향)");
  g.begin(0);
  eq(g.eatenBy(0), g.eatenBy(1), "두 사람이 같은 접시를 본다");
  for (let off = -7; off <= 7; off++) { g.state.off = off; eq(g.eatenBy(0), g.plateAt(9), "먹는 칸은 항상 슬롯 9"); }
  g.state.off = 0;
  const kind = B.PLATES[g.eatenBy(0)].kind;
  g.state.targets = [kind, kind];
  const r = g.tick(g.state.endAt);
  eq(r.success, [true, true], "같은 맛을 원하는 두 사람은 둘 다 성공 (같은 접시, 각자 점수)");
  eq(r.points[0], r.points[1], "점수도 같다");
  // 서로 다른 맛이면 최대 한 사람만
  g.next(); g.begin(100000);
  const k0 = B.PLATES[g.eatenBy(0)].kind;
  g.state.targets = [k0, (k0 + 1) % 8];
  const r2 = g.tick(g.state.endAt);
  eq(r2.success, [true, false], "서로 다른 맛이면 멈춘 접시와 맞는 사람만");
  // 가까운 길 계산이 공유 칸 기준: 두 사람이 같은 맛을 원하면 같은 길
  g.next(); g.begin(200000);
  g.state.targets = [3, 3];
  eq(g.stepsToSeat(3, 0), g.stepsToSeat(3, 1), "같은 맛 -> 같은 길");
  g.state.targets = [3, 4];
  const o0 = g.optionsToSeat(3, 0), o1 = g.optionsToSeat(4, 1);
  ok(o0.length === 1 && o1.length === 1, "연어알/장어 등 1개짜리");
})();

(() => {
  // 한 칸 공유에서의 봇 시뮬레이션: 결과 분포를 눈으로 본다
  const bots = { rate: 3 };
  const r0 = sim({ __shared: true, endJitter: 0, coopDeal: 0 }, bots, bots, 300, 5);
  const r3 = sim({ __shared: true, endJitter: 0 }, bots, bots, 300, 5);
  const rr = sim({ __shared: true, endJitter: 0, brake: "free" }, bots, bots, 300, 5);
  console.log("한 칸 공유 봇 시뮬레이션 (12칸 8종, 같은 실력 초당 3회, 300판, 판당 평균 라운드 수): 둘 다 먹음 / 한쪽만 / 아무도 못 먹음");
  for (const [nm, r] of [["coopDeal 0  ", r0], ["coopDeal 0.3", r3], ["0.3, 제한없음", rr]]) console.log(`  ${nm} 둘다 ${(r.both / 300).toFixed(2)} 한쪽 ${(r.one / 300).toFixed(2)} 아무도 ${(r.none / 300).toFixed(2)} / 평균이동 ${r.moved.toFixed(2)} 밀기사용 ${r.used.toFixed(1)}`);
  ok(r3.rounds === 2100, "300판 x 7라운드");
  ok(r3.both > r0.both * 1.5, "공유 칸에서도 coopDeal이 같은 맛 주문을 늘려 동시 성공이 늘어난다");
})();

// ---- 11. 막판 매복 시뮬레이션: 종료 시각을 숨기면 매복이 얼마나 약해지는가 ----
(() => {
  // 매복형: 자기가 아는 "정해진 종료 시각"(roundMs) 직전 win ms 동안에만 초당 8회로 반응한다 (jitter는 모른다)
  const mkSniper = (win) => (g, seat, rng) => { const inner = B.makeBot(g, seat, { rate: 8, thrift: 99 }, rng); return { step: (now) => (g.state.phase !== "active" || now < g.state.roundStart + g.cfg.roundMs - win) ? 0 : inner.step(now) }; };
  function duel(cfg, games, seed, win) {
    const rng = B.mulberry32(seed); let d = 0;
    for (let k = 0; k < games; k++) {
      const g = B.create(Object.assign({ rng }, cfg.__shared ? {} : cfg.__new ? FIXED12 : CLASSIC, cfg)), a = mkSniper(win)(g, 0, rng), b = B.makeBot(g, 1, { rate: 3 }, rng);
      let now = 0;
      while (g.state.phase !== "end") {
        if (g.state.phase === "idle") g.begin(now);
        for (let t = 0; t < 8000; t += 20) { now += 20; if ((now / 20) % 2) { a.step(now); b.step(now); } else { b.step(now); a.step(now); } g.tick(now); if (g.state.phase !== "active") break; }
        g.tick(now + 1); if (g.state.phase === "result") g.next();
      }
      d += g.state.scores[0] - g.state.scores[1];
    }
    return d / games;
  }
  const fixedEnd = duel({ brake: "budget", budget: 36, endJitter: 0 }, 600, 41, 700);
  const hidden = duel({ brake: "budget", budget: 36, endJitter: 1000 }, 600, 41, 700);
  console.log(`막판 매복(마지막 0.7초만 초당 8회) vs 보통 봇, 점수차(매복 - 보통): 종료 시각 고정 ${fixedEnd.toFixed(2)} / 종료 ±1초 숨김 ${hidden.toFixed(2)}`);
  ok(fixedEnd > 3, "종료 시각이 고정이면 매복이 압도적으로 유리하다(규칙 결함의 증거): " + fixedEnd);
  ok(hidden < fixedEnd * 0.75 && hidden > 0, "종료 시각을 숨기면 매복 이점이 줄어들지만(약 절반) 없어지지는 않는다: " + hidden + " vs " + fixedEnd);
})();

// ---- 13. 색 모드: 10색 접시, 주문 종류(일반/지정/중급/특선), 무늬 ----
(() => {
  const P = B.PLATES_COLOR, N = P.length, ci = (a, b) => Math.min((a - b + N) % N, (b - a + N) % N);
  eq(N, 10, "색 모드 벨트 10칸");
  eq(new Set(P.map((p) => p.kind)).size, 10, "색 10가지가 한 장씩");
  eq(B.COLORS.map((c) => c.name), ["빨강", "주황", "노랑", "초록", "파랑", "보라", "분홍", "흰색", "검정", "회색"], "색 이름 (사용자 지정 10색)");
  for (let q = 0; q < 5; q++) {
    const idx = P.map((p, i) => (p.pattern === q ? i : -1)).filter((i) => i >= 0);
    eq(idx.length, 2, `무늬 ${q}는 접시 두 장`);
    ok(ci(idx[0], idx[1]) >= 4, `같은 무늬 두 장은 4칸 이상 떨어짐 (${idx})`);
  }
  for (let i = 0; i < N; i++) ok(P[i].pattern !== P[(i + 1) % N].pattern, `이웃 접시 무늬가 다르다 ${i}`);
  eq(Object.keys(B.ORDER_TYPES).map((k) => B.ORDER_TYPES[k].points), [2, 3, 5, 10], "점수 = 원래 보상금 비율 (일반 2 / 지정 3 / 중급 5 / 특선 10)");
  const mkC = (o) => B.create(Object.assign({ rng: B.mulberry32(3) }, B.PRESET_COLOR, o));
  // 주문 구조: 종류별로 받아 주는 접시 수
  const counts = { normal: 0, fixed: 0, fragile: 0, valuable: 0 }, fx = { color: 0, pattern: 0 }, sushiSeen = {};
  const g = mkC({ coopDeal: 0 });
  for (let k = 0; k < 6000; k++) {
    g.state.dealt = false; g.state.phase = "idle"; g.deal();
    for (const o of g.state.orders) {
      counts[o.type]++;
      if (o.type === "normal") { eq(o.colors.length, 2, "일반: 두 색"); eq(o.plates.length, 2, "일반: 접시 2장"); ok(o.colors[0] !== o.colors[1], "일반: 서로 다른 두 색"); }
      else if (o.type === "fixed") { if (o.pattern != null) { fx.pattern++; eq(o.plates.length, 2, "지정(무늬): 같은 무늬 2장"); eq(o.colors.length, 0, "지정(무늬): 색 없음"); } else { fx.color++; eq(o.plates.length, 1, "지정(색): 접시 1장"); } }
      else { eq(o.colors.length, 1, o.type + ": 정확히 한 색"); eq(o.plates.length, 1, o.type + ": 접시 1장"); }
      eq(o.points, B.ORDER_TYPES[o.type].points, "주문 점수");
      ok(B.ORDER_TYPES[o.type].sushis.indexOf(o.sushi) >= 0, `${o.type} 주문의 초밥은 그 급의 목록 안: ${o.sushi}`);
      sushiSeen[o.sushi] = (sushiSeen[o.sushi] || 0) + 1;
    }
  }
  const tot = counts.normal + counts.fixed + counts.fragile + counts.valuable, wsum = 17;
  for (const [k, w] of [["normal", 4], ["fixed", 6], ["fragile", 4], ["valuable", 3]]) ok(Math.abs(counts[k] / tot - w / wsum) < 0.03, `${k} 비율 ${(counts[k] / tot).toFixed(3)} ~ ${(w / wsum).toFixed(3)}`);
  ok(Math.abs(fx.color / (fx.color + fx.pattern) - 0.5) < 0.05, "지정 주문은 색/무늬가 반반");
  eq(Object.keys(sushiSeen).sort(), ["eel", "egg", "ikura", "octopus", "salmon", "shrimp", "tofu", "tuna"], "여덟 가지 초밥이 모두 주문표에 나온다");
  eq(B.ORDER_TYPES.normal.sushis, ["egg", "tofu"], "일반 = 계란/유부 (쉬운 초밥)");
  ok(B.ORDER_TYPES.valuable.sushis.indexOf("eel") >= 0, "특선(귀중품)에 장어");
  // 판정: 받아 주는 접시가 먹는 칸에 서면 성공, 점수는 주문 종류 점수. 아니면 실패.
  for (let k = 0; k < 200; k++) {
    const h = mkC({ coopDeal: 0, brake: "free", rng: B.mulberry32(100 + k) }); h.begin(0);
    const o0 = h.state.orders[0], o1 = h.state.orders[1];
    const res = (h.tick(99999), h.state.history[0]);
    const e = h.eatenBy(0);
    eq(res.success[0], o0.plates.indexOf(e) >= 0, "성공 여부 = 먹은 접시가 주문에 포함");
    eq(res.points[0], res.success[0] ? o0.points : 0, "점수");
    eq(res.success[1], o1.plates.indexOf(e) >= 0, "한 칸 공유: 둘 다 같은 접시와 비교");
  }
  // 정확히 밀면 성공: 가까운 허용 접시까지 steps만큼 밀면 먹는 칸에 선다
  for (let k = 0; k < 100; k++) {
    const h = mkC({ coopDeal: 0, brake: "free", rng: B.mulberry32(500 + k) }); h.begin(0);
    const opt = h.optionsToOrder(0)[0];
    for (let i = 0; i < Math.abs(opt.steps); i++) h.push(0, opt.steps > 0 ? 1 : -1, 10);
    ok(h.accepts(0, h.eatenBy(0)), "가까운 허용 접시로 밀면 주문이 맞는다");
  }
  // coopDeal 1: 둘의 주문이 같은 접시를 동시에 받아 준다 (한 칸 공유 -> 동시에 맞출 길이가 항상 있다)
  for (let k = 0; k < 300; k++) {
    const h = mkC({ coopDeal: 1, rng: B.mulberry32(900 + k) }); h.deal();
    const a = new Set(h.state.orders[0].plates); ok(h.state.orders[1].plates.some((p) => a.has(p)), "coopDeal 1: 두 주문이 겹치는 접시가 있다");
  }
  // 봇 시뮬레이션: 주문 종류가 섞인 색 모드. 허용 접시가 둘이면 가까운 쪽으로 간다.
  function csim(cfg, games, seed) {
    const rng = B.mulberry32(seed), o = { both: 0, one: 0, none: 0, pts: 0, used: 0, rounds: 0 };
    for (let k = 0; k < games; k++) {
      const gg = B.create(Object.assign({ rng, endJitter: 0 }, B.PRESET_COLOR, cfg)), a = B.makeBot(gg, 0, { rate: 3 }, rng), b = B.makeBot(gg, 1, { rate: 3 }, rng);
      let now = 0;
      while (gg.state.phase !== "end") {
        if (gg.state.phase === "idle") gg.begin(now);
        for (let t = 0; t < 8000; t += 25) { now += 25; a.step(now); b.step(now); gg.tick(now); if (gg.state.phase !== "active") break; }
        gg.tick(now + 1); if (gg.state.phase === "result") gg.next();
      }
      const sm = gg.summary(); o.both += sm.both; o.one += sm.one; o.none += sm.none; o.rounds += sm.rounds; o.pts += sm.scores[0] + sm.scores[1]; o.used += (sm.used[0] + sm.used[1]) / 2;
    }
    for (const q of ["both", "one", "none", "pts", "used"]) o[q] /= games;
    return o;
  }
  const c0 = csim({ coopDeal: 0 }, 300, 7), c3 = csim({ coopDeal: 0.3 }, 300, 7);
  console.log("색 모드 봇 시뮬레이션 (10색 한 칸 공유, 주문 4종, 300판, 판당 평균 라운드): 둘 다 / 한쪽만 / 아무도 -- 합계점 / 밀기");
  console.log(`  coopDeal 0   둘다 ${c0.both.toFixed(2)} 한쪽 ${c0.one.toFixed(2)} 아무도 ${c0.none.toFixed(2)} / 합계점 ${c0.pts.toFixed(1)} 밀기 ${c0.used.toFixed(1)}/48`);
  console.log(`  coopDeal 0.3 둘다 ${c3.both.toFixed(2)} 한쪽 ${c3.one.toFixed(2)} 아무도 ${c3.none.toFixed(2)} / 합계점 ${c3.pts.toFixed(1)} 밀기 ${c3.used.toFixed(1)}/48`);
  eq(Math.round(c0.both * 300 + c0.one * 300 + c0.none * 300), 2100, "라운드 수 합");
  ok(c3.both > c0.both * 1.5, "coopDeal이 색 모드에서도 동시 성공을 늘린다");
})();

console.log(`[test-core] ALL CHECKS PASSED (${n} assertions)`);
