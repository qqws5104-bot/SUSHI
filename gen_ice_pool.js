// 초밥 담기(ice) 판 생성기 -- 사용: node gen_ice_pool.js <가로> <세로> <판수> <P개수> <최소슬라이드> <최대슬라이드> [시드]
// 무작위로 벽을 깔고 BFS로 최적 미끄러짐 수를 재서, 범위 안이고 풀리는 판만 모은다. 출력은 minigames.js의 ICE_POOL 한 레벨 배열 형식(JSON 줄들).
"use strict";
const { iceSolve } = require("./test_puzzle_solvers.js");
const [W, H, N, NP, LO, HI, SEED] = process.argv.slice(2).map(Number);
let s = (SEED || 12345) >>> 0;
const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
const ri = (n) => Math.floor(rnd() * n);
const out = [], seen = new Set();
let tries = 0;
while (out.length < N && tries < 400000) {
  tries++;
  const g = [];
  for (let y = 0; y < H; y++) { const r = []; for (let x = 0; x < W; x++) r.push(rnd() < 0.2 ? "#" : " "); g.push(r); }
  const free = () => { for (;;) { const x = ri(W), y = ri(H); if (g[y][x] === " ") return [x, y]; } };
  const put = (ch) => { const [x, y] = free(); g[y][x] = ch; return [x, y]; };
  const [sx, sy] = put("S"), [gx, gy] = put("G");
  if (Math.abs(sx - gx) + Math.abs(sy - gy) < 4) continue;
  for (let k = 0; k < NP; k++) put("P");
  const rows = g.map((r) => r.join(""));
  const sol = iceSolve(rows);
  if (!sol || sol.length < LO || sol.length > HI) continue;
  const key = rows.join("|"); if (seen.has(key)) continue; seen.add(key);
  out.push({ rows, len: sol.length });
}
console.error(`${out.length}판 (시도 ${tries}) 최적 슬라이드: ` + out.map((o) => o.len).join(","));
console.log("[" + out.map((o) => "[" + o.rows.map((r) => JSON.stringify(r)).join(", ") + "]").join(",\n ") + "]");
