// 색 모드 봇 시뮬레이션: 색 10종(10칸 1장씩) vs 색 6종(12칸 2장씩). node sim_color.js
"use strict";
const B = require("./belt-core.js");
function plates(layout) { return layout.map((c) => ({ key: B.COLORS[c].key, name: B.COLORS[c].name, tier: 1, kind: c })); }
const P10 = B.PLATES_COLOR, P6 = plates([0, 1, 2, 3, 4, 5, 3, 4, 5, 0, 1, 2]);
function sim(cfg, games, seed) {
  const rng = B.mulberry32(seed), o = { both: 0, one: 0, none: 0, moved: 0, used: 0, pts: 0 };
  for (let k = 0; k < games; k++) {
    const g = B.create(Object.assign({ rng, pointsBy: "order", seatRule: "any", endJitter: 0 }, cfg));
    const a = B.makeBot(g, 0, { rate: 3 }, rng), b = B.makeBot(g, 1, { rate: 3 }, rng);
    let now = 0;
    while (g.state.phase !== "end") {
      if (g.state.phase === "idle") g.begin(now);
      for (let t = 0; t < 8000; t += 25) { now += 25; a.step(now); b.step(now); g.tick(now); if (g.state.phase !== "active") break; }
      g.tick(now + 1); if (g.state.phase === "result") g.next();
    }
    const s = g.summary();
    o.both += s.both; o.one += s.one; o.none += s.none; o.moved += s.avgMoved; o.used += (s.used[0] + s.used[1]) / 2; o.pts += s.scores[0] + s.scores[1];
  }
  for (const k in o) o[k] /= games;
  return o;
}
const f = (r) => `둘다 ${r.both.toFixed(2)} 한쪽 ${r.one.toFixed(2)} 아무도 ${r.none.toFixed(2)} / 평균이동 ${r.moved.toFixed(2)} 밀기 ${r.used.toFixed(1)}/48 / 합계점 ${r.pts.toFixed(1)}`;
console.log("색 모드, 한 칸 공유, 봇 초당 3회, 300판, 판당 평균 라운드 수 (7라운드)");
for (const cd of [0, 0.3]) {
  console.log(`  coopDeal ${cd}`);
  console.log("    10색 x 1장(10칸):", f(sim({ plates: P10, seats: [0, 5], coopDeal: cd }, 300, 7)));
  console.log("     6색 x 2장(12칸):", f(sim({ plates: P6, seats: [9, 3], coopDeal: cd }, 300, 7)));
}
module.exports = { sim };
